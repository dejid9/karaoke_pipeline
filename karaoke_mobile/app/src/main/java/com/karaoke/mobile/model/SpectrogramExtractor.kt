package com.karaoke.mobile.model

import androidx.compose.ui.graphics.Color
import kotlin.math.*

/**
 * Настройки анализа спектрограммы (соответствуют SpectrogramAnalysisSettings из ПК-версии).
 */
data class SpectrogramAnalysisSettings(
    val sampleRate: Int = 22050,
    val fftSize: Int = 256,
    val overlap: Float = 0.75f,
    val window: String = "hann"
) {
    val hopSize: Int get() = max(1, (fftSize * (1.0f - overlap)).roundToInt())
}

/**
 * Настройки отображения спектрограммы (соответствуют SpectrogramViewSettings из ПК-версии).
 */
data class SpectrogramViewSettings(
    val minFrequency: Float = 80.0f,
    val maxFrequency: Float = 5000.0f,
    val dbFloor: Float = -72.0f,
    val dbCeiling: Float = -8.0f,
    val frequencyScale: String = "linear"
)

/**
 * Режим отображения дорожки на таймлайне.
 */
enum class TimelineViewMode(val title: String) {
    WAVEFORM("Волна"),
    SPECTROGRAM("Спектр"),
    BOTH("Совместно")
}

/**
 * Рассчитанные данные спектрограммы для таймлайна.
 */
data class SpectrogramData(
    val frames: List<FloatArray>, // Каждый фрейм — массив амплитуд в дБ по частотным бинам
    val sampleRate: Int,
    val hopSize: Int,
    val numBins: Int,
    val durationSec: Double
) {
    val frameDurationSec: Double = hopSize.toDouble() / sampleRate.toDouble()
}

/**
 * Цветовая карта Magma / Inferno для спектрограммы (из ПК-версии karaoke_core/spectrogram.py).
 */
object SpectrogramColorMap {
    private val COLOR_STOPS = arrayOf(
        0.00f to Color(0xFF080A12), // (8, 10, 18)
        0.20f to Color(0xFF19264E), // (25, 38, 78)
        0.43f to Color(0xFF49307E), // (73, 48, 126)
        0.68f to Color(0xFFB24E52), // (178, 78, 82)
        0.86f to Color(0xFFEB9B48), // (235, 155, 72)
        1.00f to Color(0xFFFFEEB8)  // (255, 238, 184)
    )

    fun getColor(normalized: Float): Color {
        val n = normalized.coerceIn(0f, 1f)
        for (i in 0 until COLOR_STOPS.size - 1) {
            val (pos1, col1) = COLOR_STOPS[i]
            val (pos2, col2) = COLOR_STOPS[i + 1]
            if (n in pos1..pos2) {
                val factor = (n - pos1) / (pos2 - pos1)
                return Color(
                    red = col1.red + factor * (col2.red - col1.red),
                    green = col1.green + factor * (col2.green - col1.green),
                    blue = col1.blue + factor * (col2.blue - col1.blue),
                    alpha = 1.0f
                )
            }
        }
        return COLOR_STOPS.last().second
    }
}

/**
 * Быстрый расчёт спектрограммы на основе БПФ (Radix-2 Cooley-Tukey FFT).
 */
object SpectrogramExtractor {

    fun computeSpectrogram(
        rawSamples: FloatArray,
        analysis: SpectrogramAnalysisSettings,
        view: SpectrogramViewSettings
    ): SpectrogramData {
        val n = analysis.fftSize
        val hop = analysis.hopSize
        val numBins = n / 2
        val window = createHannWindow(n)

        val totalFrames = max(1, (rawSamples.size - n) / hop)
        // Для производительности мобильного рендеринга ограничиваем максимальное число фреймов до ~3000
        val step = max(1, totalFrames / 3000)
        val frames = ArrayList<FloatArray>(totalFrames / step + 1)

        val real = FloatArray(n)
        val imag = FloatArray(n)

        var offset = 0
        while (offset + n <= rawSamples.size) {
            // Применяем окно
            for (i in 0 until n) {
                real[i] = rawSamples[offset + i] * window[i]
                imag[i] = 0f
            }

            // FFT in-place
            fft(real, imag)

            // Вычисляем магнитуды в дБ
            val binMags = FloatArray(numBins)
            for (k in 0 until numBins) {
                val magSq = real[k] * real[k] + imag[k] * imag[k]
                val mag = sqrt(magSq)
                // Преобразуем в dB
                val db = (20.0f * log10(max(1e-6f, mag))).coerceIn(view.dbFloor, view.dbCeiling)
                binMags[k] = db
            }
            frames.add(binMags)

            offset += hop * step
        }

        val effectiveHop = hop * step
        val duration = rawSamples.size.toDouble() / analysis.sampleRate.toDouble()
        return SpectrogramData(
            frames = frames,
            sampleRate = analysis.sampleRate,
            hopSize = effectiveHop,
            numBins = numBins,
            durationSec = duration
        )
    }

