"""
Builds the ChromaDB vector index from merged_drugs.jsonl.

Chunking strategy: each drug record produces up to 3 chunks, split by
content type rather than indexed as one giant blob per drug. This
matters for retrieval quality -- a query about interactions shouldn't
retrieve a chunk full of unrelated dosage-form text, and it lets the
safety-relevant sections (warnings/interactions) surface precisely
when asked about, rather than being buried in a general description.

    "overview"      -- what the drug is, what it's for, composition
    "warnings"       -- warnings, contraindications, boxed warnings
    "interactions"   -- drug interactions, adverse reactions

Records with no openFDA match (has_clinical_reference=False) still
get an "overview" chunk from DRAP data alone (brand/generic/company/
registration info is still useful for the equivalent-lookup feature),
just no warnings/interactions chunks since there's no source for them.

Uses a local sentence-transformers model (no API key, no cost) for
embeddings, consistent with the free-tier deployment goal.

Usage:
    python build_index.py
"""

import json
import logging
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MERGED_FILE = DATA_DIR / "processed" / "merged_drugs.jsonl"
CHROMA_DIR = DATA_DIR / "chroma_index"

COLLECTION_NAME = "medicines"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def build_overview_text(record: dict) -> str:
    parts = [
        f"Product: {record.get('Product Name', '')}",
        f"Composition: {record.get('Composition', '')}",
        f"Dosage form: {record.get('Dosage Form', '')}",
        f"Used for: {record.get('Used For', '')}",
        f"Registration status: {record.get('Registration Status', '')}",
    ]
    for ing in record.get("parsed_ingredients", []):
        match = ing.get("openfda_match")
        if match and match.get("indications_and_usage"):
            parts.append(
                f"What {ing['drap_name']} is for: {match['indications_and_usage']}"
            )
    return "\n".join(p for p in parts if p.strip())


def build_warnings_text(record: dict) -> str | None:
    sections = []
    for ing in record.get("parsed_ingredients", []):
        match = ing.get("openfda_match")
        if not match:
            continue
        for field in ("warnings", "warnings_and_cautions", "contraindications", "boxed_warning"):
            if match.get(field):
                sections.append(f"[{ing['drap_name']} - {field}]\n{match[field]}")
    return "\n\n".join(sections) if sections else None


def build_interactions_text(record: dict) -> str | None:
    sections = []
    for ing in record.get("parsed_ingredients", []):
        match = ing.get("openfda_match")
        if not match:
            continue
        for field in ("drug_interactions", "adverse_reactions"):
            if match.get(field):
                sections.append(f"[{ing['drap_name']} - {field}]\n{match[field]}")
    return "\n\n".join(sections) if sections else None


def build_metadata(record: dict, chunk_type: str) -> dict:
    ingredient_names = ", ".join(
        ing["drap_name"] for ing in record.get("parsed_ingredients", [])
    )
    return {
        "reg_no": record.get("Registration No", ""),
        "product_name": record.get("Product Name", ""),
        "dosage_form": record.get("Dosage Form", ""),
        "used_for": record.get("Used For", ""),
        "registration_status": record.get("Registration Status", ""),
        "ingredients": ingredient_names,
        "has_clinical_reference": record.get("has_clinical_reference", False),
        "chunk_type": chunk_type,
    }


def run():
    records = []
    with open(MERGED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    log.info(f"Loaded {len(records)} merged records.")

    log.info(f"Loading embedding model ({EMBEDDING_MODEL})... this may take a "
             f"moment the first time as it downloads.")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Fresh build each run -- delete if it exists so re-running doesn't duplicate.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME, embedding_function=embed_fn
    )

    ids, documents, metadatas = [], [], []
    for record in records:
        reg_no = record.get("Registration No", "") or record.get("_reg_no_queried", "")
        if not reg_no:
            continue

        overview = build_overview_text(record)
        if overview.strip():
            ids.append(f"{reg_no}_overview")
            documents.append(overview)
            metadatas.append(build_metadata(record, "overview"))

        warnings = build_warnings_text(record)
        if warnings:
            ids.append(f"{reg_no}_warnings")
            documents.append(warnings)
            metadatas.append(build_metadata(record, "warnings"))

        interactions = build_interactions_text(record)
        if interactions:
            ids.append(f"{reg_no}_interactions")
            documents.append(interactions)
            metadatas.append(build_metadata(record, "interactions"))

    log.info(f"Prepared {len(documents)} chunks from {len(records)} records. Embedding + indexing...")

    # Batch to avoid overwhelming memory on large runs.
    BATCH = 100
    for i in range(0, len(documents), BATCH):
        collection.add(
            ids=ids[i:i + BATCH],
            documents=documents[i:i + BATCH],
            metadatas=metadatas[i:i + BATCH],
        )
        log.info(f"Indexed {min(i + BATCH, len(documents))}/{len(documents)} chunks")

    log.info(f"Done. ChromaDB collection '{COLLECTION_NAME}' persisted at {CHROMA_DIR}")
    log.info(f"Total chunks: {collection.count()}")


if __name__ == "__main__":
    run()
