package com.karaoke.mobile.ui.components

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Save
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.ui.theme.KaraokeOnSurface
import com.karaoke.mobile.ui.theme.KaraokeOnSurfaceVariant
import com.karaoke.mobile.ui.theme.KaraokePrimary
import com.karaoke.mobile.ui.theme.KaraokeSecondary
import com.karaoke.mobile.ui.theme.KaraokeSurface
import com.karaoke.mobile.ui.theme.KaraokeSurfaceVariant

@Composable
fun FilesTab(
    lines: List<AssLine>,
    audioFileName: String?,
    onLoadAss: (String) -> Unit,
    onSetAudio: (Context, Uri) -> Unit,
    onSaveAss: () -> String,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current

    val assPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let {
            context.contentResolver.openInputStream(it)?.use { stream ->
                val content = stream.bufferedReader().readText()
                onLoadAss(content)
            }
        }
    }

    val audioPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let { onSetAudio(context, it) }
    }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(
                text = "Файлы проекта",
                style = MaterialTheme.typography.headlineMedium,
                color = KaraokeOnSurface
            )
            Spacer(modifier = Modifier.height(8.dp))
        }

        item {
            ActionCard(
                icon = Icons.Default.Description,
                title = "Загрузить ASS",
                subtitle = if (lines.isNotEmpty()) "Загружено ${lines.size} строк" else "Файл не выбран",
                buttonText = "Выбрать файл",
                onClick = { assPicker.launch("text/plain") }
            )
        }

        item {
            ActionCard(
                icon = Icons.Default.AudioFile,
                title = "Аудио",
                subtitle = audioFileName ?: "Файл не выбран",
                buttonText = "Выбрать аудио",
                onClick = { audioPicker.launch("audio/*") }
            )
        }

        item {
            OutlinedButton(
                onClick = {
                    val content = onSaveAss()
                    // In real app, use Storage Access Framework to save
                },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(Icons.Default.Save, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text("Сохранить ASS")
            }
        }

        if (lines.isNotEmpty()) {
            item {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Строки",
                    style = MaterialTheme.typography.titleLarge,
                    color = KaraokeOnSurface
                )
                Spacer(modifier = Modifier.height(4.dp))
            }

            itemsIndexed(lines) { idx, line ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    colors = CardDefaults.cardColors(containerColor = KaraokeSurface)
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "#${idx + 1}",
                            style = MaterialTheme.typography.labelMedium,
                            color = KaraokeOnSurfaceVariant,
                            modifier = Modifier.padding(end = 12.dp)
                        )
                        Column {
                            Text(
                                text = line.text.replace(Regex("\\{[^}]*\\}"), ""),
                                style = MaterialTheme.typography.bodyLarge,
                                color = KaraokeOnSurface
                            )
                            Text(
                                text = "${line.start}ms — ${line.end}ms",
                                style = MaterialTheme.typography.labelMedium,
                                color = KaraokeOnSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ActionCard(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    subtitle: String,
    buttonText: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = KaraokeSurfaceVariant)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, contentDescription = null, tint = KaraokePrimary)
                Spacer(modifier = Modifier.width(12.dp))
                Column {
                    Text(text = title, style = MaterialTheme.typography.titleLarge, color = KaraokeOnSurface)
                    Text(text = subtitle, style = MaterialTheme.typography.bodyMedium, color = KaraokeOnSurfaceVariant)
                }
            }
            Button(onClick = onClick, shape = RoundedCornerShape(8.dp)) {
                Text(buttonText)
            }
        }
    }
}
