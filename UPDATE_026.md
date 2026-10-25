# Update 026 — persistent player / Audacity-like transport

Этот пакет заменяет запуск отдельного короткого плеера для каждого слога на постоянный Windows audio backend.

## Что изменено

- Один WinMM `waveOut` endpoint держится открытым всё время работы программы.
- FFmpeg декодирует выбранный участок напрямую в `s16le 48 kHz stereo`, который потоково отправляется в уже открытое устройство.
- Короткие слоги больше не требуют 700-мс тишины перед собой в нормальном Windows backend.
- Добавлены обычные `Play/Pause` и `Stop`: обычный Play идёт от текущей полосы до конца медиа.
- Клик по детальному timeline ставит playhead.
- Playhead синхронно отображается в overview и detail timeline и обновляется без полной перерисовки waveform/spectrogram.
- Добавлена скорость 0.25×–2.00×. Используется `atempo`, то есть изменение скорости сохраняет pitch.
- Смена скорости во время playback перезапускает декодирование с текущей позиции, но не закрывает waveOut-устройство.
- Добавлена настраиваемая задержка визуального playhead (0–750 мс, default 80 мс) для компенсации остаточной аппаратной latency.
- Старый WAV+warm-up+`winsound`/`ffplay` оставлен как fallback, если WinMM backend недоступен.

## Проверки

- Python compile: OK.
- Targeted regression suite: 24/24.
- New transport tests: 5/5.
- GUI smoke under Xvfb: OK (Windows waveOut закономерно недоступен в Linux и корректно остаётся fallback).
