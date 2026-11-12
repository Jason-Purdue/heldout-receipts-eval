"""Stage 2: models as judges. "Does the source text directly state that X is the answer?" Yes or No.

Arms: main (true pairs show their source passage) and full_sentence (true pairs show the full sentence containing it).
Fakes are identical in both. GOOD JUDGE = accuracy >= 0.90 AND at most 10% of fakes accepted.

    python3 judge.py server <label> <url>      llama-server, grammar-limited Yes/No (Qwen3.6-35B-A3B, Phi-3)
    python3 judge.py hf_chat <hf-model>        chat template, Yes-minus-No logit margin (Qwen2.5-3B-Instruct)
    python3 judge.py hf_raw <hf-model>         raw prompt, " Yes"-minus-" No" logit margin (gemma-4-31B base;
                                               it was run streamed from RAM with a 4-bit loader not included here)
"""
import json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts as p

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"
PAIRS = {"main": OUTPUTS / "stage2_pairs_main.jsonl", "full_sentence": OUTPUTS / "stage2_pairs_full_sentence.jsonl"}
GOOD_ACC, GOOD_FYR = 0.90, 0.10


def load(arm):
    return [json.loads(l) for l in PAIRS[arm].open()]


def summarize(rows):
    nt = sum(r["label"] == "true" for r in rows)
    nf = sum(r["label"] == "false" for r in rows)
    yt = sum(r["yes"] for r in rows if r["label"] == "true")
    yf = sum(r["yes"] for r in rows if r["label"] == "false")
    acc = (yt + (nf - yf)) / (nt + nf)
    t = [r["margin"] for r in rows if r["label"] == "true" and r.get("margin") is not None]
    f = [r["margin"] for r in rows if r["label"] == "false" and r.get("margin") is not None]
    auc = round(sum((a > b) + 0.5 * (a == b) for a in t for b in f) / (len(t) * len(f)), 3) if t and f else None
    return {"yes_true": yt, "n_true": nt, "yes_false": yf, "n_false": nf, "accuracy": round(acc, 3),
            "good_judge": acc >= GOOD_ACC and yf / nf <= GOOD_FYR, "auc": auc}


def run(arm, judge, stream_to=None):
    """stream_to: an optional file that gets every row as it is judged, so a long run loses nothing if it stops."""
    rows, t0, pairs = [], time.time(), load(arm)
    for n, r in enumerate(pairs, 1):
        yes, margin = judge(r["q"], r["value"], r["anchor"])
        row = {"id": r["id"], "label": r["label"], "value": r["value"], "yes": bool(yes), "margin": margin}
        rows.append(row)
        if stream_to:
            with open(stream_to, "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{arm} {n}/{len(pairs)}]", flush=True)
    return rows, round(time.time() - t0)


def record(label, method, arm, rows, secs):
    out = OUTPUTS / f"stage2_{arm}_{re.sub(r'[^A-Za-z0-9.]+', '_', label).strip('_')}.jsonl"
    assert not out.exists(), f"{out} exists; refusing to overwrite"
    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    res = {"model": label, "method": method, "arm": arm, "seconds": secs, **summarize(rows)}
    print(json.dumps(res), flush=True)


def server(label, url):
    b = p.ServerBackend(url)
    for arm in PAIRS:
        rows, secs = run(arm, lambda q, v, a: (b.verify(q, v, a), None))
        record(label, "server_grammar_yes_no", arm, rows, secs)


def hf_chat(name):
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float16, device_map="cuda").eval()
    yes_ids, no_ids = tok("Yes", add_special_tokens=False)["input_ids"], tok("No", add_special_tokens=False)["input_ids"]
    assert len(yes_ids) == 1 and len(no_ids) == 1, (yes_ids, no_ids)

    @torch.no_grad()
    def judge(q, value, anchor):   # the same prompt as one user turn through the chat template
        msgs = [{"role": "user", "content": p.verify_prompt(q, value, anchor)}]
        enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        lg = model(input_ids=enc["input_ids"].to("cuda")).logits[0, -1].float()
        m = float(lg[yes_ids[0]] - lg[no_ids[0]])
        return m > 0, round(m, 3)

    for arm in PAIRS:
        rows, secs = run(arm, judge)
        record(name + " [chat template]", "hf_chat_template_logit_margin", arm, rows, secs)


def hf_raw(name):
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, device_map="auto").eval()
    yes_id = tok(" Yes", add_special_tokens=False)["input_ids"][-1]
    no_id = tok(" No", add_special_tokens=False)["input_ids"][-1]

    @torch.no_grad()
    def judge(q, value, anchor):
        enc = tok(p.verify_prompt(q, value, anchor), return_tensors="pt").to(model.device)
        lg = model(input_ids=enc["input_ids"]).logits[0, -1].float()
        m = float(lg[yes_id] - lg[no_id])
        return m > 0, round(m, 3)

    for arm in PAIRS:
        rows, secs = run(arm, judge)
        record(name, "raw_prompt_logit_margin", arm, rows, secs)


if __name__ == "__main__":
    {"server": lambda: server(sys.argv[2], sys.argv[3]), "hf_chat": lambda: hf_chat(sys.argv[2]),
     "hf_raw": lambda: hf_raw(sys.argv[2])}[sys.argv[1]]()
