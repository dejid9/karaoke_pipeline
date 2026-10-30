package com.karaoke.mobile.model

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import java.util.UUID

/**
 * Тип караоке-тега: \k, \kf, \ko, \K
 */
enum class KaraokeTagType(val tag: String) {
    K("k"),
    KF("kf"),
    KO("ko"),
    K_CAPITAL("K");

    companion object {
        fun fromTag(tag: String): KaraokeTagType =
            entries.find { it.tag == tag } ?: K
    }
}

/**
 * Цвет в формате ASS (&HAABBGGRR или &HBBGGRR)
 */
data class AssColor(val alpha: Int, val red: Int, val green: Int, val blue: Int) {
    companion object {
        fun fromAssString(s: String): AssColor {
            val hex = s.trim().removePrefix("&H").removeSuffix("&")
            val value = hex.toLongOrNull(16) ?: 0
            return if (hex.length > 6) {
                AssColor(
                    alpha = ((value shr 24) and 0xFF).toInt(),
                    blue = ((value shr 16) and 0xFF).toInt(),
                    green = ((value shr 8) and 0xFF).toInt(),
                    red = (value and 0xFF).toInt()
                )
            } else {
                AssColor(
                    alpha = 0,
                    blue = ((value shr 16) and 0xFF).toInt(),
                    green = ((value shr 8) and 0xFF).toInt(),
                    red = (value and 0xFF).toInt()
                )
            }
        }
    }

    fun toAssString(withAlpha: Boolean = true): String =
        if (withAlpha) "&H%02X%02X%02X%02X&".format(alpha, blue, green, red)
        else "&H%02X%02X%02X&".format(blue, green, red)

    fun toComposeColor(): Color = Color(red, green, blue, 255 - alpha)
}

/**
 * Стиль текста ASS
 */
data class AssStyle(
    val name: String = "Default",
    val fontName: String = "Arial",
    val fontSize: Double = 20.0,
    val primaryColor: AssColor = AssColor(0, 255, 255, 255),
    val secondaryColor: AssColor = AssColor(0, 255, 0, 0),
    val outlineColor: AssColor = AssColor(0, 0, 0, 0),
    val backColor: AssColor = AssColor(0, 0, 0, 0),
    val bold: Boolean = false,
    val italic: Boolean = false,
    val underline: Boolean = false,
    val strikeOut: Boolean = false,
    val scaleX: Double = 100.0,
    val scaleY: Double = 100.0,
    val spacing: Double = 0.0,
    val angle: Double = 0.0,
    val borderStyle: Int = 1,
    val outline: Double = 2.0,
    val shadow: Double = 0.0,
    val alignment: Int = 2,
    val marginL: Int = 10,
    val marginR: Int = 10,
    val marginV: Int = 10,
    val encoding: Int = 1
) {
    fun toAssFormat(): String =
        "Style: $name,$fontName,${fontSize.toInt()},${primaryColor.toAssString()},${secondaryColor.toAssString()},${outlineColor.toAssString()},${backColor.toAssString()},${if (bold) -1 else 0},${if (italic) -1 else 0},${if (underline) -1 else 0},${if (strikeOut) -1 else 0},${scaleX.toInt()},${scaleY.toInt()},${spacing.toInt()},${angle.toInt()},$borderStyle,${outline.toInt()},${shadow.toInt()},$alignment,$marginL,$marginR,$marginV,$encoding"

    companion object {
        fun fromAssFormat(line: String): AssStyle {
            val parts = line.substringAfter("Style:").split(",").map { it.trim() }
            return AssStyle(
                name = parts.getOrElse(0) { "Default" },
                fontName = parts.getOrElse(1) { "Arial" },
                fontSize = parts.getOrElse(2) { "20" }.toDoubleOrNull() ?: 20.0,
                primaryColor = AssColor.fromAssString(parts.getOrElse(3) { "&H00FFFFFF&" }),
                secondaryColor = AssColor.fromAssString(parts.getOrElse(4) { "&H000000FF&" }),
                outlineColor = AssColor.fromAssString(parts.getOrElse(5) { "&H00000000&" }),
                backColor = AssColor.fromAssString(parts.getOrElse(6) { "&H00000000&" }),
                bold = parts.getOrElse(7) { "0" } == "-1",
                italic = parts.getOrElse(8) { "0" } == "-1",
                underline = parts.getOrElse(9) { "0" } == "-1",
                strikeOut = parts.getOrElse(10) { "0" } == "-1",
                scaleX = parts.getOrElse(11) { "100" }.toDoubleOrNull() ?: 100.0,
                scaleY = parts.getOrElse(12) { "100" }.toDoubleOrNull() ?: 100.0,
                spacing = parts.getOrElse(13) { "0" }.toDoubleOrNull() ?: 0.0,
                angle = parts.getOrElse(14) { "0" }.toDoubleOrNull() ?: 0.0,
                borderStyle = parts.getOrElse(15) { "1" }.toIntOrNull() ?: 1,
                outline = parts.getOrElse(16) { "2" }.toDoubleOrNull() ?: 2.0,
                shadow = parts.getOrElse(17) { "0" }.toDoubleOrNull() ?: 0.0,
                alignment = parts.getOrElse(18) { "2" }.toIntOrNull() ?: 2,
                marginL = parts.getOrElse(19) { "10" }.toIntOrNull() ?: 10,
                marginR = parts.getOrElse(20) { "10" }.toIntOrNull() ?: 10,
                marginV = parts.getOrElse(21) { "10" }.toIntOrNull() ?: 10,
                encoding = parts.getOrElse(22) { "1" }.toIntOrNull() ?: 1
            )
        }
    }
}

