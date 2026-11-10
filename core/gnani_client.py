import os
import re
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from rapidfuzz import process, fuzz

load_dotenv()

GNANI_API_KEY = os.getenv("GNANI_API_KEY", "")
GNANI_STT_URL = os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3")

ROSTER_MALAYALAM_MAP = {
    "ലീല": "Leela",
    "രാധ": "Radha",
    "ചിത്ര": "Chitra",
    "മീര": "Meera",
    "സുമ": "Suma"
}

SPOKEN_NUMBER_MAP = {
    # Malayalam transliterations & colloquial spoken forms
    "pathu": 10.0,
    "irupathu": 20.0,
    "muppathu": 30.0,
    "nalppathu": 40.0,
    "ambathu": 50.0,
    "anpathu": 50.0,
    "ambadu": 50.0,
    "arupathu": 60.0,
    "ezhupathu": 70.0,
    "enbathu": 80.0,
    "thonnooru": 90.0,
    "nooru": 100.0,
    "nuru": 100.0,
    "orunooru": 100.0,
    "irunooru": 200.0,
    "irunuru": 200.0,
    "munnooru": 300.0,
    "munnuru": 300.0,
    "nanooru": 400.0,
    "nanuru": 400.0,
    "anooru": 500.0,
    "annooru": 500.0,
    "anjooru": 500.0,
    "anjoor": 500.0,
    "aayiram": 1000.0,
    "ayiram": 1000.0,
    "oruaayiram": 1000.0,
    "randaayiram": 2000.0,
    "randayiram": 2000.0,
    "moonaayiram": 3000.0,
    "moonayiram": 3000.0,
    "naalaayiram": 4000.0,
    "naalayiram": 4000.0,
    "ayinaayiram": 5000.0,
    "ayyaayiram": 5000.0,
    "pathinaayiram": 10000.0,
    # Malayalam script
    "പത്ത്": 10.0,
    "ഇരുപത്": 20.0,
    "മുപ്പത്": 30.0,
    "നാല്പത്": 40.0,
    "അമ്പത്": 50.0,
    "അൻപത്": 50.0,
    "അമ്പതു": 50.0,
    "അറുപത്": 60.0,
    "എഴുപത്": 70.0,
    "എൺപത്": 80.0,
    "തൊണ്ണൂറ്": 90.0,
    "നൂറ്": 100.0,
    "ഇരുന്നൂറ്": 200.0,
    "മുന്നൂറ്": 300.0,
    "നാനൂറ്": 400.0,
    "അഞ്ഞൂറ്": 500.0,
    "അന്യോര്": 500.0,
    "അന്യോർ": 500.0,
    "ആയിരം": 1000.0,
    "രണ്ടായിരം": 2000.0,
    "മൂവായിരം": 3000.0,
    "അയ്യായിരം": 5000.0,
    "പതിനായിരം": 10000.0,
    # English terms
    "fifty": 50.0,
    "hundred": 100.0,
    "one hundred": 100.0,
    "two hundred": 200.0,
    "five hundred": 500.0,
    "thousand": 1000.0,
    "one thousand": 1000.0,
    "two thousand": 2000.0,
    "five thousand": 5000.0
}

def normalize_amount(text: str) -> float:
    """
    Extract numeric digits via regex, with fallback mapping for spoken numbers
    (ambathu/50: 50, nooru: 100, anooru: 500, aayiram: 1000, randaayiram: 2000, etc.).
    """
    if not text:
        return 0.0

    # 1. Search for numeric digits (e.g. 50, 100, 500, 1000, 250.50, 1,000)
    clean_text = text.replace("₹", " ").replace("Rs.", " ").replace("Rs", " ").replace("രൂപ", " ")
    digit_matches = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", clean_text)
    if digit_matches:
        val_str = digit_matches[0].replace(",", "")
        try:
            return float(val_str)
        except ValueError:
            pass

    # 2. Spoken word matching (check longest keys first to avoid partial conflicts)
    lower_text = text.lower()
    normalized_words = re.sub(r"[^\w\s\u0D00-\u0D7F]", " ", lower_text).split()
    joined_text = " ".join(normalized_words)

    sorted_spoken_keys = sorted(SPOKEN_NUMBER_MAP.keys(), key=len, reverse=True)
    for key in sorted_spoken_keys:
        if key in joined_text:
            return SPOKEN_NUMBER_MAP[key]

    return 0.0

