from __future__ import annotations

import os
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple


# Pre-computed high-accuracy phonetic transcriptions for rap slang, proper nouns,
# and loan words commonly encountered in multilingual rap tracks, mapped to the
# unified MFA Russian IPA phoneset (russian_mfa.zip).
CUSTOM_RAP_PRONUNCIATIONS: Dict[str, str] = {
    "аку": "ɐ k u",
    "бедрок": "bʲ e d̪ r o k",
    "вб": "v e b e",
    "врединой": "v rʲ e dʲ ɪ n̪ ɐ j",
    "выморозили": "v ɨ m ɐ r ɐ zʲ ɪ ʎ ɪ",
    "ганнибалу": "ɡ ɐ ɲ ɪ b a ɫ ʊ",
    "диффузорах": "dʲ ɪ f ʊ z̪ o r ɐ x",
    "драгун": "d̪ r ɐ ɡ u n̪",
    "коледино": "k ɐ ʎ e dʲ ɪ n̪ ɐ",
    "лагом": "ɫ a ɡ ɐ m",
    "мб": "m e b e",
    "митболы": "mʲ ɪ t̪ b o ɫ ɨ",
    "намотаться": "n̪ ɐ m ɐ t̪ a t̪s̪ː ɐ",
    "операционно": "ɐ pʲ ɪ r ɐ t̪s̪ ɪ o n̪ː ɐ",
    "перерубает": "pʲ ɪ rʲ ɪ r ʊ b a j ɪ t̪",
    "подраил": "p ɐ d̪ r a j ɪ ɫ",
    "роском": "r ɐ s̪ k o m",
    "ситкома": "sʲ ɪ t̪ k o m ɐ",
    "фарнсворт": "f a r n̪ s̪ v ɐ r t̪",
    "цефалоконцом": "tsʲ e f ɐ ɫ ɐ k ɐ n̪ t̪s̪ o m",
    "цианоакрилате": "tsʲ ɪ ɐ n̪ ɐ ɐ k rʲ ɪ ɫ a tʲ e",
    "честер": "tɕ e s̪ t̪ e r",
    "kuso": "k u s̪ o",
    "dolce": "d̪ o ʎ tɕ e",
    "vita": "vʲ i t̪ ɐ",
    "dormammu": "d̪ o r m a m u",
    "effect": "ɪ f ɛ k t̪",
}

# English IPA phones to Russian MFA IPA phoneset translation map
EN_TO_RU_PHONE_MAP: Dict[str, str] = {
    "d": "d̪", "t": "t̪", "n": "n̪", "s": "s̪", "z": "z̪", "l": "ɫ", "w": "v",
    "ɹ": "r", "dʒ": "dʐː", "tʃ": "tɕ", "ʃ": "ʂ", "ʒ": "ʐ", "ŋ": "n̪",
    "θ": "s̪", "ð": "z̪", "h": "x", "ɑ": "a", "ɑː": "a", "ɒ": "a", "ɒː": "a",
    "ɔ": "o", "ow": "o ʊ", "ej": "e j", "aj": "a j", "aw": "a ʊ", "ɔj": "o j",
    "iː": "i", "uː": "u", "ɜː": "ə r", "ɚ": "ə r", "ɝ": "ə r", "ʌ": "ɐ",
    "əw": "o ʊ", "m̩": "m", "n̩": "n̪", "ɫ̩": "ɫ", "ʋ": "v", "ʈ": "t̪", "ɖ": "d̪",
    "ɾ": "r", "ʔ": "", "ç": "x", "ɱ": "m",
}


def clean_multilingual_transcript(raw_text: str) -> str:
    """Prepare clean whitespace-separated transcript text for MFA corpus .lab.

    Strips inline language tags [ru]...[/ru], [en]...[/en], {ru:...}, normalizes quotes,
    dashes, and punctuation, splits hyphenated compound words, and standardizes clitics.
    """
    text = unicodedata.normalize("NFKC", raw_text)
    # Strip language tags: [ru], [/ru], [en], [/en], [ja], [/ja], etc.
    text = re.sub(r"\[/?(?:ru|en|ja|de|es|fr|it|pl|pt|tr)\]", " ", text, flags=re.IGNORECASE)
    # Strip compact braces syntax: {ru: ...} -> ...
    text = re.sub(r"\{[a-z]{2}:([^}]*)\}", r" \1 ", text, flags=re.IGNORECASE)

    # Normalize typographical quotes and dashes
    text = text.replace("“", " ").replace("”", " ").replace('"', " ").replace("«", " ").replace("»", " ")
    text = text.replace("—", " ").replace("–", " ")
    text = text.replace("?", " ").replace("!", " ").replace(".", " ").replace(",", " ")
    text = text.replace(":", " ").replace(";", " ").replace("…", " ")
    text = text.replace("’", "'")

    # Clitics / contractions
    text = text.replace("effect'a", "effect a").replace("effect'а", "effect a")
    text = text.replace("I've", "i've").replace("i've", "i've")

    # Separate hyphenated words (e.g. горе-карлик-драгун -> горе карлик драгун)
    text = text.replace("-", " ")

    # Collapse whitespace
    tokens = [t.strip() for t in text.split() if t.strip()]
    return " ".join(tokens)


