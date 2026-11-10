import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gtts import gTTS
from core.gnani_client import process_voice_entry

scenarios = [
    ("Leela 100 roopa thrift", "Leela", "thrift", 100.0),
    ("Radha 1000 roopa loan vaaypa", "Radha", "loan_disbursement", 1000.0),
    ("Chitra 50 roopa pizha adachu", "Chitra", "fine", 50.0),
    ("Meera 500 roopa repayment adachu", "Meera", "repayment", 500.0),
    ("Radha 500 roopa vaaypa adachu", "Radha", "repayment", 500.0),
]

roster = ["Leela", "Radha", "Chitra", "Meera", "Suma"]

def run():
    print("Testing all 4 Kudumbashree speech scenarios...")
    for text, exp_member, exp_event, exp_amt in scenarios:
        fp = io.BytesIO()
        tts = gTTS(text=text, lang="ml")
        tts.write_to_fp(fp)
        audio_bytes = fp.getvalue()
        res = process_voice_entry(audio_bytes, roster)
        print(f"\nScenario: '{text}'")
        print(f"  -> Extracted: member={res['matched_member']}, event={res['event_type']}, amount={res['amount']}, status={res['status']}")
        print(f"  -> P1 Transcript: {res['transcript_pass1']}")
        assert res["matched_member"] == exp_member, f"Expected member {exp_member}, got {res['matched_member']}"
        assert res["event_type"] == exp_event, f"Expected event {exp_event}, got {res['event_type']}"
        assert res["amount"] == exp_amt, f"Expected amount {exp_amt}, got {res['amount']}"

    print("\n✓ ALL 4 SCENARIOS PASSED WITH EXACT MATCHES!")

if __name__ == "__main__":
    run()