    /**
     * Генерация спектрограммы на основе waveform и слогов (для быстрого превью без полного декодирования).
     */
    fun generateEstimatedSpectrogram(
        waveformData: List<Float>,
        durationSec: Double,
        analysis: SpectrogramAnalysisSettings,
        view: SpectrogramViewSettings
    ): SpectrogramData {
        val numBins = analysis.fftSize / 2
        val framesCount = max(50, min(1500, waveformData.size))
        val frames = ArrayList<FloatArray>(framesCount)

        val binFreqStep = (analysis.sampleRate / 2f) / numBins

        for (i in 0 until framesCount) {
            val amp = waveformData.getOrNull(i) ?: 0.05f
            val binMags = FloatArray(numBins)

            for (k in 0 until numBins) {
                val freq = k * binFreqStep
                // Имитация спектрального спада речи (1/f) с формантными пиками в области 300-800 Гц и 2000-3500 Гц
                val formant1 = exp(-((freq - 500f) * (freq - 500f)) / (2f * 200f * 200f)) * 0.9f
                val formant2 = exp(-((freq - 2200f) * (freq - 2200f)) / (2f * 500f * 500f)) * 0.7f
                val formant3 = exp(-((freq - 3500f) * (freq - 3500f)) / (2f * 800f * 800f)) * 0.4f
                val rolloff = 1f / (1f + freq / 1000f)

                val energy = amp * (formant1 + formant2 + formant3 + rolloff * 0.5f).coerceIn(0.01f, 1f)
                val db = (view.dbFloor + energy * (view.dbCeiling - view.dbFloor)).coerceIn(view.dbFloor, view.dbCeiling)
                binMags[k] = db
            }
            frames.add(binMags)
        }

        val hopSize = if (framesCount > 0) ((durationSec * analysis.sampleRate) / framesCount).toInt().coerceAtLeast(1) else analysis.hopSize
        return SpectrogramData(
            frames = frames,
            sampleRate = analysis.sampleRate,
            hopSize = hopSize,
            numBins = numBins,
            durationSec = durationSec
        )
    }

    private fun createHannWindow(size: Int): FloatArray {
        val win = FloatArray(size)
        for (i in 0 until size) {
            win[i] = 0.5f * (1.0f - cos(2.0f * Math.PI.toFloat() * i / (size - 1)))
        }
        return win
    }

    /**
     * Radix-2 Cooley-Tukey FFT in-place.
     */
    private fun fft(real: FloatArray, imag: FloatArray) {
        val n = real.size
        var j = 0
        for (i in 0 until n - 1) {
            if (i < j) {
                val tempR = real[i]
                real[i] = real[j]
                real[j] = tempR
                val tempI = imag[i]
                imag[i] = imag[j]
                imag[j] = tempI
            }
            var k = n shr 1
            while (k <= j) {
                j -= k
                k = k shr 1
            }
            j += k
        }

        var len = 2
        while (len <= n) {
            val half = len shr 1
            val angle = -2.0 * Math.PI / len
            val wStepR = cos(angle).toFloat()
            val wStepI = sin(angle).toFloat()

            var i = 0
            while (i < n) {
                var wR = 1.0f
                var wI = 0.0f
                for (k in 0 until half) {
                    val uR = real[i + k]
                    val uI = imag[i + k]
                    val vR = real[i + k + half] * wR - imag[i + k + half] * wI
                    val vI = real[i + k + half] * wI + imag[i + k + half] * wR

                    real[i + k] = uR + vR
                    imag[i + k] = uI + vI
                    real[i + k + half] = uR - vR
                    imag[i + k + half] = uI - vI

                    val nextWR = wR * wStepR - wI * wStepI
                    val nextWI = wR * wStepI + wI * wStepR
                    wR = nextWR
                    wI = nextWI
                }
                i += len
            }
            len = len shl 1
        }
    }
}
