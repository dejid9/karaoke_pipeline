package com.karaoke.mobile

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.ui.components.*
import com.karaoke.mobile.viewmodel.StudioUiState
import com.karaoke.mobile.ui.theme.KaraokeMobileTheme
import com.karaoke.mobile.ui.theme.NavyDarkPalette
import com.karaoke.mobile.viewmodel.StudioEvent
import com.karaoke.mobile.viewmodel.StudioState
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val viewModel: StudioState by viewModels()

    // Лаунчеры для выбора файлов
    private val pickMediaLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let { viewModel.setMedia(it, this) }
    }

    private val pickAssLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let { viewModel.loadAss(it, this) }
    }

    private val exportProjectLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/zip")
    ) { uri: Uri? ->
        uri?.let { viewModel.exportProject(this, it) }
    }

    private val exportAssLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("text/plain")
    ) { uri: Uri? ->
        uri?.let { viewModel.exportAss(this, it) }
    }

    private val importProjectLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let { viewModel.importProject(this, it) }
    }

    private val importAssLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let { viewModel.loadAss(it, this) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Обработка событий ViewModel
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.events.collect { event ->
                    when (event) {
                        is StudioEvent.ShowError -> {
                            // Показываем через Snackbar или Toast
                        }
                        is StudioEvent.ShowSuccess -> {
                            // Показываем через Snackbar или Toast
                        }
                        is StudioEvent.RequestMediaPick -> {
                            pickMediaLauncher.launch("audio/*")
                        }
                        is StudioEvent.ShareFile -> {
                            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                                type = "*/*"
                                putExtra(Intent.EXTRA_STREAM, event.uri)
                            }
                            startActivity(Intent.createChooser(shareIntent, "Поделиться"))
                        }
                    }
                }
            }
        }

        setContent {
            val uiState by viewModel.uiState
            val context = LocalContext.current

            KaraokeMobileTheme(palette = uiState.currentTheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    Box(modifier = Modifier.fillMaxSize()) {
                        if (uiState.syllables.isEmpty() && uiState.project == null) {
                            // Пустое состояние
                            EmptyState(
                                palette = uiState.currentTheme,
                                onCreateProject = {
                                    viewModel.createNewProject("project-${System.currentTimeMillis()}", context)
                                },
                                onOpenProject = {
                                    // TODO: показать список проектов
                                },
                                onImportProject = {
                                    importProjectLauncher.launch("application/zip")
                                },
                                onLoadAss = {
                                    pickAssLauncher.launch("text/plain")
                                }
                            )
                        } else {
                            // Основной интерфейс студии
                            StudioScreen(
                                uiState = uiState,
                                viewModel = viewModel,
                                onPickMedia = { pickMediaLauncher.launch("audio/*") },
                                onPickAss = { pickAssLauncher.launch("text/plain") }
                            )
                        }

                        // Диалоги
                        if (uiState.showThemePicker) {
                            ThemePickerDialog(
                                currentTheme = uiState.currentTheme,
                                onThemeSelected = { viewModel.setTheme(it) },
                                onDismiss = { viewModel.hideThemePicker() }
                            )
                        }

                        if (uiState.showExportDialog) {
                            ExportImportDialog(
                                isExport = true,
                                palette = uiState.currentTheme,
                                onExportProject = {
                                    exportProjectLauncher.launch("karaoke-project.zip")
                                    viewModel.hideExportDialog()
                                },
                                onExportAss = {
                                    exportAssLauncher.launch("subtitles.ass")
                                    viewModel.hideExportDialog()
                                },
                                onImportProject = {},
                                onImportAss = {},
                                onDismiss = { viewModel.hideExportDialog() }
                            )
                        }

                        if (uiState.showImportDialog) {
                            ExportImportDialog(
                                isExport = false,
                                palette = uiState.currentTheme,
                                onExportProject = {},
                                onExportAss = {},
                                onImportProject = {
                                    importProjectLauncher.launch("application/zip")
                                    viewModel.hideImportDialog()
                                },
                                onImportAss = {
                                    importAssLauncher.launch("text/plain")
                                    viewModel.hideImportDialog()
                                },
                                onDismiss = { viewModel.hideImportDialog() }
                            )
                        }

                        if (uiState.showTimingEditor) {
                            TimingEditorDialog(
                                start = uiState.timingStart,
                                end = uiState.timingEnd,
                                palette = uiState.currentTheme,
                                onStartChange = { viewModel.updateTiming(it, uiState.timingEnd) },
                                onEndChange = { viewModel.updateTiming(uiState.timingStart, it) },
                                onConfirm = { viewModel.commitTiming() },
                                onDismiss = { viewModel.cancelTimingEdit() }
                            )
                        }

                        // Сообщения
                        Box(
                            modifier = Modifier
                                .align(Alignment.BottomCenter)
                                .padding(16.dp)
                        ) {
                            uiState.errorMessage?.let {
                                MessageSnackbar(
                                    message = it,
                                    isError = true,
                                    palette = uiState.currentTheme,
                                    onDismiss = { viewModel.clearMessage() }
                                )
                            }
                            uiState.successMessage?.let {
                                MessageSnackbar(
                                    message = it,
                                    isError = false,
                                    palette = uiState.currentTheme,
                                    onDismiss = { viewModel.clearMessage() }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StudioScreen(
    uiState: StudioUiState,
    viewModel: StudioState,
    onPickMedia: () -> Unit,
    onPickAss: () -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Таймлайн
        Timeline(
            syllables = uiState.syllables,
            waveformData = uiState.waveformData,
            playbackPosition = uiState.playbackPosition,
            duration = uiState.mediaDuration.coerceAtLeast(
                uiState.syllables.maxOfOrNull { it.end } ?: 300.0
            ),
            zoomLevel = uiState.zoomLevel,
            scrollOffset = uiState.scrollOffset,
            selectedIds = uiState.selectedIds,
            activeSyllableId = uiState.activeSyllableId,
            palette = uiState.currentTheme,
            onSeek = { viewModel.seekTo(it) },
            onSelectSyllable = { id ->
                viewModel.selectSyllable(id, addToSelection = false)
            },
            onZoomChange = { viewModel.setZoom(it) },
            onScrollChange = { viewModel.setScroll(it) },
            modifier = Modifier.fillMaxWidth()
        )

        // Инспектор / панель управления
        InspectorPane(
            isPlaying = uiState.isPlaying,
            playbackPosition = uiState.playbackPosition,
            playbackSpeed = uiState.playbackSpeed,
            duration = uiState.mediaDuration.coerceAtLeast(
                uiState.syllables.maxOfOrNull { it.end } ?: 300.0
            ),
            selectedCount = uiState.selectedIds.size,
            canUndo = uiState.canUndo,
            canRedo = uiState.canRedo,
            palette = uiState.currentTheme,
            onPlayPause = { viewModel.togglePlayback() },
            onStop = { viewModel.stopPlayback() },
            onSeek = { viewModel.seekTo(it) },
            onSpeedChange = { viewModel.setPlaybackSpeed(it) },
            onUndo = { viewModel.undo() },
            onRedo = { viewModel.redo() },
            onSplit = {
                uiState.activeSyllableId?.let { viewModel.splitSyllable(it) }
            },
            onMerge = { viewModel.mergeSelected() },
            onInsert = { viewModel.insertSyllable() },
            onSetTagType = { viewModel.setTagType(it) },
            onToggleUnspoken = { viewModel.toggleUnspoken() },
            onShowSettings = { viewModel.showSettings() },
            onShowThemes = { viewModel.showThemePicker() },
            onShowExport = { viewModel.showExportDialog() },
            onShowImport = { viewModel.showImportDialog() }
        )

        // Список слогов
        SyllablesTab(
            syllables = uiState.syllables,
            selectedIds = uiState.selectedIds,
            activeSyllableId = uiState.activeSyllableId,
            editTextId = uiState.editTextId,
            editTextValue = uiState.editTextValue,
            palette = uiState.currentTheme,
            onSelect = { id, add -> viewModel.selectSyllable(id, add) },
            onStartEdit = { viewModel.startEditText(it) },
            onEditValueChange = { viewModel.updateEditText(it) },
            onCommitEdit = { viewModel.commitEditText() },
            onCancelEdit = { viewModel.cancelEditText() },
            onStartTimingEdit = { viewModel.startTimingEdit(it) },
            onDelete = { viewModel.deleteSyllable(it) },
            modifier = Modifier.weight(1f)
        )
    }
}
