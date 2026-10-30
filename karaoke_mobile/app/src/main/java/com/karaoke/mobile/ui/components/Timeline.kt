package com.karaoke.mobile.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.ui.theme.KaraokeThemePalette
import kotlin.math.max
import kotlin.math.min

/**
 * Визуальный таймлайн с waveform и слогами.
 * Портирован из karaoke_gui/timeline.py
 */
@Composable
fun Timeline(
    syllables: List<KaraokeSyllable>,
    waveformData: List<Float>,
    playbackPosition: Double,
    duration: Double,
    zoomLevel: Float,
    scrollOffset: Float,
    selectedIds: Set<String>,
    activeSyllableId: String?,
    palette: KaraokeThemePalette,
    onSeek: (Double) -> Unit,
    onSelectSyllable: (String) -> Unit,
    onZoomChange: (Float) -> Unit,
    onScrollChange: (Float) -> Unit,
    modifier: Modifier = Modifier
) {
    val density = LocalDensity.current
    val canvasHeight = 180.dp
    val timeHeight = 24.dp
    val totalHeight = canvasHeight + timeHeight

    var canvasWidth by remember { mutableFloatStateOf(0f) }
    val pixelsPerSecond = 50f * zoomLevel
    val totalWidth = (duration * pixelsPerSecond).toFloat()

    Box(modifier = modifier.fillMaxWidth().height(totalHeight)) {
        // Canvas с waveform и слогами
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(canvasHeight)
                .background(palette.canvas)
                .pointerInput(zoomLevel, scrollOffset) {
                    detectTapGestures { offset ->
                        val time = ((offset.x + scrollOffset) / pixelsPerSecond).toDouble()
                        onSeek(time.coerceIn(0.0, duration))
                    }
                }
                .pointerInput(Unit) {
                    detectDragGestures { change, dragAmount ->
                        change.consume()
                        if (kotlin.math.abs(dragAmount.x) > kotlin.math.abs(dragAmount.y)) {
                            // Horizontal drag - scroll
                            val newScroll = (scrollOffset - dragAmount.x).coerceIn(0f, max(0f, totalWidth - canvasWidth))
                            onScrollChange(newScroll)
                        } else {
                            // Vertical drag - zoom
                            val zoomDelta = dragAmount.y * 0.01f
                            onZoomChange((zoomLevel - zoomDelta).coerceIn(0.5f, 10f))
                        }
                    }
                }
        ) {
            canvasWidth = size.width
            val visibleStart = (scrollOffset / pixelsPerSecond).toDouble()
            val visibleEnd = ((scrollOffset + canvasWidth) / pixelsPerSecond).toDouble()

            // Рисуем waveform
            drawWaveform(
                waveformData = waveformData,
                duration = duration,
                pixelsPerSecond = pixelsPerSecond,
                scrollOffset = scrollOffset,
                canvasHeight = size.height,
                color = palette.accent.copy(alpha = 0.3f)
            )

            // Рисуем сетку времени
            drawTimeGrid(
                visibleStart = visibleStart,
                visibleEnd = visibleEnd,
                pixelsPerSecond = pixelsPerSecond,
                scrollOffset = scrollOffset,
                canvasHeight = size.height,
                color = palette.grid
            )

            // Рисуем слоги
            syllables.forEach { syllable ->
                val x = (syllable.start * pixelsPerSecond - scrollOffset).toFloat()
                val width = (syllable.duration * pixelsPerSecond).toFloat()
                if (x + width < 0 || x > canvasWidth) return@forEach

                val isSelected = syllable.id in selectedIds
                val isActive = syllable.id == activeSyllableId

                val bgColor = when {
                    isActive -> palette.accent
                    isSelected -> palette.selection.copy(alpha = 0.5f)
                    syllable.isUnspoken -> palette.muted.copy(alpha = 0.3f)
                    else -> palette.raised.copy(alpha = 0.5f)
                }

                val borderColor = when {
                    isActive -> palette.accentAlt
                    isSelected -> palette.accent
                    else -> palette.border.copy(alpha = 0.3f)
                }

                // Фон слога
                drawRect(
                    color = bgColor,
                    topLeft = Offset(x, 20f),
                    size = Size(width.coerceAtLeast(2f), size.height - 40f)
                )

                // Граница
                drawRect(
                    color = borderColor,
                    topLeft = Offset(x, 20f),
                    size = Size(width.coerceAtLeast(2f), size.height - 40f),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1f)
                )

                // Текст слога (если достаточно места)
                if (width > 30f) {
                    // Текст рисуется через drawContext, но для простоты пропускаем
                    // В реальном приложении используйте Text на Canvas или overlay
                }
            }

            // Playhead
            val playheadX = (playbackPosition * pixelsPerSecond - scrollOffset).toFloat()
            if (playheadX in 0f..canvasWidth) {
                drawLine(
                    color = palette.danger,
                    start = Offset(playheadX, 0f),
                    end = Offset(playheadX, size.height),
                    strokeWidth = 2f
                )
                // Треугольник наверху
                drawCircle(
                    color = palette.danger,
                    radius = 6f,
                    center = Offset(playheadX, 6f)
                )
            }
        }

        // Шкала времени
        TimeRuler(
            visibleStart = (scrollOffset / pixelsPerSecond).toDouble(),
            visibleEnd = ((scrollOffset + canvasWidth) / pixelsPerSecond).toDouble(),
            pixelsPerSecond = pixelsPerSecond,
            palette = palette,
            modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth().height(timeHeight)
        )
    }
}

