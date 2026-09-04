from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject, QSignalBlocker, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QScrollArea, QSplitter, QVBoxLayout, QWidget
from builtin_oled_font import DEFAULT_CHARACTERS, recommended_advance, recommended_baseline
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters, recommended_font_size, recommended_truetype_layout
from i18n import DEFAULT_LANGUAGE, Translator
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas
from ui_controls import StudioButton, StudioNumericInput, StudioSelect


class _FontGenerateWorker(QObject):
    progress=Signal(int,int)
    succeeded=Signal(object,int)
    failed=Signal(str)
    finished=Signal()
    max_progress_updates=50

    def __init__(self,*,root: Path,name: str,cell: tuple[int,int],baseline: int,advance: int,characters: str,font_path: str|None,font_size: int,threshold: int,alignment: str,antialias_scale: int,resize: bool):
        super().__init__(); self.root=root; self.name=name; self.cell=cell; self.baseline=baseline; self.advance=advance; self.characters=characters; self.font_path=font_path; self.font_size=font_size; self.threshold=threshold; self.alignment=alignment; self.antialias_scale=antialias_scale; self.resize=resize; self._last_progress=0

    def _emit_progress(self,done: int,total: int):
        step=max(1,int(total)//self.max_progress_updates)
        if done==1 or done==total or done-self._last_progress>=step:
            self._last_progress=done
            self.progress.emit(done,total)

    @Slot()
    def run(self):
        try:
            if self.resize:
                pack=create_font_pack(self.root,self.name,cell=self.cell,baseline=self.baseline,advance=self.advance)
            else:
                pack=FontPack.load(self.root); pack.set_metrics(baseline=self.baseline,advance=self.advance)
            count=rasterize_characters(
                pack,self.characters,font_path=self.font_path,font_size=self.font_size,threshold=self.threshold,
                alignment=self.alignment,antialias_scale=self.antialias_scale,progress=self._emit_progress,
            )
            self.succeeded.emit(pack,count)
        except (OSError,ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class FontLabEditor(QWidget):
    fontSaved=Signal(str)
    def __init__(self,root: str|Path,*,parent=None,name='OLED Font',cell=(5,8),language: str=DEFAULT_LANGUAGE):
        super().__init__(parent)
        self.tr=Translator(language);self.root=Path(root).resolve();self.document_id='font:'+str(self.root);self.title=self.root.name;self._dirty=False;self._resolved_theme='monooled-light'
        manifest_exists=(self.root/'fontpack.json').exists()
        self.pack=FontPack.load(self.root) if manifest_exists else create_font_pack(self.root,name,cell=cell,baseline=recommended_baseline(cell),advance=recommended_advance(cell))
        if not manifest_exists:self.pack.save()
        self.current_char=None;self.document=PixelDocument(*self.pack.cell)
        self._generation_thread:QThread|None=None;self._generation_worker:_FontGenerateWorker|None=None;self._generation_error='';self._baseline_user_override=False;self._advance_user_override=False;self._font_size_user_override=False
        self._build();self.refresh_glyphs();self.retranslate_ui()

    @property
    def dirty(self):return self._dirty or self.document.dirty

    @property
    def generation_in_progress(self):
        return self._generation_thread is not None and self._generation_thread.isRunning()

    def can_close(self):
        if self.generation_in_progress:
            self.generation_status.setText(self.tr('font.generate.running'));return False
        return True

    def _build(self):
        root=QVBoxLayout(self);root.setContentsMargins(6,6,6,6);root.setSpacing(6)
        top=QHBoxLayout();self.title_label=QLabel();self.title_label.setObjectName('PanelTitle');top.addWidget(self.title_label);top.addStretch(1);self.save_btn=StudioButton();self.save_btn.setObjectName('PrimaryButton');self.save_btn.clicked.connect(self.save);top.addWidget(self.save_btn);root.addLayout(top)
        self.split=QSplitter(Qt.Horizontal);root.addWidget(self.split,1)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(4,4,4,4);self.glyphs=QListWidget();self.glyphs.currentTextChanged.connect(self._select_glyph);self.characters_label=QLabel();ll.addWidget(self.characters_label);ll.addWidget(self.glyphs,1);self.split.addWidget(left)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(4,4,4,4);self.canvas=PixelCanvas(self.document);self.canvas.zoom=24;self.canvas._sync_size();scroll=QScrollArea();scroll.setWidget(self.canvas);scroll.setWidgetResizable(False);cl.addWidget(scroll,1);self.split.addWidget(center)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,8,8,8);form=QFormLayout();self.chars=QLineEdit(DEFAULT_CHARACTERS);self.font_path=QLineEdit();self.font_path.setPlaceholderText(self.tr('font.source_builtin'));self.font_path.textChanged.connect(self._font_source_changed);self.browse_btn=StudioButton();self.browse_btn.clicked.connect(self._browse_font);fontrow=QWidget();fr=QHBoxLayout(fontrow);fr.setContentsMargins(0,0,0,0);fr.addWidget(self.font_path,1);fr.addWidget(self.browse_btn)
        self.font_size=StudioNumericInput();self.font_size.setRange(4,96);self.font_size.setValue(recommended_font_size(self.pack.cell));self.font_size.editingFinished.connect(self._font_size_edited);self.cell_w=StudioNumericInput();self.cell_w.setRange(1,128);self.cell_w.setValue(self.pack.cell[0]);self.cell_h=StudioNumericInput();self.cell_h.setRange(1,128);self.cell_h.setValue(self.pack.cell[1]);self.baseline=StudioNumericInput();self.baseline.setRange(0,max(0,self.pack.cell[1]-1));self.baseline.setValue(self.pack.baseline);self.advance=StudioNumericInput();self.advance.setRange(1,128);self.advance.setValue(self.pack.advance);self.threshold=StudioNumericInput();self.threshold.setRange(0,255);self.threshold.setValue(128);self.alignment=StudioSelect();self.alignment.addItem('相对于整体','font_set');self.alignment.addItem('相对于字宽','glyph_width');self.alignment.setCurrentIndex(self.alignment.findData('glyph_width'));self.antialias=StudioSelect();self.antialias.addItem('1×',1);self.antialias.addItem('2×',2);self.antialias.addItem('4×',4);self.cell_w.valueChanged.connect(self._cell_width_changed);self.cell_h.valueChanged.connect(self._cell_height_changed);self.baseline.valueChanged.connect(self._metrics_changed);self.baseline.editingFinished.connect(self._baseline_edited);self.advance.valueChanged.connect(self._metrics_changed);self.advance.editingFinished.connect(self._advance_edited)
        self._form_labels={}
        for key,widget in (('font.characters',self.chars),('font.source',fontrow),('font.size',self.font_size),('font.cell_width',self.cell_w),('font.cell_height',self.cell_h),('font.baseline',self.baseline),('font.advance',self.advance),('font.threshold',self.threshold),('font.alignment',self.alignment),('font.antialias',self.antialias)):
            label=QLabel();self._form_labels[key]=label;form.addRow(label,widget)
        rl.addLayout(form);self.generate_btn=StudioButton();self.generate_btn.setObjectName('PrimaryButton');self.generate_btn.clicked.connect(self.generate);rl.addWidget(self.generate_btn)
        self.generation_status=QLabel();self.generation_status.setObjectName('Muted');self.generation_status.setWordWrap(True);rl.addWidget(self.generation_status);rl.addStretch(1);self.split.addWidget(right);self.split.setSizes([180,700,300]);self._sync_source_controls()

    def retranslate_ui(self):
        self.title_label.setText(self.tr('font.title'));self.save_btn.setText(self.tr('font.save_glyph'));self.characters_label.setText(self.tr('font.characters'));self.browse_btn.setText(self.tr('font.browse'));self.generate_btn.setText(self.tr('font.generate'))
        for key,label in self._form_labels.items():label.setText(self.tr(key))
        self.font_path.setPlaceholderText(self.tr('font.source_builtin'))
        if self.generation_in_progress:self.generation_status.setText(self.tr('font.generate.running'))

    def apply_runtime_delta(self,delta):
        runtime=delta.after
        if delta.language_changed and runtime.language!=self.tr.language:
            self.tr.set_language(runtime.language);self.retranslate_ui()
        host=self.window();theme=getattr(host,'_resolved_theme',None)
        if theme and (delta.appearance_changed or theme!=self._resolved_theme):
            self._resolved_theme=theme;self.canvas.theme_name=theme;self.canvas.update()
        if delta.performance_changed:self.document.set_max_undo(runtime.undo_history)

    def _browse_font(self):
        p,_=QFileDialog.getOpenFileName(self,self.tr('font.file_dialog'),'','Fonts (*.ttf *.otf *.ttc)')
        if p:self.font_path.setText(p)

    def _font_source_changed(self,*_):
        self._sync_source_controls()
        self._apply_auto_font_layout()

    def _sync_source_controls(self):
        custom=bool(self.font_path.text().strip())
        available=not self.generation_in_progress
        self.font_size.setEnabled(custom and available)
        self.threshold.setEnabled(custom and available)

    def _baseline_edited(self):
        self._baseline_user_override=True

    def _advance_edited(self):
        self._advance_user_override=True

    def _font_size_edited(self):
        self._font_size_user_override=True
        self._apply_auto_font_layout()

    def _apply_auto_font_layout(self):
        cell=(self.cell_w.value(),self.cell_h.value())
        path=self.font_path.text().strip()
        if not path:
            if not self._baseline_user_override:
                blocker=QSignalBlocker(self.baseline);self.baseline.setValue(recommended_baseline(cell));del blocker
            if not self._advance_user_override:
                blocker=QSignalBlocker(self.advance);self.advance.setValue(recommended_advance(cell));del blocker
            if not self._font_size_user_override:
                blocker=QSignalBlocker(self.font_size);self.font_size.setValue(recommended_font_size(cell));del blocker
            self._metrics_changed();return
        try:
            fitted,baseline=recommended_truetype_layout(path,cell,self.chars.text(),self.font_size.value())
        except (OSError,ValueError):
            return
        if not self._font_size_user_override:
            blocker=QSignalBlocker(self.font_size);self.font_size.setValue(fitted);del blocker
        if not self._baseline_user_override:
            blocker=QSignalBlocker(self.baseline);self.baseline.setValue(baseline);del blocker
        self._metrics_changed()

    def _cell_width_changed(self,value):
        cell=(int(value),self.cell_h.value())
        if not self._advance_user_override:
            blocker=QSignalBlocker(self.advance);self.advance.setValue(recommended_advance(cell));del blocker
        if not self._font_size_user_override:
            blocker=QSignalBlocker(self.font_size);self.font_size.setValue(recommended_font_size(cell));del blocker
        self._apply_auto_font_layout()
        self._metrics_changed()

    def refresh_glyphs(self):
        current=self.current_char;self.glyphs.clear();self.glyphs.addItems(self.pack.characters())
        items=self.glyphs.findItems(current,Qt.MatchExactly) if current else []
        if items:self.glyphs.setCurrentItem(items[0])
        elif self.glyphs.count()>0:self.glyphs.setCurrentRow(0)
        else:
            self.current_char=None;self.document=PixelDocument(*self.pack.cell);self.canvas.set_document(self.document)

    def _select_glyph(self,ch):
        if not ch:return
        if self.current_char and self.document.dirty:
            previous=self.current_char
            if not self.save():
                blocker=QSignalBlocker(self.glyphs); items=self.glyphs.findItems(previous,Qt.MatchExactly)
                if items:self.glyphs.setCurrentItem(items[0])
                del blocker; return
        self.current_char=ch;g=self.pack.glyph(ch);self.document=PixelDocument(self.pack.cell[0],self.pack.cell[1],[row[:] for row in g.pixels]);self.canvas.set_document(self.document)

    def _cell_height_changed(self,value):
        maximum=max(0,int(value)-1);self.baseline.setMaximum(maximum);cell=(self.cell_w.value(),int(value))
        if not self._baseline_user_override:
            blocker=QSignalBlocker(self.baseline);self.baseline.setValue(recommended_baseline(cell));del blocker
        elif self.baseline.value()>maximum:
            self.baseline.setValue(maximum)
        if not self._font_size_user_override:
            blocker=QSignalBlocker(self.font_size);self.font_size.setValue(recommended_font_size(cell));del blocker
        self._apply_auto_font_layout()
        self._metrics_changed()

    def _metrics_changed(self,*_):
        self._dirty=(self.baseline.value()!=self.pack.baseline or self.advance.value()!=self.pack.advance)

    def _set_generation_busy(self,busy: bool):
        for widget in (self.glyphs,self.canvas,self.chars,self.font_path,self.browse_btn,self.font_size,self.cell_w,self.cell_h,self.baseline,self.advance,self.threshold,self.alignment,self.antialias,self.save_btn,self.generate_btn):
            widget.setEnabled(not busy)
        if not busy:self._sync_source_controls()

    def _generation_progress(self,done: int,total: int):
        self.generation_status.setText(self.tr('font.generate.progress',done=done,total=total))

    def _generation_succeeded(self,pack: FontPack,count: int):
        self.pack=pack;self._dirty=False;self.current_char=None;self.refresh_glyphs();self.fontSaved.emit(str(self.root));self.generation_status.setText(self.tr('font.generated',count=count));self.generation_status.setToolTip('')

    def _generation_failed(self,message: str):
        self._generation_error=str(message);self.generation_status.setText(self.tr('font.generate.failed'));self.generation_status.setToolTip(self._generation_error)

    def _generation_finished(self):
        self._set_generation_busy(False);self._generation_worker=None;self._generation_thread=None

    def generate(self):
        if self.generation_in_progress:return
        new_cell=(self.cell_w.value(),self.cell_h.value());resize=new_cell!=self.pack.cell
        if resize and self.pack.characters():
            if QMessageBox.question(self,self.tr('font.resize_title'),self.tr('font.resize_confirm'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:FontPack.validate_metrics(cell=new_cell,baseline=self.baseline.value(),advance=self.advance.value())
        except ValueError as exc:self._generation_failed(str(exc));return
        characters=self.chars.text();total=len(dict.fromkeys(characters));self._generation_error='';self._set_generation_busy(True);self._generation_progress(0,total)
        thread=QThread(self);worker=_FontGenerateWorker(root=self.root,name=self.pack.name,cell=new_cell,baseline=self.baseline.value(),advance=self.advance.value(),characters=characters,font_path=self.font_path.text().strip() or None,font_size=self.font_size.value(),threshold=self.threshold.value(),alignment=self.alignment.currentData(),antialias_scale=self.antialias.currentData(),resize=resize)
        worker.moveToThread(thread);thread.started.connect(worker.run);worker.progress.connect(self._generation_progress);worker.succeeded.connect(self._generation_succeeded);worker.failed.connect(self._generation_failed);worker.finished.connect(thread.quit);worker.finished.connect(worker.deleteLater);thread.finished.connect(self._generation_finished);thread.finished.connect(thread.deleteLater)
        self._generation_thread=thread;self._generation_worker=worker;thread.start()

    def save(self):
        if self.generation_in_progress:return False
        try:
            if self.current_char:
                old=self.pack.glyph(self.current_char).metrics if self.current_char in self.pack.characters() else GlyphMetrics(0,0,self.pack.advance);self.pack.set_glyph(self.current_char,[r[:] for r in self.document.pixels],old)
            self.pack.set_metrics(baseline=self.baseline.value(),advance=self.advance.value()); changed={self.current_char} if self.current_char and self.document.dirty else set(); path=self.pack.save(changed_chars=changed)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self,self.tr('font.title'),str(exc)); return False
        self.document.dirty=False;self._dirty=False;self.fontSaved.emit(str(self.root));return path

    def undo(self):
        if self.document.undo():self.canvas.update();return True
        return False
    def redo(self):
        if self.document.redo():self.canvas.update();return True
        return False

    def closeEvent(self,event):  # noqa: N802
        if not self.can_close():event.ignore();return
        super().closeEvent(event)

    def layout_violations(self):
        out=[]
        if self.width()>0 and self.width()<520:out.append('font_lab_width')
        if self.canvas.width()<=0 or self.canvas.height()<=0:out.append('font_canvas')
        return out
