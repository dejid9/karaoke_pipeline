from .workbench import Workbench


class EditorView(Workbench):
    """Compatibility entry point for `main.py` and the new V3 Workbench UI."""

    @property
    def selected_syllable_id(self):
        return self.selected_id

    @selected_syllable_id.setter
    def selected_syllable_id(self, value):
        self.selected_id = value

    def _refresh_ui(self):
        self.refresh()
