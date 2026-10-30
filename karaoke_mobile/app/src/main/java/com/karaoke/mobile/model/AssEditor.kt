package com.karaoke.mobile.model

import java.util.UUID

/**
 * Результат редактирования
 */
data class EditResult(
    val success: Boolean,
    val message: String = "",
    val newSyllables: List<KaraokeSyllable> = emptyList()
)

/**
 * Команда для undo/redo
 */
sealed class EditCommand {
    abstract fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable>
    abstract fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable>

    data class SetText(
        val id: String,
        val oldText: String,
        val newText: String
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(text = oldText) else it }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(text = newText) else it }
    }

    data class SetRomanization(
        val id: String,
        val oldRom: String?,
        val newRom: String?
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(romanization = oldRom) else it }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(romanization = newRom) else it }
    }

    data class SplitSyllable(
        val id: String,
        val oldSyllable: KaraokeSyllable,
        val newSyllables: List<KaraokeSyllable>
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            val idx = result.indexOfFirst { it.id == id }
            if (idx >= 0) {
                result.removeAt(idx)
                result.addAll(idx, listOf(oldSyllable))
            }
            return result
        }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            val idx = result.indexOfFirst { it.id == id }
            if (idx >= 0) {
                result.removeAt(idx)
                result.addAll(idx, newSyllables)
            }
            return result
        }
    }

    data class MergeSyllables(
        val ids: List<String>,
        val oldSyllables: List<KaraokeSyllable>,
        val newSyllable: KaraokeSyllable
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            val firstIdx = result.indexOfFirst { it.id == ids.first() }
            if (firstIdx >= 0) {
                // Удаляем все объединённые
                result.removeAll { it.id in ids }
                // Вставляем обратно старые
                result.addAll(firstIdx, oldSyllables)
            }
            return result
        }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            val firstIdx = result.indexOfFirst { it.id == ids.first() }
            if (firstIdx >= 0) {
                result.removeAll { it.id in ids }
                result.add(firstIdx, newSyllable)
            }
            return result
        }
    }

    data class DeleteSyllable(
        val oldSyllables: List<KaraokeSyllable>,
        val id: String
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            val oldIdx = oldSyllables.indexOfFirst { it.id == id }
            val oldSyllable = oldSyllables[oldIdx]
            if (result.isEmpty()) {
                result.add(oldSyllable)
            } else {
                // Находим позицию по времени
                val insertIdx = result.indexOfFirst { it.start > oldSyllable.start }
                    .let { if (it < 0) result.size else it }
                result.add(insertIdx, oldSyllable)
            }
            return result
        }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.filter { it.id != id }
    }

    data class InsertSyllable(
        val afterId: String?,
        val newSyllable: KaraokeSyllable
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.filter { it.id != newSyllable.id }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> {
            val result = syllables.toMutableList()
            if (afterId == null) {
                result.add(0, newSyllable)
            } else {
                val idx = result.indexOfFirst { it.id == afterId }
                if (idx >= 0) result.add(idx + 1, newSyllable)
                else result.add(newSyllable)
            }
            return result
        }
    }

    data class SetTagType(
        val ids: List<String>,
        val oldType: KaraokeTagType,
        val newType: KaraokeTagType
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id in ids) it.copy(tagType = oldType) else it }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id in ids) it.copy(tagType = newType) else it }
    }

    data class SetTiming(
        val id: String,
        val oldStart: Double,
        val oldEnd: Double,
        val newStart: Double,
        val newEnd: Double
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(start = oldStart, end = oldEnd) else it }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id == id) it.copy(start = newStart, end = newEnd) else it }
    }

    data class ToggleUnspoken(
        val ids: List<String>,
        val oldStates: Map<String, Boolean>,
        val newUnspoken: Boolean
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id in ids) it.copy(isUnspoken = oldStates[it.id] ?: false) else it }

        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> =
            syllables.map { if (it.id in ids) it.copy(isUnspoken = newUnspoken) else it }
    }

    data class BatchEdit(
        val oldSyllables: List<KaraokeSyllable>,
        val newSyllables: List<KaraokeSyllable>
    ) : EditCommand() {
        override fun undo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> = oldSyllables
        override fun redo(syllables: List<KaraokeSyllable>): List<KaraokeSyllable> = newSyllables
    }
}

