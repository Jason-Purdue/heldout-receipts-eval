"""Stage 3: pick from the engine's shortlist (two option orders), then check the model's quote with code.

Arms per model:
  PICK   the two-order pick alone (orders disagree -> INCONSISTENT, counted as no answer)
  V2     the pick is kept only if the model's quote gets a SUPPORTED verdict from receipts/evidence.py (verdict_v2)
  WIDEN  if the quote is found in the document, code widens it to its full sentence, then V2 as above
Correctness uses the typed scorer (score.match). PARTIAL (one end of a range, part of a list) is reported separately.

    python3 stage3.py validate                 fake pickers on the shortlist must give the expected counts
    python3 stage3.py server <label> <url>     llama-server (Qwen3.6-35B-A3B, Phi-3)
    python3 stage3.py hf <hf-model>            raw prompt, letter logits (Qwen2.5-3B-Instruct)
"""
import json, random, re, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "receipts"))
sys.path.insert(0, str(Path(__file__).parent))
import prompts as p
import evidence
import score
from candidates import sentence_at

DATA = Path(__file__).resolve().parents[1] / "data"
OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"
CANDS = OUTPUTS / "stage3_shortlist.jsonl"


def items_from(cands_path, accept_of):
    """Each item: the shortlist plus "None of these", shuffled (seed 20261105), and a second order rotated by one."""
    items = []
    for r in map(json.loads, open(cands_path)):
        opts = [(c["value"].strip(), c["anchor"][:p.BOOTSTRAP_ANCHOR_CHARS]) for c in r["candidates"]] + [(p.NONE, "")]
        order1 = opts[:]
        random.Random(f"{p.SEED}-{r['id']}").shuffle(order1)
        order2 = order1[1:] + order1[:1]
        acc = accept_of[r["id"]]
        items.append({"id": r["id"], "q": r["q"], "accept": acc, "orders": [order1, order2],
                      "in_list": bool(acc) and any(score.match(v, acc) == "CORRECT" for v, _ in opts if v != p.NONE)})
    return items


def outcome(item, picks):
    """Outcome of a two-order pick, scored with the typed scorer; PARTIAL reported separately."""
    acc = item["accept"]
    if picks[0] != picks[1]:
        both_ok = acc is not None and all(p.NONE != v and score.match(v, acc) == "CORRECT" for v in picks)
        return "CORRECT" if both_ok else "INCONSISTENT"
    v = picks[0]
    if acc is None:
        return "CORRECT_NONE" if v == p.NONE else "WRONG"
    if v == p.NONE:
        return "MISS"
    return score.match(v, acc)


def widen(quote, doc):
    """If the quote is in the document (any whitespace between its words), return its full sentence, found on the
    ORIGINAL text so line breaks still end a sentence (table rows and list lines stay separate); else the quote
    unchanged."""
    toks = (quote or "").split()
    if not toks or evidence.collapse(quote) == evidence.NONE_QUOTE:
        return quote
    m = re.search(r"\s+".join(map(re.escape, toks)), doc)
    return evidence.collapse(sentence_at(doc, m.start(), m.end())) if m else quote


def judge_item(it, picks, quote, doc):
    row = {"id": it["id"], "picks": picks, "in_list": it["in_list"], "PICK": outcome(it, picks)}
    if picks[0] == picks[1] and picks[0] != p.NONE:
        wide = widen(quote, doc)
        v2 = evidence.verdict_v2(it["q"], picks[0], quote, doc)
        vw = evidence.verdict_v2(it["q"], picks[0], wide, doc)
        row.update({"quote": quote, "widened": wide, "verdict_v2": v2, "verdict_widen": vw,
                    "V2": outcome(it, picks if v2 == "SUPPORTED" else [p.NONE, p.NONE]),
                    "WIDEN": outcome(it, picks if vw == "SUPPORTED" else [p.NONE, p.NONE])})
    else:
        row.update({"V2": row["PICK"], "WIDEN": row["PICK"]})
    return row


def summary(rows):
    return {arm: dict(Counter(r[arm] for r in rows)) for arm in ("PICK", "V2", "WIDEN")}


def inputs():
    key = json.loads((DATA / "questions.json").read_text())
    acc = {q["id"]: q["accept"] for q in key["questions"]}
    doc_of = {q["id"]: q["doc"] for q in key["questions"]}
    docs = {d: (DATA / "docs" / f"{d}.txt").read_text() for d in key["docs"]}
    return items_from(CANDS, acc), docs, doc_of


