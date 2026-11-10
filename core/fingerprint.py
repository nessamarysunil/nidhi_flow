WORD_LIST_EN = [
    "kuri", "thrift", "panam", "varavu", "selavu",
    "leela", "radha", "chitra", "meera", "suma",
    "sabha", "oppu", "kootam", "nidhi", "sangham",
    "kaikaryam", "kanakku", "shg", "pangu", "dhana",
    "labham", "muttathu", "kudumbam", "sahayam", "vithu",
    "padi", "chirak", "ayalkoottam", "nanma", "swantham",
    "sambadhyam", "theerppu"
]

WORD_LIST_ML = [
    "കുറി", "സമ്പാദ്യം", "പണം", "വരവ്", "ചെലവ്",
    "ലീല", "രാധ", "ചിത്ര", "മീര", "സുമ",
    "സഭ", "ഒപ്പ്", "കൂട്ടം", "നിധി", "സംഘം",
    "കൈകാര്യം", "കണക്ക്", "അയൽക്കൂട്ടം", "പങ്ക്", "ധനം",
    "ലാഭം", "മുറ്റത്ത്", "കുടുംബം", "സഹായം", "വിത്ത്",
    "പടി", "ചിറക്", "കൂട്ടായ്മ", "നന്മ", "സ്വന്തം",
    "ശ്രമം", "തീർപ്പ്"
]

# Aliases for backwards compatibility
WORD_LIST = WORD_LIST_EN
WORDLIST = WORD_LIST


def get_fingerprint_indices(hex_hash: str) -> list[int]:
    """Extract 6 indices from the first 15 hex characters."""
    if not hex_hash or set(hex_hash) == {"0"}:
        return []

    hex_prefix = hex_hash[:15]
    num = int(hex_prefix, 16)
    indices = []
    for _ in range(6):
        indices.append(num % len(WORD_LIST_ML))
        num //= len(WORD_LIST_ML)
    return indices


def hash_to_fingerprint(hex_hash: str, separator: str = " • ") -> str:
    """
    Produce a distinct 6-word human-verifiable string in native Malayalam script from the hex hash.
    When the ledger has no entries yet, returns 'Genesis Session — Awaiting Block #1'.
    """
    indices = get_fingerprint_indices(hex_hash)
    if not indices:
        return "Genesis Session — Awaiting Block #1"

    words = [WORD_LIST_ML[idx] for idx in indices]
    return separator.join(words)


def hash_to_fingerprint_en(hex_hash: str, separator: str = " • ") -> str:
    """
    Produce the English transliterated equivalent of the 6-word fingerprint.
    """
    indices = get_fingerprint_indices(hex_hash)
    if not indices:
        return "Genesis Session — Awaiting Block #1"

    words = [WORD_LIST_EN[idx] for idx in indices]
    return separator.join(words)


def hash_to_fingerprint_spoken(hex_hash: str) -> str:
    """
    Produce a natural pause-separated Malayalam string for gTTS / speech synthesis.
    """
    indices = get_fingerprint_indices(hex_hash)
    if not indices:
        return ""

    words = [WORD_LIST_ML[idx] for idx in indices]
    return ", ".join(words)

