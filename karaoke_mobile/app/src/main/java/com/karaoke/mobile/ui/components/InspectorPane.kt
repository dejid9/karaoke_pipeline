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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Компактная панель управления плеером и инструментами редактирования.
 */
@Composable
fun InspectorPane(
    isPlaying: Boolean,
    playbackPosition: Double,
    playbackSpeed: Float,
    duration: Double,
    selectedCount: Int,
    canUndo: Boolean,
    canRedo: Boolean,
    palette: KaraokeThemePalette,
    activeTagType: KaraokeTagType? = null,
    isCurrentUnspoken: Boolean = false,
    onPlayPause: () -> Unit,
    onStop: () -> Unit,
    onSeek: (Double) -> Unit,
    onSpeedChange: (Float) -> Unit,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSplit: () -> Unit,
    onMerge: () -> Unit,
    onInsert: () -> Unit,
    onSetTagType: (KaraokeTagType) -> Unit,
    onToggleUnspoken: () -> Unit,
    onShowSettings: () -> Unit,
    onShowThemes: () -> Unit,
    onShowExport: () -> Unit,
    onShowImport: () -> Unit,
    onOpenProjects: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(palette.panel)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // 1. Компактный транспорт (плей, стоп, таймлайн, время, скорость)
        CompactTransportBar(
            isPlaying = isPlaying,
            playbackPosition = playbackPosition,
            duration = duration,
            playbackSpeed = playbackSpeed,
            palette = palette,
            onPlayPause = onPlayPause,
            onStop = onStop,
            onSeek = onSeek,
            onSpeedChange = onSpeedChange
        )

        HorizontalDivider(color = palette.border.copy(alpha = 0.25f), thickness = 0.5.dp)

        // 2. Инструменты редактирования (действия со слогами + теги и Непропетое в одной строке)
        CompactEditingToolbar(
            canUndo = canUndo,
            canRedo = canRedo,
            selectedCount = selectedCount,
            activeTagType = activeTagType,
            isCurrentUnspoken = isCurrentUnspoken,
            palette = palette,
            onUndo = onUndo,
            onRedo = onRedo,
            onSplit = onSplit,
            onMerge = onMerge,
            onInsert = onInsert,
            onSetTagType = onSetTagType,
            onToggleUnspoken = onToggleUnspoken
        )

        HorizontalDivider(color = palette.border.copy(alpha = 0.25f), thickness = 0.5.dp)

        // 3. Файловые операции и настройки (все 5 кнопок в одну аккуратную строку)
        CompactFileToolbar(
            palette = palette,
            onShowSettings = onShowSettings,
            onShowThemes = onShowThemes,
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
    palette: KaraokeThemePalette,
    onPlayPause: () -> Unit,
    onStop: () -> Unit,
    onSeek: (Double) -> Unit,
    onSpeedChange: (Float) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(34.dp),
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
            modifier = Modifier.size(32.dp)
        ) {
            Icon(
                if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                contentDescription = if (isPlaying) "Pause" else "Play",
                tint = palette.accentFg,
                modifier = Modifier.size(18.dp)
            )
        }

        // Stop
        IconButton(
            onClick = onStop,
            modifier = Modifier.size(28.dp)
        ) {
            Icon(
                Icons.Default.Stop,
                contentDescription = "Stop",
                tint = palette.fg,
                modifier = Modifier.size(18.dp)
            )
        }

        // Компактный слайдер
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

        // Меню выбора скорости
        var speedMenuExpanded by remember { mutableStateOf(false) }
        Box {
            OutlinedButton(
                onClick = { speedMenuExpanded = true },
                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                modifier = Modifier.height(26.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.accent),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                shape = RoundedCornerShape(4.dp)
            ) {
                Text("${playbackSpeed}x", fontSize = 10.sp)
            }
            DropdownMenu(
                expanded = speedMenuExpanded,
                onDismissRequest = { speedMenuExpanded = false },
                modifier = Modifier.background(palette.panel)
            ) {
                listOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f).forEach { speed ->
                    DropdownMenuItem(
                        text = { Text("${speed}x", color = palette.fg, fontSize = 12.sp) },
                        onClick = {
                            onSpeedChange(speed)
                            speedMenuExpanded = false
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun CompactEditingToolbar(
    canUndo: Boolean,
    canRedo: Boolean,
    selectedCount: Int,
    activeTagType: KaraokeTagType?,
    isCurrentUnspoken: Boolean,
    palette: KaraokeThemePalette,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSplit: () -> Unit,
    onMerge: () -> Unit,
    onInsert: () -> Unit,
    onSetTagType: (KaraokeTagType) -> Unit,
    onToggleUnspoken: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        // Строка 1: Undo, Redo, Разделить, Объединить, Вставить
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
                modifier = Modifier.height(28.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = palette.fg,
                    disabledContentColor = palette.muted.copy(alpha = 0.35f)
                ),
                border = BorderStroke(1.dp, if (canUndo) palette.border else palette.border.copy(alpha = 0.2f)),
                shape = RoundedCornerShape(4.dp)
            ) {
                Icon(Icons.Default.Undo, contentDescription = "Undo", modifier = Modifier.size(14.dp))
            }

            // Redo
            OutlinedButton(
                onClick = onRedo,
                enabled = canRedo,
                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                modifier = Modifier.height(28.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = palette.fg,
                    disabledContentColor = palette.muted.copy(alpha = 0.35f)
                ),
                border = BorderStroke(1.dp, if (canRedo) palette.border else palette.border.copy(alpha = 0.2f)),
                shape = RoundedCornerShape(4.dp)
            ) {
                Icon(Icons.Default.Redo, contentDescription = "Redo", modifier = Modifier.size(14.dp))
            }

            // Разделить
            Button(
                onClick = onSplit,
                enabled = selectedCount == 1,
                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                modifier = Modifier
                    .weight(1f)
                    .height(28.dp),
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
                    .height(28.dp),
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
                    .height(28.dp),
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

        // Строка 2: Теги (\k, \kf, \ko, \K) И Непропетое В ОДНОЙ СТРОКЕ (экономит вертикальное место)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            KaraokeTagType.entries.forEach { tagType ->
                val label = when (tagType) {
                    KaraokeTagType.K -> "\\k"
                    KaraokeTagType.KF -> "\\kf"
                    KaraokeTagType.KO -> "\\ko"
                    KaraokeTagType.K_CAPITAL -> "\\K"
                }
                val isTagActive = (selectedCount > 0 && activeTagType == tagType)
                OutlinedButton(
                    onClick = { onSetTagType(tagType) },
                    enabled = selectedCount > 0,
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 2.dp),
                    modifier = Modifier
                        .weight(1f)
                        .height(28.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = if (isTagActive) palette.accent else Color.Transparent,
                        contentColor = if (isTagActive) palette.accentFg else palette.accent,
                        disabledContentColor = palette.muted.copy(alpha = 0.35f)
                    ),
                    border = BorderStroke(
                        1.dp,
                        if (isTagActive) palette.accentAlt else palette.border.copy(alpha = 0.6f)
                    ),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(label, fontSize = 11.sp, fontWeight = if (isTagActive) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal)
                }
            }

            // Непропетое на этой же строке
            val isUnspokenActive = selectedCount > 0 && isCurrentUnspoken
            OutlinedButton(
                onClick = onToggleUnspoken,
                enabled = selectedCount > 0,
                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                modifier = Modifier
                    .weight(1.8f)
                    .height(28.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = if (isUnspokenActive) palette.warning else Color.Transparent,
                    contentColor = if (isUnspokenActive) Color.White else palette.muted,
                    disabledContentColor = palette.muted.copy(alpha = 0.35f)
                ),
                border = BorderStroke(
                    1.dp,
                    if (isUnspokenActive) palette.warning else palette.border.copy(alpha = 0.6f)
                ),
                shape = RoundedCornerShape(4.dp)
            ) {
                Icon(
                    Icons.Default.VolumeOff,
                    contentDescription = "Unspoken",
                    modifier = Modifier.size(13.dp)
                )
                Spacer(modifier = Modifier.width(3.dp))
                Text(
                    "Непропетое",
                    fontSize = 10.sp,
                    maxLines = 1
                )
            }
        }
    }
}

@Composable
private fun CompactFileToolbar(
    palette: KaraokeThemePalette,
    onShowSettings: () -> Unit,
    onShowThemes: () -> Unit,
    onShowExport: () -> Unit,
    onShowImport: () -> Unit,
    onOpenProjects: () -> Unit
) {
    // Единая компактная строка для всех 5 действий: Проекты, Импорт, Экспорт, Тема, Настройки
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
        CompactActionButton(
            icon = Icons.Default.Palette,
            label = "Тема",
            palette = palette,
            onClick = onShowThemes,
            modifier = Modifier.weight(1f)
        )
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
        modifier = modifier.height(28.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = Color.Transparent,
            contentColor = palette.fg
        ),
        border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
        shape = RoundedCornerShape(4.dp)
    ) {
        Icon(icon, contentDescription = label, modifier = Modifier.size(13.dp), tint = palette.accent)
        Spacer(modifier = Modifier.width(3.dp))
        Text(label, fontSize = 10.sp, maxLines = 1)
    }
}