def detect_audio_format(audio_bytes: bytes) -> tuple:
    """Detect whether audio is WAV or MP3, returning (filename, mime_type)."""
    if audio_bytes.startswith(b"RIFF"):
        return ("speech.wav", "audio/wav")
    return ("speech.mp3", "audio/mpeg")

def ml_to_phonetic(text: str) -> str:
    """
    Lightweight Malayalam-to-Latin phonetic transliteration helper.
    Maps Malayalam consonants, vowel signs, independent vowels, chillus,
    and handles inherent vowels so Malayalam script names (e.g. 'ഹുസൈൻ', 'രാജീവ്', 'പ്രിയ')
    and English script names (e.g. 'Husain', 'Rajeev', 'Priya') normalize to the same
    phonetic root representation for cross-script fuzzy matching (> 85% score).
    """
    if not text:
        return ""

    consonants = {
        'ക': 'k', 'ഖ': 'kh', 'ഗ': 'g', 'ഘ': 'gh', 'ങ': 'ng',
        'ച': 'ch', 'ഛ': 'ch', 'ജ': 'j', 'ഝ': 'jh', 'ഞ': 'nj',
        'ട': 't', 'ഠ': 'th', 'ഡ': 'd', 'ഢ': 'dh', 'ണ': 'n',
        'ത': 'th', 'ഥ': 'th', 'ദ': 'd', 'ധ': 'dh', 'ന': 'n',
        'പ': 'p', 'ഫ': 'f', 'ബ': 'b', 'ഭ': 'bh', 'മ': 'm',
        'യ': 'y', 'ര': 'r', 'ല': 'l', 'വ': 'v', 'ശ': 'sh', 'ഷ': 'sh', 'സ': 's', 'ഹ': 'h',
        'ള': 'l', 'ഴ': 'zh', 'റ': 'r'
    }
    vowel_signs = {
        'ാ': 'a', 'ി': 'i', 'ീ': 'i', 'ു': 'u', 'ൂ': 'u', 'ൃ': 'ri',
        'െ': 'e', 'േ': 'e', 'ൈ': 'ai', 'ൊ': 'o', 'ോ': 'o', 'ൌ': 'ou', 'ൗ': 'ou'
    }
    independent_vowels = {
        'അ': 'a', 'ആ': 'a', 'ഇ': 'i', 'ഈ': 'i', 'ഉ': 'u', 'ഊ': 'u', 'ഋ': 'ri',
        'എ': 'e', 'ഏ': 'e', 'ഐ': 'ai', 'ഒ': 'o', 'ഓ': 'o', 'ഔ': 'ou'
    }
    chillus = {'ൺ': 'n', 'ൻ': 'n', 'ർ': 'r', 'ൽ': 'l', 'ൾ': 'l', 'ൿ': 'k'}
    misc = {'ം': 'm', 'ഃ': 'h'}

    out = []
    chars = list(text)
    n = len(chars)
    for i, ch in enumerate(chars):
        if ch in consonants:
            p = consonants[ch]
            next_ch = chars[i + 1] if i + 1 < n else None
            if next_ch == '്':
                out.append(p)
            elif next_ch in vowel_signs:
                out.append(p)
            else:
                out.append(p + 'a')
        elif ch in vowel_signs:
            out.append(vowel_signs[ch])
        elif ch in independent_vowels:
            out.append(independent_vowels[ch])
        elif ch in chillus:
            out.append(chillus[ch])
        elif ch in misc:
            out.append(misc[ch])
        elif ch == '്':
            continue
        else:
            out.append(ch)

    res = ''.join(out).lower()
    res = re.sub(r'ee', 'i', res)
    res = re.sub(r'oo', 'u', res)
    res = re.sub(r'th', 't', res)
    res = re.sub(r'dh', 'd', res)
    res = re.sub(r'bh', 'b', res)
    res = re.sub(r'ph', 'f', res)
    res = re.sub(r'sh', 's', res)
    res = re.sub(r'zh', 'l', res)
    res = re.sub(r'([a-z])\1+', r'\1', res)
    res = re.sub(r'[^a-z0-9]', '', res)
    return res


