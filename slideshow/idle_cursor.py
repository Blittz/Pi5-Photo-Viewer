"""Window-scoped cursor inactivity, shared by slideshow and night displays."""
from PyQt6 import sip
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget


class IdleCursor(QObject):
    """Hide only this display's pointer; never use an application-wide override.

    Event filtering does not consume input. Descendant tracking also covers a
    future nighttime widget added to this display's window.
    """
    def __init__(self, window, timeout_ms=3000):
        super().__init__(window)
        self.window = window
        self.hidden = False
        self._saved = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(timeout_ms)
        self.timer.timeout.connect(self._hide_cursor)
        self._app_filter_active = False
        window.installEventFilter(self)
        window.destroyed.connect(self._remove_app_filter)
        self._track_children()

    def _install_app_filter(self):
        app = QApplication.instance()
        if app is not None and not self._app_filter_active:
            app.installEventFilter(self)
            self._app_filter_active = True

    def _remove_app_filter(self):
        app = QApplication.instance()
        if app is not None and getattr(self, '_app_filter_active', False):
            app.removeEventFilter(self)
        self._app_filter_active = False

    def _widgets(self):
        if sip.isdeleted(self.window):
            return []
        return [self.window, *self.window.findChildren(QWidget)]

    def _track_children(self):
        for widget in self._widgets():
            widget.setMouseTracking(True)
            if self.hidden and widget not in self._saved:
                self._blank(widget)

    def _blank(self, widget):
        self._saved[widget] = (widget.testAttribute(Qt.WidgetAttribute.WA_SetCursor), widget.cursor())
        widget.setCursor(Qt.CursorShape.BlankCursor)

    def _hide_cursor(self):
        if sip.isdeleted(self.window) or not self.window.isVisible():
            return
        # Save every cursor before changing any inherited cursor.
        widgets = self._widgets()
        self._saved = {w: (w.testAttribute(Qt.WidgetAttribute.WA_SetCursor), w.cursor()) for w in widgets}
        for widget in widgets:
            widget.setCursor(Qt.CursorShape.BlankCursor)
        self.hidden = True

    def show_cursor(self):
        for widget, (explicit, cursor) in self._saved.items():
            try:
                if explicit:
                    widget.setCursor(cursor)
                else:
                    widget.unsetCursor()
            except RuntimeError:
                pass  # A transient child may have been deleted while hidden.
        self._saved.clear()
        self.hidden = False

    def stop(self):
        self.timer.stop()
        self.show_cursor()

    def eventFilter(self, watched, event):
        window = getattr(self, "window", None)
        if window is None or sip.isdeleted(window) or not isinstance(watched, QWidget):
            return False
        belongs = watched is window or window.isAncestorOf(watched)
        kind = event.type()
        if belongs:
            if kind in (QEvent.Type.Show, QEvent.Type.ChildAdded):
                # ChildAdded can precede completion of a QWidget constructor.
                QTimer.singleShot(0, self._track_children)
            if watched is self.window:
                if kind == QEvent.Type.Show:
                    self._install_app_filter()
                    self.timer.start()
                elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
                    self.stop()
                    self._remove_app_filter()
            if kind in (QEvent.Type.MouseMove,
                        QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                        QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.TouchBegin):
                self.show_cursor()
                if self.window.isVisible():
                    self.timer.start()
        return False
