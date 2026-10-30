package com.karaoke.mobile

import com.karaoke.mobile.model.AssDocument
import com.karaoke.mobile.model.AssParser
import com.karaoke.mobile.model.KaraokeTagType
import com.karaoke.mobile.model.formatAssTime
import com.karaoke.mobile.model.parseAssTime
import org.junit.Assert.assertEquals
import org.junit.Test

class AssParserTest {
    @Test
    fun testParseTime() {
        assertEquals(61.0, parseAssTime("1:01.00"), 0.001)
        assertEquals(3661.0, parseAssTime("1:01:01.00"), 0.001)
        assertEquals(0.5, parseAssTime("0:00.50"), 0.001)
        assertEquals(0.5, parseAssTime("0:00:00.50"), 0.001)
    }

    @Test
    fun testFormatTime() {
        assertEquals("0:01:01.00", formatAssTime(61.0))
        assertEquals("0:00:00.50", formatAssTime(0.5))
    }

    @Test
    fun testParseSimpleAss() {
        val ass = """
            [Script Info]
            Title: Test
            
            [V4+ Styles]
            Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
            
            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\k100}Hello {\kf200}World
        """.trimIndent()

        val parsed = AssParser.parse(ass)
        assertEquals(1, parsed.events.size)
        val event = parsed.events[0]
        assertEquals(2, event.syllables.size)
        assertEquals("Hello", event.syllables[0].text)
        assertEquals(KaraokeTagType.K, event.syllables[0].tagType)
        assertEquals(1.0, event.syllables[0].duration, 0.001)
        assertEquals("World", event.syllables[1].text)
        assertEquals(KaraokeTagType.KF, event.syllables[1].tagType)
        assertEquals(2.0, event.syllables[1].duration, 0.001)
    }

    @Test
    fun testSerializeAndParse() {
        val original = """
            [Script Info]
            Title: Test
            ScriptType: v4.00+
            PlayResX: 1280
            PlayResY: 720

            [V4+ Styles]
            Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            Style: Default,Arial,24,&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0000,0000,0000,,{\k100}Test
        """.trimIndent()

        val parsed = AssParser.parse(original)
        val serialized = parsed.toAssText()
        val reparsed = AssParser.parse(serialized)
        assertEquals(parsed.events.size, reparsed.events.size)
        assertEquals(parsed.events[0].start, reparsed.events[0].start, 0.001)
        assertEquals(parsed.events[0].end, reparsed.events[0].end, 0.001)
    }

    @Test
    fun testPreserveSpacesAndPauses() {
        val original = """
            [Script Info]
            Title: Space and Pause Test
            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            Dialogue: 0,0:00:00.00,0:00:03.50,Default,,0,0,0,,{\kf100}Toda {\kf100}essa {\k50}{\kf100}loucura
        """.trimIndent()

        val doc = AssParser.parse(original)
        val syllables = doc.events[0].syllables
        assertEquals(4, syllables.size)

        // Trailing space preserved on first syllable
        assertEquals("Toda ", syllables[0].text)
        assertEquals(1.0, syllables[0].duration, 0.001)
        assertEquals(0.0, syllables[0].start, 0.001)
        assertEquals(1.0, syllables[0].end, 0.001)

        // Trailing space preserved on second syllable
        assertEquals("essa ", syllables[1].text)
        assertEquals(1.0, syllables[1].duration, 0.001)
        assertEquals(1.0, syllables[1].start, 0.001)
        assertEquals(2.0, syllables[1].end, 0.001)

        // Pause tag kept as unspoken syllable
        assertEquals("", syllables[2].text)
        assertEquals(true, syllables[2].isUnspoken)
        assertEquals(0.5, syllables[2].duration, 0.001)
        assertEquals(2.0, syllables[2].start, 0.001)
        assertEquals(2.5, syllables[2].end, 0.001)

        // Final syllable starts after pause
        assertEquals("loucura", syllables[3].text)
        assertEquals(1.0, syllables[3].duration, 0.001)
        assertEquals(2.5, syllables[3].start, 0.001)
        assertEquals(3.5, syllables[3].end, 0.001)

        // Roundtrip serialization preserves exact text
        val serialized = AssParser.serializeSyllables(syllables)
        assertEquals("{\\kf100}Toda {\\kf100}essa {\\k50}{\\kf100}loucura", serialized)
    }

    @Test
    fun testUtf8BomAndHardLinebreaks() {
        val withBom = "\uFEFF[Script Info]\nTitle: BOM Test\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf100}Trevor\\N{\\kf100}Eu"
        val doc = AssParser.parse(withBom)
        assertEquals("BOM Test", doc.title)
        val syllables = doc.events[0].syllables
        assertEquals(2, syllables.size)
        assertEquals("Trevor\\N", syllables[0].text)
        assertEquals("Eu", syllables[1].text)
        assertEquals("Trevor ↵", syllables[0].displayText)
    }
}
