package com.karaoke.mobile.model

class AssEditor(initial: AssFile = AssFile()) {
    private val history = mutableListOf<AssFile>()
    private var historyPos = -1
    private val maxHistory = 100

    init {
        pushState(initial)
    }

    private fun pushState(state: AssFile) {
        while (history.size > historyPos + 1) {
            history.removeAt(history.size - 1)
        }
        history.add(state)
        if (history.size > maxHistory) {
            history.removeAt(0)
        } else {
            historyPos++
        }
    }

    fun canUndo(): Boolean = historyPos > 0
    fun canRedo(): Boolean = historyPos < history.size - 1

    fun undo(): AssFile {
        if (canUndo()) historyPos--
        return history[historyPos]
    }

    fun redo(): AssFile {
        if (canRedo()) historyPos++
        return history[historyPos]
    }

    val current: AssFile get() = history[historyPos]

    fun updateLines(newLines: List<AssLine>): AssFile {
        val newState = current.copy(lines = newLines)
        pushState(newState)
        return newState
    }

    fun updateLine(index: Int, transform: (AssLine) -> AssLine): AssFile {
        val newLines = current.lines.toMutableList()
        if (index in newLines.indices) {
            newLines[index] = transform(newLines[index])
            pushState(current.copy(lines = newLines))
        }
        return current
    }

    fun updateSyllable(lineIndex: Int, syllableIndex: Int, transform: (Syllable) -> Syllable): AssFile {
        return updateLine(lineIndex) { line ->
            val newSyllables = line.syllables.toMutableList()
            if (syllableIndex in newSyllables.indices) {
                newSyllables[syllableIndex] = transform(newSyllables[syllableIndex])
            }
            line.copy(syllables = newSyllables)
        }
    }

    fun setSyllableText(lineIndex: Int, syllableIndex: Int, newText: String): AssFile {
        return updateSyllable(lineIndex, syllableIndex) { it.copy(text = newText) }
    }

    fun setSyllableTimes(lineIndex: Int, syllableIndex: Int, start: Long, end: Long): AssFile {
        return updateSyllable(lineIndex, syllableIndex) { it.copy(start = start, end = end) }
    }

    fun toggleSyllableBurst(lineIndex: Int, syllableIndex: Int): AssFile {
        return updateSyllable(lineIndex, syllableIndex) { it.copy(isBurst = !it.isBurst) }
    }

    fun toggleLineBurst(lineIndex: Int): AssFile {
        return updateLine(lineIndex) { it.copy(isBurst = !it.isBurst) }
    }

    fun setLineTimes(lineIndex: Int, start: Long, end: Long): AssFile {
        return updateLine(lineIndex) { it.copy(start = start, end = end) }
    }

    fun splitSyllable(lineIndex: Int, syllableIndex: Int, splitPoint: Long): AssFile {
        return updateLine(lineIndex) { line ->
            val syls = line.syllables.toMutableList()
            if (syllableIndex in syls.indices) {
                val s = syls[syllableIndex]
                if (splitPoint > s.start && splitPoint < s.end) {
                    val first = s.copy(end = splitPoint)
                    val second = s.copy(start = splitPoint)
                    syls[syllableIndex] = first
                    syls.add(syllableIndex + 1, second)
                }
            }
            line.copy(syllables = syls)
        }
    }

    fun mergeSyllables(lineIndex: Int, fromIndex: Int, toIndex: Int): AssFile {
        return updateLine(lineIndex) { line ->
            val syls = line.syllables.toMutableList()
            val range = fromIndex..toIndex.coerceAtMost(syls.size - 1)
            if (range.first in syls.indices && range.last in syls.indices && range.first < range.last) {
                val merged = syls.slice(range)
                val newSyl = Syllable(
                    text = merged.joinToString("") { it.text },
                    start = merged.first().start,
                    end = merged.last().end,
                    tag = merged.first().tag,
                    isBurst = merged.any { it.isBurst }
                )
                repeat(range.count()) { syls.removeAt(range.first) }
                syls.add(range.first, newSyl)
            }
            line.copy(syllables = syls)
        }
    }

    fun insertLine(atIndex: Int, line: AssLine): AssFile {
        val newLines = current.lines.toMutableList()
        newLines.add(atIndex.coerceIn(0, newLines.size), line)
        pushState(current.copy(lines = newLines))
        return current
    }

    fun deleteLine(index: Int): AssFile {
        val newLines = current.lines.toMutableList()
        if (index in newLines.indices) {
            newLines.removeAt(index)
            pushState(current.copy(lines = newLines))
        }
        return current
    }

    fun moveLine(fromIndex: Int, toIndex: Int): AssFile {
        val newLines = current.lines.toMutableList()
        if (fromIndex in newLines.indices) {
            val line = newLines.removeAt(fromIndex)
            newLines.add(toIndex.coerceIn(0, newLines.size), line)
            pushState(current.copy(lines = newLines))
        }
        return current
    }

    fun setAudioFile(path: String?): AssFile {
        val newState = current.copy(audioFile = path)
        pushState(newState)
        return newState
    }

    fun clearHistory() {
        val state = current
        history.clear()
        historyPos = -1
        pushState(state)
    }
}
