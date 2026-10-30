package com.karaoke.mobile.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Пустое состояние — когда нет открытого проекта или ASS.
 */
@Composable
fun EmptyState(
    palette: KaraokeThemePalette,
    onCreateProject: () -> Unit,
    onOpenProject: () -> Unit,
    onImportProject: () -> Unit,
    onLoadAss: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.MusicNote,
            contentDescription = null,
            tint = palette.accent.copy(alpha = 0.5f),
            modifier = Modifier.size(80.dp)
        )

        Spacer(modifier = Modifier.height(24.dp))

        Text(
            text = "Karaoke Mobile Studio",
            color = palette.fg,
            fontSize = 24.sp,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "Редактор ASS-караоке для Android",
            color = palette.muted,
            fontSize = 16.sp,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(32.dp))

        // Быстрые действия
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = onCreateProject,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
            ) {
                Icon(Icons.Default.Create, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Новый проект", color = palette.accentFg)
            }

            OutlinedButton(
                onClick = onOpenProject,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.FolderOpen, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Открыть проект")
            }

            OutlinedButton(
                onClick = onImportProject,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Импорт проекта")
            }

            OutlinedButton(
                onClick = onLoadAss,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                border = ButtonDefaults.outlinedButtonBorder
            ) {
                Icon(Icons.Default.Description, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Загрузить ASS")
            }
        }

        Spacer(modifier = Modifier.height(32.dp))

        // Подсказки
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HelpItem("• Выберите слог на таймлайне тапом", palette)
            HelpItem("• Два слога объединяются кнопкой", palette)
            HelpItem("• Pinch для zoom, drag для скролла", palette)
            HelpItem("• Тап по тексту — редактирование", palette)
        }
    }
}

@Composable
private fun HelpItem(text: String, palette: KaraokeThemePalette) {
    Text(
        text = text,
        color = palette.muted.copy(alpha = 0.7f),
        fontSize = 13.sp,
        textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth()
    )
}