/**
 * Слог караоке
 */
data class KaraokeSyllable(
    val id: String = UUID.randomUUID().toString(),
    val text: String = "",
    val start: Double = 0.0,
    val end: Double = 0.0,
    val tagType: KaraokeTagType = KaraokeTagType.K,
    val isUnspoken: Boolean = false,
    val romanization: String? = null,
    val styleName: String = "Default",
    val actor: String = "",
    val effect: String = "",
    val marginL: Int = 0,
    val marginR: Int = 0,
    val marginV: Int = 0
) {
    val duration: Double get() = end - start

    val displayText: String get() = when {
        isUnspoken || text.isBlank() -> "(пауза)"
        else -> text.replace("\\N", " ↵").replace("\\n", " ↵").replace("\\h", " ")
    }

    fun toAssKaraokeTag(): String {
        val centis = Math.round(duration * 100.0).toInt().coerceAtLeast(0)
        return when (tagType) {
            KaraokeTagType.K -> "{\\k$centis}"
            KaraokeTagType.KF -> "{\\kf$centis}"
            KaraokeTagType.KO -> "{\\ko$centis}"
            KaraokeTagType.K_CAPITAL -> "{\\K$centis}"
        }
    }

    fun toAnnotatedString(selected: Boolean = false, active: Boolean = false): AnnotatedString =
        buildAnnotatedString {
            val baseColor = when {
                isUnspoken -> Color.Gray
                active -> Color(0xFF5D8FE8)
                selected -> Color(0xFF8FB8FF)
                else -> Color.White
            }
            withStyle(SpanStyle(color = baseColor)) {
                val clean = text.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
                append(clean.ifEmpty { if (isUnspoken) " " else "" })
            }
            romanization?.let { rom ->
                append("\n")
                withStyle(SpanStyle(color = baseColor.copy(alpha = 0.7f), fontSize = androidx.compose.ui.unit.TextUnit.Unspecified)) {
                    append(rom)
                }
            }
        }
}

/**
 * Событие диалога ASS
 */
