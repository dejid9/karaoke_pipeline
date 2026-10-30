package com.karaoke.mobile

import org.junit.Assert.*
import org.junit.Test

class AssEditorTest {
    private val source = "[Script Info]\r\nTitle: Demo\r\n[Events]\r\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\kf40}Hello{\\kf60}world\r\n"

    @Test fun roundTripPreservesLineEndings() {
        val editor = AssEditor.parse(source)
        assertEquals(source, editor.serialize())
        assertEquals(listOf("Hello", "world"), editor.syllables().map { it.text })
    }
    @Test fun boundaryPreservesPairDurationAndUndo() {
        val editor = AssEditor.parse(source)
        val (a, b) = editor.syllables()
        editor.moveBoundary(a.id, b.id, 150)
        assertEquals(listOf(50, 50), editor.syllables().map { it.endCs - it.startCs })
        editor.undo()
        assertEquals(source, editor.serialize())
        editor.redo()
        assertEquals(150, editor.syllables().first().endCs)
    }
    @Test fun splitAndMergeKeepTextAndTiming() {
        val editor = AssEditor.parse(source)
        val first = editor.syllables().first()
        editor.split(first.id, 120)
        assertEquals(3, editor.syllables().size)
        assertEquals(140, editor.syllables()[1].endCs)
        editor.merge(editor.syllables().take(2).map { it.id })
        assertEquals(listOf("Hello", "world"), editor.syllables().map { it.text })
        assertEquals(200, editor.syllables().last().endCs)
    }
    @Test fun textEditPreservesColourTags() {
        val editor = AssEditor.parse(source.replace("Hello", "{\\c&HFF&}Hello{\\c}"))
        editor.setText(editor.syllables().first().id, "New")
        assertTrue(editor.serialize().contains("{\\c&HFF&}New{\\c}"))
        assertEquals("New", editor.syllables().first().text)
    }
    @Test fun burstMarkingAndRemoval() {
        val editor = AssEditor.parse(source)
        val first = editor.syllables().first().id
        editor.setBurst(first, true)
        assertTrue(editor.syllables().first().burst)
        assertFalse(editor.syllables().last().burst)
        editor.setBurst(first, false)
        assertFalse(editor.syllables().first().burst)
    }
    @Test fun lastSyllableEndUpdatesDialogueEnd() {
        val editor = AssEditor.parse(source)
        editor.setEnd(editor.syllables().last().id, 240)
        assertTrue(editor.serialize().contains("0:00:02.40"))
        assertEquals(240, editor.syllables().last().endCs)
    }
}
