package com.karaoke.mobile

import com.karaoke.mobile.model.AssEditor
import com.karaoke.mobile.model.AssFile
import com.karaoke.mobile.model.AssLine
import com.karaoke.mobile.model.AssParser
import com.karaoke.mobile.model.KaraokeTag
import com.karaoke.mobile.model.Syllable
import org.junit.Assert.*
import org.junit.Test

class AssEditorTest {
    private val sampleAss = """
        [Script Info]
        Title: Demo

        [Events]
        Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\k40}Hello{\kf60}world
    """.trimIndent()

    @Test
    fun testInitialState() {
        val file = AssParser.parse(sampleAss)
        val editor = AssEditor(file)
        assertEquals(1, editor.current.lines.size)
        assertEquals(2, editor.current.lines[0].syllables.size)
        assertFalse(editor.canUndo())
        assertFalse(editor.canRedo())
    }

    @Test
    fun testUndoRedo() {
        val file = AssParser.parse(sampleAss)
        val editor = AssEditor(file)

        editor.setSyllableText(0, 0, "Hi")
        assertEquals("Hi", editor.current.lines[0].syllables[0].text)
        assertTrue(editor.canUndo())
        assertFalse(editor.canRedo())

        editor.undo()
        assertEquals("Hello", editor.current.lines[0].syllables[0].text)
        assertFalse(editor.canUndo())
        assertTrue(editor.canRedo())

        editor.redo()
        assertEquals("Hi", editor.current.lines[0].syllables[0].text)
        assertTrue(editor.canUndo())
        assertFalse(editor.canRedo())
    }

    @Test
    fun testSplitAndMergeSyllables() {
        val file = AssParser.parse(sampleAss)
        val editor = AssEditor(file)
        val syl = editor.current.lines[0].syllables[0]
        val mid = (syl.start + syl.end) / 2

        editor.splitSyllable(0, 0, mid)
        assertEquals(3, editor.current.lines[0].syllables.size)
        assertEquals(mid, editor.current.lines[0].syllables[0].end)
        assertEquals(mid, editor.current.lines[0].syllables[1].start)

        editor.mergeSyllables(0, 0, 1)
        assertEquals(2, editor.current.lines[0].syllables.size)
    }

    @Test
    fun testToggleBurst() {
        val file = AssParser.parse(sampleAss)
        val editor = AssEditor(file)
        assertFalse(editor.current.lines[0].syllables[0].isBurst)

        editor.toggleSyllableBurst(0, 0)
        assertTrue(editor.current.lines[0].syllables[0].isBurst)

        editor.toggleSyllableBurst(0, 0)
        assertFalse(editor.current.lines[0].syllables[0].isBurst)
    }

    @Test
    fun testLineOperations() {
        val file = AssParser.parse(sampleAss)
        val editor = AssEditor(file)
        val newLine = AssLine(start = 2000, end = 3000, text = "Second line")

        editor.insertLine(1, newLine)
        assertEquals(2, editor.current.lines.size)

        editor.deleteLine(0)
        assertEquals(1, editor.current.lines.size)
        assertEquals("Second line", editor.current.lines[0].text)
    }
}
