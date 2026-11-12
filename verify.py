"""One command: check the files, run the self-tests, and re-derive every reported number from the raw outputs.

    python3 verify.py

No GPU and no models. Python 3.10+; the receipt tests also need pytest and scikit-learn (skipped, and said so, if
missing). Exits non-zero on any mismatch.
"""
import hashlib, json, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, OUTPUTS = ROOT / "data", ROOT / "outputs"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "receipts"))

failures = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def files_unchanged():
    bad = []
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        h, f = line.split(None, 1)
        if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
            bad.append(f)
    check("data and outputs match SHA256SUMS", not bad, str(bad) if bad else "")


def selftests():
    import score, check_key
    check("scorer self-test (28 cases)", score.selftest())
    key = json.loads((DATA / "questions.json").read_text())
    docs = {d: (DATA / "docs" / f"{d}.txt").read_text() for d in key["docs"]}
    check("question set: every source in its document, every answer in its source, no silent drops",
          not check_key.check(key, docs))
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "values.jsonl"
        subprocess.run([sys.executable, str(ROOT / "tools/candidates.py"), str(out)], capture_output=True, check=True)
        check("sampled values regenerate byte-for-byte from the documents and the seed",
              out.read_bytes() == (DATA / "sampled_values.jsonl").read_bytes())
    try:
        import pytest, sklearn  # noqa: F401
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "receipts")], capture_output=True, text=True)
        check("receipt tests (20, including 5 attacks)", r.returncode == 0, r.stdout.strip().splitlines()[-1])
    except ImportError:
        print("SKIP  receipt tests: install pytest and scikit-learn to run them")


def stage1():
    import score
    key = {q["id"]: q for q in json.loads((DATA / "questions.json").read_text())["questions"]}
    got = Counter(score.outcome(key[r["id"]], r) for r in map(json.loads, (OUTPUTS / "stage1_engine.jsonl").open()))
    want = {"MISS": 43, "ROUTED_OUT": 36, "CORRECT_NOT_FOUND": 18, "CORRECT": 2, "WRONG": 1}   # RESULTS.md, Stage 1
    check("Stage 1 re-derived from the engine's raw outputs", dict(got) == want, str(dict(got)))


def stage2():
    import judge
    for r in map(json.loads, (OUTPUTS / "stage2_results.jsonl").open()):
        f = OUTPUTS / f"stage2_{r['arm']}_{re.sub(r'[^A-Za-z0-9.]+', '_', r['model']).strip('_')}.jsonl"
        s = judge.summarize([json.loads(l) for l in f.open()])
        same = all(s[k] == r[k] for k in ("yes_true", "yes_false", "accuracy", "good_judge"))
        check(f"Stage 2 {r['model'][:40]:40s} {r['arm']:13s}", same,
              f"true accepted {s['yes_true']}/77, fakes accepted {s['yes_false']}/75")


def stage3():
    import stage3 as st
    items, docs, doc_of = st.inputs()
    by_id = {it["id"]: it for it in items}
    for r in map(json.loads, (OUTPUTS / "stage3_results.jsonl").open()):
        f = OUTPUTS / f"stage3_{re.sub(r'[^A-Za-z0-9.]+', '_', r['model']).strip('_')}.jsonl"
        rows = [json.loads(l) for l in f.open()]
        again = [st.judge_item(by_id[x["id"]], x["picks"], x.get("quote"), docs[doc_of[x["id"]]]) for x in rows]
        check(f"Stage 3 {r['model'][:40]:40s} re-derived from raw picks and quotes",
              st.summary(again) == {k: r[k] for k in ("PICK", "V2", "WIDEN")})


if __name__ == "__main__":
    files_unchanged()
    selftests()
    stage1()
    stage2()
    stage3()
    print(f"\n{'ALL CHECKS PASS' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)
