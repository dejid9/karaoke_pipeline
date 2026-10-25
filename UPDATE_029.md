# Update 029 — immediate PortAudio playhead sync

Исправляет поздний старт полосы воспроизведения после Update 028.

## Причина

PortAudio backend уже держит устройство открытым, но позиция playhead всё ещё вычислялась как `submitted_frame - stream.latency - manual_delay`. На части Windows/WASAPI устройств reported output latency существенно завышает воспринимаемую задержку. Дополнительно у существующих пользователей сохранялось legacy-значение 80 мс.

## Изменения

- Playhead теперь следует за media frame, уже переданным PortAudio callback, без обязательного вычитания `stream.latency`.
- Legacy `playback_cursor_delay_ms` не мигрируется; новый default = 0 мс.
- Вместо задержки добавлена signed fine-tuning настройка `playback_cursor_offset_ms` в диапазоне -250..+250 мс.
- 0 мс рекомендуется по умолчанию.
- `+` двигает визуальную полосу вперёд, `-` назад.
- PortAudio output latency всё ещё используется только там, где он действительно нужен: для безопасного drain хвоста после последнего переданного блока.
- Старый API `set_cursor_delay()` оставлен как compatibility shim, но основное приложение использует `set_cursor_offset()`.

## Проверка

Regression-тест с искусственно большой reported latency 120 мс подтверждает: после первого 10-мс callback playhead показывает ~10 мс, а не остаётся на нуле ~200 мс как раньше. Также проверены signed offset и миграция старой настройки 80 мс в 0.
