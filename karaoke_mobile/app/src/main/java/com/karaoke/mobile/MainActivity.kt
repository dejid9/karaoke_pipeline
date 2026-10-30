package com.karaoke.mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
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

    companion object {
        val ZIP_MIME_TYPES = arrayOf(
            "application/zip",
            "application/x-zip",
            "application/x-zip-compressed",
            "application/octet-stream",
            "*/*"
        )
        val ASS_MIME_TYPES = arrayOf(
            "text/plain",
            "text/*",
            "application/octet-stream",
            "*/*"
        )
        val MEDIA_MIME_TYPES = arrayOf(
            "audio/*",
            "video/*",
            "application/octet-stream",
            "*/*"
        )
    }

    private val viewModel: StudioState by viewModels()

    // Лаунчеры для выбора файлов (OpenDocument обеспечивает универсальный выбор на всех версиях Android)
    private val pickMediaLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        uri?.let { viewModel.setMedia(it, this) }
    }

    private val pickAssLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
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
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) {
            try {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            } catch (e: Exception) {
                // Ignore if not supported by provider
            }
            viewModel.importProject(this, uri)
        }
    }

    private val importAssLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
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
                            Toast.makeText(this@MainActivity, event.message, Toast.LENGTH_LONG).show()
                        }
                        is StudioEvent.ShowSuccess -> {
                            Toast.makeText(this@MainActivity, event.message, Toast.LENGTH_SHORT).show()
                        }
                        is StudioEvent.RequestMediaPick -> {
                            pickMediaLauncher.launch(MEDIA_MIME_TYPES)
                        }
                        is StudioEvent.ShareFile -> {
                            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                                type = "*/*"
                                putExtra(Intent.EXTRA_STREAM, event.uri)
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
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
                                    viewModel.showProjectsDialog(context)
                                },
                                onImportProject = {
                                    importProjectLauncher.launch(ZIP_MIME_TYPES)
                                },
                                onLoadAss = {
                                    pickAssLauncher.launch(ASS_MIME_TYPES)
                                }
                            )
                        } else {
                            // Основной интерфейс студии
                            StudioScreen(
                                uiState = uiState,
                                viewModel = viewModel,
                                onPickMedia = { pickMediaLauncher.launch(MEDIA_MIME_TYPES) },
                                onPickAss = { pickAssLauncher.launch(ASS_MIME_TYPES) }
                            )
                        }

                        // Диалоги
                        if (uiState.showProjectsDialog) {
                            ProjectsListDialog(
                                projects = uiState.savedProjects,
                                palette = uiState.currentTheme,
                                onSelectProject = { projectId ->
                                    viewModel.loadProject(projectId, context)
                                    viewModel.hideProjectsDialog()
                                },
                                onDeleteProject = { projectId ->
                                    viewModel.deleteProject(projectId, context)
                                },
                                onImportZip = {
                                    viewModel.hideProjectsDialog()
                                    importProjectLauncher.launch(ZIP_MIME_TYPES)
                                },
                                onDismiss = { viewModel.hideProjectsDialog() }
                            )
                        }
                        if (uiState.showSettings) {
                            SettingsDialog(
                                autoScroll = uiState.autoScroll,
                                defaultTagType = uiState.defaultTagType,
                                palette = uiState.currentTheme,
                                onToggleAutoScroll = { viewModel.toggleAutoScroll() },
                                onSetDefaultTagType = { viewModel.setDefaultTagType(it) },
                                onOpenThemes = {
                                    viewModel.hideSettings()
                                    viewModel.showThemePicker()
                                },
                                onDismiss = { viewModel.hideSettings() }
                            )
                        }
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
                                    importProjectLauncher.launch(ZIP_MIME_TYPES)
                                    viewModel.hideImportDialog()
                                },
                                onImportAss = {
                                    importAssLauncher.launch(ASS_MIME_TYPES)
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
    val context = LocalContext.current
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

        // Активный слог для отображения в панели инспектора
        val activeSyllable = uiState.syllables.firstOrNull { it.id == uiState.activeSyllableId }
            ?: uiState.syllables.firstOrNull { it.id in uiState.selectedIds }

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
            activeTagType = activeSyllable?.tagType ?: uiState.defaultTagType,
            isCurrentUnspoken = activeSyllable?.isUnspoken ?: false,
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
            onShowImport = { viewModel.showImportDialog() },
            onOpenProjects = { viewModel.showProjectsDialog(context) }
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
