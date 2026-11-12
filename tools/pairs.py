"""Stage 2: build the judge pairs (seed 20261109).

TRUE: (question, accepted answer, its source passage). FALSE: a value of the SAME kind from the SAME document, drawn by
the seeded RNG from data/sampled_values.jsonl among values the scorer does not match to the accepted answers, shown
with ITS OWN sentence. No value of that kind -> any kind from the same document; none at all -> skipped. Signature
questions: the other named signatory in the same document, else skipped. Source text capped at 300 characters.
The published pairs were built with the scorer before its date fix; rebuilding with today's scorer changes one fake
(TP-4). outputs/stage2_pairs_main.jsonl is what was run.

    python3 pairs.py <out_path>
"""
import json, random, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import score

DATA = Path(__file__).resolve().parents[1] / "data"
SEED = 20261109
CAP = 300


def signatories(text):
    """(name, the 'COMPANY\\nBy: /s/ Name' passage) for every signature line."""
    return [(m.group(2), m.group(0)) for m in re.finditer(r"([^\n]*)\nBy: /s/ ([^\n]+)", text)]


def main():
    OUT = Path(sys.argv[1])
    assert not OUT.exists(), f"{OUT} exists; refusing to overwrite"
    key = json.loads((DATA / "questions.json").read_text())
    for q in key["questions"]:
        q["q"] = q["question"]
    docs = {d: (DATA / "docs" / f"{d}.txt").read_text() for d in key["docs"]}
    cands = [json.loads(l) for l in (DATA / "sampled_values.jsonl").open()]
    kind_of = {(c["doc"], c["order"]): c["kind"] for c in cands}
    pairs, skips = [], []
    for q in key["questions"]:
        if not q["accept"]:
            continue
        pairs.append(dict(id=q["id"], label="true", q=q["q"], value=q["accept"][0], anchor=q["sources"][0][:CAP]))
        rng = random.Random(f"{SEED}-{q['id']}")
        m = re.match(r"(\w+)#(\d+)", q["origin"])
        if m:
            kind = kind_of[(m.group(1), int(m.group(2)))]
            pool = [c for c in cands if c["doc"] == q["doc"] and score.match(c["value"], q["accept"]) == "WRONG"]
            same = sorted({(c["value"], c["sentence"]) for c in pool if c["kind"] == kind})
            pick_from, how = (same, "same kind") if same else (sorted({(c["value"], c["sentence"]) for c in pool}), "any kind")
            if not pick_from:
                skips.append((q["id"], "no non-matching value in the document"))
                continue
            value, sentence = rng.choice(pick_from)
        else:  # signature-line question
            others = [(n, p) for n, p in signatories(docs[q["doc"]]) if n not in q["accept"]]
            if not others:
                skips.append((q["id"], "only one named signatory in the document"))
                continue
            (value, sentence), how = rng.choice(sorted(others)), "other signatory"
        pairs.append(dict(id=q["id"], label="false", q=q["q"], value=value, anchor=sentence[:CAP], fake_rule=how))
    with OUT.open("w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    nt = sum(p["label"] == "true" for p in pairs)
    nf = sum(p["label"] == "false" for p in pairs)
    shown_t = sum(p["label"] == "true" and p["value"] in p["anchor"] for p in pairs)
    shown_f = sum(p["label"] == "false" and p["value"] in p["anchor"] for p in pairs)
    print(f"{nt} true, {nf} false pairs; value inside the shown text: true {shown_t}/{nt}, false {shown_f}/{nf}")
    print("fake rule:", {r: sum(p.get('fake_rule') == r for p in pairs) for r in ("same kind", "any kind", "other signatory")})
    for s in skips:
        print("SKIP", *s)


if __name__ == "__main__":
    main()
