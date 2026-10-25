from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """Language-specific defaults shared by MFA and syllable conversion."""

    code: str
    name: str
    label: str
    acoustic_model: str
    dictionary_model: str
    pyphen_language: str | None


LANGUAGE_PROFILES: tuple[LanguageProfile, ...] = (
    LanguageProfile("en", "english", "English (en)", "english_mfa", "english_us_mfa", "en_US"),
    LanguageProfile("ru", "russian", "Русский (ru)", "russian_mfa", "russian_mfa", "ru_RU"),
    LanguageProfile("de", "german", "Deutsch (de)", "german_mfa", "german_mfa", "de_DE"),
    LanguageProfile("pl", "polish", "Polski (pl)", "polish_mfa", "polish_mfa", "pl_PL"),
    LanguageProfile("tr", "turkish", "Türkçe (tr)", "turkish_mfa", "turkish_mfa", "tr_TR"),
    LanguageProfile("hu", "hungarian", "Magyar (hu)", "hungarian_cv", "hungarian_cv", "hu_HU"),
    LanguageProfile("pt", "portuguese", "Português (pt)", "portuguese_mfa", "portuguese_mfa", "pt_PT"),
    # The legacy scripts did not syllabify Japanese with Pyphen.  MFA/Sudachi
    # tokens therefore remain the visible timing units for this profile.
    LanguageProfile("ja", "japanese", "日本語 (ja)", "japanese_mfa", "japanese_mfa", None),
    # MFA's current official model catalogue has no Persian acoustic/dictionary
    # pair.  Keep a script-aware profile nevertheless so auto-detection never
    # silently sends Persian text through the English models or syllabifier.
    # Users can still disable auto models and provide a compatible custom pair.
    LanguageProfile("fa", "persian", "فارسی / Persian (fa)", "", "", None),
)

_BY_CODE = {profile.code: profile for profile in LANGUAGE_PROFILES}
_ALIASES = {
    alias.casefold(): profile
    for profile in LANGUAGE_PROFILES
    for alias in (
        profile.code,
        profile.name,
        profile.label,
        profile.pyphen_language or "",
        profile.pyphen_language.split("_", 1)[0] if profile.pyphen_language else "",
    )
    if alias
}

_ASS_OVERRIDE_RE = re.compile(r"\{[^{}]*\}")


def profile_for_language(value: str | LanguageProfile | None) -> LanguageProfile:
    if isinstance(value, LanguageProfile):
        return value
    key = (value or "en").strip().casefold().replace("-", "_")
    if key in _ALIASES:
        return _ALIASES[key]
    short = key.split("_", 1)[0]
    if short in _BY_CODE:
        return _BY_CODE[short]
    # MFA can gain new language models without an application update.  Keep
    # such catalogue languages distinct instead of silently treating them as
    # English.  Their model defaults are supplied by the installed-model
    # catalogue in the GUI; syllabification safely falls back when no Pyphen
    # dictionary is known.
    display = key.replace("_", " ").strip() or "English"
    return LanguageProfile(key or "en", key or "english", display.title(), "", "", None)


def language_labels() -> tuple[str, ...]:
    return tuple(profile.label for profile in LANGUAGE_PROFILES)


def clean_language_text(text: str) -> str:
    text = _ASS_OVERRIDE_RE.sub(" ", text)
    text = text.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    return " ".join(text.split())


def _script_hint(text: str) -> str | None:
    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x9FFF:
            return "ja"
    # Persian-specific letters/forms distinguish it from other languages using
    # the Arabic script without pretending all Arabic-script text is Persian.
    if any(ch in "پچژگکیۀ" for ch in text):
        return "fa"
    if any("CYRILLIC" in unicodedata.name(ch, "") for ch in text if ch.isalpha()):
        return "ru"
    return None


def _latin_hint(text: str) -> str | None:
    folded = text.casefold()
    # Include English in the comparison and require more than one ambiguous
    # stop-word hit.  The earlier fallback could label a long English lyric as
    # Turkish merely because it contained one standalone "bu".
    words = re.findall(r"[^\W\d_]+", folded, re.UNICODE)
    vocabulary = {
        "en": {"the", "and", "you", "that", "this", "with", "for", "not", "have", "your", "what", "when", "even"},
        "pl": {"jest", "nie", "się", "jak", "dla", "ale", "ten", "tak", "mam", "już"},
        "tr": {"bir", "ve", "bu", "için", "değil", "ben", "sen", "gibi", "ile", "çok"},
        "hu": {"hogy", "nem", "egy", "van", "és", "mint", "még", "aki", "csak", "itt"},
        "de": {"der", "die", "das", "und", "nicht", "ich", "ist", "ein", "mit", "auf"},
        "pt": {"que", "não", "uma", "para", "com", "por", "como", "mais", "você", "está"},
    }
    keyword_scores = {
        code: sum(1 for word in words if word in known)
        for code, known in vocabulary.items()
    }
    scores = dict(keyword_scores)
    scores["pl"] += 3 * sum(folded.count(ch) for ch in "ąćęłńóśźż")
    scores["tr"] += 3 * sum(folded.count(ch) for ch in "ğıİşç")
    hungarian_unique = sum(folded.count(ch) for ch in "őű")
    # Acute vowels distinguish Hungarian well only when Hungarian vocabulary
    # (or the unique double-accent vowels) is also present; this avoids mapping
    # unsupported Spanish text to Hungarian merely because it contains á/é/í.
    if keyword_scores["hu"] >= 2 or hungarian_unique:
        scores["hu"] += 3 * hungarian_unique + sum(folded.count(ch) for ch in "áéíóú")
    scores["de"] += 3 * sum(folded.count(ch) for ch in "ßäöü")
    scores["pt"] += 3 * sum(folded.count(ch) for ch in "ãõç")
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else None


def detect_language_profile(text: str) -> LanguageProfile:
    """Detect a language/script profile used by alignment and conversion.

    ``langdetect`` is used when available in the GUI's Conda environment.  The
    Unicode/script fallback keeps the core usable and testable without optional
    packages.  Some detected profiles, such as Persian, intentionally have no
    bundled MFA model defaults but still prevent unsafe English fallback.
    """

    cleaned = clean_language_text(text)
    if not cleaned:
        return _BY_CODE["en"]
    hinted = _script_hint(cleaned)
    if hinted:
        return _BY_CODE[hinted]

    detected: str | None = None
    try:
        from langdetect import DetectorFactory, detect  # type: ignore

        DetectorFactory.seed = 0
        detected = str(detect(cleaned)).casefold()
    except Exception:
        detected = None
    if detected in _BY_CODE:
        return _BY_CODE[detected]

    hinted = _latin_hint(cleaned)
    return _BY_CODE[hinted or "en"]


def detect_language(text: str) -> str:
    """Backward-compatible name returned by ``scripts/auto_language.py``."""

    return detect_language_profile(text).name
