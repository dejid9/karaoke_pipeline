package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Заглушка для разделов приложения, находящихся в разработке ("Подготовка", "Точный SPS", "Рендер").
 */
@Composable
fun PlaceholderTab(
    title: String,
    icon: ImageVector,
    description: String,
    palette: KaraokeThemePalette,
    onNavigateToKaraoke: () -> Unit,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(palette.bg)
            .padding(24.dp),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.92f)
                .wrapContentHeight(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = palette.accent.copy(alpha = 0.15f),
                    border = BorderStroke(1.dp, palette.accent.copy(alpha = 0.4f)),
                    modifier = Modifier.size(72.dp)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            imageVector = icon,
                            contentDescription = title,
                            tint = palette.accent,
                            modifier = Modifier.size(36.dp)
                        )
                    }
                }

                Text(
                    text = title,
                    color = palette.fg,
                    fontSize = 20.sp,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    textAlign = TextAlign.Center
                )

                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = palette.warning.copy(alpha = 0.15f),
                    border = BorderStroke(0.5.dp, palette.warning.copy(alpha = 0.6f))
                ) {
                    Text(
                        text = "В разработке для Android",
                        color = palette.warning,
                        fontSize = 11.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }

                Text(
                    text = description,
                    color = palette.muted,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center,
                    lineHeight = 18.sp
                )

                Spacer(modifier = Modifier.height(4.dp))

                Button(
                    onClick = onNavigateToKaraoke,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = palette.accent,
                        contentColor = palette.accentFg
                    ),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.height(40.dp)
                ) {
                    Text("Перейти в редактор «Караоке»", fontSize = 13.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                }
            }
        }
    }
}
