package com.karaoke.mobile.model

import java.util.UUID

/**
 * Интервал времени в Praat TextGrid.
 */
data class TextGridInterval(
    val start: Double,
    val end: Double,
    val text: String
) {
    val duration: Double get() = maxOf(0.0, end - start)
}

/**
 * Дорожка (слой) интервалов TextGrid.
 */
data class TextGridTier(
    val name: String,
    val intervals: List<TextGridInterval>
)

/**
 * Распарсенный TextGrid документ.
 */
data class ParsedTextGrid(
    val xmin: Double,
    val xmax: Double,
    val tiers: List<TextGridTier>
) {
    fun tier(vararg names: String): TextGridTier? {
        val wanted = names.map { it.lowercase() }.toSet()
        return tiers.find { it.name.lowercase() in wanted }
    }

    val tierNames: List<String> get() = tiers.map { it.name }
}

/**
 * Настройки конвертации TextGrid в ASS.
 */
data class TextGridConversionSettings(
    val wordTier: String = "words",
    val phoneTier: String = "phones",
    val karaokeTag: KaraokeTagType = KaraokeTagType.KF,
    val maxWordsPerLine: Int = 8,
    val maxGapSeconds: Double = 0.65,
    val maxLineSeconds: Double = 8.0,
    val playResX: Int = 1920,
    val playResY: Int = 1080,
    val styleName: String = "Default"
)

object TextGridConverter {

    private val SILENCE_LABELS = setOf(
        "", "<sil>", "sil", "sp", "spn", "{sil}", "{sp}", "<eps>", "null", "none"
    )

    private val VOWELS_MAP = mapOf(
        "ru" to "аеёиоуыэюяАЕЁИОУЫЭЮЯ",
        "en" to "aeiouyAEIOUY",
        "de" to "aeiouyäöüAEIOUYÄÖÜ",
        "es" to "aeiouyáéíóúüAEIOUYÁÉÍÓÚÜ"
    )

    /**
     * Парсинг Praat TextGrid (поддерживает длинный и короткий форматы).
     */
    fun parseTextGrid(content: String): ParsedTextGrid {
        val trimmed = content.trim()
        return if (trimmed.startsWith("ooTextFile short") || content.take(100).contains("ooTextFile short")) {
            parseShortTextGrid(trimmed)
        } else {
            parseLongTextGrid(trimmed)
        }
    }

    private fun unquotePraat(s: String): String {
        var str = s.trim()
        if (str.startsWith("\"") && str.endsWith("\"") && str.length >= 2) {
            str = str.substring(1, str.length - 1)
        }
        return str.replace("\"\"", "\"")
    }

    private fun parseLongTextGrid(text: String): ParsedTextGrid {
        val lines = text.lines()
        var globalXmin = 0.0
        var globalXmax = 0.0

        for (line in lines) {
            val s = line.trim()
            if (s.startsWith("item []")) break
            if (s.startsWith("xmin") && "=" in s) {
                globalXmin = s.substringAfter("=").trim().toDoubleOrNull() ?: 0.0
            } else if (s.startsWith("xmax") && "=" in s) {
                globalXmax = s.substringAfter("=").trim().toDoubleOrNull() ?: 0.0
            }
        }

        val tiers = mutableListOf<TextGridTier>()
        var i = 0
        while (i < lines.size) {
            val line = lines[i].trim()
            if (!line.matches(Regex("""item \[\d+\]:"""))) {
                i++
                continue
            }
            i++
            var tierName = ""
            var tierClass = ""
            val intervals = mutableListOf<TextGridInterval>()

            while (i < lines.size) {
                val s = lines[i].trim()
                if (s.matches(Regex("""item \[\d+\]:"""))) break

                if (s.startsWith("class") && "=" in s) {
                    tierClass = unquotePraat(s.substringAfter("="))
                } else if (s.startsWith("name") && "=" in s) {
                    tierName = unquotePraat(s.substringAfter("="))
                } else if (s.matches(Regex("""intervals \[\d+\]:"""))) {
                    var xmin: Double? = null
                    var xmax: Double? = null
                    var label = ""
                    i++
                    while (i < lines.size) {
                        val part = lines[i].trim()
                        if (part.matches(Regex("""intervals \[\d+\]:""")) || part.matches(Regex("""item \[\d+\]:"""))) {
                            i--
                            break
                        }
                        if (part.startsWith("xmin") && "=" in part) {
                            xmin = part.substringAfter("=").trim().toDoubleOrNull()
                        } else if (part.startsWith("xmax") && "=" in part) {
                            xmax = part.substringAfter("=").trim().toDoubleOrNull()
                        } else if (part.startsWith("text") && "=" in part) {
                            label = unquotePraat(part.substringAfter("="))
                        }
                        i++
                    }
                    if (xmin != null && xmax != null) {
                        intervals.add(TextGridInterval(xmin, xmax, label))
                    }
                }
                i++
            }
            if (tierClass.isEmpty() || tierClass == "IntervalTier") {
                tiers.add(TextGridTier(tierName, intervals))
            }
        }
        return ParsedTextGrid(globalXmin, globalXmax, tiers)
    }

