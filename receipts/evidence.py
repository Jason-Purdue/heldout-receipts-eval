"""
EVIDENCE RECEIPTS: proof that a claim is, or is not, stated by a specific span of a specific document.

The model may PROPOSE a quote; it never decides the
verdict. issue() derives the verdict from three mechanical checks, and verify() re-derives everything from the
claim, the quote and the document. Anyone holding the document can re-check a receipt without trusting us or
the model.

    check quote_in_source   the quote occurs in the document (whitespace collapsed on both sides, nothing else)
    check answer_in_quote   the claimed answer occurs in the quote
    check keyword_in_quote  at least one content word of the question occurs in the quote

    verdict SUPPORTED    all three checks pass
            UNSUPPORTED  a quote was given and some check failed
            NOT_FOUND    no answer claimed, or the quote is NONE

Encoding: canonical JSON and SHA-256 (canon_min.py). Chaining: append-only, seq + prev_hash + receipt_hash,
verified end to end.
"""
import hashlib, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canon_min import canonical, sha256_hex          # noqa: E402

SCHEMA = "IWJJ_EVIDENCE_V1"
VERSION = 1
GENESIS = "0" * 64
NONE_QUOTE = "NONE"
# Same stopword list as the desktop app's keyword extractor, so "keyword" means the same thing on both sides.
STOPWORDS = {"what", "who", "when", "where", "why", "how", "is", "the", "a", "an", "for", "of", "in", "to", "and",
             "or", "be", "are", "was", "were", "much", "long", "many", "does", "do", "did", "will", "would", "could",
             "this", "that", "these", "those", "it", "its"}
FIELDS = {"schema", "version", "seq", "prev_hash", "question", "answer", "doc_id", "doc_sha256", "quote",
          "quote_start", "quote_end", "quote_sha256", "checks", "verdict", "receipt_hash"}


class ReceiptError(ValueError):
    pass


def collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def keywords(question):
    return [w for w in re.split(r"[^0-9a-z]+", question.lower()) if len(w) > 2 and w not in STOPWORDS]


def _norm_value(s):
    return re.sub(r"[\s,]", "", s.lower())


def _checks(question, answer, quote, doc):
    """-> (checks dict, start, end) in the collapsed document. Pure function of its inputs."""
    d = collapse(doc)
    q = collapse(quote) if quote else ""
    start = d.find(q) if q and q != NONE_QUOTE else -1
    checks = {
        "quote_in_source": start >= 0,
        "answer_in_quote": bool(answer) and start >= 0 and _norm_value(answer) in _norm_value(q),
        "keyword_in_quote": start >= 0 and any(k in q.lower() for k in keywords(question)),
    }
    return checks, start, (start + len(q) if start >= 0 else -1)


def _verdict(answer, quote, checks):
    if not answer or not quote or collapse(quote) == NONE_QUOTE:
        return "NOT_FOUND"
    return "SUPPORTED" if all(checks.values()) else "UNSUPPORTED"


def _hash(rec):
    return sha256_hex(canonical({k: v for k, v in rec.items() if k != "receipt_hash"}))


def issue(question, answer, quote, doc, doc_id, prev=None):
    """Build the next receipt in a chain. prev is the previous receipt (None for the first)."""
    checks, start, end = _checks(question, answer, quote, doc)
    rec = {"schema": SCHEMA, "version": VERSION,
           "seq": 0 if prev is None else prev["seq"] + 1,
           "prev_hash": GENESIS if prev is None else prev["receipt_hash"],
           "question": question, "answer": answer, "doc_id": doc_id,
           "doc_sha256": sha256_hex(collapse(doc).encode()),
           "quote": quote, "quote_start": start, "quote_end": end,
           "quote_sha256": sha256_hex(collapse(quote).encode()) if quote else None,
           "checks": checks, "verdict": _verdict(answer, quote, checks)}
    rec["receipt_hash"] = _hash(rec)
    return rec


