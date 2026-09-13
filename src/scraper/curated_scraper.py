"""
Curated scraper: searches DRAP by generic name for a fixed list of
common medicines, then fetches full details for every matching
registration number found. Much faster than brute-force ID
enumeration -- run this when time-boxed.

Usage:
    python curated_scraper.py
"""

import json
import time
import random
import logging
from pathlib import Path
from urllib.parse import quote

import requests

from drap_scraper import fetch_one, OUTPUT_DIR
from curated_drugs import COMMON_GENERICS

SEARCH_URL = "https://eapp.dra.gov.pk/productView.php"
CURATED_OUTPUT = OUTPUT_DIR / "drap_products_curated.jsonl"
LOG_FILE = OUTPUT_DIR / "curated_scrape.log"

MIN_DELAY = 0.5
MAX_DELAY = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://eapp.dra.gov.pk/WebProductIndex.php",
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    force=True,
)
log = logging.getLogger(__name__)


def search_by_generic_name(session: requests.Session, name: str) -> list[str]:
    """Returns a list of registration-number ids matching this generic name."""
    url = f"{SEARCH_URL}?search={quote(name)}&_type=generic%20name"
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    try:
        data = json.loads(resp.text.lstrip("\ufeff"))
    except ValueError:
        log.warning(f"Non-JSON response searching {name!r}, skipping. "
                    f"Raw response (first 300 chars): {resp.text[:300]!r}")
        return []
    return [r["id"] for r in data.get("results", [])]


def run():
    session = requests.Session()
    all_ids: set[str] = set()

    log.info(f"Searching {len(COMMON_GENERICS)} generic names...")
    for name in COMMON_GENERICS:
        try:
            ids = search_by_generic_name(session, name)
            log.info(f"  {name!r}: {len(ids)} matches")
            all_ids.update(ids)
        except requests.RequestException as e:
            log.error(f"Search failed for {name!r}: {e}")
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    log.info(f"Total unique registration IDs to fetch: {len(all_ids)}")

    found = 0
    skipped = 0
    with open(CURATED_OUTPUT, "w", encoding="utf-8") as out:
        for i, reg_no in enumerate(sorted(all_ids), start=1):
            # Skip the special EX-/REG.NO. formats for now -- the POST
            # detail endpoint expects the plain 6-digit id.
            if not reg_no.isdigit():
                skipped += 1
                continue

            try:
                record = fetch_one(session, reg_no)
            except requests.RequestException as e:
                log.error(f"Detail fetch failed for {reg_no}: {e}")
                skipped += 1
                time.sleep(2)
                continue

            if record:
                record["_reg_no_queried"] = reg_no
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                found += 1
            else:
                skipped += 1

            if i % 25 == 0:
                out.flush()
                log.info(f"Progress: {i}/{len(all_ids)} ({found} found, {skipped} skipped)")

            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    log.info(f"Done. {found} records written to {CURATED_OUTPUT}, {skipped} skipped.")


if __name__ == "__main__":
    run()
