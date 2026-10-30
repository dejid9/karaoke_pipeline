package com.karaoke.mobile.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.karaoke.mobile.ui.theme.KaraokeThemePalette

/**
 * Вкладка «Рендер»:
 * - Выбор разрешения и FPS
 * - Выбор фона (сплошной цвет, изображение, видео)
 * - Позиционирование и стили караоке-субтитров
 * - Локальный рендер через FFmpeg (команда / экспорт ASS / минимальная сборка)
 * - Пакет для облачного рендера в Colab
 */
@Composable
fun RenderTab(
    resolution: String,
    fps: Int,
    backgroundType: String,
    backgroundColor: Long,
    backgroundImageSelected: Boolean,
    backgroundVideoSelected: Boolean,
    alignment: Int,
    fontSize: Int,
    smoothScroll: Boolean,
    palette: KaraokeThemePalette,
    onResolutionChange: (String) -> Unit,
    onFpsChange: (Int) -> Unit,
    onBackgroundTypeChange: (String) -> Unit,
    onBackgroundColorChange: (Long) -> Unit,
    onPickBackgroundImage: () -> Unit,
    onPickBackgroundVideo: () -> Unit,
    onAlignmentChange: (Int) -> Unit,
    onFontSizeChange: (Int) -> Unit,
    onSmoothScrollChange: (Boolean) -> Unit,
    onExportRenderAss: () -> Unit,
    onCopyFfmpegCommand: () -> Unit,
    onBundleForColabRender: () -> Unit,
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
                        imageVector = Icons.Default.Movie,
                        contentDescription = null,
                        tint = palette.accent,
                        modifier = Modifier.padding(8.dp).size(24.dp)
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Рендер караоке-видео",
                        color = palette.fg,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Сборка видеоряда с наложением караоке libass",
                        color = palette.muted,
                        fontSize = 11.sp
                    )
                }
            }
        }

        // Разрешение и частота кадров (FPS)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Разрешение и частота кадров",
                    color = palette.fg,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold
                )

                // Разрешение
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val resolutions = listOf("1080p", "720p", "480p")
                    resolutions.forEach { res ->
                        val isSelected = resolution == res
                        FilterChip(
                            selected = isSelected,
                            onClick = { onResolutionChange(res) },
                            label = { Text(res, fontSize = 12.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f))
                        )
                    }
                }

                // FPS
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val fpsList = listOf(30, 60)
                    fpsList.forEach { valFps ->
                        val isSelected = fps == valFps
                        FilterChip(
                            selected = isSelected,
                            onClick = { onFpsChange(valFps) },
                            label = { Text("$valFps FPS", fontSize = 12.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f))
                        )
                    }
                }
            }
        }

        // Фон видео
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Фоновый видеоряд",
                    color = palette.fg,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val bgTypes = listOf(
                        "color" to "Цвет",
                        "image" to "Картинка",
                        "video" to "Видео"
                    )
                    bgTypes.forEach { (type, label) ->
                        val isSelected = backgroundType == type
                        FilterChip(
                            selected = isSelected,
                            onClick = { onBackgroundTypeChange(type) },
                            label = { Text(label, fontSize = 12.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f))
                        )
                    }
                }

                when (backgroundType) {
                    "color" -> {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Цвет заливки:", color = palette.muted, fontSize = 12.sp)
                            val colors = listOf(
                                0xFF0B101BL to "Тёмно-синий",
                                0xFF050508L to "Глубокий чёрный",
                                0xFF140D24L to "Фиолетовый",
                                0xFF101D1BL to "Изумрудный"
                            )
                            colors.forEach { (cLong, _) ->
                                val isSelected = backgroundColor == cLong
                                Surface(
                                    shape = CircleShape,
                                    color = Color(cLong),
                                    border = BorderStroke(
                                        if (isSelected) 2.dp else 1.dp,
                                        if (isSelected) palette.accent else palette.border
                                    ),
                                    modifier = Modifier.size(28.dp),
                                    onClick = { onBackgroundColorChange(cLong) }
                                ) {}
                            }
                        }
                    }
                    "image" -> {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = if (backgroundImageSelected) "✓ Изображение выбрано" else "Изображение не выбрано",
                                color = if (backgroundImageSelected) palette.accent else palette.muted,
                                fontSize = 12.sp
                            )
                            OutlinedButton(
                                onClick = onPickBackgroundImage,
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                                border = BorderStroke(1.dp, palette.border),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Icon(Icons.Default.Image, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Выбрать JPG/PNG", fontSize = 11.sp)
                            }
                        }
                    }
                    "video" -> {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = if (backgroundVideoSelected) "✓ Видео выбрано" else "Видео не выбрано",
                                color = if (backgroundVideoSelected) palette.accent else palette.muted,
                                fontSize = 12.sp
                            )
                            OutlinedButton(
                                onClick = onPickBackgroundVideo,
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                                border = BorderStroke(1.dp, palette.border),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Icon(Icons.Default.VideoFile, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Выбрать MP4", fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        }

        // Форматирование и позиционирование караоке
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Позиционирование и стили субтитров",
                    color = palette.fg,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold
                )

                // Выравнивание
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val alignments = listOf(
                        2 to "Снизу (\\an2)",
                        5 to "По центру (\\an5)",
                        8 to "Сверху (\\an8)"
                    )
                    alignments.forEach { (alignVal, label) ->
                        val isSelected = alignment == alignVal
                        FilterChip(
                            selected = isSelected,
                            onClick = { onAlignmentChange(alignVal) },
                            label = { Text(label, fontSize = 11.sp) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f))
                        )
                    }
                }

                // Размер шрифта
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text("Размер шрифта:", color = palette.muted, fontSize = 12.sp)
                    val fontSizes = listOf(36, 44, 54, 64, 72)
                    fontSizes.forEach { sz ->
                        val isSelected = fontSize == sz
                        FilterChip(
                            selected = isSelected,
                            onClick = { onFontSizeChange(sz) },
                            label = { Text("$sz", fontSize = 11.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = palette.accent.copy(alpha = 0.2f),
                                selectedLabelColor = palette.accent,
                                containerColor = palette.raised,
                                labelColor = palette.fg
                            ),
                            border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border.copy(alpha = 0.4f))
                        )
                    }
                }

                // Плавная прокрутка (Lead-in)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Плавное появление (Lead-in 0.5с)", color = palette.fg, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                        Text("Заранее выводит строку на экран до первого слога", color = palette.muted, fontSize = 10.sp)
                    }
                    Switch(
                        checked = smoothScroll,
                        onCheckedChange = onSmoothScrollChange,
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = palette.accent,
                            checkedTrackColor = palette.accent.copy(alpha = 0.35f),
                            uncheckedThumbColor = palette.muted,
                            uncheckedTrackColor = palette.raised
                        )
                    )
                }
            }
        }

        // Локальный рендер и FFmpeg
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Default.PhoneAndroid, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                    Text(
                        text = "Локальный рендер (на устройстве)",
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
                    Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            text = "ℹ️ Минимальная сборка FFmpeg для Android:",
                            color = palette.fg,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = "Для рендера караоке требуется библиотека libass (рендер эффектов \\kf, шрифтов и цветов) + зависимости libfreetype/libfribidi. Видеокодирование выполняется встроенным аппаратным MediaCodec (h264_mediacodec), что не нагружает процессор телефона. Вес сборки для arm64-v8a укладывается в 14–17 МБ!",
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
                        onClick = onExportRenderAss,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.FileDownload, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Экспорт ASS", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }

                    OutlinedButton(
                        onClick = onCopyFfmpegCommand,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.fg),
                        border = BorderStroke(1.dp, palette.border),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.ContentCopy, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Команда FFmpeg", fontSize = 11.sp)
                    }
                }
            }
        }

        // Облачный рендер (Google Colab)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = palette.panel),
            border = BorderStroke(1.dp, palette.border.copy(alpha = 0.5f))
        ) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Default.CloudUpload, contentDescription = null, tint = palette.accent, modifier = Modifier.size(18.dp))
                    Text(
                        text = "Облачный рендер (Google Colab)",
                        color = palette.fg,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                Text(
                    text = "Если видео длинное, в 4K 60 FPS или телефон слабый — сформируйте готовый пакет и отправьте в Colab для мгновенного рендера на GPU.",
                    color = palette.muted,
                    fontSize = 11.sp
                )

                Button(
                    onClick = onBundleForColabRender,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = palette.raised),
                    border = BorderStroke(1.dp, palette.border),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.Archive, contentDescription = null, tint = palette.accent, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Сформировать пакет для Colab Video Render", fontSize = 12.sp, color = palette.fg)
                }
            }
        }
    }
}
