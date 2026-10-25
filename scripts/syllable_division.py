import re
import math
import pronouncing
import pyphen

from auto_language import detect_language

# =====================================================
# PATHS
# =====================================================

INPUT_ASS = r"C:\Users\dejid\Desktop\karaoke_pipeline\work\output.ass"
OUTPUT_ASS = r"C:\Users\dejid\Desktop\karaoke_pipeline\work\output_syllables.ass"

# =====================================================
# LOAD ASS
# =====================================================

with open(INPUT_ASS, "r", encoding="utf-8") as f:
    ass_text = f.read()

with open(r"C:\Users\dejid\Desktop\karaoke_pipeline\work\corpus\audio.txt", "r", encoding="utf-8") as f:
    corpus = f.read()

LANG = detect_language(corpus)

print("Detected language:", LANG)

# =====================================================
# PYPHEN MAP
# =====================================================

PYPHEN_LANGS = {
    "russian": "ru_RU",
    "german": "de_DE",
    "polish": "pl_PL",
    "turkish": "tr_TR",
    "hungarian": "hu_HU"
}

pyphen_dic = None

if LANG in PYPHEN_LANGS:

    pyphen_dic = pyphen.Pyphen(
        lang=PYPHEN_LANGS[LANG]
    )

# =====================================================
# TIME
# =====================================================

def parse_time(t):

    h, m, s = t.split(":")

    return (
        int(h) * 3600 +
        int(m) * 60 +
        float(s)
    )

def fmt_time(t):

    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60

    return f"{h}:{m:02}:{s:05.2f}"

# =====================================================
# ENGLISH SYLLABLES
# =====================================================

VOWELS = "aeiouy"

def english_syllables(word):

    phones = pronouncing.phones_for_word(
        word.lower()
    )

    # fallback
    if not phones:
        return fallback_vowel_split(word)

    syll_count = pronouncing.syllable_count(
        phones[0]
    )

    if syll_count <= 1:
        return [word]

    return split_by_vowel_groups(
        word,
        syll_count
    )

# =====================================================
# VOWEL GROUP SPLIT
# =====================================================

def split_by_vowel_groups(word, expected_count):

    groups = []

    current = ""

    vowel_seen = False

    for i, ch in enumerate(word):

        current += ch

        is_vowel = ch.lower() in VOWELS

        if is_vowel:
            vowel_seen = True

        next_is_vowel = False

        if i + 1 < len(word):

            next_is_vowel = (
                word[i + 1].lower() in VOWELS
            )

        boundary = (
            vowel_seen and
            not next_is_vowel
        )

        if boundary:

            groups.append(current)

            current = ""
            vowel_seen = False

    if current:

        if groups:
            groups[-1] += current
        else:
            groups.append(current)

    # rebalance

    while len(groups) > expected_count:

        groups[-2] += groups[-1]
        groups.pop()

    while len(groups) < expected_count:

        longest_i = max(
            range(len(groups)),
            key=lambda i: len(groups[i])
        )

        g = groups[longest_i]

        if len(g) <= 1:
            break

        mid = len(g) // 2

        groups[longest_i] = g[:mid]

        groups.insert(
            longest_i + 1,
            g[mid:]
        )

    return groups

# =====================================================
# GENERIC FALLBACK
# =====================================================

def fallback_vowel_split(word):

    parts = []

    current = ""

    vowel_seen = False

    for i, ch in enumerate(word):

        current += ch

        if ch.lower() in VOWELS:
            vowel_seen = True

        next_is_vowel = False

        if i + 1 < len(word):

            next_is_vowel = (
                word[i + 1].lower() in VOWELS
            )

        if vowel_seen and not next_is_vowel:

            parts.append(current)

            current = ""

            vowel_seen = False

    if current:

        if parts:
            parts[-1] += current
        else:
            parts.append(current)

    return parts if parts else [word]

# =====================================================
# UNIVERSAL SYLLABLE SPLIT
# =====================================================

def split_syllables(word):

    # english

    if LANG == "english":

        return english_syllables(word)

    # pyphen languages

    if pyphen_dic:

        res = pyphen_dic.inserted(word)

        if not res:
            return [word]

        return res.split("-")

    return [word]

# =====================================================
# PARSE DIALOGUES
# =====================================================

dialogues = []

for line in ass_text.splitlines():

    if not line.startswith("Dialogue:"):
        continue

    parts = line.split(",", 9)

    if len(parts) < 10:
        continue

    try:

        start = parse_time(parts[1])
        end = parse_time(parts[2])

        text = parts[9].strip()

    except:
        continue

    dialogues.append([
        start,
        end,
        text
    ])

if not dialogues:

    raise Exception(
        "No valid dialogue lines found"
    )