    private fun parseShortTextGrid(text: String): ParsedTextGrid {
        // Токенизация с учетом кавычек
        val tokens = mutableListOf<String>()
        val sb = java.lang.StringBuilder()
        var inQuotes = false
        var idx = 0
        while (idx < text.length) {
            val ch = text[idx]
            if (ch == '"') {
                inQuotes = !inQuotes
                sb.append(ch)
            } else if (ch.isWhitespace() && !inQuotes) {
                if (sb.isNotEmpty()) {
                    tokens.add(sb.toString())
                    sb.clear()
                }
            } else {
                sb.append(ch)
            }
            idx++
        }
        if (sb.isNotEmpty()) tokens.add(sb.toString())

        var pos = 0
        // Пропускаем заголовок
        while (pos < tokens.size && tokens[pos].toDoubleOrNull() == null) {
            pos++
        }
        val xmin = tokens.getOrNull(pos)?.toDoubleOrNull() ?: 0.0; pos++
        val xmax = tokens.getOrNull(pos)?.toDoubleOrNull() ?: 0.0; pos++
        if (pos < tokens.size && tokens[pos].contains("exists")) pos++
        val tierCount = tokens.getOrNull(pos)?.toIntOrNull() ?: 0; pos++

        val tiers = mutableListOf<TextGridTier>()
        for (t in 0 until tierCount) {
            if (pos >= tokens.size) break
            val tierClass = unquotePraat(tokens[pos++])
            val name = if (pos < tokens.size) unquotePraat(tokens[pos++]) else ""
            pos += 2 // xmin, xmax
            val count = if (pos < tokens.size) tokens[pos++].toIntOrNull() ?: 0 else 0

            val intervals = mutableListOf<TextGridInterval>()
            if (tierClass == "IntervalTier") {
                for (j in 0 until count) {
                    if (pos + 2 >= tokens.size) break
                    val start = tokens[pos++].toDoubleOrNull() ?: 0.0
                    val end = tokens[pos++].toDoubleOrNull() ?: 0.0
                    val label = unquotePraat(tokens[pos++])
                    intervals.add(TextGridInterval(start, end, label))
                }
                tiers.add(TextGridTier(name, intervals))
            } else {
                // TextTier (точки)
                pos += count * 2
            }
        }
        return ParsedTextGrid(xmin, xmax, tiers)
    }