def build_expanded_keyterms(keyterms: list) -> list:
    """
    Build dynamically expanded keyterm list from the active roster.
    Includes Malayalam script names, Latin phonetic roots, and financial keywords
    to bias Gnani Prisma STT across both Pass 1 (ITN) and Pass 2 (Transliterate).
    """
    if not keyterms:
        return []
    expanded = []
    for item in keyterms:
        if not item or not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in expanded:
            expanded.append(cleaned)

        # Phonetic Latin form for Malayalam names
        phonetic = ml_to_phonetic(cleaned)
        if phonetic and phonetic != cleaned.lower():
            p_cap = phonetic.capitalize()
            if p_cap not in expanded:
                expanded.append(p_cap)
            if phonetic not in expanded:
                expanded.append(phonetic)

        # Static bidirectional mapping check
        if cleaned in ROSTER_MALAYALAM_MAP and ROSTER_MALAYALAM_MAP[cleaned] not in expanded:
            expanded.append(ROSTER_MALAYALAM_MAP[cleaned])
        for k, v in ROSTER_MALAYALAM_MAP.items():
            if v.lower() == cleaned.lower() and k not in expanded:
                expanded.append(k)

    # Core SHG banking domain keywords
    domain_terms = [
        "thrift", "loan", "repayment", "fine", "vaaypa", "adachu", "pizha", "roopa",
        "സമ്പാദ്യം", "വായ്പ", "തിരിച്ചടവ്", "പിഴ", "രൂപ", "കണക്ക്", "അടവ്"
    ]
    for dt in domain_terms:
        if dt not in expanded:
            expanded.append(dt)
    return expanded


def transcribe_clip(audio_bytes: bytes, output_format: str = "transcribe",
                    keyterms: list = None) -> dict:
    """
    Calls Gnani Prisma v3.0 STT endpoint.
    - POST https://api.vachana.ai/stt/v3
    - Header: {"X-API-Key-ID": GNANI_API_KEY}
    - Form data: model="prisma-v3.0", audio_file=...
    - language_code="ml-IN,en-IN"
    - keyterms: JSON string (ensure_ascii=False)
    """
    if not GNANI_API_KEY:
        return {
            "success": False,
            "error": "GNANI_API_KEY is not set in environment or .env file.",
            "transcript": ""
        }

    headers = {
        "X-API-Key-ID": GNANI_API_KEY
    }

    data = {
        "model": "prisma-v3.0",
        "output_format": output_format,
        "language_code": "ml-IN,en-IN"
    }

    if keyterms:
        expanded_keyterms = build_expanded_keyterms(keyterms)
        data["keyterms"] = json.dumps(expanded_keyterms, ensure_ascii=False)

    filename, mime_type = detect_audio_format(audio_bytes)
    files = {
        "audio_file": (filename, audio_bytes, mime_type)
    }

    try:
        response = requests.post(
            GNANI_STT_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=25
        )

        if response.status_code == 200:
            res_json = response.json()
            transcript = ""
            if isinstance(res_json, dict):
                transcript = (
                    res_json.get("transcript") or
                    res_json.get("text") or
                    res_json.get("transcription") or
                    res_json.get("asr_output") or
                    (res_json.get("data") and isinstance(res_json["data"], dict) and (res_json["data"].get("transcript") or res_json["data"].get("text"))) or
                    ""
                )
                if not transcript and "results" in res_json and isinstance(res_json["results"], list) and res_json["results"]:
                    transcript = res_json["results"][0].get("transcript", "")
            elif isinstance(res_json, str):
                transcript = res_json

            return {
                "success": True,
                "status_code": 200,
                "transcript": transcript.strip(),
                "raw": res_json
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
                "transcript": ""
            }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Network/Connection error calling Gnani STT: {str(e)}",
            "transcript": ""
        }

