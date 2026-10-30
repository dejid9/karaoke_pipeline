package com.karaoke.mobile.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Merge
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Splitscreen
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.model.Syllable
import com.karaoke.mobile.model.formatTime
import com.karaoke.mobile.model.toDisplayText
import com.karaoke.mobile.ui.theme.KaraokeAccent
import com.karaoke.mobile.ui.theme.KaraokeBurst
import com.karaoke.mobile.ui.theme.KaraokeOnSurface
import com.karaoke.mobile.ui.theme.KaraokeOnSurfaceVariant
import com.karaoke.mobile.ui.theme.KaraokePrimary
import com.karaoke.mobile.ui.theme.KaraokeSecondary
import com.karaoke.mobile.ui.theme.KaraokeSurface
import com.karaoke.mobile.ui.theme.KaraokeSurfaceVariant

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun SyllablesTab(
    lines: List<AssLine>,
    currentLineIndex: Int,
    currentSyllableIndex: Int,
    onSelectLine: (Int) -> Unit,
    onSelectSyllable: (Int, Int) -> Unit,
    onUpdateSyllableText: (Int, Int, String) -> Unit,
    onToggleBurst: (Int, Int) -> Unit,
    onSplitSyllable: (Int, Int, Long) -> Unit,
    onMergeSyllables: (Int, Int, Int) -> Unit,
    onSnapToSyllable: (Syllable) -> Unit,
    modifier: Modifier = Modifier
) {
    val listState = rememberLazyListState()

    LaunchedEffect(currentLineIndex, currentSyllableIndex) {
        if (currentLineIndex >= 0) {
            listState.animateScrollToItem(currentLineIndex)
        }
    }

    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        itemsIndexed(lines) { lineIdx, line ->
            val isExpanded = lineIdx == currentLineIndex
            LineCard(
                line = line,
                lineIndex = lineIdx,
                isExpanded = isExpanded,
                currentSyllableIndex = if (isExpanded) currentSyllableIndex else -1,
                onClick = { onSelectLine(lineIdx) },
                onSelectSyllable = { sIdx -> onSelectSyllable(lineIdx, sIdx) },
                onUpdateSyllableText = { sIdx, text -> onUpdateSyllableText(lineIdx, sIdx, text) },
                onToggleBurst = { sIdx -> onToggleBurst(lineIdx, sIdx) },
                onSplitSyllable = { sIdx, point -> onSplitSyllable(lineIdx, sIdx, point) },
                onMergeSyllables = { from, to -> onMergeSyllables(lineIdx, from, to) },
                onSnapToSyllable = onSnapToSyllable,
                modifier = Modifier.animateItemPlacement()
            )
        }
    }
}

