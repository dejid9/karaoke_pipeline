from __future__ import annotations

from collections import OrderedDict

# User-facing configurable shortcuts.  Values are deliberately human-readable;
# ``shortcut_to_tk`` converts them to Tk event sequences.
DEFAULT_HOTKEYS = OrderedDict([
    ("transport_toggle", "Space"),
    ("play_selection", "Ctrl+Space"),
    ("play_range", "Shift+Space"),
    ("stop", "Esc"),
    ("set_play_start", "I"),
    ("play_from_start", "Ctrl+I"),
    ("set_play_stop", "O"),
    ("play_to_stop", "Ctrl+O"),
    ("clear_play_limits", "Ctrl+Shift+Backspace"),
    ("range_from_selection", "Ctrl+Shift+Space"),
    ("previous_syllable", "Ctrl+Left"),
    ("next_syllable", "Ctrl+Right"),
    ("insert_syllable", "Ctrl+Shift+I"),
    ("split_syllable", "Ctrl+Shift+K"),
    ("merge_syllables", "Ctrl+Shift+M"),
    ("delete_syllable", "Delete"),
    ("reset_measurement", "Ctrl+Shift+R"),
])

# These were the defaults before Alt was removed.  They are only used for a
# one-time, value-based migration: a user-defined Alt shortcut remains valid.
_LEGACY_ALT_DEFAULTS = {
    "previous_syllable": "Alt+Left",
    "next_syllable": "Alt+Right",
    "insert_syllable": "Ctrl+Alt+I",
    "split_syllable": "Ctrl+Alt+S",
    "merge_syllables": "Ctrl+Alt+M",
    "reset_measurement": "Ctrl+Alt+R",
}

HOTKEY_LABELS = OrderedDict([
    ("transport_toggle", "Play / Stop с возвратом"),
    ("play_selection", "Проиграть выделенные слоги"),
    ("play_range", "|▶|: проиграть между метками"),
    ("stop", "Stop"),
    ("set_play_start", "|←: поставить метку старта"),
    ("play_from_start", "|▶: проиграть от метки старта"),
    ("set_play_stop", "→|: поставить метку окончания"),
    ("play_to_stop", "▶|: проиграть от курсора до метки окончания"),
    ("clear_play_limits", "Очистить обе метки"),
    ("range_from_selection", "Поставить обе метки по выделению"),
    ("previous_syllable", "Предыдущий слог"),
    ("next_syllable", "Следующий слог"),
    ("insert_syllable", "Вставить karaoke-слог"),
    ("split_syllable", "Разделить karaoke-слог"),
    ("merge_syllables", "Совместить karaoke-слоги"),
    ("delete_syllable", "Удалить karaoke-слог"),
    ("reset_measurement", "Сбросить точные SPS-границы"),
])

_MOD_ALIASES = {
    "ctrl": "Control", "control": "Control",
    "shift": "Shift",
    "alt": "Alt", "option": "Alt",
}
_KEY_ALIASES = {
    "space": "space",
    "esc": "Escape", "escape": "Escape",
    "del": "Delete", "delete": "Delete",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down",
    "enter": "Return", "return": "Return",
    "tab": "Tab",
    "backspace": "BackSpace",
    "home": "Home", "end": "End",
    "pageup": "Prior", "pagedown": "Next",
}


def normalize_shortcut(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in raw.replace("-", "+").split("+") if part.strip()]
    if not parts:
        return ""
    modifiers: list[str] = []
    key = None
    for part in parts:
        low = part.lower()
        if low in _MOD_ALIASES:
            mod = _MOD_ALIASES[low]
            if mod not in modifiers:
                modifiers.append(mod)
        elif key is None:
            key = _KEY_ALIASES.get(low, part.upper() if len(part) == 1 else part)
        else:
            raise ValueError(f"В сочетании должна быть одна клавиша: {value}")
    if key is None:
        raise ValueError(f"Не указана клавиша: {value}")
    # Stable modifier order keeps persisted settings readable.
    order = {"Control": 0, "Alt": 1, "Shift": 2}
    modifiers.sort(key=lambda item: order.get(item, 99))
    display_key = "Space" if key == "space" else ("Esc" if key == "Escape" else key)
    display_mods = ["Ctrl" if m == "Control" else m for m in modifiers]
    return "+".join(display_mods + [display_key])


