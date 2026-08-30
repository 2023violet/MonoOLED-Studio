from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from editor_model import EditorSession
from evidence import frame_evidence
from exporter import ExportBlockedError, export_scene
from presets import clinical_states
from scene import LOGS_DIR, ROOT, load_scene
from session_log import SessionLogger
from validate import has_blockers


APP_TITLE = 'MonoOLED Studio · Legacy Tk Reference'
ZOOM_LEVELS = (4, 6, 8, 10, 12, 16)
RUN_SPEEDS = {'1×': 1000, '2×': 500, '5×': 200, '10×': 100}


class OLEDDesignerApp:
    def __init__(self, root: tk.Tk, scene_name: str = 'main_scene'):
        self.root = root
        self.scene = load_scene(scene_name)
        self.pending_logs: list[dict] = []
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = LOGS_DIR / f'gui_session_{stamp}.jsonl'
        self.logger = SessionLogger(self.log_path, callback=self._on_log)
        self.session = EditorSession(self.scene, logger=self.logger)

        self.selected_id: str | None = None
        self.drag_start: tuple[int, int] | None = None
        self.drag_origin: tuple[int, int] | None = None
        self.drag_has_command = False
        self.playing = False
        self.play_after_id: str | None = None
        self.asset_watch_after_id: str | None = None
        self.asset_mtimes: dict[Path, int] = {}
        self.last_used_files: tuple[Path, ...] = ()
        self.last_frame_signature: tuple | None = None
        self.geometry_cache: dict[str, tuple[int, int, int, int]] = {}

        self.zoom_var = tk.IntVar(value=int(self.scene.get('canvas', {}).get('preview_scale', 8)))
        if self.zoom_var.get() not in ZOOM_LEVELS:
            self.zoom_var.set(8)
        self.grid_var = tk.BooleanVar(value=True)
        self.bounds_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value='Ready')
        self.speed_var = tk.StringVar(value='1×')

        self.prop_vars = {name: tk.StringVar() for name in ('x', 'y', 'w', 'h')}
        self.prop_entries: dict[str, ttk.Entry] = {}
        self.state_vars: dict[str, tk.Variable] = {}
        self.state_widgets: dict[str, tk.Widget] = {}

        self._build_ui()
        self._bind_shortcuts()
        self._rebuild_element_list()
        if self.scene.get('elements'):
            self.select_element(self.scene['elements'][0]['id'])
        self.refresh_all()
        self._flush_pending_logs()
        self._schedule_asset_watch()

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry('1280x800')
        self.root.minsize(1024, 680)

        self._build_menu()
        self._build_toolbar()

        vertical = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        vertical.pack(fill=tk.BOTH, expand=True)

        body = ttk.Panedwindow(vertical, orient=tk.HORIZONTAL)
        vertical.add(body, weight=5)

        left = ttk.Frame(body, padding=6)
        center = ttk.Frame(body, padding=6)
        right = ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        body.add(center, weight=5)
        body.add(right, weight=2)

        self._build_element_panel(left)
        self._build_canvas_panel(center)
        self._build_right_panel(right)

        log_frame = ttk.LabelFrame(vertical, text='Session Log (JSONL evidence)', padding=4)
        vertical.add(log_frame, weight=1)
        self.log_text = tk.Text(log_frame, height=9, wrap='none', state='disabled', font=('Consolas', 9))
        log_y = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_y.set)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_y.grid(row=0, column=1, sticky='ns')
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        status = ttk.Frame(self.root, padding=(6, 2))
        status.pack(fill=tk.X)
        ttk.Label(status, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(status, text=f'Log: {self.log_path}').pack(side=tk.RIGHT)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label='Save Scene  Ctrl+S', command=self.save_scene)
        file_menu.add_separator()
        file_menu.add_command(label='Export Current Frame...', command=self.export_current)
        file_menu.add_command(label='Export 14 Clinical States...', command=self.export_all)
        file_menu.add_separator()
        file_menu.add_command(label='Exit', command=self.on_close)
        menu.add_cascade(label='File', menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label='Undo  Ctrl+Z', command=self.undo)
        edit_menu.add_command(label='Redo  Ctrl+Y', command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label='Add Placeholder...', command=self.add_placeholder)
        edit_menu.add_command(label='Assign Bitmap...', command=self.assign_bitmap)
        edit_menu.add_command(label='Delete Element  Del', command=self.remove_selected)
        menu.add_cascade(label='Edit', menu=edit_menu)

        run_menu = tk.Menu(menu, tearoff=False)
        run_menu.add_command(label='Play / Pause  Space', command=self.toggle_play)
        run_menu.add_command(label='Step +1s', command=self.step_runtime)
        run_menu.add_command(label='Reset Timeline', command=self.reset_runtime)
        run_menu.add_separator()
        run_menu.add_command(label='Validate', command=self.validate_now)
        menu.add_cascade(label='Run', menu=run_menu)
        self.root.configure(menu=menu)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=4)
        bar.pack(fill=tk.X)
        for text, command in (
            ('Save', self.save_scene), ('Undo', self.undo), ('Redo', self.redo),
            ('Validate', self.validate_now), ('Export 14', self.export_all),
        ):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self.play_button = ttk.Button(bar, text='▶ Play', command=self.toggle_play)
        self.play_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text='Step +1s', command=self.step_runtime).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text='Reset', command=self.reset_runtime).pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text='Speed').pack(side=tk.LEFT, padx=(8, 2))
        speed = ttk.Combobox(bar, textvariable=self.speed_var, values=list(RUN_SPEEDS), state='readonly', width=5)
        speed.pack(side=tk.LEFT)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(bar, text='Zoom').pack(side=tk.LEFT, padx=(2, 2))
        zoom = ttk.Combobox(bar, textvariable=self.zoom_var, values=ZOOM_LEVELS, state='readonly', width=4)
        zoom.pack(side=tk.LEFT)
        zoom.bind('<<ComboboxSelected>>', lambda _e: self.redraw_canvas())
        ttk.Checkbutton(bar, text='Grid', variable=self.grid_var, command=self.redraw_canvas).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(bar, text='Bounds', variable=self.bounds_var, command=self.redraw_canvas).pack(side=tk.LEFT, padx=4)

    def _build_element_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='Elements', font=('', 10, 'bold')).pack(anchor='w')
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 6))
        self.element_list = tk.Listbox(list_frame, exportselection=False, width=25)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.element_list.yview)
        self.element_list.configure(yscrollcommand=scroll.set)
        self.element_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.element_list.bind('<<ListboxSelect>>', self._on_list_select)

        ttk.Button(parent, text='+ Add Placeholder', command=self.add_placeholder).pack(fill=tk.X, pady=2)
        ttk.Button(parent, text='Assign Bitmap...', command=self.assign_bitmap).pack(fill=tk.X, pady=2)
        ttk.Button(parent, text='Delete Selected', command=self.remove_selected).pack(fill=tk.X, pady=2)

    def _build_canvas_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text='OLED Production Preview — 128×32 / 1-bit', font=('', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header, text='Yellow/gray boxes are editor overlays only').pack(side=tk.RIGHT)

        holder = ttk.Frame(parent)
        holder.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.canvas = tk.Canvas(holder, bg='black', highlightthickness=1, highlightbackground='#555555')
        xbar = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=self.canvas.xview)
        ybar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        ybar.grid(row=0, column=1, sticky='ns')
        xbar.grid(row=1, column=0, sticky='ew')
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.canvas.bind('<Button-1>', self._canvas_press)
        self.canvas.bind('<B1-Motion>', self._canvas_drag)
        self.canvas.bind('<ButtonRelease-1>', self._canvas_release)

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        props = ttk.LabelFrame(parent, text='Selected Element — X / Y / W / H', padding=6)
        props.pack(fill=tk.X)
        self.id_var = tk.StringVar(value='—')
        self.type_var = tk.StringVar(value='—')
        self.resource_var = tk.StringVar(value='—')
        ttk.Label(props, text='ID').grid(row=0, column=0, sticky='w')
        ttk.Label(props, textvariable=self.id_var).grid(row=0, column=1, columnspan=2, sticky='w')
        ttk.Label(props, text='Type').grid(row=1, column=0, sticky='w')
        ttk.Label(props, textvariable=self.type_var).grid(row=1, column=1, columnspan=2, sticky='w')

        for row, name in enumerate(('x', 'y', 'w', 'h'), start=2):
            ttk.Label(props, text=name.upper()).grid(row=row, column=0, sticky='w', pady=2)
            entry = ttk.Entry(props, textvariable=self.prop_vars[name], width=9)
            entry.grid(row=row, column=1, sticky='ew', pady=2)
            entry.bind('<Return>', lambda _e: self.apply_properties())
            self.prop_entries[name] = entry
        ttk.Button(props, text='Apply Geometry', command=self.apply_properties).grid(row=6, column=0, columnspan=2, sticky='ew', pady=(6, 2))
        ttk.Button(props, text='Assign / Replace Bitmap...', command=self.assign_bitmap).grid(row=7, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Label(props, text='Resource', font=('', 9, 'bold')).grid(row=8, column=0, sticky='nw', pady=(6, 0))
        ttk.Label(props, textvariable=self.resource_var, wraplength=260, justify='left').grid(row=9, column=0, columnspan=3, sticky='w')
        props.columnconfigure(1, weight=1)

        state_frame = ttk.LabelFrame(parent, text='Runtime UI State', padding=6)
        state_frame.pack(fill=tk.X, pady=(8, 0))
        for row, (name, spec) in enumerate(self.scene.get('states', {}).items()):
            ttk.Label(state_frame, text=name).grid(row=row, column=0, sticky='w', padx=(0, 6), pady=2)
            if spec.get('type') == 'enum':
                var = tk.StringVar(value=str(self.session.runtime.state[name]))
                widget = ttk.Combobox(state_frame, textvariable=var, values=spec.get('values', []), state='readonly', width=12)
                widget.bind('<<ComboboxSelected>>', lambda _e, n=name: self._apply_state(n))
            else:
                var = tk.IntVar(value=int(self.session.runtime.state[name]))
                widget = ttk.Spinbox(
                    state_frame, textvariable=var,
                    from_=int(spec.get('min', 0)), to=int(spec.get('max', 9999)), width=12,
                    command=lambda n=name: self._apply_state(n),
                )
                widget.bind('<Return>', lambda _e, n=name: self._apply_state(n))
                widget.bind('<FocusOut>', lambda _e, n=name: self._apply_state(n))
            widget.grid(row=row, column=1, sticky='ew', pady=2)
            self.state_vars[name] = var
            self.state_widgets[name] = widget
        state_frame.columnconfigure(1, weight=1)

        run = ttk.Frame(parent)
        run.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(run, text='▶ / ❚❚', command=self.toggle_play).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(run, text='+1s', command=self.step_runtime).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(run, text='Reset', command=self.reset_runtime).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        validation = ttk.LabelFrame(parent, text='Validation', padding=4)
        validation.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.validation_text = tk.Text(validation, height=10, wrap='word', state='disabled', font=('Consolas', 9))
        self.validation_text.pack(fill=tk.BOTH, expand=True)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all('<Control-s>', lambda _e: self.save_scene())
        self.root.bind_all('<Control-z>', lambda _e: self.undo())
        self.root.bind_all('<Control-y>', lambda _e: self.redo())
        self.root.bind_all('<Delete>', lambda _e: self.remove_selected())
        self.root.bind_all('<space>', self._space_toggle)
        for sequence, dx, dy in (
            ('<Left>', -1, 0), ('<Right>', 1, 0), ('<Up>', 0, -1), ('<Down>', 0, 1),
            ('<Shift-Left>', -10, 0), ('<Shift-Right>', 10, 0), ('<Shift-Up>', 0, -10), ('<Shift-Down>', 0, 10),
        ):
            self.root.bind_all(sequence, lambda _e, a=dx, b=dy: self.nudge_selected(a, b))

    # ---------- logging ----------
    def _on_log(self, record: dict) -> None:
        if not hasattr(self, 'log_text'):
            self.pending_logs.append(record)
            return
        text = json.dumps(record, ensure_ascii=False, sort_keys=True)
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, text + '\n')
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def _flush_pending_logs(self) -> None:
        pending = list(self.pending_logs)
        self.pending_logs.clear()
        for record in pending:
            self._on_log(record)

    # ---------- selection / properties ----------
    def _rebuild_element_list(self) -> None:
        previous = self.selected_id
        self.element_list.delete(0, tk.END)
        for item in self.scene.get('elements', []):
            suffix = ' [DRAFT]' if item.get('type') == 'placeholder' else ''
            self.element_list.insert(tk.END, f"{item.get('id', '?')}  ·  {item.get('type', '?')}{suffix}")
        if previous and any(e.get('id') == previous for e in self.scene.get('elements', [])):
            self.select_element(previous)

    def _on_list_select(self, _event=None) -> None:
        selection = self.element_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        elements = self.scene.get('elements', [])
        if 0 <= index < len(elements):
            self.select_element(elements[index]['id'], sync_list=False)

    def select_element(self, element_id: str | None, *, sync_list: bool = True) -> None:
        self.selected_id = element_id
        if element_id is None:
            self.id_var.set('—')
            self.type_var.set('—')
            self.resource_var.set('—')
            return
        try:
            element = self.session.document.element(element_id)
            geom = self.session.geometry(element_id)
        except Exception as exc:
            self.status_var.set(f'Selection error: {exc}')
            return

        self.id_var.set(element_id)
        self.type_var.set(str(element.get('type', '')))
        for name, value in zip(('x', 'y', 'w', 'h'), (geom.x, geom.y, geom.w, geom.h)):
            self.prop_vars[name].set(str(value))
            self.prop_entries[name].configure(state='normal' if geom.editable[name] else 'disabled')
        self.resource_var.set(self._resource_description(element))

        if sync_list:
            for index, item in enumerate(self.scene.get('elements', [])):
                if item.get('id') == element_id:
                    self.element_list.selection_clear(0, tk.END)
                    self.element_list.selection_set(index)
                    self.element_list.see(index)
                    break
        self.redraw_canvas()

    @staticmethod
    def _resource_description(element: dict) -> str:
        kind = element.get('type')
        if kind == 'image':
            return str(element.get('asset', ''))
        if kind in {'image_seq', 'digits'}:
            return f"{element.get('dir', '')}  /  {element.get('pattern', '')}"
        if kind == 'text':
            return f"text={element.get('text', '')}\nfont={element.get('font_header', '')}"
        if kind == 'placeholder':
            return f"Draft placeholder: {element.get('label', element.get('id'))}"
        return '—'

    def apply_properties(self) -> None:
        if not self.selected_id:
            return
        try:
            geom = self.session.geometry(self.selected_id)
            values = {}
            for name in ('x', 'y', 'w', 'h'):
                if geom.editable[name]:
                    values[name] = int(self.prop_vars[name].get())
            self.session.set_geometry(self.selected_id, **values)
            self.logger.log('PROPERTY_APPLY', element=self.selected_id, values=values)
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            messagebox.showerror('Geometry Error', str(exc), parent=self.root)

    def nudge_selected(self, dx: int, dy: int) -> str:
        if not self.selected_id:
            return 'break'
        # Do not hijack arrow keys while the user is typing in an Entry/Spinbox.
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, ttk.Spinbox)):
            return 'break'
        try:
            self.session.move(self.selected_id, dx=dx, dy=dy)
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            self.status_var.set(f'Move blocked: {exc}')
        return 'break'

    # ---------- canvas ----------
    def redraw_canvas(self) -> None:
        scale = max(1, int(self.zoom_var.get()))
        width = int(self.scene['canvas']['w'])
        height = int(self.scene['canvas']['h'])
        self.canvas.delete('all')
        self.canvas.configure(scrollregion=(0, 0, width * scale, height * scale))
        self.geometry_cache.clear()

        if self.grid_var.get() and scale >= 6:
            for x in range(width + 1):
                shade = '#303030' if x % 8 == 0 else '#171717'
                self.canvas.create_line(x * scale, 0, x * scale, height * scale, fill=shade)
            for y in range(height + 1):
                shade = '#303030' if y % 8 == 0 else '#171717'
                self.canvas.create_line(0, y * scale, width * scale, y * scale, fill=shade)

        result = None
        try:
            result = self.session.render()
            for y, row in enumerate(result.framebuffer.to_rows()):
                for x, lit in enumerate(row):
                    if lit:
                        self.canvas.create_rectangle(
                            x * scale, y * scale, (x + 1) * scale, (y + 1) * scale,
                            fill='white', outline='',
                        )
            self.last_used_files = result.used_files
            evidence = frame_evidence(result, self.session.runtime.state, elapsed=self.session.runtime.elapsed)
            signature = (evidence['sha256'], tuple(sorted(evidence['state'].items())))
            if signature != self.last_frame_signature:
                self.logger.log('FRAME', **evidence)
                self.last_frame_signature = signature
        except Exception as exc:
            self.status_var.set(f'Render error: {exc}')
            self.logger.log('RENDER_ERROR', error=str(exc))

        for element in self.scene.get('elements', []):
            eid = element.get('id')
            try:
                geom = self.session.geometry(eid)
            except Exception:
                zone = element.get('zone', {})
                x = element.get('x', zone.get('x', 0))
                y = element.get('y', zone.get('y', 0))
                w = element.get('w', zone.get('w', 1))
                h = element.get('h', zone.get('h', 1))
                try:
                    geom_tuple = (int(x), int(y), int(w), int(h))
                except Exception:
                    continue
            else:
                geom_tuple = (geom.x, geom.y, geom.w, geom.h)
            self.geometry_cache[eid] = geom_tuple
            x, y, w, h = geom_tuple

            if element.get('type') == 'placeholder':
                self.canvas.create_rectangle(
                    x * scale, y * scale, (x + w) * scale, (y + h) * scale,
                    outline='#ff9f1a', width=2, dash=(5, 3), tags=('overlay',),
                )
                self.canvas.create_text(
                    (x + w / 2) * scale, (y + h / 2) * scale,
                    text=element.get('label', eid), fill='#ff9f1a', font=('TkDefaultFont', max(8, scale)), tags=('overlay',),
                )
            elif self.bounds_var.get():
                self.canvas.create_rectangle(
                    x * scale, y * scale, (x + w) * scale, (y + h) * scale,
                    outline='#666666', width=1, dash=(3, 3), tags=('overlay',),
                )

        if self.selected_id in self.geometry_cache:
            x, y, w, h = self.geometry_cache[self.selected_id]
            self.canvas.create_rectangle(
                x * scale, y * scale, (x + w) * scale, (y + h) * scale,
                outline='#ffd400', width=2, tags=('selection',),
            )

    def _event_pixel(self, event) -> tuple[int, int]:
        scale = int(self.zoom_var.get())
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        return int(cx // scale), int(cy // scale)

    def _hit_test(self, px: int, py: int) -> str | None:
        for element in reversed(self.scene.get('elements', [])):
            eid = element.get('id')
            box = self.geometry_cache.get(eid)
            if not box:
                continue
            x, y, w, h = box
            if x <= px < x + w and y <= py < y + h:
                return eid
        return None

    def _canvas_press(self, event) -> None:
        px, py = self._event_pixel(event)
        hit = self._hit_test(px, py)
        if hit:
            self.select_element(hit)
            geom = self.session.geometry(hit)
            self.drag_start = (px, py)
            self.drag_origin = (geom.x, geom.y)
            self.drag_has_command = False
        else:
            self.drag_start = None
            self.drag_origin = None

    def _canvas_drag(self, event) -> None:
        if not self.selected_id or self.drag_start is None or self.drag_origin is None:
            return
        px, py = self._event_pixel(event)
        dx = px - self.drag_start[0]
        dy = py - self.drag_start[1]
        target_x = self.drag_origin[0] + dx
        target_y = self.drag_origin[1] + dy
        try:
            current = self.session.geometry(self.selected_id)
            if (current.x, current.y) == (target_x, target_y):
                return
            self.session.set_geometry(
                self.selected_id, x=target_x, y=target_y,
                coalesce=self.drag_has_command,
            )
            self.drag_has_command = True
            self._sync_property_panel()
            self.redraw_canvas()
            self._update_validation_panel()
            self._update_title()
        except Exception as exc:
            self.status_var.set(f'Drag blocked: {exc}')

    def _canvas_release(self, _event) -> None:
        self.drag_start = None
        self.drag_origin = None
        self.drag_has_command = False

    # ---------- state / runtime ----------
    def _apply_state(self, name: str) -> None:
        try:
            value = self.state_vars[name].get()
            self.session.set_state(name, value)
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            self.status_var.set(f'State error: {exc}')

    def _sync_state_controls(self) -> None:
        for name, value in self.session.runtime.state.items():
            var = self.state_vars.get(name)
            if var is not None:
                try:
                    var.set(value)
                except tk.TclError:
                    var.set(str(value))

    def step_runtime(self) -> None:
        try:
            self.session.step(1)
            self.logger.log('FRAME_STEP', elapsed=self.session.runtime.elapsed, state=dict(self.session.runtime.state))
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            messagebox.showerror('Runtime Error', str(exc), parent=self.root)

    def reset_runtime(self) -> None:
        self.session.reset()
        self.refresh_all(keep_selection=True)

    def toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_button.configure(text='❚❚ Pause' if self.playing else '▶ Play')
        self.logger.log('PLAY' if self.playing else 'PAUSE', elapsed=self.session.runtime.elapsed)
        if self.playing:
            self._schedule_play_tick(immediate=False)
        elif self.play_after_id:
            self.root.after_cancel(self.play_after_id)
            self.play_after_id = None

    def _space_toggle(self, _event=None) -> str:
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, ttk.Spinbox)):
            return 'break'
        self.toggle_play()
        return 'break'

    def _schedule_play_tick(self, *, immediate: bool) -> None:
        if not self.playing:
            return
        delay = 0 if immediate else RUN_SPEEDS.get(self.speed_var.get(), 1000)
        self.play_after_id = self.root.after(delay, self._play_tick)

    def _play_tick(self) -> None:
        self.play_after_id = None
        if not self.playing:
            return
        self.step_runtime()
        self._schedule_play_tick(immediate=False)

    # ---------- element structure ----------
    def add_placeholder(self) -> None:
        element_id = simpledialog.askstring('Add Placeholder', 'Element ID (unique):', parent=self.root)
        if not element_id:
            return
        try:
            self.session.add_placeholder(element_id.strip(), x=8, y=8, w=16, h=8, label=element_id.strip())
            self._rebuild_element_list()
            self.select_element(element_id.strip())
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            messagebox.showerror('Add Placeholder', str(exc), parent=self.root)

    def assign_bitmap(self) -> None:
        if not self.selected_id:
            messagebox.showinfo('Assign Bitmap', 'Select a placeholder or image first.', parent=self.root)
            return
        element = self.session.document.element(self.selected_id)
        if element.get('type') not in {'placeholder', 'image'}:
            messagebox.showinfo('Assign Bitmap', 'Only placeholder/image elements accept direct bitmap assignment.', parent=self.root)
            return
        if element.get('type') == 'image' and '{' in str(element.get('asset', '')):
            if not messagebox.askyesno(
                'Replace Dynamic Asset',
                'This image uses a state template. Replacing it will make this element use one fixed bitmap. Continue?',
                parent=self.root,
            ):
                return
        path = filedialog.askopenfilename(
            parent=self.root, title='Select 1-bit bitmap asset',
            filetypes=[('Image files', '*.png *.bmp'), ('PNG', '*.png'), ('BMP', '*.bmp'), ('All files', '*.*')],
        )
        if not path:
            return
        try:
            self.session.assign_bitmap(self.selected_id, path)
            self._rebuild_element_list()
            self.select_element(self.selected_id)
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            messagebox.showerror('Asset Error', str(exc), parent=self.root)

    def remove_selected(self) -> str:
        if not self.selected_id:
            return 'break'
        element_id = self.selected_id
        if not messagebox.askyesno('Delete Element', f'Delete {element_id}?\nThis can be undone with Ctrl+Z.', parent=self.root):
            return 'break'
        try:
            self.session.remove_element(element_id)
            self.selected_id = None
            self._rebuild_element_list()
            if self.scene.get('elements'):
                self.select_element(self.scene['elements'][0]['id'])
            self.refresh_all(keep_selection=True)
        except Exception as exc:
            messagebox.showerror('Delete Element', str(exc), parent=self.root)
        return 'break'

    # ---------- validate / save / export ----------
    def _update_validation_panel(self):
        findings = self.session.validate()
        blockers = [f for f in findings if f.severity in {'ERROR', 'BLOCKER'}]
        lines = []
        if not findings:
            lines.append('PASS — 0 findings')
        else:
            lines.append(f'{len(blockers)} blocking / {len(findings)} total')
            for f in findings:
                suffix = f' [{f.element_id}]' if f.element_id else ''
                lines.append(f'{f.severity} {f.code}{suffix}: {f.message}')
        self.validation_text.configure(state='normal')
        self.validation_text.delete('1.0', tk.END)
        self.validation_text.insert('1.0', '\n'.join(lines))
        self.validation_text.configure(state='disabled')
        if blockers:
            self.status_var.set(f'Validation FAIL — {len(blockers)} blocking finding(s)')
        else:
            self.status_var.set(f'Validation PASS — {len(findings)} finding(s)')
        return findings

    def validate_now(self) -> None:
        findings = self._update_validation_panel()
        self.logger.log(
            'VALIDATE', total=len(findings),
            blocking=sum(1 for f in findings if f.severity in {'ERROR', 'BLOCKER'}),
        )

    def save_scene(self) -> None:
        try:
            path = self.session.save()
            self.logger.write_markdown(self.log_path.with_suffix('.md'))
            self.status_var.set(f'Saved: {path}')
            self._update_title()
        except Exception as exc:
            messagebox.showerror('Save Error', str(exc), parent=self.root)

    def export_current(self) -> None:
        state = dict(self.session.runtime.state)
        name = f"{state.get('mode','state').lower()}_{state.get('phase','frame')}_t{self.session.runtime.elapsed:04d}"
        target = filedialog.askdirectory(parent=self.root, title='Choose export directory')
        if not target:
            return
        output = Path(target) / name
        self._run_export(output, {name: state})

    def export_all(self) -> None:
        target = filedialog.askdirectory(parent=self.root, title='Choose directory for 14-state export')
        if not target:
            return
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = Path(target) / f'clinical_14_{stamp}'
        states = clinical_states(
            self.scene,
            seconds=int(self.session.runtime.state.get('seconds', 10)),
            battery=int(self.session.runtime.state.get('battery', 4)),
        )
        self._run_export(output, states)

    def _run_export(self, output: Path, states: dict[str, dict]) -> None:
        try:
            summary = export_scene(self.scene, output, states)
        except ExportBlockedError as exc:
            self.logger.log('EXPORT_BLOCKED', output=str(output), error=str(exc))
            messagebox.showerror('Export Blocked', str(exc), parent=self.root)
            self._update_validation_panel()
            return
        except Exception as exc:
            self.logger.log('EXPORT_ERROR', output=str(output), error=str(exc))
            messagebox.showerror('Export Error', str(exc), parent=self.root)
            return
        self.logger.log('EXPORT', output=str(summary.output_dir), frames=summary.frame_count, hashes=summary.frame_hashes)
        messagebox.showinfo('Export Complete', f'{summary.frame_count} frame(s) exported to:\n{summary.output_dir}', parent=self.root)
        self.status_var.set(f'Exported {summary.frame_count} frame(s): {summary.output_dir}')

    # ---------- undo / redo ----------
    def undo(self) -> None:
        if self.session.undo():
            self._rebuild_element_list()
            if self.selected_id and not any(e.get('id') == self.selected_id for e in self.scene.get('elements', [])):
                self.selected_id = None
            if self.selected_id is None and self.scene.get('elements'):
                self.selected_id = self.scene['elements'][0]['id']
            self.refresh_all(keep_selection=True)

    def redo(self) -> None:
        if self.session.redo():
            self._rebuild_element_list()
            if self.selected_id is None and self.scene.get('elements'):
                self.selected_id = self.scene['elements'][0]['id']
            self.refresh_all(keep_selection=True)

    # ---------- live asset watch ----------
    def _schedule_asset_watch(self) -> None:
        self.asset_watch_after_id = self.root.after(1000, self._poll_assets)

    def _poll_assets(self) -> None:
        changed: list[str] = []
        for path in self.last_used_files:
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            old = self.asset_mtimes.get(path)
            if old is not None and old != mtime:
                changed.append(path.as_posix())
            self.asset_mtimes[path] = mtime
        if changed:
            self.logger.log('ASSET_CHANGED', files=changed)
            self.redraw_canvas()
            self._update_validation_panel()
        self._schedule_asset_watch()

    # ---------- general refresh / close ----------
    def _sync_property_panel(self) -> None:
        if not self.selected_id:
            return
        try:
            geom = self.session.geometry(self.selected_id)
            for name, value in zip(('x', 'y', 'w', 'h'), (geom.x, geom.y, geom.w, geom.h)):
                self.prop_vars[name].set(str(value))
            element = self.session.document.element(self.selected_id)
            self.type_var.set(str(element.get('type', '')))
            self.resource_var.set(self._resource_description(element))
        except Exception:
            pass

    def _update_title(self) -> None:
        dirty = ' *' if self.session.document.dirty else ''
        self.root.title(APP_TITLE + dirty)

    def refresh_all(self, *, keep_selection: bool = False) -> None:
        self._sync_state_controls()
        if keep_selection:
            self._sync_property_panel()
        self.redraw_canvas()
        self._update_validation_panel()
        self._update_title()

    def on_close(self) -> None:
        if self.session.document.dirty:
            choice = messagebox.askyesnocancel('Unsaved Scene', 'Save scene changes before closing?', parent=self.root)
            if choice is None:
                return
            if choice:
                try:
                    self.session.save()
                except Exception as exc:
                    messagebox.showerror('Save Error', str(exc), parent=self.root)
                    return
        self.playing = False
        if self.play_after_id:
            self.root.after_cancel(self.play_after_id)
        if self.asset_watch_after_id:
            self.root.after_cancel(self.asset_watch_after_id)
        try:
            self.logger.write_markdown(self.log_path.with_suffix('.md'))
        finally:
            self.logger.close()
        self.root.destroy()


def check_environment(scene_name: str) -> int:
    try:
        import tkinter  # noqa: F401 — explicit dependency check
        scene = load_scene(scene_name)
        session = EditorSession(scene)
        result = session.render()
        findings = session.validate()
        raw = result.framebuffer.to_vlsb()
        if len(raw) != 512 or has_blockers(findings):
            print(f'GUI CHECK FAIL: framebuffer={len(raw)} bytes, blockers={sum(1 for f in findings if f.severity in {"ERROR", "BLOCKER"})}')
            return 2
        print(f'GUI CHECK PASS: tkinter={tk.TkVersion}, canvas=128x32, framebuffer={len(raw)} bytes, elements={len(scene.get("elements", []))}')
        return 0
    except Exception as exc:
        print(f'GUI CHECK FAIL: {exc}', file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument('--scene', default='main_scene', help='scene name or JSON path')
    parser.add_argument('--check', action='store_true', help='verify GUI/core dependencies without opening a window')
    parser.add_argument('--smoke-ms', type=int, default=0, help=argparse.SUPPRESS)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        return check_environment(args.scene)
    root = tk.Tk()
    app = OLEDDesignerApp(root, args.scene)
    if args.smoke_ms > 0:
        root.after(args.smoke_ms, app.on_close)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
