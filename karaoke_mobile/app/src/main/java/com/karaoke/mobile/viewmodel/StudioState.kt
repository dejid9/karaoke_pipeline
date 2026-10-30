package com.karaoke.mobile.viewmodel

import android.content.Context
import android.net.Uri
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.karaoke.mobile.model.*
import com.karaoke.mobile.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.BufferedReader
import java.io.File
import java.io.FileInputStream
import java.io.InputStreamReader
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/**
 * Краткая информация о сохранённом проекте
 */
data class ProjectSummary(
    val id: String,
    val name: String,
    val modifiedAt: Long,
    val subtitlePath: String? = null,
    val mediaPath: String? = null
)

/**
 * Состояние UI студии
 */
data class StudioUiState(
    val project: KaraokeProject? = null,
    val document: AssDocument = AssDocument(),
    val syllables: List<KaraokeSyllable> = emptyList(),
    val selectedIds: Set<String> = emptySet(),
    val activeSyllableId: String? = null,
    val playbackPosition: Double = 0.0,
    val isPlaying: Boolean = false,
    val playbackSpeed: Float = 1.0f,
    val mediaDuration: Double = 0.0,
    val currentTheme: KaraokeThemePalette = NavyDarkPalette,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val successMessage: String? = null,
    val showSettings: Boolean = false,
    val showThemePicker: Boolean = false,
    val showExportDialog: Boolean = false,
    val showImportDialog: Boolean = false,
    val showProjectsDialog: Boolean = false,
    val savedProjects: List<ProjectSummary> = emptyList(),
    val editTextId: String? = null,
    val editTextValue: String = "",
    val showTimingEditor: Boolean = false,
    val timingEditId: String? = null,
    val timingStart: Double = 0.0,
    val timingEnd: Double = 0.0,
    val waveformData: List<Float> = emptyList(),
    val zoomLevel: Float = 1.0f,
    val scrollOffset: Float = 0.0f,
    val showHelp: Boolean = false,
    val canUndo: Boolean = false,
    val canRedo: Boolean = false
)

/**
 * События навигации/эффектов
 */
sealed class StudioEvent {
    data class ShowError(val message: String) : StudioEvent()
    data class ShowSuccess(val message: String) : StudioEvent()
    data class RequestMediaPick(val forExport: Boolean = false) : StudioEvent()
    data class ShareFile(val uri: Uri) : StudioEvent()
}

class StudioState : ViewModel() {

    private val _uiState = mutableStateOf(StudioUiState())
    val uiState = _uiState

    private val _events = MutableSharedFlow<StudioEvent>()
    val events: SharedFlow<StudioEvent> = _events

    private var editor: AssEditor = AssEditor()
    private var mediaPlayer: android.media.MediaPlayer? = null

    // --- Проекты ---

