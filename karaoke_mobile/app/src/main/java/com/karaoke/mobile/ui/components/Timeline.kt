package com.karaoke.mobile.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.model.Syllable
import com.karaoke.mobile.model.WaveformData
import com.karaoke.mobile.model.formatTime
import com.karaoke.mobile.ui.theme.KaraokeAccent
import com.karaoke.mobile.ui.theme.KaraokeBurst
import com.karaoke.mobile.ui.theme.KaraokeOnSurface
import com.karaoke.mobile.ui.theme.KaraokeOnSurfaceVariant
import com.karaoke.mobile.ui.theme.KaraokePrimary
import com.karaoke.mobile.ui.theme.KaraokeSecondary
import com.karaoke.mobile.ui.theme.KaraokeSurfaceVariant
import kotlin.math.roundToLong

@Composable
fun TimelinePane(
    waveform: WaveformData?,
    lines: List<AssLine>,
    currentLineIndex: Int,
    currentSyllableIndex: Int,
    playbackPositionMs: Long,
    zoomLevel: Float,
    scrollOffsetMs: Long,
    viewportDurationMs: Long,
    onSeek: (Long) -> Unit,
    onZoomChange: (Float) -> Unit,
    onScrollChange: (Long) -> Unit,
    onSyllableTap: (Int, Int) -> Unit,
    modifier: Modifier = Modifier
) {
    val density = LocalDensity.current
    val textMeasurer = rememberTextMeasurer()
    val backgroundColor = MaterialTheme.colorScheme.surfaceVariant
    val gridColor = KaraokeOnSurfaceVariant.copy(alpha = 0.15f)
    val playheadColor = KaraokeAccent
    val waveformColor = KaraokePrimary.copy(alpha = 0.6f)
    val waveformFillColor = KaraokePrimary.copy(alpha = 0.2f)

    var lastZoom by remember { mutableFloatStateOf(zoomLevel) }
    var lastScroll by remember { mutableLongStateOf(scrollOffsetMs) }

    val animatedZoom by animateFloatAsState(targetValue = zoomLevel, label = "zoom")

    val visibleStart = scrollOffsetMs
    val visibleEnd = visibleStart + (viewportDurationMs / animatedZoom).toLong()

    Column(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(backgroundColor)
            .padding(8.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(120.dp)
                .pointerInput("zoom") {
                    detectTransformGestures { _, _, zoom, _ ->
                        val newZoom = (lastZoom * zoom).coerceIn(0.5f, 10f)
                        onZoomChange(newZoom)
                        lastZoom = newZoom
                    }
                }
                .pointerInput("drag") {
                    detectDragGestures(
                        onDragStart = { lastScroll = scrollOffsetMs },
                        onDrag = { change, dragAmount ->
                            change.consume()
                            val msPerPixel = (viewportDurationMs / animatedZoom) / size.width
                            val newScroll = lastScroll - (dragAmount.x * msPerPixel).roundToLong()
                            onScrollChange(newScroll)
                        }
                    )
                }
                .pointerInput("tap") {
                    detectTapGestures { offset ->
                        val msPerPixel = (viewportDurationMs / animatedZoom) / size.width
                        val clickedMs = scrollOffsetMs + (offset.x * msPerPixel).roundToLong()
                        onSeek(clickedMs.coerceAtLeast(0))

                        val line = lines.getOrNull(currentLineIndex)
                        line?.syllables?.forEachIndexed { sIdx, syl ->
                            val sylStartPx = ((syl.start - scrollOffsetMs) / msPerPixel)
                            val sylEndPx = ((syl.end - scrollOffsetMs) / msPerPixel)
                            if (offset.x in sylStartPx..sylEndPx && offset.y > 60.dp.toPx()) {
                                onSyllableTap(currentLineIndex, sIdx)
                            }
                        }
                    }
                }
        ) {
            Canvas(modifier = Modifier.fillMaxSize()) {
                val width = size.width
                val height = size.height
                val msPerPixel = (viewportDurationMs / animatedZoom) / width
                val visibleStart = scrollOffsetMs
                val visibleEnd = visibleStart + (width * msPerPixel).toLong()

                val gridIntervalMs = 1000L
                val firstGrid = ((visibleStart / gridIntervalMs) + 1) * gridIntervalMs
                for (t in firstGrid..visibleEnd step gridIntervalMs) {
                    val x = ((t - visibleStart) / msPerPixel)
                    drawLine(gridColor, Offset(x, 0f), Offset(x, height), strokeWidth = 1f)
                    val timeText = formatTime(t)
                    val textLayout = textMeasurer.measure(timeText, androidx.compose.ui.text.TextStyle(fontSize = 10.sp, color = KaraokeOnSurfaceVariant))
                    drawText(textLayout, topLeft = Offset(x + 4f, 2f))
                }

                waveform?.let { wf ->
                    drawWaveform(this, wf, visibleStart, visibleEnd, msPerPixel, width, height * 0.55f, waveformColor, waveformFillColor)
                } ?: run {
                    drawRect(
                        brush = Brush.verticalGradient(
                            colors = listOf(
                                KaraokePrimary.copy(alpha = 0.1f),
                                KaraokeSecondary.copy(alpha = 0.05f)
                            ),
                            startY = 0f,
                            endY = height * 0.55f
                        ),
                        size = Size(width, height * 0.55f)
                    )
                }

                val line = lines.getOrNull(currentLineIndex)
                line?.let { l ->
                    val rowHeight = 22f
                    val rowTop = height * 0.6f
                    l.syllables.forEachIndexed { idx, syl ->
                        val sylLeft = ((syl.start - visibleStart) / msPerPixel)
                        val sylRight = ((syl.end - visibleStart) / msPerPixel)
                        if (sylRight >= 0 && sylLeft <= width) {
                            val isSelected = idx == currentSyllableIndex
                            val color = when {
                                syl.isBurst -> KaraokeBurst
                                isSelected -> KaraokeSecondary
                                else -> KaraokePrimary.copy(alpha = 0.7f)
                            }
                            drawRoundRect(
                                color = color.copy(alpha = if (isSelected) 0.9f else 0.5f),
                                topLeft = Offset(sylLeft.coerceIn(0f, width), rowTop),
                                size = Size((sylRight - sylLeft).coerceAtLeast(2f), rowHeight),
                                cornerRadius = androidx.compose.ui.geometry.CornerRadius(4f, 4f)
                            )
                            if (sylRight - sylLeft > 30f) {
                                val text = if (syl.text.length > 8) syl.text.take(6) + "…" else syl.text
                                val textLayout = textMeasurer.measure(
                                    text,
                                    androidx.compose.ui.text.TextStyle(fontSize = 10.sp, color = Color.White)
                                )
                                drawText(
                                    textLayout,
                                    topLeft = Offset(
                                        sylLeft.coerceIn(0f, width - textLayout.size.width) + 4f,
                                        rowTop + 4f
                                    )
                                )
                            }
                        }
                    }
                }

                val playheadX = ((playbackPositionMs - visibleStart) / msPerPixel)
                if (playheadX in 0f..width) {
                    drawLine(playheadColor, Offset(playheadX, 0f), Offset(playheadX, height), strokeWidth = 2f)
                    drawCircle(playheadColor, radius = 5f, center = Offset(playheadX, 0f))
                }
            }
        }

        Text(
            text = "${formatTime(visibleStart)} — ${formatTime(visibleEnd)}  |  ${formatTime(playbackPositionMs)}",
            style = MaterialTheme.typography.labelMedium,
            color = KaraokeOnSurfaceVariant,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 4.dp)
        )
    }
}

