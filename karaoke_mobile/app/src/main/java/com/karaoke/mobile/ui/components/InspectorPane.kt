package com.karaoke.mobile.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FastForward
import androidx.compose.material.icons.filled.FastRewind
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Repeat
import androidx.compose.material.icons.filled.RepeatOne
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.model.Syllable
import com.karaoke.mobile.model.formatTime
import com.karaoke.mobile.ui.theme.KaraokeAccent
import com.karaoke.mobile.ui.theme.KaraokeOnSurface
import com.karaoke.mobile.ui.theme.KaraokeOnSurfaceVariant
import com.karaoke.mobile.ui.theme.KaraokePrimary
import com.karaoke.mobile.ui.theme.KaraokeSecondary
import com.karaoke.mobile.ui.theme.KaraokeSurfaceVariant

@Composable
fun InspectorPane(
    currentLine: AssLine?,
    currentSyllable: Syllable?,
    isPlaying: Boolean,
    playbackSpeed: Float,
    playbackPositionMs: Long,
    inPointMs: Long,
    outPointMs: Long,
    loopEnabled: Boolean,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onSetSpeed: (Float) -> Unit,
    onSetInPoint: () -> Unit,
    onSetOutPoint: () -> Unit,
    onToggleLoop: () -> Unit,
    onSnapToLineStart: () -> Unit,
    onSnapToLineEnd: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = KaraokeSurfaceVariant)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Playback controls
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = { onSeek((playbackPositionMs - 5000).coerceAtLeast(0)) }) {
                    Icon(Icons.Default.FastRewind, "Назад 5с", tint = KaraokeOnSurface)
                }

                Button(
                    onClick = onPlayPause,
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(
                        if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                        contentDescription = if (isPlaying) "Пауза" else "Играть"
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(if (isPlaying) "Пауза" else "Играть")
                }

                IconButton(onClick = { onSeek(playbackPositionMs + 5000) }) {
                    Icon(Icons.Default.FastForward, "Вперёд 5с", tint = KaraokeOnSurface)
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Position display
            Text(
                text = formatTime(playbackPositionMs),
                style = MaterialTheme.typography.displayMedium,
                color = KaraokePrimary,
                modifier = Modifier.align(Alignment.CenterHorizontally)
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Speed control
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Speed, contentDescription = null, tint = KaraokeOnSurfaceVariant)
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Скорость: ${String.format("%.1f", playbackSpeed)}×",
                    style = MaterialTheme.typography.bodyLarge,
                    color = KaraokeOnSurface
                )
            }
            Slider(
                value = playbackSpeed,
                onValueChange = onSetSpeed,
                valueRange = 0.5f..1.5f,
                steps = 9,
                modifier = Modifier.padding(horizontal = 8.dp)
            )

            Spacer(modifier = Modifier.height(8.dp))

            // In/Out points
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                OutlinedButton(onClick = onSetInPoint, shape = RoundedCornerShape(8.dp)) {
                    Text("In: ${formatTime(inPointMs)}")
                }
                OutlinedButton(onClick = onSetOutPoint, shape = RoundedCornerShape(8.dp)) {
                    Text("Out: ${formatTime(outPointMs)}")
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            IconButton(
                onClick = onToggleLoop,
                modifier = Modifier.align(Alignment.CenterHorizontally)
            ) {
                Icon(
                    if (loopEnabled) Icons.Default.RepeatOne else Icons.Default.Repeat,
                    "Петля",
                    tint = if (loopEnabled) KaraokeSecondary else KaraokeOnSurfaceVariant
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Current syllable info
            currentSyllable?.let { syl ->
                Text(
                    text = "Текущий слог",
                    style = MaterialTheme.typography.titleLarge,
                    color = KaraokeOnSurface
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "\"${syl.text}\"",
                    style = MaterialTheme.typography.bodyLarge,
                    color = KaraokePrimary
                )
                Text(
                    text = "${formatTime(syl.start)} → ${formatTime(syl.end)} (${syl.duration}мс)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaraokeOnSurfaceVariant
                )
                Spacer(modifier = Modifier.height(8.dp))
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                    OutlinedButton(onClick = onSnapToLineStart, shape = RoundedCornerShape(8.dp)) {
                        Text("К началу строки")
                    }
                    OutlinedButton(onClick = onSnapToLineEnd, shape = RoundedCornerShape(8.dp)) {
                        Text("К концу строки")
                    }
                }
            }
        }
    }
}
