# Held-out receipts eval

**Can AI answer questions from real documents without making things up, and can anyone check that it didn't?**

We wrote 100 questions about seven public SEC and FDA filings the system had never seen, froze every rule before
running anything, and measured how often an answer engine and four AI models gave wrong answers, and how well code
checks on their quotes caught them. Everything is here: documents, questions, rules, raw outputs and the failures.

```
python3 verify.py
```
re-derives every number from the raw outputs in seconds, with no GPU and no models (Python 3.10+; the receipt tests
also need `pytest` and `scikit-learn`).

By Jason Purdue, IWJJ Technologies, working with Claude (Anthropic) as an AI collaborator.

## What we found
- **The answer engine alone almost never answers wrong, but rarely answers.** 2 of 77 found, 1 wrong, 18 of 23
  correctly said "not found". An earlier result of 9 of 21 on our own practice questions did not hold up on unseen
  documents.
- **AI judges fail in opposite directions.** Shown 75 convincing fakes, a 31B model accepted 19 while accepting every
  true answer; a 35B mixture-of-experts model accepted none of the fakes but rejected about a third of the true answers.
- **Code that checks a model's quote cuts wrong answers sharply, at a cost.** Per model, wrong answers fell from 6-18 to
  0-3, and right answers fell too. Several wrong picks came with a quote that named the right answer: the model found
  it, the shortlist did not offer it.
- **The checks have limits we saw directly:** they compare numbers but not units, and they prove that words appear
  together, not what they mean.

Full results: [RESULTS.md](RESULTS.md). Rules, models and predictions: [PROTOCOL.md](PROTOCOL.md).

## What's in here
| path | contents |
|---|---|
| `data/docs/` | the seven documents as tested, plus the raw openFDA record |
| `data/questions.json` | the 100 questions, accepted answers, source passages, and the 14 values skipped (with reasons) |
| `data/sampled_values.jsonl` | every candidate value in each document, in the seeded order questions were written from |
| `data/human_check.json` | the 20 questions a person checked (0 errors) |
| `outputs/` | raw outputs for every stage and model, and the result summaries |
| `tools/` | the scorer, the question-set checks, the pair builder, and the Stage 2 and 3 runners, with the exact prompts |
| `receipts/` | the evidence-receipt checks and 20 tests, 5 of them attacks that fooled an earlier version |
| `SHA256SUMS` | hashes of every data and output file |

Not included: the desktop app (in development) and model weights.

## License
Code: MIT (see `LICENSE`). The documents in `data/docs/` are public SEC and FDA records.