def ru_word_to_mfa_ipa(word: str) -> str:
    """Algorithmic Russian G2P fallback synthesizer producing valid Russian MFA IPA phones."""
    w = word.lower().strip()
    if not w:
        return ""
    vowels = {"а": "a", "о": "o", "у": "u", "ы": "ɨ", "э": "e", "я": "a", "ё": "o", "ю": "u", "е": "e", "и": "i"}
    consonants = {
        "б": ("b", "bʲ"), "в": ("v", "vʲ"), "г": ("ɡ", "ɡ"), "д": ("d̪", "dʲ"),
        "ж": ("ʐ", "ʐ"), "з": ("z̪", "zʲ"), "к": ("k", "k"), "л": ("ɫ", "ʎ"),
        "м": ("m", "mʲ"), "н": ("n̪", "ɲ"), "п": ("p", "pʲ"), "р": ("r", "rʲ"),
        "с": ("s̪", "sʲ"), "т": ("t̪", "tʲ"), "ф": ("f", "fʲ"), "х": ("x", "x"),
        "ц": ("t̪s̪", "t̪s̪"), "ч": ("tɕ", "tɕ"), "ш": ("ʂ", "ʂ"), "щ": ("ɕː", "ɕː"),
    }
    softening = {"я", "ё", "ю", "е", "и", "ь"}
    phones = []
    i = 0
    while i < len(w):
        ch = w[i]
        next_ch = w[i + 1] if i + 1 < len(w) else ""
        if ch in consonants:
            is_soft = next_ch in softening
            phones.append(consonants[ch][1] if is_soft else consonants[ch][0])
        elif ch in vowels:
            is_start_or_after_vowel = (i == 0 or w[i - 1] in vowels or w[i - 1] in {"ъ", "ь"})
            if ch in {"я", "ё", "ю", "е"} and is_start_or_after_vowel:
                phones.append("j")
            phones.append(vowels[ch])
        elif ch == "й":
            phones.append("j")
        i += 1
    return " ".join(phones)


def convert_en_phones_to_ru_mfa(phones_str: str) -> str:
    """Convert English IPA phone sequence to Russian MFA acoustic phones."""
    phones = phones_str.split()
    conv = []
    for ph in phones:
        mapped = EN_TO_RU_PHONE_MAP.get(ph, ph)
        if mapped:
            conv.extend(mapped.split())
    return " ".join(conv)


def load_mfa_dictionary_entries(dict_path: str | Path) -> Dict[str, list[str]]:
    """Load MFA dictionary into a map of word -> list of pronunciation phone strings."""
    path = Path(dict_path)
    if not path.is_file():
        return {}
    entries: Dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split("\t")
            if not parts or not parts[0]:
                continue
            word = parts[0].lower().strip()
            if len(parts) >= 2:
                phones = parts[-1].strip()
                entries.setdefault(word, []).append(phones)
    return entries


def load_acoustic_model_phones(acoustic_zip_path: str | Path) -> Set[str]:
    """Read the set of valid phone symbols from an MFA acoustic model archive."""
    path = Path(acoustic_zip_path)
    if not path.is_file():
        return set()
    try:
        with zipfile.ZipFile(path, "r") as z:
            for name in z.namelist():
                if name.endswith("phones.txt"):
                    lines = z.read(name).decode("utf-8", errors="replace").splitlines()
                    return {line.split("\t")[0] for line in lines if line.strip()}
    except Exception:
        pass
    return set()


def build_composite_dictionary(
    words: Iterable[str],
    output_dict_path: str | Path,
    *,
    acoustic_model_path: Optional[str | Path] = None,
    primary_dict_path: Optional[str | Path] = None,
    secondary_dict_path: Optional[str | Path] = None,
    custom_pronunciations_path: Optional[str | Path] = None,
) -> Path:
    """Generate a unified composite dictionary for the specified words.

    Ensures that every word in the lyrics transcript has at least one valid
    pronunciation in the acoustic model's phone inventory, eliminating OOVs.
    """
    out_path = Path(output_dict_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    valid_phones = load_acoustic_model_phones(acoustic_model_path) if acoustic_model_path else set()

    primary_dict = load_mfa_dictionary_entries(primary_dict_path) if primary_dict_path else {}
    secondary_dict = load_mfa_dictionary_entries(secondary_dict_path) if secondary_dict_path else {}
    project_custom = load_mfa_dictionary_entries(custom_pronunciations_path) if custom_pronunciations_path else {}

    unique_words = sorted({w.lower().strip() for w in words if w.strip()})

    with open(out_path, "w", encoding="utf-8") as out:
        for w in unique_words:
            prons: list[str] = []
            if w in project_custom:
                prons = project_custom[w]
            elif w in CUSTOM_RAP_PRONUNCIATIONS:
                prons = [CUSTOM_RAP_PRONUNCIATIONS[w]]
            elif w in primary_dict:
                prons = primary_dict[w]
            elif w in secondary_dict:
                prons = [convert_en_phones_to_ru_mfa(p) for p in secondary_dict[w]]
            else:
                # Heuristic fallback: if Cyrillic, synthesize Russian IPA; else spn
                is_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in w)
                if is_cyrillic:
                    synth = ru_word_to_mfa_ipa(w)
                    if synth:
                        prons = [synth]
                if not prons:
                    prons = ["spn"]

            # Filter or sanitize against valid_phones if known
            valid_prons = []
            for pron in prons:
                if not valid_phones:
                    valid_prons.append(pron)
                else:
                    phones = pron.split()
                    if all(ph in valid_phones for ph in phones):
                        valid_prons.append(pron)
                    else:
                        # Attempt to filter out invalid phones or replace
                        cleaned_phones = [ph for ph in phones if ph in valid_phones]
                        if cleaned_phones:
                            valid_prons.append(" ".join(cleaned_phones))

            if not valid_prons:
                valid_prons = ["spn"] if "spn" in valid_phones else []

            for vp in valid_prons:
                out.write(f"{w}\t{vp}\n")

    return out_path
