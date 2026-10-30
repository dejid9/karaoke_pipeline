package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
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
 * Компактный список слогов с inline-редактированием.
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
        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp)
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
        isActive -> palette.accent.copy(alpha = 0.22f)
        isSelected -> palette.selection.copy(alpha = 0.18f)
        else -> palette.panel
    }
    val borderColor = when {
        isActive -> palette.accent
        isSelected -> palette.selection
        else -> palette.border.copy(alpha = 0.35f)
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .clickable { onSelect(false) },
        colors = CardDefaults.cardColors(containerColor = bgColor),
        border = BorderStroke(if (isActive || isSelected) 1.5.dp else 1.dp, borderColor)
    ) {
        Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
            // Верхняя строка: тег, время и действия в одну линию
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    // Тег типа (\k, \kf, \ko, \K)
                    val tagLabel = when (syllable.tagType) {
                        KaraokeTagType.K -> "\\k"
                        KaraokeTagType.KF -> "\\kf"
                        KaraokeTagType.KO -> "\\ko"
                        KaraokeTagType.K_CAPITAL -> "\\K"
                    }
                    Surface(
                        color = if (syllable.isUnspoken) palette.warning.copy(alpha = 0.2f) else palette.accent.copy(alpha = 0.18f),
                        shape = RoundedCornerShape(3.dp),
                        border = BorderStroke(0.5.dp, if (syllable.isUnspoken) palette.warning else palette.accent.copy(alpha = 0.5f))
                    ) {
                        Text(
                            text = if (syllable.isUnspoken) "$tagLabel (mute)" else tagLabel,
                            color = if (syllable.isUnspoken) palette.warning else palette.accent,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }

                    // Интервал времени
                    Text(
                        text = "${formatTime(syllable.start)} — ${formatTime(syllable.end)}",
                        color = palette.muted,
                        fontSize = 11.sp
                    )
                }

                // Кнопки действий (редактировать, тайминг, удалить)
                if (!isEditing) {
                    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        IconButton(onClick = onStartEdit, modifier = Modifier.size(24.dp)) {
                            Icon(Icons.Default.Edit, contentDescription = "Edit", tint = palette.muted, modifier = Modifier.size(15.dp))
                        }
                        IconButton(onClick = onStartTimingEdit, modifier = Modifier.size(24.dp)) {
                            Icon(Icons.Default.Schedule, contentDescription = "Timing", tint = palette.muted, modifier = Modifier.size(15.dp))
                        }
                        IconButton(onClick = onDelete, modifier = Modifier.size(24.dp)) {
                            Icon(Icons.Default.Delete, contentDescription = "Delete", tint = palette.danger.copy(alpha = 0.7f), modifier = Modifier.size(15.dp))
                        }
                    }
                }
            }

            // Текст слога
            if (isEditing) {
                Spacer(modifier = Modifier.height(4.dp))
                OutlinedTextField(
                    value = editValue,
                    onValueChange = onEditValueChange,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    textStyle = LocalTextStyle.current.copy(color = palette.fg, fontSize = 14.sp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = palette.accent,
                        unfocusedBorderColor = palette.border,
                        focusedContainerColor = palette.inputBg,
                        unfocusedContainerColor = palette.inputBg
                    ),
                    trailingIcon = {
                        Row {
                            IconButton(onClick = onCommitEdit, modifier = Modifier.size(28.dp)) {
                                Icon(Icons.Default.Check, contentDescription = "OK", tint = palette.success, modifier = Modifier.size(18.dp))
                            }
                            IconButton(onClick = onCancelEdit, modifier = Modifier.size(28.dp)) {
                                Icon(Icons.Default.Close, contentDescription = "Cancel", tint = palette.danger, modifier = Modifier.size(18.dp))
                            }
                        }
                    }
                )
            } else {
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = syllable.displayText,
                    color = if (syllable.isUnspoken || syllable.text.isBlank()) palette.muted else palette.fg,
                    fontSize = 14.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onStartEdit() }
                )
            }

            // Романизация (если есть)
            syllable.romanization?.let { rom ->
                Text(
                    text = rom,
                    color = palette.muted.copy(alpha = 0.75f),
                    fontSize = 11.sp
                )
            }
        }
    }
}
