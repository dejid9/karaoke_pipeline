package com.karaoke.mobile.model

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Вкладки приложения, идентичные вкладкам ПК-версии (karaoke_gui).
 */
enum class AppTab(val title: String) {
    PREPARATION("Подготовка"),
    KARAOKE("Караоке"),
    SPS("Точный SPS"),
    RENDER("Рендер"),
    LOGS("Логи")
}

/**
 * Уровень важности записи в логах.
 */
enum class LogLevel(val label: String) {
    INFO("ИНФО"),
    ACTION("ДЕЙСТВИЕ"),
    WARN("ВНИМАНИЕ"),
    ERROR("ОШИБКА")
}

/**
 * Запись в журнале событий приложения.
 */
data class LogEntry(
    val id: Long = System.currentTimeMillis() + (0..999).random(),
    val timestamp: Long = System.currentTimeMillis(),
    val level: LogLevel = LogLevel.INFO,
    val tag: String = "App",
    val message: String
) {
    val timeFormatted: String by lazy {
        val sdf = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault())
        sdf.format(Date(timestamp))
    }
}
