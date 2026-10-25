from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
import unicodedata
from typing import Iterable, Sequence


class TextPreprocessError(RuntimeError):
    pass


def _utf8_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    # On Russian Windows a child Python otherwise writes JSON through cp1251,
    # which cannot represent Japanese Sudachi tokens.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


@dataclass(slots=True, frozen=True)
class TextPreprocessSettings:
    mode: str = "none"  # none | normalize | japanese_sudachi
    unicode_form: str = "NFKC"
    sudachi_split_mode: str = "C"  # A | B | C
    strip_punctuation: bool = False


@dataclass(slots=True, frozen=True)
class TextPreprocessReport:
    text: str
    original_characters: int
    prepared_characters: int
    token_count: int
    mode: str
    warnings: tuple[str, ...] = ()


def normalize_text(text: str, *, unicode_form: str = "NFKC") -> str:
    """Normalize Unicode and whitespace without changing lexical content.

    MFA consumes a single transcript for the one audio file in this workbench,
    so line breaks are treated as whitespace.  The original transcript file is
    never modified; this result is only written to the generated corpus `.lab`.
    """
    form = unicode_form.upper().strip() or "NFKC"
    if form not in {"NFC", "NFD", "NFKC", "NFKD"}:
        raise TextPreprocessError(f"Неизвестная Unicode-нормализация: {unicode_form}")
    value = unicodedata.normalize(form, text.replace("\ufeff", ""))
    value = value.replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value, flags=re.UNICODE).strip()
    return value


def _is_punctuation_token(token: str) -> bool:
    visible = [ch for ch in token if not ch.isspace()]
    return bool(visible) and all(unicodedata.category(ch)[0] in {"P", "S"} for ch in visible)


def strip_punctuation_tokens(text: str) -> str:
    tokens = [token for token in text.split() if not _is_punctuation_token(token)]
    return " ".join(tokens)


def prepare_text_local(text: str, settings: TextPreprocessSettings) -> TextPreprocessReport:
    mode = settings.mode.casefold().strip()
    if mode not in {"none", "normalize"}:
        raise TextPreprocessError("Japanese Sudachi требует выбранного Conda-окружения")
    has_lang_tags = bool(
        re.search(r"\[/?(?:ru|en|ja|de|es|fr|it|pl|pt|tr)\]", text, re.IGNORECASE)
        or re.search(r"\{[a-z]{2}:[^}]*\}", text, re.IGNORECASE)
    )
    if has_lang_tags:
        from .multilang import clean_multilingual_transcript
        prepared = clean_multilingual_transcript(text)
    elif mode == "none":
        prepared = text.strip()
    else:
        prepared = normalize_text(text, unicode_form=settings.unicode_form)

    if settings.strip_punctuation:
        if mode == "none" and not has_lang_tags:
            prepared = normalize_text(prepared, unicode_form=settings.unicode_form)
        prepared = strip_punctuation_tokens(prepared)

    return TextPreprocessReport(
        text=prepared,
        original_characters=len(text),
        prepared_characters=len(prepared),
        token_count=len(prepared.split()),
        mode="multilang_cleaned" if has_lang_tags else mode,
    )


def probe_python_packages(command_prefix: Sequence[str], packages: Iterable[str], *, timeout: float = 30.0) -> dict[str, bool]:
    names = tuple(dict.fromkeys(str(name).strip() for name in packages if str(name).strip()))
    if not names:
        return {}
    script = (
        "import importlib.util,json,sys; "
        "print(json.dumps({n:(importlib.util.find_spec(n) is not None) for n in sys.argv[1:]}))"
    )
    try:
        result = subprocess.run(
            list(command_prefix) + ["python", "-c", script, *names],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_utf8_subprocess_env(),
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise TextPreprocessError(f"Не удалось проверить Python-пакеты в Conda: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise TextPreprocessError("Conda Python package probe завершился ошибкой" + (f": {detail[-1000:]}" if detail else ""))
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return {name: bool(data.get(name, False)) for name in names}
    raise TextPreprocessError("Не удалось прочитать результат проверки Python-пакетов")


def tokenize_japanese_sudachi(
    text: str,
    conda_python_prefix: Sequence[str],
    *,
    split_mode: str = "C",
    unicode_form: str = "NFKC",
    strip_punctuation: bool = False,
    timeout: float = 60.0,
) -> TextPreprocessReport:
    """Tokenize Japanese through SudachiPy inside the selected Conda env.

    `conda_python_prefix` is expected to be a launcher prefix ending before the
    executable, e.g. (`conda`, `run`, `-n`, `mfa`).  The script prints only
    a JSON payload, so the caller can use the same function even when the GUI
    itself runs from a different Python environment.
    """
    mode = split_mode.upper().strip() or "C"
    if mode not in {"A", "B", "C"}:
        raise TextPreprocessError("Sudachi split mode должен быть A, B или C")
    normalized = normalize_text(text, unicode_form=unicode_form)
    script = r'''
import json, sys
from sudachipy import dictionary, tokenizer
text = sys.stdin.read()
mode_name = sys.argv[1]
mode = getattr(tokenizer.Tokenizer.SplitMode, mode_name)
tok = dictionary.Dictionary().create()
items = [m.surface() for m in tok.tokenize(text, mode) if m.surface().strip()]
print(json.dumps(items, ensure_ascii=False))
'''
    try:
        result = subprocess.run(
            list(conda_python_prefix) + ["python", "-c", script, mode],
            input=normalized,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_utf8_subprocess_env(),
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise TextPreprocessError(f"Не удалось запустить SudachiPy: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise TextPreprocessError(
            "SudachiPy недоступен или завершился ошибкой. Установите sudachipy и sudachidict_core в выбранное Conda-окружение"
            + (f": {detail[-1200:]}" if detail else "")
        )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    items = None
    for line in reversed(lines):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, list):
            items = [str(x) for x in candidate if str(x).strip()]
            break
    if items is None:
        raise TextPreprocessError("SudachiPy не вернул список токенов")
    if strip_punctuation:
        items = [token for token in items if not _is_punctuation_token(token)]
    prepared = " ".join(items)
    warnings: list[str] = []
    if not prepared:
        warnings.append("После японской предобработки текст пуст")
    return TextPreprocessReport(
        text=prepared,
        original_characters=len(text),
        prepared_characters=len(prepared),
        token_count=len(items),
        mode="japanese_sudachi",
        warnings=tuple(warnings),
    )
