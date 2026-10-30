package com.karaoke.mobile.ui.components

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.ui.theme.KaraokeThemePalette
import kotlin.math.max

/**
 * Информационная панель дорожки со счетчиком слогов и SPS-индикатором из ПК-версии.
 */
@Composable
fun TrackInfoBar(
    projectName: String?,
    syllableCount: Int,
    activeSyllable: KaraokeSyllable?,
    palette: KaraokeThemePalette,
    modifier: Modifier = Modifier
) {
    val sps = if (activeSyllable != null && activeSyllable.duration > 0.02) {
        1.0 / activeSyllable.duration
    } else 0.0

    val spsColor = when {
        sps <= 0.0 -> palette.muted
        sps < 6.0 -> palette.success
        sps < 9.0 -> palette.warning
        else -> palette.danger
    }

    val spsBadgeText = when {
        sps <= 0.0 -> ""
        sps < 6.0 -> "Обычный"
        sps < 9.0 -> "Быстрый"
        else -> "Экстрим"
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(palette.panel)
            .padding(horizontal = 8.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                text = projectName ?: "Проект",
                color = palette.fg,
                fontSize = 11.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                maxLines = 1
            )
            Surface(
                color = palette.raised,
                shape = RoundedCornerShape(3.dp),
                border = androidx.compose.foundation.BorderStroke(0.5.dp, palette.border.copy(alpha = 0.5f))
            ) {
                Text(
                    text = "$syllableCount сл.",
                    color = palette.muted,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                )
            }
        }

        if (activeSyllable != null && sps > 0) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = "SPS: %.1f".format(sps),
                    color = spsColor,
                    fontSize = 10.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                )
                Surface(
                    color = spsColor.copy(alpha = 0.18f),
                    shape = RoundedCornerShape(3.dp),
                    border = androidx.compose.foundation.BorderStroke(0.5.dp, spsColor.copy(alpha = 0.5f))
                ) {
                    Text(
                        text = spsBadgeText,
                        color = spsColor,
                        fontSize = 9.sp,
                        modifier = Modifier.padding(horizontal = 3.dp, vertical = 1.dp)
                    )
                }
            }
        }
    }
}

/**
 * Обзорный мини-таймлайн всей композиции (Overview Timeline из ПК-версии).
 * Показывает полную панораму песни с рамкой текущего видимого окна.
 */
@Composable
fun OverviewTimeline(
    duration: Double,
    scrollOffset: Float,
    zoomLevel: Float,
    waveformData: List<Float>,
    syllables: List<KaraokeSyllable>,
    playbackPosition: Double,
    palette: KaraokeThemePalette,
    onSeekOrScroll: (Double) -> Unit,
    modifier: Modifier = Modifier
) {
    val height = 20.dp
    val pps = 50f * zoomLevel

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .background(palette.canvasAlt)
            .border(androidx.compose.foundation.BorderStroke(0.5.dp, palette.border.copy(alpha = 0.4f)))
            .pointerInput(duration) {
                detectTapGestures { offset ->
                    if (duration > 0 && size.width > 0) {
                        val fraction = (offset.x / size.width).coerceIn(0f, 1f)
                        onSeekOrScroll((fraction * duration).toDouble())
                    }
                }
            }
    ) {
        if (duration <= 0) return@Canvas
        val totalSecs = duration.toFloat()

        // 1. Полная форма волны в миниатюре
        if (waveformData.isNotEmpty()) {
            val samplesCount = waveformData.size
            val centerY = size.height / 2f
            val amp = size.height / 2.2f
            val step = max(1, samplesCount / size.width.toInt().coerceAtLeast(1))
            for (px in 0 until size.width.toInt()) {
                val sIdx = (px * step).coerceIn(0, samplesCount - 1)
                val v = waveformData[sIdx]
                drawLine(
                    color = palette.accent.copy(alpha = 0.3f),
                    start = Offset(px.toFloat(), centerY - v * amp),
                    end = Offset(px.toFloat(), centerY + v * amp),
                    strokeWidth = 1f
                )
            }
        }

        // 2. Отметки слогов (тонкие линии)
        syllables.forEach { syl ->
            val startFrac = (syl.start.toFloat() / totalSecs).coerceIn(0f, 1f)
            val endFrac = (syl.end.toFloat() / totalSecs).coerceIn(0f, 1f)
            val x1 = startFrac * size.width
            val x2 = endFrac * size.width
            val w = max(1f, x2 - x1)
            drawRect(
                color = if (syl.isUnspoken) palette.muted.copy(alpha = 0.35f) else palette.accentAlt.copy(alpha = 0.55f),
                topLeft = Offset(x1, 2f),
                size = Size(w, size.height - 4f)
            )
        }

        // 3. Рамка видимой области (viewport)
        val visibleStartSec = (scrollOffset / pps).coerceAtLeast(0f)
        val visibleSpanSec = (size.width / pps).coerceAtLeast(0.1f)
        val vStartFrac = (visibleStartSec / totalSecs).coerceIn(0f, 1f)
        val vEndFrac = ((visibleStartSec + visibleSpanSec) / totalSecs).coerceIn(0f, 1f)
        val vx = vStartFrac * size.width
        val vw = max(6f, (vEndFrac - vStartFrac) * size.width)

        drawRect(
            color = palette.accent.copy(alpha = 0.15f),
            topLeft = Offset(vx, 0f),
            size = Size(vw, size.height)
        )
        drawRect(
            color = palette.accent,
            topLeft = Offset(vx, 0f),
            size = Size(vw, size.height),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.5f)
        )

        // 4. Текущий плейхед
        val playFrac = (playbackPosition.toFloat() / totalSecs).coerceIn(0f, 1f)
        val px = playFrac * size.width
        drawLine(
            color = palette.danger,
            start = Offset(px, 0f),
            end = Offset(px, size.height),
            strokeWidth = 2f
        )
    }
}

