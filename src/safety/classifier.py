"""
Safety classifier for the medicine assistant.

This gate runs BEFORE any retrieval or generation. Its job is to sort
every incoming query into exactly one of three categories:

    "lookup"          -- factual question about a registered drug
                         (what it's for, generic equivalents, listed
                         side effects/interactions). Proceeds to RAG.
    "advice_seeking"  -- personalized dosing, "should I take X",
                         symptom-based diagnosis-seeking. NEVER reaches
                         generation -- returns a fixed canned response.
    "out_of_scope"    -- unrelated to medicines entirely. Returns a
                         fixed canned response.

Design choice: "advice_seeking" is caught by a rule-based keyword/regex
pass FIRST, before any LLM call. This is deliberate -- the
highest-stakes category should not depend on an LLM classifying
correctly. The rules are tuned for high recall (catch as many real
cases as possible, tolerate some false positives) since a false
positive here just means an extra "see a doctor" message, which is
never a harmful outcome.

Only queries that pass the rule-based check go to the LLM to split
between "lookup" and "out_of_scope", since that distinction genuinely
needs language understanding.

Fails closed: if the LLM call errors or returns something unparseable,
the query is treated as unresolvable and generation does NOT proceed.
"""

import os
import re
import json
import logging
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# NOTE: llama-3.1-8b-instant was shut down by Groq on 2026-08-16.
# openai/gpt-oss-20b is the current recommended replacement in that
# fast/cheap tier. Verify at console.groq.com/docs/models if this
# ever 404s again.
GROQ_MODEL = "openai/gpt-oss-20b"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# High-recall patterns for personalized advice-seeking. Deliberately
# broad -- false positives are acceptable here, false negatives are not.
ADVICE_SEEKING_PATTERNS = [
    r"\bshould i (take|use|stop|start)\b",
    r"\bcan i take\b",
    r"\bis it (safe|ok|okay) for me\b",
    r"\bam i (allowed|able) to\b",
    r"\bwhat (dose|dosage) should i\b",
    r"\bhow much (should|can) i take\b",
    r"\bhow many .* should i take\b",
    r"\bi('m| am) (taking|on)\b.*\b(and|with)\b",  # combo-drug personal check
    r"\bmy (doctor|prescription|symptoms?)\b",
    r"\bdo i have\b",
    r"\bwhat('s| is) wrong with me\b",
    r"\bis this (safe|dangerous) for (my|me)\b",
    r"\bcan i (mix|combine)\b",
    r"\bi feel\b.*\b(should|need)\b",
]

_ADVICE_RE = re.compile("|".join(ADVICE_SEEKING_PATTERNS), re.IGNORECASE)


@dataclass
class ClassificationResult:
    category: str  # "lookup" | "advice_seeking" | "out_of_scope" | "error"
    reasoning: str = ""


def _rule_based_check(query: str) -> bool:
    """Returns True if the query matches an advice-seeking pattern."""
    return bool(_ADVICE_RE.search(query))


LLM_CLASSIFIER_SYSTEM_PROMPT = """You classify questions for a Pakistani medicine information assistant. The assistant gives factual, reference-only information about registered drugs -- it never gives personalized medical advice.

Classify the user's question into exactly one category:

"lookup" -- a factual question about a specific medicine: what it's for, its generic equivalents, its officially listed side effects or interactions, its composition, its registration status. Also counts if it names a drug and asks a general factual question about it.

"out_of_scope" -- anything not about a specific medicine or drug information at all (general chit-chat, unrelated topics, requests for code, etc).

Respond with ONLY a JSON object, nothing else: {"category": "lookup" or "out_of_scope", "reasoning": "one short phrase"}

Note: questions asking for personalized advice ("should I take X", dosing for a specific person, diagnosis) are handled separately and will never reach you -- you only need to distinguish drug-information lookups from unrelated questions."""


def _llm_classify(query: str) -> ClassificationResult:
    if not GROQ_API_KEY:
        log.error("GROQ_API_KEY not set in environment.")
        return ClassificationResult(category="error", reasoning="no API key configured")

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "temperature": 0,
                "max_tokens": 100,
                "messages": [
                    {"role": "system", "content": LLM_CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
            },
            timeout=10,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Model may wrap JSON in markdown fences despite instructions.
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(content)

        category = parsed.get("category")
        if category not in ("lookup", "out_of_scope"):
            log.warning(f"LLM returned unexpected category: {category!r}")
            return ClassificationResult(category="error", reasoning="invalid category from LLM")

        return ClassificationResult(category=category, reasoning=parsed.get("reasoning", ""))

    except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
        log.error(f"LLM classification failed: {e}")
        return ClassificationResult(category="error", reasoning=str(e))


def classify_query(query: str) -> ClassificationResult:
    """
    Main entry point. Always call this before retrieval/generation.
    """
    if _rule_based_check(query):
        return ClassificationResult(
            category="advice_seeking",
            reasoning="matched rule-based advice-seeking pattern",
        )

    return _llm_classify(query)
