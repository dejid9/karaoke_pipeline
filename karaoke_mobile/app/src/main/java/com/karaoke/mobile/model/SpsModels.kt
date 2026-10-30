package com.karaoke.mobile.model

import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Точка на графике артикуляционной скорости (SPS).
 */
data class SpsPoint(
    val time: Double,
    val speed: Double,
    val count: Int = 0,
    val syllableId: String? = null
)

/**
 * Быстрый участок песни (очередь слогов / Burst).
 */
data class SpsBurst(
    val id: String = UUID.randomUUID().toString(),
    val start: Double,
    val end: Double,
    val peakSps: Double,
    val meanSps: Double,
    val text: String,
    val syllableIds: List<String>
) {
    val duration: Double get() = max(0.0, end - start)
}

/**
 * Общая статистика скорости слогов по проекту.
 */
data class SpsStatistics(
    val peakSps: Double = 0.0,
    val meanSps: Double = 0.0,
    val totalSyllables: Int = 0,
    val burstCount: Int = 0,
    val fastestSyllableText: String = "",
    val duration: Double = 0.0
)

object SpsCalculator {

    /**
     * Расчет точек графика скорости SPS во времени с скользящим окном windowSeconds (по умолчанию 1.0с).
     */
    fun calculateSpsCurve(
        syllables: List<KaraokeSyllable>,
        windowSeconds: Double = 1.0,
        stepSeconds: Double = 0.05
    ): List<SpsPoint> {
        val spoken = syllables.filter { !it.isUnspoken && it.text.trim().isNotEmpty() && it.end > it.start }
        if (spoken.isEmpty()) return emptyList()

        val songStart = spoken.minOf { it.start }
        val songEnd = spoken.maxOf { it.end }
        val halfWin = windowSeconds / 2.0

        val points = mutableListOf<SpsPoint>()
        var t = songStart
        while (t <= songEnd) {
            val winStart = t - halfWin
            val winEnd = t + halfWin

            // Слоги, пересекающие окно
            var count = 0
            for (s in spoken) {
                if (s.start < winEnd && s.end > winStart) {
                    count++
                }
            }

            val speed = count.toDouble() / windowSeconds
            points.add(SpsPoint(time = t, speed = speed, count = count))
            t += stepSeconds
        }
        return points
    }

    /**
     * Поиск скоростных очередей (Bursts) в песне.
     * Группирует слоги с паузами не более maxGap, где пиковая скорость >= minPeakSps.
     */
    fun detectBursts(
        syllables: List<KaraokeSyllable>,
        minPeakSps: Double = 5.0,
        maxGap: Double = 0.4
    ): List<SpsBurst> {
        val spoken = syllables.filter { !it.isUnspoken && it.text.trim().isNotEmpty() && it.end > it.start }
        if (spoken.size < 2) return emptyList()

        // Разбиваем слоги на связные фразы по паузам
        val phrases = mutableListOf<MutableList<KaraokeSyllable>>()
        var currentPhrase = mutableListOf<KaraokeSyllable>()

        for (s in spoken) {
            if (currentPhrase.isEmpty()) {
                currentPhrase.add(s)
                continue
            }
            val gap = max(0.0, s.start - currentPhrase.last().end)
            if (gap <= maxGap) {
                currentPhrase.add(s)
            } else {
                phrases.add(currentPhrase)
                currentPhrase = mutableListOf(s)
            }
        }
        if (currentPhrase.isNotEmpty()) {
            phrases.add(currentPhrase)
        }

        val bursts = mutableListOf<SpsBurst>()

        for (phrase in phrases) {
            if (phrase.size < 2) continue
            val pStart = phrase.first().start
            val pEnd = phrase.last().end
            val pDur = max(0.1, pEnd - pStart)

            // Расчет локальных скоростей для каждого слога
            val localSpeeds = phrase.map { s ->
                val d = max(0.02, s.duration)
                1.0 / d
            }
            val peak = localSpeeds.maxOrNull() ?: 0.0
            val mean = phrase.size.toDouble() / pDur

            if (peak >= minPeakSps || mean >= 4.5) {
                val text = phrase.joinToString("") { it.text }.trim()
                bursts.add(
                    SpsBurst(
                        start = pStart,
                        end = pEnd,
                        peakSps = (peak * 10.0).roundToInt() / 10.0,
                        meanSps = (mean * 10.0).roundToInt() / 10.0,
                        text = text,
                        syllableIds = phrase.map { it.id }
                    )
                )
            }
        }

        return bursts.sortedByDescending { it.peakSps }
    }

    /**
     * Сводная статистика по скорости слогов в песне.
     */
    fun calculateStatistics(syllables: List<KaraokeSyllable>): SpsStatistics {
        val spoken = syllables.filter { !it.isUnspoken && it.text.trim().isNotEmpty() && it.end > it.start }
        if (spoken.isEmpty()) return SpsStatistics()

        val durations = spoken.map { max(0.02, it.duration) }
        val speeds = durations.map { 1.0 / it }
        val peak = speeds.maxOrNull() ?: 0.0
        val maxIdx = speeds.indexOfFirst { it == peak }
        val fastestText = if (maxIdx >= 0) spoken[maxIdx].text.trim() else ""

        val totalDuration = spoken.maxOf { it.end } - spoken.minOf { it.start }
        val mean = if (totalDuration > 0) spoken.size / totalDuration else 0.0
        val bursts = detectBursts(syllables)

        return SpsStatistics(
            peakSps = (peak * 10.0).roundToInt() / 10.0,
            meanSps = (mean * 10.0).roundToInt() / 10.0,
            totalSyllables = spoken.size,
            burstCount = bursts.size,
            fastestSyllableText = fastestText,
            duration = totalDuration
        )
    }
}
