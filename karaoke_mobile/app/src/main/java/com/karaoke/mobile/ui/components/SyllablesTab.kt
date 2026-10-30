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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Компактный список слогов с inline-редактированием текста, романизации и статуса "Непропетое".
 */
@Composable
fun SyllablesTab(
    syllables: List<KaraokeSyllable>,
    selectedIds: Set<String>,
    activeSyllableId: String?,
    editTextId: String?,
    editTextValue: String,
    editTextRomanization: String,
    editIsUnspoken: Boolean,
    palette: KaraokeThemePalette,
    onSelect: (String, Boolean) -> Unit,
    onStartEdit: (String) -> Unit,
    onEditValueChange: (String) -> Unit,
    onEditRomanizationChange: (String) -> Unit,
    onToggleEditUnspoken: () -> Unit,
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
            val isEditing = syllable.id == editTextId
            SyllableItem(
                syllable = syllable,
                isSelected = syllable.id in selectedIds,
                isActive = syllable.id == activeSyllableId,
                isEditing = isEditing,
                editValue = editTextValue,
                editRomanization = editTextRomanization,
                editIsUnspoken = editIsUnspoken,
                palette = palette,
                onSelect = { addToSelection -> onSelect(syllable.id, addToSelection) },
                onStartEdit = { onStartEdit(syllable.id) },
                onEditValueChange = onEditValueChange,
                onEditRomanizationChange = onEditRomanizationChange,
                onToggleEditUnspoken = onToggleEditUnspoken,
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
    editRomanization: String,
    editIsUnspoken: Boolean,
    palette: KaraokeThemePalette,
    onSelect: (Boolean) -> Unit,
    onStartEdit: () -> Unit,
    onEditValueChange: (String) -> Unit,
    onEditRomanizationChange: (String) -> Unit,
    onToggleEditUnspoken: () -> Unit,
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
        else -> palette.border.copy(alpha = 0.4f)
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .clickable { onSelect(false) },
        colors = CardDefaults.cardColors(containerColor = bgColor),
        border = BorderStroke(if (isActive || isSelected) 1.5.dp else 1.dp, borderColor)
    ) {
        Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp)) {
            // Верхняя строка: тег, время и действия
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
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
                            text = if (syllable.isUnspoken) "$tagLabel (пауза)" else tagLabel,
                            color = if (syllable.isUnspoken) palette.warning else palette.accent,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }

                    Text(
                        text = "${formatTime(syllable.start)} — ${formatTime(syllable.end)}",
                        color = palette.muted,
                        fontSize = 11.sp
                    )
                }

                if (!isEditing) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // 1. Изменить текст и параметры (увеличенная кнопка)
                        Surface(
                            onClick = onStartEdit,
                            shape = RoundedCornerShape(8.dp),
                            color = palette.raised,
                            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                            modifier = Modifier.size(36.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    imageVector = Icons.Default.Edit,
                                    contentDescription = "Изменить текст",
                                    tint = palette.fg,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }

                        // 2. Тайминг (увеличенная кнопка)
                        Surface(
                            onClick = onStartTimingEdit,
                            shape = RoundedCornerShape(8.dp),
                            color = palette.accent.copy(alpha = 0.18f),
                            border = BorderStroke(1.dp, palette.accent.copy(alpha = 0.5f)),
                            modifier = Modifier.size(36.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    imageVector = Icons.Default.Schedule,
                                    contentDescription = "Тайминг",
                                    tint = palette.accent,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }

                        // 3. Удалить слог (увеличенная кнопка с красным акцентом)
                        Surface(
                            onClick = onDelete,
                            shape = RoundedCornerShape(8.dp),
                            color = palette.danger.copy(alpha = 0.15f),
                            border = BorderStroke(1.dp, palette.danger.copy(alpha = 0.5f)),
                            modifier = Modifier.size(36.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    imageVector = Icons.Default.Delete,
                                    contentDescription = "Удалить слог",
                                    tint = palette.danger,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }
                    }
                }
            }

            // Режим редактирования слога
            if (isEditing) {
                Spacer(modifier = Modifier.height(4.dp))

                // Поле ввода текста слога
                OutlinedTextField(
                    value = editValue,
                    onValueChange = onEditValueChange,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Текст слога", color = palette.muted, fontSize = 11.sp) },
                    textStyle = LocalTextStyle.current.copy(color = palette.fg, fontSize = 14.sp),
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

                Spacer(modifier = Modifier.height(4.dp))

                // Поле ввода романизации (транслита)
                OutlinedTextField(
                    value = editRomanization,
                    onValueChange = onEditRomanizationChange,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Романизация / транслит", color = palette.muted, fontSize = 11.sp) },
                    textStyle = LocalTextStyle.current.copy(color = palette.fg, fontSize = 13.sp),
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

                Spacer(modifier = Modifier.height(6.dp))

                // Строка с кнопкой "Непропетое" и кнопками сохранения/отмены
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Кнопка переключения "Непропетое" возле слога
                    OutlinedButton(
                        onClick = onToggleEditUnspoken,
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                        modifier = Modifier.height(28.dp),
                        colors = ButtonDefaults.outlinedButtonColors(
                            containerColor = if (editIsUnspoken) palette.warning.copy(alpha = 0.25f) else Color.Transparent,
                            contentColor = if (editIsUnspoken) palette.warning else palette.muted
                        ),
                        border = BorderStroke(1.dp, if (editIsUnspoken) palette.warning else palette.border.copy(alpha = 0.6f)),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Icon(
                            if (editIsUnspoken) Icons.Default.VolumeOff else Icons.Default.VolumeUp,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            if (editIsUnspoken) "Непропетое" else "Пропетое",
                            fontSize = 11.sp
                        )
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Button(
                            onClick = onCommitEdit,
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            modifier = Modifier.height(28.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent, contentColor = palette.accentFg),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Icon(Icons.Default.Check, contentDescription = "Save", modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(3.dp))
                            Text("OK", fontSize = 11.sp)
                        }

                        OutlinedButton(
                            onClick = onCancelEdit,
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            modifier = Modifier.height(28.dp),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.muted),
                            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.6f)),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Icon(Icons.Default.Close, contentDescription = "Cancel", modifier = Modifier.size(14.dp))
                        }
                    }
                }
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

                // Романизация (если заполнена)
                syllable.romanization?.let { rom ->
                    if (rom.isNotBlank()) {
                        Text(
                            text = rom,
                            color = palette.muted.copy(alpha = 0.8f),
                            fontSize = 11.sp,
                            fontStyle = androidx.compose.ui.text.font.FontStyle.Italic
                        )
                    }
                }
            }
        }
    }
}
