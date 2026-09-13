"""
Run this FIRST, before the full scrape, to confirm the parser is
correctly reading the live site's HTML structure.

Usage:
    python src/scraper/test_scraper.py
"""

import json
from drap_scraper import fetch_one
import requests

# Known-good reg_nos from manual spot-checks during investigation.
TEST_IDS = ["000500", "050000", "100000", "058327"]

session = requests.Session()

for reg_no in TEST_IDS:
    print(f"\n--- Testing {reg_no} ---")
    try:
        record = fetch_one(session, reg_no)
    except Exception as e:
        print(f"  ERROR: {e}")
        continue

    if record is None:
        print("  No record found (or parsing failed -- check warnings above).")
    else:
        print(json.dumps(record, indent=2, ensure_ascii=False))

print("\nIf all four returned real-looking records with populated fields, "
      "the parser is working correctly. If any came back empty or with "
      "missing fields, paste the output here and we'll fix the parser "
      "before running the full scrape.")
