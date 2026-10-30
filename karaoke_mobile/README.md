# Karaoke Mobile

Мобильная версия редактора ASS-караоке для Android. Позволяет редактировать тайминги слогов, тексты и границы прямо на телефоне или планшете.

## Возможности

- **Редактирование ASS-файлов** — полная поддержка тегов `\k`, `\kf`, `\ko`, `\K`
- **Аудиоплеер** — воспроизведение с переменной скоростью (0.5×–1.5×)
- **Визуальный таймлайн** — pinch-to-zoom, drag для перемотки, tap для выбора слога
- **Визуализация waveform** — отображение амплитуды аудио на таймлайне
- **Inline-редактирование** — редактируйте текст слогов прямо в интерфейсе
- **Навигация по слогам** — быстрое переключение между слогами с автопрокруткой
- **Undo/Redo** — история изменений до 100 шагов
- **Burst-метки** — пометка непропетых участков
- **Диапазоны In/Out** — циклическое воспроизведение выбранного фрагмента

## Структура проекта

```
karaoke_mobile/
├── app/
│   ├── src/main/java/com/karaoke/mobile/
│   │   ├── MainActivity.kt              # Главный экран с навигацией
│   │   ├── model/
│   │   │   ├── AssModels.kt             # Модели данных (AssLine, Syllable, etc.)
│   │   │   ├── AssParser.kt             # Парсер/сериализатор ASS
│   │   │   ├── AssEditor.kt             # Ядро редактора с undo/redo
│   │   │   └── WaveformExtractor.kt     # Извлечение waveform из аудио
│   │   ├── viewmodel/
│   │   │   └── StudioState.kt           # ViewModel состояния студии
│   │   └── ui/
│   │       ├── theme/
│   │       │   ├── Color.kt             # Цветовая палитра
│   │       │   ├── Theme.kt             # Material Theme
│   │       │   └── Type.kt              # Типографика
│   │       └── components/
│   │           ├── Timeline.kt          # Таймлайн с waveform
│   │           ├── SyllablesTab.kt      # Список строк/слогов
│   │           ├── FilesTab.kt          # Управление файлами
│   │           ├── InspectorPane.kt     # Панель управления плеером
│   │           └── EmptyState.kt        # Пустое состояние
│   └── build.gradle.kts
├── build.gradle.kts
├── settings.gradle.kts
└── gradle/
```

## Технологии

- Kotlin 2.0.21
- Jetpack Compose (BOM 2024.12.01)
- Material Design 3
- MediaPlayer + MediaExtractor (waveform)
- Coroutines

## Сборка

```bash
./gradlew :app:assembleDebug
```

## CI/CD

Сборка автоматизирована через GitHub Actions:
- Debug APK собирается на каждый push/PR
- Release APK с подписью — на git tag `v*`

Для release-сборки добавьте секреты в репозиторий:
- `SIGNING_KEY` — base64-кодированный keystore
- `ALIAS` — alias ключа
- `KEY_STORE_PASSWORD` — пароль keystore
- `KEY_PASSWORD` — пароль ключа

## Отличия от ПК-версии

Мобильная версия фокусируется на редактировании ASS. Следующие функции остаются в ПК-версии:
- MFA (Montreal Forced Aligner)
- Точные SPS-измерения
- Спектрограмма
- Видеорендер
