# Update 031 — Windows audio-device hotfix

Install over Update 030.

## Problem

The persistent PortAudio stream was opened once on the WASAPI device that was
Windows' default at application startup. If the system default output device was
changed later (speakers/headphones/Bluetooth/HDMI/USB DAC), the stream stayed
bound to the old endpoint, so playback could become inaudible even though the
transport itself continued to run.

## Fix

- Windows Core Audio default render endpoint is now tracked by endpoint id.
- A lightweight background monitor checks for a real endpoint change every
  750 ms. It does not redraw the GUI or poll through Tk.
- When the default endpoint changes, the old PortAudio stream is stopped and
  closed, PortAudio's device snapshot is refreshed, and a new low-latency
  WASAPI stream is opened on the new default output device.
- Active playback is restored from the current media position when a rebind is
  needed; PCM cache is not rebuilt.
- Every explicit Play also performs a cheap endpoint check, so a switch that
  happens while the monitor is temporarily unavailable is corrected before
  playback starts.
- Ordinary playback does not reopen the device when the endpoint did not
  change, preserving Update 027's low startup latency.

## Settings

`Settings -> Playback` now contains:

- `Следовать системному устройству вывода по умолчанию` (enabled by default);
- current PortAudio/WASAPI output-device description;
- `Переподключить сейчас` for a forced manual refresh.

The auto-follow setting is stored in the global UI preferences.

## Compatibility

No new Python dependency is required. Windows endpoint detection uses the Core
Audio COM API through ctypes; `sounddevice`/PortAudio remains the audio backend.