    /**
     * Конвертация TextGrid в ASS документ с разбивкой на строки и караоке-тегами.
     */
    fun convertToAss(
        grid: ParsedTextGrid,
        settings: TextGridConversionSettings = TextGridConversionSettings(),
        language: String = "ru"
    ): AssDocument {
        val wordTier = grid.tier(settings.wordTier, "words", "word")
            ?: grid.tiers.firstOrNull()
            ?: return AssDocument()

        val phoneTier = grid.tier(settings.phoneTier, "phones", "phone")

        val validWords = wordTier.intervals.filter {
            it.text.trim().lowercase() !in SILENCE_LABELS && it.end > it.start
        }

        if (validWords.isEmpty()) {
            return AssDocument()
        }

        // Группировка слов в строки диалога
        val lines = groupWordsIntoLines(validWords, settings)
        val events = mutableListOf<AssEvent>()

        for (group in lines) {
            val lineStart = group.first().start
            val lineEnd = group.last().end

            // Собираем караоке слоги для строки
            val lineSyllables = mutableListOf<KaraokeSyllable>()

            for ((wIdx, word) in group.withIndex()) {
                val prefixSpace = wIdx > 0
                val wordPhones = phonesForWord(word, phoneTier)

                val wordSyllables = splitWordIntoSyllables(word.text.trim(), language)
                val boundaries = computeClusterBoundaries(word, wordSyllables.size, wordPhones)

                for (sIdx in wordSyllables.indices) {
                    val sylStart = boundaries[sIdx]
                    val sylEnd = boundaries[sIdx + 1]
                    val sylText = (if (sIdx == 0 && prefixSpace) " " else "") + wordSyllables[sIdx]

                    lineSyllables.add(
                        KaraokeSyllable(
                            id = UUID.randomUUID().toString(),
                            text = sylText,
                            start = sylStart,
                            end = sylEnd,
                            tagType = settings.karaokeTag,
                            styleName = settings.styleName
                        )
                    )
                }
            }

            // Формируем текст диалога с караоке-тегами
            val dialogueText = buildString {
                for (syl in lineSyllables) {
                    val cs = Math.round(syl.duration * 100.0).toInt().coerceAtLeast(1)
                    val tagStr = when (settings.karaokeTag) {
                        KaraokeTagType.KF -> "{\\kf$cs}"
                        KaraokeTagType.KO -> "{\\ko$cs}"
                        KaraokeTagType.K_CAPITAL -> "{\\K$cs}"
                        else -> "{\\k$cs}"
                    }
                    append(tagStr)
                    append(syl.text)
                }
            }

            events.add(
                AssEvent(
                    id = UUID.randomUUID().toString(),
                    start = lineStart,
                    end = lineEnd,
                    styleName = settings.styleName,
                    text = dialogueText,
                    syllables = lineSyllables
                )
            )
        }

        return AssDocument(
            title = "TextGrid Aligned Karaoke",
            playResX = settings.playResX,
            playResY = settings.playResY,
            events = events
        )
    }

    private fun phonesForWord(word: TextGridInterval, phoneTier: TextGridTier?): List<TextGridInterval> {
        if (phoneTier == null) return emptyList()
        return phoneTier.intervals.filter {
            it.text.trim().lowercase() !in SILENCE_LABELS &&
                    minOf(word.end, it.end) - maxOf(word.start, it.start) > 1e-6
        }
    }

    private fun computeClusterBoundaries(
        word: TextGridInterval,
        clusterCount: Int,
        phones: List<TextGridInterval>
    ): List<Double> {
        if (clusterCount <= 1) return listOf(word.start, word.end)
        val duration = maxOf(0.0, word.end - word.start)
        if (duration <= 0.0) return List(clusterCount + 1) { word.start }

        val candidates = phones.map { minOf(word.end, maxOf(word.start, it.end)) }
            .filter { it > word.start && it < word.end }
            .distinct()
            .sorted()

        if (candidates.size >= clusterCount - 1) {
            val selected = mutableListOf<Double>()
            var loIndex = 0
            for (k in 1 until clusterCount) {
                val remaining = clusterCount - k - 1
                val maxIndex = candidates.size - remaining - 1
                val target = word.start + duration * (k.toDouble() / clusterCount.toDouble())
                var bestIndex = loIndex
                var bestDist = Double.MAX_VALUE
                for (idx in loIndex..maxIndex) {
                    val dist = kotlin.math.abs(candidates[idx] - target)
                    if (dist < bestDist) {
                        bestDist = dist
                        bestIndex = idx
                    }
                }
                selected.add(candidates[bestIndex])
                loIndex = bestIndex + 1
            }
            return listOf(word.start) + selected + listOf(word.end)
        }

        // Пропорциональное разделение если фонем меньше
        return (0..clusterCount).map { k ->
            word.start + duration * (k.toDouble() / clusterCount.toDouble())
        }
    }

    private fun groupWordsIntoLines(
        words: List<TextGridInterval>,
        settings: TextGridConversionSettings
    ): List<List<TextGridInterval>> {
        val groups = mutableListOf<List<TextGridInterval>>()
        var current = mutableListOf<TextGridInterval>()

        for (word in words) {
            if (current.isEmpty()) {
                current.add(word)
                continue
            }
            val gap = maxOf(0.0, word.start - current.last().end)
            val lineDuration = word.end - current.first().start

            if (current.size >= settings.maxWordsPerLine ||
                gap > settings.maxGapSeconds ||
                lineDuration > settings.maxLineSeconds
            ) {
                groups.add(current)
                current = mutableListOf(word)
            } else {
                current.add(word)
            }
        }
        if (current.isNotEmpty()) {
            groups.add(current)
        }
        return groups
    }

