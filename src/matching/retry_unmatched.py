"""
Re-attempts openFDA matching for ingredients that came back unmatched
in a previous match_openfda.py run -- useful when some of those
misses were caused by a transient network blip rather than a genuine
absence from openFDA, without re-running the full matching pass.

Usage:
    python retry_unmatched.py
"""

import json
import time
import shutil
import logging
from pathlib import Path

from parse_composition import parse_composition
from openfda_client import match_ingredient

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

    # Backup before we overwrite anything.
    backup = MERGED_FILE.with_suffix(".jsonl.bak")
    shutil.copy(MERGED_FILE, backup)
    log.info(f"Backed up existing merged file to {backup}")

    # Build full_name -> base_name lookup by re-parsing composition text.
    name_to_base = {}
    for record in records:
        for ing in parse_composition(record.get("Composition", "")):
            name_to_base[ing["full_name"]] = ing["base_name"]

    # Find every distinct unmatched ingredient name across all records.
    unmatched_names = set()
    for record in records:
        for ing_match in record.get("parsed_ingredients", []):
            if ing_match["openfda_match"] is None:
                unmatched_names.add(ing_match["drap_name"])

    log.info(f"Retrying {len(unmatched_names)} unmatched ingredients: "
             f"{sorted(unmatched_names)}")

    newly_matched = {}
    for name in unmatched_names:
        base_name = name_to_base.get(name, name)
        result = match_ingredient(name, base_name)
        if result:
            newly_matched[name] = result
            log.info(f"  NOW MATCHED: {name!r} (strategy: {result['_match_strategy']})")
        else:
            log.info(f"  still unmatched: {name!r}")
        time.sleep(0.3)

    if not newly_matched:
        log.info("Nothing newly matched -- no changes to write.")
        return

    # Apply fixes to every record/ingredient that had that name.
    updated_records = 0
    for record in records:
        record_changed = False
        for ing_match in record.get("parsed_ingredients", []):
            if ing_match["openfda_match"] is None and ing_match["drap_name"] in newly_matched:
                ing_match["openfda_match"] = newly_matched[ing_match["drap_name"]]
                record_changed = True
        if record_changed:
            record["has_clinical_reference"] = any(
                m["openfda_match"] for m in record["parsed_ingredients"]
            )
            updated_records += 1

    with open(MERGED_FILE, "w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info(f"Done. {len(newly_matched)} ingredients newly matched, "
             f"{updated_records} records updated in place.")


if __name__ == "__main__":
    run()