def verify(rec, doc):
    """Re-derive one receipt from its claim, its quote and the document. Raises ReceiptError on any mismatch."""
    if set(rec) != FIELDS or rec["schema"] != SCHEMA or rec["version"] != VERSION:
        raise ReceiptError("not an IWJJ_EVIDENCE_V1 receipt")
    if _hash(rec) != rec["receipt_hash"]:
        raise ReceiptError("receipt altered after issue")
    if sha256_hex(collapse(doc).encode()) != rec["doc_sha256"]:
        raise ReceiptError("document is not the one the receipt was issued against")
    again = issue(rec["question"], rec["answer"], rec["quote"], doc, rec["doc_id"])
    for k in ("checks", "verdict", "quote_start", "quote_end", "quote_sha256"):
        if again[k] != rec[k]:
            raise ReceiptError(f"{k} does not re-derive")
    return rec["verdict"]


def verify_chain(recs, docs):
    """recs in order; docs: {doc_id: text}. Checks every link and every receipt."""
    prev = GENESIS
    for i, r in enumerate(recs):
        if r.get("seq") != i or r.get("prev_hash") != prev:
            raise ReceiptError(f"chain broken at seq {i}")
        verify(r, docs[r["doc_id"]])
        prev = r["receipt_hash"]
    return True


# ============================================================================
# v2 checks. v1 above is unchanged, so every v1 receipt still verifies by its own rules. v2 closes five known
# attacks: function-word keywords, two values in one quote, partial numbers, whole-document quotes, a wrong date
# beside the right one. Even v2 shows co-occurrence under tighter rules, not meaning.
# ============================================================================
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as _SKLEARN_STOPWORDS   # published list, not tuned here

V2_MAX_QUOTE_CHARS = 300
V2_STOPWORDS = STOPWORDS | set(_SKLEARN_STOPWORDS)
_SENTENCE_BREAK = re.compile(r"[.!?][\"”)]?\s+[A-Z]")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = re.compile(rf"\b(?:{_MONTHS}) \d{{1,2}}, \d{{4}}\b")
_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


def _num(s):
    return s.replace(",", "").rstrip(".")


def _values(pattern, text):
    return {_num(re.sub(r"[$\s]", "", m.group(0))) if pattern is not _DATE else m.group(0) for m in pattern.finditer(text)}


def _answer_type(answer):
    if _DATE.search(answer):
        return _DATE
    if "$" in answer:
        return _MONEY
    if re.search(r"\d", answer):
        return _NUMBER
    return None


def _whole_token(answer, quote):
    nums = [_num(n) for n in _NUMBER.findall(answer)]
    if nums and not _DATE.search(answer):
        quote_nums = {_num(n) for n in _NUMBER.findall(quote)}
        return all(n in quote_nums for n in nums)
    return re.search(r"(?<!\w)" + re.escape(collapse(answer).lower()) + r"(?!\w)", quote.lower()) is not None


def keywords_v2(question, answer=""):
    answer_words = set(re.split(r"[^0-9a-z]+", (answer or "").lower()))
    return [w for w in re.split(r"[^0-9a-z]+", question.lower())
            if len(w) > 2 and w not in V2_STOPWORDS and w not in answer_words]


def checks_v2(question, answer, quote, doc):
    """-> dict of the five v2 checks. Pure function of its inputs."""
    d = collapse(doc)
    q = collapse(quote) if quote else ""
    found = bool(q) and q != NONE_QUOTE and d.find(q) >= 0
    kind = _answer_type(answer or "")
    return {
        "quote_in_source": found,
        "quote_one_sentence": found and len(q) <= V2_MAX_QUOTE_CHARS and not _SENTENCE_BREAK.search(q),
        "answer_whole_token": found and bool(answer) and _whole_token(answer, q),
        "answer_unambiguous": found and bool(answer) and (kind is None or len(_values(kind, q)) == 1),
        "keyword_whole_word": found and any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", q.lower())
                                            for k in keywords_v2(question, answer)),
    }


def verdict_v2(question, answer, quote, doc):
    if not answer or not quote or collapse(quote) == NONE_QUOTE:
        return "NOT_FOUND"
    return "SUPPORTED" if all(checks_v2(question, answer, quote, doc).values()) else "UNSUPPORTED"
