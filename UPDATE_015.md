# Update 015 — Simple/Advanced UI and themes

This update changes presentation only; SPS, ASS editing, MFA, render and media-processing algorithms are unchanged.

## Interface modes

The top toolbar now has an **Advanced** switch.

- **Simple** is the default for a fresh user profile.
- **Advanced** restores the detailed controls from the previous interface.
- Switching modes does not recreate the session, reload the ASS, clear selections, reset zoom, or discard measurement/render settings.

The main tabs now follow the typical workflow:

1. Подготовка
2. Караоке
3. Точный SPS
4. Рендер

Simple mode mainly hides fine-grained controls rather than functionality. For example, the default SPS graph remains visible but its metric/window/smoothing controls move behind Advanced; MFA keeps its main run path while Validate/OOV/model tools become Advanced; render keeps overlay/burn actions while low-level layout/codec tuning becomes Advanced.

## Theme engine

The visual system is intentionally between modern GNOME/Libadwaita colour hierarchy and classic Windows Forms density/geometry: flat rectangular controls, compact spacing, clear borders, neutral surfaces and a strong accent colour.

Available palettes, each with light and night variants:

- Тёмно-синяя
- Фиолетовая
- Красная
- Зелёная
- Жёлтая
- Вэйпорвэйв
- Каппучино

The theme affects ttk widgets, menus, text editors, timeline canvases, waveform colours, measurement handles, SPS plots, selections and crop preview. The automatic burst heat scale is not recoloured because it carries speed information.

## Preferences

Theme + Simple/Advanced choice are stored globally in:

`~/.karaoke_sps_workbench_ui.json`

The file is optional and safe to delete. Invalid/missing settings fall back to the dark-navy Simple interface.

## Verification

- 78/78 automated tests pass.
- Tkinter smoke test passed for all 14 themes.
- Simple → Advanced → Simple transitions were tested for the SPS graph, Alignment advanced blocks and Render advanced blocks.
- Theme switching while Simple mode is active does not accidentally re-show Advanced controls.
