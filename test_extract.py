"""
Self-test for extract.py.

Run: `python test_extract.py`                 -> defensive/parsing unit tests only
Run: `python test_extract.py YOUR_GROQ_KEY`   -> also runs the 10 real sample
                                                  transcripts against the live
                                                  Groq API and reports accuracy

IMPORTANT (per project instructions): no Groq API key was available at
build time. The unit tests below verify _coerce()'s defensive parsing
(malformed JSON, wrong types, out-of-schema values) using a stubbed Groq
client -- they do NOT verify real extraction accuracy, because that
requires an actual model call. The 10 SAMPLE_CASES are the real go/no-go
accuracy test and MUST be run with a real key (`python test_extract.py
<key>`) before trusting voice entry for the demo. Until that's done,
treat voice extraction as unverified and keep manual entry as the primary
path, per the kickoff instructions.
"""

import sys
from unittest.mock import MagicMock, patch

import extract

# --- 10 realistic sample transcripts (Urdu/English code-switched), with the
# CORRECT expected extraction for each. Includes 2 deliberately ambiguous ones.
SAMPLE_CASES = [
    ("Ali ne paanch sau rupay udhaar liya",
     {"customer_name": "Ali", "amount": 500, "type": "credit_given"}),
    ("Fatima ne teen sau rupay wapis kiye",
     {"customer_name": "Fatima", "amount": 300, "type": "payment_received"}),
    ("maine Usman ko do hazar rupay ka saman udhaar par diya",
     {"customer_name": "Usman", "amount": 2000, "type": "credit_given"}),
    ("Bilal paid back 150 rupees today",
     {"customer_name": "Bilal", "amount": 150, "type": "payment_received"}),
    ("Ayesha ne cash mein chaar sau rupay ka saman khareeda",
     {"customer_name": "Ayesha", "amount": 400, "type": "sale"}),
    ("sold two packets of biscuits for 50 rupees cash",
     {"customer_name": None, "amount": 50, "type": "sale"}),
    ("Sara ka hazar rupay udhaar baaki hai, aaj us ne paanch sau diye",
     {"customer_name": "Sara", "amount": 500, "type": "payment_received"}),
    ("Ahmed ne 1200 rupay udhaar liya samaan ke liye",
     {"customer_name": "Ahmed", "amount": 1200, "type": "credit_given"}),
    # -- ambiguous / tricky --
    ("kuch samajh nahi aaya, phir se bolna",
     {"customer_name": None, "amount": None, "type": "unknown"}),
    ("Zara aaj dukan pe aayi thi",
     {"customer_name": "Zara", "amount": None, "type": "unknown"}),
]


def run_unit_tests():
    """Defensive parsing tests using a stubbed Groq client (no network/API key)."""
    cases = [
        ('{"customer_name":"Ali","amount":500,"type":"credit_given"}',
         {"customer_name": "Ali", "amount": 500.0, "type": "credit_given"}),
        ('not valid json at all',
         extract._NULL_RESULT),
        ('{"customer_name":"Ali","amount":"five hundred","type":"credit_given"}',
         {"customer_name": "Ali", "amount": None, "type": "credit_given"}),
        ('{"customer_name":null,"amount":null,"type":"made_up_type"}',
         {"customer_name": None, "amount": None, "type": "unknown"}),
        ('{"amount":300}',
         {"customer_name": None, "amount": 300.0, "type": "unknown"}),
        ('[]',
         extract._NULL_RESULT),
    ]

    passed = 0
    for content, expected in cases:
        mock_response = MagicMock()
        mock_response.choices[0].message.content = content
        with patch("extract.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_response
            result = extract.extract_transaction("irrelevant transcript", "fake-key")
        ok = result == expected
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] input={content!r} -> {result}")

    print(f"\nUnit tests: {passed}/{len(cases)} passed.\n")
    assert passed == len(cases), "Some defensive-parsing unit tests failed."


def run_live_accuracy_test(api_key: str):
    """Runs the 10 real sample transcripts against the live Groq API."""
    passed = 0
    for transcript, expected in SAMPLE_CASES:
        try:
            result = extract.extract_transaction(transcript, api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {transcript!r} -> API call failed: {exc}")
            continue
        ok = (
            result["type"] == expected["type"]
            and result["amount"] == expected["amount"]
            and (result["customer_name"] or "").lower()
            == (expected["customer_name"] or "").lower()
        )
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {transcript!r}")
        print(f"         expected={expected} got={result}")

    print(f"\nLive accuracy: {passed}/{len(SAMPLE_CASES)}.")
    if passed < 8:
        print(
            "\n*** GO/NO-GO SIGNAL: below the 8/10 target. Per the kickoff "
            "instructions, treat voice entry as a stretch/demo-only feature "
            "and keep manual entry as the primary path until the prompt is "
            "iterated further. ***"
        )


if __name__ == "__main__":
    run_unit_tests()
    if len(sys.argv) > 1:
        run_live_accuracy_test(sys.argv[1])
    else:
        print(
            "No Groq API key passed -- skipping live accuracy test.\n"
            "Run `python test_extract.py <your_groq_api_key>` once you have "
            "one, BEFORE relying on voice entry for the demo."
        )
