package com.karaoke.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.filled.AudioFile
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.karaoke.mobile.ui.components.EmptyState
import com.karaoke.mobile.ui.components.FilesTab
import com.karaoke.mobile.ui.components.InspectorPane
import com.karaoke.mobile.ui.components.SyllablesTab
import com.karaoke.mobile.ui.components.TimelinePane
import com.karaoke.mobile.ui.theme.KaraokeDark
import com.karaoke.mobile.ui.theme.KaraokeMobileTheme
import com.karaoke.mobile.ui.theme.KaraokeOnSurface
import com.karaoke.mobile.ui.theme.KaraokeOnSurfaceVariant
import com.karaoke.mobile.ui.theme.KaraokePrimary
import com.karaoke.mobile.ui.theme.KaraokeSurface
import com.karaoke.mobile.viewmodel.StudioState

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            KaraokeMobileTheme(darkTheme = true) {
                StudioScreen()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudioScreen(viewModel: StudioState = viewModel()) {
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }
    val lines = viewModel.editor.current.lines
    val currentLine = lines.getOrNull(viewModel.currentLineIndex)
    val currentSyllable = currentLine?.syllables?.getOrNull(viewModel.currentSyllableIndex)

    LaunchedEffect(viewModel.snackbarMessage) {
        viewModel.snackbarMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.dismissSnackbar()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.MusicNote,
                            contentDescription = null,
                            tint = KaraokePrimary,
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Karaoke Studio",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = KaraokeOnSurface
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { viewModel.undo() },
                        enabled = viewModel.editor.canUndo()
                    ) {
                        Icon(
                            Icons.AutoMirrored.Filled.Undo,
                            "Отменить",
                            tint = if (viewModel.editor.canUndo()) KaraokeOnSurface else KaraokeOnSurfaceVariant.copy(alpha = 0.4f)
                        )
                    }
                    IconButton(
                        onClick = { viewModel.redo() },
                        enabled = viewModel.editor.canRedo()
                    ) {
                        Icon(
                            Icons.AutoMirrored.Filled.Redo,
                            "Повторить",
                            tint = if (viewModel.editor.canRedo()) KaraokeOnSurface else KaraokeOnSurfaceVariant.copy(alpha = 0.4f)
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = KaraokeDark,
                    titleContentColor = KaraokeOnSurface
                )
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = KaraokeSurface,
                tonalElevation = 0.dp
            ) {
                NavigationBarItem(
                    icon = { Icon(Icons.Default.Description, contentDescription = null) },
                    label = { Text("Слоги") },
                    selected = viewModel.currentTab == StudioState.StudioTab.SYLLABLES,
                    onClick = { viewModel.setTab(StudioState.StudioTab.SYLLABLES) }
                )
                NavigationBarItem(
                    icon = { Icon(Icons.Default.FolderOpen, contentDescription = null) },
                    label = { Text("Файлы") },
                    selected = viewModel.currentTab == StudioState.StudioTab.FILES,
                    onClick = { viewModel.setTab(StudioState.StudioTab.FILES) }
                )
                NavigationBarItem(
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                    label = { Text("Настройки") },
                    selected = viewModel.currentTab == StudioState.StudioTab.SETTINGS,
                    onClick = { viewModel.setTab(StudioState.StudioTab.SETTINGS) }
                )
            }
        },
        snackbarHost = {
            SnackbarHost(snackbarHostState) { data ->
                Snackbar(
                    snackbarData = data,
                    containerColor = KaraokeSurface,
                    contentColor = KaraokeOnSurface,
                    shape = RoundedCornerShape(12.dp)
                )
            }
        },
        containerColor = KaraokeDark
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(KaraokeDark)
        ) {
            when (viewModel.currentTab) {
                StudioState.StudioTab.SYLLABLES -> {
                    if (lines.isEmpty()) {
                        EmptyState(
                            title = "Нет данных",
                            subtitle = "Загрузите ASS-файл во вкладке «Файлы», чтобы начать редактирование",
                            modifier = Modifier.weight(1f)
                        )
                    } else {
                        // Timeline
                        TimelinePane(
                            waveform = viewModel.waveform,
                            lines = lines,
                            currentLineIndex = viewModel.currentLineIndex,
                            currentSyllableIndex = viewModel.currentSyllableIndex,
                            playbackPositionMs = viewModel.playbackPositionMs,
                            zoomLevel = viewModel.zoomLevel,
                            scrollOffsetMs = viewModel.scrollOffsetMs,
                            viewportDurationMs = viewModel.viewportDurationMs,
                            onSeek = { viewModel.seekTo(it) },
                            onZoomChange = { viewModel.setZoom(it) },
                            onScrollChange = { viewModel.setScrollOffset(it) },
                            onSyllableTap = { lIdx, sIdx -> viewModel.selectSyllable(lIdx, sIdx) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 8.dp)
                        )

                        // Inspector
                        InspectorPane(
                            currentLine = currentLine,
                            currentSyllable = currentSyllable,
                            isPlaying = viewModel.isPlaying,
                            playbackSpeed = viewModel.playbackSpeed,
                            playbackPositionMs = viewModel.playbackPositionMs,
                            inPointMs = viewModel.inPointMs,
                            outPointMs = viewModel.outPointMs,
                            loopEnabled = viewModel.loopEnabled,
                            onPlayPause = { viewModel.playPause() },
                            onSeek = { viewModel.seekTo(it) },
                            onSetSpeed = { viewModel.setPlaybackSpeed(it) },
                            onSetInPoint = { viewModel.setInPoint() },
                            onSetOutPoint = { viewModel.setOutPoint() },
                            onToggleLoop = { viewModel.toggleLoop() },
                            onSnapToLineStart = { currentLine?.let { viewModel.snapToLineStart(it) } },
                            onSnapToLineEnd = { currentLine?.let { viewModel.snapToLineEnd(it) } },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp)
                        )

                        Spacer(modifier = Modifier.height(8.dp))

                        // Syllables list
                        SyllablesTab(
                            lines = lines,
                            currentLineIndex = viewModel.currentLineIndex,
                            currentSyllableIndex = viewModel.currentSyllableIndex,
                            onSelectLine = { viewModel.selectLine(it) },
                            onSelectSyllable = { lIdx, sIdx -> viewModel.selectSyllable(lIdx, sIdx) },
                            onUpdateSyllableText = { lIdx, sIdx, text -> viewModel.updateSyllableText(lIdx, sIdx, text) },
                            onToggleBurst = { lIdx, sIdx -> viewModel.toggleSyllableBurst(lIdx, sIdx) },
                            onSplitSyllable = { lIdx, sIdx, point -> viewModel.splitSyllable(lIdx, sIdx, point) },
                            onMergeSyllables = { lIdx, from, to -> viewModel.mergeSyllables(lIdx, from, to) },
                            onSnapToSyllable = { viewModel.snapToSyllable(it) },
                            modifier = Modifier.weight(1f)
                        )
                    }
                }

                StudioState.StudioTab.FILES -> {
                    FilesTab(
                        lines = lines,
                        audioFileName = viewModel.editor.current.audioFile,
                        onLoadAss = { viewModel.loadAss(it) },
                        onSetAudio = { ctx, uri -> viewModel.setAudio(ctx, uri) },
                        onSaveAss = { viewModel.serializeAss() },
                        modifier = Modifier.fillMaxSize()
                    )
                }

                StudioState.StudioTab.SETTINGS -> {
                    SettingsTab(modifier = Modifier.fillMaxSize())
                }
            }
        }
    }
}

@Composable
fun SettingsTab(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "Настройки",
            style = MaterialTheme.typography.headlineSmall,
            color = KaraokeOnSurface
        )
        InfoCard(
            title = "О приложении",
            content = "Karaoke Mobile Studio v1.0\nРедактор ASS-караоке для Android"
        )
        InfoCard(
            title = "Горячие клавиши",
            content = "Space — Play/Pause\n← → — Навигация по слогам\nCtrl+Z — Отмена\nCtrl+Y — Повтор"
        )
    }
}

@Composable
fun InfoCard(title: String, content: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(KaraokeSurface)
            .padding(16.dp)
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleLarge,
            color = KaraokePrimary,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Text(
            text = content,
            style = MaterialTheme.typography.bodyLarge,
            color = KaraokeOnSurfaceVariant
        )
    }
}
