"""Static, click-through window edge and compact information-area warning."""
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QSizePolicy

DAY_RED = '#ba5b57'


def warning_color(brightness=None):
    color = QColor(DAY_RED)
    if brightness is None:
        return color
    background = QColor('#070809')
    ratio = max(5, min(100, brightness)) / 100
    return QColor(*[round(background.getRgb()[i] + (color.getRgb()[i] - background.getRgb()[i]) * ratio)
                    for i in range(3)])


class HealthEdge(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.issues = ()
        self.brightness = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def set_health(self, issues, brightness=None):
        self.issues, self.brightness = tuple(issues), brightness
        self.setVisible(bool(self.issues))
        self.raise_()
        self.update()

    def paintEvent(self, event):
        if not self.issues:
            return
        p = QPainter(self)
        color = warning_color(self.brightness)
        fade = min(16, self.width() / 4, self.height() / 4)
        # Four gradients point inward; the entire centre stays transparent.
        for rect, start, end in [
            (QRectF(0, 0, self.width(), fade), QPointF(0, 0), QPointF(0, fade)),
            (QRectF(0, self.height()-fade, self.width(), fade), QPointF(0, self.height()), QPointF(0, self.height()-fade)),
            (QRectF(0, 0, fade, self.height()), QPointF(0, 0), QPointF(fade, 0)),
            (QRectF(self.width()-fade, 0, fade, self.height()), QPointF(self.width(), 0), QPointF(self.width()-fade, 0)),
        ]:
            gradient = QLinearGradient(start, end)
            outer = QColor(color); outer.setAlpha(75)
            inner = QColor(color); inner.setAlpha(0)
            gradient.setColorAt(0, outer); gradient.setColorAt(1, inner)
            p.fillRect(rect, gradient)
        p.setPen(QPen(color, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(1, 1, max(0, self.width()-2), max(0, self.height()-2)))


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
