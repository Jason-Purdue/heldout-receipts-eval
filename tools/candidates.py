"""Step 1 of building the question set: list every candidate value in each document and draw a seeded random order.

One question was then written per value, walking each document's order until its quota was met. Values that could not
carry a unique question were logged as skipped (data/questions.json "skipped_values"), never silently dropped.

    python3 candidates.py [out_path]          default: data/sampled_values.jsonl
"""
import json, random, re, hashlib, sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DOCS = DATA / "docs"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "sampled_values.jsonl"
SEED = 20261108  # the date the rules were written; fixed before any candidate was listed

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
PATTERNS = {
    "date": rf"\b(?:{MONTHS}) \d{{1,2}}, \d{{4}}\b",
    "money": r"\$ ?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?: (?:million|billion))?(?![\d])",
    "percent": r"\b\d+(?:\.\d+)?%",
    "unit": r"\b\d[\d,]*(?:\.\d+)? ?(?:mg/kg/day|mg/kg|mg/day|mg|mcg|mL|g|kg|weeks?|days?|hours?|minutes?|years?|shares|°C|°F|patients|sites)\b",
}
DOC_ORDER = ["ten_8k", "ten_pr", "biaf_8k", "biaf_pr", "pono_ex21", "divalproex_label", "temazepam_label"]


def sentence_at(text, start, end):
    """The sentence holding [start, end): bounded by a newline or by '. ' followed by a capital."""
    left = max(text.rfind("\n", 0, start), max((m.end() - 1 for m in re.finditer(r"[.;] (?=[A-Z(“])", text[:start])), default=-1))
    right_nl = text.find("\n", end)
    m = re.search(r"[.;] (?=[A-Z(“])", text[end:])
    right = min(x for x in [right_nl if right_nl >= 0 else len(text), end + m.start() + 1 if m else len(text)])
    return text[left + 1:right].strip()


def main():
    rng = random.Random(SEED)
    rows = []
    for name in DOC_ORDER:
        text = (DOCS / f"{name}.txt").read_text()
        seen, cands = set(), []
        for kind, pat in PATTERNS.items():
            for m in re.finditer(pat, text):
                s = sentence_at(text, m.start(), m.end())
                key = (m.group(0), s)
                if key in seen:
                    continue
                seen.add(key)
                cands.append({"doc": name, "kind": kind, "value": m.group(0), "offset": m.start(), "sentence": s})
        cands.sort(key=lambda c: c["offset"])
        rng.shuffle(cands)
        for i, c in enumerate(cands):
            c["order"] = i
        rows += cands
        print(name, len(cands), "candidates", hashlib.sha256(text.encode()).hexdigest()[:16])
    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