/**
 * Визуальный таймлайн с waveform и слогами.
 * Поддерживает pinch-to-zoom, панорамирование (скролл) и тап для поиска/выделения.
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
    onCanvasWidthChange: (Float) -> Unit = {},
    modifier: Modifier = Modifier
) {
    val canvasHeight = 90.dp
    val timeHeight = 18.dp
    val totalHeight = canvasHeight + timeHeight

    var canvasWidth by remember { mutableFloatStateOf(0f) }
    val pixelsPerSecond = 50f * zoomLevel

    // Актуальные состояния для жестов
    val curZoom by rememberUpdatedState(zoomLevel)
    val curScroll by rememberUpdatedState(scrollOffset)
    val curDuration by rememberUpdatedState(duration)
    val curWidth by rememberUpdatedState(canvasWidth)
    val curSyllables by rememberUpdatedState(syllables)
    val curOnSeek by rememberUpdatedState(onSeek)
    val curOnSelect by rememberUpdatedState(onSelectSyllable)
    val curOnZoomChange by rememberUpdatedState(onZoomChange)
    val curOnScrollChange by rememberUpdatedState(onScrollChange)

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(totalHeight)
            .background(palette.canvas)
            .border(androidx.compose.foundation.BorderStroke(0.5.dp, palette.border.copy(alpha = 0.4f)))
    ) {
        // Основной Canvas с waveform и слогами
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(canvasHeight)
                .background(palette.canvas)
                .pointerInput(Unit) {
                    detectTapGestures { offset ->
                        val pps = 50f * curZoom
                        val clickTime = ((offset.x + curScroll) / pps).toDouble()
                        val hit = curSyllables.firstOrNull { s ->
                            clickTime in s.start..s.end
                        }
                        if (hit != null) {
                            curOnSelect(hit.id)
                        } else {
                            curOnSeek(clickTime.coerceIn(0.0, curDuration))
                        }
                    }
                }
                .pointerInput(Unit) {
                    detectTransformGestures(panZoomLock = false) { centroid, pan, zoom, _ ->
                        val pps = 50f * curZoom
                        val effectiveTotalWidth = (curDuration * pps).toFloat()
                        val maxScroll = max(0f, effectiveTotalWidth - curWidth)

                        // 1. Zoom (pinch)
                        if (kotlin.math.abs(zoom - 1f) > 0.005f) {
                            val newZoom = (curZoom * zoom).coerceIn(0.25f, 20f)
                            val newPps = 50f * newZoom
                            val anchorTime = (curScroll + centroid.x) / pps
                            val newScroll = (anchorTime * newPps - centroid.x)
                                .coerceIn(0f, max(0f, (curDuration * newPps - curWidth).toFloat()))
                            curOnZoomChange(newZoom)
                            curOnScrollChange(newScroll)
                        }

                        // 2. Pan (скролл)
                        if (kotlin.math.abs(pan.x) > 0.1f) {
                            val newScroll = (curScroll - pan.x).coerceIn(0f, maxScroll)
                            curOnScrollChange(newScroll)
                        }
                    }
                }
        ) {
            canvasWidth = size.width
            onCanvasWidthChange(size.width)

            val visibleStart = (scrollOffset / pixelsPerSecond).toDouble()
            val visibleEnd = ((scrollOffset + canvasWidth) / pixelsPerSecond).toDouble()

            // Сетка времени
            drawTimeGrid(
                visibleStart = visibleStart,
                visibleEnd = visibleEnd,
                pixelsPerSecond = pixelsPerSecond,
                scrollOffset = scrollOffset,
                canvasHeight = size.height,
                color = palette.grid
            )

            // Waveform
            drawWaveform(
                waveformData = waveformData,
                duration = duration,
                pixelsPerSecond = pixelsPerSecond,
                scrollOffset = scrollOffset,
                canvasHeight = size.height,
                color = palette.accent.copy(alpha = 0.35f)
            )

            // Слоги
            val textPaint = Paint().apply {
                color = palette.fg.toArgb()
                textSize = 24f
                isAntiAlias = true
                textAlign = Paint.Align.LEFT
            }

            syllables.forEach { syllable ->
                val x = (syllable.start * pixelsPerSecond - scrollOffset).toFloat()
                val width = (syllable.duration * pixelsPerSecond).toFloat()
                if (x + width < 0 || x > canvasWidth) return@forEach

                val isSelected = syllable.id in selectedIds
                val isActive = syllable.id == activeSyllableId

                val bgColor = when {
                    isActive -> palette.accent.copy(alpha = 0.85f)
                    isSelected -> palette.selection.copy(alpha = 0.6f)
                    syllable.isUnspoken -> palette.muted.copy(alpha = 0.25f)
                    else -> palette.raised.copy(alpha = 0.6f)
                }

                val borderColor = when {
                    isActive -> palette.accentAlt
                    isSelected -> palette.accent
                    else -> palette.border.copy(alpha = 0.5f)
                }

                val topY = 10f
                val boxHeight = size.height - 20f

                // Фон слога
                drawRect(
                    color = bgColor,
                    topLeft = Offset(x, topY),
                    size = Size(width.coerceAtLeast(2f), boxHeight)
                )

                // Рамка слога
                drawRect(
                    color = borderColor,
                    topLeft = Offset(x, topY),
                    size = Size(width.coerceAtLeast(2f), boxHeight),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = if (isActive || isSelected) 2f else 1f)
                )

                // Текст слога внутри блока (если блок достаточно широкий)
                if (width > 24f) {
                    val rawText = syllable.displayText
                    val textToDraw = if (rawText.length > 8) rawText.take(7) + "…" else rawText
                    drawContext.canvas.nativeCanvas.drawText(
                        textToDraw,
                        x + 4f,
                        topY + boxHeight / 2f + 8f,
                        textPaint
                    )
                }
            }

            // Playhead (текущая позиция воспроизведения)
            val playheadX = (playbackPosition * pixelsPerSecond - scrollOffset).toFloat()
            if (playheadX in 0f..canvasWidth) {
                drawLine(
                    color = palette.danger,
                    start = Offset(playheadX, 0f),
                    end = Offset(playheadX, size.height),
                    strokeWidth = 2.5f
                )
                drawCircle(
                    color = palette.danger,
                    radius = 5f,
                    center = Offset(playheadX, 5f)
                )
            }
        }

        // Кнопки зума (+) и (-) в правом верхнем углу
        Row(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(4.dp),
            horizontalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = palette.panel.copy(alpha = 0.9f),
                border = androidx.compose.foundation.BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
            ) {
                IconButton(
                    onClick = { onZoomChange((zoomLevel * 1.3f).coerceIn(0.25f, 20f)) },
                    modifier = Modifier.size(24.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Add,
                        contentDescription = "Zoom In",
                        tint = palette.fg,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = palette.panel.copy(alpha = 0.9f),
                border = androidx.compose.foundation.BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
            ) {
                IconButton(
                    onClick = { onZoomChange((zoomLevel / 1.3f).coerceIn(0.25f, 20f)) },
                    modifier = Modifier.size(24.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Remove,
                        contentDescription = "Zoom Out",
                        tint = palette.fg,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }

        // Шкала времени
        TimeRulerCanvas(
            visibleStart = (scrollOffset / pixelsPerSecond).toDouble(),
            visibleEnd = ((scrollOffset + canvasWidth) / pixelsPerSecond).toDouble(),
            pixelsPerSecond = pixelsPerSecond,
            scrollOffset = scrollOffset,
            palette = palette,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .height(timeHeight)
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
    val amplitude = (canvasHeight - 24f) / 2f

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
            color = color.copy(alpha = 0.25f),
            start = Offset(x, 0f),
            end = Offset(x, canvasHeight),
            strokeWidth = 0.5f
        )
        t += step
    }
}

@Composable
private fun TimeRulerCanvas(
    visibleStart: Double,
    visibleEnd: Double,
    pixelsPerSecond: Float,
    scrollOffset: Float,
    palette: KaraokeThemePalette,
    modifier: Modifier = Modifier
) {
    val textPaint = remember(palette) {
        Paint().apply {
            color = palette.muted.toArgb()
            textSize = 22f
            isAntiAlias = true
            textAlign = Paint.Align.LEFT
        }
    }

    Canvas(modifier = modifier.background(palette.canvasAlt)) {
        val step = when {
            pixelsPerSecond > 200 -> 0.5
            pixelsPerSecond > 100 -> 1.0
            pixelsPerSecond > 50 -> 2.0
            pixelsPerSecond > 20 -> 5.0
            else -> 10.0
        }

        drawLine(
            color = palette.border.copy(alpha = 0.4f),
            start = Offset(0f, 0f),
            end = Offset(size.width, 0f),
            strokeWidth = 1f
        )

        var t = (visibleStart / step).toInt() * step
        while (t <= visibleEnd) {
            val x = (t * pixelsPerSecond - scrollOffset).toFloat()
            if (x in 0f..size.width) {
                drawLine(
                    color = palette.border.copy(alpha = 0.5f),
                    start = Offset(x, 0f),
                    end = Offset(x, 4f),
                    strokeWidth = 1f
                )
                drawContext.canvas.nativeCanvas.drawText(
                    formatTime(t),
                    x + 3f,
                    size.height - 3f,
                    textPaint
                )
            }
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