/**
 * Редактор с историей undo/redo.
 * Портирован из karaoke_core/editor.py
 */
class AssEditor(initialSyllables: List<KaraokeSyllable> = emptyList()) {
    private val history = mutableListOf<EditCommand>()
    private var historyIndex = -1
    private val maxHistory = 100

    var syllables: List<KaraokeSyllable> = initialSyllables
        private set

    val canUndo: Boolean get() = historyIndex >= 0
    val canRedo: Boolean get() = historyIndex < history.size - 1

    fun execute(command: EditCommand) {
        // Удаляем redo-историю
        while (history.size > historyIndex + 1) {
            history.removeAt(history.size - 1)
        }
        syllables = command.redo(syllables)
        history.add(command)
        if (history.size > maxHistory) {
            history.removeAt(0)
        } else {
            historyIndex++
        }
    }

    fun undo(): Boolean {
        if (!canUndo) return false
        val command = history[historyIndex]
        syllables = command.undo(syllables)
        historyIndex--
        return true
    }

    fun redo(): Boolean {
        if (!canRedo) return false
        historyIndex++
        val command = history[historyIndex]
        syllables = command.redo(syllables)
        return true
    }

    fun setText(id: String, newText: String): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        if (syllable.text == newText) return EditResult(true, "Без изменений")
        execute(EditCommand.SetText(id, syllable.text, newText))
        return EditResult(true, "Текст обновлён", syllables)
    }

    fun setRomanization(id: String, romanization: String?): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        execute(EditCommand.SetRomanization(id, syllable.romanization, romanization))
        return EditResult(true, "Романизация обновлена", syllables)
    }

    fun splitSyllable(id: String, ratio: Double = 0.5): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        if (syllable.duration < 0.1) return EditResult(false, "Слог слишком короткий")

        val splitPoint = syllable.start + syllable.duration * ratio.coerceIn(0.1, 0.9)
        val left = syllable.copy(
            id = UUID.randomUUID().toString(),
            end = splitPoint
        )
        val right = syllable.copy(
            id = UUID.randomUUID().toString(),
            start = splitPoint
        )
        execute(EditCommand.SplitSyllable(id, syllable, listOf(left, right)))
        return EditResult(true, "Слог разделён", syllables)
    }

    fun splitSyllableAtText(id: String, textOffset: Int): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        if (textOffset <= 0 || textOffset >= syllable.text.length) {
            return EditResult(false, "Неверная позиция разделения")
        }

        val ratio = textOffset.toDouble() / syllable.text.length
        val splitPoint = syllable.start + syllable.duration * ratio
        val leftText = syllable.text.substring(0, textOffset)
        val rightText = syllable.text.substring(textOffset)

        val left = syllable.copy(
            id = UUID.randomUUID().toString(),
            text = leftText,
            end = splitPoint
        )
        val right = syllable.copy(
            id = UUID.randomUUID().toString(),
            text = rightText,
            start = splitPoint
        )
        execute(EditCommand.SplitSyllable(id, syllable, listOf(left, right)))
        return EditResult(true, "Слог разделён по тексту", syllables)
    }

    fun mergeSyllables(ids: List<String>): EditResult {
        if (ids.size < 2) return EditResult(false, "Выберите минимум 2 слога")
        val toMerge = syllables.filter { it.id in ids }
        if (toMerge.size < 2) return EditResult(false, "Слоги не найдены")

        val merged = KaraokeSyllable(
            id = UUID.randomUUID().toString(),
            text = toMerge.joinToString("") { it.text },
            start = toMerge.minOf { it.start },
            end = toMerge.maxOf { it.end },
            tagType = toMerge.first().tagType,
            isUnspoken = toMerge.all { it.isUnspoken },
            romanization = toMerge.mapNotNull { it.romanization }.joinToString(" ").ifEmpty { null },
            styleName = toMerge.first().styleName
        )
        execute(EditCommand.MergeSyllables(ids, toMerge, merged))
        return EditResult(true, "Слоги объединены", syllables)
    }

    fun deleteSyllable(id: String): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        execute(EditCommand.DeleteSyllable(syllables, id))
        return EditResult(true, "Слог удалён", syllables)
    }

    fun insertSyllable(afterId: String?, text: String = "", duration: Double = 1.0): EditResult {
        val newSyllable = if (afterId != null) {
            val after = syllables.find { it.id == afterId }
                ?: return EditResult(false, "Опорный слог не найден")
            KaraokeSyllable(
                id = UUID.randomUUID().toString(),
                text = text,
                start = after.end,
                end = after.end + duration,
                tagType = after.tagType,
                styleName = after.styleName
            )
        } else {
            KaraokeSyllable(
                id = UUID.randomUUID().toString(),
                text = text,
                start = 0.0,
                end = duration
            )
        }
        execute(EditCommand.InsertSyllable(afterId, newSyllable))
        return EditResult(true, "Слог вставлен", syllables)
    }

    fun setTagType(ids: List<String>, tagType: KaraokeTagType): EditResult {
        if (ids.isEmpty()) return EditResult(false, "Ничего не выбрано")
        val first = syllables.find { it.id in ids } ?: return EditResult(false, "Слоги не найдены")
        execute(EditCommand.SetTagType(ids, first.tagType, tagType))
        return EditResult(true, "Тип тега изменён", syllables)
    }

    fun setTiming(id: String, start: Double, end: Double): EditResult {
        val syllable = syllables.find { it.id == id }
            ?: return EditResult(false, "Слог не найден")
        if (end <= start) return EditResult(false, "Конец должен быть после начала")
        execute(EditCommand.SetTiming(id, syllable.start, syllable.end, start, end))
        return EditResult(true, "Тайминг обновлён", syllables)
    }

    fun redistributeBoundary(id: String, newBoundary: Double): EditResult {
        val idx = syllables.indexOfFirst { it.id == id }
        if (idx < 0 || idx >= syllables.size - 1) {
            return EditResult(false, "Нет следующего слога для перераспределения")
        }
        val left = syllables[idx]
        val right = syllables[idx + 1]
        if (newBoundary < left.start + 0.02 || newBoundary > right.end - 0.02) {
            return EditResult(false, "Граница за пределами допустимого диапазона")
        }
        val oldSyllables = syllables
        val newLeft = left.copy(end = newBoundary)
        val newRight = right.copy(start = newBoundary)
        val newSyllables = syllables.toMutableList().apply {
            this[idx] = newLeft
            this[idx + 1] = newRight
        }
        execute(EditCommand.BatchEdit(oldSyllables, newSyllables))
        return EditResult(true, "Граница перераспределена", syllables)
    }

    fun toggleUnspoken(ids: List<String>): EditResult {
        if (ids.isEmpty()) return EditResult(false, "Ничего не выбрано")
        val oldStates = syllables.filter { it.id in ids }.associate { it.id to it.isUnspoken }
        val newUnspoken = !oldStates.values.all { it }
        execute(EditCommand.ToggleUnspoken(ids, oldStates, newUnspoken))
        return EditResult(true, if (newUnspoken) "Отмечено как непропетое" else "Снята отметка", syllables)
    }

    fun getAllSyllables(): List<KaraokeSyllable> = syllables

    fun findByTime(time: Double): KaraokeSyllable? =
        syllables.find { time >= it.start && time < it.end }
            ?: syllables.lastOrNull { it.start <= time }

    fun findNext(id: String): KaraokeSyllable? {
        val idx = syllables.indexOfFirst { it.id == id }
        return syllables.getOrNull(idx + 1)
    }

    fun findPrevious(id: String): KaraokeSyllable? {
        val idx = syllables.indexOfFirst { it.id == id }
        return syllables.getOrNull(idx - 1)
    }

    fun reset(newSyllables: List<KaraokeSyllable>) {
        syllables = newSyllables
        history.clear()
        historyIndex = -1
    }
}
