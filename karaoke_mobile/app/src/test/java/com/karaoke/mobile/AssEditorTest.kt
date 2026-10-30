package com.karaoke.mobile

import com.karaoke.mobile.model.AssEditor
import com.karaoke.mobile.model.KaraokeSyllable
import com.karaoke.mobile.model.KaraokeTagType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssEditorTest {
    private fun createSampleSyllables(): List<KaraokeSyllable> = listOf(
        KaraokeSyllable(
            id = "syl-1",
            text = "Hello",
            start = 1.0,
            end = 1.4,
            tagType = KaraokeTagType.K
        ),
        KaraokeSyllable(
            id = "syl-2",
            text = "world",
            start = 1.4,
            end = 2.0,
            tagType = KaraokeTagType.KF
        )
    )

    @Test
    fun testInitialState() {
        val syllables = createSampleSyllables()
        val editor = AssEditor(syllables)
        assertEquals(2, editor.syllables.size)
        assertFalse(editor.canUndo)
        assertFalse(editor.canRedo)
    }

    @Test
    fun testUndoRedo() {
        val editor = AssEditor(createSampleSyllables())

        val res = editor.setText("syl-1", "Hi")
        assertTrue(res.success)
        assertEquals("Hi", editor.syllables[0].text)
        assertTrue(editor.canUndo)
        assertFalse(editor.canRedo)

        editor.undo()
        assertEquals("Hello", editor.syllables[0].text)
        assertFalse(editor.canUndo)
        assertTrue(editor.canRedo)

        editor.redo()
        assertEquals("Hi", editor.syllables[0].text)
        assertTrue(editor.canUndo)
        assertFalse(editor.canRedo)
    }

    @Test
    fun testSplitAndMergeSyllables() {
        val editor = AssEditor(createSampleSyllables())
        val initialId = editor.syllables[0].id

        val splitRes = editor.splitSyllable(initialId, 0.5)
        assertTrue(splitRes.success)
        assertEquals(3, editor.syllables.size)
        assertEquals(1.0, editor.syllables[0].start, 0.001)
        assertEquals(1.2, editor.syllables[0].end, 0.001)
        assertEquals(1.2, editor.syllables[1].start, 0.001)
        assertEquals(1.4, editor.syllables[1].end, 0.001)

        val idsToMerge = listOf(editor.syllables[0].id, editor.syllables[1].id)
        val mergeRes = editor.mergeSyllables(idsToMerge)
        assertTrue(mergeRes.success)
        assertEquals(2, editor.syllables.size)
        assertEquals(1.0, editor.syllables[0].start, 0.001)
        assertEquals(1.4, editor.syllables[0].end, 0.001)
    }

    @Test
    fun testDeleteSyllable() {
        val editor = AssEditor(createSampleSyllables())
        assertEquals(2, editor.syllables.size)

        editor.deleteSyllable("syl-1")
        assertEquals(1, editor.syllables.size)
        assertEquals("world", editor.syllables[0].text)

        editor.undo()
        assertEquals(2, editor.syllables.size)
        assertEquals("Hello", editor.syllables[0].text)
    }

    @Test
    fun testTagTypeAndTiming() {
        val editor = AssEditor(createSampleSyllables())
        editor.setTagType(listOf("syl-1"), KaraokeTagType.KO)
        assertEquals(KaraokeTagType.KO, editor.syllables[0].tagType)

        editor.setTiming("syl-1", 0.8, 1.3)
        assertEquals(0.8, editor.syllables[0].start, 0.001)
        assertEquals(1.3, editor.syllables[0].end, 0.001)

        editor.undo()
        assertEquals(1.0, editor.syllables[0].start, 0.001)
        assertEquals(1.4, editor.syllables[0].end, 0.001)
    }

    @Test
    fun testToggleUnspoken() {
        val editor = AssEditor(createSampleSyllables())
        assertFalse(editor.syllables[0].isUnspoken)

        editor.toggleUnspoken(listOf("syl-1"))
        assertTrue(editor.syllables[0].isUnspoken)

        editor.toggleUnspoken(listOf("syl-1"))
        assertFalse(editor.syllables[0].isUnspoken)
    }
}