def shortcut_to_tk(value: str) -> str:
    normalized = normalize_shortcut(value)
    if not normalized:
        return ""
    parts = normalized.split("+")
    key = parts[-1]
    mods = []
    for part in parts[:-1]:
        mods.append("Control" if part == "Ctrl" else part)
    if len(key) == 1 and key.isalpha():
        # Tk reports a shifted letter as an upper-case keysym.  Binding a
        # lower-case keysym together with Shift therefore never fires on
        # Windows (for example <Control-Shift-i> versus the actual "I").
        key_name = key.upper() if "Shift" in mods else key.lower()
    else:
        key_name = _KEY_ALIASES.get(key.lower(), key)
    return "<" + "-".join(mods + [key_name]) + ">"


def merged_hotkeys(raw: object) -> dict[str, str]:
    result = dict(DEFAULT_HOTKEYS)
    if isinstance(raw, dict):
        migrated = dict(raw)
        # Updates 030-032 stored a second In/Out pair. Update 033 merges that
        # pair with the transport markers. Preserve the familiar I/O marker
        # keys and reuse the former Ctrl+I/Ctrl+O bindings for the new dedicated
        # |▶ and ▶| playback commands, avoiding duplicate shortcuts.
        if "set_range_in" in raw or "set_range_out" in raw:
            migrated["set_play_start"] = raw.get("set_range_in", "I")
            migrated["set_play_stop"] = raw.get("set_range_out", "O")
            migrated["play_from_start"] = raw.get("set_play_start", "Ctrl+I")
            migrated["play_to_stop"] = raw.get("set_play_stop", "Ctrl+O")
        for action in DEFAULT_HOTKEYS:
            if action not in migrated:
                continue
            try:
                value = normalize_shortcut(str(migrated[action] or ""))
            except ValueError:
                continue
            result[action] = value
        for action, legacy_value in _LEGACY_ALT_DEFAULTS.items():
            try:
                saved_value = normalize_shortcut(str(migrated.get(action, "") or ""))
            except ValueError:
                continue
            if saved_value == normalize_shortcut(legacy_value):
                result[action] = DEFAULT_HOTKEYS[action]
    # Corrupt/old preference files could contain duplicate or newly reserved
    # bindings.  A complete valid default set is safer than silently leaving
    # one of two actions inactive because Tk replaces the earlier binding.
    try:
        return validate_hotkeys(result)
    except ValueError:
        return dict(DEFAULT_HOTKEYS)


RESERVED_SHORTCUTS = {
    shortcut_to_tk("Ctrl+S").lower(): "Сохранить ASS",
    shortcut_to_tk("Ctrl+Shift+S").lower(): "Сохранить ASS как",
    shortcut_to_tk("Ctrl+Z").lower(): "Отменить",
    shortcut_to_tk("Ctrl+Y").lower(): "Повторить",
    shortcut_to_tk("Ctrl+Shift+Z").lower(): "Повторить",
    shortcut_to_tk("F2").lower(): "Редактор текста слога",
    shortcut_to_tk("Ctrl+,").lower(): "Настройки",
}


def validate_hotkeys(values: dict[str, str]) -> dict[str, str]:
    result = dict(DEFAULT_HOTKEYS)
    used: dict[str, str] = {}
    for action in DEFAULT_HOTKEYS:
        value = normalize_shortcut(values.get(action, ""))
        if value:
            canonical = shortcut_to_tk(value).lower()
            reserved = RESERVED_SHORTCUTS.get(canonical)
            if reserved is not None:
                raise ValueError(f"Сочетание {value!r} уже зарезервировано: {reserved}.")
            previous = used.get(canonical)
            if previous is not None:
                raise ValueError(
                    f"Одинаковое сочетание {value!r} назначено действиям "
                    f"«{HOTKEY_LABELS[previous]}» и «{HOTKEY_LABELS[action]}»."
                )
            used[canonical] = action
        result[action] = value
    return result
