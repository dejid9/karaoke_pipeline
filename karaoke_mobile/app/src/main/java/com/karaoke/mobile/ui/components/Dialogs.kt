package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.window.Dialog
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.*
import com.karaoke.mobile.viewmodel.ProjectSummary
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Диалог настроек редактора
 */
@Composable
fun SettingsDialog(
    autoScroll: Boolean,
    defaultTagType: KaraokeTagType,
    palette: KaraokeThemePalette,
    onToggleAutoScroll: () -> Unit,
    onSetDefaultTagType: (KaraokeTagType) -> Unit,
    onOpenThemes: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f))
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Настройки",
                        color = palette.fg,
                        fontSize = 18.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = palette.muted)
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Автоскролл таймлайна
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Автоскролл таймлайна",
                            color = palette.fg,
                            fontSize = 14.sp,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.Medium
                        )
                        Text(
                            text = "Следовать за курсором при воспроизведении",
                            color = palette.muted,
                            fontSize = 11.sp
                        )
                    }
                    Switch(
                        checked = autoScroll,
                        onCheckedChange = { onToggleAutoScroll() },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = palette.accentFg,
                            checkedTrackColor = palette.accent,
                            uncheckedThumbColor = palette.muted,
                            uncheckedTrackColor = palette.raised
                        )
                    )
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp), color = palette.border.copy(alpha = 0.3f))

                // Дефолтный тег караоке
                Text(
                    text = "Тег по умолчанию для новых слогов",
                    color = palette.fg,
                    fontSize = 14.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Medium
                )
                Spacer(modifier = Modifier.height(6.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    KaraokeTagType.entries.forEach { tagType ->
                        val isSelected = tagType == defaultTagType
                        val label = when (tagType) {
                            KaraokeTagType.K -> "\\k"
                            KaraokeTagType.KF -> "\\kf"
                            KaraokeTagType.KO -> "\\ko"
                            KaraokeTagType.K_CAPITAL -> "\\K"
                        }
                        Button(
                            onClick = { onSetDefaultTagType(tagType) },
                            modifier = Modifier.weight(1f).height(32.dp),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 2.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isSelected) palette.accent else palette.raised,
                                contentColor = if (isSelected) palette.accentFg else palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accentAlt else palette.border.copy(alpha = 0.5f)),
                            shape = RoundedCornerShape(6.dp)
                        ) {
                            Text(label, fontSize = 12.sp, fontWeight = if (isSelected) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal)
                        }
                    }
                }

                HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp), color = palette.border.copy(alpha = 0.3f))

                // Выбор темы оформления
                OutlinedButton(
                    onClick = onOpenThemes,
                    modifier = Modifier.fillMaxWidth().height(38.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = Color.Transparent,
                        contentColor = palette.fg
                    ),
                    border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(6.dp)
                ) {
                    Icon(Icons.Default.Palette, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Сменить цветовую тему (${palette.name})", fontSize = 12.sp)
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Информация о приложении
                Text(
                    text = "Karaoke Mobile Studio • v1.0",
                    color = palette.muted.copy(alpha = 0.7f),
                    fontSize = 11.sp,
                    modifier = Modifier.align(Alignment.CenterHorizontally)
                )

                Spacer(modifier = Modifier.height(8.dp))

                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("Закрыть", color = palette.accent, fontSize = 13.sp)
                }
            }
        }
    }
}

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
            colors = CardDefaults.cardColors(containerColor = currentTheme.panel),
            border = BorderStroke(1.dp, currentTheme.border.copy(alpha = 0.6f))
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
            .background(if (isSelected) theme.accent.copy(alpha = 0.2f) else theme.raised)
            .border(
                BorderStroke(
                    1.dp,
                    if (isSelected) theme.accent else theme.border.copy(alpha = 0.3f)
                ),
                shape = RoundedCornerShape(8.dp)
            )
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
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f))
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
            colors = CardDefaults.cardColors(containerColor = palette.raised),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.4f))
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text("Проект (.zip)", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Включая ASS, медиа и настройки", color = palette.muted, fontSize = 12.sp)
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onExportAss),
            colors = CardDefaults.cardColors(containerColor = palette.raised),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.4f))
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
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
            colors = CardDefaults.cardColors(containerColor = palette.raised),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.4f))
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text("Проект (.zip)", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Импортировать полный проект", color = palette.muted, fontSize = 12.sp)
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onImportAss),
            colors = CardDefaults.cardColors(containerColor = palette.raised),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.4f))
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text("ASS-файл", color = palette.fg, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                Text("Импортировать только субтитры", color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}

/**
 * Оверлей редактирования тайминга (в формате нижней панели без модального окна).
 * Каждое изменение сохраняется мгновенно без подтверждения кнопкой.
 */
@Composable
fun TimingEditorDock(
    syllableText: String,
    start: Double,
    end: Double,
    maxDuration: Double,
    palette: KaraokeThemePalette,
    onTimingChange: (Double, Double) -> Unit,
    onPreview: (Int, Int) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 6.dp, vertical = 2.dp),
        shape = RoundedCornerShape(topStart = 10.dp, topEnd = 10.dp, bottomStart = 6.dp, bottomEnd = 6.dp),
        colors = CardDefaults.cardColors(containerColor = palette.panel),
        border = BorderStroke(1.5.dp, palette.accent.copy(alpha = 0.8f))
    ) {
        Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
            // Верхняя строка: заголовок, длительность и кнопка закрытия
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        text = "Тайминг: «$syllableText»",
                        color = palette.fg,
                        fontSize = 12.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                        maxLines = 1
                    )
                    Text(
                        text = "(%.2f с)".format((end - start).coerceAtLeast(0.0)),
                        color = palette.accent,
                        fontSize = 11.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold
                    )
                }
                IconButton(onClick = onClose, modifier = Modifier.size(22.dp)) {
                    Icon(Icons.Default.Close, contentDescription = "Close", tint = palette.muted, modifier = Modifier.size(15.dp))
                }
            }

            Spacer(modifier = Modifier.height(3.dp))

            // Строка 1: Начало (Start)
            TimingAdjustRow(
                label = "Начало",
                value = start,
                minValue = 0.0,
                maxValue = (end - 0.01).coerceAtLeast(0.0),
                palette = palette,
                onValueChange = { onTimingChange(it, end) }
            )

            Spacer(modifier = Modifier.height(2.dp))

            // Строка 2: Конец (End)
            TimingAdjustRow(
                label = "Конец",
                value = end,
                minValue = (start + 0.01),
                maxValue = maxDuration.coerceAtLeast(start + 1.0),
                palette = palette,
                onValueChange = { onTimingChange(start, it) }
            )

            Spacer(modifier = Modifier.height(4.dp))

            // Строка 3: Прослушивание слога и соседних слогов (контекст)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Слушать:",
                    color = palette.muted,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(end = 2.dp)
                )

                // -2 слога
                OutlinedButton(
                    onClick = { onPreview(2, 0) },
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 1.dp),
                    modifier = Modifier.height(24.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                    border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text("◀ -2", fontSize = 10.sp)
                }

                // -1 слог
                OutlinedButton(
                    onClick = { onPreview(1, 0) },
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 1.dp),
                    modifier = Modifier.height(24.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                    border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text("◀ -1", fontSize = 10.sp)
                }

                // Этот слог (основная кнопка)
                Button(
                    onClick = { onPreview(0, 0) },
                    contentPadding = PaddingValues(horizontal = 6.dp, vertical = 1.dp),
                    modifier = Modifier.weight(1f).height(24.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = palette.accent, contentColor = palette.accentFg),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(13.dp))
                    Spacer(modifier = Modifier.width(2.dp))
                    Text("Этот слог", fontSize = 10.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                }

                // +1 слог
                OutlinedButton(
                    onClick = { onPreview(0, 1) },
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 1.dp),
                    modifier = Modifier.height(24.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                    border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text("+1 ▶", fontSize = 10.sp)
                }

                // +2 слога
                OutlinedButton(
                    onClick = { onPreview(0, 2) },
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 1.dp),
                    modifier = Modifier.height(24.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                    border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text("+2 ▶", fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
private fun TimingAdjustRow(
    label: String,
    value: Double,
    minValue: Double,
    maxValue: Double,
    palette: KaraokeThemePalette,
    onValueChange: (Double) -> Unit
) {
    var textInput by remember(value) { mutableStateOf("%.2f".format(value)) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "$label:",
            color = palette.fg,
            fontSize = 11.sp,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
            modifier = Modifier.width(44.dp)
        )

        // Кнопка -0.01
        OutlinedButton(
            onClick = {
                val newVal = (kotlin.math.round((value - 0.01) * 100.0) / 100.0).coerceIn(minValue, maxValue)
                onValueChange(newVal)
            },
            contentPadding = PaddingValues(horizontal = 2.dp, vertical = 0.dp),
            modifier = Modifier.height(24.dp).width(30.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.7f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Text("-", fontSize = 14.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        }

        // Поле ручного ввода
        OutlinedTextField(
            value = textInput,
            onValueChange = { str ->
                textInput = str
                val parsed = str.replace(',', '.').toDoubleOrNull()
                if (parsed != null && parsed in minValue..maxValue) {
                    onValueChange(parsed)
                }
            },
            singleLine = true,
            modifier = Modifier.width(70.dp).height(36.dp),
            textStyle = LocalTextStyle.current.copy(
                color = palette.fg,
                fontSize = 11.sp,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            ),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = palette.fg,
                unfocusedTextColor = palette.fg,
                focusedContainerColor = palette.inputBg,
                unfocusedContainerColor = palette.inputBg,
                focusedBorderColor = palette.accent,
                unfocusedBorderColor = palette.border.copy(alpha = 0.7f),
                cursorColor = palette.accent
            )
        )

        // Кнопка +0.01
        OutlinedButton(
            onClick = {
                val newVal = (kotlin.math.round((value + 0.01) * 100.0) / 100.0).coerceIn(minValue, maxValue)
                onValueChange(newVal)
            },
            contentPadding = PaddingValues(horizontal = 2.dp, vertical = 0.dp),
            modifier = Modifier.height(24.dp).width(30.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.7f)),
            shape = RoundedCornerShape(4.dp)
        ) {
            Text("+", fontSize = 14.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        }

        // Слайдер
        Slider(
            value = value.toFloat().coerceIn(minValue.toFloat(), maxValue.toFloat()),
            onValueChange = { onValueChange(it.toDouble()) },
            valueRange = minValue.toFloat()..maxValue.toFloat().coerceAtLeast(minValue.toFloat() + 0.01f),
            colors = SliderDefaults.colors(
                thumbColor = palette.accent,
                activeTrackColor = palette.accent,
                inactiveTrackColor = palette.raised
            ),
            modifier = Modifier.weight(1f).height(18.dp)
        )
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
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "Редактирование тайминга",
                    color = palette.fg,
                    fontSize = 18.sp,
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

/**
 * Диалог со списком сохранённых проектов
 */
@Composable
fun ProjectsListDialog(
    projects: List<ProjectSummary>,
    palette: KaraokeThemePalette,
    onSelectProject: (String) -> Unit,
    onDeleteProject: (String) -> Unit,
    onImportZip: () -> Unit,
    onDismiss: () -> Unit
) {
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f))
        ) {
            Column(
                modifier = Modifier
                    .padding(16.dp)
                    .fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Проекты",
                        color = palette.fg,
                        fontSize = 20.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss, modifier = Modifier.size(28.dp)) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Закрыть",
                            tint = palette.muted
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                if (projects.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "Нет сохранённых проектов",
                            color = palette.muted,
                            fontSize = 14.sp
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 280.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(projects, key = { it.id }) { proj ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(palette.raised)
                                    .border(BorderStroke(1.dp, palette.border.copy(alpha = 0.35f)), RoundedCornerShape(8.dp))
                                    .clickable { onSelectProject(proj.id) }
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = proj.name,
                                        color = palette.fg,
                                        fontSize = 14.sp,
                                        fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
                                        maxLines = 1
                                    )
                                    Text(
                                        text = dateFormat.format(Date(proj.modifiedAt)),
                                        color = palette.muted,
                                        fontSize = 11.sp
                                    )
                                }
                                IconButton(
                                    onClick = { onDeleteProject(proj.id) },
                                    modifier = Modifier.size(32.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Delete,
                                        contentDescription = "Удалить",
                                        tint = palette.danger.copy(alpha = 0.8f),
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedButton(
                        onClick = onImportZip,
                        colors = ButtonDefaults.outlinedButtonColors(
                            containerColor = Color.Transparent,
                            contentColor = palette.fg
                        ),
                        border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(16.dp), tint = palette.accent)
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Импорт ZIP", fontSize = 12.sp)
                    }
                    TextButton(onClick = onDismiss) {
                        Text("Закрыть", color = palette.accent)
                    }
                }
            }
        }
    }
}
