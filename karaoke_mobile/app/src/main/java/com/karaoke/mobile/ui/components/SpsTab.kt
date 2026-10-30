package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.*
import com.karaoke.mobile.ui.theme.KaraokeThemePalette
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Вкладка «Точный SPS»:
 * - Расчет и визуализация артикуляционной скорости (SPS)
 * - Интерактивный SPS-график скорости по времени
 * - Прецизионная акустическая обрезка границ слогов (с шагом до 0.01с и привязкой)
 * - Контекстное прослушивание слогов (1 и 2 слога слева и справа)
 * - Список скоростных очередей (Bursts)
 */
@Composable
fun SpsTab(
    syllables: List<KaraokeSyllable>,
    activeSyllableId: String?,
    spsStatistics: SpsStatistics,
    spsBursts: List<SpsBurst>,
    selectedBurstId: String?,
    waveformData: List<Float>,
    spectrogramData: SpectrogramData?,
    spectrogramView: SpectrogramViewSettings,
    timelineViewMode: TimelineViewMode,
    playbackPosition: Double,
    duration: Double,
    playbackSpeed: Float,
    preservePitch: Boolean,
    returnToStart: Boolean,
    isPlaying: Boolean,
    zoomLevel: Float,
    scrollOffset: Float,
    palette: KaraokeThemePalette,
    onReturnToKaraoke: () -> Unit,
    onSelectSyllable: (String) -> Unit,
    onAdjustStart: (String, Double) -> Unit,
    onAdjustEnd: (String, Double) -> Unit,
    onSnapStartToPrevious: (String) -> Unit,
    onSnapEndToNext: (String) -> Unit,
    onShiftJointBoundary: (String, Double) -> Unit,
    onPreviewSyllable: (String, Int, Int) -> Unit,
    onSelectBurst: (SpsBurst) -> Unit,
    onPlayPause: () -> Unit,
    onStop: () -> Unit,
    onSeek: (Double) -> Unit,
    onZoomChange: (Float) -> Unit,
    onScrollChange: (Float) -> Unit,
    onTimelineViewModeChange: (TimelineViewMode) -> Unit,
    onShowSpeedDialog: () -> Unit,
    onToggleReturnToStart: () -> Unit,
    modifier: Modifier = Modifier
) {
    val activeSyllable = syllables.find { it.id == activeSyllableId } ?: syllables.firstOrNull()

    // Точки SPS графика
    val spsPoints = remember(syllables) {
        SpsCalculator.calculateSpsCurve(syllables)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(palette.bg)
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        // Шапка и сводка SPS
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Метрики SPS
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Speed,
                        contentDescription = null,
                        tint = palette.accent,
                        modifier = Modifier.size(20.dp)
                    )
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "Пик: ${spsStatistics.peakSps} сл/с",
                                color = palette.fg,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "• Средн: ${spsStatistics.meanSps} сл/с",
                                color = palette.muted,
                                fontSize = 12.sp
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "Слогов: ${spsStatistics.totalSyllables}",
                                color = palette.muted,
                                fontSize = 11.sp
                            )
                            if (spsStatistics.burstCount > 0) {
                                Text(
                                    text = "• Очередей: ${spsStatistics.burstCount}",
                                    color = if (spsStatistics.burstCount > 5) palette.warning else palette.muted,
                                    fontSize = 11.sp
                                )
                            }
                        }
                    }

                    // Бейдж категории темпа
                    val (badgeText, badgeColor) = when {
                        spsStatistics.peakSps <= 5.0 -> "Обычный" to palette.muted
                        spsStatistics.peakSps <= 7.5 -> "Быстрый" to palette.warning
                        else -> "Экстрим" to palette.danger
                    }
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = badgeColor.copy(alpha = 0.15f),
                        border = BorderStroke(1.dp, badgeColor.copy(alpha = 0.4f))
                    ) {
                        Text(
                            text = badgeText,
                            color = badgeColor,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }

                // Кнопка возврата в караоке
                OutlinedButton(
                    onClick = onReturnToKaraoke,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.accent),
                    border = BorderStroke(1.dp, palette.accent.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(6.dp),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                    modifier = Modifier.height(28.dp)
                ) {
                    Icon(Icons.Default.ArrowBack, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("В караоке", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }

        // SPS График артикуляционной скорости
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(containerColor = palette.canvas),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(4.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "График скорости слогов (SPS Curve)",
                        color = palette.muted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = "Окно 1.0с | Порог 6.0 сл/с",
                        color = palette.muted.copy(alpha = 0.7f),
                        fontSize = 10.sp
                    )
                }

                SpsGraphView(
                    points = spsPoints,
                    peakSps = spsStatistics.peakSps,
                    meanSps = spsStatistics.meanSps,
                    duration = duration,
                    playbackPosition = playbackPosition,
                    scrollOffset = scrollOffset,
                    zoomLevel = zoomLevel,
                    palette = palette,
                    onSeek = onSeek,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(95.dp)
                )
            }
        }

        // Таймлайн с волноформой и спектрограммой
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(containerColor = palette.canvasAlt),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Компактный транспорт-бар
                CompactTransportBar(
                    isPlaying = isPlaying,
                    playbackPosition = playbackPosition,
                    duration = duration,
                    playbackSpeed = playbackSpeed,
                    preservePitch = preservePitch,
                    returnToStart = returnToStart,
                    palette = palette,
                    onPlayPause = onPlayPause,
                    onStop = onStop,
                    onSeek = onSeek,
                    onShowSpeedDialog = onShowSpeedDialog,
                    onToggleReturnToStart = onToggleReturnToStart
                )

                // Сам таймлайн
                Timeline(
                    syllables = syllables,
                    waveformData = waveformData,
                    spectrogramData = spectrogramData,
                    spectrogramView = spectrogramView,
                    timelineViewMode = timelineViewMode,
                    playbackPosition = playbackPosition,
                    duration = duration,
                    zoomLevel = zoomLevel,
                    scrollOffset = scrollOffset,
                    selectedIds = if (activeSyllable != null) setOf(activeSyllable.id) else emptySet(),
                    activeSyllableId = activeSyllable?.id,
                    palette = palette,
                    onSeek = onSeek,
                    onSelectSyllable = onSelectSyllable,
                    onZoomChange = onZoomChange,
                    onScrollChange = onScrollChange,
                    onTimelineViewModeChange = onTimelineViewModeChange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                )
            }
        }

        // Панель прецизионной обрезки слога (Acoustic Trimming)
        if (activeSyllable != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = palette.panel),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f))
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    // Инфо о текущем слоге
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "Слог: \"${activeSyllable.text.trim()}\"",
                                color = palette.fg,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold
                            )
                            val sylSps = if (activeSyllable.duration > 0.02) (1.0 / activeSyllable.duration) else 0.0
                            Surface(
                                shape = RoundedCornerShape(3.dp),
                                color = palette.raised,
                                border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.4f))
                            ) {
                                Text(
                                    text = "%.2f с | %.1f сл/с".format(activeSyllable.duration, sylSps),
                                    color = if (sylSps >= 6.0) palette.warning else palette.muted,
                                    fontSize = 11.sp,
                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                                )
                            }
                        }

                        // Контекстное прослушивание
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            OutlinedButton(
                                onClick = { onPreviewSyllable(activeSyllable.id, 1, 0) },
                                contentPadding = PaddingValues(horizontal = 5.dp, vertical = 1.dp),
                                modifier = Modifier.height(24.dp),
                                shape = RoundedCornerShape(4.dp),
                                border = BorderStroke(0.5.dp, palette.border)
                            ) {
                                Text("◀ 1 сл", fontSize = 10.sp, color = palette.fg)
                            }
                            Button(
                                onClick = { onPreviewSyllable(activeSyllable.id, 0, 0) },
                                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                                modifier = Modifier.height(24.dp),
                                shape = RoundedCornerShape(4.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = palette.accent)
                            ) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(12.dp))
                                Spacer(Modifier.width(2.dp))
                                Text("Слог", fontSize = 10.sp, fontWeight = FontWeight.Bold)
                            }
                            OutlinedButton(
                                onClick = { onPreviewSyllable(activeSyllable.id, 0, 1) },
                                contentPadding = PaddingValues(horizontal = 5.dp, vertical = 1.dp),
                                modifier = Modifier.height(24.dp),
                                shape = RoundedCornerShape(4.dp),
                                border = BorderStroke(0.5.dp, palette.border)
                            ) {
                                Text("1 сл ▶", fontSize = 10.sp, color = palette.fg)
                            }
                        }
                    }

                    // Начало (Start)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text("Старт: ${formatAssTime(activeSyllable.start)}", color = palette.muted, fontSize = 11.sp, modifier = Modifier.width(90.dp))
                        TrimButton("-0.05", palette) { onAdjustStart(activeSyllable.id, -0.05) }
                        TrimButton("-0.01", palette, isAccent = true) { onAdjustStart(activeSyllable.id, -0.01) }
                        TrimButton("+0.01", palette, isAccent = true) { onAdjustStart(activeSyllable.id, 0.01) }
                        TrimButton("+0.05", palette) { onAdjustStart(activeSyllable.id, 0.05) }
                        Spacer(Modifier.weight(1f))
                        OutlinedButton(
                            onClick = { onSnapStartToPrevious(activeSyllable.id) },
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                            modifier = Modifier.height(24.dp),
                            shape = RoundedCornerShape(4.dp),
                            border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.6f))
                        ) {
                            Text("К пред. слогу", fontSize = 10.sp, color = palette.accent)
                        }
                    }

                    // Конец (End)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text("Конец: ${formatAssTime(activeSyllable.end)}", color = palette.muted, fontSize = 11.sp, modifier = Modifier.width(90.dp))
                        TrimButton("-0.05", palette) { onAdjustEnd(activeSyllable.id, -0.05) }
                        TrimButton("-0.01", palette, isAccent = true) { onAdjustEnd(activeSyllable.id, -0.01) }
                        TrimButton("+0.01", palette, isAccent = true) { onAdjustEnd(activeSyllable.id, 0.01) }
                        TrimButton("+0.05", palette) { onAdjustEnd(activeSyllable.id, 0.05) }
                        Spacer(Modifier.weight(1f))
                        OutlinedButton(
                            onClick = { onSnapEndToNext(activeSyllable.id) },
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                            modifier = Modifier.height(24.dp),
                            shape = RoundedCornerShape(4.dp),
                            border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.6f))
                        ) {
                            Text("К след. слогу", fontSize = 10.sp, color = palette.accent)
                        }
                    }

                    // Сдвиг стыка слогов
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Стык слогов:", color = palette.muted, fontSize = 11.sp)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            OutlinedButton(
                                onClick = { onShiftJointBoundary(activeSyllable.id, -0.01) },
                                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                                modifier = Modifier.height(24.dp),
                                shape = RoundedCornerShape(4.dp),
                                border = BorderStroke(0.5.dp, palette.border)
                            ) {
                                Text("◀ Стык -0.01с", fontSize = 10.sp, color = palette.fg)
                            }
                            OutlinedButton(
                                onClick = { onShiftJointBoundary(activeSyllable.id, 0.01) },
                                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                                modifier = Modifier.height(24.dp),
                                shape = RoundedCornerShape(4.dp),
                                border = BorderStroke(0.5.dp, palette.border)
                            ) {
                                Text("Стык +0.01с ▶", fontSize = 10.sp, color = palette.fg)
                            }
                        }
                    }
                }
            }
        }

        // Блок скоростных очередей (Bursts)
        if (spsBursts.isNotEmpty()) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 110.dp),
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = palette.panel),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
            ) {
                Column(modifier = Modifier.padding(6.dp)) {
                    Text(
                        text = "Скоростные очереди (Bursts): ${spsBursts.size}",
                        color = palette.fg,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )

                    val scrollBursts = rememberScrollState()
                    Row(
                        modifier = Modifier.horizontalScroll(scrollBursts),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        spsBursts.forEach { burst ->
                            val isSelected = burst.id == selectedBurstId
                            Surface(
                                onClick = { onSelectBurst(burst) },
                                shape = RoundedCornerShape(6.dp),
                                color = if (isSelected) palette.accent.copy(alpha = 0.2f) else palette.raised,
                                border = BorderStroke(
                                    1.dp,
                                    if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f)
                                ),
                                modifier = Modifier.width(180.dp)
                            ) {
                                Column(modifier = Modifier.padding(6.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text(
                                            text = "Пик: ${burst.peakSps}",
                                            color = if (burst.peakSps >= 7.5) palette.danger else palette.warning,
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            text = formatTime(burst.start),
                                            color = palette.muted,
                                            fontSize = 9.sp
                                        )
                                    }
                                    Text(
                                        text = burst.text,
                                        color = palette.fg,
                                        fontSize = 10.sp,
                                        maxLines = 1,
                                        modifier = Modifier.padding(top = 2.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TrimButton(
    label: String,
    palette: KaraokeThemePalette,
    isAccent: Boolean = false,
    onClick: () -> Unit
) {
    OutlinedButton(
        onClick = onClick,
        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 0.dp),
        modifier = Modifier.height(24.dp),
        shape = RoundedCornerShape(4.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = if (isAccent) palette.accent else palette.fg
        ),
        border = BorderStroke(
            1.dp,
            if (isAccent) palette.accent.copy(alpha = 0.7f) else palette.border.copy(alpha = 0.5f)
        )
    ) {
        Text(
            text = label,
            fontSize = 10.sp,
            fontWeight = if (isAccent) FontWeight.Bold else FontWeight.Normal
        )
    }
}

/**
 * Отрисовка интерактивного графика артикуляционной скорости (SPS).
 */
@Composable
fun SpsGraphView(
    points: List<SpsPoint>,
    peakSps: Double,
    meanSps: Double,
    duration: Double,
    playbackPosition: Double,
    scrollOffset: Float,
    zoomLevel: Float,
    palette: KaraokeThemePalette,
    onSeek: (Double) -> Unit,
    modifier: Modifier = Modifier
) {
    val pps = 50f * zoomLevel

    Canvas(
        modifier = modifier
            .pointerInput(duration, scrollOffset, zoomLevel) {
                detectTapGestures { tapOffset ->
                    if (pps > 0) {
                        val targetTime = ((tapOffset.x + scrollOffset) / pps).toDouble()
                        onSeek(targetTime.coerceIn(0.0, duration))
                    }
                }
            }
    ) {
        val w = size.width
        val h = size.height
        if (w <= 0 || h <= 0) return@Canvas

        val maxY = max(10.0, peakSps * 1.25).toFloat()

        // Сетка уровней скорости (3, 6, 9 SPS)
        val levels = listOf(3f, 6f, 9f)
        for (lvl in levels) {
            val y = h - (lvl / maxY) * h
            drawLine(
                color = if (lvl == 6f) palette.danger.copy(alpha = 0.4f) else palette.border.copy(alpha = 0.25f),
                start = Offset(0f, y),
                end = Offset(w, y),
                strokeWidth = if (lvl == 6f) 1.2.dp.toPx() else 0.8.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 4f), 0f)
            )
        }

        // Линия среднего SPS
        if (meanSps > 0) {
            val meanY = h - (meanSps.toFloat() / maxY) * h
            drawLine(
                color = palette.accent.copy(alpha = 0.5f),
                start = Offset(0f, meanY),
                end = Offset(w, meanY),
                strokeWidth = 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 4f), 0f)
            )
        }

        if (points.isNotEmpty()) {
            val curvePath = Path()
            val fillPath = Path()

            var started = false
            var firstX = 0f
            var lastX = 0f

            for (p in points) {
                val x = (p.time.toFloat() * pps) - scrollOffset
                if (x < -50f || x > w + 50f) continue

                val y = (h - (p.speed.toFloat() / maxY) * h).coerceIn(4f, h - 2f)

                if (!started) {
                    curvePath.moveTo(x, y)
                    fillPath.moveTo(x, h)
                    fillPath.lineTo(x, y)
                    firstX = x
                    started = true
                } else {
                    curvePath.lineTo(x, y)
                    fillPath.lineTo(x, y)
                }
                lastX = x
            }

            if (started) {
                fillPath.lineTo(lastX, h)
                fillPath.close()

                // Заливка под графиком
                drawPath(
                    path = fillPath,
                    color = palette.accent.copy(alpha = 0.18f)
                )

                // Линия графика
                drawPath(
                    path = curvePath,
                    color = palette.accent,
                    style = Stroke(width = 2.dp.toPx())
                )
            }
        }

        // Плейхед воспроизведения
        val playheadX = (playbackPosition.toFloat() * pps) - scrollOffset
        if (playheadX in 0f..w) {
            drawLine(
                color = Color.White,
                start = Offset(playheadX, 0f),
                end = Offset(playheadX, h),
                strokeWidth = 2.dp.toPx()
            )
            // Маркер на верху плейхеда
            drawCircle(
                color = palette.accent,
                radius = 3.5.dp.toPx(),
                center = Offset(playheadX, 3.5.dp.toPx())
            )
        }
    }
}
