package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.MusicNote,
            contentDescription = null,
            tint = palette.accent.copy(alpha = 0.6f),
            modifier = Modifier.size(64.dp)
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "Karaoke Mobile Studio",
            color = palette.fg,
            fontSize = 22.sp,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(4.dp))

        Text(
            text = "Редактор ASS-караоке для Android",
            color = palette.muted,
            fontSize = 14.sp,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Быстрые действия
        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth(0.9f)) {
            Button(
                onClick = onCreateProject,
                modifier = Modifier.fillMaxWidth().height(42.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = palette.accent,
                    contentColor = palette.accentFg
                ),
                shape = RoundedCornerShape(8.dp)
            ) {
                Icon(Icons.Default.Create, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Новый проект", color = palette.accentFg, fontSize = 14.sp)
            }

            OutlinedButton(
                onClick = onOpenProject,
                modifier = Modifier.fillMaxWidth().height(42.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = Color.Transparent,
                    contentColor = palette.fg
                ),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.7f)),
                shape = RoundedCornerShape(8.dp)
            ) {
                Icon(Icons.Default.FolderOpen, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Открыть проект", fontSize = 14.sp)
            }

            OutlinedButton(
                onClick = onImportProject,
                modifier = Modifier.fillMaxWidth().height(42.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = Color.Transparent,
                    contentColor = palette.fg
                ),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.7f)),
                shape = RoundedCornerShape(8.dp)
            ) {
                Icon(Icons.Default.Download, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Импорт проекта (.zip)", fontSize = 14.sp)
            }

            OutlinedButton(
                onClick = onLoadAss,
                modifier = Modifier.fillMaxWidth().height(42.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = Color.Transparent,
                    contentColor = palette.fg
                ),
                border = BorderStroke(1.dp, palette.border.copy(alpha = 0.7f)),
                shape = RoundedCornerShape(8.dp)
            ) {
                Icon(Icons.Default.Description, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Загрузить ASS субтитры", fontSize = 14.sp)
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Подсказки
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            HelpItem("• Pinch для зума, свайп для скролла таймлайна", palette)
            HelpItem("• Тап по слогу на таймлайне выбирает его", palette)
            HelpItem("• Быстрое объединение, разделение и смена тегов", palette)
        }
    }
}

@Composable
private fun HelpItem(text: String, palette: KaraokeThemePalette) {
    Text(
        text = text,
        color = palette.muted.copy(alpha = 0.8f),
        fontSize = 12.sp,
        textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth()
    )
}