dialogues.sort(
    key=lambda x: x[0]
)

# =====================================================
# REGEX
# =====================================================

kara_re = re.compile(
    r"\{\\[kKfF](\d+)\}([^\{])"
)

# =====================================================
# LETTER → SYLLABLE KARAOKE
# =====================================================

def syllabify_karaoke(text):

    tokens = kara_re.findall(text)

    if not tokens:
        return text

    # rebuild plain text + timings

    letters = []
    ks = []

    for k, ch in tokens:

        letters.append(ch)
        ks.append(int(k))

    plain = "".join(letters)

    # IMPORTANT:
    # preserve exact spacing structure

    chunks = re.findall(
        r'\S+|\s+',
        plain,
        re.UNICODE
    )

    result = []

    pos = 0

    for chunk in chunks:

        # =================================================
        # SPACES
        # =================================================

        if chunk.isspace():

            total_k = 0

            for _ in chunk:

                if pos < len(ks):

                    total_k += ks[pos]
                    pos += 1

            if total_k > 0:

                result.append(
                    f"{{\\K{total_k}}}{chunk}"
                )

            continue

        # =================================================
        # WORD
        # =================================================

        word = chunk

        syllables = split_syllables(word)

        if not syllables:
            syllables = [word]

        # ---------------------------------------------
        # EXACT TIMING MAPPING
        # ---------------------------------------------

        local_pos = 0

        for syll in syllables:

            syll_len = len(syll)

            syll_k = sum(
                ks[
                    pos + local_pos:
                    pos + local_pos + syll_len
                ]
            )

            if syll_k <= 0:
                syll_k = 1

            # IMPORTANT:
            # use \K instead of \kf
            # because your original timing system
            # was generated with \K accumulation logic

            result.append(
                f"{{\\K{syll_k}}}{syll}"
            )

            local_pos += syll_len

        pos += len(word)

    return "".join(result)

# =====================================================
# FIX INTERNAL DRIFT
# =====================================================

def fix_internal_k_drift(
    text,
    real_duration_sec
):

    ks = list(map(
        int,
        re.findall(
            r"\\[kKfF](\d+)",
            text
        )
    ))

    kara_duration_sec = (
        sum(ks) / 100.0
    )

    if kara_duration_sec == 0:
        return text

    delta_sec = (
        real_duration_sec -
        kara_duration_sec
    )

    delta_k = int(
        round(delta_sec * 100)
    )

    matches = list(re.finditer(
        r"\\[kKfF](\d+)",
        text
    ))

    if not matches:
        return text

    last = matches[-1]

    old_k = int(last.group(1))

    new_k = max(
        1,
        old_k + delta_k
    )

    text = (
        text[:last.start(1)] +
        str(new_k) +
        text[last.end(1):]
    )

    return text

# =====================================================
# CONVERT EACH LINE
# =====================================================

for d in dialogues:

    d[2] = syllabify_karaoke(
        d[2]
    )

# =====================================================
# ACCUMULATIVE MERGE
# =====================================================

acc_start, acc_end, acc_text = dialogues[0]

for i in range(1, len(dialogues)):

    cur_start, cur_end, cur_text = dialogues[i]

    # fix internal drift

    real_dur = acc_end - acc_start

    acc_text = fix_internal_k_drift(
        acc_text,
        real_dur
    )

    # gap correction

    gap = max(
        0,
        cur_start - acc_end
    )

    gap_k = int(
        round(gap * 100)
    )

    matches = list(re.finditer(
        r"\\[kKfF](\d+)",
        acc_text
    ))

    if matches:

        last = matches[-1]

        old_k = int(last.group(1))

        new_k = old_k + gap_k

        acc_text = (
            acc_text[:last.start(1)] +
            str(new_k) +
            acc_text[last.end(1):]
        )

    # merge

    acc_text += " " + cur_text

    acc_end = cur_end

# =====================================================
# FINAL DRIFT FIX
# =====================================================

final_duration = acc_end - acc_start

acc_text = fix_internal_k_drift(
    acc_text,
    final_duration
)

# =====================================================
# FINAL ASS LINE
# =====================================================

final_line = (
    f"Dialogue: 0,"
    f"{fmt_time(acc_start)},"
    f"{fmt_time(acc_end)},"
    f"Default,,0,0,0,,"
    f"{acc_text}"
)

# =====================================================
# WRITE ASS
# =====================================================

with open(
    OUTPUT_ASS,
    "w",
    encoding="utf-8"
) as f:

    f.write(
"""[Script Info]
Title: Syllable Karaoke
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Heading Pro Variable,72,&H00FFFFFF,&H80FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,2,0,2,30,30,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    )

    f.write(final_line + "\n")

print("DONE ->", OUTPUT_ASS)