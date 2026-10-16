"""Cursor inactivity is scoped to display windows and never consumes controls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from PyQt6.QtTest import QTest
from slideshow.idle_cursor import IdleCursor

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class IdleCursorTests(unittest.TestCase):
    def display(self):
        window=QWidget(); window.resize(400,300)
        layout=QVBoxLayout(window); button=QPushButton('Keep clicks working'); layout.addWidget(button)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        controller=IdleCursor(window,timeout_ms=60)
        window.show(); APP.processEvents()
        self.addCleanup(window.close)
        return window,button,controller

    def test_three_second_default(self):
        window=QWidget(); controller=IdleCursor(window)
        self.assertEqual(controller.timer.interval(),3000)
        window.close()

    def test_idle_move_click_and_explicit_cursor_restore(self):
        window,button,controller=self.display()
        QTest.qWait(90)
        self.assertTrue(controller.hidden)
        self.assertEqual(button.cursor().shape(),Qt.CursorShape.BlankCursor)
        # Send an actual mouse-move event to a child, without any click.
        QTest.mouseMove(button,QPoint(8,8)); APP.processEvents()
        self.assertFalse(controller.hidden)
        self.assertEqual(button.cursor().shape(),Qt.CursorShape.PointingHandCursor)
        clicks=[]; button.clicked.connect(lambda:clicks.append(True))
        QTest.qWait(90); self.assertTrue(controller.hidden)
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertEqual(clicks,[True]); self.assertFalse(controller.hidden)
        window.close(); self.assertFalse(controller.timer.isActive())
        self.assertEqual(window.cursor().shape(),Qt.CursorShape.ArrowCursor)
        self.assertEqual(button.cursor().shape(),Qt.CursorShape.PointingHandCursor)

    def test_settings_and_dynamic_nighttime_children(self):
        window,button,controller=self.display()
        settings=QWidget(); settings.show(); self.addCleanup(settings.close)
        QTest.qWait(90)
        self.assertTrue(controller.hidden)
        self.assertNotEqual(settings.cursor().shape(),Qt.CursorShape.BlankCursor)
        night=QWidget(window); night.resize(100,100); night.show(); APP.processEvents()
        self.assertTrue(night.hasMouseTracking())
        # A display's child show may generate Enter events; wait for idle again.
        QTest.qWait(90)
        self.assertEqual(night.cursor().shape(),Qt.CursorShape.BlankCursor)
        QTest.mouseMove(night,QPoint(20,20)); APP.processEvents()
        self.assertFalse(controller.hidden)
        self.assertNotEqual(night.cursor().shape(),Qt.CursorShape.BlankCursor)
        window.hide(); self.assertFalse(controller.timer.isActive())
        self.assertNotEqual(settings.cursor().shape(),Qt.CursorShape.BlankCursor)

if __name__=='__main__': unittest.main()
