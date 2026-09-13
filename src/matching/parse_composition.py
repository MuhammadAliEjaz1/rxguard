"""
Parses DRAP's composition field into a list of individual active
ingredients, since it's free text with inconsistent formatting:
    "Paracetamol................. ......500 mg"
    "Gentamicin as Sulphate ...... 80 mg"
    "Ciprofloxacin ...... 250 mg"
    combos separated by "+" or newlines in some records

Returns each ingredient as both a "full_name" (keeps salt-form
qualifiers like "as Sulphate", useful for exact substance_name
matches) and a "base_name" (strips those qualifiers, useful as a
fallback for fuzzy matching).
"""

import re

# Matches a name followed by a run of dots/spaces then a
# number+unit strength, e.g. "Paracetamol....... 500 mg"
_INGREDIENT_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9\s\-]*?)"      # name (non-greedy)
    r"[\.\s]{2,}"                        # separator (dots/spaces)
    r"([\d.]+\s*(?:mg|g|ml|mcg|iu|%)"    # number + unit
    r"(?:\s*/\s*[\d.]+\s*(?:mg|g|ml|mcg|iu|%))?)",  # optional /number+unit ratio
    re.IGNORECASE,
)

# Qualifiers that describe salt form / equivalence, not the base drug.
_QUALIFIER_RE = re.compile(
    r"\s+(as|eq\.?\s*to|equivalent to)\s+.*$", re.IGNORECASE
)


def parse_composition(text: str) -> list[dict]:
    if not text:
        return []

    # Normalize: collapse repeated dot-runs, split combo ingredients on '+'.
    text = re.sub(r"\.{2,}", " ", text)
    parts = re.split(r"\+", text)

    ingredients = []
    seen = set()
    for part in parts:
        for match in _INGREDIENT_RE.finditer(part):
            full_name = match.group(1).strip()
            strength = match.group(2).strip()
            if not full_name or len(full_name) < 3:
                continue

            base_name = _QUALIFIER_RE.sub("", full_name).strip()

            key = (full_name.upper(), strength)
            if key in seen:
                continue  # dedupe the known duplicate-composition-line bug
            seen.add(key)

            ingredients.append({
                "full_name": full_name,
                "base_name": base_name,
                "strength": strength,
            })

    return ingredients


if __name__ == "__main__":
    # Quick self-test against real examples seen during investigation.
    examples = [
        "Paracetamol................. ......500 mg",
        "Gentamicin as Sulphate ...... 80 mgGentamicin as Sulphate ...... 80 mgGentamicin as Sulphate ...... 80 mg",
        "Ciprofloxacin ...... 250 mg",
        "Cefixime trihydrate eq to cefixime ...... 100 mg",
    ]
    for ex in examples:
        print(f"\nInput: {ex!r}")
        for ing in parse_composition(ex):
            print(f"  {ing}")
