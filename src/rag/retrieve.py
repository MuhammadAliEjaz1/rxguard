"""
Retrieval against the ChromaDB index built by build_index.py.
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CHROMA_DIR = DATA_DIR / "chroma_index"
COLLECTION_NAME = "medicines"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_client = None
_collection = None


def get_collection():
    """Lazily initialize the Chroma client/collection (loaded once per process)."""
    global _client, _collection
    if _collection is None:
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_collection(
            name=COLLECTION_NAME, embedding_function=embed_fn
        )
    return _collection


def _format(results) -> list[dict]:
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        chunks.append({"document": doc, "metadata": meta, "distance": dist})
    return chunks


def retrieve(query: str, n_results: int = 8, keyword: str | None = None) -> list[dict]:
    """
    Returns a list of {document, metadata, distance} dicts, ranked by
    relevance to the query.

    If `keyword` is given (a known drug/ingredient name detected in the
    query), first tries restricting the vector search to chunks whose
    text actually contains that keyword, via Chroma's where_document
    $contains filter. This fixes cases where pure semantic similarity
    ranks an unrelated drug's chunk above the actually-relevant one
    (e.g. "side effects of cetirizine" pulling in Doxycycline chunks).
    Falls back to plain vector search if the keyword filter finds
    nothing (or no keyword was detected).
    """
    collection = get_collection()

    if keyword:
        # Chroma's $contains is case-sensitive on raw document text,
        # and DRAP/openFDA text casing is inconsistent (Title Case,
        # ALL CAPS, lowercase), so try a few common variants.
        for variant in {keyword, keyword.upper(), keyword.lower(), keyword.title()}:
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where_document={"$contains": variant},
                )
            except Exception:
                continue
            if results.get("documents") and results["documents"][0]:
                return _format(results)

    # No keyword, or the filtered search found nothing -- fall back to
    # plain vector search.
    results = collection.query(query_texts=[query], n_results=n_results)
    return _format(results)
