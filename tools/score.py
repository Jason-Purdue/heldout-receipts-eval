"""The scorer. Saved and self-tested before any run.

match(answer, accept_list) -> CORRECT | PARTIAL | WRONG, comparing TYPED values, never substrings:
- money: "$10 M" == "$10 million" == "$10,000,000"; "$ 1,446,066" == "1,446,066" (a bare number matches a money accept
  only when the numbers are equal)
- dates: "Nov 5, 2026" style is not produced by the app; dates compare as normalized text "november 5, 2026"
- one number (with or without a unit word): "169 patients" == "169"; units, when both sides have one, must agree
- ranges/lists (accept holds 2+ numbers): CORRECT only if the answer holds the same numbers in the same order;
  an answer holding a proper subset of them is PARTIAL (e.g. "100 mcg/mL" for "50 to 100 mcg/mL")
- names/text: case-insensitive equality after collapsing spaces
An answer holding numbers that are not all in the accept is WRONG. `python3 score.py --selftest` must pass first.
"""
import json, os, re, sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
NUM = re.compile(r"(?<![\w.])\$?\s?\(?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?\s?(million|billion|thousand|[mkb])?(?![\w])", re.I)


def _text(s):
    return re.sub(r"\s+", " ", s.replace("º", "°").replace(" ", " ")).strip(" .,;:").lower()


def numbers(s):
    """Every number in s, scaled when a $ amount carries million/billion/M/B."""
    out = []
    for m in NUM.finditer(s):
        v = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        unit = (m.group(3) or "").lower()
        if unit and "$" in m.group(0):
            v *= SCALE[unit]
        out.append(round(v, 6))
    return out


MONTH_DATE = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})\b", re.I)


def dates(s):
    """(month, day, year) for every 'Month D, YYYY' in s. Dates must match on the month too: comparing numbers alone
    would let "April 14, 2025" match "January 14, 2025"."""
    return [(m.group(1).lower(), int(m.group(2)), m.group(3)) for m in MONTH_DATE.finditer(s)]


def unit_word(s):
    m = re.search(r"\d\s*(mg/kg/day|mg/kg|mg/ml|mcg/ml|mg|mcg|ml|weeks?|days?|hours?|minutes?|years?|shares|patients|%)", s, re.I)
    return m.group(1).lower().rstrip("s") if m else None


def match_one(answer, accept):
    a, t = _text(answer), _text(accept)
    if a == t:
        return "CORRECT"
    na, nt = numbers(answer), numbers(accept)
    if not nt:  # names / text
        return "WRONG"
    if not na:
        return "WRONG"
    if dates(accept) and dates(answer) != dates(accept):
        return "WRONG"
    ua, ut = unit_word(answer), unit_word(accept)
    if ua and ut and ua != ut:
        return "WRONG"
    if na == nt:
        return "CORRECT"
    if len(nt) >= 2 and set(na) < set(nt) and all(x in nt for x in na):
        return "PARTIAL"
    return "WRONG"


def match(answer, accepts):
    if answer is None or not str(answer).strip():
        return None
    results = [match_one(str(answer), acc) for acc in accepts]
    for r in ("CORRECT", "PARTIAL"):
        if r in results:
            return r
    return "WRONG"


def outcome(q, row):
    """Stage 1 outcome for one question. row: the app's result (route, verdict, answer)."""
    engine_routes = {"hub_lookup", "hub_concept", "hub_miss"}
    if row.get("route") not in engine_routes:
        return "ROUTED_OUT"
    answered = row.get("verdict") != "not_found" and row.get("answer")
    if q["accept"] is None:
        return "WRONG" if answered else "CORRECT_NOT_FOUND"
    if not answered:
        return "MISS"
    return match(row["answer"], q["accept"])


SELFTEST = [  # (answer, accept list, expected)
    ("$10 M", ["$10 million"], "CORRECT"),
    ("$10,000,000", ["$10 million"], "CORRECT"),
    ("1", ["$10 million"], "WRONG"),                  # a substring rule would pass this
    ("65", ["$65.60"], "WRONG"),                      # and this
    ("$5.60", ["$65.60"], "WRONG"),
    ("$ 1,446,066", ["$ 1,446,066", "1,446,066"], "CORRECT"),
    ("1,446,066", ["$ 1,446,066"], "CORRECT"),
    ("105,354,809 shares", ["105,354,809"], "CORRECT"),
    ("169 patients", ["169 patients", "169"], "CORRECT"),
    ("169 weeks", ["169 patients"], "WRONG"),
    ("100 mcg/mL", ["50 to 100 mcg/mL"], "PARTIAL"),
    ("50 to 100 mcg/mL", ["50 to 100 mcg/mL"], "CORRECT"),
    ("50 to 110 mcg/mL", ["50 to 100 mcg/mL"], "WRONG"),
    ("November 6, 2026", ["November 6, 2026"], "CORRECT"),
    ("November 5, 2026", ["November 6, 2026"], "WRONG"),
    ("April 14, 2025", ["January 14, 2025"], "WRONG"),            # same day and year, different month
    ("January 14, 2025", ["January 14, 2025"], "CORRECT"),
    ("Christopher Jannette", ["Christopher Jannette"], "CORRECT"),
    ("Dustin Shindo", ["Christopher Jannette"], "WRONG"),
    ("17.9%", ["12.8%"], "WRONG"),
    ("12.8%", ["12.8%"], "CORRECT"),
    ("$0.73 million", ["$0.73 million", "$0.7 million"], "CORRECT"),
    ("$7.5 million and $5.8 million", ["$7.5 million"], "WRONG"),   # two values, one right: not an answer
]


def selftest():
    bad = [(a, acc, exp, match(a, acc)) for a, acc, exp in SELFTEST if match(a, acc) != exp]
    q_ans, q_una = {"accept": ["$10 million"]}, {"accept": None}
    route_cases = [
        (q_ans, {"route": "hub_concept", "verdict": "verified", "answer": "$10 M"}, "CORRECT"),
        (q_ans, {"route": "hub_miss", "verdict": "not_found", "answer": None}, "MISS"),
        (q_ans, {"route": "retrieval_fallthrough", "verdict": "pending", "answer": None}, "ROUTED_OUT"),
        (q_una, {"route": "hub_concept", "verdict": "verified", "answer": "$3"}, "WRONG"),
        (q_una, {"route": "hub_miss", "verdict": "not_found", "answer": None}, "CORRECT_NOT_FOUND"),
    ]
    bad += [("route", r, exp, outcome(q, r)) for q, r, exp in route_cases if outcome(q, r) != exp]
    for b in bad:
        print("SELFTEST FAIL", b)
    print(f"selftest: {len(SELFTEST) + len(route_cases) - len(bad)}/{len(SELFTEST) + len(route_cases)} pass")
    return not bad


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if not selftest():
        sys.exit("scorer selftest failed; refusing to score")
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    key = {q["id"]: dict(q, q=q["question"]) for q in json.loads((DATA / "questions.json").read_text())["questions"]}
    rows = [json.loads(l) for l in raw.open()]
    assert {r["id"] for r in rows} == set(key), "results do not cover exactly the question set"
    with out.open("w") as f:
        for r in rows:
            r["score"] = outcome(key[r["id"]], r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(Counter(r["score"] for r in rows))


if __name__ == "__main__":
    main()
