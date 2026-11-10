import unittest
from core.gnani_client import (
    match_member_from_roster,
    match_member_from_text,
    ml_to_phonetic,
    build_expanded_keyterms,
    process_voice_entry
)
from unittest.mock import patch

class TestCrossScriptMatching(unittest.TestCase):
    def test_ml_to_phonetic_normalization(self):
        self.assertEqual(ml_to_phonetic("ഹുസൈൻ"), "husain")
        self.assertEqual(ml_to_phonetic("Husain"), "husain")
        self.assertEqual(ml_to_phonetic("Hussain"), "husain")
        self.assertEqual(ml_to_phonetic("രാജീവ്"), "rajiv")
        self.assertEqual(ml_to_phonetic("Rajeev"), "rajiv")
        self.assertEqual(ml_to_phonetic("പ്രിയ"), "priya")
        self.assertEqual(ml_to_phonetic("Priya"), "priya")

    def test_cross_script_roster_matching_husain(self):
        roster = ["രാജീവ്", "ഹുസൈൻ", "പ്രിയ", "ലീല"]

        # 1. Speaking Husain in Latin script (Pass 2 output) against Malayalam roster
        name, score = match_member_from_roster("", "husain 100 roopa thrift", roster)
        self.assertEqual(name, "ഹുസൈൻ")
        self.assertGreaterEqual(score, 85.0)

        # 2. Speaking Hussain with double 's'
        name, score = match_member_from_roster("", "hussain 500 roopa loan", roster)
        self.assertEqual(name, "ഹുസൈൻ")
        self.assertGreaterEqual(score, 85.0)

        # 3. Exact Malayalam script in Pass 1 transcript
        name, score = match_member_from_roster("ഹുസൈൻ 100 രൂപ", "", roster)
        self.assertEqual(name, "ഹുസൈൻ")
        self.assertEqual(score, 100.0)

    def test_cross_script_roster_matching_rajeev_and_priya(self):
        roster = ["രാജീവ്", "ഹുസൈൻ", "പ്രിയ", "തോമസ്"]

        # Rajeev
        name, score = match_member_from_roster("", "rajeev 1000 roopa loan", roster)
        self.assertEqual(name, "രാജീവ്")
        self.assertGreaterEqual(score, 85.0)

        # Priya
        name, score = match_member_from_roster("", "priya 50 roopa pizha", roster)
        self.assertEqual(name, "പ്രിയ")
        self.assertGreaterEqual(score, 85.0)

    def test_english_roster_with_malayalam_transcripts(self):
        roster = ["Rajeev", "Husain", "Priya", "Thomas"]

        name, score = match_member_from_roster("ഹുസൈൻ 100 രൂപ", "", roster)
        self.assertEqual(name, "Husain")
        self.assertGreaterEqual(score, 85.0)

        name, score = match_member_from_roster("രാജീവ് 1000 രൂപ", "", roster)
        self.assertEqual(name, "Rajeev")
        self.assertGreaterEqual(score, 85.0)

    def test_build_expanded_keyterms(self):
        roster = ["ഹുസൈൻ", "രാജീവ്"]
        keyterms = build_expanded_keyterms(roster)
        # Must include both Malayalam script and phonetic Latin versions
        self.assertIn("ഹുസൈൻ", keyterms)
        self.assertIn("Husain", keyterms)
        self.assertIn("രാജീവ്", keyterms)
        self.assertIn("Rajiv", keyterms)
        self.assertIn("thrift", keyterms)
        self.assertIn("loan", keyterms)

    def test_unrecognized_member_reason_string(self):
        with patch("core.gnani_client.transcribe_clip") as mock_stt:
            mock_stt.side_effect = [
                {"success": True, "transcript": "unknown person 100 roopa"},
                {"success": True, "transcript": "unknown person 100 roopa"}
            ]
            res = process_voice_entry(b"fake_bytes", ["രാജീവ്", "ഹുസൈൻ"])
            self.assertEqual(res["matched_member"], "Unknown")
            self.assertEqual(res["status"], "amber")
            # Must NOT contain Kudumbashree
            self.assertFalse(any("Kudumbashree" in r for r in res["reasons"]))
            self.assertTrue(any("അംഗത്തിന്റെ പേര് പട്ടികയിൽ വ്യക്തമായി തിരിച്ചറിഞ്ഞില്ല" in r for r in res["reasons"]))

if __name__ == "__main__":
    unittest.main()