def match_member_from_roster(transcript_p1: str, transcript_p2: str, roster_names: list) -> tuple:
    """
    Fuzzy match member name from dual transcripts against roster_names using rapidfuzz
    with cross-script (Malayalam <-> English) phonetic normalization.
    Returns (matched_name, confidence_score).
    If confidence <= 60 or no match, returns ("Unknown", score).
    """
    if not roster_names:
        return ("Unknown", 0.0)

    p1 = (transcript_p1 or "").strip()
    p2 = (transcript_p2 or "").strip()
    if not p1 and not p2:
        return ("Unknown", 0.0)

    # 1. Exact string containment check in either transcript (100% confidence)
    for name in roster_names:
        clean_name = name.strip()
        if clean_name and (clean_name in p1 or clean_name in p2):
            return (clean_name, 100.0)
        if clean_name and (clean_name.lower() in p1.lower() or clean_name.lower() in p2.lower()):
            return (clean_name, 100.0)

    # 2. Known bidirectional mapping check
    for ml_name, en_name in ROSTER_MALAYALAM_MAP.items():
        if (ml_name in p1 or en_name.lower() in p2.lower()):
            if en_name in roster_names:
                return (en_name, 100.0)
            if ml_name in roster_names:
                return (ml_name, 100.0)

    # 3. Extract complete Unicode words without splitting combining marks
    words_p1 = re.findall(r'[^\s,.;!?:()\[\]]+', p1)
    words_p2 = re.findall(r'[^\s,.;!?:()\[\]]+', p2)
    all_words = list(dict.fromkeys(words_p1 + words_p2))
    phonetic_words = [ml_to_phonetic(w) for w in all_words if len(w) >= 2]

    best_name = "Unknown"
    best_score = 0.0

    for name in roster_names:
        clean_name = name.strip()
        name_p = ml_to_phonetic(clean_name)

        # Cross-script phonetic matching (e.g. 'ഹുസൈൻ' <-> 'husain')
        for pw in phonetic_words:
            if name_p == pw and len(name_p) >= 3:
                return (clean_name, 100.0)
            score = fuzz.ratio(name_p, pw)
            if score > best_score:
                best_score = score
                best_name = clean_name

        # Same-script raw word matching
        for rw in all_words:
            score = fuzz.ratio(clean_name.lower(), rw.lower())
            if score > best_score:
                best_score = score
                best_name = clean_name

        # Full phrase token match
        full_text = f"{p1} {p2}".lower()
        score = fuzz.token_set_ratio(clean_name.lower(), full_text)
        if score > best_score:
            best_score = score
            best_name = clean_name

    if best_score > 60:
        return (best_name, float(best_score))
    return ("Unknown", float(best_score))


def match_member_from_text(text: str, roster_names: list) -> tuple:
    """
    Backwards-compatible wrapper calling match_member_from_roster.
    """
    return match_member_from_roster(text, text, roster_names)

