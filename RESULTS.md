# Results

All numbers are held-out: none of these documents or questions was seen before the rules were frozen, and nothing was
tuned on them. Every number below is re-derived from the raw outputs by `python3 verify.py`.

## Stage 1: the answer engine alone (100 questions)
| outcome | n | |
|---|---|---|
| CORRECT | 2 | of 77 answerable (2.6%) |
| WRONG | 1 | "how long before retiring was the 30 mg capsule given?" answered "30 mg": a type rule for doses matched " mg" before the "how long" rule |
| PARTIAL | 0 | |
| MISS | 43 | said "not found" although the document states it |
| CORRECT_NOT_FOUND | 18 | of 23 unanswerable |
| ROUTED_OUT | 36 | passed to a later tier (31 answerable, 5 unanswerable) |

Rule "never wrong on unseen documents": **fails** (1 wrong). Of the 64 questions the engine settled itself, 63 were
right or an honest "not found". On an earlier 29-question development set the same engine had found 9 of 21 with 0
wrong; that result did not transfer. In two routed-out answers the app returned the start of its own internal prompt
as the answer text (a defect in that route; neither was scored).

## Stage 2: models as judges (77 true pairs, 75 hard fakes)
| judge | arm | true accepted | fakes accepted | accuracy | GOOD JUDGE |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B, 2-bit | main | 53 | **0** | 0.842 | no |
| Qwen3.6-35B-A3B, 2-bit | full_sentence | 63 | **0** | 0.908 | **yes** |
| gemma-4-31B base, 4-bit | main | 77 | 19 | 0.875 | no |
| gemma-4-31B base, 4-bit | full_sentence | 76 | 19 | 0.868 | no |
| Phi-3-mini, q4 | main | 77 | 33 | 0.783 | no |
| Phi-3-mini, q4 | full_sentence | 76 | 33 | 0.776 | no |
| Qwen2.5-3B-Instruct | main | 37 | 4 | 0.711 | no |
| Qwen2.5-3B-Instruct | full_sentence | 31 | 4 | 0.671 | no |

No model's accuracy moved by 0.10 or more between arms. The two strongest judges fail in **opposite directions**:
gemma-4-31B accepts every true answer and a quarter of the fakes; Qwen3.6-35B-A3B accepts no fake and rejects about a
third of true answers, mostly when the shown passage omits the company or period ("for the same period last year").

## Stage 3: pick from the shortlist, then check the quote (100 questions)
The shortlist contained the right answer for 23 of 77 answerable questions, which caps every picker.

| model | arm | CORRECT | WRONG | PARTIAL | INCONSISTENT | MISS | CORRECT_NONE /23 |
|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | PICK | 19 | 5 | 1 | 3 | 49 | 23 |
| | V2 | 2 | 1 | 0 | 3 | 71 | 23 |
| | WIDEN | 6 | 0 | 0 | 3 | 68 | 23 |
| gemma-4-31B | PICK | 16 | 6 | 1 | 11 | 45 | 21 |
| | V2 | 4 | 1 | 0 | 11 | 63 | 21 |
| | WIDEN | 4 | 1 | 0 | 11 | 63 | 21 |
| Phi-3-mini | PICK | 13 | 17 | 1 | 21 | 35 | 13 |
| | V2 | 3 | 2 | 0 | 21 | 55 | 19 |
| | WIDEN | 3 | 3 | 0 | 21 | 55 | 18 |
| Qwen2.5-3B-Instruct | PICK | 8 | 9 | 0 | 18 | 45 | 20 |
| | V2 | 0 | 0 | 0 | 18 | 61 | 21 |
| | WIDEN | 2 | 0 | 0 | 18 | 59 | 21 |

Rule "the quote check holds" (WRONG + PARTIAL <= 1): holds for Qwen3.6-35B-A3B, gemma-4-31B and Qwen2.5-3B; **fails**
for Phi-3 (2 in V2, 3 in WIDEN). WIDEN "helps" (+5 CORRECT): no model (Qwen3.6-35B-A3B +4).

Every wrong or partial pick by Qwen3.6-35B-A3B came when the right answer was not on the shortlist, and in 5 of the 6
its own quote named the right answer (picked "30 mg", quoted "1 hour"). The model found it; the shortlist did not offer it.

## Predictions
| stage | prediction | result |
|---|---|---|
| 1 | Jason: 4 or more WRONG | failed (1) |
| 1 | Jason: finds under 30% | held (2.6%) |
| 1 | Claude: WRONG + PARTIAL 1 to 3 | held (1) |
| 1 | Claude: finds 15 to 25 | failed (2) |
| 1 | Claude: ROUTED_OUT >= 5 | held (36) |
| 2 | Jason: the Qwen3.6 judge drops a lot (accuracy < 0.80 or not the most accurate) | held on `main` (gemma-4-31B more accurate); not on `full_sentence` |
| 2 | Claude: Qwen3.6 stays best at 0.85-0.93 | failed on `main` (0.842, second) |
| 2 | Claude: Phi-3 accepts >= 70% of fakes | failed (44%) |
| 2 | Claude: Qwen2.5-3B accuracy 0.60-0.75 | held (0.711) |
| 3 | Claude: the quote check holds for every model | failed (Phi-3) |
| 3 | Claude: WIDEN helps the Qwen3.6 model by >= 5 | failed (+4) |

## What the quote check cannot do (seen in this run)
- It compares numbers, not units: "30 mg" passed on the quote "30 minutes prior to bedtime".
- It proves co-occurrence, not meaning: the par value of the *preferred* stock passed for a *common* stock question.
- Receipts are tamper-evident (SHA-256), not signed: they show a record was not changed, not who made it.

## Errata (each recorded before the affected stage ran, unless stated)
1. The scorer first compared only the numbers in a date, so "April 14, 2025" matched "January 14, 2025". Found and
   fixed before Stage 3; re-scoring Stage 1 with the fix changed nothing. Stage 2's fake pairs had been drawn with the
   earlier scorer; rebuilding them today would change one fake (TP-4). The pairs as run are published.
2. The WIDEN step first looked for sentence boundaries in text with line breaks removed, merging table rows into one
   "sentence". Fixed before any Stage 3 model output existed.
3. During Stage 2, gemma-4-31B's `full_sentence` arm was lost to a time limit before its rows were saved; it was
   re-run with each row saved as it was judged. No other result was affected.
