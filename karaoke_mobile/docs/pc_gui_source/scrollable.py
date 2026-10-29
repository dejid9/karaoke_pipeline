from __future__ import annotations

import tkinter as tk
from tkinter import ttk


from typing import Any, Optional


class ScrollableFrame(ttk.Frame):
    """A vertical scrolling container using Tk Canvas + Scrollbar.

    Place child widgets inside ``scrollable_frame.content``.
    """

    def __init__(self, master, *args, **kwargs) -> None:
        super().__init__(master, *args, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)

        self.content_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    def _update_scrollregion(self) -> None:
        can_w = max(self.canvas.winfo_width(), 1)
        can_h = max(self.canvas.winfo_height(), 1)
        bbox = self.canvas.bbox(self.content_id)
        if bbox is None:
            bbox = self.canvas.bbox("all")
        if bbox:
            w = max(bbox[2], can_w)
            h = max(bbox[3], can_h)
            self.canvas.configure(scrollregion=(0, 0, w, h))
            if bbox[3] <= can_h:
                self.canvas.yview_moveto(0.0)
        else:
            self.canvas.configure(scrollregion=(0, 0, can_w, can_h))
            self.canvas.yview_moveto(0.0)

    def _on_content_configure(self, _event=None) -> None:
        self._update_scrollregion()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfig(self.content_id, width=event.width)
        self._update_scrollregion()

    def _on_enter(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_leave(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _find_inner_scrollable(self, widget: Any) -> Optional[Any]:
        curr = widget
        while curr is not None:
            if curr is self.canvas or curr is self.scrollbar or curr is self:
                return None
            if hasattr(curr, "yview") and hasattr(curr, "yview_scroll"):
                return curr
            curr = getattr(curr, "master", None)
        return None

    def _on_mousewheel(self, event) -> None:
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        units = int(-1 * (delta / 120))
        if not units:
            units = -1 if delta > 0 else 1

        inner = self._find_inner_scrollable(getattr(event, "widget", None))
        if inner is not None:
            try:
                top, bottom = inner.yview()
                # Scrolling up: inner can scroll if not at top edge
                if units < 0 and top > 1e-4:
                    if inner.winfo_class() not in ("Text", "Treeview"):
                        inner.yview_scroll(units, "units")
                    return
                # Scrolling down: inner can scroll if not at bottom edge
                if units > 0 and bottom < 1.0 - 1e-4:
                    if inner.winfo_class() not in ("Text", "Treeview"):
                        inner.yview_scroll(units, "units")
                    return
            except Exception:
                pass

        bbox = self.canvas.bbox(self.content_id) or self.canvas.bbox("all")
        can_h = self.canvas.winfo_height()
        if bbox and bbox[3] <= can_h:
            self.canvas.yview_moveto(0.0)
            return

        self.canvas.yview_scroll(units, "units")
        if self.canvas.canvasy(0) < 0:
            self.canvas.yview_moveto(0.0)
        elif bbox and self.canvas.canvasy(can_h) > bbox[3]:
            self.canvas.yview_moveto(1.0)

    def set_palette(self, palette) -> None:
        bg = getattr(palette, "bg", None)
        if bg:
            try:
                self.canvas.configure(background=bg)
            except tk.TclError:
                pass
