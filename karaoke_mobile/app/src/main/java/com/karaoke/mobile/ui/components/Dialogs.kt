package com.karaoke.mobile.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.window.Dialog
import com.karaoke.mobile.model.KaraokeProject
import com.karaoke.mobile.ui.theme.*

/**
 * Диалог выбора темы
 */
@Composable
fun ThemePickerDialog(
    currentTheme: KaraokeThemePalette,
    onThemeSelected: (KaraokeThemePalette) -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = currentTheme.panel)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "Выбор темы",
                    color = currentTheme.fg,
                    fontSize = 20.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(allThemes) { theme ->
                        ThemeItem(
                            theme = theme,
                            isSelected = theme.name == currentTheme.name,
                            onClick = { onThemeSelected(theme) }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("Закрыть", color = currentTheme.accent)
                }
            }
        }
    }
}

@Composable
private fun ThemeItem(
    theme: KaraokeThemePalette,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(if (isSelected) theme.accent.copy(alpha = 0.15f) else theme.raised)
            .clickable(onClick = onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Превью цветов
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Box(modifier = Modifier.size(24.dp).clip(RoundedCornerShape(4.dp)).background(theme.bg))
            Box(modifier = Modifier.size(24.dp).clip(RoundedCornerShape(4.dp)).background(theme.panel))
            Box(modifier = Modifier.size(24.dp).clip(RoundedCornerShape(4.dp)).background(theme.accent))
        }

        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = theme.name.replace("_", " ").replaceFirstChar { it.uppercase() },
                color = theme.fg,
                fontSize = 14.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium
            )
            Text(
                text = if (theme.isDark) "Тёмная" else "Светлая",
                color = theme.muted,
                fontSize = 12.sp
            )
        }

        if (isSelected) {
            Text("✓", color = theme.accent, fontSize = 18.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        }
    }
}

/**
 * Диалог экспорта/импорта
 */
@Composable
fun ExportImportDialog(
    isExport: Boolean,
    palette: KaraokeThemePalette,
    onExportProject: () -> Unit,
    onExportAss: () -> Unit,
    onImportProject: () -> Unit,
    onImportAss: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = if (isExport) "Экспорт" else "Импорт",
                    color = palette.fg,
                    fontSize = 20.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                if (isExport) {
                    ExportOptions(
                        palette = palette,
                        onExportProject = onExportProject,
                        onExportAss = onExportAss
                    )
                } else {
                    ImportOptions(
                        palette = palette,
                        onImportProject = onImportProject,
                        onImportAss = onImportAss
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("Отмена", color = palette.accent)
                }
            }
        }
    }
}

@Composable
private fun ExportOptions(
    palette: KaraokeThemePalette,
    onExportProject: () -> Unit,
    onExportAss: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onExportProject),
            colors = CardDefaults.cardColors(containerColor = palette.raised)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Проект (.zip)", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Включая ASS, медиа и настройки", color = palette.muted, fontSize = 12.sp)
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onExportAss),
            colors = CardDefaults.cardColors(containerColor = palette.raised)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("ASS-файл", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Только субтитры", color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun ImportOptions(
    palette: KaraokeThemePalette,
    onImportProject: () -> Unit,
    onImportAss: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onImportProject),
            colors = CardDefaults.cardColors(containerColor = palette.raised)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Проект (.zip)", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Импортировать полный проект", color = palette.muted, fontSize = 12.sp)
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onImportAss),
            colors = CardDefaults.cardColors(containerColor = palette.raised)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("ASS-файл", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Импортировать только субтитры", color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}

/**
 * Диалог редактирования тайминга
 */
@Composable
fun TimingEditorDialog(
    start: Double,
    end: Double,
    palette: KaraokeThemePalette,
    onStartChange: (Double) -> Unit,
    onEndChange: (Double) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "Редактирование тайминга",
                    color = palette.fg,
                    fontSize = 20.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                // Start
                Text("Начало: ${formatTime(start)}", color = palette.muted, fontSize = 12.sp)
                Slider(
                    value = start.toFloat(),
                    onValueChange = { onStartChange(it.toDouble()) },
                    valueRange = 0f..(end - 0.05).toFloat().coerceAtLeast(0f),
                    colors = SliderDefaults.colors(
                        thumbColor = palette.accent,
                        activeTrackColor = palette.accent,
                        inactiveTrackColor = palette.raised
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                // End
                Text("Конец: ${formatTime(end)}", color = palette.muted, fontSize = 12.sp)
                Slider(
                    value = end.toFloat(),
                    onValueChange = { onEndChange(it.toDouble()) },
                    valueRange = (start + 0.05).toFloat()..300f,
                    colors = SliderDefaults.colors(
                        thumbColor = palette.accent,
                        activeTrackColor = palette.accent,
                        inactiveTrackColor = palette.raised
                    )
                )

                Spacer(modifier = Modifier.height(12.dp))

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) {
                        Text("Отмена", color = palette.muted)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = onConfirm,
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent)
                    ) {
                        Text("Применить", color = palette.accentFg)
                    }
                }
            }
        }
    }
}

/**
 * Toast / Snackbar для сообщений
 */
@Composable
fun MessageSnackbar(
    message: String?,
    isError: Boolean,
    palette: KaraokeThemePalette,
    onDismiss: () -> Unit
) {
    message?.let { msg ->
        val bgColor = if (isError) palette.danger.copy(alpha = 0.9f) else palette.success.copy(alpha = 0.9f)
        val textColor = if (isError) Color.White else Color.Black

        LaunchedEffect(msg) {
            kotlinx.coroutines.delay(2500)
            onDismiss()
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(bgColor)
                .padding(12.dp)
        ) {
            Text(
                text = msg,
                color = textColor,
                fontSize = 14.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium
            )
        }
    }
}