@Composable
private fun LineCard(
    line: AssLine,
    lineIndex: Int,
    isExpanded: Boolean,
    currentSyllableIndex: Int,
    onClick: () -> Unit,
    onSelectSyllable: (Int) -> Unit,
    onUpdateSyllableText: (Int, String) -> Unit,
    onToggleBurst: (Int) -> Unit,
    onSplitSyllable: (Int, Long) -> Unit,
    onMergeSyllables: (Int, Int) -> Unit,
    onSnapToSyllable: (Syllable) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isExpanded) KaraokeSurfaceVariant else KaraokeSurface
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isExpanded) 4.dp else 1.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "#${lineIndex + 1}",
                    style = MaterialTheme.typography.labelMedium,
                    color = KaraokeOnSurfaceVariant
                )
                Text(
                    text = "${formatTime(line.start)} → ${formatTime(line.end)}",
                    style = MaterialTheme.typography.labelMedium,
                    color = KaraokeOnSurfaceVariant
                )
            }

            Text(
                text = line.text.replace(Regex("\\{[^}]*\\}"), ""),
                style = MaterialTheme.typography.bodyLarge,
                color = KaraokeOnSurface,
                modifier = Modifier.padding(vertical = 4.dp)
            )

            if (line.isBurst) {
                Text(
                    text = "✦ BURST",
                    style = MaterialTheme.typography.labelMedium,
                    color = KaraokeBurst,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            AnimatedVisibility(visible = isExpanded) {
                Column {
                    Spacer(modifier = Modifier.height(8.dp))
                    line.syllables.forEachIndexed { sIdx, syllable ->
                        SyllableRow(
                            syllable = syllable,
                            index = sIdx,
                            isSelected = sIdx == currentSyllableIndex,
                            onClick = { onSelectSyllable(sIdx) },
                            onTextChange = { text -> onUpdateSyllableText(sIdx, text) },
                            onToggleBurst = { onToggleBurst(sIdx) },
                            onSplit = { point -> onSplitSyllable(sIdx, point) },
                            onMergeNext = {
                                if (sIdx < line.syllables.size - 1) {
                                    onMergeSyllables(sIdx, sIdx + 1)
                                }
                            },
                            onSnap = { onSnapToSyllable(syllable) }
                        )
                        if (sIdx < line.syllables.size - 1) {
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SyllableRow(
    syllable: Syllable,
    index: Int,
    isSelected: Boolean,
    onClick: () -> Unit,
    onTextChange: (String) -> Unit,
    onToggleBurst: () -> Unit,
    onSplit: (Long) -> Unit,
    onMergeNext: () -> Unit,
    onSnap: () -> Unit,
    modifier: Modifier = Modifier
) {
    var isEditing by remember { mutableStateOf(false) }
    var editText by remember { mutableStateOf(syllable.text) }
    val focusRequester = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current

    LaunchedEffect(isSelected) {
        if (!isSelected) {
            isEditing = false
        }
    }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(
                if (isSelected) KaraokePrimary.copy(alpha = 0.15f)
                else KaraokeSurface.copy(alpha = 0.5f)
            )
            .clickable { onClick() }
            .padding(8.dp)
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "${index + 1}.",
                        style = MaterialTheme.typography.labelMedium,
                        color = KaraokeOnSurfaceVariant,
                        modifier = Modifier.width(24.dp)
                    )
                    if (isEditing && isSelected) {
                        BasicTextField(
                            value = editText,
                            onValueChange = { editText = it },
                            modifier = Modifier
                                .weight(1f)
                                .focusRequester(focusRequester)
                                .onFocusChanged { if (!it.isFocused) { isEditing = false; onTextChange(editText) } },
                            textStyle = TextStyle(color = KaraokeOnSurface, fontSize = 14.sp),
                            singleLine = true,
                            cursorBrush = SolidColor(KaraokeAccent),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = {
                                isEditing = false
                                onTextChange(editText)
                                focusManager.clearFocus()
                            })
                        )
                        LaunchedEffect(Unit) { focusRequester.requestFocus() }
                    } else {
                        Text(
                            text = syllable.toDisplayText(),
                            style = MaterialTheme.typography.bodyLarge,
                            color = if (syllable.isBurst) KaraokeBurst else KaraokeOnSurface,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }

                Row {
                    IconButton(onClick = onSnap, modifier = Modifier.padding(0.dp)) {
                        Icon(Icons.Default.MusicNote, "К позиции", tint = KaraokeSecondary)
                    }
                    IconButton(onClick = { isEditing = !isEditing; editText = syllable.text }, modifier = Modifier.padding(0.dp)) {
                        Icon(Icons.Default.Edit, "Редактировать", tint = KaraokeOnSurfaceVariant)
                    }
                    IconButton(onClick = onToggleBurst, modifier = Modifier.padding(0.dp)) {
                        Icon(
                            Icons.Default.Star,
                            "Burst",
                            tint = if (syllable.isBurst) KaraokeBurst else KaraokeOnSurfaceVariant.copy(alpha = 0.4f)
                        )
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${formatTime(syllable.start)} → ${formatTime(syllable.end)} (${syllable.duration}мс)",
                    style = MaterialTheme.typography.labelMedium,
                    color = KaraokeOnSurfaceVariant
                )
                Row {
                    IconButton(onClick = { onSplit(syllable.mid) }, modifier = Modifier.padding(0.dp)) {
                        Icon(Icons.Default.Splitscreen, "Разделить", tint = KaraokeOnSurfaceVariant)
                    }
                    IconButton(onClick = onMergeNext, modifier = Modifier.padding(0.dp)) {
                        Icon(Icons.Default.Merge, "Объединить", tint = KaraokeOnSurfaceVariant)
                    }
                }
            }
        }
    }
}