def validate():
    items, docs, doc_of = inputs()
    def oracle_pick(it, order):
        for i, (v, _) in enumerate(order):
            if it["accept"] and v != p.NONE and score.match(v, it["accept"]) == "CORRECT":
                return i
        return [v for v, _ in order].index(p.NONE)
    none_pick = lambda it, order: [v for v, _ in order].index(p.NONE)
    first_pick = lambda it, order: 0
    cases = {"oracle": oracle_pick, "always_none": none_pick, "always_first": first_pick}
    n_in = sum(it["in_list"] for it in items)
    n_una = sum(it["accept"] is None for it in items)
    ok = True
    for name, pick in cases.items():
        rows = []
        for it in items:
            picks = [order[pick(it, order)][0] for order in it["orders"]]
            # the quote a perfect model would give: the option's own source text
            quote = dict(it["orders"][0]).get(picks[0], "") if picks[0] == picks[1] else ""
            rows.append(judge_item(it, picks, quote, docs[doc_of[it["id"]]]))
        s = summary(rows)
        pk = s["PICK"]
        if name == "oracle":
            good = pk.get("CORRECT", 0) == n_in and pk.get("WRONG", 0) == 0 and pk.get("CORRECT_NONE", 0) == n_una
        elif name == "always_none":
            good = pk.get("CORRECT", 0) == 0 and pk.get("WRONG", 0) == 0 and pk.get("CORRECT_NONE", 0) == n_una
        else:   # always_first: the two orders disagree whenever they show different first options
            good = pk.get("INCONSISTENT", 0) > 0
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {name}: {s}")
    print(f"shortlist: right answer on the list for {n_in} of {sum(it['accept'] is not None for it in items)} answerable")
    print("VALIDATION PASS" if ok else "VALIDATION FAIL: nothing may run")
    return ok


def run(label, pick, generate):
    items, docs, doc_of = inputs()
    out = OUTPUTS / f"stage3_{re.sub(r'[^A-Za-z0-9.]+', '_', label).strip('_')}.jsonl"
    assert not out.exists(), f"{out} exists; refusing to overwrite"
    rows, t0 = [], time.time()
    for n, it in enumerate(items, 1):
        picks = [order[pick(it, order)][0] for order in it["orders"]]
        quote = None
        if picks[0] == picks[1] and picks[0] != p.NONE:
            anchor = dict(it["orders"][0])[picks[0]]
            quote = generate(p.quote_prompt(it["q"], picks[0], anchor))
        row = judge_item(it, picks, quote, docs[doc_of[it["id"]]])
        rows.append(row)
        with out.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{n}/{len(items)}] {it['id']} PICK={row['PICK']} V2={row['V2']} WIDEN={row['WIDEN']}", flush=True)
    res = {"model": label, "seconds": round(time.time() - t0), **summary(rows)}
    print(json.dumps(res), flush=True)


def server(label, url):
    b = p.ServerBackend(url)
    run(label, b.pick, b.generate)


def hf_like(label, model, tok):
    import torch
    ids = [tok(" " + L, add_special_tokens=False)["input_ids"][-1] for L in p.LETTERS]

    @torch.no_grad()
    def pick(it, order):
        enc = tok(p.prompt(it["q"], order), return_tensors="pt").to("cuda")
        logits = model(input_ids=enc["input_ids"]).logits[0, -1].float()
        return int(torch.stack([logits[i] for i in ids[:len(order)]]).argmax())

    @torch.no_grad()
    def generate(text):   # greedy, token by token, stops at a newline
        x = tok(text, return_tensors="pt")["input_ids"].to("cuda")
        out = []
        for _ in range(p.BOOTSTRAP_QUOTE_TOKENS):
            nxt = int(model(input_ids=x).logits[0, -1].argmax())
            if nxt == tok.eos_token_id or "\n" in tok.decode([nxt]):
                break
            out.append(nxt)
            x = torch.cat([x, torch.tensor([[nxt]], device="cuda")], dim=1)
        return tok.decode(out, skip_special_tokens=True).strip().strip('"').strip()

    run(label, pick, generate)


def hf(name):
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float16, device_map="cuda").eval()
    hf_like(name, model, tok)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "validate":
        sys.exit(0 if validate() else 1)
    elif cmd == "server":
        server(sys.argv[2], sys.argv[3])
    elif cmd == "hf":
        hf(sys.argv[2])
