from __future__ import annotations

import sys
from pathlib import Path
import flet as ft

# Ensure src/ is on sys.path regardless of execution context
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ui_v2.editor import EditorState
from ui_v2.timeline import Timeline

ASPECTS = {
    "Полный экран": None,
    "20:9": 20 / 9,
    "19.5:9": 19.5 / 9,
    "18:9": 2.0,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
}
SCALES = [0.70, 0.80, 0.90, 1.0, 1.15, 1.30]


def main(page: ft.Page):
    page.title = "Karaoke // SPS — Mobile Editor V2"
    page.bgcolor = "#000000"  # Black outer background for letterboxing
    page.padding = 0

    state = EditorState()
    current_scale = 1.0
    current_aspect: float | None = None
    timeline: Timeline | None = None

    status = ft.Text("ASS: demo.ass · 7 слогов", color="#94a3b8", size=12)
    selected_title = ft.Text("Слог не выбран", size=15, weight=ft.FontWeight.BOLD, color="#f8fafc")
    burst_badge = ft.Container(
        ft.Text("Burst: НЕТ", size=11, weight=ft.FontWeight.BOLD, color="#94a3b8"),
        bgcolor="#1e293b",
        padding=ft.Padding(left=8, right=8, top=3, bottom=3),
        border_radius=4,
    )

    text_field = ft.TextField(label="Текст слога", dense=True, text_size=13)
    roman_field = ft.TextField(label="Над слогом (романизация)", dense=True, text_size=13)
    tag_dropdown = ft.Dropdown(
        label="Тег",
        value="k",
        options=[ft.DropdownOption(x) for x in ["k", "kf", "ko", "K"]],
        width=110,
        dense=True,
    )

    def show_toast(msg: str):
        try:
            page.show_dialog(ft.SnackBar(ft.Text(msg)))
        except Exception:
            pass

    def refresh():
        selected = state.selected
        if selected:
            selected_title.value = (
                f"Слог #{selected.syllable_ordinal + 1} · {selected.start:.2f}–{selected.end:.2f} "
                f"({selected.duration_cs * 10} мс)"
            )
            text_field.value = selected.visible_text
            roman_field.value = selected.romanization or ""
            if selected.burst_marked:
                burst_badge.content.value = "Burst: ДА"
                burst_badge.content.color = "#fca5a5"
                burst_badge.bgcolor = "#7f1d1d"
            else:
                burst_badge.content.value = "Burst: НЕТ"
                burst_badge.content.color = "#94a3b8"
                burst_badge.bgcolor = "#1e293b"
        else:
            selected_title.value = "Слог не выбран"
            text_field.value = ""
            roman_field.value = ""
            burst_badge.content.value = "Burst: —"
            burst_badge.content.color = "#64748b"
            burst_badge.bgcolor = "#0f172a"

        in_str = f"{state.in_point:.2f}s" if state.in_point is not None else "--"
        out_str = f"{state.out_point:.2f}s" if state.out_point is not None else "--"
        status.value = (
            f"ASS: {len(state.syllables)} слогов | Курсор: {state.cursor:.2f}s | "
            f"Метки: [{in_str} .. {out_str}]"
        )
        if timeline:
            timeline.refresh()
        try:
            page.update()
        except RuntimeError:
            pass

    state.on_change = refresh

    def action(fn):
        def wrapped(e=None):
            fn()
            refresh()
        return wrapped

    def select_at(t: float):
        state.select_at(t)
        refresh()

    def play_at(t: float):
        state.cursor = t
        refresh()

    def set_in(e):
        state.in_point = state.cursor
        refresh()

    def set_out(e):
        state.out_point = state.cursor
        refresh()

    def clear_limits(e):
        state.in_point = state.out_point = None
        refresh()

    def range_from_selection(e):
        selected = state.selected
        if selected:
            state.in_point = selected.start
            state.out_point = selected.end
            refresh()

    def toggle_unspoken(e):
        selected = state.selected
        if not selected:
            return
        cur_text = selected.visible_text.strip()
        if cur_text.startswith("[") and cur_text.endswith("]"):
            new_text = cur_text[1:-1]
        else:
            new_text = f"[{cur_text}]"
        state.set_text(new_text)

    def load_ass(e):
        if e.files:
            try:
                with open(e.files[0].path, encoding="utf-8-sig") as f:
                    state.load_ass(f.read())
                show_toast(f"Загружен файл {Path(e.files[0].path).name}")
            except Exception as ex:
                show_toast(f"Ошибка загрузки: {ex}")
            refresh()

    def save_ass(e):
        show_toast("Документ ASS обновлен в памяти редактора")

    def show_all_lines(e):
        lines_list = ft.ListView(expand=True, spacing=4)
        for i, line in enumerate(state.document.events):
            if line.is_comment:
                continue
            lines_list.controls.append(
                ft.Container(
                    ft.Text(f"#{i + 1} [{line.start} - {line.end}]: {line.clean_text}", size=12),
                    padding=6,
                    bgcolor="#1e293b",
                    border_radius=4,
                    on_click=lambda ev, t=line.start_seconds: (select_at(t), page.pop_dialog()),
                )
            )

        dialog = ft.AlertDialog(
            title=ft.Text("Все строки песни", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(lines_list, width=360, height=300),
            actions=[ft.TextButton("Закрыть", on_click=lambda _: page.pop_dialog())],
        )
        page.show_dialog(dialog)

    picker = ft.FilePicker(on_result=load_ass)
    page.services.append(picker)

    file_row = ft.Row([
        ft.FilledButton(
            "ASS…",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=lambda e: picker.pick_files(allowed_extensions=["ass"]),
        ),
        ft.OutlinedButton("Сохранить ASS", icon=ft.Icons.SAVE, on_click=save_ass),
    ], wrap=True)

    transport = ft.Row([
        ft.IconButton(ft.Icons.PLAY_ARROW, tooltip="Play", on_click=lambda e: play_at(state.in_point or state.cursor)),
        ft.IconButton(ft.Icons.PAUSE, tooltip="Pause"),
        ft.IconButton(ft.Icons.STOP, tooltip="Stop", on_click=lambda e: play_at(state.in_point or 0)),
        ft.VerticalDivider(),
        ft.Text("Метки:", size=12, color="#94a3b8"),
        ft.IconButton(ft.Icons.VERTICAL_ALIGN_TOP, tooltip="Start In [|←]", on_click=set_in),
        ft.IconButton(ft.Icons.VERTICAL_ALIGN_BOTTOM, tooltip="Stop Out [→|]", on_click=set_out),
        ft.IconButton(ft.Icons.SPACE_BAR, tooltip="Диапазон по слогу [↔]", on_click=range_from_selection),
        ft.IconButton(ft.Icons.CLEAR, tooltip="Сброс меток [×]", on_click=clear_limits),
    ], wrap=True)

    speed_chips = []
    for x in [0.5, 0.75, 1.0, 1.25, 1.5]:
        def make_select(v):
            return lambda e: (setattr(state, "speed", v), update_speed_chips())
        chip = ft.Chip(
            label=ft.Text(f"{x}×", size=11),
            selected=(x == 1.0),
            on_select=make_select(x),
        )
        speed_chips.append((x, chip))

    def update_speed_chips():
        for val, chip in speed_chips:
            chip.selected = (val == state.speed)
        try:
            page.update()
        except RuntimeError:
            pass

    speed_row = ft.Row([
        ft.Text("Скорость:", size=12, color="#94a3b8"),
        *[chip for _, chip in speed_chips],
    ], wrap=True)

    timeline = Timeline(state, select_at, play_at)

    text_field.on_change = lambda e: state.set_text(e.control.value)
    roman_field.on_change = lambda e: state.set_romanization(e.control.value)

    selected_card = ft.Column([
        ft.Row([selected_title, burst_badge], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Row([
            ft.FilledButton("▶ Слог", on_click=lambda e: play_at(state.selected.start if state.selected else state.cursor)),
            ft.IconButton(
                ft.Icons.ARROW_BACK,
                tooltip="Предыдущий слог",
                on_click=lambda e: select_at(max(0.0, (state.selected.start if state.selected else 0.0) - 0.01)),
            ),
            ft.IconButton(
                ft.Icons.ARROW_FORWARD,
                tooltip="Следующий слог",
                on_click=lambda e: select_at((state.selected.end if state.selected else 0.0) + 0.01),
            ),
        ]),
        text_field,
        roman_field,
        ft.Row([
            ft.OutlinedButton("✂ Разрезать по курсору", on_click=action(state.split_at_cursor)),
            ft.OutlinedButton("[Непроизнесённое]", on_click=toggle_unspoken),
        ], wrap=True),
    ], tight=True)

    actions = ft.Column([
        ft.Row([
            ft.FilledButton("Вставить", on_click=action(state.insert)),
            ft.FilledButton("Разделить 50/50", on_click=action(state.split_half)),
            ft.FilledButton("Совместить", on_click=action(state.merge)),
            ft.FilledButton("Удалить", on_click=action(state.delete)),
        ], wrap=True),
        ft.Row([
            tag_dropdown,
            ft.OutlinedButton("Применить тег", on_click=lambda e: action(lambda: state.apply_tag(tag_dropdown.value))()),
            ft.IconButton(ft.Icons.UNDO, tooltip="Отмена", on_click=action(state.undo)),
            ft.IconButton(ft.Icons.REDO, tooltip="Повтор", on_click=action(state.redo)),
        ], wrap=True),
        ft.Row([
            ft.OutlinedButton("🔥 Burst", on_click=action(lambda: state.burst(True))),
            ft.OutlinedButton("Снять burst", on_click=action(lambda: state.burst(False))),
            ft.OutlinedButton("📑 Все строки", on_click=show_all_lines),
        ], wrap=True),
    ], tight=True)

    # Main content layout (landscape default with dock cards on the right)
    landscape_content = ft.Row([
        ft.Container(
            ft.Column([file_row, transport, speed_row, timeline], expand=True),
            expand=True,
        ),
        ft.Container(
            ft.Column([selected_card, ft.Divider(color="#334155"), actions], scroll=ft.ScrollMode.AUTO),
            width=360,
            bgcolor="#0b1329",
            padding=10,
            border_radius=8,
        ),
    ], expand=True)

    # Root workspace frame: letterboxing and DPI UI scaling
    inner_container = ft.Container(
        content=landscape_content,
        expand=True,
    )

    workspace_frame = ft.Container(
        content=ft.SafeArea(
            ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.MIC, color="#38bdf8", size=20),
                        ft.Text("KARAOKE // SPS", weight=ft.FontWeight.BOLD, color="#f8fafc"),
                    ], spacing=6),
                    status,
                    ft.IconButton(ft.Icons.TUNE, tooltip="Настройки экрана / DPI", on_click=lambda e: open_settings_dialog()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                inner_container,
            ], expand=True),
            expand=True,
        ),
        bgcolor="#020617",
        alignment=ft.Alignment.CENTER,
        aspect_ratio=current_aspect,
        scale=current_scale,
        expand=True if current_aspect is None else False,
    )

    letterbox_wrapper = ft.Container(
        content=workspace_frame,
        alignment=ft.Alignment.CENTER,
        bgcolor="#000000",
        expand=True,
    )

    def open_settings_dialog():
        nonlocal current_scale, current_aspect
        scale_dd = ft.Dropdown(
            label="UI Scale / DPI",
            value=f"{int(current_scale * 100)}%",
            options=[ft.DropdownOption(f"{int(x * 100)}%") for x in SCALES],
        )
        ratio_dd = ft.Dropdown(
            label="Эмуляция экрана (Letterbox)",
            value=next((k for k, v in ASPECTS.items() if v == current_aspect), "Полный экран"),
            options=[ft.DropdownOption(x) for x in ASPECTS],
        )

        def apply_settings(_):
            nonlocal current_scale, current_aspect
            current_scale = float(scale_dd.value.replace("%", "")) / 100.0
            current_aspect = ASPECTS[ratio_dd.value]

            # Apply aspect ratio constraint (creates letterbox bars)
            workspace_frame.aspect_ratio = current_aspect
            workspace_frame.expand = True if current_aspect is None else False
            # Apply DPI scaling
            workspace_frame.scale = current_scale

            page.pop_dialog()
            page.update()
            show_toast(f"Применено: {ratio_dd.value}, DPI: {int(current_scale * 100)}%")

        dialog = ft.AlertDialog(
            title=ft.Text("Настройки экрана и масштаба", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Text("Эмулируйте пропорции других телефонов через добавление рамок:", size=12, color="#94a3b8"),
                ratio_dd,
                ft.Text("Регулируйте масштаб элементов интерфейса (DPI):", size=12, color="#94a3b8"),
                scale_dd,
            ], tight=True),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton("Применить", on_click=apply_settings),
            ],
        )
        page.show_dialog(dialog)

    page.add(letterbox_wrapper)
    refresh()


if __name__ == "__main__":
    ft.app(target=main)
