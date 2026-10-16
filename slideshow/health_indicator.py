"""Static, click-through window edge and compact information-area warning."""
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QSizePolicy

DAY_RED = '#ba5b57'
EVENT_BLUE = '#5c8fbc'


def _edge_color(value, brightness=None):
    color = QColor(value)
    if brightness is None:
        return color
    background = QColor('#070809')
    ratio = max(5, min(100, brightness)) / 100
    return QColor(*[round(background.getRgb()[i] + (color.getRgb()[i] - background.getRgb()[i]) * ratio)
                    for i in range(3)])


def warning_color(brightness=None):
    return _edge_color(DAY_RED, brightness)


def event_color(brightness=None):
    return _edge_color(EVENT_BLUE, brightness)


class HealthEdge(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.issues = ()
        self.brightness = None
        self.mode = None
        self._border_cache = None
        self._border_key = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def set_health(self, issues, brightness=None, imminent=False):
        self.issues, self.brightness = tuple(issues), brightness
        self.mode = "health" if self.issues else "event" if imminent else None
        self.setVisible(self.mode is not None)
        self.raise_()
        self.update()

    def fade_width(self):
        return max(1, round(min(self.width(), self.height()) * .05))

    def paintEvent(self, event):
        if self.mode is None:
            return
        color = warning_color(self.brightness) if self.mode == "health" else event_color(self.brightness)
        key = (self.width(), self.height(), color.rgba(), self.devicePixelRatioF())
        if key != self._border_key:
            ratio = self.devicePixelRatioF()
            pixmap = QPixmap(round(self.width()*ratio), round(self.height()*ratio))
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            fade = self.fade_width()
            # Nested rounded contours produce a smooth, non-additive fade at
            # corners too. Cache the static result; photo motion cannot animate it.
            for depth in range(fade-1, -1, -1):
                ink = QColor(color)
                ink.setAlpha(round(145 * (1-depth/fade)**2))
                outer = QPainterPath(); inner = QPainterPath()
                radius = max(0, fade*.6-depth)
                outer.addRoundedRect(QRectF(depth,depth,max(0,self.width()-2*depth),
                                           max(0,self.height()-2*depth)),radius,radius)
                inset = depth+1
                inner.addRoundedRect(QRectF(inset,inset,max(0,self.width()-2*inset),
                                           max(0,self.height()-2*inset)),max(0,radius-1),max(0,radius-1))
                painter.fillPath(outer.subtracted(inner), ink)
            painter.setPen(QPen(color, 2))
            painter.drawRoundedRect(QRectF(1,1,max(0,self.width()-2),max(0,self.height()-2)),
                                    fade*.6, fade*.6)
            painter.end()
            self._border_cache, self._border_key = pixmap, key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._border_cache)


class WarningIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(DAY_RED)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/24, self.height()/24)
        p.setPen(QPen(self.color, 1.5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath(); path.moveTo(12, 3); path.lineTo(22, 21); path.lineTo(2, 21); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(12, 9, 12, 14)
        p.drawPoint(12, 17)


class HealthNotice(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.issues = ()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.row = QHBoxLayout(self); self.row.setContentsMargins(0, 0, 0, 0)
        self.icon = WarningIcon(self)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.row.addWidget(self.label, 1)
        self.hide()

    def set_health(self, issues, brightness=None):
        self.issues = tuple(issues)
        self.label.setText(' · '.join(self.issues))
        color = warning_color(brightness)
        self.label.setStyleSheet(f'color:{color.name()}; background:transparent;')
        self.icon.color = color; self.icon.update()
        self.setVisible(bool(issues))

    def set_metrics(self, pixels, width):
        font = QFont('DejaVu Sans'); font.setPixelSize(max(12, round(pixels)))
        self.label.setFont(font)
        size = max(16, round(pixels * 1.2))
        self.icon.setFixedSize(size, size)
        self.row.setSpacing(max(5, round(pixels * .45)))
        available = max(1, int(width) - size - self.row.spacing())
        bounds = QFontMetrics(font).boundingRect(QRect(0, 0, available, 10000),
                                               int(Qt.TextFlag.TextWordWrap), self.label.text())
        self.label.setMinimumHeight(bounds.height()+4 if self.issues else 0)
