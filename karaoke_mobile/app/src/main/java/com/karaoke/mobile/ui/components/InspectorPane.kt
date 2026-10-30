package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Значок вертикальной двусторонней стрелки ↕ с индикацией сохранения тона (перечёркнута).
 */
@Composable
fun PitchArrowIcon(
    preservePitch: Boolean,
    tint: Color,
    modifier: Modifier = Modifier
) {
    androidx.compose.foundation.Canvas(modifier = modifier.size(10.dp, 16.dp)) {
        val w = size.width
        val h = size.height
        val midX = w / 2f

        // Верхняя стрелка
        val topPath = androidx.compose.ui.graphics.Path().apply {
            moveTo(midX, 1f)
            lineTo(midX - 3.5f, 5f)
            lineTo(midX + 3.5f, 5f)
            close()
        }
        drawPath(topPath, color = tint)

        // Линия по центру
        drawLine(
            color = tint,
            start = Offset(midX, 4f),
            end = Offset(midX, h - 4f),
            strokeWidth = 1.8f
        )

        // Нижняя стрелка
        val bottomPath = androidx.compose.ui.graphics.Path().apply {
            moveTo(midX, h - 1f)
            lineTo(midX - 3.5f, h - 5f)
            lineTo(midX + 3.5f, h - 5f)
            close()
        }
        drawPath(bottomPath, color = tint)

        // Если сохранение тона включено -> перечёркиваем диагональной красной чертой
        if (preservePitch) {
            drawLine(
                color = Color(0xFFFF4855),
                start = Offset(0f, h - 1f),
                end = Offset(w, 1f),
                strokeWidth = 2.0f
            )
        }
    }
}

/**
 * Ультракомпактная панель управления плеером и редактированием.
 */
@Composable
fun InspectorPane(
    isPlaying: Boolean,
    playbackPosition: Double,
    playbackSpeed: Float,
    preservePitch: Boolean = true,
    returnToStart: Boolean = true,
    duration: Double,
    selectedCount: Int,
    canUndo: Boolean,
    canRedo: Boolean,
    palette: KaraokeThemePalette,
    activeTagType: KaraokeTagType = KaraokeTagType.K,
    onPlayPause: () -> Unit,
    onStop: () -> Unit,
    onSeek: (Double) -> Unit,
    onShowSpeedDialog: () -> Unit,
    onToggleReturnToStart: () -> Unit,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSplit: () -> Unit,
    onMerge: () -> Unit,
    onInsert: () -> Unit,
    onSetTagType: (KaraokeTagType) -> Unit,
    onShowSettings: () -> Unit,
    onShowExport: () -> Unit,
    onShowImport: () -> Unit,
    onOpenProjects: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(palette.panel)
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp)
    ) {
        // 1. Компактный транспорт (Play/Pause, Stop, Возврат к старту, Slider, Time, Speed)
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

        HorizontalDivider(color = palette.border.copy(alpha = 0.25f), thickness = 0.5.dp)

        // 2. Инструменты редактирования (Undo, Redo, Разделить, Объединить, + Слог)
        CompactEditingToolbar(
            canUndo = canUndo,
            canRedo = canRedo,
            selectedCount = selectedCount,
            palette = palette,
            onUndo = onUndo,
            onRedo = onRedo,
            onSplit = onSplit,
            onMerge = onMerge,
            onInsert = onInsert
        )

        HorizontalDivider(color = palette.border.copy(alpha = 0.25f), thickness = 0.5.dp)

        // 3. Файловые операции и меню "Тип" (вместо "Тема", со скрытым выбором тега)
        CompactFileToolbar(
            palette = palette,
            activeTagType = activeTagType,
            hasSelection = selectedCount > 0,
            onSetTagType = onSetTagType,
            onShowSettings = onShowSettings,
            onShowExport = onShowExport,
            onShowImport = onShowImport,
            onOpenProjects = onOpenProjects
        )
    }
}

