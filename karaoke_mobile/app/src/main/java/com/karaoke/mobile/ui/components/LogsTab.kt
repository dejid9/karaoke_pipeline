package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.LogEntry
import com.karaoke.mobile.model.LogLevel
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Вкладка журнала событий (Логи), перенесенная из ПК-версии.
 */
@Composable
fun LogsTab(
    logs: List<LogEntry>,
    palette: KaraokeThemePalette,
    onClear: () -> Unit,
    onShare: () -> Unit,
    modifier: Modifier = Modifier
) {
    var selectedFilter by remember { mutableStateOf<LogLevel?>(null) }
    var searchQuery by remember { mutableStateOf("") }

    val filteredLogs = remember(logs, selectedFilter, searchQuery) {
        logs.filter { entry ->
            val matchesFilter = selectedFilter == null || entry.level == selectedFilter
            val matchesSearch = searchQuery.isBlank() ||
                    entry.message.contains(searchQuery, ignoreCase = true) ||
                    entry.tag.contains(searchQuery, ignoreCase = true)
            matchesFilter && matchesSearch
        }.reversed()
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(palette.bg)
            .padding(8.dp)
    ) {
        // Панель управления логами
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Icon(
                            imageVector = Icons.Default.Terminal,
                            contentDescription = null,
                            tint = palette.accent,
                            modifier = Modifier.size(20.dp)
                        )
                        Text(
                            text = "Журнал событий",
                            color = palette.fg,
                            fontSize = 15.sp,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                        )
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = palette.raised,
                            border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.5f))
                        ) {
                            Text(
                                text = "${logs.size}",
                                color = palette.muted,
                                fontSize = 11.sp,
                                modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp)
                            )
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        IconButton(onClick = onShare, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Share, contentDescription = "Поделиться логами", tint = palette.accent, modifier = Modifier.size(18.dp))
                        }
                        IconButton(onClick = onClear, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.DeleteOutline, contentDescription = "Очистить логи", tint = palette.danger.copy(alpha = 0.8f), modifier = Modifier.size(18.dp))
                        }
                    }
                }

                // Фильтры по уровням
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    FilterChip(
                        selected = selectedFilter == null,
                        onClick = { selectedFilter = null },
                        label = { Text("Все", fontSize = 11.sp) },
                        modifier = Modifier.height(28.dp),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = palette.raised,
                            labelColor = palette.fg,
                            selectedContainerColor = palette.accent,
                            selectedLabelColor = palette.accentFg
                        )
                    )

                    FilterChip(
                        selected = selectedFilter == LogLevel.ERROR,
                        onClick = { selectedFilter = if (selectedFilter == LogLevel.ERROR) null else LogLevel.ERROR },
                        label = { Text("Ошибки", fontSize = 11.sp) },
                        modifier = Modifier.height(28.dp),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = palette.raised,
                            labelColor = palette.danger,
                            selectedContainerColor = palette.danger,
                            selectedLabelColor = Color.White
                        )
                    )

                    FilterChip(
                        selected = selectedFilter == LogLevel.WARN,
                        onClick = { selectedFilter = if (selectedFilter == LogLevel.WARN) null else LogLevel.WARN },
                        label = { Text("Внимание", fontSize = 11.sp) },
                        modifier = Modifier.height(28.dp),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = palette.raised,
                            labelColor = palette.warning,
                            selectedContainerColor = palette.warning,
                            selectedLabelColor = Color.Black
                        )
                    )

                    FilterChip(
                        selected = selectedFilter == LogLevel.ACTION,
                        onClick = { selectedFilter = if (selectedFilter == LogLevel.ACTION) null else LogLevel.ACTION },
                        label = { Text("Действия", fontSize = 11.sp) },
                        modifier = Modifier.height(28.dp),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = palette.raised,
                            labelColor = palette.accent,
                            selectedContainerColor = palette.accent,
                            selectedLabelColor = palette.accentFg
                        )
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(6.dp))

        // Список записей
        if (filteredLogs.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = if (logs.isEmpty()) "Журнал пока пуст" else "Нет записей, подходящих под фильтр",
                    color = palette.muted,
                    fontSize = 13.sp
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                verticalArrangement = Arrangement.spacedBy(3.dp)
            ) {
                items(filteredLogs, key = { it.id }) { log ->
                    LogItem(log = log, palette = palette)
                }
            }
        }
    }
}

@Composable
private fun LogItem(
    log: LogEntry,
    palette: KaraokeThemePalette
) {
    val levelColor = when (log.level) {
        LogLevel.ERROR -> palette.danger
        LogLevel.WARN -> palette.warning
        LogLevel.ACTION -> palette.accent
        LogLevel.INFO -> palette.muted
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = palette.panel),
        border = BorderStroke(0.5.dp, palette.border.copy(alpha = 0.35f))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 6.dp, vertical = 4.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            // Время
            Text(
                text = log.timeFormatted,
                color = palette.muted.copy(alpha = 0.8f),
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(top = 1.dp)
            )

            // Бейдж уровня
            Surface(
                shape = RoundedCornerShape(2.dp),
                color = levelColor.copy(alpha = 0.18f),
                border = BorderStroke(0.5.dp, levelColor.copy(alpha = 0.6f))
            ) {
                Text(
                    text = log.level.label,
                    color = levelColor,
                    fontSize = 9.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 3.dp, vertical = 0.5.dp)
                )
            }

            // Тэг
            Text(
                text = "[${log.tag}]",
                color = palette.muted,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
                modifier = Modifier.padding(top = 1.dp)
            )

            // Сообщение
            Text(
                text = log.message,
                color = palette.fg,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier
                    .weight(1f)
                    .padding(top = 1.dp)
            )
        }
    }
}
