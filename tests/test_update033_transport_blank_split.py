from __future__ import annotations

from pathlib import Path
import tempfile

from karaoke_core.ass import AssDocument, KaraokeTagType
from karaoke_core.editor import split_raw_text_ratio, split_syllable_at_time
from karaoke_core.sps import MeasurementTimeline, TimelineSyllable
from karaoke_gui.app import KaraokeApp
from karaoke_gui.session import KaraokeSession


HEADER = """[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""


def _doc(text: str) -> AssDocument:
    return AssDocument.from_text(
        HEADER + f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{text}\n"
    )


def _items(count: int = 20, step: float = 0.1):
    return [TimelineSyllable(f"L0:S{i}", i * step, (i + 1) * step, str(i)) for i in range(count)]


def test_proportional_text_split_ignores_ass_override_blocks():
    doc = _doc(r"{\kf100\c&HFF}ab{\bord2}cdefghij")
    split_syllable_at_time(doc, "L4:S0", 0.30, new_type=KaraokeTagType.KF)
    syllables = doc.karaoke_syllables()
    assert [s.duration_cs for s in syllables] == [30, 70]
    assert [s.visible_text for s in syllables] == ["abc", "defghij"]
    dumped = doc.dumps()
    assert r"\c&HFF" in dumped
    assert r"\bord2" in dumped


def test_proportional_split_supports_empty_unknown_lyrics():
    doc = _doc(r"{\kf100}")
    split_syllable_at_time(doc, "L4:S0", 0.37)
    syllables = doc.karaoke_syllables()
    assert [s.duration_cs for s in syllables] == [37, 63]
    assert [s.visible_text for s in syllables] == ["", ""]


def test_visible_ratio_does_not_count_override_tag_characters():
    left, right = split_raw_text_ratio(r"a{\bord10\shad2}bcdefghi", 0.25)
    visible = lambda x: x.replace(r"{\bord10\shad2}", "")
    assert visible(left) == "ab"
    assert visible(right) == "cdefghi"


def test_blank_ass_has_invisible_seed_span_and_undo_redo_timing():
    session = KaraokeSession()
    session.new_blank_subtitles(12.34)
    assert session.subtitle_path is None
    assert session.dirty is True
    assert len(session.syllables) == 1
    assert session.syllables[0].text == ""
    assert abs(session.syllables[0].end - 12.34) < 1e-9

    sid = session.syllables[0].id
    session.edit_split_at_time(sid, 2.50)
    assert [(round(s.start, 2), round(s.end, 2), s.text) for s in session.syllables] == [
        (0.00, 2.50, ""), (2.50, 12.34, "")
    ]
    assert session.undo()
    assert len(session.syllables) == 1
    assert session.redo()
    assert len(session.syllables) == 2


def test_space_transport_is_independent_from_marker_buttons():
    app = KaraokeApp()
    try:
        items = _items()
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)
        app.playhead_time = 0.47
        app.karaoke_timeline.select_ids((items[2].id,))
        app.set_playback_limit_marker("karaoke", "start")
        app.karaoke_timeline.select_ids((items[14].id,))
        app.set_playback_limit_marker("karaoke", "stop")

        assert app._continuous_bounds("karaoke") == (0.47, None)
        captured = []
        app._begin_transport = lambda start, end, **kw: captured.append((start, end, kw["mode"])) or True
        app.play_from_start_marker("karaoke")
        app.playhead_time = 0.66
        app.play_to_stop_marker("karaoke")
        app.play_between_markers("karaoke")
        assert captured[0] == (items[2].start, None, "from-start")
        assert captured[1] == (0.66, items[14].end, "to-stop")
        assert captured[2] == (items[2].start, items[14].end, "bounded")
    finally:
        app.destroy()


def test_manual_stop_reapplies_return_target_after_idle():
    app = KaraokeApp()
    try:
        class FakePlayer:
            playing = True
            paused = False
            def position(self): return 1.35
            def stop(self): self.playing = False
            def close(self): pass

        try:
            app.player.close()
        except Exception:
            pass
        app.player = FakePlayer()
        app.playback_return_to_start_var.set(True)
        app._playback_origin = 0.42
        app._playback_return_target = 0.42
        app._playback_was_active = True
        app._transport_mode = "bounded"
        app.stop_playback()
        # Simulate one stale paint trying to move the line after Stop; the idle
        # guard must restore the transport origin.
        app._set_playhead(1.35)
        app.update_idletasks()
        assert abs(app.playhead_time - 0.42) < 1e-12
    finally:
        if getattr(app, "_playback_poll_job", None):
            try: app.after_cancel(app._playback_poll_job)
            except Exception: pass
        app.destroy()


def test_transport_buttons_use_u25b6_and_tabs_have_no_number_prefixes():
    app = KaraokeApp()
    try:
        titles = [app.notebook.tab(tab_id, "text") for tab_id in app.notebook.tabs()]
        assert titles == ["Подготовка", "Караоке", "Точный SPS", "Рендер", "Логи"]
        for tab in (app.karaoke_tab, app.sps_tab):
            texts = []
            stack = [tab]
            while stack:
                widget = stack.pop()
                stack.extend(widget.winfo_children())
                try:
                    if widget.winfo_class() == "TButton":
                        texts.append(str(widget.cget("text")))
                except Exception:
                    pass
            for expected in ("|←", "|▶", "→|", "▶|", "|▶|"):
                assert expected in texts
            assert all("\ufe0f" not in text for text in texts)
    finally:
        app.destroy()