private fun DrawScope.drawWaveform(
    waveformData: List<Float>,
    duration: Double,
    pixelsPerSecond: Float,
    scrollOffset: Float,
    canvasHeight: Float,
    color: Color
) {
    if (waveformData.isEmpty() || duration <= 0) return

    val samplesPerPixel = (waveformData.size / (duration * pixelsPerSecond)).toFloat().coerceAtLeast(1f)
    val centerY = canvasHeight / 2f
    val amplitude = (canvasHeight - 40f) / 2f

    val startPixel = (scrollOffset / pixelsPerSecond * samplesPerPixel).toInt().coerceAtLeast(0)
    val endPixel = ((scrollOffset + size.width) / pixelsPerSecond * samplesPerPixel).toInt()
        .coerceAtMost(waveformData.size - 1)

    for (pixel in startPixel..endPixel) {
        val sampleIndex = (pixel * samplesPerPixel).toInt().coerceIn(0, waveformData.size - 1)
        val value = waveformData[sampleIndex]
        val x = (pixel / samplesPerPixel * pixelsPerSecond - scrollOffset).toFloat()
        val h = value * amplitude

        drawLine(
            color = color,
            start = Offset(x, centerY - h),
            end = Offset(x, centerY + h),
            strokeWidth = 1f
        )
    }
}

private fun DrawScope.drawTimeGrid(
    visibleStart: Double,
    visibleEnd: Double,
    pixelsPerSecond: Float,
    scrollOffset: Float,
    canvasHeight: Float,
    color: Color
) {
    val step = when {
        pixelsPerSecond > 200 -> 0.5
        pixelsPerSecond > 100 -> 1.0
        pixelsPerSecond > 50 -> 2.0
        pixelsPerSecond > 20 -> 5.0
        else -> 10.0
    }

    var t = (visibleStart / step).toInt() * step
    while (t <= visibleEnd) {
        val x = (t * pixelsPerSecond - scrollOffset).toFloat()
        drawLine(
            color = color.copy(alpha = 0.3f),
            start = Offset(x, 0f),
            end = Offset(x, canvasHeight),
            strokeWidth = 0.5f
        )
        t += step
    }
}

@Composable
private fun TimeRuler(
    visibleStart: Double,
    visibleEnd: Double,
    pixelsPerSecond: Float,
    palette: KaraokeThemePalette,
    modifier: Modifier = Modifier
) {
    val step = when {
        pixelsPerSecond > 200 -> 0.5
        pixelsPerSecond > 100 -> 1.0
        pixelsPerSecond > 50 -> 2.0
        pixelsPerSecond > 20 -> 5.0
        else -> 10.0
    }

    Box(modifier = modifier.background(palette.canvasAlt)) {
        var t = (visibleStart / step).toInt() * step
        while (t <= visibleEnd) {
            val x = (t * pixelsPerSecond).toFloat()
            Text(
                text = formatTime(t),
                color = palette.muted,
                fontSize = 10.sp,
                modifier = Modifier.padding(start = x.dp + 4.dp, top = 4.dp)
            )
            t += step
        }
    }
}

fun formatTime(seconds: Double): String {
    val totalCentis = (seconds * 100).toLong()
    val centis = totalCentis % 100
    val totalSecs = totalCentis / 100
    val secs = totalSecs % 60
    val mins = totalSecs / 60
    return if (mins > 0) "%d:%02d.%02d".format(mins, secs, centis)
    else "%d.%02d".format(secs, centis)
}
