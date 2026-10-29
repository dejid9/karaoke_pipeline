# ИНСТРУКЦИЯ ДЛЯ CLAUDE OPUS 4.6 THINKING: РЕДИЗАЙН МОБИЛЬНОГО ИНТЕРФЕЙСА (`ui_alt`)

> **ВНИМАНИЕ! КРИТИЧЕСКОЕ ОГРАНИЧЕНИЕ ПО ТОКЕНАМ:**
> У пользователя **крайне малый лимит токенов**.
> 1. **Внутреннее рассуждение (Thinking):** МИНИМАЛЬНОЕ (не более 3–5 предложений в уме). ЗАПРЕЩЕНО пересказывать условие задачи, рассуждать по кругу или цитировать исходники. Сразу переходи к коду.
> 2. **Формат ответа:** СТРОГО готовый код файлов без вступительных слов, приветствий, объяснений («Вот код...») и заключений. Выдавай ТОЛЬКО блоки кода с указанием пути файла.
> 3. **Изоляция:** Код пиши ТОЛЬКО в директорию `karaoke_mobile/src/ui_alt/`. Папку `karaoke_mobile/src/ui/` НЕ трогать.
> 4. **Ядро:** ЗАПРЕЩЕНО переписывать или дублировать логику из `core/`. Все модули `core.*` полностью готовы, оттестированы и импортируются напрямую.

---

## 1. Цель задачи
Переосмыслить и написать эргономичный, удобный мобильный интерфейс для караоке-редактора в папке `karaoke_mobile/src/ui_alt/`.
Дизайн должен приблизить опыт использования мобильной версии к возможностям ПК-версии (`karaoke_gui`), решив проблемы интерфейса на экранах смартфонов (особенно вытянутых **20:9**).

---

## 2. Ключевые проблемы старого UI и требования к дизайну

### Проблема 1: Вытянутые экраны 20:9 и ориентация
- **В портретном режиме (вертикально):** экран узкий. Не запирать текст в узких контейнерах (ранее текст «Караоке редактор» и количество слогов вытягивался вертикально буквой за буквой, закрывая всё поле). Кнопки управления не должны вылезать за левый или правый край экрана.
- **В ландшафтном режиме (горизонтально 20:9):** экран очень широкий, но низкий по высоте. Верхняя шапка и нижний навбар съедают драгоценные пиксели.
  - **Решение:** Адаптивная двухколоночная верстка (2-Column Split):
    - Слева (50-55% ширины): Таймлайн (спектрограмма + вейвформа), курсор, зум и транспорт воспроизведения.
    - Справа (45-50% ширины): Список слогов со скроллом, компактная панель редактирования выбранного слога и действий.
  - В портрете — вертикальный стек с компактными строками кнопок или выпадающей шторкой (BottomSheet).

### Проблема 2: Функционал из ПК-версии (PC-parity)
1. **Спектрограмма и вейвформа на таймлайне:**
   - Отображение спектрограммы (`render_spectrogram_bmp`) и вейвформы (`render_waveform_bmp`).
   - Отображение границ слогов (цветные плашки / метки поверх или под таймлайном) с возможностью тапа для выбора.
   - Курсор воспроизведения (playhead) с синхронизацией времени в миллисекундах.
2. **Воспроизведение звука:**
   - Кнопки Play / Pause, перемотка по тапу на таймлайн.
   - Регулировка скорости воспроизведения (0.5x, 0.75x, 1.0x, 1.25x, 1.5x).
   - Маркеры диапазона In/Out (`[I]` и `[O]`) для зацикленного прослушивания фрагмента.
3. **«✂ По курсору» (Split at cursor):**
   - Разделение активного слога ровно по текущей позиции курсора воспроизведения:
     `split_syllable_at_time(doc, syl_id, split_time_ms)`.
4. **Множественное выделение слогов (Multi-select):**
   - Возможность выбрать несколько слогов (например, через режим выбора или чекбоксы/тап), чтобы кнопка **«Слить» (`merge_syllables`)** объединяла выделенные слоги.
5. **Компактное и точное редактирование таймингов:**
   - Никаких громоздких контейнеров на пол-экрана.
   - Компактный ряд кнопок-шагов: `[-100] [-50] [-10] [+10] [+50] [+100]` для Start и End или сдвига (`shift_syllable`).
6. **Редактирование текста слога:**
   - Быстрый ввод текста слога (inline TextField или лаконичный диалог) и переключение тега караоке (`\k`, `\kf`, `\ko`).
7. **Просмотр полного текста песни:**
   - Кнопка для вызова диалога со всеми строками и слогами песни.

---

## 3. Архитектурный контракт с `main.py`

Точка входа `karaoke_mobile/src/main.py` уже поддерживает флаг `KARAOKE_UI_ALT=1` и использует `ui.view_resolver`.
Если модуль в `ui_alt` отсутствует, приложение автоматически берет стандартную версию из `ui/`.

