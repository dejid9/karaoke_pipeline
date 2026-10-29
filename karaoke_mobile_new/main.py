"""Unified mobile karaoke editor workbench.

The UI is intentionally kept in one screen: the same workbench adapts from a
wide desktop-like layout to a portrait mobile layout. Editing is delegated to
``core.ass`` and ``core.editor``; this module only owns presentation and state.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import flet as ft

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.ass import AssDocument, KaraokeSyllable, format_ass_time
from core.editor import (
    colour_burst, delete_syllable, insert_after, merge_syllables,
    set_syllable_romanization, set_syllable_text, set_tag_type,
    split_syllable, split_syllable_at_time, uncolour_burst,
)
from core.media import load_waveform, load_or_extract_waveform


BG = "#0b1018"
PANEL = "#141c28"
PANEL_2 = "#1b2635"
BORDER = "#2d3b4f"
TEXT = "#e8edf5"
MUTED = "#8d9bb0"
ACCENT = "#55d6be"
WARN = "#ffb454"
DANGER = "#ff647c"


def button(label: str, handler: Callable, *, primary: bool = False, disabled: bool = False) -> ft.Button:
    return ft.Button(label, on_click=handler, disabled=disabled, bgcolor=ACCENT if primary else PANEL_2,
                     color="#071018" if primary else TEXT)


def card(title: str, controls: list[ft.Control], *, expand: bool = False) -> ft.Container:
    return ft.Container(ft.Column([ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=ACCENT), *controls], spacing=8),
                        bgcolor=PANEL, border=ft.Border.all(1, BORDER), border_radius=10, padding=12, expand=expand)


class Workbench:
    def __init__(self, page: ft.Page):
        self.page = page
        self.doc: AssDocument | None = None
        self.ass_path: Path | None = None
        self.media_path: Path | None = None
        self.waveform = None
        self.selected: list[str] = []
        self.cursor = 0.0
        self.in_point: float | None = None
        self.out_point: float | None = None
        self.speed = 1.0
        self.audio_layer = "Волна"
        self.aspect = "Полный экран"
        self.dpi = 1.0
        self.playing = False
        self.undo_stack: list[str] = []
        self.redo_stack: list[str] = []

        self.status = ft.Text("ASS не загружен", color=MUTED, expand=True)
        self.count = ft.Text("0 слогов", color=ACCENT)
        self.notice = ft.Text("Откройте ASS-файл, чтобы начать работу", color=MUTED, size=12)
        self.timeline = ft.Container(expand=True)
        self.inspector = ft.Container(expand=True)
        self.range_label = ft.Text("Диапазон: —", color=MUTED)
        self.cursor_label = ft.Text("Курсор 0:00.00", color=WARN)
        self.zoom = ft.Slider(min=0.5, max=4, value=1, divisions=14, label="Зум {value}x", on_change=lambda e: self.refresh())
        self.text_field = ft.TextField(label="Текст слога", on_change=self.text_changed)
        self.roman_field = ft.TextField(label="Романизация / фуригана", on_change=self.roman_changed)
        self.tag_dropdown = ft.Dropdown(label="Тег", value="k", options=[ft.DropdownOption(k, f"\\{k}") for k in ("k", "kf", "ko", "K")])
        self.file_picker = ft.FilePicker(on_result=self.file_result)
        if hasattr(page, "services") and self.file_picker not in page.services:
            page.services.append(self.file_picker)
        if hasattr(page, "overlay") and self.file_picker not in page.overlay:
            page.overlay.append(self.file_picker)
        self.build()

    def build(self):
        p = self.page
        p.title = "KARAOKE // SPS — Mobile Workbench"
        p.bgcolor = BG
        p.padding = 0
        p.theme_mode = ft.ThemeMode.DARK
        p.on_resize = lambda e: self.refresh()
        header = ft.Container(ft.Column([
            ft.Row([ft.Text("KARAOKE // SPS", size=20, weight=ft.FontWeight.BOLD, color=ACCENT), self.status, self.count], spacing=16),
            ft.Row([button("Проект…", self.open_project), button("ASS…", self.open_ass), button("Медиа…", self.open_media),
                    button("💾 Сохранить", self.save_ass), button("⚙ Настройки", self.open_settings),
                    button("MFA", lambda e: self.open_drawer("MFA выравнивание", "Автовыравнивание MFA готово для выбранной строки.")),
                    button("SPS", lambda e: self.open_drawer("SPS график", "SPS-анализ строится по текущим таймингам."))], wrap=True)
        ], spacing=8), padding=12, bgcolor=PANEL, border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)))
        transport = self.transport_bar()
        self.main_area = ft.Row([ft.Container(ft.Column([transport, self.timeline], expand=True), expand=2), self.inspector], expand=True, spacing=10)
        root = ft.Container(ft.Column([header, self.main_area, self.notice], expand=True, spacing=8), padding=8, expand=True)
        self.workspace = root
        p.add(ft.SafeArea(ft.Container(root, bgcolor=BG, expand=True), expand=True))
        self.refresh()

    def transport_bar(self):
        return ft.Container(ft.Column([
            ft.Row([button("▶ Play", self.play), button("⏸ Pause", self.pause), button("■ Stop", self.stop),
                    ft.VerticalDivider(width=8), button("|← In", self.set_in), button("Out →|", self.set_out),
                    button("|▶| Range", self.play_range), button("↔ Syl", self.range_from_selected), button("× Clear", self.clear_range), self.range_label], wrap=True),
            ft.Row([ft.Text("Скорость", color=MUTED), *[button(f"{x:g}×", self.set_speed) for x in (.5, .75, 1, 1.25, 1.5)],
                    ft.Text("Слой", color=MUTED), *[button(x, self.set_layer) for x in ("Волна", "Спектр", "Оба")], self.cursor_label], wrap=True)
        ], spacing=7), bgcolor=PANEL, padding=10, border=ft.Border.all(1, BORDER), border_radius=10)

    def refresh(self):
        self.workspace.scale = self.dpi
        self.workspace.alignment = ft.Alignment.CENTER if self.aspect != "Полный экран" else ft.Alignment.TOP_LEFT
        self.workspace.aspect_ratio = {"20:9": 20 / 9, "19.5:9": 19.5 / 9, "18:9": 2, "16:9": 16 / 9, "4:3": 4 / 3}.get(self.aspect)
        self.refresh_timeline()
        self.refresh_inspector()
        self.status.value = f"ASS: {self.ass_path.name}" if self.ass_path else "ASS не загружен"
        syllables = self.syllables()
        bursts = sum(s.burst_marked for s in syllables)
        self.count.value = f"{len(syllables)} слогов" + (f" · 🔥 {bursts}" if bursts else "")
        self.range_label.value = f"Диапазон: {format_ass_time(self.in_point) if self.in_point is not None else '—'} .. {format_ass_time(self.out_point) if self.out_point is not None else '—'}"
        self.cursor_label.value = f"Курсор {format_ass_time(self.cursor)}"
        self.page.update()

    def syllables(self) -> list[KaraokeSyllable]:
        return self.doc.karaoke_syllables() if self.doc else []

    def refresh_timeline(self):
        items = self.syllables()
        if not items:
            self.timeline.content = ft.Container(ft.Column([ft.Text("OVERVIEW", color=MUTED), ft.Text("DETAIL", color=MUTED), ft.Text("Выберите ASS для отображения слогов", color=MUTED)], spacing=18), bgcolor=PANEL, padding=16, border_radius=10, expand=True)
            return
        end = max(s.end for s in items) or 1
        overview = ft.Row([self.syllable_block(s, end, compact=True) for s in items], spacing=2, scroll=ft.ScrollMode.AUTO, height=42)
        detail = ft.Row([self.syllable_block(s, end) for s in items], spacing=5, scroll=ft.ScrollMode.AUTO, expand=True)
        self.timeline.content = ft.Container(ft.Column([ft.Text("OVERVIEW · вся песня", color=MUTED, size=11), overview,
            ft.Divider(color=BORDER), ft.Row([ft.Text(f"DETAIL · {self.audio_layer}", color=MUTED, size=11), self.zoom], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(detail, bgcolor="#0f1722", padding=12, expand=True)], expand=True), bgcolor=PANEL, padding=10, border_radius=10, border=ft.Border.all(1, BORDER), expand=True)

    def syllable_block(self, s: KaraokeSyllable, total: float, compact=False):
        width = max(28 if compact else 72, (s.end - s.start) * (55 if compact else 125) * float(self.zoom.value or 1))
        selected = s.id in self.selected
        color = DANGER if s.burst_marked else ("#245a61" if selected else PANEL_2)
        label = "" if compact else (s.visible_text or "·")
        block = ft.Container(ft.Text(label, color=TEXT, size=11, text_align=ft.TextAlign.CENTER), width=width, height=25 if compact else 90,
                             bgcolor=color, border=ft.Border.all(2 if selected else 1, ACCENT if selected else BORDER), border_radius=5,
                             alignment=ft.Alignment.CENTER, data=s.id, tooltip=f"{s.visible_text} · {format_ass_time(s.start)}")
        return ft.GestureDetector(content=block, on_tap=lambda e, sid=s.id: self.select_syllable(sid),
                                  on_double_tap=lambda e, sid=s.id: self.listen_syllable(sid))

    def refresh_inspector(self):
        s = self.selected_item()
        if not s:
            self.text_field.value = ""; self.roman_field.value = ""
            self.inspector.content = card("СЛОГ / ДЕЙСТВИЯ", [ft.Text("Выберите блок на таймлайне", color=MUTED), self.text_field, self.roman_field], expand=True)
            return
        self.text_field.value = s.raw_text
        self.roman_field.value = s.romanization
        title = f"Слог {s.id} · {format_ass_time(s.start)} – {format_ass_time(s.end)} ({s.duration_cs * 10} мс)"
        actions = [ft.Row([button("▶ Слог", lambda e: self.listen_syllable(s.id)), button("←", self.previous), button("→", self.next)], wrap=True),
            self.text_field, self.roman_field, ft.Row([button("✂ Разрезать по курсору", self.split_at_cursor), button("[Непроизнесённое]", self.toggle_unspoken)], wrap=True)]
        timing = [ft.Row([button("➕ Вставить после", self.insert), button("✂ Разделить 50/50", self.split_half), button("🔗 Объединить", self.merge), button("🗑 Удалить", self.delete)], wrap=True),
            ft.Row([self.tag_dropdown, button("Применить тег", self.apply_tag)]), ft.Row([button("↶ Undo", self.undo), button("↷ Redo", self.redo), button("🔥 Burst", self.burst), button("Снять Burst", self.unburst)], wrap=True),
            ft.Text(f"Burst: {'ДА' if s.burst_marked else 'НЕТ'}", color=DANGER if s.burst_marked else MUTED), button("📑 Все строки песни", self.show_lines)]
        self.inspector.content = ft.Column([card(title, actions), card("ТАЙМИНГ / ТЕГИ / ИСТОРИЯ", timing)], scroll=ft.ScrollMode.AUTO, expand=True)

    def selected_item(self):
        items = self.syllables(); return next((s for s in items if s.id == self.selected[0]), None) if self.selected else None

    def select_syllable(self, sid):
        self.selected = [sid]
        s = self.selected_item()
        if s:
            self.cursor = s.start
        self.refresh()

    def selected_ids(self): return self.selected
    def mutate(self, fn: Callable):
        if not self.doc or not self.selected: return
        before = self.doc.dumps()
        try:
            result = fn()
            self.undo_stack.append(before); self.redo_stack.clear()
            if getattr(result, "selected_ids", None): self.selected = list(result.selected_ids)
            else: self.selected = [s.id for s in self.syllables() if s.id in self.selected][:1]
            self.notice.value = "Готово"
        except Exception as exc: self.notice.value = f"Ошибка: {exc}"
        self.refresh()

    def split_half(self, e): self.mutate(lambda: split_syllable(self.doc, self.selected[0]))
    def split_at_cursor(self, e): self.mutate(lambda: split_syllable_at_time(self.doc, self.selected[0], self.cursor))
    def insert(self, e): self.mutate(lambda: insert_after(self.doc, self.selected[0]))
    def delete(self, e): self.mutate(lambda: delete_syllable(self.doc, self.selected[0]))
    def merge(self, e): self.mutate(lambda: merge_syllables(self.doc, self.selected))
    def apply_tag(self, e): self.mutate(lambda: set_tag_type(self.doc, self.selected, self.tag_dropdown.value))
    def burst(self, e): self.mutate(lambda: colour_burst(self.doc, self.selected))
    def unburst(self, e): self.mutate(lambda: uncolour_burst(self.doc, self.selected))
    def text_changed(self, e):
        if self.doc and self.selected and e.control.value != self.selected_item().raw_text: self.mutate(lambda: set_syllable_text(self.doc, self.selected[0], e.control.value))
    def roman_changed(self, e):
        if self.doc and self.selected: self.mutate(lambda: set_syllable_romanization(self.doc, self.selected[0], e.control.value))
    def toggle_unspoken(self, e):
        s = self.selected_item();
        if s: self.text_field.value = s.visible_text.strip("[]") if s.visible_text.startswith("[") else f"[{s.visible_text}]"; self.text_changed(type("E", (), {"control": self.text_field})())

    def previous(self, e): self.move_selection(-1)
    def next(self, e): self.move_selection(1)
    def move_selection(self, delta):
        items = self.syllables(); i = next((i for i, s in enumerate(items) if s.id in self.selected), 0); i = max(0, min(len(items)-1, i+delta)); self.select_syllable(items[i].id) if items else None
    def listen_syllable(self, sid): self.cursor = next((s.start for s in self.syllables() if s.id == sid), self.cursor); self.notice.value = "▶ Прослушивание слога (подключите аудиоплеер для вывода)"; self.refresh()
    def play(self, e): self.playing = True; self.notice.value = "▶ Воспроизведение"; self.refresh()
    def pause(self, e): self.playing = False; self.notice.value = "⏸ Пауза"; self.refresh()
    def stop(self, e): self.playing = False; self.cursor = self.in_point or 0; self.refresh()
    def play_range(self, e): self.cursor = self.in_point or 0; self.playing = True; self.notice.value = "▶ Диапазон In/Out"; self.refresh()
    def set_in(self, e): self.in_point = self.cursor; self.refresh()
    def set_out(self, e): self.out_point = self.cursor; self.refresh()
    def clear_range(self, e): self.in_point = self.out_point = None; self.refresh()
    def range_from_selected(self, e):
        s = self.selected_item()
        if s: self.in_point, self.out_point = s.start, s.end; self.refresh()
    def set_speed(self, e): self.speed = float(e.control.text.rstrip("×")); self.notice.value = f"Скорость {self.speed:g}×"; self.refresh()
    def set_layer(self, e): self.audio_layer = e.control.text; self.refresh()

    def file_result(self, e):
        if not e.files: return
        path = Path(e.files[0].path)
        try:
            if self.file_picker.data == "ass": self.doc, self.ass_path = AssDocument.load(path), path
            elif self.file_picker.data == "media": self.media_path = path; self.waveform = load_or_extract_waveform(path)
            else: self.notice.value = f"Проект: {path.name} (bundle готов к подключению)"
            self.refresh()
        except Exception as exc: self.notice.value = f"Не удалось открыть {path.name}: {exc}"; self.refresh()
    async def choose(self, kind, exts):
        self.file_picker.data = kind
        await self.file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=exts)
    async def open_ass(self, e): await self.choose("ass", ["ass"])
    async def open_media(self, e): await self.choose("media", ["wav", "mp3", "ogg", "flac", "m4a"])
    async def open_project(self, e): await self.choose("project", ["karaoke"])
    def save_ass(self, e):
        try: self.doc.save(self.ass_path) if self.doc and self.ass_path else None; self.notice.value = "ASS сохранён"; self.refresh()
        except Exception as exc: self.notice.value = f"Ошибка сохранения: {exc}"; self.refresh()
    def undo(self, e):
        if self.doc and self.undo_stack:
            self.redo_stack.append(self.doc.dumps()); self.doc = AssDocument.from_text(self.undo_stack.pop()); self.refresh()
    def redo(self, e):
        if self.doc and self.redo_stack:
            self.undo_stack.append(self.doc.dumps()); self.doc = AssDocument.from_text(self.redo_stack.pop()); self.refresh()
    def show_lines(self, e): self.open_drawer("Все строки песни", "\n".join(f"{i+1}. {s.visible_text}" for i, s in enumerate(self.syllables())) or "Нет строк")
    def open_settings(self, e):
        aspect = ft.Dropdown(label="Letterboxing", value=self.aspect, options=[ft.DropdownOption(x) for x in ("Полный экран", "20:9", "19.5:9", "18:9", "16:9", "4:3")], on_select=lambda ev: (setattr(self, "aspect", ev.control.value), self.refresh()))
        dpi = ft.Dropdown(label="DPI интерфейса", value=f"{int(self.dpi * 100)}%", options=[ft.DropdownOption(f"{x}%") for x in (70,80,90,100,115,130)], on_select=lambda ev: (setattr(self, "dpi", int(ev.control.value.rstrip("%"))/100), self.refresh()))
        self.page.show_dialog(ft.AlertDialog(title=ft.Text("Настройки экрана"), content=ft.Column([ft.Text("Эмуляция соотношения сторон — рабочая область центрируется с рамками"), aspect, dpi]), actions=[button("Готово", lambda e: self.close_dialog())]))
    def close_dialog(self): self.page.pop_dialog(); self.page.update()
    def open_drawer(self, title, text): self.page.show_dialog(ft.AlertDialog(title=ft.Text(title), content=ft.Container(ft.Text(text, color=MUTED), width=400), actions=[button("Закрыть", lambda e: self.close_dialog())]))


def main(page: ft.Page): Workbench(page)

if __name__ == "__main__": ft.run(main)
