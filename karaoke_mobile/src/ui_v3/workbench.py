from __future__ import annotations

import base64
from pathlib import Path
from typing import Callable

import flet as ft

from core.ass import AssDocument, KaraokeSyllable, format_ass_time
from core.editor import (
    colour_burst, delete_syllable, insert_after, merge_syllables,
    set_syllable_romanization, set_syllable_text, set_tag_type,
    split_syllable, split_syllable_at_time, uncolour_burst,
)
from core.media import WaveformData
from ui.components.audio_timeline import AudioTimelineWidget
from ui.components.audio_timeline import load_waveform_from_wav_bytes
from core.sps import MeasurementTimeline


class Workbench(ft.Container):
    """Independent touch UI; only the media service is shared for robust playback."""
    def __init__(self, on_document_changed: Callable[[AssDocument], None] | None = None,
                 on_audio_loaded: Callable | None = None, **_):
        super().__init__(expand=True, padding=8)
        self.document: AssDocument | None = None
        self.selected_id: str | None = None
        self.undo_stack: list[str] = []; self.redo_stack: list[str] = []
        self.on_document_changed = on_document_changed; self.on_audio_loaded_cb = on_audio_loaded
        self.ass_picker = ft.FilePicker(on_result=self._load_ass)
        self.audio = AudioTimelineWidget(on_audio_loaded=self._audio_loaded, on_syllable_clicked=self._select)
        # Compatibility with the coordinator in main.py; this is the V3 transport.
        self.audio_timeline = self.audio
        self.mode = "syllable"
        self._build()

    def set_page(self, page): self.audio._page = page
    def get_services(self): return [self.ass_picker, *self.audio.get_services()]
    def apply_theme(self, _): self._build(); self.refresh()

    @property
    def syllables(self) -> list[KaraokeSyllable]: return list(self.document.karaoke_syllables()) if self.document else []
    @property
    def selected(self): return next((s for s in self.syllables if s.id == self.selected_id), None)

    def set_document(self, doc, _timeline=None): self.document = doc; self.refresh()
    def load_ass_text(self, text): self.document=AssDocument.from_text(text); self.selected_id=None; self.undo_stack.clear(); self.redo_stack.clear(); self.refresh()

    def _show_notice(self, text):
        if self.page:
            self.page.snack_bar=ft.SnackBar(ft.Text(text)); self.page.snack_bar.open=True; self.page.update()
    def _mutate(self, fn):
        if not self.document: return
        self.undo_stack.append(self.document.dumps()); self.redo_stack.clear()
        try: fn()
        except Exception as ex: self.undo_stack.pop(); self._show_notice(f"Ошибка: {ex}")
        else:
            if self.on_document_changed: self.on_document_changed(self.document)
            self.refresh()
    def undo(self, _=None):
        if self.undo_stack:
            self.redo_stack.append(self.document.dumps()); self.document=AssDocument.from_text(self.undo_stack.pop()); self.refresh()
    def redo(self, _=None):
        if self.redo_stack:
            self.undo_stack.append(self.document.dumps()); self.document=AssDocument.from_text(self.redo_stack.pop()); self.refresh()
    def _select(self, sid): self.selected_id=sid; self.refresh()
    def _audio_loaded(self, name, data, waveform, spectrogram):
        if self.on_audio_loaded_cb: self.on_audio_loaded_cb(name, data, waveform, spectrogram)

    def _load_ass(self, e):
        if e.files and e.files[0].path:
            self.load_ass_text(Path(e.files[0].path).read_text(encoding="utf-8-sig"))

    def _timeline_data(self):
        return MeasurementTimeline.from_karaoke(self.syllables).syllables if self.document else []

    def _build(self):
        p="#0b1020"; panel="#121a2d"; accent="#4fd1c5"; muted="#94a3b8"
        self.title=ft.Text("KARAOKE / WORKBENCH", weight=ft.FontWeight.BOLD, size=16, color="#f8fafc")
        self.meta=ft.Text("ASS не загружен", size=11, color=muted)
        head=ft.Container(ft.Row([ft.Column([self.title,self.meta],spacing=1,tight=True),ft.Row([
            ft.IconButton(ft.Icons.UNDO,on_click=self.undo,tooltip="Undo"),ft.IconButton(ft.Icons.REDO,on_click=self.redo,tooltip="Redo"),
            ft.IconButton(ft.Icons.FOLDER_OPEN,action=ft.PickFiles(self.ass_picker,with_data=True),icon_color=accent,tooltip="Открыть ASS")],tight=True,spacing=0)],alignment=ft.MainAxisAlignment.SPACE_BETWEEN),bgcolor=panel,padding=10,border_radius=12)
        self.overview=ft.Row([],spacing=1,scroll=ft.ScrollMode.ALWAYS)
        self.detail=ft.Row([],spacing=3,scroll=ft.ScrollMode.ALWAYS)
        timeline=ft.Container(ft.Column([ft.Text("ОБЗОР ПЕСНИ",size=10,color=muted),self.overview,ft.Divider(height=1),ft.Text("СЛОГИ / ТАЙМИНГ",size=10,color=muted),self.detail],spacing=5),bgcolor=panel,padding=9,border_radius=12)
        self.inspector=ft.Column([],scroll=ft.ScrollMode.AUTO,expand=True)
        self.lines=ft.ListView(expand=True,spacing=6)
        tabs=ft.Row([self._tab("Слог", "syllable"),self._tab("Действия", "actions"),self._tab("Строки", "lines")],spacing=5)
        self.workspace=ft.Container(self.inspector,expand=True,bgcolor=panel,padding=10,border_radius=12)
        self.content=ft.Column([head,self.audio,timeline,tabs,self.workspace],expand=True,spacing=8)

    def _tab(self, label, value):
        active=self.mode==value
        return ft.FilledButton(label,on_click=lambda e,v=value:self._switch(v),expand=True,style=ft.ButtonStyle(bgcolor="#4fd1c5" if active else "#1e293b",color="#04111d" if active else "#e2e8f0"))
    def _switch(self, value): self.mode=value; self._build(); self.refresh()

    def refresh(self):
        if not hasattr(self,"inspector"): return
        syls=self.syllables; self.meta.value=f"{len(syls)} слогов · {'аудио готово' if self.audio.waveform else 'загрузите аудио'}"
        self.audio.set_syllables(self._timeline_data(),self.selected_id)
        self.overview.controls=[ft.Container(width=max(8,(s.end-s.start)*18),height=12,bgcolor="#ef4444" if s.burst_marked else "#4fd1c5" if s.id==self.selected_id else "#334155",border_radius=2) for s in syls]
        self.detail.controls=[ft.GestureDetector(content=ft.Container(ft.Text(s.visible_text or "·",size=13,color="#f8fafc"),width=max(48,(s.end-s.start)*90),height=58,padding=8,bgcolor="#dc2626" if s.burst_marked else "#2563eb" if s.id==self.selected_id else "#1e293b",border_radius=7),on_tap=lambda e,item=s:self._select(item.id),on_double_tap=lambda e,item=s:self.audio.play_range(item.start,item.end)) for s in syls]
        self.inspector.controls=[]
        if self.mode=="lines":
            self.inspector.controls=[ft.Text("Все строки",weight=ft.FontWeight.BOLD)]+[ft.OutlinedButton(f"{format_ass_time(s.start)}  {s.visible_text}",on_click=lambda e,item=s:self._select(item.id)) for s in syls]
        elif self.mode=="actions": self._actions()
        else: self._syllable()
        try: self.update()
        except Exception: pass

    def _syllable(self):
        s=self.selected
        if not s: self.inspector.controls=[ft.Text("Выберите слог на таймлайне",color="#94a3b8")]; return
        text=ft.TextField(label="Текст",value=s.visible_text,on_change=lambda e:self._mutate(lambda:set_syllable_text(self.document,s.id,e.control.value)))
        roma=ft.TextField(label="Romanization",value=s.romanization,on_change=lambda e:self._mutate(lambda:set_syllable_romanization(self.document,s.id,e.control.value)))
        self.inspector.controls=[ft.Text(f"Слог #{s.syllable_ordinal+1} · {s.duration_cs*10} мс",weight=ft.FontWeight.BOLD,size=16),ft.Text(f"{format_ass_time(s.start)} — {format_ass_time(s.end)}",color="#94a3b8"),ft.Row([ft.FilledButton("▶ Слог",on_click=lambda e:self.audio.play_range(s.start,s.end)),ft.IconButton(ft.Icons.ARROW_BACK),ft.IconButton(ft.Icons.ARROW_FORWARD)]),text,roma,ft.FilledButton("✂ Разделить по курсору",on_click=lambda e:self._mutate(lambda:split_syllable_at_time(self.document,s.id,self.audio.center_time))),ft.OutlinedButton("🔥 Burst" if not s.burst_marked else "Снять Burst",on_click=lambda e:self._mutate(lambda: colour_burst(self.document,[s.id]) if not s.burst_marked else uncolour_burst(self.document,[s.id])))]
    def _actions(self):
        s=self.selected
        if not s: self.inspector.controls=[ft.Text("Выберите слог для действий",color="#94a3b8")]; return
        self.inspector.controls=[ft.Text("Тайминг и структура",weight=ft.FontWeight.BOLD,size=16),ft.FilledButton("➕ Вставить после",on_click=lambda e:self._mutate(lambda:insert_after(self.document,s.id))),ft.FilledButton("✂ Разделить 50/50",on_click=lambda e:self._mutate(lambda:split_syllable(self.document,s.id))),ft.FilledButton("🔗 Объединить со следующим",on_click=lambda e:self._merge_next(s)),ft.OutlinedButton("🗑 Удалить",on_click=lambda e:self._mutate(lambda:delete_syllable(self.document,s.id))),ft.Row([ft.OutlinedButton(tag,on_click=lambda e,t=tag:self._mutate(lambda:set_tag_type(self.document,[s.id],t))) for tag in ["k","kf","ko","K"]],wrap=True)]
    def _merge_next(self,s):
        all_s=self.syllables; idx=all_s.index(s)
        if idx+1<len(all_s): self._mutate(lambda:merge_syllables(self.document,[s.id,all_s[idx+1].id]))
