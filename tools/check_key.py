"""Mechanical checks on the question set. Exit 1 on any failure.

1. every source passage is a literal substring of its document
2. every accepted answer is a literal substring of at least one of its source passages
3. no silent drops: for each document, every sampled value up to the last one used is either used or logged as skipped
`--selftest` plants one error of each kind and requires all three checks to fire.
"""
import copy, json, re, sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def check(key, docs):
    errs = []
    used = {}
    for q in key["questions"]:
        text = docs[q["doc"]]
        for s in q["sources"]:
            if s not in text:
                errs.append(f"{q['id']}: source not in {q['doc']}: {s[:60]!r}")
        for a in q["accept"] or []:
            if not any(a in s for s in q["sources"]):
                errs.append(f"{q['id']}: accept {a!r} not in any source")
        m = re.match(r"(\w+)#(\d+)", q["origin"])
        if m:
            used.setdefault(m.group(1), set()).add(int(m.group(2)))
    skipped = {}
    for s in key["skipped_values"]:
        d, n = s["candidate"].split("#")
        skipped.setdefault(d, set()).add(int(n))
    for d, nums in used.items():
        for n in range(max(nums) + 1):
            if n not in nums and n not in skipped.get(d, set()):
                errs.append(f"{d}#{n}: silently dropped (neither used nor logged)")
    return errs


def main():
    key = json.loads((DATA / "questions.json").read_text())
    docs = {d: (DATA / "docs" / f"{d}.txt").read_text() for d in key["docs"]}
    if "--selftest" in sys.argv:
        bad = copy.deepcopy(key)
        bad["questions"][0]["sources"][0] += " PLANTED"
        bad["questions"][1]["accept"][0] = "December 1, 1999"
        bad["skipped_values"] = bad["skipped_values"][1:]
        errs = check(bad, docs)
        fired = {k: any(k in e for e in errs) for k in ["source not in", "not in any source", "silently dropped"]}
        print("selftest:", fired)
        sys.exit(0 if all(fired.values()) else 1)
    errs = check(key, docs)
    for e in errs:
        print("FAIL", e)
    print(f"{len(key['questions'])} questions, {len(errs)} failures")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