@Composable
private fun CompactTransportBar(
    isPlaying: Boolean,
    playbackPosition: Double,
    duration: Double,
    playbackSpeed: Float,
    preservePitch: Boolean,
    returnToStart: Boolean,
    palette: KaraokeThemePalette,
    onPlayPause: () -> Unit,
    onStop: () -> Unit,
    onSeek: (Double) -> Unit,
    onShowSpeedDialog: () -> Unit,
    onToggleReturnToStart: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(32.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // Play / Pause
        FilledIconButton(
            onClick = onPlayPause,
            colors = IconButtonDefaults.filledIconButtonColors(
                containerColor = palette.accent,
                contentColor = palette.accentFg
            ),
            modifier = Modifier.size(30.dp)
        ) {
            Icon(
                if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                contentDescription = if (isPlaying) "Pause" else "Play",
                tint = palette.accentFg,
                modifier = Modifier.size(16.dp)
            )
        }

        // Stop
        IconButton(
            onClick = onStop,
            modifier = Modifier.size(26.dp)
        ) {
            Icon(
                Icons.Default.Stop,
                contentDescription = "Stop",
                tint = palette.fg,
                modifier = Modifier.size(16.dp)
            )
        }

        // Кнопка-переключатель "Возврат к старту"
        Surface(
            onClick = onToggleReturnToStart,
            shape = RoundedCornerShape(4.dp),
            color = if (returnToStart) palette.accent.copy(alpha = 0.2f) else palette.raised,
            border = BorderStroke(1.dp, if (returnToStart) palette.accent else palette.border.copy(alpha = 0.4f)),
            modifier = Modifier.height(26.dp)
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Replay,
                    contentDescription = "Возврат к старту",
                    tint = if (returnToStart) palette.accent else palette.muted,
                    modifier = Modifier.size(12.dp)
                )
                Text(
                    text = "Возвр",
                    color = if (returnToStart) palette.accent else palette.muted,
                    fontSize = 9.sp,
                    fontWeight = if (returnToStart) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal
                )
            }
        }

        // Слайдер
        Slider(
            value = playbackPosition.toFloat().coerceIn(0f, duration.toFloat().coerceAtLeast(0.001f)),
            onValueChange = { onSeek(it.toDouble()) },
            valueRange = 0f..duration.toFloat().coerceAtLeast(1f),
            colors = SliderDefaults.colors(
                thumbColor = palette.accent,
                activeTrackColor = palette.accent,
                inactiveTrackColor = palette.raised,
                activeTickColor = palette.accentAlt,
                inactiveTickColor = palette.border
            ),
            modifier = Modifier
                .weight(1f)
                .height(24.dp)
        )

        // Время (текущее / общее)
        Text(
            text = "${formatTime(playbackPosition)} / ${formatTime(duration)}",
            color = palette.muted,
            fontSize = 10.sp,
            maxLines = 1
        )

        // Кнопка вызова окна скорости со значком сохранения тона (двусторонняя стрелка ↕)
        OutlinedButton(
            onClick = onShowSpeedDialog,
            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 1.dp),
            modifier = Modifier.height(26.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.accent),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            PitchArrowIcon(preservePitch = preservePitch, tint = palette.accent)
            Spacer(modifier = Modifier.width(3.dp))
            Text("${playbackSpeed}x", fontSize = 10.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
        }
    }
}