    /**
     * Офлайн разбиение отдельного слова на слоги по гласным ядрам.
     */
    fun splitWordIntoSyllables(word: String, lang: String = "ru"): List<String> {
        if (word.length <= 2) return listOf(word)
        val vowels = VOWELS_MAP[lang.lowercase()] ?: VOWELS_MAP["ru"]!!
        val lowered = word.lowercase()

        val nuclei = mutableListOf<Pair<Int, Int>>()
        var i = 0
        while (i < lowered.length) {
            if (lowered[i] !in vowels) {
                i++
                continue
            }
            val start = i
            i++
            while (i < lowered.length && lowered[i] in vowels) {
                i++
            }
            nuclei.add(Pair(start, i))
        }

        if (nuclei.size <= 1) return listOf(word)

        val cutPositions = mutableListOf<Int>()
        for (pairIdx in 0 until nuclei.size - 1) {
            val prevEnd = nuclei[pairIdx].second
            val nextStart = nuclei[pairIdx + 1].first
            val consonants = maxOf(0, nextStart - prevEnd)
            val boundary = if (consonants >= 2) nextStart - 1 else prevEnd
            val bounded = maxOf(prevEnd, minOf(nextStart, boundary))
            if (bounded in 1 until word.length) {
                cutPositions.add(bounded)
            }
        }

        val cuts = listOf(0) + cutPositions.distinct().sorted() + listOf(word.length)
        val result = mutableListOf<String>()
        for (k in 0 until cuts.size - 1) {
            val part = word.substring(cuts[k], cuts[k + 1])
            if (part.isNotEmpty()) result.add(part)
        }
        return if (result.isEmpty()) listOf(word) else result
    }

    /**
     * Генерация черновика караоке ASS из простого текста песни (построчно),
     * с офлайн-разбивкой на слоги и равномерной расстановкой времени.
     */
    fun generateDraftAssFromLyrics(
        lyricsText: String,
        lang: String = "ru"
    ): AssDocument {
        val rawLines = lyricsText.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (rawLines.isEmpty()) return AssDocument()

        var currentTime = 1.0 // старт через 1 секунду от начала
        val events = mutableListOf<AssEvent>()

        for (line in rawLines) {
            val words = line.split(Regex("""\s+""")).filter { it.isNotEmpty() }
            val lineSyllables = mutableListOf<KaraokeSyllable>()

            // Считаем все слоги строки
            val wordSyllablePairs = words.map { word ->
                Pair(word, splitWordIntoSyllables(word, lang))
            }
            val totalSyllableCount = wordSyllablePairs.sumOf { it.second.size }.coerceAtLeast(1)
            val lineDur = maxOf(2.0, totalSyllableCount * 0.35)
            val sylDuration = (lineDur / totalSyllableCount).coerceAtLeast(0.1)

            val lineStart = currentTime
            var sylCurrentTime = lineStart

            for ((wIdx, pair) in wordSyllablePairs.withIndex()) {
                val (_, syls) = pair
                for ((sIdx, syl) in syls.withIndex()) {
                    val prefixSpace = wIdx > 0 && sIdx == 0
                    val text = (if (prefixSpace) " " else "") + syl
                    val sylEnd = sylCurrentTime + sylDuration

                    lineSyllables.add(
                        KaraokeSyllable(
                            id = UUID.randomUUID().toString(),
                            text = text,
                            start = sylCurrentTime,
                            end = sylEnd,
                            tagType = KaraokeTagType.KF,
                            styleName = "Default"
                        )
                    )
                    sylCurrentTime = sylEnd
                }
            }

            val lineEnd = sylCurrentTime
            val dialogueText = buildString {
                for (syl in lineSyllables) {
                    val cs = Math.round(syl.duration * 100.0).toInt().coerceAtLeast(1)
                    append("{\\kf$cs}${syl.text}")
                }
            }

            events.add(
                AssEvent(
                    id = UUID.randomUUID().toString(),
                    start = lineStart,
                    end = lineEnd,
                    styleName = "Default",
                    text = dialogueText,
                    syllables = lineSyllables
                )
            )

            currentTime = lineEnd + 0.5 // пауза 0.5с между строками
        }

        return AssDocument(
            title = "Prepared Karaoke Lyrics",
            events = events
        )
    }
}