def detect_event_type(text: str) -> str:
    """
    Classify Kudumbashree event type from text:
    Priority order:
    1st: 'fine' / 'pizha'
    2nd: 'repayment' ('repay', 'adak', 'adach', 'thirich') -> checked before loan so 'vaaypa adachu' is repayment
    3rd: 'loan_disbursement' ('loan', 'vaaypa')
    4th: 'thrift' (default)
    """
    lower_tx = text.lower()
    # 1st: Fine / Penalty
    if any(k in lower_tx for k in ["fine", "pizha", "പിഴ", "പിസാ", "pisa", "പെസ", "pesa", "penalty"]):
        return "fine"
    # 2nd: Repayment (checked before loan_disbursement so 'vaaypa adachu' -> repayment)
    elif any(k in lower_tx for k in ["repay", "റീപേ", "റീപേയ്മെന്റ്", "adak", "adach", "thirich", "തിരിച്ച", "അട", "അതാ", "അദാ", "അടച്ചു", "അദാക്ഷു", "അതാച്ചു"]):
        return "repayment"
    # 3rd: Loan Disbursement
    elif any(k in lower_tx for k in ["loan", "vaaypa", "vaypa", "വായ്പ", "borrow", "disbursement"]):
        return "loan_disbursement"
    # 4th: Default to Thrift
    else:
        return "thrift"

def process_voice_entry(audio_bytes: bytes, roster_names: list) -> dict:
    """
    Dual-pass transcription and disagreement detection:
    - Pass 1: output_format="transcribe" (Inverse Text Normalization).
    - Pass 2: output_format="transliterate" (Latin script).
    Executes Pass 1 and Pass 2 concurrently in parallel using ThreadPoolExecutor.
    - Fuzzy match member from roster_names.
    - Extract amounts amt1 and amt2.
    - Amber flag if amt1 != amt2, amt1 == 0.0, matched_member == "Unknown", or event_type == "loan_disbursement".
    - Otherwise green flag.
    """
    # Pass dynamically expanded active roster keyterms to both passes
    expanded_keyterms = build_expanded_keyterms(roster_names)

    # Execute Pass 1 and Pass 2 in parallel to cut latency in half
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(transcribe_clip, audio_bytes, output_format="transcribe", keyterms=expanded_keyterms)
        future2 = executor.submit(transcribe_clip, audio_bytes, output_format="transliterate", keyterms=expanded_keyterms)
        res1 = future1.result()
        res2 = future2.result()

    text1 = res1.get("transcript", "").strip()
    text2 = res2.get("transcript", "").strip()

    # Empty Pass 2 / Pass 1 Fallback:
    # If Pass 2 (transliteration) returned empty while Pass 1 succeeded, fall back to Pass 1
    # to avoid false-positive amount discrepancies against ₹0.00.
    pass2_fallback_used = False
    if not text2 and text1:
        text2 = text1
        pass2_fallback_used = True
    elif not text1 and text2:
        text1 = text2

    # Extract amounts
    amt1 = normalize_amount(text1)
    amt2 = normalize_amount(text2)

    final_amount = amt1 if amt1 > 0 else amt2

    combined_text = f"{text1} {text2}".strip()

    # Match member name using cross-script phonetic roster matching
    matched_member, member_score = match_member_from_roster(text1, text2, roster_names)

    # Detect event type (priority checks fine first)
    event_type = detect_event_type(combined_text)

    # Disagreement & risk detection
    reasons = []
    if amt1 != amt2 and not pass2_fallback_used:
        reasons.append(f"Dual-pass amount discrepancy: Pass 1 (ITN) extracted ₹{amt1:.2f}, while Pass 2 (Transliterate) extracted ₹{amt2:.2f}.")
    if amt1 == 0.0:
        reasons.append("Zero or undetectable amount in primary Inverse Text Normalization transcript.")
    if matched_member == "Unknown":
        reasons.append("അംഗത്തിന്റെ പേര് പട്ടികയിൽ വ്യക്തമായി തിരിച്ചറിഞ്ഞില്ല — ദയവായി താഴെ നിന്ന് ശരിയായ പേര് തിരഞ്ഞെടുക്കുക (Could not confidently match spoken name to the group roster — please verify the selected member below).")
    if event_type == "loan_disbursement":
        reasons.append("High-risk transaction: Loan disbursements require mandatory roll-call scrutiny.")

    status = "amber" if reasons else "green"

    return {
        "status": status,
        "matched_member": matched_member,
        "member_confidence": member_score,
        "event_type": event_type,
        "amount": final_amount,
        "amt1": amt1,
        "amt2": amt2,
        "transcript_pass1": text1,
        "transcript_pass2": text2,
        "pass2_fallback_used": pass2_fallback_used,
        "reasons": reasons,
        "pass1_result": res1,
        "pass2_result": res2
    }


