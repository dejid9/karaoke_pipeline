# Update 027 — PortAudio transport / PCM cache / global Space

Главная цель — убрать архитектурную причину задержки и зависания playback.

- Добавлен отдельный PCM-кэш 48 kHz stereo (`cache/playback`). FFmpeg декодирует медиа один раз заранее.
- Основной playback backend — `sounddevice`/PortAudio с постоянно открытым RawOutputStream. Старый raw waveOut больше не выбирается как основной backend.
- На 1× и в режиме изменения pitch воспроизведение читает PCM напрямую из memory-mapped cache без запуска FFmpeg в момент Play.
- Для скорости != 1× с включённым «Сохранять тон» используется фоновый `atempo` над готовым raw PCM; PortAudio stream не закрывается.
- Позиция playhead основана на реально отправленных аудиофреймах и output latency, поэтому UI не должен ждать завершения фрагмента и прыгать в конец.
- Добавлен переключатель «Сохранять тон».
- `Space` стал глобальным Play/Pause поверх кнопок/Combobox/таймлайнов; внутри Entry/Text пробел остаётся обычным символом.
- Клик по overview/detail timeline явно переводит фокус на Canvas.
- В doctor добавлена проверка `sounddevice`.

## Установка зависимости

В активной Conda-среде:

```bat
conda install -c conda-forge python-sounddevice
```

или:

```bat
python -m pip install sounddevice
```

После установки перезапустите GUI. При отсутствии `sounddevice` программа не будет молча использовать старый low-latency backend: в строке состояния появится инструкция по установке.