@Composable
private fun CompactEditingToolbar(
    canUndo: Boolean,
    canRedo: Boolean,
    selectedCount: Int,
    palette: KaraokeThemePalette,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSplit: () -> Unit,
    onMerge: () -> Unit,
    onInsert: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Undo
        OutlinedButton(
            onClick = onUndo,
            enabled = canUndo,
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
            modifier = Modifier.height(26.dp),
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = palette.fg,
                disabledContentColor = palette.muted.copy(alpha = 0.35f)
            ),
            border = BorderStroke(1.dp, if (canUndo) palette.border else palette.border.copy(alpha = 0.2f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Icon(Icons.Default.Undo, contentDescription = "Undo", modifier = Modifier.size(13.dp))
        }

        // Redo
        OutlinedButton(
            onClick = onRedo,
            enabled = canRedo,
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
            modifier = Modifier.height(26.dp),
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = palette.fg,
                disabledContentColor = palette.muted.copy(alpha = 0.35f)
            ),
            border = BorderStroke(1.dp, if (canRedo) palette.border else palette.border.copy(alpha = 0.2f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Icon(Icons.Default.Redo, contentDescription = "Redo", modifier = Modifier.size(13.dp))
        }

        // Разделить
        Button(
            onClick = onSplit,
            enabled = selectedCount == 1,
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
            modifier = Modifier
                .weight(1f)
                .height(26.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = palette.raised,
                contentColor = palette.fg,
                disabledContainerColor = palette.raised.copy(alpha = 0.3f),
                disabledContentColor = palette.muted.copy(alpha = 0.35f)
            ),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Text("Разделить", fontSize = 11.sp)
        }

        // Объединить
        Button(
            onClick = onMerge,
            enabled = selectedCount >= 2,
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
            modifier = Modifier
                .weight(1f)
                .height(26.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = palette.raised,
                contentColor = palette.fg,
                disabledContainerColor = palette.raised.copy(alpha = 0.3f),
                disabledContentColor = palette.muted.copy(alpha = 0.35f)
            ),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Text("Объединить", fontSize = 11.sp)
        }

        // Вставить
        Button(
            onClick = onInsert,
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
            modifier = Modifier
                .weight(1f)
                .height(26.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = palette.raised,
                contentColor = palette.fg
            ),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Text("+ Слог", fontSize = 11.sp)
        }
    }
}

@Composable
private fun CompactFileToolbar(
    palette: KaraokeThemePalette,
    activeTagType: KaraokeTagType,
    hasSelection: Boolean,
    onSetTagType: (KaraokeTagType) -> Unit,
    onShowSettings: () -> Unit,
    onShowExport: () -> Unit,
    onShowImport: () -> Unit,
    onOpenProjects: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        CompactActionButton(
            icon = Icons.Default.FolderOpen,
            label = "Проекты",
            palette = palette,
            onClick = onOpenProjects,
            modifier = Modifier.weight(1f)
        )
        CompactActionButton(
            icon = Icons.Default.Download,
            label = "Импорт",
            palette = palette,
            onClick = onShowImport,
            modifier = Modifier.weight(1f)
        )
        CompactActionButton(
            icon = Icons.Default.Upload,
            label = "Экспорт",
            palette = palette,
            onClick = onShowExport,
            modifier = Modifier.weight(1f)
        )

        // Кнопка "Тип" с выпадающим меню тегов караоке (заменила кнопку "Тема")
        var tagMenuExpanded by remember { mutableStateOf(false) }
        val currentTagLabel = when (activeTagType) {
            KaraokeTagType.K -> "\\k"
            KaraokeTagType.KF -> "\\kf"
            KaraokeTagType.KO -> "\\ko"
            KaraokeTagType.K_CAPITAL -> "\\K"
        }

        Box(modifier = Modifier.weight(1f)) {
            OutlinedButton(
                onClick = { tagMenuExpanded = true },
                contentPadding = PaddingValues(horizontal = 2.dp, vertical = 2.dp),
                modifier = Modifier.fillMaxWidth().height(26.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = if (hasSelection) palette.accent.copy(alpha = 0.15f) else Color.Transparent,
                    contentColor = if (hasSelection) palette.accent else palette.fg
                ),
                border = BorderStroke(1.dp, if (hasSelection) palette.accent else palette.border.copy(alpha = 0.6f)),
                shape = RoundedCornerShape(4.dp)
            ) {
                Icon(Icons.Default.Style, contentDescription = "Тип", modifier = Modifier.size(12.dp), tint = palette.accent)
                Spacer(modifier = Modifier.width(2.dp))
                Text("Тип: $currentTagLabel", fontSize = 10.sp, maxLines = 1)
            }

            DropdownMenu(
                expanded = tagMenuExpanded,
                onDismissRequest = { tagMenuExpanded = false },
                modifier = Modifier.background(palette.panel)
            ) {
                listOf(
                    KaraokeTagType.K to "\\k — Обычный (дискретный)",
                    KaraokeTagType.KF to "\\kf — Плавный (fill)",
                    KaraokeTagType.KO to "\\ko — Контурный (outline)",
                    KaraokeTagType.K_CAPITAL to "\\K — Заглавный (перелив)"
                ).forEach { (tag, desc) ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                text = desc,
                                color = if (tag == activeTagType) palette.accent else palette.fg,
                                fontWeight = if (tag == activeTagType) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal,
                                fontSize = 12.sp
                            )
                        },
                        onClick = {
                            onSetTagType(tag)
                            tagMenuExpanded = false
                        }
                    )
                }
            }
        }

        CompactActionButton(
            icon = Icons.Default.Settings,
            label = "Опции",
            palette = palette,
            onClick = onShowSettings,
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun CompactActionButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    palette: KaraokeThemePalette,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        contentPadding = PaddingValues(horizontal = 2.dp, vertical = 2.dp),
        modifier = modifier.height(26.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = Color.Transparent,
            contentColor = palette.fg
        ),
        border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
        shape = RoundedCornerShape(4.dp)
    ) {
        Icon(icon, contentDescription = label, modifier = Modifier.size(12.dp), tint = palette.accent)
        Spacer(modifier = Modifier.width(3.dp))
        Text(label, fontSize = 10.sp, maxLines = 1)
    }
}