### Главный файл для реализации:
`karaoke_mobile/src/ui_alt/views/editor_view.py`
(и при необходимости `karaoke_mobile/src/ui_alt/components/audio_timeline.py`)

Класс `EditorView` должен наследоваться от `ft.Container` (или `ft.Column`):
```python
class EditorView(ft.Container):
    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_jump_to_sps: Optional[Callable[[str], None]] = None,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[object], Optional[object]], None]] = None,
    ):
        ...
```

**Обязательные атрибуты и методы `EditorView`:**
1. `self.audio_timeline`: Экземпляр виджета таймлайна с методами/полями:
   - `set_audio(name: str, audio_bytes: Optional[bytes], waveform: Optional[WaveformData], spectrogram: Optional[SpectrogramData])`
   - `center_time: float` (текущая позиция курсора в секундах)
   - `is_playing: bool`
   - `stop_audio()`
2. `self.document: Optional[AssDocument]`
3. `self.selected_syllable_id: Optional[str]`
4. `def _refresh_ui(self):` — перерисовка списка слогов и таймлайна при изменении данных.
5. `def apply_theme(self, palette: ThemePalette):` — обновление цветов (фон, текст, границы, акцент).
6. `def set_page(self, page: ft.Page):` — сохранение ссылки на страницу Flet.
7. `def get_services(self) -> list:` — возврат сервисов (например, `[self.ass_picker]`).

---

## 4. Доступные готовые API ядра (Импортируй, НЕ переписывай!)

```python
# 1. Документ и слоги
from core.ass import AssDocument, KaraokeSyllable, KaraokeTagType, format_ass_time
# doc.karaoke_syllables() -> список KaraokeSyllable(id, text, start_ms, end_ms, duration_ms, line_index, syl_index, tag_type, is_pause)
# doc.update_syllable(id, text=..., start_ms=..., end_ms=..., tag_type=...)
# doc.to_text() -> str

# 2. Операции редактирования слогов
from core.editor import (
    split_syllable_at_time,      # (doc, syl_id, split_time_ms) -> (left_syl, right_syl)
    split_syllable,              # (doc, syl_id, char_offset)
    merge_syllables,             # (doc, [id1, id2, ...]) -> merged_syl
    shift_syllable,              # (doc, syl_id, delta_ms)
    nudge_syllable_duration,     # (doc, syl_id, delta_ms)
    set_syllable_text,           # (doc, syl_id, text)
    set_syllable_start_at_time,  # (doc, syl_id, start_ms)
    set_syllable_end_at_time,    # (doc, syl_id, end_ms)
    redistribute_boundary,       # (doc, syl_id_left, syl_id_right, new_boundary_ms)
    delete_syllable,             # (doc, syl_id)
    set_tag_type,                # (doc, syl_id, tag_type)
)

# 3. Готовый рендеринг спектрограммы и вейвформы в BMP (без numpy!)
from core.media import WaveformData, render_waveform_bmp
from core.spectrogram import SpectrogramData, render_spectrogram_bmp

# 4. Тема и настройки экрана
from ui.theme import ThemePalette, get_current_palette
from ui.display_settings import get_display_settings
# ds = get_display_settings()
# ds.font_size(12), ds.icon_size(20), ds.button_padding(8, 5)
```

---

## 5. Требуемые файлы для генерации

Сгенерируй чистый, самодостаточный код для следующих двух файлов:

1. **`karaoke_mobile/src/ui_alt/components/audio_timeline.py`**
   - Виджет таймлайна с поддержкой:
     - Отрисовки вейвформы / спектрограммы (BMP Image в base64).
     - Полосы слогов с подсветкой активного/выделенных.
     - Курсора воспроизведения, зума (пикселей на секунду), перемотки по тапу/драгу.
     - Воспроизведения аудио (`flet_audio.Audio` или воспроизведение WAV) с поддержкой скорости (0.5x, 0.75x, 1.0x, 1.25x, 1.5x) и маркеров In/Out.
     - Сворачивания в компактный режим без потери кнопок Play/Pause.

2. **`karaoke_mobile/src/ui_alt/views/editor_view.py`**
   - Главный экран редактирования:
     - Адаптивность к 20:9 (split-view в ландшафте, компактный стек в портрете).
     - Список слогов с чипом тайминга, длительности и текста.
     - Одиночное и множественное выделение слогов.
     - Действия: «✂ По курсору», «Слить», «Сдвиг», «Тайминг» (+/-10, +/-50), «Текст», «Удалить», «Весь текст».
     - Полная реализация интерфейса контракта `EditorView`.

---

## 6. Формат вывода для Claude

Выведи файлы в виде отдельных блоков кода:
```python
# File: karaoke_mobile/src/ui_alt/components/audio_timeline.py
...
```
```python
# File: karaoke_mobile/src/ui_alt/views/editor_view.py
...
```

**Никакого лишнего текста до и после кода.**