GROUP_INDICATORS = [
    "koottayma", "koottaayma", "koottam", "sangham", "samithi", "group", "unit", "shg",
    "ward", "colony", "association", "ayalkkoottam", "ayalkootam",
    "കൂട്ടായ്മ", "സംഘം", "സമിതി", "അയൽക്കൂട്ടം", "ഗ്രൂപ്പ്", "കോളനി", "വാർഡ്", "യൂണിറ്റ്", "അസോസിയേഷൻ"
]

ROLE_KEYWORDS = {
    "secretary": "secretary",
    "secretery": "secretary",
    "sekeratary": "secretary",
    "സെക്രട്ടറി": "secretary",
    "president": "president",
    "presidant": "president",
    "പ്രസിഡന്റ്": "president",
    "member": "member",
    "അംഗം": "member"
}

FILLER_WORDS = {
    "and", "pinne", "pinneyum", "koodathe", "ennivar", "ennivaraanu", "aanu", "aane", "the", "is", "are",
    "name", "names", "members", "member", "per", "peer", "shg", "kudumbashree",
    "പേരുകൾ", "അംഗങ്ങൾ", "ആണ്", "എന്നിവർ"
}

def extract_onboarding_from_text(raw_tx: str) -> dict:
    """
    Parses a spoken or typed onboarding transcript to extract Group Name and Members with Roles.
    Handles phrases like:
      - 'Suryakanthi Koottayma, Leela Secretary, Radha President, Chitra, Meera'
      - 'Haritha Sangham, Shobhana, Anitha'
      - 'Ward 4 Kudumbashree'
      - 'Leela Secretary, Radha President, Chitra'
    """
    if not raw_tx or not raw_tx.strip():
        return {"transcript": "", "group_name": None, "members": []}

    clean_tx = raw_tx.strip()

    # 1. Break text into logical segments by punctuation or conjunction pauses
    segments = [s.strip() for s in re.split(r"[,;.\n|]|\b(?:pinne|and|pinneyum|koodathe)\b", clean_tx, flags=re.IGNORECASE) if s.strip()]

    extracted_group = None
    group_segment_idx = -1

    # Rule 1a: Check each segment for a community/group indicator
    for idx, seg in enumerate(segments):
        seg_lower = seg.lower()
        if any((re.search(r"\b" + re.escape(gi) + r"\b", seg_lower, re.I) if gi.isascii() else gi in seg_lower) for gi in GROUP_INDICATORS):
            extracted_group = seg.strip()
            group_segment_idx = idx
            break

    # Rule 1b: If no indicator was found, but the first segment has >= 2 words and NO role keyword
    if not extracted_group and segments:
        first_seg = segments[0]
        words_first = re.findall(r"[A-Za-z\u0D00-\u0D7F0-9\-]+", first_seg)
        has_role = any(w.lower() in ROLE_KEYWORDS for w in words_first)
        if len(words_first) >= 2 and not has_role:
            extracted_group = first_seg.strip()
            group_segment_idx = 0

    # Rule 2: If only a single segment exists in the entire transcript and no member/role is detected
    if not extracted_group and len(segments) == 1:
        words_only = re.findall(r"[A-Za-z\u0D00-\u0D7F0-9\-]+", segments[0])
        has_role = any(w.lower() in ROLE_KEYWORDS for w in words_only)
        if not has_role:
            extracted_group = segments[0].strip()
            group_segment_idx = 0

    if extracted_group:
        # Format group title nicely
        extracted_group = " ".join([w.title() if w.isascii() else w for w in extracted_group.split()])

    # 3. Collect remaining text for member extraction
    if group_segment_idx >= 0:
        member_segments = [seg for i, seg in enumerate(segments) if i != group_segment_idx]
        member_text = " , ".join(member_segments)
    else:
        member_text = clean_tx

    group_words = set(w.lower() for w in re.findall(r"[A-Za-z\u0D00-\u0D7F]+", extracted_group)) if extracted_group else set()

    words = re.findall(r"[A-Za-z\u0D00-\u0D7F]+", member_text)
    members = []
    i = 0
    while i < len(words):
        w = words[i]
        w_lower = w.lower()

        if w_lower in group_words or w_lower in FILLER_WORDS:
            i += 1
            continue

        # If current word is a role keyword (e.g. 'Secretary Leela')
        if w_lower in ROLE_KEYWORDS:
            role = ROLE_KEYWORDS[w_lower]
            if i + 1 < len(words):
                next_w = words[i + 1]
                if next_w.lower() not in ROLE_KEYWORDS and next_w.lower() not in FILLER_WORDS and next_w.lower() not in group_words:
                    name = next_w.title()
                    if name in ROSTER_MALAYALAM_MAP:
                        name = ROSTER_MALAYALAM_MAP[name]
                    if not any(m["name"].lower() == name.lower() for m in members):
                        members.append({"name": name, "role": role})
                    i += 2
                    continue
            elif members and members[-1]["role"] == "member":
                members[-1]["role"] = role
            i += 1
            continue

        name = w.title()
        if name in ROSTER_MALAYALAM_MAP:
            name = ROSTER_MALAYALAM_MAP[name]

        role = "member"
        # Lookahead: is next word a role? (e.g. 'Leela Secretary')
        if i + 1 < len(words) and words[i + 1].lower() in ROLE_KEYWORDS:
            role = ROLE_KEYWORDS[words[i + 1].lower()]
            i += 2
        else:
            i += 1

        if not any(m["name"].lower() == name.lower() for m in members):
            members.append({"name": name, "role": role})

    return {
        "transcript": clean_tx,
        "group_name": extracted_group,
        "members": members
    }

