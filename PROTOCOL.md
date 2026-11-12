# Protocol

Every rule below was fixed before the stage it governs was run, and the documents that fixed them were frozen by
SHA-256 at the time. Those originals contain private working notes and are held by the authors; their hashes are
listed at the end so they can be checked against the originals on request. A hash shows a document has not changed
since; it does not, by itself, prove when it was written.

## 1. Documents (chosen by rule, before any was opened)
- **Business:** from SEC EDGAR's live list of the latest 8-K filings (read 8 Nov 2026, 11:09 PM ET), the first two
  filings from distinct companies that attach an EX-99.1 press release: TEN Holdings, Inc. and bioAffinity
  Technologies, Inc. Both the 8-K and the press release, for each.
- **Legal:** from the same list, the first filing attaching an EX-10.x or EX-2.1 under 150 KB: the First Amendment to
  the Merger Agreement of Pono Capital Four, Inc.
- **Medical:** openFDA human prescription drug labels with a dosage section, skip = 1000 (a round number chosen before
  any result was seen), the first two distinct drugs: divalproex sodium and temazepam.
- **Untrimmed.** SEC HTML was converted to text by one fixed procedure and checked byte-for-byte against a hash taken
  at download. Labels are every text field of the openFDA record, in order (raw record in `data/docs/`).

## 2. Questions
- Code listed every date, dollar amount, percentage and number-with-unit in each document and shuffled them with a
  fixed seed (`tools/candidates.py`, seed 20261108). One question was written per value, in that order. A value that
  could not carry a unique question was logged as skipped with its reason (14 skips).
- Where the sampled value is one end of a range ("50 to 100 mcg/mL"), the answer is the whole range as stated.
- Three questions ask who signed a document (chosen by hand). 23 questions are deliberately unanswerable.
- Total: 100 questions on 7 documents; 77 answerable, 23 unanswerable.
- Mechanical checks (`tools/check_key.py`): every source passage is in its document; every accepted answer is in its
  passage; no sampled value was dropped without a log entry. Each check was shown to fire on a planted error first.
- **Human check.** The questions and answers were written with an AI assistant (Claude). Jason Purdue checked a
  seeded random 20 (15 answerable, 5 unanswerable; seed 1122): 0 errors. With n = 20 the true error rate could
  still be as high as about 14% (one-sided 95% bound).
- Nothing in the set was used to tune the app, the checks or the prompts.

## 3. Stage 1: the answer engine alone
The desktop app's real query path (document ingest with its own chunking and embedder, then its query function as the
interface calls it), one fresh store per document, the language-model tier switched off. Outcomes: CORRECT, PARTIAL,
WRONG, MISS (said "not found" although the document states it), CORRECT_NOT_FOUND, ROUTED_OUT (passed on to a later
tier). **Rule:** "never wrong on unseen documents" survives only if WRONG + PARTIAL = 0.

## 4. Stage 2: models as judges
"Does the source text directly state that X is the answer to the question?" Yes or No.
- **True pair** per answerable question: the accepted answer with its source passage.
- **Fake pair** per answerable question: a value of the same kind (date, money, percent, unit) from the same document,
  drawn by a seeded generator (seed 20261109) among values the scorer does not accept, shown with its own sentence.
  Signature questions use the other named signatory, if any. 77 true and 75 fake pairs (2 skipped: one signatory).
- **Arms:** `main`, as above; `full_sentence`, added before any judge ran, where each true pair shows the full sentence
  containing its passage (fakes unchanged), because a judge could otherwise key on the passage's shape. If a model's
  accuracy moves by 0.10 or more between arms, both numbers are quoted together.
- **Rule:** a GOOD JUDGE has accuracy >= 0.90 and accepts at most 10% of fakes.

## 5. Stage 3: pick from the engine's shortlist, then check the quote
The app's shortlist export (up to 4 options plus "None of these"), shown in two orders (seed 20261105); a pick counts
only if both orders agree. The model then quotes the words that state its answer, and code checks the quote
(`receipts/evidence.py`, v2: the quote is in the document, is one sentence of at most 300 characters, holds the answer
as a whole token, holds exactly one value of the answer's type, and contains a question keyword).
**Arms:** PICK (alone), V2 (quote check), WIDEN (quote widened by code to its full sentence, then V2).
**Rules:** the quote check "holds" for a model and arm if WRONG <= 1 of 100 (also evaluated as WRONG + PARTIAL;
the stricter is the headline). WIDEN "helps" if it adds at least 5 CORRECT over V2 with WRONG <= 1.
Fixed before Stage 3 ran: the engine's known Stage 1 type bug was NOT fixed first, so Stage 3 measures the same app.

## 6. Models
| model | how it was run |
|---|---|
| Qwen3.6-35B-A3B (Alibaba, open weights), 2-bit GGUF quantization, 10.55 GB, file SHA-256 4BB9C261E5F6164114ABF1F2E35C477439F8ABE25D328C67745BCA493F209DC7. Quantization recipe not published; results may differ with other quantizations | llama.cpp build b11756, chat template, grammar-limited Yes/No and option letters, greedy |
| google/gemma-4-31B (base model) | 4-bit, streamed from system RAM; raw prompt; Yes-minus-No logit margin |
| Phi-3-mini-4k-instruct, q4 GGUF | llama.cpp build b12191, as the Qwen3.6 row |
| Qwen/Qwen2.5-3B-Instruct | fp16; chat template for Stage 2, raw prompt for Stage 3 (each as in an earlier development run) |
Prompts: `tools/prompts.py`, exactly as run.

## 7. Predictions, recorded before each stage ran
| stage | Jason Purdue | Claude (AI collaborator) |
|---|---|---|
| 1 | 4 or more WRONG; finds under 30% of the 77 | WRONG + PARTIAL between 1 and 3; finds 15 to 25; ROUTED_OUT >= 5 |
| 2 | the Qwen3.6-35B-A3B judge "drops a lot" from its earlier development score (read as: accuracy < 0.80, or no longer the most accurate judge) | it stays the best judge at 0.85-0.93; Phi-3 accepts >= 70% of fakes; Qwen2.5-3B accuracy 0.60-0.75 |
| 3 | none recorded | the quote check holds for every model; WIDEN helps the Qwen3.6 model by >= 5 |

## 8. Frozen originals (held by the authors)
| document | SHA-256 |
|---|---|
| question-set manifest (15 files) | 44d25f5e71dc9a8e2ce0320db697735ea38505fe56f1dfad82ce9787303ce0c2 |
| pre-registration (all stages) | 2053b4facdbbd18f63060a32889b0d210709f2a374116979a51c23d4b092dd84 |
| addendum A (`full_sentence` arm) | 935224ea07c8befbdbed8a2e6a1f1c6001f9c9666020173dd0866832b4f5d64e |
| addendum B (Stage 3 mechanics; scorer date fix) | 73af4f264a1beed00565488b55bed38d3cb59a0af9c3071075ebbfdd100e6fdb |
| addendum C (sentence boundary for WIDEN) | d0af4e3b34e5176816a1da95a73f353e88c291f85bfb0d3bf8b562205569f92e |