    fun createNewProject(name: String, context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            val projectDir = File(context.filesDir, "projects/$name")
            projectDir.mkdirs()
            val project = KaraokeProject(
                name = name,
                subtitlePath = File(projectDir, "subtitles.ass").absolutePath
            )
            saveProjectToDisk(project, context)
            withContext(Dispatchers.Main) {
                _uiState.value = _uiState.value.copy(
                    project = project,
                    document = AssDocument(),
                    syllables = emptyList(),
                    selectedIds = emptySet(),
                    successMessage = "Проект создан"
                )
            }
        }
    }

    fun loadProject(projectId: String, context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val projectDir = File(context.filesDir, "projects/$projectId")
                val projectFile = File(projectDir, "project.json")
                if (!projectFile.exists()) {
                    withContext(Dispatchers.Main) {
                        _events.emit(StudioEvent.ShowError("Проект не найден"))
                    }
                    return@launch
                }
                val json = JSONObject(projectFile.readText().removePrefix("\uFEFF"))
                val project = KaraokeProject(
                    id = json.optString("id").takeIf { it.isNotBlank() } ?: projectId,
                    name = json.optString("name").takeIf { it.isNotBlank() } ?: projectDir.name,
                    mediaPath = json.optString("mediaPath").takeIf { it.isNotBlank() } ?: json.optString("media").takeIf { it.isNotBlank() },
                    subtitlePath = json.optString("subtitlePath").takeIf { it.isNotBlank() } ?: json.optString("subtitles").takeIf { it.isNotBlank() },
                    createdAt = json.optLong("createdAt", projectDir.lastModified()),
                    modifiedAt = json.optLong("modifiedAt", System.currentTimeMillis())
                )

                var document = AssDocument()
                var syllables = emptyList<KaraokeSyllable>()

                // Поиск файла субтитров (по абсолютному или относительному пути, либо первый .ass в папке)
                val subFile = project.subtitlePath?.let { path ->
                    File(path).takeIf { it.exists() } ?: File(projectDir, path).takeIf { it.exists() }
                } ?: projectDir.listFiles()?.find { it.extension.equals("ass", ignoreCase = true) }

                if (subFile != null && subFile.exists()) {
                    document = AssParser.parse(subFile.readText().removePrefix("\uFEFF"))
                    syllables = document.events.flatMap { it.syllables }
                }

                editor = AssEditor(syllables)

                // Поиск медиафайла
                val mediaFile = project.mediaPath?.let { path ->
                    File(path).takeIf { it.exists() } ?: File(projectDir, path).takeIf { it.exists() }
                }

                withContext(Dispatchers.Main) {
                    if (mediaFile != null && mediaFile.exists()) {
                        setMediaFile(mediaFile)
                    }
                    _uiState.value = _uiState.value.copy(
                        project = project.copy(
                            subtitlePath = subFile?.absolutePath,
                            mediaPath = mediaFile?.absolutePath,
                            document = document
                        ),
                        document = document,
                        syllables = syllables,
                        selectedIds = emptySet(),
                        activeSyllableId = null,
                        canUndo = editor.canUndo,
                        canRedo = editor.canRedo,
                        successMessage = "Проект «${project.name}» загружен"
                    )
                    _events.emit(StudioEvent.ShowSuccess("Проект «${project.name}» загружен"))
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _events.emit(StudioEvent.ShowError("Ошибка загрузки: ${e.message}"))
                }
            }
        }
    }

    fun showProjectsDialog(context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            val projects = getSavedProjects(context)
            withContext(Dispatchers.Main) {
                _uiState.value = _uiState.value.copy(
                    showProjectsDialog = true,
                    savedProjects = projects
                )
            }
        }
    }

    fun hideProjectsDialog() {
        _uiState.value = _uiState.value.copy(showProjectsDialog = false)
    }

    fun deleteProject(projectId: String, context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            val dir = File(context.filesDir, "projects/$projectId")
            if (dir.exists()) {
                dir.deleteRecursively()
            }
            val projects = getSavedProjects(context)
            withContext(Dispatchers.Main) {
                _uiState.value = _uiState.value.copy(savedProjects = projects)
                _events.emit(StudioEvent.ShowSuccess("Проект удалён"))
            }
        }
    }

    fun getSavedProjects(context: Context): List<ProjectSummary> {
        val projectsDir = File(context.filesDir, "projects")
        if (!projectsDir.exists()) return emptyList()
        val list = mutableListOf<ProjectSummary>()
        projectsDir.listFiles()?.forEach { dir ->
            if (dir.isDirectory) {
                val projectJson = File(dir, "project.json")
                if (projectJson.exists()) {
                    try {
                        val json = JSONObject(projectJson.readText().removePrefix("\uFEFF"))
                        val name = json.optString("name").takeIf { it.isNotBlank() } ?: dir.name
                        val id = json.optString("id").takeIf { it.isNotBlank() } ?: dir.name
                        val modifiedAt = json.optLong("modifiedAt", dir.lastModified())
                        val subPath = json.optString("subtitlePath").takeIf { it.isNotBlank() }
                            ?: json.optString("subtitles").takeIf { it.isNotBlank() }
                        val medPath = json.optString("mediaPath").takeIf { it.isNotBlank() }
                            ?: json.optString("media").takeIf { it.isNotBlank() }
                        list.add(ProjectSummary(id = id, name = name, modifiedAt = modifiedAt, subtitlePath = subPath, mediaPath = medPath))
                    } catch (e: Exception) {
                        list.add(ProjectSummary(id = dir.name, name = dir.name, modifiedAt = dir.lastModified()))
                    }
                } else {
                    list.add(ProjectSummary(id = dir.name, name = dir.name, modifiedAt = dir.lastModified()))
                }
            }
        }
        return list.sortedByDescending { it.modifiedAt }
    }

    fun saveProject(context: Context) {
        val project = _uiState.value.project ?: return
        viewModelScope.launch(Dispatchers.IO) {
            try {
                // Обновляем документ из слогов
                val updatedDocument = rebuildDocumentFromSyllables()
                val subtitleFile = File(project.subtitlePath ?: return@launch)
                subtitleFile.parentFile?.mkdirs()
                subtitleFile.writeText(updatedDocument.toAssText())

                saveProjectToDisk(project.copy(modifiedAt = System.currentTimeMillis()), context)

                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(
                        document = updatedDocument,
                        canUndo = editor.canUndo,
                        canRedo = editor.canRedo,
                        successMessage = "Проект сохранён"
                    )
                }
            } catch (e: Exception) {
                _events.emit(StudioEvent.ShowError("Ошибка сохранения: ${e.message}"))
            }
        }
    }

    fun exportProject(context: Context, uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val project = _uiState.value.project ?: return@launch
                context.contentResolver.openOutputStream(uri)?.use { output ->
                    ZipOutputStream(BufferedOutputStream(output)).use { zip ->
                        // subtitles.ass
                        val doc = rebuildDocumentFromSyllables()
                        zip.putNextEntry(ZipEntry("subtitles.ass"))
                        zip.write(doc.toAssText().toByteArray())
                        zip.closeEntry()

                        // media (если есть)
                        var relMediaPath: String? = null
                        project.mediaPath?.let { mediaPath ->
                            val mediaFile = File(mediaPath)
                            if (mediaFile.exists()) {
                                relMediaPath = "media/${mediaFile.name}"
                                zip.putNextEntry(ZipEntry(relMediaPath))
                                mediaFile.inputStream().use { it.copyTo(zip) }
                                zip.closeEntry()
                            }
                        }

                        // project.json
                        zip.putNextEntry(ZipEntry("project.json"))
                        val json = JSONObject().apply {
                            put("id", project.id)
                            put("name", project.name)
                            if (relMediaPath != null) {
                                put("mediaPath", relMediaPath)
                                put("media", relMediaPath)
                            }
                            put("subtitlePath", "subtitles.ass")
                            put("subtitles", "subtitles.ass")
                            put("createdAt", project.createdAt)
                            put("modifiedAt", System.currentTimeMillis())
                        }
                        zip.write(json.toString(2).toByteArray())
                        zip.closeEntry()
                    }
                }
                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(successMessage = "Проект экспортирован")
                    _events.emit(StudioEvent.ShowSuccess("Проект экспортирован"))
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _events.emit(StudioEvent.ShowError("Ошибка экспорта: ${e.message}"))
                }
            }
        }
    }

    fun importProject(context: Context, uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            val projectId = UUID.randomUUID().toString()
            val projectDir = File(context.filesDir, "projects/$projectId")
            projectDir.mkdirs()

            val tempZip = File(context.cacheDir, "import_${projectId}.zip")
            val extractedFiles = mutableListOf<File>()

            try {
                // 1. Надёжно считываем файл из ContentResolver в локальный файл кэша.
                // Сначала пробуем openFileDescriptor (прямой доступ к дескриптору Android),
                // если недоступен — обычный openInputStream.
                var bytesCopied = 0L
                try {
                    val pfd = context.contentResolver.openFileDescriptor(uri, "r")
                    if (pfd != null) {
                        pfd.use { desc ->
                            FileInputStream(desc.fileDescriptor).use { fis ->
                                tempZip.outputStream().use { out ->
                                    bytesCopied = fis.copyTo(out)
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    // Игнорируем и пробуем openInputStream
                }

                if (bytesCopied == 0L) {
                    try {
                        context.contentResolver.openInputStream(uri)?.use { stream ->
                            tempZip.outputStream().use { out ->
                                bytesCopied = stream.copyTo(out)
                            }
                        }
                    } catch (e: Exception) {
                        // ignore
                    }
                }

                if (!tempZip.exists() || tempZip.length() == 0L) {
                    withContext(Dispatchers.Main) {
                        _events.emit(StudioEvent.ShowError("Не удалось получить файл (размер 0 байт или нет доступа к хранилищу)"))
                    }
                    projectDir.deleteRecursively()
                    return@launch
                }

                // 2. Распаковка через ZipFile (чтение таблицы Central Directory — надёжно для любых архивов)
                var zipReadSuccess = false
                try {
                    ZipFile(tempZip).use { zipFile ->
                        val entries = zipFile.entries()
                        while (entries.hasMoreElements()) {
                            val entry = entries.nextElement()
                            val entryName = entry.name
                            if (!entry.isDirectory && !entryName.startsWith("__MACOSX") && !File(entryName).name.startsWith("._")) {
                                val cleanName = entryName.replace('\\', '/').trimStart('/')
                                val outFile = File(projectDir, cleanName)
                                outFile.parentFile?.mkdirs()
                                zipFile.getInputStream(entry).use { inStream ->
                                    outFile.outputStream().use { outStream ->
                                        inStream.copyTo(outStream)
                                    }
                                }
                                extractedFiles.add(outFile)
                            }
                        }
                    }
                    zipReadSuccess = extractedFiles.isNotEmpty()
                } catch (e: Exception) {
                    // Пробуем потоковый fallback
                }

                // 3. Fallback через ZipInputStream, если ZipFile не смог прочитать архив
                if (!zipReadSuccess) {
                    try {
                        FileInputStream(tempZip).use { fis ->
                            ZipInputStream(BufferedInputStream(fis)).use { zis ->
                                var entry = zis.nextEntry
                                while (entry != null) {
                                    val entryName = entry.name
                                    if (!entry.isDirectory && !entryName.startsWith("__MACOSX") && !File(entryName).name.startsWith("._")) {
                                        val cleanName = entryName.replace('\\', '/').trimStart('/')
                                        val outFile = File(projectDir, cleanName)
                                        outFile.parentFile?.mkdirs()
                                        outFile.outputStream().use { out ->
                                            zis.copyTo(out)
                                        }
                                        extractedFiles.add(outFile)
                                    }
                                    zis.closeEntry()
                                    entry = zis.nextEntry
                                }
                            }
                        }
                    } catch (e: Exception) {
                        // ignore
                    }
                }

                if (extractedFiles.isEmpty()) {
                    withContext(Dispatchers.Main) {
                        _events.emit(StudioEvent.ShowError("Архив пуст или не удалось прочитать zip (размер: ${tempZip.length()} байт)"))
                    }
                    projectDir.deleteRecursively()
                    return@launch
                }

                val audioExtensions = setOf("mp3", "wav", "ogg", "flac", "m4a", "aac", "opus")
                val videoExtensions = setOf("mp4", "mkv", "webm", "avi", "mov")

                val projectJsonFile = extractedFiles.find { it.name.equals("project.json", ignoreCase = true) }
                val assFiles = extractedFiles.filter { it.extension.equals("ass", ignoreCase = true) }
                val mediaFiles = extractedFiles.filter {
                    val ext = it.extension.lowercase()
                    ext in audioExtensions || ext in videoExtensions
                }

                // Отсеиваем служебные/промежуточные каталоги (MFA alignment, cache, backup)
                val usableAssFiles = assFiles.filter { file ->
                    val p = file.path.replace('\\', '/')
                    !p.contains("/backup", ignoreCase = true)
                }.ifEmpty { assFiles }

                val usableMediaFiles = mediaFiles.filter { file ->
                    val p = file.path.replace('\\', '/')
                    !p.contains("/alignment/", ignoreCase = true) &&
                    !p.contains("/mfa/", ignoreCase = true) &&
                    !p.contains("/cache/", ignoreCase = true) &&
                    !p.contains("/temp/", ignoreCase = true) &&
                    !p.contains("/corpus/", ignoreCase = true)
                }.ifEmpty { mediaFiles }

                var projectName: String? = null
                var mediaPathCandidate: String? = null
                var subPathCandidate: String? = null
                var createdAt = System.currentTimeMillis()

                if (projectJsonFile != null && projectJsonFile.exists()) {
                    try {
                        val rawJson = projectJsonFile.readText().removePrefix("\uFEFF")
                        val json = JSONObject(rawJson)
                        if (json.has("name") && !json.isNull("name")) {
                            projectName = json.getString("name")
                        }
                        if (json.has("mediaPath") && !json.isNull("mediaPath")) {
                            mediaPathCandidate = json.getString("mediaPath")
                        } else if (json.has("media") && !json.isNull("media")) {
                            mediaPathCandidate = json.getString("media")
                        }
                        if (json.has("subtitlePath") && !json.isNull("subtitlePath")) {
                            subPathCandidate = json.getString("subtitlePath")
                        } else if (json.has("subtitles") && !json.isNull("subtitles")) {
                            subPathCandidate = json.getString("subtitles")
                        }
                        if (json.has("createdAt") && !json.isNull("createdAt")) {
                            createdAt = json.optLong("createdAt", createdAt)
                        }
                    } catch (e: Exception) {
                        // Игнорируем ошибки парсинга json и используем файлы напрямую
                    }
                }

                // Поиск файла субтитров .ass
                var chosenAssFile: File? = null
                if (!subPathCandidate.isNullOrBlank()) {
                    val subName = File(subPathCandidate).name
                    chosenAssFile = extractedFiles.find { it.name.equals(subName, ignoreCase = true) }
                        ?: File(projectDir, subPathCandidate).takeIf { it.exists() }
                }
                if (chosenAssFile == null) {
                    chosenAssFile = usableAssFiles.find { it.name.equals("subtitles.ass", ignoreCase = true) }
                        ?: usableAssFiles.firstOrNull()
                }

                // Поиск медиа-файла (приоритет: project.json -> имя ass -> vocals -> первое доступное аудио)
                var chosenMediaFile: File? = null
                if (!mediaPathCandidate.isNullOrBlank()) {
                    val mediaName = File(mediaPathCandidate).name
                    chosenMediaFile = extractedFiles.find { it.name.equals(mediaName, ignoreCase = true) }
                        ?: File(projectDir, mediaPathCandidate).takeIf { it.exists() }
                }
                if (chosenMediaFile == null) {
                    chosenMediaFile = usableMediaFiles.find { it.nameWithoutExtension.equals(chosenAssFile?.nameWithoutExtension, ignoreCase = true) }
                        ?: usableMediaFiles.find { it.name.contains("vocal", ignoreCase = true) }
                        ?: usableMediaFiles.find { it.extension.lowercase() in audioExtensions }
                        ?: usableMediaFiles.firstOrNull()
                }

                if (chosenAssFile == null && chosenMediaFile == null) {
                    withContext(Dispatchers.Main) {
                        _events.emit(StudioEvent.ShowError("В архиве не найдены файлы караоке (.ass) или аудио"))
                    }
                    return@launch
                }

                if (projectName.isNullOrBlank()) {
                    projectName = chosenAssFile?.nameWithoutExtension
                        ?: chosenMediaFile?.nameWithoutExtension
                        ?: "Импортированный проект"
                }

                var document = AssDocument()
                var syllables = emptyList<KaraokeSyllable>()
                if (chosenAssFile != null && chosenAssFile.exists()) {
                    try {
                        val assText = chosenAssFile.readText().removePrefix("\uFEFF")
                        document = AssParser.parse(assText)
                        syllables = document.events.flatMap { it.syllables }
                    } catch (e: Exception) {
                        // Ошибка парсинга ASS
                    }
                }
                editor = AssEditor(syllables)

                val project = KaraokeProject(
                    id = projectId,
                    name = projectName,
                    mediaPath = chosenMediaFile?.absolutePath,
                    subtitlePath = chosenAssFile?.absolutePath,
                    document = document,
                    createdAt = createdAt,
                    modifiedAt = System.currentTimeMillis()
                )

                saveProjectToDisk(project, context)

                withContext(Dispatchers.Main) {
                    if (chosenMediaFile != null && chosenMediaFile.exists()) {
                        setMediaFile(chosenMediaFile)
                    }
                    _uiState.value = _uiState.value.copy(
                        project = project,
                        document = document,
                        syllables = syllables,
                        selectedIds = emptySet(),
                        activeSyllableId = null,
                        canUndo = editor.canUndo,
                        canRedo = editor.canRedo,
                        successMessage = "Проект «${project.name}» загружен"
                    )
                    _events.emit(StudioEvent.ShowSuccess("Проект «${project.name}» импортирован"))
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _events.emit(StudioEvent.ShowError("Ошибка импорта: ${e.message ?: e.toString()}"))
                }
            } finally {
                tempZip.delete()
            }
        }
    }

    fun exportAss(context: Context, uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val doc = rebuildDocumentFromSyllables()
                context.contentResolver.openOutputStream(uri)?.use {
                    it.write(doc.toAssText().toByteArray())
                }
                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(successMessage = "ASS экспортирован")
                }
            } catch (e: Exception) {
                _events.emit(StudioEvent.ShowError("Ошибка экспорта ASS: ${e.message}"))
            }
        }
    }

    private fun saveProjectToDisk(project: KaraokeProject, context: Context) {
        val projectDir = File(context.filesDir, "projects/${project.id}")
        projectDir.mkdirs()
        val projectFile = File(projectDir, "project.json")
        val json = JSONObject().apply {
            put("id", project.id)
            put("name", project.name)
            put("mediaPath", project.mediaPath)
            put("subtitlePath", project.subtitlePath)
            put("createdAt", project.createdAt)
            put("modifiedAt", project.modifiedAt)
        }
        projectFile.writeText(json.toString(2))
    }

    private fun rebuildDocumentFromSyllables(): AssDocument {
        val current = _uiState.value.document
        val syllables = editor.getAllSyllables()
        if (syllables.isEmpty()) return current

        // Сохраняем атрибуты первого события (стиль, автор, отступы и т.д.)
        val baseEvent = current.events.firstOrNull() ?: AssEvent()
        val event = baseEvent.copy(
            start = syllables.first().start,
            end = syllables.last().end,
            syllables = syllables,
            text = AssParser.serializeSyllables(syllables)
        )
        return current.copy(events = listOf(event))
    }

    // --- Редактирование слогов ---

    fun selectSyllable(id: String, addToSelection: Boolean = false) {
        val current = _uiState.value
        val newSelection = if (addToSelection) {
            if (id in current.selectedIds) current.selectedIds - id else current.selectedIds + id
        } else {
            setOf(id)
        }
        _uiState.value = current.copy(
            selectedIds = newSelection,
            activeSyllableId = id
        )
    }

    fun clearSelection() {
        _uiState.value = _uiState.value.copy(selectedIds = emptySet(), activeSyllableId = null)
    }

    fun startEditText(id: String) {
        val syllable = editor.getAllSyllables().find { it.id == id } ?: return
        _uiState.value = _uiState.value.copy(
            editTextId = id,
            editTextValue = syllable.text
        )
    }

    fun updateEditText(value: String) {
        _uiState.value = _uiState.value.copy(editTextValue = value)
    }

    fun commitEditText() {
        val id = _uiState.value.editTextId ?: return
        val text = _uiState.value.editTextValue
        val result = editor.setText(id, text)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                editTextId = null,
                editTextValue = "",
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun cancelEditText() {
        _uiState.value = _uiState.value.copy(editTextId = null, editTextValue = "")
    }

    fun splitSyllable(id: String) {
        val result = editor.splitSyllable(id)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun mergeSelected() {
        val ids = _uiState.value.selectedIds.toList()
        val result = editor.mergeSyllables(ids)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                selectedIds = emptySet(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun deleteSyllable(id: String) {
        val result = editor.deleteSyllable(id)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                selectedIds = _uiState.value.selectedIds - id,
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun insertSyllable() {
        val afterId = _uiState.value.activeSyllableId
        val result = editor.insertSyllable(afterId, duration = 1.0)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun setTagType(tagType: KaraokeTagType) {
        val ids = _uiState.value.selectedIds.toList()
        if (ids.isEmpty()) return
        val result = editor.setTagType(ids, tagType)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        }
    }

    fun toggleUnspoken() {
        val ids = _uiState.value.selectedIds.toList()
        if (ids.isEmpty()) return
        val result = editor.toggleUnspoken(ids)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        }
    }

    fun undo() {
        if (editor.undo()) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = "Отменено"
            )
        }
    }

    fun redo() {
        if (editor.redo()) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = "Повторено"
            )
        }
    }

    // --- Тайминг ---

    fun startTimingEdit(id: String) {
        val syllable = editor.getAllSyllables().find { it.id == id } ?: return
        _uiState.value = _uiState.value.copy(
            showTimingEditor = true,
            timingEditId = id,
            timingStart = syllable.start,
            timingEnd = syllable.end
        )
    }

    fun updateTiming(start: Double, end: Double) {
        _uiState.value = _uiState.value.copy(timingStart = start, timingEnd = end)
    }

    fun commitTiming() {
        val id = _uiState.value.timingEditId ?: return
        val result = editor.setTiming(id, _uiState.value.timingStart, _uiState.value.timingEnd)
        if (result.success) {
            _uiState.value = _uiState.value.copy(
                syllables = editor.getAllSyllables(),
                showTimingEditor = false,
                timingEditId = null,
                canUndo = editor.canUndo,
                canRedo = editor.canRedo,
                successMessage = result.message
            )
        } else {
            viewModelScope.launch { _events.emit(StudioEvent.ShowError(result.message)) }
        }
    }

    fun cancelTimingEdit() {
        _uiState.value = _uiState.value.copy(showTimingEditor = false, timingEditId = null)
    }

    // --- Темы ---

    fun setTheme(palette: KaraokeThemePalette) {
        _uiState.value = _uiState.value.copy(currentTheme = palette, showThemePicker = false)
    }

    fun showThemePicker() {
        _uiState.value = _uiState.value.copy(showThemePicker = true)
    }

    fun hideThemePicker() {
        _uiState.value = _uiState.value.copy(showThemePicker = false)
    }

    // --- Плеер ---

    fun setMediaFile(file: File) {
        try {
            mediaPlayer?.release()
            mediaPlayer = android.media.MediaPlayer().apply {
                setDataSource(file.absolutePath)
                prepare()
                setOnCompletionListener {
                    _uiState.value = _uiState.value.copy(isPlaying = false, playbackPosition = 0.0)
                }
            }
            _uiState.value = _uiState.value.copy(
                mediaDuration = mediaPlayer?.duration?.toDouble()?.div(1000.0) ?: 0.0
            )
        } catch (e: Exception) {
            viewModelScope.launch {
                _events.emit(StudioEvent.ShowError("Не удалось инициализировать аудио: ${e.message}"))
            }
        }
    }

    fun setMedia(uri: Uri, context: Context) {
        try {
            mediaPlayer?.release()
            mediaPlayer = android.media.MediaPlayer().apply {
                setDataSource(context, uri)
                prepare()
                setOnCompletionListener {
                    _uiState.value = _uiState.value.copy(isPlaying = false, playbackPosition = 0.0)
                }
            }
            _uiState.value = _uiState.value.copy(
                mediaDuration = mediaPlayer?.duration?.toDouble()?.div(1000.0) ?: 0.0
            )
        } catch (e: Exception) {
            viewModelScope.launch {
                _events.emit(StudioEvent.ShowError("Не удалось открыть медиа: ${e.message}"))
            }
        }
    }

    fun togglePlayback() {
        mediaPlayer?.let { player ->
            if (player.isPlaying) {
                player.pause()
                _uiState.value = _uiState.value.copy(isPlaying = false)
            } else {
                player.start()
                _uiState.value = _uiState.value.copy(isPlaying = true)
                startPlaybackPolling()
            }
        }
    }

    fun seekTo(position: Double) {
        mediaPlayer?.seekTo((position * 1000).toInt())
        _uiState.value = _uiState.value.copy(playbackPosition = position)
    }

    fun setPlaybackSpeed(speed: Float) {
        mediaPlayer?.let {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.M) {
                it.playbackParams = it.playbackParams.setSpeed(speed)
            }
        }
        _uiState.value = _uiState.value.copy(playbackSpeed = speed)
    }

    private fun startPlaybackPolling() {
        viewModelScope.launch {
            while (mediaPlayer?.isPlaying == true) {
                val pos = mediaPlayer?.currentPosition?.toDouble()?.div(1000.0) ?: 0.0
                _uiState.value = _uiState.value.copy(playbackPosition = pos)
                kotlinx.coroutines.delay(50)
            }
        }
    }

    fun stopPlayback() {
        mediaPlayer?.pause()
        _uiState.value = _uiState.value.copy(isPlaying = false)
    }

    // --- ASS ---

    fun loadAss(uri: Uri, context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val text = context.contentResolver.openInputStream(uri)?.use {
                    BufferedReader(InputStreamReader(it)).readText()
                } ?: return@launch

                val document = AssParser.parse(text)
                val syllables = document.events.flatMap { it.syllables }
                editor = AssEditor(syllables)

                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(
                        document = document,
                        syllables = syllables,
                        selectedIds = emptySet(),
                        canUndo = editor.canUndo,
                        canRedo = editor.canRedo,
                        successMessage = "ASS загружен"
                    )
                }
            } catch (e: Exception) {
                _events.emit(StudioEvent.ShowError("Ошибка загрузки ASS: ${e.message}"))
            }
        }
    }

    fun createBlankAss(duration: Double) {
        val document = AssParser.createBlankDocument(duration)
        val syllables = document.events.flatMap { it.syllables }
        editor = AssEditor(syllables)
        _uiState.value = _uiState.value.copy(
            document = document,
            syllables = syllables,
            selectedIds = emptySet(),
            canUndo = editor.canUndo,
            canRedo = editor.canRedo,
            successMessage = "Создан пустой ASS"
        )
    }

    // --- Waveform ---

    fun loadWaveform(uri: Uri, context: Context) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val extractor = android.media.MediaExtractor()
                extractor.setDataSource(context, uri, null)
                val trackIndex = (0 until extractor.trackCount).firstOrNull { i ->
                    val format = extractor.getTrackFormat(i)
                    format.getString(android.media.MediaFormat.KEY_MIME)?.startsWith("audio/") == true
                } ?: return@launch

                extractor.selectTrack(trackIndex)
                val format = extractor.getTrackFormat(trackIndex)
                val sampleRate = format.getInteger(android.media.MediaFormat.KEY_SAMPLE_RATE)
                val channelCount = format.getInteger(android.media.MediaFormat.KEY_CHANNEL_COUNT)

                val decoder = android.media.MediaCodec.createDecoderByType(
                    format.getString(android.media.MediaFormat.KEY_MIME)!!
                )
                decoder.configure(format, null, null, 0)
                decoder.start()

                val samples = mutableListOf<Float>()
                val bufferInfo = android.media.MediaCodec.BufferInfo()
                var sawInputEOS = false
                var sawOutputEOS = false

                while (!sawOutputEOS) {
                    if (!sawInputEOS) {
                        val inputBufferId = decoder.dequeueInputBuffer(10000)
                        if (inputBufferId >= 0) {
                            val inputBuffer = decoder.getInputBuffer(inputBufferId)!!
                            val sampleSize = extractor.readSampleData(inputBuffer, 0)
                            if (sampleSize < 0) {
                                decoder.queueInputBuffer(inputBufferId, 0, 0, 0, android.media.MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                sawInputEOS = true
                            } else {
                                decoder.queueInputBuffer(inputBufferId, 0, sampleSize, extractor.sampleTime, 0)
                                extractor.advance()
                            }
                        }
                    }

                    val outputBufferId = decoder.dequeueOutputBuffer(bufferInfo, 10000)
                    if (outputBufferId >= 0) {
                        val outputBuffer = decoder.getOutputBuffer(outputBufferId)!!
                        val chunk = ByteArray(bufferInfo.size)
                        outputBuffer.get(chunk)
                        outputBuffer.clear()

                        // Простая декимация для waveform
                        val shorts = chunk.toList().chunked(2).map {
                            ((it[1].toInt() shl 8) or (it[0].toInt() and 0xFF)).toShort()
                        }
                        val maxInChunk = shorts.maxOfOrNull { kotlin.math.abs(it.toInt()) }?.toFloat()?.div(Short.MAX_VALUE) ?: 0f
                        samples.add(maxInChunk)

                        decoder.releaseOutputBuffer(outputBufferId, false)
                        if (bufferInfo.flags and android.media.MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) {
                            sawOutputEOS = true
                        }
                    }
                }

                decoder.stop()
                decoder.release()
                extractor.release()

                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(waveformData = samples)
                }
            } catch (e: Exception) {
                _events.emit(StudioEvent.ShowError("Ошибка waveform: ${e.message}"))
            }
        }
    }

    // --- Zoom / Scroll ---

    fun setZoom(level: Float) {
        _uiState.value = _uiState.value.copy(zoomLevel = level.coerceIn(0.5f, 10f))
    }

    fun setScroll(offset: Float) {
        _uiState.value = _uiState.value.copy(scrollOffset = offset.coerceAtLeast(0f))
    }

    // --- Диалоги ---

    fun showExportDialog() {
        _uiState.value = _uiState.value.copy(showExportDialog = true)
    }

    fun hideExportDialog() {
        _uiState.value = _uiState.value.copy(showExportDialog = false)
    }

    fun showImportDialog() {
        _uiState.value = _uiState.value.copy(showImportDialog = true)
    }

    fun hideImportDialog() {
        _uiState.value = _uiState.value.copy(showImportDialog = false)
    }

    fun showSettings() {
        _uiState.value = _uiState.value.copy(showSettings = true)
    }

    fun hideSettings() {
        _uiState.value = _uiState.value.copy(showSettings = false)
    }

    fun showHelp() {
        _uiState.value = _uiState.value.copy(showHelp = true)
    }

    fun hideHelp() {
        _uiState.value = _uiState.value.copy(showHelp = false)
    }

    fun clearMessage() {
        _uiState.value = _uiState.value.copy(errorMessage = null, successMessage = null)
    }

    override fun onCleared() {
        super.onCleared()
        mediaPlayer?.release()
        mediaPlayer = null
    }
}
