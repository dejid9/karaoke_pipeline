package com.karaoke.mobile.model

/**
 * Парсер и сериализатор ASS-файлов.
 * Портирован из karaoke_core/ass.py
 */
object AssParser {

    fun parse(text: String): AssDocument {
        val lines = text.lines()
        var section: String? = null
        var title = ""
        var scriptType = "v4.00+"
        var playResX = 1280
        var playResY = 720
        val styles = mutableListOf<AssStyle>()
        val events = mutableListOf<AssEvent>()
        val extraHeaders = mutableMapOf<String, String>()

        for (rawLine in lines) {
            val line = rawLine.trim()
            if (line.isEmpty() || line.startsWith(";")) continue

            if (line.startsWith("[") && line.endsWith("]")) {
                section = line
                continue
            }

            when (section) {
                "[Script Info]" -> {
                    if (line.contains(":")) {
                        val key = line.substringBefore(":").trim()
                        val value = line.substringAfter(":").trim()
                        when (key.lowercase()) {
                            "title" -> title = value
                            "scripttype" -> scriptType = value
                            "playresx" -> playResX = value.toIntOrNull() ?: 1280
                            "playresy" -> playResY = value.toIntOrNull() ?: 720
                            else -> extraHeaders[key] = value
                        }
                    }
                }
                "[V4+ Styles]", "[V4 Styles]" -> {
                    if (line.startsWith("Style:", ignoreCase = true)) {
                        styles.add(AssStyle.fromAssFormat(line))
                    }
                }
                "[Events]" -> {
                    if (line.startsWith("Dialogue:", ignoreCase = true)) {
                        val event = AssEvent.fromAssLine(line)
                        events.add(event.copy(syllables = parseKaraokeSyllables(event)))
                    } else if (line.startsWith("Comment:", ignoreCase = true)) {
                        // Пропускаем комментарии или можно сохранить
                    }
                }
            }
        }

        if (styles.isEmpty()) {
            styles.add(AssStyle())
        }

        return AssDocument(
            title = title,
            scriptType = scriptType,
            playResX = playResX,
            playResY = playResY,
            styles = styles,
            events = events,
            extraHeaders = extraHeaders
        )
    }

    /**
     * Парсит караоке-слоги из текста события.
     * Поддерживает теги \k, \kf, \ko, \K с последующим текстом.
     */
    fun parseKaraokeSyllables(event: AssEvent): List<KaraokeSyllable> {
        val text = event.text
        val syllables = mutableListOf<KaraokeSyllable>()
        var currentPos = 0.0

        // Регулярное выражение для караоке-тегов
        val regex = Regex("""\{\\(kf|ko|K|k)(\d+)\}""")
        val matches = regex.findAll(text).toList()

        if (matches.isEmpty()) {
            // Нет караоке-тегов — весь текст как один слог
            if (text.isNotBlank()) {
                return listOf(
                    KaraokeSyllable(
                        text = text.removeAssTags().trim(),
                        start = event.start,
                        end = event.end,
                        styleName = event.styleName,
                        actor = event.actor,
                        effect = event.effect,
                        marginL = event.marginL,
                        marginR = event.marginR,
                        marginV = event.marginV
                    )
                )
            }
            return emptyList()
        }

        var lastEnd = 0
        for (match in matches) {
            val rawTag = match.groupValues[1]
            val tagType = when {
                rawTag == "K" -> KaraokeTagType.K_CAPITAL
                rawTag.equals("kf", ignoreCase = true) -> KaraokeTagType.KF
                rawTag.equals("ko", ignoreCase = true) -> KaraokeTagType.KO
                else -> KaraokeTagType.K
            }
            val centis = match.groupValues[2].toIntOrNull() ?: 10
            val duration = centis / 100.0

            // Текст между текущим и следующим тегом
            val textStart = match.range.last + 1
            val nextMatch = matches.getOrNull(matches.indexOf(match) + 1)
            val textEnd = nextMatch?.range?.first ?: text.length
            val syllableText = text.substring(textStart, textEnd).removeAssTags().trim()

            if (syllableText.isNotEmpty() || syllables.isEmpty()) {
                val start = event.start + currentPos
                val end = start + duration
                syllables.add(
                    KaraokeSyllable(
                        text = syllableText.ifEmpty { " " },
                        start = start,
                        end = end,
                        tagType = tagType,
                        styleName = event.styleName,
                        actor = event.actor,
                        effect = event.effect,
                        marginL = event.marginL,
                        marginR = event.marginR,
                        marginV = event.marginV
                    )
                )
                currentPos += duration
            }
        }

        return syllables
    }

    /**
     * Сериализует список слогов обратно в ASS-текст
     */
    fun serializeSyllables(syllables: List<KaraokeSyllable>): String {
        return syllables.joinToString("") { syllable ->
            val centis = Math.round(syllable.duration * 100.0).toInt().coerceAtLeast(1)
            val tag = when (syllable.tagType) {
                KaraokeTagType.K -> "\\k"
                KaraokeTagType.KF -> "\\kf"
                KaraokeTagType.KO -> "\\ko"
                KaraokeTagType.K_CAPITAL -> "\\K"
            }
            "{$tag$centis}${syllable.text}"
        }
    }

    /**
     * Пересобирает событие из слогов
     */
    fun rebuildEventFromSyllables(event: AssEvent): AssEvent {
        if (event.syllables.isEmpty()) return event
        val newText = serializeSyllables(event.syllables)
        val first = event.syllables.first()
        val last = event.syllables.last()
        return event.copy(
            start = first.start,
            end = last.end,
            text = newText
        )
    }

    private fun String.removeAssTags(): String {
        // Удаляем override блоки {\...}
        return this.replace(Regex("""\{[^}]*\}"""), "")
    }

    /**
     * Создаёт пустой ASS документ с заданной длительностью
     */
    fun createBlankDocument(duration: Double): AssDocument {
        val event = AssEvent(
            start = 0.0,
            end = duration,
            text = "{\\k0}"
        )
        return AssDocument(
            events = listOf(event.copy(syllables = listOf(
                KaraokeSyllable(
                    text = "",
                    start = 0.0,
                    end = duration,
                    tagType = KaraokeTagType.K
                )
            )))
        )
    }
}
