package com.karaoke.mobile.model

import android.content.Context
import android.media.MediaExtractor
import android.media.MediaFormat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.ByteBuffer
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

data class WaveformData(
    val samplesPerPixel: Int,
    val minAmplitudes: FloatArray,
    val maxAmplitudes: FloatArray,
    val durationMs: Long
)

object WaveformExtractor {
    suspend fun extract(context: Context, uri: android.net.Uri, targetSamples: Int = 2000): WaveformData? =
        withContext(Dispatchers.IO) {
            try {
                val extractor = MediaExtractor()
                extractor.setDataSource(context, uri, null)
                val trackIndex = (0 until extractor.trackCount).firstOrNull { i ->
                    val format = extractor.getTrackFormat(i)
                    format.getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
                } ?: return@withContext null

                extractor.selectTrack(trackIndex)
                val format = extractor.getTrackFormat(trackIndex)
                val durationUs = format.getLong(MediaFormat.KEY_DURATION)
                val durationMs = durationUs / 1000

                val sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                val channelCount = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)

                val buffer = ByteBuffer.allocate(1024 * 1024)
                val allSamples = mutableListOf<Short>()

                while (true) {
                    val sampleSize = extractor.readSampleData(buffer, 0)
                    if (sampleSize < 0) break
                    buffer.position(0)
                    while (buffer.remaining() >= 2) {
                        allSamples.add(buffer.short)
                    }
                    buffer.clear()
                    extractor.advance()
                }
                extractor.release()

                if (allSamples.isEmpty()) return@withContext null

                val samplesPerPixel = max(1, allSamples.size / targetSamples)
                val minAmps = FloatArray(targetSamples)
                val maxAmps = FloatArray(targetSamples)

                for (i in 0 until targetSamples) {
                    val start = i * samplesPerPixel
                    val end = min(start + samplesPerPixel, allSamples.size)
                    var minVal = 0
                    var maxVal = 0
                    for (j in start until end) {
                        val sample = allSamples[j].toInt()
                        if (sample < minVal) minVal = sample
                        if (sample > maxVal) maxVal = sample
                    }
                    minAmps[i] = abs(minVal) / 32768f
                    maxAmps[i] = abs(maxVal) / 32768f
                }

                WaveformData(
                    samplesPerPixel = samplesPerPixel,
                    minAmplitudes = minAmps,
                    maxAmplitudes = maxAmps,
                    durationMs = durationMs
                )
            } catch (e: Exception) {
                e.printStackTrace()
                null
            }
        }
}