private fun drawWaveform(
    scope: DrawScope,
    waveform: WaveformData,
    visibleStart: Long,
    visibleEnd: Long,
    msPerPixel: Float,
    width: Float,
    height: Float,
    color: Color,
    fillColor: Color
) {
    with(scope) {
        val totalDurationMs = waveform.durationMs
        val samples = waveform.length
        val startSample = ((visibleStart.toFloat() / totalDurationMs) * samples).toInt().coerceIn(0, samples - 1)
        val endSample = ((visibleEnd.toFloat() / totalDurationMs) * samples).toInt().coerceIn(0, samples - 1)
        val visibleSamples = (endSample - startSample).coerceAtLeast(1)
        val pixelsPerSample = width / visibleSamples

        if (pixelsPerSample > 2f) {
            for (i in 0 until visibleSamples.coerceAtMost(width.toInt())) {
                val sampleIdx = startSample + i
                if (sampleIdx >= samples) break
                val amp = waveform.maxAmplitudes[sampleIdx]
                val barHeight = amp * height
                val x = i * pixelsPerSample
                val centerY = height / 2
                drawRect(
                    color = color,
                    topLeft = Offset(x, centerY - barHeight / 2),
                    size = Size((pixelsPerSample * 0.8f).coerceAtLeast(1f), barHeight)
                )
            }
        } else {
            val path = androidx.compose.ui.graphics.Path()
            val step = (visibleSamples / width.toInt().coerceAtLeast(1)).coerceAtLeast(1)
            var first = true
            for (x in 0 until width.toInt()) {
                val sampleIdx = startSample + (x * step)
                if (sampleIdx >= samples) break
                var maxAmp = 0f
                val endIdx = (sampleIdx + step).coerceAtMost(samples)
                for (s in sampleIdx until endIdx) {
                    maxAmp = maxOf(maxAmp, waveform.maxAmplitudes[s])
                }
                val y = height / 2 - (maxAmp * height / 2)
                if (first) {
                    path.moveTo(x.toFloat(), y)
                    first = false
                } else {
                    path.lineTo(x.toFloat(), y)
                }
            }
            for (x in width.toInt() downTo 0) {
                val sampleIdx = startSample + (x * step)
                if (sampleIdx >= samples) continue
                var maxAmp = 0f
                val endIdx = (sampleIdx + step).coerceAtMost(samples)
                for (s in sampleIdx until endIdx) {
                    maxAmp = maxOf(maxAmp, waveform.maxAmplitudes[s])
                }
                val y = height / 2 + (maxAmp * height / 2)
                path.lineTo(x.toFloat(), y)
            }
            path.close()
            drawPath(path, fillColor)
            drawPath(path, color, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1f))
        }
    }
}
