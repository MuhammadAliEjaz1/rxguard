"""
FastAPI backend for the medicine assistant.

Endpoints:
    POST /ask                  -- main RAG chat endpoint, routed through
                                   the safety classifier before any
                                   retrieval or generation happens
    GET  /equivalents/{name}   -- generic equivalents lookup (DRAP data
                                   only, no LLM involved)
    GET  /health                -- basic liveness check

Run with:
    uvicorn main:app --reload --port 8000
(from this directory, so the sys.path additions below resolve correctly)
"""

import sys
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # must run BEFORE importing classifier/generate, since
                # they read GROQ_API_KEY at module import time

# chromadb requires sqlite3 >= 3.35.0. Some minimal Docker base images
# (e.g. Debian bullseye) ship an older system sqlite3 that's too old
# and crashes on import. pysqlite3-binary bundles a modern sqlite3
# build; swapping it in before chromadb is imported anywhere avoids
# that crash regardless of the host's system sqlite version.
try:
    __import__("pysqlite3")
    import sys as _sys
    _sys.modules["sqlite3"] = _sys.modules.pop("pysqlite3")
except ImportError:
    pass  # not installed (e.g. local dev on a machine with a modern sqlite already) -- fine

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Sibling modules live in separate flat-script folders (src/safety,
# src/rag) rather than being installed as a package, so add them to
# the path explicitly -- keeps each stage runnable standalone too.
_SRC = Path(__file__).resolve().parent.parent
sys.path.append(str(_SRC / "safety"))
sys.path.append(str(_SRC / "rag"))
sys.path.append(str(_SRC / "scraper"))

from classifier import classify_query
from responses import (
    ADVICE_SEEKING_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    CLASSIFIER_ERROR_FALLBACK,
    SAFETY_FOOTER,
)
from retrieve import retrieve
from generate import generate_answer
from equivalents import get_equivalents, build_index as build_equivalents_index
from curated_drugs import COMMON_GENERICS

_SORTED_GENERICS = sorted(COMMON_GENERICS, key=len, reverse=True)


def extract_keyword(query: str) -> str | None:
    """Detects a known drug/ingredient name in the query, longest match
    first, to bias retrieval toward that specific drug's chunks."""
    q_lower = query.lower()
    for name in _SORTED_GENERICS:
        if name.lower() in q_lower:
            return name
    return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Pakistan Medicine Assistant API")

# Loosen for local dev; tighten to your actual frontend origin before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    log.info("Building equivalents index...")
    build_equivalents_index()
    log.info("Ready.")


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    answer: str
    category: str
    sources: list[dict] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    result = classify_query(req.query)

    if result.category == "advice_seeking":
        return AskResponse(answer=ADVICE_SEEKING_RESPONSE, category="advice_seeking")

    if result.category == "out_of_scope":
        return AskResponse(answer=OUT_OF_SCOPE_RESPONSE, category="out_of_scope")

    if result.category == "error":
        return AskResponse(answer=CLASSIFIER_ERROR_FALLBACK, category="error")

    # category == "lookup" -- proceed to retrieval + generation
    keyword = extract_keyword(req.query)
    chunks = retrieve(req.query, n_results=8, keyword=keyword)
    answer = generate_answer(req.query, chunks)
    answer += SAFETY_FOOTER

    sources = [
        {"product_name": c["metadata"].get("product_name", ""),
         "chunk_type": c["metadata"].get("chunk_type", "")}
        for c in chunks
    ]
    return AskResponse(answer=answer, category="lookup", sources=sources)


@app.get("/equivalents/{generic_name}")
def equivalents(generic_name: str):
    brands = get_equivalents(generic_name)
    return {"generic_name": generic_name, "count": len(brands), "brands": brands}
