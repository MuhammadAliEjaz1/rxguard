"""
Re-checks every openFDA match already stored in merged_drugs.jsonl
against the plausibility guard added to openfda_client.py, and nulls
out any that fail it (e.g. "Ibuprofen" matched to "Trametinib Dimethyl
Sulfoxide" -- a real bug caught during manual QA).

This does NOT make any new API calls -- it only re-validates matches
already on disk using their stored _matched_on / matched_substance_name
fields, so it runs in under a second regardless of dataset size.

A null match is always safer than a wrong one: a wrong match attaches
one drug's real safety data to a different drug, which is actively
dangerous for a medical-information assistant. A null match just
means "no reference data available," which is honest.

Usage:
    python revalidate_matches.py
"""

import json
import shutil
import logging
from pathlib import Path

from openfda_client import _is_plausible_match

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MERGED_FILE = DATA_DIR / "processed" / "merged_drugs.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def run():
    records = []
    with open(MERGED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    backup = MERGED_FILE.with_suffix(".jsonl.prevalidation.bak")
    shutil.copy(MERGED_FILE, backup)
    log.info(f"Backed up current file to {backup}")

    invalidated = []
    checked = 0
    for record in records:
        record_changed = False
        for ing in record.get("parsed_ingredients", []):
            match = ing.get("openfda_match")
            if not match:
                continue
            checked += 1

            matched_on = match.get("_matched_on", ing["drap_name"])
            matched_substances = match.get("matched_substance_name", [])

            if not _is_plausible_match(matched_on, matched_substances):
                invalidated.append({
                    "product": record.get("Product Name", ""),
                    "drap_ingredient": ing["drap_name"],
                    "wrongly_matched_to": matched_substances,
                })
                ing["openfda_match"] = None
                record_changed = True

        if record_changed:
            record["has_clinical_reference"] = any(
                m.get("openfda_match") for m in record["parsed_ingredients"]
            )

    with open(MERGED_FILE, "w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info(f"Checked {checked} existing matches.")
    if invalidated:
        log.warning(f"Invalidated {len(invalidated)} bad matches:")
        for bad in invalidated:
            log.warning(f"  {bad['product']!r}: {bad['drap_ingredient']!r} "
                        f"was wrongly matched to {bad['wrongly_matched_to']}")
        log.info("These now have openfda_match=None (no clinical reference) "
                 "instead of wrong data. You MUST rebuild the Chroma index "
                 "after this (python ../indexing/build_index.py) so the bad "
                 "chunks are removed from the vector store too.")
    else:
        log.info("No bad matches found -- everything already checks out.")


if __name__ == "__main__":
    run()
