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
        assertEquals("La ", doc.events[0].syllables[0].text)

        val mediaFiles = extractedFiles.filter { it.extension.equals("mp3", ignoreCase = true) }
        assertEquals(1, mediaFiles.size)
        assertEquals(1024, mediaFiles[0].length())
    }

    @Test
    fun testComplexDesktopArchiveWithMfaAndBackups() {
        val destDir = tempFolder.newFolder("desktop_archive_project")

        val baos = ByteArrayOutputStream()
        ZipOutputStream(BufferedOutputStream(baos)).use { zip ->
            // project.json
            zip.putNextEntry(ZipEntry("project.json"))
            val jsonStr = """
                {
                    "name": "antares_convida_pt_1_blingg",
                    "media": "antares_convida_pt_1_ivan_o_vic_vocals.mp3",
                    "subtitles": "subtitles/antares_convida_pt_1_ivan_o_vic_vocals.ass"
                }
            """.trimIndent()
            zip.write(jsonStr.toByteArray())
            zip.closeEntry()

            // alignment/mfa/corpus/antares_convida_pt_1_ivan_o_vic_vocals.wav
            zip.putNextEntry(ZipEntry("alignment/mfa/corpus/antares_convida_pt_1_ivan_o_vic_vocals.wav"))
            zip.write(ByteArray(512) { 0x11 })
            zip.closeEntry()

            // antares_convida_pt_1_ivan_o_vic_vocals.mp3
            zip.putNextEntry(ZipEntry("antares_convida_pt_1_ivan_o_vic_vocals.mp3"))
            zip.write(ByteArray(2048) { 0x22 })
            zip.closeEntry()

            // subtitles/antares_convida_pt_1_ivan_o_vic_vocals.ass
            zip.putNextEntry(ZipEntry("subtitles/antares_convida_pt_1_ivan_o_vic_vocals.ass"))
            val assContent = """
                [Script Info]
                Title: Antares
                [Events]
                Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
                Dialogue: 0,0:00:00.00,0:00:54.70,Default,,0,0,0,,{\kf12}Toda {\kf15}essa {\kf18}lou{\kf14}cu{\kf11}ra\N{\kf39}Eu 
            """.trimIndent()
            zip.write(assContent.toByteArray())
            zip.closeEntry()

            // subtitles/antares_convida_pt_1_ivan_o_vic_vocals.ass.bak
            zip.putNextEntry(ZipEntry("subtitles/antares_convida_pt_1_ivan_o_vic_vocals.ass.bak"))
            zip.write(assContent.toByteArray())
            zip.closeEntry()

            // subtitles/backups/antares_convida_pt_1_ivan_o_vic_vocals.ass.bak1
            zip.putNextEntry(ZipEntry("subtitles/backups/antares_convida_pt_1_ivan_o_vic_vocals.ass.bak1"))
            zip.write(assContent.toByteArray())
            zip.closeEntry()
        }

        val extractedFiles = mutableListOf<File>()
        ZipInputStream(BufferedInputStream(ByteArrayInputStream(baos.toByteArray()))).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    val cleanName = entry.name.replace('\\', '/').trimStart('/')
                    val outFile = File(destDir, cleanName)
                    outFile.parentFile?.mkdirs()
                    outFile.outputStream().use { out -> zip.copyTo(out) }
                    extractedFiles.add(outFile)
                }
                zip.closeEntry()
                entry = zip.nextEntry
            }
        }

        // Heuristics filter
        val audioExtensions = setOf("mp3", "wav", "ogg", "flac", "m4a", "aac", "opus")
        val assFiles = extractedFiles.filter { it.extension.equals("ass", ignoreCase = true) }
        val mediaFiles = extractedFiles.filter { it.extension.lowercase() in audioExtensions }

        val usableAssFiles = assFiles.filter { file ->
            !file.path.replace('\\', '/').contains("/backup", ignoreCase = true)
        }.ifEmpty { assFiles }

        val usableMediaFiles = mediaFiles.filter { file ->
            val p = file.path.replace('\\', '/')
            !p.contains("/alignment/", ignoreCase = true) && !p.contains("/mfa/", ignoreCase = true)
        }.ifEmpty { mediaFiles }

        assertEquals(1, usableAssFiles.size)
        assertEquals("antares_convida_pt_1_ivan_o_vic_vocals.ass", usableAssFiles[0].name)

        assertEquals(1, usableMediaFiles.size)
        assertEquals("antares_convida_pt_1_ivan_o_vic_vocals.mp3", usableMediaFiles[0].name)
        assertEquals(2048, usableMediaFiles[0].length())

        val doc = AssParser.parse(usableAssFiles[0].readText())
        val syllables = doc.events[0].syllables
        assertEquals(6, syllables.size)
        assertEquals("Toda ", syllables[0].text)
        assertEquals("essa ", syllables[1].text)
        assertEquals("lou", syllables[2].text)
        assertEquals("cu", syllables[3].text)
        assertEquals("ra\\N", syllables[4].text)
        assertEquals("Eu", syllables[5].text.trim())
    }
}
