"""Stationary, click-through imminent-session caption over the photo viewport."""
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont,QFontMetrics
from PyQt6.QtWidgets import QWidget,QLabel,QVBoxLayout,QSizePolicy


class EventCaption(QWidget):
    def __init__(self,viewport):
        super().__init__(viewport)
        self.view={}
        self._position_key=None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName('imminentEventCaption')
        self.setStyleSheet('QWidget#imminentEventCaption {background-color:rgba(12,14,16,170);border-radius:5px;}')
        self.layout=QVBoxLayout(self)
        self.labels=[]
        for name in ('title','when','countdown'):
            label=QLabel(self);label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True);label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            label.setStyleSheet('background:transparent;color:'+('#d1cec8' if name=='when' else '#f3eee5')+';')
            setattr(self,name,label);self.labels.append(label);self.layout.addWidget(label)
        self.hide()

    def set_view(self,view):
        view=view if view and view.get('imminent') else {}
        if view!=self.view:
            self.view=dict(view)
            self._position_key=None
            for name in ('title','when','countdown'):getattr(self,name).setText(view.get(name,''))
        self.setVisible(bool(view))
        if view:self.raise_()

    def position(self,bottom_caption=None,font_scale=1):
        if not self.view:return
        viewport=self.parentWidget()
        key=(viewport.width(),viewport.height(), font_scale,
             bottom_caption.y() if bottom_caption is not None and bottom_caption.isVisible() else None)
        if key==self._position_key:return
        self._position_key=key
        scale=max(.5,min(1.5,viewport.height()/1080))
        control=max(.8,min(1.3,font_scale))
        margin=max(12,round(24*scale))
        top=max(18,round(min(viewport.width(),viewport.height())*.065))
        width=max(1,min(viewport.width()-2*margin,round(1000*scale)))
        padding=max(8,round(14*scale))
        self.layout.setContentsMargins(padding,padding,padding,padding)
        self.layout.setSpacing(max(3,round(6*scale)))
        available=max(1,width-2*padding)
        bottom=viewport.height()-margin
        if bottom_caption is not None and bottom_caption.isVisible():bottom=min(bottom,bottom_caption.y()-margin)
        max_height=max(1,bottom-top)
        factor=1.0
        while True:
            heights=[]
            for label,pixels in zip(self.labels,(26,19,34)):
                font=QFont('DejaVu Sans');font.setPixelSize(max(12,round(pixels*scale*control*factor)))
                if label is self.countdown:font.setWeight(QFont.Weight.DemiBold)
                label.setFont(font)
                bounds=QFontMetrics(font).boundingRect(QRect(0,0,available,10000),
                                                     int(Qt.TextFlag.TextWordWrap),label.text())
                height=bounds.height()+2
                label.setMinimumHeight(height);heights.append(height)
            height=sum(heights)+2*padding+2*self.layout.spacing()
            if height<=max_height or factor<=.45:break
            factor-=.05
        self.setGeometry(max(0,(viewport.width()-width)//2),top,width,height)
        self.layout.activate()
        self.raise_()
