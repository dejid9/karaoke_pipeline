package com.karaoke.mobile.viewmodel

import android.content.Context
import android.media.MediaPlayer
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.karaoke.mobile.model.AssEditor
import com.karaoke.mobile.model.AssFile
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.model.AssParser
import com.karaoke.mobile.model.Syllable
import com.karaoke.mobile.model.WaveformData
import com.karaoke.mobile.model.WaveformExtractor
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class StudioState : ViewModel() {
    var assFile by mutableStateOf(AssFile())
        private set

    var editor by mutableStateOf(AssEditor(assFile))
        private set

    var currentLineIndex by mutableIntStateOf(-1)
        private set

    var currentSyllableIndex by mutableIntStateOf(-1)
        private set

    var playbackPositionMs by mutableLongStateOf(0L)
        private set

    var isPlaying by mutableStateOf(false)
        private set

    var playbackSpeed by mutableFloatStateOf(1.0f)
        private set

    var inPointMs by mutableLongStateOf(0L)
        private set

    var outPointMs by mutableLongStateOf(0L)
        private set

    var loopEnabled by mutableStateOf(false)
        private set

    var zoomLevel by mutableFloatStateOf(1.0f)
        private set

    var scrollOffsetMs by mutableLongStateOf(0L)
        private set

    var waveform by mutableStateOf<WaveformData?>(null)
        private set

    var isLoadingWaveform by mutableStateOf(false)
        private set

    var snackbarMessage by mutableStateOf<String?>(null)
        private set

    var currentTab by mutableStateOf(StudioTab.SYLLABLES)
        private set

    private var mediaPlayer: MediaPlayer? = null
    private var progressJob: Job? = null
    private var audioUri: Uri? = null

    enum class StudioTab { SYLLABLES, FILES, SETTINGS }

    fun loadAss(content: String) {
        val parsed = AssParser.parse(content)
        assFile = parsed
        editor = AssEditor(parsed)
        currentLineIndex = if (parsed.lines.isNotEmpty()) 0 else -1
        currentSyllableIndex = if (parsed.lines.isNotEmpty() && parsed.lines[0].syllables.isNotEmpty()) 0 else -1
        showSnackbar("Файл загружен: ${parsed.lines.size} строк")
    }

    fun serializeAss(): String = AssParser.serialize(editor.current)

    fun selectLine(index: Int) {
        if (index in editor.current.lines.indices) {
            currentLineIndex = index
            currentSyllableIndex = if (editor.current.lines[index].syllables.isNotEmpty()) 0 else -1
        }
    }

    fun selectSyllable(lineIndex: Int, syllableIndex: Int) {
        if (lineIndex in editor.current.lines.indices) {
            currentLineIndex = lineIndex
            val line = editor.current.lines[lineIndex]
            if (syllableIndex in line.syllables.indices) {
                currentSyllableIndex = syllableIndex
            }
        }
    }

    fun previousSyllable() {
        val line = editor.current.lines.getOrNull(currentLineIndex) ?: return
        when {
            currentSyllableIndex > 0 -> currentSyllableIndex--
            currentLineIndex > 0 -> {
                currentLineIndex--
                currentSyllableIndex = editor.current.lines[currentLineIndex].syllables.size - 1
            }
        }
    }

    fun nextSyllable() {
        val line = editor.current.lines.getOrNull(currentLineIndex) ?: return
        when {
            currentSyllableIndex < line.syllables.size - 1 -> currentSyllableIndex++
            currentLineIndex < editor.current.lines.size - 1 -> {
                currentLineIndex++
                currentSyllableIndex = 0
            }
        }
    }

    fun updateSyllableText(lineIndex: Int, syllableIndex: Int, text: String) {
        assFile = editor.setSyllableText(lineIndex, syllableIndex, text)
    }

    fun updateSyllableTimes(lineIndex: Int, syllableIndex: Int, start: Long, end: Long) {
        assFile = editor.setSyllableTimes(lineIndex, syllableIndex, start, end)
    }

    fun toggleSyllableBurst(lineIndex: Int, syllableIndex: Int) {
        assFile = editor.toggleSyllableBurst(lineIndex, syllableIndex)
    }

    fun toggleLineBurst(lineIndex: Int) {
        assFile = editor.toggleLineBurst(lineIndex)
    }

    fun splitSyllable(lineIndex: Int, syllableIndex: Int, splitPoint: Long) {
        assFile = editor.splitSyllable(lineIndex, syllableIndex, splitPoint)
    }

    fun mergeSyllables(lineIndex: Int, fromIndex: Int, toIndex: Int) {
        assFile = editor.mergeSyllables(lineIndex, fromIndex, toIndex)
    }

    fun undo() {
        if (editor.canUndo()) {
            assFile = editor.undo()
            showSnackbar("Отменено")
        }
    }

    fun redo() {
        if (editor.canRedo()) {
            assFile = editor.redo()
            showSnackbar("Повторено")
        }
    }

    fun setAudio(context: Context, uri: Uri) {
        releasePlayer()
        audioUri = uri
        mediaPlayer = MediaPlayer().apply {
            setDataSource(context, uri)
            prepare()
        }
        outPointMs = mediaPlayer?.duration?.toLong() ?: 0L
        editor = AssEditor(editor.current.copy(audioFile = uri.toString()))
        assFile = editor.current
        loadWaveform(context, uri)
    }

    private fun loadWaveform(context: Context, uri: Uri) {
        isLoadingWaveform = true
        viewModelScope.launch {
            waveform = WaveformExtractor.extract(context, uri)
            isLoadingWaveform = false
        }
    }

    fun playPause() {
        mediaPlayer?.let { player ->
            if (player.isPlaying) {
                player.pause()
                isPlaying = false
                progressJob?.cancel()
            } else {
                if (loopEnabled && playbackPositionMs >= outPointMs) {
                    seekTo(inPointMs)
                }
                player.playbackParams = player.playbackParams.setSpeed(playbackSpeed)
                player.start()
                isPlaying = true
                startProgressTracking()
            }
        }
    }

    fun seekTo(positionMs: Long) {
        val pos = positionMs.coerceIn(0, mediaPlayer?.duration?.toLong() ?: positionMs)
        mediaPlayer?.seekTo(pos.toInt())
        playbackPositionMs = pos
    }

    @JvmName("updatePlaybackSpeed")
    fun setPlaybackSpeed(speed: Float) {
        playbackSpeed = speed.coerceIn(0.5f, 1.5f)
        mediaPlayer?.let {
            if (it.isPlaying) {
                it.playbackParams = it.playbackParams.setSpeed(playbackSpeed)
            }
        }
    }

    fun setInPoint() {
        inPointMs = playbackPositionMs
        showSnackbar("In: ${formatTime(inPointMs)}")
    }

    fun setOutPoint() {
        outPointMs = playbackPositionMs
        showSnackbar("Out: ${formatTime(outPointMs)}")
    }

    fun toggleLoop() {
        loopEnabled = !loopEnabled
        showSnackbar(if (loopEnabled) "Петля включена" else "Петля выключена")
    }

    fun setZoom(zoom: Float) {
        zoomLevel = zoom.coerceIn(0.5f, 10f)
    }

    fun setScrollOffset(offsetMs: Long) {
        val maxOffset = (mediaPlayer?.duration?.toLong() ?: 0L) - (viewportDurationMs / zoomLevel).toLong()
        scrollOffsetMs = offsetMs.coerceIn(0, maxOf(0, maxOffset))
    }

    val viewportDurationMs: Long get() = 30000L

    fun snapToSyllable(syllable: Syllable) {
        seekTo(syllable.start)
    }

    fun snapToLineStart(line: AssLine) {
        seekTo(line.start)
    }

    fun snapToLineEnd(line: AssLine) {
        seekTo(line.end)
    }

    fun showSnackbar(message: String) {
        snackbarMessage = message
        viewModelScope.launch {
            delay(2000)
            snackbarMessage = null
        }
    }

    fun dismissSnackbar() {
        snackbarMessage = null
    }

    fun setTab(tab: StudioTab) {
        currentTab = tab
    }

    private fun startProgressTracking() {
        progressJob?.cancel()
        progressJob = viewModelScope.launch {
            while (isActive) {
                mediaPlayer?.let { player ->
                    if (player.isPlaying) {
                        playbackPositionMs = player.currentPosition.toLong()
                        if (loopEnabled && playbackPositionMs >= outPointMs) {
                            seekTo(inPointMs)
                        }
                    }
                }
                delay(50)
            }
        }
    }

    fun releasePlayer() {
        progressJob?.cancel()
        mediaPlayer?.release()
        mediaPlayer = null
        isPlaying = false
    }

    override fun onCleared() {
        super.onCleared()
        releasePlayer()
    }

    private fun formatTime(ms: Long): String {
        val totalSeconds = ms / 1000
        val minutes = totalSeconds / 60
        val seconds = totalSeconds % 60
        val centis = (ms % 1000) / 10
        return String.format("%02d:%02d.%02d", minutes, seconds, centis)
    }
}
