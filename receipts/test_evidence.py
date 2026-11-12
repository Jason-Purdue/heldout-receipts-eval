"""Tests for evidence.py: every check must be able to fail, and every kind of tampering must be caught."""
import copy, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import ReceiptError, issue, verify, verify_chain   # noqa: E402
import evidence   # noqa: E402

DOC = ("Each share was converted into the right to receive (A) $65.60 (the “Closing Amount”) in cash.\n"
       "On November 13, 2025, Pfizer Inc.   completed its acquisition of Metsera, Inc.")
Q = "What is the closing amount per share?"


def test_supported():
    r = issue(Q, "$65.60", "$65.60 (the “Closing Amount”) in cash", DOC, "d")
    assert r["verdict"] == "SUPPORTED" and verify(r, DOC) == "SUPPORTED"


def test_whitespace_collapsed_but_nothing_else():
    r = issue("When was the acquisition completed?", "November 13, 2025",
              "On November 13, 2025, Pfizer Inc. completed its acquisition", DOC, "d")
    assert r["checks"]["quote_in_source"] and r["verdict"] == "SUPPORTED"


@pytest.mark.parametrize("answer,quote,failed", [
    ("$65.60", "$65.60 (the Closing Amount) in cash", "quote_in_source"),        # straight quotes: not in doc
    ("$9.65", "$65.60 (the “Closing Amount”) in cash", "answer_in_quote"),
    ("$65.60", "(A) $65.60", "keyword_in_quote"),                                  # no question word
])
def test_each_check_can_fail(answer, quote, failed):
    r = issue(Q, answer, quote, DOC, "d")
    assert not r["checks"][failed] and r["verdict"] == "UNSUPPORTED"


def test_none_and_null():
    assert issue(Q, "$65.60", "NONE", DOC, "d")["verdict"] == "NOT_FOUND"
    assert issue(Q, None, None, DOC, "d")["verdict"] == "NOT_FOUND"


@pytest.mark.parametrize("field,value", [("quote", "$65.60 in cash"), ("verdict", "SUPPORTED"),
                                         ("answer", "$66.00"), ("doc_sha256", "0" * 64)])
def test_tampering_caught(field, value):
    r = issue(Q, "$9.65", "$65.60 (the “Closing Amount”) in cash", DOC, "d")
    t = copy.deepcopy(r)
    t[field] = value
    with pytest.raises(ReceiptError):
        verify(t, DOC)


def test_forged_rehash_still_caught():
    """Editing the verdict AND recomputing receipt_hash must still fail: the verdict has to re-derive."""
    from evidence import _hash
    r = issue(Q, "$9.65", "$65.60 (the “Closing Amount”) in cash", DOC, "d")
    r["verdict"] = "SUPPORTED"
    r["receipt_hash"] = _hash(r)
    with pytest.raises(ReceiptError, match="re-derive"):
        verify(r, DOC)


def test_wrong_document_caught():
    r = issue(Q, "$65.60", "$65.60 (the “Closing Amount”) in cash", DOC, "d")
    with pytest.raises(ReceiptError, match="document"):
        verify(r, DOC.replace("65.60", "66.60"))


def test_chain():
    a = issue(Q, "$65.60", "$65.60 (the “Closing Amount”) in cash", DOC, "d")
    b = issue(Q, None, None, DOC, "d", prev=a)
    assert verify_chain([a, b], {"d": DOC})
    with pytest.raises(ReceiptError, match="chain"):
        verify_chain([b, a], {"d": DOC})
    with pytest.raises(ReceiptError, match="chain"):
        verify_chain([a, issue(Q, None, None, DOC, "d")], {"d": DOC})   # second link not chained to the first


# ---------------------------------------------------------------- v2 attack suite
# Text excerpts copied from a public SEC 8-K (Metsera, Inc., November 2025).
DOC_8K = ("On November 13, 2025, Pfizer Inc., a Delaware corporation, completed its previously announced acquisition "
          "of the Company, pursuant to the Merger Agreement dated September 21, 2025. Each share was converted into "
          "the right to receive (A) $65.60 (the “Closing Amount”) in cash, plus (B) one contractual contingent value "
          "right (a “CVR”) per share. Each CVR represents a non-tradable contractual contingent right to receive (A) "
          "$4.60 per CVR in cash, payable upon the initiation of the first Phase 3 Clinical Trial.")
Q_AMOUNT = "What is the closing amount per share?"
Q_DATE = "When did Pfizer complete the acquisition of Metsera?"


@pytest.mark.parametrize("name,question,answer,quote", [
    ("A function-word keyword (M1)", Q_AMOUNT, "$4.60",
     "$4.60 per CVR in cash, payable upon the initiation of the first Phase 3 Clinical Trial"),
    ("B two values in one quote", Q_AMOUNT, "$4.60",
     "receive (A) $65.60 (the “Closing Amount”) in cash, plus (B) one contractual contingent value right (a “CVR”) "
     "per share. Each CVR represents a non-tradable contractual contingent right to receive (A) $4.60"),
    ("D partial number", Q_AMOUNT, "65", "$65.60 (the “Closing Amount”) in cash"),
    ("E whole-document quote", Q_AMOUNT, "$4.60", DOC_8K),
    ("G wrong date beside the right one", Q_DATE, "September 21, 2025",
     "On November 13, 2025, Pfizer Inc., a Delaware corporation, completed its previously announced acquisition of "
     "the Company, pursuant to the Merger Agreement dated September 21, 2025."),
])
def test_v2_red_team_attacks_are_caught(name, question, answer, quote):
    assert evidence.verdict_v2(question, answer, quote, DOC_8K) == "UNSUPPORTED", (name, evidence.checks_v2(question, answer, quote, DOC_8K))


@pytest.mark.parametrize("question,answer,quote", [
    (Q_AMOUNT, "$65.60", "$65.60 (the “Closing Amount”) in cash"),
    (Q_DATE, "November 13, 2025", "On November 13, 2025, Pfizer Inc., a Delaware corporation, completed its "
                                  "previously announced acquisition of the Company"),
])
def test_v2_positive_controls_still_supported(question, answer, quote):
    """Control: a v2 that rejects everything would 'catch' every attack. Correct answers with proper quotes must pass."""
    assert evidence.verdict_v2(question, answer, quote, DOC_8K) == "SUPPORTED", evidence.checks_v2(question, answer, quote, DOC_8K)
