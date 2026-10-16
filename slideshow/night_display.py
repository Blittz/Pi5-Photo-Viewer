"""Dim, landscape information display; intensity never controls the monitor."""
import math
from PyQt6 import sip
from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout
from .quiet_sidebar import QuietSidebar

DEFAULT_NIGHT_BRIGHTNESS = 30
NIGHT_BACKGROUND = '#070809'


def night_brightness(value):
    try:
        if isinstance(value, bool):
            return DEFAULT_NIGHT_BRIGHTNESS
        value = float(value)
        if not math.isfinite(value):
            return DEFAULT_NIGHT_BRIGHTNESS
        return max(5, min(100, round(value)))
    except (ValueError, TypeError):
        return DEFAULT_NIGHT_BRIGHTNESS


def _remove_layout(layout):
    # Delete layout objects only, preserving their widgets for the new layout.
    while layout.count():
        item = layout.takeAt(0)
        if item.layout() is not None:
            _remove_layout(item.layout())
    sip.delete(layout)


class NightDisplay(QuietSidebar):
    """Reuse weather formatting and icons, with a separate landscape layout."""
    def __init__(self, parent=None, font_size=29, brightness=DEFAULT_NIGHT_BRIGHTNESS):
        self._night_ready = False
        self.brightness = night_brightness(brightness)
        super().__init__(parent, font_size)
        _remove_layout(self.weather_layout)
        _remove_layout(self.layout)
        self.layout = QVBoxLayout(self.content)
        self.upper = QHBoxLayout()
        self.clock_panel = QWidget()
        self.clock_layout = QVBoxLayout(self.clock_panel)
        self.clock_layout.setContentsMargins(0, 0, 0, 0)
        self.clock_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.time_row = QHBoxLayout()
        self.time_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)
        self.time_row.addWidget(self.clock_label)
        self.time_row.addWidget(self.period_label)
        self.clock_layout.addLayout(self.time_row)
        self.clock_layout.addWidget(self.day_label)
        self.clock_layout.addWidget(self.date_label)
        self.weather_layout = QVBoxLayout(self.weather_panel)
        self.weather_layout.setContentsMargins(0, 0, 0, 0)
        self.weather_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.weather_layout.addWidget(self.location_label)
        self.grid = QGridLayout()
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 2)
        self.grid.addWidget(self.icon, 0, 0, Qt.AlignmentFlag.AlignLeft)
        self.grid.addWidget(self.temperature_label, 0, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(self.condition_label, 1, 0, 1, 2)
        self.grid.addWidget(self.feels_label, 2, 0, 1, 2)
        self.weather_layout.addLayout(self.grid)
        self.upper.addWidget(self.clock_panel, 1)
        self.upper.addWidget(self.weather_panel, 1)
        self.layout.addLayout(self.upper)
        self.layout.addWidget(self.dividers[0])
        self.tiles = QHBoxLayout()
        self.tile_headers = []
        self.tile_layouts = []
        self.detail_rows = [(None, title, value) for _, title, value in self.detail_rows]
        entries = [(self.detail_icons[i], row[1], row[2]) for i, row in enumerate(self.detail_rows)]
        entries += list(zip(self.solar_icons, self.solar_titles, self.solar_labels))
        for icon, title, value in entries:
            cell = QVBoxLayout()
            header = QHBoxLayout()
            header.addWidget(icon)
            header.addWidget(title, 1)
            cell.addLayout(header)
            value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            cell.addWidget(value)
            self.tiles.addLayout(cell, 1)
            self.tile_headers.append(header)
            self.tile_layouts.append(cell)
        self.layout.addLayout(self.tiles)
        self.layout.addStretch(1)
        self.layout.addWidget(self.dividers[1])
        self.footer = QVBoxLayout()
        self.footer.addWidget(self.source_label)
        self.footer.addWidget(self.status_label)
        self.layout.addLayout(self.footer)
        self._night_ready = True
        self.apply_metrics()
        self.set_brightness(self.brightness)
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start()

    def set_brightness(self, value):
        self.brightness = night_brightness(value)
        background = QColor(NIGHT_BACKGROUND)
        def dim(color):
            color = QColor(color)
            ratio = self.brightness / 100
            return QColor(*[round(background.getRgb()[i] + (color.getRgb()[i] - background.getRgb()[i]) * ratio)
                            for i in range(3)]).name()
        self.primary = dim('#b2aaa0')
        self.secondary = dim('#948c82')
        self.amber = dim('#b58c54')
        self.setStyleSheet(f'''
            QScrollArea, QWidget#quietContent {{ background:{NIGHT_BACKGROUND}; border:0; }}
            QLabel {{ background:transparent; color:{self.primary}; border:0; }}
            QScrollBar:vertical {{ background:{NIGHT_BACKGROUND}; width:8px; }}
            QScrollBar::handle:vertical {{ background:{self.secondary}; min-height:20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        ''')
        primary_labels = [self.clock_label, self.day_label, self.date_label, self.temperature_label,
                          *self.solar_labels, self.humidity_label, self.wind_label]
        for label in self.labels:
            color = self.primary if label in primary_labels else self.secondary
            if label is self.status_label and ('STALE' in label.text() or 'failed' in label.text()):
                color = self.amber
            label.setStyleSheet(f'color:{color}; background:transparent;')
        for icon in [self.icon, *self.detail_icons, *self.solar_icons]:
            icon.ink = self.amber
            icon.background = NIGHT_BACKGROUND
            icon.update()
        for divider in self.dividers:
            divider.setStyleSheet(f'background:{dim("#484039")};')

    def set_weather(self, lines, summary=None, icon_hint=None):
        super().set_weather(lines, summary, icon_hint)
        self.set_brightness(self.brightness)

    def apply_metrics(self):
        if not getattr(self, '_night_ready', False):
            return
        width = max(300, self.viewport().width())
        height = max(300, self.viewport().height())
        scale = max(.45, min(1.5, min(width / 1920, height / 1080) * (self.font_size / 29) ** .25))
        self.scale = scale
        margin = round(96 * scale)
        gap = round(72 * scale)
        self.layout.setContentsMargins(margin, round(72 * scale), margin, round(48 * scale))
        self.layout.setSpacing(round(30 * scale))
        self.upper.setSpacing(gap)
        self.clock_layout.setSpacing(round(14 * scale))
        self.weather_layout.setSpacing(round(22 * scale))
        self.grid.setHorizontalSpacing(round(28 * scale))
        self.grid.setVerticalSpacing(round(12 * scale))
        self.time_row.setSpacing(round(16 * scale))
        self.tiles.setSpacing(round(44 * scale))
        self.footer.setSpacing(round(8 * scale))
        panel_width = max(80, (width - 2 * margin - gap) / 2)
        tile_width = max(60, (width - 2 * margin - 3 * round(44 * scale)) / 4)
        def font(label, pixels, available=None, weight=QFont.Weight.Normal):
            f = QFont('DejaVu Sans')
            f.setWeight(weight)
            f.setPixelSize(max(12, round(pixels * scale)))
            if available:
                while f.pixelSize() > 12 and QFontMetrics(f).horizontalAdvance(label.text()) > available:
                    f.setPixelSize(f.pixelSize() - 1)
            label.setFont(f)
        font(self.period_label, 42)
        # Fit the widest clock value, not just the current minute.
        clock_width = panel_width - QFontMetrics(self.period_label.font()).horizontalAdvance('PM') - round(16 * scale)
        font(self.clock_label, 240, weight=QFont.Weight.Light)
        f = self.clock_label.font()
        while f.pixelSize() > 24 and QFontMetrics(f).horizontalAdvance('12:59') > clock_width:
            f.setPixelSize(f.pixelSize() - 1)
        self.clock_label.setFont(f)
        font(self.day_label, 76, panel_width)
        font(self.date_label, 36)
        font(self.location_label, 24)
        font(self.temperature_label, 136, panel_width - round(210 * scale), QFont.Weight.Light)
        self.icon.setFixedSize(round(180 * scale), round(180 * scale))
        font(self.condition_label, 46)
        font(self.feels_label, 30)
        for _, title, value in self.detail_rows:
            font(title, 27)
            font(value, 54)
        for title in self.solar_titles:
            font(title, 27)
        for value in self.solar_labels:
            font(value, 54, tile_width)
        for icon in [*self.detail_icons, *self.solar_icons]:
            icon.setFixedSize(round(42 * scale), round(42 * scale))
        for header in self.tile_headers:
            header.setSpacing(round(14 * scale))
        for cell in self.tile_layouts:
            cell.setSpacing(round(20 * scale))
        font(self.source_label, 21)
        font(self.status_label, 21)
        for label, available in [(self.date_label, panel_width), (self.condition_label, panel_width),
                                 (self.feels_label, panel_width), (self.status_label, width - 2 * margin),
                                 (self.humidity_label, tile_width), (self.wind_label, tile_width)]:
            rect = QFontMetrics(label.font()).boundingRect(QRect(0, 0, int(available), 10000),
                                                         int(Qt.TextFlag.TextWordWrap), label.text())
            label.setMinimumHeight(rect.height() + 4 if label.text() else 0)
        self.layout.activate()
        self.content.setMinimumHeight(max(0, self.layout.totalHeightForWidth(width)))
        self.content.updateGeometry()