data class AssEvent(
    val id: String = UUID.randomUUID().toString(),
    val layer: Int = 0,
    val start: Double = 0.0,
    val end: Double = 0.0,
    val styleName: String = "Default",
    val actor: String = "",
    val marginL: Int = 0,
    val marginR: Int = 0,
    val marginV: Int = 0,
    val effect: String = "",
    val text: String = "",
    val syllables: List<KaraokeSyllable> = emptyList()
) {
    val duration: Double get() = end - start

    fun toAssLine(): String {
        val startStr = formatAssTime(start)
        val endStr = formatAssTime(end)
        return "Dialogue: $layer,$startStr,$endStr,$styleName,$actor,${marginL.toAssMargin()},${marginR.toAssMargin()},${marginV.toAssMargin()},$effect,$text"
    }

    companion object {
        fun fromAssLine(line: String): AssEvent {
            val trimmed = line.trim()
            if (!trimmed.startsWith("Dialogue:")) {
                return AssEvent(text = trimmed)
            }
            val parts = trimmed.substringAfter("Dialogue:").split(",", limit = 10)
            return AssEvent(
                layer = parts.getOrElse(0) { "0" }.toIntOrNull() ?: 0,
                start = parseAssTime(parts.getOrElse(1) { "0:00:00.00" }),
                end = parseAssTime(parts.getOrElse(2) { "0:00:00.00" }),
                styleName = parts.getOrElse(3) { "Default" }.trim(),
                actor = parts.getOrElse(4) { "" }.trim(),
                marginL = parts.getOrElse(5) { "0000" }.toMarginInt(),
                marginR = parts.getOrElse(6) { "0000" }.toMarginInt(),
                marginV = parts.getOrElse(7) { "0000" }.toMarginInt(),
                effect = parts.getOrElse(8) { "" }.trim(),
                text = parts.getOrElse(9) { "" }.trim()
            )
        }
    }
}

/**
 * Полный ASS документ
 */
data class AssDocument(
    val title: String = "",
    val scriptType: String = "v4.00+",
    val playResX: Int = 1280,
    val playResY: Int = 720,
    val styles: List<AssStyle> = listOf(AssStyle()),
    val events: List<AssEvent> = emptyList(),
    val extraHeaders: Map<String, String> = emptyMap()
) {
    fun toAssText(): String = buildString {
        appendLine("[Script Info]")
        appendLine("Title: $title")
        appendLine("ScriptType: $scriptType")
        appendLine("PlayResX: $playResX")
        appendLine("PlayResY: $playResY")
        extraHeaders.forEach { (k, v) -> appendLine("$k: $v") }
        appendLine()
        appendLine("[V4+ Styles]")
        appendLine("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        styles.forEach { appendLine(it.toAssFormat()) }
        appendLine()
        appendLine("[Events]")
        appendLine("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
        events.forEach { appendLine(it.toAssLine()) }
    }

    companion object {
        fun fromText(text: String): AssDocument {
            return AssParser.parse(text)
        }
    }
}

/**
 * Проект караоке
 */
data class KaraokeProject(
    val id: String = UUID.randomUUID().toString(),
    val name: String = "karaoke-project",
    val mediaPath: String? = null,
    val subtitlePath: String? = null,
    val document: AssDocument = AssDocument(),
    val createdAt: Long = System.currentTimeMillis(),
    val modifiedAt: Long = System.currentTimeMillis()
)

// --- Utility functions ---

fun formatAssTime(seconds: Double): String {
    val totalCentis = Math.round(seconds * 100.0)
    val centis = totalCentis % 100
    val totalSeconds = totalCentis / 100
    val secs = totalSeconds % 60
    val mins = (totalSeconds / 60) % 60
    val hours = totalSeconds / 3600
    return "%d:%02d:%02d.%02d".format(hours, mins, secs, centis)
}

fun parseAssTime(timeStr: String): Double {
    val parts = timeStr.trim().split(":", ".")
    return when (parts.size) {
        3 -> {
            val minutes = parts[0].toIntOrNull() ?: 0
            val seconds = parts[1].toIntOrNull() ?: 0
            val centis = parts[2].toIntOrNull() ?: 0
            minutes * 60.0 + seconds + centis / 100.0
        }
        4 -> {
            val hours = parts[0].toIntOrNull() ?: 0
            val minutes = parts[1].toIntOrNull() ?: 0
            val seconds = parts[2].toIntOrNull() ?: 0
            val centis = parts[3].toIntOrNull() ?: 0
            hours * 3600.0 + minutes * 60.0 + seconds + centis / 100.0
        }
        else -> 0.0
    }
}

private fun String.toMarginInt(): Int =
    trimStart('0').ifEmpty { "0" }.toIntOrNull() ?: 0

private fun Int.toAssMargin(): String =
    toString().padStart(4, '0')

fun List<KaraokeSyllable>.toAssText(): String =
    joinToString("") { it.toAssKaraokeTag() + it.text }

fun List<KaraokeSyllable>.totalDuration(): Double =
    sumOf { it.duration }
