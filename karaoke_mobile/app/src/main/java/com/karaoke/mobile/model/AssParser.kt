package com.karaoke.mobile.model

object AssParser {
    fun parse(content: String): AssFile {
        val lines = content.lines()
        var section = ""
        val scriptInfo = mutableMapOf<String, String>()
        val styles = mutableListOf<AssStyle>()
        val assLines = mutableListOf<AssLine>()
        var audioFile: String? = null
        var videoFile: String? = null

        for (rawLine in lines) {
            val line = rawLine.trim()
            when {
                line.startsWith("[") && line.endsWith("]") -> section = line
                section == "[Script Info]" && line.contains(":") -> {
                    val (key, value) = line.split(":", limit = 2).map { it.trim() }
                    scriptInfo[key] = value
                    if (key.equals("Audio File", ignoreCase = true)) audioFile = value
                    if (key.equals("Video File", ignoreCase = true)) videoFile = value
                }
                section == "[V4+ Styles]" && line.startsWith("Style:") -> {
                    styles.add(parseStyle(line))
                }
                section == "[Events]" && line.startsWith("Dialogue:") -> {
                    assLines.add(parseDialogue(line))
                }
            }
        }

        return AssFile(
            scriptInfo = scriptInfo,
            styles = styles,
            lines = assLines,
            audioFile = audioFile,
            videoFile = videoFile
        )
    }

    private fun parseStyle(line: String): AssStyle {
        val parts = line.substringAfter("Style:").trim().split(",")
        return AssStyle(
            name = parts.getOrNull(0)?.trim() ?: "Default",
            fontName = parts.getOrNull(1)?.trim() ?: "Arial",
            fontSize = parts.getOrNull(2)?.trim()?.toIntOrNull() ?: 24,
            primaryColor = parseAssColor(parts.getOrNull(3) ?: "&H00FFFFFF"),
            secondaryColor = parseAssColor(parts.getOrNull(4) ?: "&H000000FF"),
            outlineColor = parseAssColor(parts.getOrNull(5) ?: "&H00000000"),
            backColor = parseAssColor(parts.getOrNull(6) ?: "&H00000000"),
            bold = (parts.getOrNull(7)?.trim()?.toIntOrNull() ?: 0) == -1,
            italic = (parts.getOrNull(8)?.trim()?.toIntOrNull() ?: 0) == -1,
            underline = (parts.getOrNull(10)?.trim()?.toIntOrNull() ?: 0) == -1,
            strikeOut = (parts.getOrNull(11)?.trim()?.toIntOrNull() ?: 0) == -1,
            scaleX = parts.getOrNull(12)?.trim()?.toDoubleOrNull() ?: 100.0,
            scaleY = parts.getOrNull(13)?.trim()?.toDoubleOrNull() ?: 100.0,
            spacing = parts.getOrNull(14)?.trim()?.toIntOrNull() ?: 0,
            angle = parts.getOrNull(15)?.trim()?.toDoubleOrNull() ?: 0.0,
            borderStyle = parts.getOrNull(16)?.trim()?.toIntOrNull() ?: 1,
            outline = parts.getOrNull(17)?.trim()?.toDoubleOrNull() ?: 2.0,
            shadow = parts.getOrNull(18)?.trim()?.toDoubleOrNull() ?: 0.0,
            alignment = parts.getOrNull(19)?.trim()?.toIntOrNull() ?: 2,
            marginL = parts.getOrNull(20)?.trim()?.toIntOrNull() ?: 10,
            marginR = parts.getOrNull(21)?.trim()?.toIntOrNull() ?: 10,
            marginV = parts.getOrNull(22)?.trim()?.toIntOrNull() ?: 10,
            encoding = parts.getOrNull(23)?.trim()?.toIntOrNull() ?: 1
        )
    }

    private fun parseDialogue(line: String): AssLine {
        val afterPrefix = line.substringAfter("Dialogue:")
        val parts = afterPrefix.split(",", limit = 10)
        val text = parts.getOrNull(9)?.trim() ?: ""
        val start = parseTime(parts.getOrNull(1)?.trim() ?: "0:00:00.00")
        val end = parseTime(parts.getOrNull(2)?.trim() ?: "0:00:00.00")
        return AssLine(
            layer = parts.getOrNull(0)?.trim()?.toIntOrNull() ?: 0,
            start = start,
            end = end,
            style = parts.getOrNull(3)?.trim() ?: "Default",
            actor = parts.getOrNull(4)?.trim() ?: "",
            marginL = parts.getOrNull(5)?.trim()?.toIntOrNull() ?: 0,
            marginR = parts.getOrNull(6)?.trim()?.toIntOrNull() ?: 0,
            marginV = parts.getOrNull(7)?.trim()?.toIntOrNull() ?: 0,
            effect = parts.getOrNull(8)?.trim() ?: "",
            text = text,
            syllables = parseSyllables(text, start, end)
        )
    }

