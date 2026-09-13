"""
Generation step: takes retrieved chunks + the user's (already
classified-as-"lookup") query, builds a grounded prompt, and calls
Groq. This only ever runs AFTER the safety gate has approved the
query as a factual lookup -- see src/safety/classifier.py.
"""

import os
import logging

import requests

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"  # llama-3.1-8b-instant was shut down 2026-08-16
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """You are a medicine information assistant for Pakistan, sourced from DRAP (Drug Regulatory Authority of Pakistan) registration data and openFDA clinical reference data.

STRICT RULES:
- You answer ONLY using the provided context below. Do not use outside knowledge about drugs.
- You NEVER give personalized medical advice, dosing recommendations, or tell someone whether they should take a medicine. If the context doesn't let you answer factually, say so.
- You are reference information only -- always factual and neutral in tone, never prescriptive ("you should take X").
- If the context doesn't contain the answer, say you don't have that information rather than guessing.
- Cite which medicine/ingredient information comes from when relevant.
"""


MAX_CHARS_PER_CHUNK = 1200  # some openFDA fields (esp. adverse_reactions on
                             # Rx-format labels) contain pages of clinical
                             # trial data and can be tens of KB long --
                             # without this, retrieving 5 of them can blow
                             # past Groq's request size limit (413 error).


def build_context(chunks: list[dict]) -> str:
    sections = []
    for c in chunks:
        meta = c["metadata"]
        header = f"--- {meta.get('product_name', 'Unknown')} ({meta.get('chunk_type', '')}) ---"
        text = c["document"]
        if len(text) > MAX_CHARS_PER_CHUNK:
            text = text[:MAX_CHARS_PER_CHUNK] + "... [truncated]"
        sections.append(f"{header}\n{text}")
    return "\n\n".join(sections)


def generate_answer(query: str, chunks: list[dict]) -> str:
    if not GROQ_API_KEY:
        return ("I'm not able to generate an answer right now (missing API "
                "configuration). Please try again later.")

    context = build_context(chunks)
    if not context.strip():
        return ("I couldn't find information about that in the medicine "
                "database. Try asking about a specific medicine by name.")

    user_message = f"Context:\n{context}\n\nQuestion: {query}"

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "temperature": 0.2,
                "max_tokens": 500,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError) as e:
        log.error(f"Generation failed: {e}")
        return ("I ran into an error generating a response. Please try again, "
                "and remember to consult a doctor or pharmacist for anything "
                "beyond general reference information.")
