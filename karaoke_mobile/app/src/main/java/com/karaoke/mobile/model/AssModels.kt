package com.karaoke.mobile.model

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle

data class AssStyle(
    val name: String,
    val fontName: String = "Arial",
    val fontSize: Int = 24,
    val primaryColor: Color = Color.White,
    val secondaryColor: Color = Color.Red,
    val outlineColor: Color = Color.Black,
    val backColor: Color = Color.Transparent,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val underline: Boolean = false,
    val strikeOut: Boolean = false,
    val scaleX: Double = 100.0,
    val scaleY: Double = 100.0,
    val spacing: Int = 0,
    val angle: Double = 0.0,
    val borderStyle: Int = 1,
    val outline: Double = 2.0,
    val shadow: Double = 0.0,
    val alignment: Int = 2,
    val marginL: Int = 10,
    val marginR: Int = 10,
    val marginV: Int = 10,
    val encoding: Int = 1
)

data class AssLine(
    val layer: Int = 0,
    val start: Long,
    val end: Long,
    val style: String = "Default",
    val actor: String = "",
    val marginL: Int = 0,
    val marginR: Int = 0,
    val marginV: Int = 0,
    val effect: String = "",
    val text: String = "",
    val syllables: List<Syllable> = emptyList(),
    val isBurst: Boolean = false
) {
    val duration: Long get() = end - start
}

data class Syllable(
    val text: String,
    val start: Long,
    val end: Long,
    val tag: KaraokeTag = KaraokeTag.K,
    val isBurst: Boolean = false
) {
    val duration: Long get() = end - start
    val mid: Long get() = (start + end) / 2
}

enum class KaraokeTag(val prefix: String) {
    K("\\k"),
    KF("\\kf"),
    KO("\\ko"),
    K_CAPITAL("\\K")
}

data class AssFile(
    val scriptInfo: Map<String, String> = emptyMap(),
    val styles: List<AssStyle> = emptyList(),
    val lines: List<AssLine> = emptyList(),
    val audioFile: String? = null,
    val videoFile: String? = null
)

data class WaveformData(
    val samplesPerPixel: Int,
    val minAmplitudes: FloatArray,
    val maxAmplitudes: FloatArray,
    val durationMs: Long
) {
    val length: Int get() = minAmplitudes.size
}

fun Syllable.toDisplayText(): AnnotatedString = buildAnnotatedString {
    if (isBurst) {
        withStyle(SpanStyle(color = Color(0xFFFF6B6B))) {
            append("✦ ")
        }
    }
    append(text)
}

fun formatTime(ms: Long): String {
    val totalSeconds = ms / 1000
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    val centis = (ms % 1000) / 10
    return if (hours > 0) {
        String.format("%d:%02d:%02d.%02d", hours, minutes, seconds, centis)
    } else {
        String.format("%02d:%02d.%02d", minutes, seconds, centis)
    }
}

fun parseTime(timeStr: String): Long {
    val parts = timeStr.split(":", ".")
    return when (parts.size) {
        3 -> {
            val min = parts[0].toLong()
            val sec = parts[1].toLong()
            val cs = parts[2].padEnd(2, '0').take(2).toLong()
            (min * 60 + sec) * 1000 + cs * 10
        }
        4 -> {
            val hr = parts[0].toLong()
            val min = parts[1].toLong()
            val sec = parts[2].toLong()
            val cs = parts[3].padEnd(2, '0').take(2).toLong()
            ((hr * 3600) + (min * 60) + sec) * 1000 + cs * 10
        }
        else -> 0L
    }
}
