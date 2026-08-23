from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QScrollArea, QSplitter, QVBoxLayout, QWidget
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters
from i18n import DEFAULT_LANGUAGE, Translator
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas
from ui_controls import StudioButton, StudioNumericInput


class FontLabEditor(QWidget):
    fontSaved=Signal(str)
    def __init__(self,root: str|Path,*,parent=None,name='OLED Font',cell=(5,8),language: str=DEFAULT_LANGUAGE):
        super().__init__(parent)
        self.tr=Translator(language);self.root=Path(root).resolve();self.document_id='font:'+str(self.root);self.title=self.root.name;self._dirty=False;self._resolved_theme='monooled-light'
        self.pack=FontPack.load(self.root) if (self.root/'fontpack.json').exists() else create_font_pack(self.root,name,cell=cell,baseline=max(0,cell[1]-2),advance=cell[0]+1)
        self.pack.save();self.current_char=None;self.document=PixelDocument(*self.pack.cell)
        self._build();self.refresh_glyphs();self.retranslate_ui()

    @property
    def dirty(self):return self._dirty or self.document.dirty

    def _build(self):
        root=QVBoxLayout(self);root.setContentsMargins(6,6,6,6);root.setSpacing(6)
        top=QHBoxLayout();self.title_label=QLabel();self.title_label.setObjectName('PanelTitle');top.addWidget(self.title_label);top.addStretch(1);self.save_btn=StudioButton();self.save_btn.setObjectName('PrimaryButton');self.save_btn.clicked.connect(self.save);top.addWidget(self.save_btn);root.addLayout(top)
        self.split=QSplitter(Qt.Horizontal);root.addWidget(self.split,1)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(4,4,4,4);self.glyphs=QListWidget();self.glyphs.currentTextChanged.connect(self._select_glyph);self.characters_label=QLabel();ll.addWidget(self.characters_label);ll.addWidget(self.glyphs,1);self.split.addWidget(left)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(4,4,4,4);self.canvas=PixelCanvas(self.document);self.canvas.zoom=24;self.canvas._sync_size();scroll=QScrollArea();scroll.setWidget(self.canvas);scroll.setWidgetResizable(False);cl.addWidget(scroll,1);self.split.addWidget(center)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,8,8,8);form=QFormLayout();self.chars=QLineEdit('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789');self.font_path=QLineEdit();self.browse_btn=StudioButton();self.browse_btn.clicked.connect(self._browse_font);fontrow=QWidget();fr=QHBoxLayout(fontrow);fr.setContentsMargins(0,0,0,0);fr.addWidget(self.font_path,1);fr.addWidget(self.browse_btn)
        self.font_size=StudioNumericInput();self.font_size.setRange(4,96);self.font_size.setValue(12);self.cell_w=StudioNumericInput();self.cell_w.setRange(1,128);self.cell_w.setValue(self.pack.cell[0]);self.cell_h=StudioNumericInput();self.cell_h.setRange(1,128);self.cell_h.setValue(self.pack.cell[1]);self.baseline=StudioNumericInput();self.baseline.setRange(-128,128);self.baseline.setValue(self.pack.baseline);self.advance=StudioNumericInput();self.advance.setRange(1,128);self.advance.setValue(self.pack.advance);self.threshold=StudioNumericInput();self.threshold.setRange(0,255);self.threshold.setValue(128)
        self._form_labels={}
        for key,widget in (('font.characters',self.chars),('font.source',fontrow),('font.size',self.font_size),('font.cell_width',self.cell_w),('font.cell_height',self.cell_h),('font.baseline',self.baseline),('font.advance',self.advance),('font.threshold',self.threshold)):
            label=QLabel();self._form_labels[key]=label;form.addRow(label,widget)
        rl.addLayout(form);self.generate_btn=StudioButton();self.generate_btn.setObjectName('PrimaryButton');self.generate_btn.clicked.connect(self.generate);rl.addWidget(self.generate_btn);rl.addStretch(1);self.split.addWidget(right);self.split.setSizes([180,700,300])

    def retranslate_ui(self):
        self.title_label.setText(self.tr('font.title'));self.save_btn.setText(self.tr('font.save_glyph'));self.characters_label.setText(self.tr('font.characters'));self.browse_btn.setText(self.tr('font.browse'));self.generate_btn.setText(self.tr('font.generate'))
        for key,label in self._form_labels.items():label.setText(self.tr(key))

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

    def refresh_glyphs(self):
        current=self.current_char;self.glyphs.clear();self.glyphs.addItems(self.pack.characters())
        if current:
            items=self.glyphs.findItems(current,Qt.MatchExactly)
            if items:self.glyphs.setCurrentItem(items[0])

    def _select_glyph(self,ch):
        if not ch:return
        if self.current_char and self.document.dirty:self.save()
        self.current_char=ch;g=self.pack.glyph(ch);self.document=PixelDocument(self.pack.cell[0],self.pack.cell[1],[row[:] for row in g.pixels]);self.canvas.set_document(self.document)

    def generate(self):
        new_cell=(self.cell_w.value(),self.cell_h.value())
        if new_cell!=self.pack.cell and self.pack.characters():
            if QMessageBox.question(self,self.tr('font.resize_title'),self.tr('font.resize_confirm'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            self.pack=create_font_pack(self.root,self.pack.name,cell=new_cell,baseline=self.baseline.value(),advance=self.advance.value())
        else:
            self.pack.cell=new_cell;self.pack.baseline=self.baseline.value();self.pack.advance=self.advance.value()
        count=rasterize_characters(self.pack,self.chars.text(),font_path=self.font_path.text().strip() or None,font_size=self.font_size.value(),threshold=self.threshold.value());self._dirty=False;self.refresh_glyphs();self.fontSaved.emit(str(self.root));QMessageBox.information(self,self.tr('font.title'),self.tr('font.generated',count=count))

    def save(self):
        if self.current_char:
            old=self.pack.glyph(self.current_char).metrics if self.current_char in self.pack.characters() else GlyphMetrics(0,0,self.pack.advance);self.pack.set_glyph(self.current_char,[r[:] for r in self.document.pixels],old)
        self.pack.baseline=self.baseline.value();self.pack.advance=self.advance.value();self.pack.save();self.document.dirty=False;self._dirty=False;self.fontSaved.emit(str(self.root));return self.pack.manifest_path

    def undo(self):
        if self.document.undo():self.canvas.update();return True
        return False
    def redo(self):
        if self.document.redo():self.canvas.update();return True
        return False

    def layout_violations(self):
        out=[]
        if self.width()>0 and self.width()<520:out.append('font_lab_width')
        if self.canvas.width()<=0 or self.canvas.height()<=0:out.append('font_canvas')
        return out
