package com.karaoke.mobile

import com.karaoke.mobile.model.AssParser
import com.karaoke.mobile.model.KaraokeTag
import com.karaoke.mobile.model.formatTime
import com.karaoke.mobile.model.parseTime
import org.junit.Assert.*
import org.junit.Test

class AssParserTest {
    @Test
    fun testParseTime() {
        assertEquals(61000L, parseTime("1:01.00"))
        assertEquals(3661000L, parseTime("1:01:01.00"))
        assertEquals(500L, parseTime("0:00.50"))
    }

    @Test
    fun testFormatTime() {
        assertEquals("01:01.00", formatTime(61000L))
        assertEquals("00:00.50", formatTime(500L))
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
            Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\\k100}Hello {\\kf200}World
        """.trimIndent()

        val parsed = AssParser.parse(ass)
        assertEquals(1, parsed.lines.size)
        assertEquals(2, parsed.lines[0].syllables.size)
        assertEquals("Hello ", parsed.lines[0].syllables[0].text)
        assertEquals(KaraokeTag.K, parsed.lines[0].syllables[0].tag)
        assertEquals(KaraokeTag.KF, parsed.lines[0].syllables[1].tag)
    }

    @Test
    fun testSerializeAndParse() {
        val original = """
            [Script Info]
            Title: Test
            
            [V4+ Styles]
            Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
            
            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\\k100}Test
        """.trimIndent()

        val parsed = AssParser.parse(original)
        val serialized = AssParser.serialize(parsed)
        val reparsed = AssParser.parse(serialized)
        assertEquals(parsed.lines.size, reparsed.lines.size)
    }
}
