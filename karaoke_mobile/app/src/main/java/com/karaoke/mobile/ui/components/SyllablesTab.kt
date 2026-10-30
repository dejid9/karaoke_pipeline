package com.karaoke.mobile.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Список слогов с inline-редактированием.
 */
@Composable
fun SyllablesTab(
    syllables: List<KaraokeSyllable>,
    selectedIds: Set<String>,
    activeSyllableId: String?,
    editTextId: String?,
    editTextValue: String,
    palette: KaraokeThemePalette,
    onSelect: (String, Boolean) -> Unit,
    onStartEdit: (String) -> Unit,
    onEditValueChange: (String) -> Unit,
    onCommitEdit: () -> Unit,
    onCancelEdit: () -> Unit,
    onStartTimingEdit: (String) -> Unit,
    onDelete: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        items(syllables, key = { it.id }) { syllable ->
            SyllableItem(
                syllable = syllable,
                isSelected = syllable.id in selectedIds,
                isActive = syllable.id == activeSyllableId,
                isEditing = syllable.id == editTextId,
                editValue = editTextValue,
                palette = palette,
                onSelect = { addToSelection -> onSelect(syllable.id, addToSelection) },
                onStartEdit = { onStartEdit(syllable.id) },
                onEditValueChange = onEditValueChange,
                onCommitEdit = onCommitEdit,
                onCancelEdit = onCancelEdit,
                onStartTimingEdit = { onStartTimingEdit(syllable.id) },
                onDelete = { onDelete(syllable.id) }
            )
        }
    }
}

@Composable
private fun SyllableItem(
    syllable: KaraokeSyllable,
    isSelected: Boolean,
    isActive: Boolean,
    isEditing: Boolean,
    editValue: String,
    palette: KaraokeThemePalette,
    onSelect: (Boolean) -> Unit,
    onStartEdit: () -> Unit,
    onEditValueChange: (String) -> Unit,
    onCommitEdit: () -> Unit,
    onCancelEdit: () -> Unit,
    onStartTimingEdit: () -> Unit,
    onDelete: () -> Unit
) {
    val bgColor = when {
        isActive -> palette.accent.copy(alpha = 0.2f)
        isSelected -> palette.selection.copy(alpha = 0.15f)
        else -> palette.panel
    }
    val borderColor = when {
        isActive -> palette.accent
        isSelected -> palette.selection
        else -> palette.border.copy(alpha = 0.2f)
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable { onSelect(false) },
        colors = CardDefaults.cardColors(containerColor = bgColor),
        border = androidx.compose.foundation.BorderStroke(1.dp, borderColor)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Тег типа
                val tagLabel = when (syllable.tagType) {
                    KaraokeTagType.K -> "\\k"
                    KaraokeTagType.KF -> "\\kf"
                    KaraokeTagType.KO -> "\\ko"
                    KaraokeTagType.K_CAPITAL -> "\\K"
                }
                Surface(
                    color = if (syllable.isUnspoken) palette.muted.copy(alpha = 0.3f) else palette.accent.copy(alpha = 0.15f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = tagLabel,
                        color = if (syllable.isUnspoken) palette.muted else palette.accent,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }

                // Время
                Text(
                    text = "${formatTime(syllable.start)} — ${formatTime(syllable.end)}",
                    color = palette.muted,
                    fontSize = 11.sp
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Текст слога
            if (isEditing) {
                OutlinedTextField(
                    value = editValue,
                    onValueChange = onEditValueChange,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    textStyle = LocalTextStyle.current.copy(color = palette.fg, fontSize = 16.sp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = palette.accent,
                        unfocusedBorderColor = palette.border,
                        focusedContainerColor = palette.inputBg,
                        unfocusedContainerColor = palette.inputBg
                    ),
                    trailingIcon = {
                        Row {
                            IconButton(onClick = onCommitEdit) {
                                Icon(Icons.Default.Check, contentDescription = "OK", tint = palette.success)
                            }
                            IconButton(onClick = onCancelEdit) {
                                Icon(Icons.Default.Close, contentDescription = "Cancel", tint = palette.danger)
                            }
                        }
                    }
                )
            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = syllable.text.ifEmpty { "(пусто)" },
                        color = if (syllable.text.isEmpty()) palette.muted else palette.fg,
                        fontSize = 16.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f).clickable { onStartEdit() }
                    )

                    // Кнопки действий
                    Row {
                        IconButton(onClick = onStartEdit, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Edit, contentDescription = "Edit", tint = palette.muted, modifier = Modifier.size(18.dp))
                        }
                        IconButton(onClick = onStartTimingEdit, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Schedule, contentDescription = "Timing", tint = palette.muted, modifier = Modifier.size(18.dp))
                        }
                        IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                            Icon(Icons.Default.Delete, contentDescription = "Delete", tint = palette.danger.copy(alpha = 0.7f), modifier = Modifier.size(18.dp))
                        }
                    }
                }
            }

            // Романизация
            syllable.romanization?.let { rom ->
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = rom,
                    color = palette.muted.copy(alpha = 0.7f),
                    fontSize = 12.sp
                )
            }
        }
    }
}
