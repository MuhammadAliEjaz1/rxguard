"""
Merges the curated DRAP scrape with openFDA clinical data.

For each DRAP record: parses its Composition field into one or more
active ingredients, matches each against openFDA (cached so each
unique ingredient is queried only once across the whole dataset), and
writes a merged record with both DRAP fields and matched openFDA
fields per ingredient.

Usage:
    python match_openfda.py
"""

import json
import time
import logging
from pathlib import Path

from parse_composition import parse_composition
from openfda_client import match_ingredient

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INPUT_FILE = DATA_DIR / "raw" / "drap_products_curated.jsonl"
OUTPUT_FILE = DATA_DIR / "processed" / "merged_drugs.jsonl"
LOG_FILE = DATA_DIR / "raw" / "match_openfda.log"

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    force=True,
)
log = logging.getLogger(__name__)


def run():
    records = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    log.info(f"Loaded {len(records)} DRAP records.")

    # Cache: ingredient base_name (uppercased) -> match result or None.
    # Querying each unique ingredient once instead of once per record.
    cache: dict[str, dict | None] = {}
    matched_count = 0
    unmatched_ingredients = set()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for i, record in enumerate(records, start=1):
            composition_text = record.get("Composition", "")
            ingredients = parse_composition(composition_text)

            ingredient_matches = []
            for ing in ingredients:
                cache_key = ing["full_name"].upper()
                if cache_key not in cache:
                    result = match_ingredient(ing["full_name"], ing["base_name"])
                    cache[cache_key] = result
                    time.sleep(0.3)  # be polite to openFDA too
                    if result:
                        matched_count += 1
                    else:
                        unmatched_ingredients.add(ing["base_name"])

                match = cache[cache_key]
                ingredient_matches.append({
                    "drap_name": ing["full_name"],
                    "strength": ing["strength"],
                    "openfda_match": match,  # None if nothing found
                })

            merged = dict(record)
            merged["parsed_ingredients"] = ingredient_matches
            merged["has_clinical_reference"] = any(
                m["openfda_match"] for m in ingredient_matches
            )
            out.write(json.dumps(merged, ensure_ascii=False) + "\n")

            if i % 100 == 0:
                out.flush()
                log.info(f"Progress: {i}/{len(records)} records, "
                         f"{len(cache)} unique ingredients queried so far")

    log.info(f"Done. {len(records)} merged records written to {OUTPUT_FILE}")
    log.info(f"{len(cache)} unique ingredients queried, {matched_count} matched.")
    if unmatched_ingredients:
        log.info(f"{len(unmatched_ingredients)} ingredients had NO openFDA match "
                  f"(kept in output with has_clinical_reference=False): "
                  f"{sorted(unmatched_ingredients)[:20]}"
                  f"{' ...' if len(unmatched_ingredients) > 20 else ''}")


if __name__ == "__main__":
    run()
