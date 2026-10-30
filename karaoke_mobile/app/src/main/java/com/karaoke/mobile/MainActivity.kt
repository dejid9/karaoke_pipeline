package com.karaoke.mobile

import android.content.Context
import android.content.Intent
import android.content.res.Configuration
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
import androidx.compose.ui.platform.LocalConfiguration
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
    val configuration = LocalConfiguration.current
    val isLandscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

    val activeSyllable = uiState.syllables.firstOrNull { it.id == uiState.activeSyllableId }
        ?: uiState.syllables.firstOrNull { it.id in uiState.selectedIds }
    val timingSyllable = uiState.syllables.firstOrNull { it.id == uiState.timingEditId }
    val totalDuration = uiState.mediaDuration.coerceAtLeast(
        uiState.syllables.maxOfOrNull { it.end } ?: 300.0
    )

    if (isLandscape) {
        // Ландшафтная ориентация: экран делится 50/50 (слева таймлайны и управление, справа список слогов)
        Row(
            modifier = Modifier
                .fillMaxSize()
                .background(uiState.currentTheme.bg)
        ) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .background(uiState.currentTheme.bg)
            ) {
                // Инфо-панель (SPS из ПК-версии)
                TrackInfoBar(
                    projectName = uiState.project?.name,
                    syllableCount = uiState.syllables.size,
                    activeSyllable = activeSyllable,
                    palette = uiState.currentTheme
                )

                // Обзорный таймлайн всей песни (Overview из ПК-версии)
                OverviewTimeline(
                    duration = totalDuration,
                    scrollOffset = uiState.scrollOffset,
                    zoomLevel = uiState.zoomLevel,
                    waveformData = uiState.waveformData,
                    syllables = uiState.syllables,
                    playbackPosition = uiState.playbackPosition,
                    palette = uiState.currentTheme,
                    onSeekOrScroll = { targetTime ->
                        viewModel.seekTo(targetTime)
                        val pps = 50f * uiState.zoomLevel
                        val targetScroll = (targetTime * pps - (uiState.canvasWidth / 2f)).toFloat().coerceAtLeast(0f)
                        viewModel.setScroll(targetScroll)
                    }
                )

                // Детальный таймлайн
                Timeline(
                    syllables = uiState.syllables,
                    waveformData = uiState.waveformData,
                    playbackPosition = uiState.playbackPosition,
                    duration = totalDuration,
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
                    onCanvasWidthChange = { viewModel.setCanvasWidth(it) },
                    modifier = Modifier.fillMaxWidth()
                )

                // Панель инспектора
                InspectorPane(
                    isPlaying = uiState.isPlaying,
                    playbackPosition = uiState.playbackPosition,
                    playbackSpeed = uiState.playbackSpeed,
                    duration = totalDuration,
                    selectedCount = uiState.selectedIds.size,
                    canUndo = uiState.canUndo,
                    canRedo = uiState.canRedo,
                    palette = uiState.currentTheme,
                    activeTagType = activeSyllable?.tagType ?: uiState.defaultTagType,
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
                    onShowSettings = { viewModel.showSettings() },
                    onShowExport = { viewModel.showExportDialog() },
                    onShowImport = { viewModel.showImportDialog() },
                    onOpenProjects = { viewModel.showProjectsDialog(context) }
                )

                // Оверлей тайминга слога (если открыт)
                if (timingSyllable != null) {
                    TimingEditorDock(
                        syllableText = timingSyllable.displayText,
                        start = uiState.timingStart,
                        end = uiState.timingEnd,
                        maxDuration = totalDuration,
                        palette = uiState.currentTheme,
                        onTimingChange = { s, e -> viewModel.updateTiming(s, e) },
                        onPreview = { left, right -> viewModel.previewSyllableWithContext(timingSyllable.id, left, right) },
                        onClose = { viewModel.closeTimingEdit() }
                    )
                }
            }

            VerticalDivider(color = uiState.currentTheme.border.copy(alpha = 0.35f), thickness = 1.dp)

            // Правая половина: список слогов
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .background(uiState.currentTheme.bg)
            ) {
                SyllablesTab(
                    syllables = uiState.syllables,
                    selectedIds = uiState.selectedIds,
                    activeSyllableId = uiState.activeSyllableId,
                    editTextId = uiState.editTextId,
                    editTextValue = uiState.editTextValue,
                    editTextRomanization = uiState.editTextRomanization,
                    editIsUnspoken = uiState.editIsUnspoken,
                    palette = uiState.currentTheme,
                    onSelect = { id, add -> viewModel.selectSyllable(id, add) },
                    onStartEdit = { viewModel.startEditText(it) },
                    onEditValueChange = { viewModel.updateEditText(it) },
                    onEditRomanizationChange = { viewModel.updateEditRomanization(it) },
                    onToggleEditUnspoken = { viewModel.toggleEditUnspoken() },
                    onCommitEdit = { viewModel.commitEditText() },
                    onCancelEdit = { viewModel.cancelEditText() },
                    onStartTimingEdit = { viewModel.startTimingEdit(it) },
                    onDelete = { viewModel.deleteSyllable(it) },
                    modifier = Modifier.fillMaxSize()
                )
            }
        }
    } else {
        // Портретная ориентация: вертикальный стек
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(uiState.currentTheme.bg)
        ) {
            // Инфо-панель (SPS из ПК-версии)
            TrackInfoBar(
                projectName = uiState.project?.name,
                syllableCount = uiState.syllables.size,
                activeSyllable = activeSyllable,
                palette = uiState.currentTheme
            )

            // Обзорный таймлайн всей песни (Overview из ПК-версии)
            OverviewTimeline(
                duration = totalDuration,
                scrollOffset = uiState.scrollOffset,
                zoomLevel = uiState.zoomLevel,
                waveformData = uiState.waveformData,
                syllables = uiState.syllables,
                playbackPosition = uiState.playbackPosition,
                palette = uiState.currentTheme,
                onSeekOrScroll = { targetTime ->
                    viewModel.seekTo(targetTime)
                    val pps = 50f * uiState.zoomLevel
                    val targetScroll = (targetTime * pps - (uiState.canvasWidth / 2f)).toFloat().coerceAtLeast(0f)
                    viewModel.setScroll(targetScroll)
                }
            )

            // Детальный таймлайн
            Timeline(
                syllables = uiState.syllables,
                waveformData = uiState.waveformData,
                playbackPosition = uiState.playbackPosition,
                duration = totalDuration,
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
                onCanvasWidthChange = { viewModel.setCanvasWidth(it) },
                modifier = Modifier.fillMaxWidth()
            )

            // Панель инспектора
            InspectorPane(
                isPlaying = uiState.isPlaying,
                playbackPosition = uiState.playbackPosition,
                playbackSpeed = uiState.playbackSpeed,
                duration = totalDuration,
                selectedCount = uiState.selectedIds.size,
                canUndo = uiState.canUndo,
                canRedo = uiState.canRedo,
                palette = uiState.currentTheme,
                activeTagType = activeSyllable?.tagType ?: uiState.defaultTagType,
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
                onShowSettings = { viewModel.showSettings() },
                onShowExport = { viewModel.showExportDialog() },
                onShowImport = { viewModel.showImportDialog() },
                onOpenProjects = { viewModel.showProjectsDialog(context) }
            )

            // Список слогов + закреплённый нижний оверлей тайминга
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .background(uiState.currentTheme.bg)
            ) {
                SyllablesTab(
                    syllables = uiState.syllables,
                    selectedIds = uiState.selectedIds,
                    activeSyllableId = uiState.activeSyllableId,
                    editTextId = uiState.editTextId,
                    editTextValue = uiState.editTextValue,
                    editTextRomanization = uiState.editTextRomanization,
                    editIsUnspoken = uiState.editIsUnspoken,
                    palette = uiState.currentTheme,
                    onSelect = { id, add -> viewModel.selectSyllable(id, add) },
                    onStartEdit = { viewModel.startEditText(it) },
                    onEditValueChange = { viewModel.updateEditText(it) },
                    onEditRomanizationChange = { viewModel.updateEditRomanization(it) },
                    onToggleEditUnspoken = { viewModel.toggleEditUnspoken() },
                    onCommitEdit = { viewModel.commitEditText() },
                    onCancelEdit = { viewModel.cancelEditText() },
                    onStartTimingEdit = { viewModel.startTimingEdit(it) },
                    onDelete = { viewModel.deleteSyllable(it) },
                    modifier = Modifier.fillMaxSize()
                )

                if (timingSyllable != null) {
                    TimingEditorDock(
                        syllableText = timingSyllable.displayText,
                        start = uiState.timingStart,
                        end = uiState.timingEnd,
                        maxDuration = totalDuration,
                        palette = uiState.currentTheme,
                        onTimingChange = { s, e -> viewModel.updateTiming(s, e) },
                        onPreview = { left, right -> viewModel.previewSyllableWithContext(timingSyllable.id, left, right) },
                        onClose = { viewModel.closeTimingEdit() },
                        modifier = Modifier.align(Alignment.BottomCenter)
                    )
                }
            }
        }
    }
}
