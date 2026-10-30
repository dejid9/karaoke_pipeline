package com.karaoke.mobile

import com.karaoke.mobile.model.AssParser
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

class ProjectZipTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun testExtractZipWithoutClosingStreamPrematurely() {
        val destDir = tempFolder.newFolder("extracted_project")

        // 1. Build a mock zip with desktop/mobile project structure
        val baos = ByteArrayOutputStream()
        ZipOutputStream(BufferedOutputStream(baos)).use { zip ->
            // project.json
            zip.putNextEntry(ZipEntry("my_project/project.json"))
            val jsonStr = """{"name": "Test Song", "media": "source/audio.mp3", "subtitles": "subtitles/track.ass"}"""
            zip.write(jsonStr.toByteArray())
            zip.closeEntry()

            // subtitles/track.ass
            zip.putNextEntry(ZipEntry("my_project/subtitles/track.ass"))
            val assContent = """
                [Script Info]
                Title: Test
                [Events]
                Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
                Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\k50}La {\kf150}la
            """.trimIndent()
            zip.write(assContent.toByteArray())
            zip.closeEntry()

            // source/audio.mp3 (dummy audio data)
            zip.putNextEntry(ZipEntry("my_project/source/audio.mp3"))
            zip.write(ByteArray(1024) { 0x42 })
            zip.closeEntry()
        }

        val zipBytes = baos.toByteArray()

        // 2. Extract using our updated ZipInputStream loop
        val extractedFiles = mutableListOf<File>()
        ZipInputStream(BufferedInputStream(ByteArrayInputStream(zipBytes))).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    val cleanName = entry.name.replace('\\', '/').trimStart('/')
                    val outFile = File(destDir, cleanName)
                    outFile.parentFile?.mkdirs()
                    outFile.outputStream().use { out ->
                        zip.copyTo(out)
                    }
                    extractedFiles.add(outFile)
                }
                zip.closeEntry()
                entry = zip.nextEntry
            }
        }

        assertEquals(3, extractedFiles.size)

        // 3. Heuristic resolution
        val projectJsonFile = extractedFiles.find { it.name.equals("project.json", ignoreCase = true) }
        assertNotNull(projectJsonFile)

        val json = JSONObject(projectJsonFile!!.readText())
        val name = json.optString("name", "Default")
        assertEquals("Test Song", name)

        val assFiles = extractedFiles.filter { it.extension.equals("ass", ignoreCase = true) }
        assertEquals(1, assFiles.size)

        val doc = AssParser.parse(assFiles[0].readText())
        assertEquals(1, doc.events.size)
        assertEquals(2, doc.events[0].syllables.size)
        assertEquals("La", doc.events[0].syllables[0].text)

        val mediaFiles = extractedFiles.filter { it.extension.equals("mp3", ignoreCase = true) }
        assertEquals(1, mediaFiles.size)
        assertEquals(1024, mediaFiles[0].length())
    }
}
