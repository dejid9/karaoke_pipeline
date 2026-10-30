package com.karaoke.mobile.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Панель управления плеером и инструментами редактирования.
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
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(palette.panel)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Транспорт
        TransportBar(
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

        HorizontalDivider(color = palette.border.copy(alpha = 0.3f))

        // Инструменты редактирования
        EditingToolbar(
            canUndo = canUndo,
            canRedo = canRedo,
            selectedCount = selectedCount,
            palette = palette,
            onUndo = onUndo,
            onRedo = onRedo,
            onSplit = onSplit,
            onMerge = onMerge,
            onInsert = onInsert,
            onSetTagType = onSetTagType,
            onToggleUnspoken = onToggleUnspoken
        )

        HorizontalDivider(color = palette.border.copy(alpha = 0.3f))

        // Файл и настройки
        FileToolbar(
            palette = palette,
            onShowSettings = onShowSettings,
            onShowThemes = onShowThemes,
            onShowExport = onShowExport,
            onShowImport = onShowImport
        )
    }
}

@Composable
private fun TransportBar(
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
    Column {
        // Время
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = formatTime(playbackPosition),
                color = palette.fg,
                fontSize = 14.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium
            )
            Text(
                text = formatTime(duration),
                color = palette.muted,
                fontSize = 14.sp
            )
        }

        Spacer(modifier = Modifier.height(4.dp))

        // Слайдер позиции
        Slider(
            value = playbackPosition.toFloat().coerceIn(0f, duration.toFloat()),
            onValueChange = { onSeek(it.toDouble()) },
            valueRange = 0f..duration.toFloat().coerceAtLeast(1f),
            colors = SliderDefaults.colors(
                thumbColor = palette.accent,
                activeTrackColor = palette.accent,
                inactiveTrackColor = palette.raised
            ),
            modifier = Modifier.fillMaxWidth()
        )

        // Кнопки управления
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onStop) {
                Icon(Icons.Default.Stop, contentDescription = "Stop", tint = palette.fg)
            }

            FilledIconButton(
                onClick = onPlayPause,
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = palette.accent)
            ) {
                Icon(
                    if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "Pause" else "Play",
                    tint = palette.accentFg
                )
            }

            // Скорость
            var expanded by remember { mutableStateOf(false) }
            Box {
                TextButton(onClick = { expanded = true }) {
                    Text("${playbackSpeed}x", color = palette.accent)
                }
                DropdownMenu(
                    expanded = expanded,
                    onDismissRequest = { expanded = false }
                ) {
                    listOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f).forEach { speed ->
                        DropdownMenuItem(
                            text = { Text("${speed}x") },
                            onClick = {
                                onSpeedChange(speed)
                                expanded = false
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EditingToolbar(
    canUndo: Boolean,
    canRedo: Boolean,
    selectedCount: Int,
    palette: KaraokeThemePalette,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSplit: () -> Unit,
    onMerge: () -> Unit,
    onInsert: () -> Unit,
    onSetTagType: (KaraokeTagType) -> Unit,
    onToggleUnspoken: () -> Unit
) {
    Column {
        Text(
            text = "Редактирование",
            color = palette.muted,
            fontSize = 12.sp,
            modifier = Modifier.padding(bottom = 4.dp)
        )

        // Undo/Redo
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            OutlinedButton(
                onClick = onUndo,
                enabled = canUndo,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Undo, contentDescription = "Undo", modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Undo", fontSize = 12.sp)
            }
            OutlinedButton(
                onClick = onRedo,
                enabled = canRedo,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Redo, contentDescription = "Redo", modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Redo", fontSize = 12.sp)
            }
        }

        Spacer(modifier = Modifier.height(4.dp))

        // Операции со слогами
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Button(
                onClick = onSplit,
                enabled = selectedCount == 1,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = palette.raised, contentColor = palette.fg),
                shape = RoundedCornerShape(6.dp)
            ) {
                Text("Разделить", fontSize = 11.sp)
            }
            Button(
                onClick = onMerge,
                enabled = selectedCount >= 2,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = palette.raised, contentColor = palette.fg),
                shape = RoundedCornerShape(6.dp)
            ) {
                Text("Объединить", fontSize = 11.sp)
            }
            Button(
                onClick = onInsert,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = palette.raised, contentColor = palette.fg),
                shape = RoundedCornerShape(6.dp)
            ) {
                Text("Вставить", fontSize = 11.sp)
            }
        }

        Spacer(modifier = Modifier.height(4.dp))

        // Типы тегов
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            KaraokeTagType.entries.forEach { tagType ->
                val label = when (tagType) {
                    KaraokeTagType.K -> "\\k"
                    KaraokeTagType.KF -> "\\kf"
                    KaraokeTagType.KO -> "\\ko"
                    KaraokeTagType.K_CAPITAL -> "\\K"
                }
                OutlinedButton(
                    onClick = { onSetTagType(tagType) },
                    enabled = selectedCount > 0,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.accent),
                    border = ButtonDefaults.outlinedButtonBorder.copy(brush = androidx.compose.ui.graphics.SolidColor(palette.border))
                ) {
                    Text(label, fontSize = 11.sp)
                }
            }
        }

        Spacer(modifier = Modifier.height(4.dp))

        // Непропетое
        OutlinedButton(
            onClick = onToggleUnspoken,
            enabled = selectedCount > 0,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.muted),
            border = ButtonDefaults.outlinedButtonBorder.copy(brush = androidx.compose.ui.graphics.SolidColor(palette.border))
        ) {
            Icon(Icons.Default.VolumeOff, contentDescription = "Unspoken", modifier = Modifier.size(16.dp))
            Spacer(modifier = Modifier.width(4.dp))
            Text("Непропетое", fontSize = 12.sp)
        }
    }
}

@Composable
private fun FileToolbar(
    palette: KaraokeThemePalette,
    onShowSettings: () -> Unit,
    onShowThemes: () -> Unit,
    onShowExport: () -> Unit,
    onShowImport: () -> Unit
) {
    Column {
        Text(
            text = "Файл",
            color = palette.muted,
            fontSize = 12.sp,
            modifier = Modifier.padding(bottom = 4.dp)
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            OutlinedButton(
                onClick = onShowExport,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Upload, contentDescription = "Export", modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Экспорт", fontSize = 11.sp)
            }
            OutlinedButton(
                onClick = onShowImport,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Download, contentDescription = "Import", modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Импорт", fontSize = 11.sp)
            }
        }

        Spacer(modifier = Modifier.height(4.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            OutlinedButton(
                onClick = onShowThemes,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Palette, contentDescription = "Theme", modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Тема", fontSize = 11.sp)
            }
            OutlinedButton(
                onClick = onShowSettings,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Settings, contentDescription = "Settings", modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Настройки", fontSize = 11.sp)
            }
        }
    }
}
