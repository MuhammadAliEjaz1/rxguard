"""
Queries openFDA for indication/warning/interaction data matching a
parsed active-ingredient name. Tries three strategies in order,
falling back only when the stricter one returns nothing:

  1. Exact substance_name match, restricted to prescription-format
     labels (richer fields: drug_interactions, contraindications).
  2. Exact substance_name match, any format (falls back to OTC-style
     Drug Facts labels, which lack drug_interactions but still have
     indications_and_usage).
  3. Non-exact substance_name search on the base name (handles salt
     form mismatches, e.g. DRAP says "Cefixime trihydrate" but
     openFDA's substance_name is just "CEFIXIME").

Each unique ingredient should be queried only once and cached --
see match_openfda.py for the caching wrapper.
"""

import time
import logging
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/drug/label.json"

# DRAP uses British/Pakistani generic naming conventions; openFDA uses
# US naming. These differ for a known set of common drugs -- tried as
# the highest-priority candidate before falling back to the raw name.
UK_TO_US_ALIASES = {
    "PARACETAMOL": "ACETAMINOPHEN",
    "SALBUTAMOL": "ALBUTEROL",
    "FRUSEMIDE": "FUROSEMIDE",
    "ADRENALINE": "EPINEPHRINE",
    "NORADRENALINE": "NOREPINEPHRINE",
    "LIGNOCAINE": "LIDOCAINE",
    "CEPHRADINE": "CEFRADINE",
    "GENTAMYCIN": "GENTAMICIN",
    "AMOXYCILLIN": "AMOXICILLIN",
    "OMEPRAOLE": "OMEPRAZOLE",  # typo in DRAP source data
}

FIELDS_TO_KEEP = [
    "indications_and_usage",
    "warnings",
    "warnings_and_cautions",
    "drug_interactions",
    "contraindications",
    "adverse_reactions",
    "boxed_warning",
]


def _extract_fields(result: dict) -> dict:
    out = {}
    for field in FIELDS_TO_KEEP:
        if field in result:
            val = result[field]
            out[field] = val[0] if isinstance(val, list) else val
    openfda = result.get("openfda", {})
    out["matched_substance_name"] = openfda.get("substance_name", [])
    out["matched_generic_name"] = openfda.get("generic_name", [])
    out["matched_product_type"] = openfda.get("product_type", [])
    return out


def _query(search_expr: str, _retried: bool = False) -> dict | None:
    url = f"{BASE_URL}?search={search_expr}&limit=1"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            return None  # openFDA returns 404 for zero results
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return _extract_fields(results[0]) if results else None
    except requests.RequestException as e:
        if not _retried:
            log.warning(f"openFDA request failed, retrying once after a pause: {e}")
            time.sleep(3)
            return _query(search_expr, _retried=True)
        log.error(f"openFDA request failed again after retry, giving up: {e}")
        return None


def _is_plausible_match(queried_name: str, matched_substance_names: list) -> bool:
    """
    Sanity check to reject nonsensical cross-matches (e.g. "Ibuprofen"
    fuzzy-matching to "Trametinib Dimethyl Sulfoxide" -- a completely
    unrelated chemotherapy drug -- because openFDA's non-exact search
    can return loosely-relevant results). Requires the queried name to
    share a substring or a 4-character prefix with at least one
    matched substance name.
    """
    if not matched_substance_names:
        return False
    q = queried_name.upper().strip()
    for s in matched_substance_names:
        s = s.upper().strip()
        if q in s or s in q:
            return True
        if len(q) >= 4 and len(s) >= 4 and q[:4] == s[:4]:
            return True
    return False


def match_ingredient(full_name: str, base_name: str) -> dict | None:
    """
    Returns matched openFDA fields, or None if nothing found across
    all three strategies. Also returns which strategy succeeded, for
    transparency about match confidence.
    """
    candidates = [full_name.upper(), base_name.upper()]
    alias_candidates = [
        UK_TO_US_ALIASES[c] for c in candidates if c in UK_TO_US_ALIASES
    ]
    # Aliases go first -- they're the most likely correct match when present.
    candidates = alias_candidates + candidates

    # Strategy 1: exact match, prescription-format preferred.
    for name in candidates:
        expr = (
            f'openfda.substance_name.exact:"{quote(name)}"'
            f'+AND+openfda.product_type:"HUMAN+PRESCRIPTION+DRUG"'
        )
        result = _query(expr)
        if result and _is_plausible_match(name, result.get("matched_substance_name", [])):
            result["_match_strategy"] = "exact_prescription"
            result["_matched_on"] = name
            return result
        time.sleep(0.3)

    # Strategy 2: exact match, any format.
    for name in candidates:
        expr = f'openfda.substance_name.exact:"{quote(name)}"'
        result = _query(expr)
        if result and _is_plausible_match(name, result.get("matched_substance_name", [])):
            result["_match_strategy"] = "exact_any_format"
            result["_matched_on"] = name
            return result
        time.sleep(0.3)

    # Strategy 3: fuzzy fallback -- try the alias translation first if
    # one exists, since that's the name openFDA is actually likely to
    # recognize (e.g. searching "Salbutamol" finds nothing, but the
    # alias "Albuterol" fuzzy-matches "ALBUTEROL SULFATE"). Every
    # fuzzy result is plausibility-checked, since this is the strategy
    # most likely to return an unrelated drug (openFDA's non-exact
    # search can be surprisingly loose).
    fuzzy_candidates = alias_candidates + [base_name.upper()]
    for name in fuzzy_candidates:
        expr = f"openfda.substance_name:{quote(name)}"
        result = _query(expr)
        if result and _is_plausible_match(name, result.get("matched_substance_name", [])):
            result["_match_strategy"] = "fuzzy_fallback"
            result["_matched_on"] = name
            return result
        time.sleep(0.3)

    return None
