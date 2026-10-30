package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Вкладка «Подготовка»:
 * - Редактирование текста песни (Lyrics)
 * - Выбор языка текста
 * - Локальное офлайн-слогоразбиение
 * - Подготовка пакета для Google Colab (MFA)
 * - Импорт готового TextGrid или ASS
 */
@Composable
fun PreparationTab(
    lyricsText: String,
    language: String,
    audioLoaded: Boolean,
    audioDuration: Double,
    palette: KaraokeThemePalette,
    onLyricsChange: (String) -> Unit,
    onLanguageChange: (String) -> Unit,
    onBreakSyllablesOffline: () -> Unit,
    onBundleForColab: () -> Unit,
    onOpenColabUrl: () -> Unit,
    onPickTextGrid: () -> Unit,
    onPickAss: () -> Unit,
    modifier: Modifier = Modifier
) {
    val scrollState = rememberScrollState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(palette.bg)
            .verticalScroll(scrollState)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Шапка раздела
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = palette.accent.copy(alpha = 0.15f),
                    border = BorderStroke(1.dp, palette.accent.copy(alpha = 0.3f))
                ) {
                    Icon(
                        imageVector = Icons.Default.Description,
                        contentDescription = null,
                        tint = palette.accent,
                        modifier = Modifier.padding(8.dp).size(24.dp)
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Подготовка и выравнивание текста",
                        color = palette.fg,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Слогоразбиение, подготовка к MFA выравниванию и импорт TextGrid",
                        color = palette.muted,
                        fontSize = 11.sp
                    )
                }
            }
        }

        // Выбор языка
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "Язык текста песни",
                    color = palette.fg,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold
                )
                val langScroll = rememberScrollState()
                Row(
                    modifier = Modifier.horizontalScroll(langScroll),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val languages = listOf(
                        "ru" to "🇷🇺 Русский",
                        "en" to "🇬🇧 English",
                        "de" to "🇩🇪 Deutsch",
                        "es" to "🇪🇸 Español"
                    )
                    languages.forEach { (code, label) ->
                        val isSelected = language.equals(code, ignoreCase = true)
                        FilterChip(
                            selected = isSelected,
                            onClick = { onLanguageChange(code) },
                            label = { Text(label, fontSize = 12.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(
                                1.dp,
                                if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f)
                            )
                        )
                    }
                }
            }
        }

        // Редактор текста песни (Lyrics)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Icon(Icons.Default.EditNote, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                        Text(
                            text = "Текст песни (построчно)",
                            color = palette.fg,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                    if (lyricsText.isNotBlank()) {
                        Text(
                            text = "${lyricsText.lines().count { it.isNotBlank() }} строк",
                            color = palette.muted,
                            fontSize = 11.sp
                        )
                    }
                }

                OutlinedTextField(
                    value = lyricsText,
                    onValueChange = onLyricsChange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 120.dp, max = 220.dp),
                    placeholder = {
                        Text(
                            "Вставьте или наберите текст песни построчно...\nКаждая строка станет фразой караоке.",
                            color = palette.muted.copy(alpha = 0.6f),
                            fontSize = 12.sp
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = palette.fg,
                        unfocusedTextColor = palette.fg,
                        focusedBorderColor = palette.accent,
                        unfocusedBorderColor = palette.border,
                        focusedContainerColor = palette.bg,
                        unfocusedContainerColor = palette.bg
                    ),
                    shape = RoundedCornerShape(8.dp)
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = { onLyricsChange("") },
                        enabled = lyricsText.isNotBlank(),
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.danger),
                        border = BorderStroke(1.dp, palette.danger.copy(alpha = 0.5f)),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.DeleteOutline, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Очистить", fontSize = 11.sp)
                    }

                    Button(
                        onClick = onBreakSyllablesOffline,
                        enabled = lyricsText.isNotBlank(),
                        modifier = Modifier.weight(2f),
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.ContentCut, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Разбить на слоги (Офлайн)", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        // Google Colab и MFA выравнивание
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Default.CloudQueue, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                    Text(
                        text = "Выравнивание через Google Colab (MFA)",
                        color = palette.fg,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = palette.raised,
                    border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.4f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Icon(
                                imageVector = if (audioLoaded) Icons.Default.CheckCircle else Icons.Default.Info,
                                contentDescription = null,
                                tint = if (audioLoaded) palette.accent else palette.muted,
                                modifier = Modifier.size(16.dp)
                            )
                            Text(
                                text = if (audioLoaded) "Аудио подключено (${formatTime(audioDuration)})" else "Аудио еще не подключено в проект",
                                color = if (audioLoaded) palette.fg else palette.muted,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }
                        Text(
                            text = "Montreal Forced Aligner требует тяжелые модели (~450 МБ) и >1.5 ГБ RAM. В Google Colab выравнивание выполняется на сервере за 1 минуту, конвертируется в .ass и отключает сессию.",
                            color = palette.muted,
                            fontSize = 11.sp,
                            lineHeight = 15.sp
                        )
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onBundleForColab,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.Archive, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("1. Пакет для Colab", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }

                    OutlinedButton(
                        onClick = onOpenColabUrl,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                        border = BorderStroke(1.dp, palette.border),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.OpenInBrowser, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("2. Блокнот Colab", fontSize = 12.sp)
                    }
                }
            }
        }

        // Импорт результата (TextGrid / ASS)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Default.FileUpload, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                    Text(
                        text = "Импорт результата выравнивания",
                        color = palette.fg,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                Text(
                    text = "Загрузите файл .TextGrid (MFA / Praat) или готовый .ass файл с устройства. TextGrid будет мгновенно распарсен прямо на телефоне.",
                    color = palette.muted,
                    fontSize = 11.sp
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onPickTextGrid,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.SyncAlt, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("TextGrid → ASS", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }

                    OutlinedButton(
                        onClick = onPickAss,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                        border = BorderStroke(1.dp, palette.border),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.Subtitles, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Открыть ASS", fontSize = 12.sp)
                    }
                }
            }
        }
    }
}