    private fun parseSyllables(text: String, lineStart: Long = 0L, lineEnd: Long = 0L): List<Syllable> {
        val result = mutableListOf<Syllable>()
        val regex = """\{[\\/]+(k[fFoO]?|[Kk])(\d+)\}([^{]*)""".toRegex()
        var currentPos = lineStart

        val matches = regex.findAll(text).toList()
        if (matches.isEmpty()) {
            if (text.isNotEmpty()) {
                val end = if (lineEnd > lineStart) lineEnd else lineStart + 1000L
                result.add(Syllable(text = text, start = lineStart, end = end))
            }
            return result
        }

        for (match in matches) {
            val tagStr = match.groupValues[1]
            val durationCs = match.groupValues[2].toLongOrNull() ?: 0L
            val sylText = match.groupValues[3]
            val durationMs = durationCs * 10L

            val tag = when (tagStr.lowercase()) {
                "kf" -> KaraokeTag.KF
                "ko" -> KaraokeTag.KO
                "k" -> if (tagStr == "K") KaraokeTag.K_CAPITAL else KaraokeTag.K
                else -> KaraokeTag.K
            }

            result.add(
                Syllable(
                    text = sylText,
                    start = currentPos,
                    end = currentPos + durationMs,
                    tag = tag
                )
            )
            currentPos += durationMs
        }

        return result
    }

    private fun parseAssColor(colorStr: String): androidx.compose.ui.graphics.Color {
        val cleaned = colorStr.replace("&H", "").replace("&", "")
        val hex = cleaned.padStart(8, '0')
        val a = hex.substring(0, 2).toIntOrNull(16) ?: 0
        val b = hex.substring(2, 4).toIntOrNull(16) ?: 0
        val g = hex.substring(4, 6).toIntOrNull(16) ?: 0
        val r = hex.substring(6, 8).toIntOrNull(16) ?: 0
        return androidx.compose.ui.graphics.Color(r / 255f, g / 255f, b / 255f, (255 - a) / 255f)
    }

    fun serialize(assFile: AssFile): String {
        val sb = StringBuilder()
        sb.appendLine("[Script Info]")
        sb.appendLine("Title: Karaoke Mobile Export")
        sb.appendLine("ScriptType: v4.00+")
        sb.appendLine("WrapStyle: 0")
        sb.appendLine("ScaledBorderAndShadow: yes")
        sb.appendLine("YCbCr Matrix: TV.601")
        assFile.audioFile?.let { sb.appendLine("Audio File: $it") }
        assFile.videoFile?.let { sb.appendLine("Video File: $it") }
        sb.appendLine()

        sb.appendLine("[V4+ Styles]")
        sb.appendLine("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        for (style in assFile.styles) {
            sb.appendLine(serializeStyle(style))
        }
        sb.appendLine()

        sb.appendLine("[Events]")
        sb.appendLine("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
        for (line in assFile.lines) {
            sb.appendLine(serializeDialogue(line))
        }

        return sb.toString()
    }

    private fun serializeStyle(style: AssStyle): String {
        return "Style: ${style.name},${style.fontName},${style.fontSize},${colorToAss(style.primaryColor)},${colorToAss(style.secondaryColor)},${colorToAss(style.outlineColor)},${colorToAss(style.backColor)},${if (style.bold) -1 else 0},${if (style.italic) -1 else 0},${if (style.underline) -1 else 0},${if (style.strikeOut) -1 else 0},${style.scaleX},${style.scaleY},${style.spacing},${style.angle},${style.borderStyle},${style.outline},${style.shadow},${style.alignment},${style.marginL},${style.marginR},${style.marginV},${style.encoding}"
    }

    private fun serializeDialogue(line: AssLine): String {
        val text = if (line.syllables.isNotEmpty()) {
            line.syllables.joinToString("") { s ->
                val tag = when (s.tag) {
                    KaraokeTag.KF -> "\\kf${s.duration / 10}"
                    KaraokeTag.KO -> "\\ko${s.duration / 10}"
                    KaraokeTag.K_CAPITAL -> "\\K${s.duration / 10}"
                    else -> "\\k${s.duration / 10}"
                }
                "{$tag}${s.text}"
            }
        } else line.text
        return "Dialogue: ${line.layer},${formatTime(line.start)},${formatTime(line.end)},${line.style},${line.actor},${line.marginL},${line.marginR},${line.marginV},${line.effect},$text"
    }

    private fun colorToAss(color: androidx.compose.ui.graphics.Color): String {
        val a = (255 - (color.alpha * 255).toInt()).toString(16).padStart(2, '0')
        val r = (color.red * 255).toInt().toString(16).padStart(2, '0')
        val g = (color.green * 255).toInt().toString(16).padStart(2, '0')
        val b = (color.blue * 255).toInt().toString(16).padStart(2, '0')
        return "&H$a$b$g$r"
    }
}