def parse_voice_onboarding(audio_bytes: bytes) -> dict:
    """
    Transcribes audio and extracts Group Name and Member Names with Roles for onboarding.
    Returns:
    {
        "transcript": raw_tx,
        "group_name": extracted_group,  # str or None
        "members": [{"name": "Shobhana", "role": "member"}, ...]
    }
    """
    keyterms = [
        "Secretary", "President", "Member", "Koottayma", "Sangham", "Samithi", "Group", "Unit", "SHG", "Ward", "Colony", "Association",
        "Leela", "Radha", "Chitra", "Meera", "Suma", "Shobhana", "Anitha", "Latha", "Bindu", "Usha", "Haritha", "Suryakanthi", "Mullappoo",
        "സെക്രട്ടറി", "പ്രസിഡന്റ്", "അംഗം", "കൂട്ടായ്മ", "സംഘം", "സമിതി", "അയൽക്കൂട്ടം", "ഗ്രൂപ്പ്", "കോളനി", "വാർഡ്",
        "ശോഭന", "അനിത", "ലത", "ബിന്ദു", "ഉഷ", "ഹരിത", "സൂര്യകാന്തി"
    ]

    # 1. Call Gnani STT with transliterate pass and keyterms
    res = transcribe_clip(audio_bytes, output_format="transliterate", keyterms=keyterms)
    raw_tx = res.get("transcript", "").strip()

    # Fallback to transcribe pass if transliterate is empty
    if not raw_tx:
        res_pass1 = transcribe_clip(audio_bytes, output_format="transcribe", keyterms=keyterms)
        raw_tx = res_pass1.get("transcript", "").strip()

    if not raw_tx:
        return {
            "transcript": "",
            "group_name": None,
            "members": []
        }

    return extract_onboarding_from_text(raw_tx)

