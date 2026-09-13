"""
DRAP (Drug Regulatory Authority of Pakistan) registered-products scraper.

Enumerates webRegNo values against the POST detail endpoint discovered via
DevTools inspection, parses the returned HTML fragment, and writes results
to a checkpointed JSONL file so the scrape can be interrupted and resumed.

Endpoint confirmed via manual DevTools inspection (2026-09-08):
    POST https://eapp.dra.gov.pk/productView.php
    body: webRegNo=<id>
    -> HTML fragment with "Product General Details" table, or a
       "no data found" message if the ID doesn't exist.

Known ID space (from manual spot-checks): 6-digit zero-padded numbers
(e.g. "000500"), roughly in the range 000100-130000+, with some special
formats (EX-XXXXXX for export-only products, REG.NO. XXXXXX duplicates)
that this script does NOT attempt to cover -- those can be added as a
second pass later if needed.
"""

import csv
import json
import re
import time
import random
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://eapp.dra.gov.pk/productView.php"

# Be a polite scraper: this is a small government server, not built for
# bulk traffic. Delay is randomized slightly to avoid a robotic rhythm.
MIN_DELAY = 0.6
MAX_DELAY = 1.2

# Save progress every N requests, so a crash/interrupt loses at most
# this many records of work, not the whole run.
CHECKPOINT_EVERY = 50

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUTPUT_FILE = OUTPUT_DIR / "drap_products.jsonl"
PROGRESS_FILE = OUTPUT_DIR / "drap_scrape_progress.txt"
FAILED_IDS_FILE = OUTPUT_DIR / "drap_failed_ids.txt"
LOG_FILE = OUTPUT_DIR / "drap_scrape.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://eapp.dra.gov.pk/WebProductIndex.php",
}

FIELD_LABELS = [
    "Product Name",
    "Registration No",
    "Registration Date",
    "Company Name",
    "Company Address",
    "Registration Status",
    "Route of Admin",
    "Used For",
    "Dosage Form",
    "Product Specification",
    "Manufacturing Type",
    "Label Claim",
    "Container Closure",
    "Composition",
    "Pack Size(s)",
]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def format_reg_no(n: int) -> str:
    """DRAP registration numbers are zero-padded 6-digit strings."""
    return f"{n:06d}"


def parse_detail_html(html: str) -> dict | None:
    """
    Parse the HTML fragment returned by the detail endpoint.
    Returns None if the response indicates no matching record.
    """
    if "no data found" in html.lower():
        return None

    soup = BeautifulSoup(html, "html.parser")
    record = {}

    # Each field is a <span class="d-block ... small ..."> label
    # followed by a <span class="fw-semibold"> value (sometimes wrapping
    # an <a> tag for Product Name / Registration No).
    labels = soup.find_all("span", class_="d-block")
    for label_span in labels:
        label_text = label_span.get_text(strip=True)
        if label_text not in FIELD_LABELS:
            continue
        value_span = label_span.find_next_sibling("span")
        if value_span is None:
            continue
        record[label_text] = value_span.get_text(strip=True)

    if not record:
        # Page structure didn't match what we expected -- flag it
        # rather than silently returning an empty record.
        log.warning("Parsed zero fields from a non-empty response; "
                    "page structure may have changed.")
        return None

    return record


def fetch_one(session: requests.Session, reg_no: str) -> dict | None:
    resp = session.post(
        BASE_URL,
        data={"webRegNo": reg_no},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return parse_detail_html(resp.text)


def load_progress() -> int:
    """Resume from the last successfully completed reg_no + 1, if any."""
    if PROGRESS_FILE.exists():
        return int(PROGRESS_FILE.read_text().strip()) + 1
    return None


def save_progress(reg_no_int: int) -> None:
    PROGRESS_FILE.write_text(str(reg_no_int))


def scrape_range(start: int, end: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    resume_from = load_progress()
    if resume_from is not None and resume_from > start:
        log.info(f"Resuming from {format_reg_no(resume_from)} "
                  f"(progress file found)")
        start = resume_from

    session = requests.Session()
    found = 0
    skipped = 0

    # Append mode: safe to resume without duplicating earlier records.
    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for i, n in enumerate(range(start, end + 1), start=1):
            reg_no = format_reg_no(n)
            try:
                record = fetch_one(session, reg_no)
            except requests.RequestException as e:
                log.error(f"Request failed for {reg_no}: {e}. "
                          f"Retrying once after a longer pause.")
                time.sleep(5)
                try:
                    record = fetch_one(session, reg_no)
                except requests.RequestException as e2:
                    log.error(f"Retry also failed for {reg_no}: {e2}. "
                              f"Skipping this ID.")
                    record = None

            if record:
                record["_reg_no_queried"] = reg_no
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                found += 1
            else:
                skipped += 1

            if i % CHECKPOINT_EVERY == 0:
                out.flush()
                save_progress(n)
                log.info(f"Checkpoint at {reg_no}: "
                         f"{found} found, {skipped} skipped so far "
                         f"({i}/{end - start + 1} in this run)")

            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        save_progress(end)

    log.info(f"Done. {found} records found, {skipped} IDs empty/skipped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape DRAP registered products.")
    parser.add_argument("--start", type=int, default=100, help="First reg_no to try (default 100)")
    parser.add_argument("--end", type=int, default=130000, help="Last reg_no to try (default 130000)")
    args = parser.parse_args()

    scrape_range(args.start, args.end)
