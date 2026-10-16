"""Compact, plain-text scheduled-event information shared by both layouts."""
from PyQt6.QtCore import Qt,QRect
from PyQt6.QtGui import QColor,QFont,QFontMetrics
from PyQt6.QtWidgets import QWidget,QLabel,QVBoxLayout,QSizePolicy
from .health_indicator import event_color


class NextSession(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.row=QVBoxLayout(self);self.row.setContentsMargins(0,0,0,0)
        self.labels=[];self.view={}
        for key in ('heading','title','when','detail','note'):
            label=QLabel(self);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
            label.setMinimumWidth(0);label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            setattr(self,key,label);self.labels.append(label);self.row.addWidget(label)
        self.hide()

    def set_view(self,view,primary,secondary,brightness=None):
        self.view=dict(view)
        for key in ('heading','title','when','detail','note'):
            label=getattr(self,key);label.setText(view.get(key,''));label.setVisible(bool(label.text()))
            color=primary if key=='title' else secondary
            if key=='detail' and view.get('imminent'):color=event_color(brightness).name()
            label.setStyleSheet(f'color:{color};background:transparent;')
        self.setVisible(bool(view))

    def set_metrics(self,scale,width,night=False):
        sizes=(18,34,24,23,20) if night else (12,22,15,15,12)
        self.row.setSpacing(max(2,round(3*scale)))
        for label,pixels in zip(self.labels,sizes):
            font=QFont('DejaVu Sans');font.setPixelSize(max(11,round(pixels*scale)))
            if label is self.heading:font.setWeight(QFont.Weight.Medium)
            label.setFont(font)
            bounds=QFontMetrics(font).boundingRect(QRect(0,0,max(1,int(width)),10000),int(Qt.TextFlag.TextWordWrap),label.text())
            label.setMinimumHeight(bounds.height()+2 if label.text() else 0)
