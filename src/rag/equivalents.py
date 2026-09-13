"""
Builds an in-memory index of brand -> generic equivalents from the
merged dataset, grouping by the normalized openFDA substance_name
where available (most reliable), falling back to the raw DRAP
ingredient name otherwise.
"""

import json
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MERGED_FILE = DATA_DIR / "processed" / "merged_drugs.jsonl"

_index = None  # normalized ingredient name -> list of brand dicts


def _normalize_key(ing: dict) -> str:
    match = ing.get("openfda_match")
    if match and match.get("matched_substance_name"):
        names = match["matched_substance_name"]
        return names[0].upper() if names else ing["drap_name"].upper()
    return ing["drap_name"].upper()


def build_index():
    global _index
    _index = defaultdict(list)

    with open(MERGED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            for ing in record.get("parsed_ingredients", []):
                key = _normalize_key(ing)
                _index[key].append({
                    "product_name": record.get("Product Name", ""),
                    "company_name": record.get("Company Name", ""),
                    "dosage_form": record.get("Dosage Form", ""),
                    "strength": ing.get("strength", ""),
                    "reg_no": record.get("Registration No", ""),
                })


def get_equivalents(generic_name: str) -> list[dict]:
    """
    Returns all registered brands matching this generic/active
    ingredient name, grouped by normalized substance name.
    """
    if _index is None:
        build_index()

    query = generic_name.strip().upper()

    # Exact key match first.
    if query in _index:
        return _index[query]

    # Fall back to substring match across known keys (handles partial
    # names, e.g. "paracetamol" matching "ACETAMINOPHEN" won't work
    # here directly -- caller should pass the substance-level name;
    # this fallback mainly catches partial/typo'd matches of DRAP names).
    matches = []
    for key, brands in _index.items():
        if query in key or key in query:
            matches.extend(brands)
    return matches
