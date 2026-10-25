"""Tkinter GUI for the karaoke/SPS pipeline.

Update 002 intentionally keeps media decoding out of the GUI. The widgets work
with subtitle timing and project/media paths only; waveform/spectrogram decoding
is scheduled for the next update.
"""

from .session import KaraokeSession

__all__ = ["KaraokeSession"]
