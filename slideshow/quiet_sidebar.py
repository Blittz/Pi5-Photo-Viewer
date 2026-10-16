"""Stationary information sidebar and local, scalable weather line icons."""
import math
from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QRect, QRectF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QScrollArea, QSizePolicy,
)
from utils.solar import MEDFORD_TIMEZONE
from .health_indicator import HealthNotice
from .next_session import NextSession

PRIMARY = '#f3eee5'
SECONDARY = '#b8b6b1'
AMBER = '#d8ac72'
BACKGROUND = '#242628'


def weather_symbol(description, icon_url=None, night=False):
    """Classify NWS metadata locally. No icon request or image download is made."""
    description = (description or '').lower()
    path = urlparse(icon_url or '').path.lower()
    if '/night/' in path:
        night = True
    elif '/day/' in path:
        night = False
    code = path.rsplit('/', 1)[-1].split(',')[0]
    if 'thunder' in description or code.startswith('tsra'): kind = 'storm'
    elif 'tornado' in description or code == 'tornado': kind = 'tornado'
    elif 'hurricane' in description or 'tropical' in description or code.startswith(('hurricane', 'tropical')): kind = 'storm'
    elif any(w in description for w in ('freezing', 'sleet', 'ice pellet')) or code in ('fzra', 'sleet', 'rain_sleet', 'rain_fzra', 'snow_sleet', 'snow_fzra'): kind = 'ice'
    elif 'snow' in description or 'blizzard' in description or code in ('snow', 'rain_snow', 'blizzard'): kind = 'snow'
    elif any(w in description for w in ('rain', 'drizzle', 'shower')) or code.startswith(('rain', 'shra')): kind = 'rain'
    elif any(w in description for w in ('fog', 'mist', 'haze', 'smoke', 'dust', 'sand')) or code in ('fog', 'haze', 'smoke', 'dust'): kind = 'fog'
    elif 'wind' in description or code.startswith('wind'): kind = 'wind'
    elif 'partly' in description or 'few' in description or code in ('few', 'sct'): kind = 'partly'
    elif any(w in description for w in ('cloud', 'overcast')) or code in ('bkn', 'ovc'): kind = 'cloud'
    elif any(w in description for w in ('clear', 'fair', 'sunny')) or code in ('skc', 'hot', 'cold'): kind = 'clear'
    else: kind = 'unknown'
    return kind, night


class LineIcon(QWidget):
    """Resolution-independent icons drawn in a common 100-unit coordinate system."""
    def __init__(self, kind='unknown', parent=None, night=False, accent=True):
        super().__init__(parent)
        self.kind, self.night, self.accent = kind, night, accent
        self.ink = None
        self.background = BACKGROUND
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_symbol(self, kind, night=False):
        self.kind, self.night = kind, night
        self.setAccessibleName(('Night ' if night else 'Day ') + kind)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        p.translate((self.width()-size)/2, (self.height()-size)/2)
        p.scale(size/100, size/100)
        p.setPen(QPen(QColor(self.ink if self.ink is not None else (AMBER if self.accent else PRIMARY)), 3.2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        def line(x,y,a,b): p.drawLine(int(x),int(y),int(a),int(b))
        def sun(cx=50,cy=46,r=17):
            p.drawEllipse(QRectF(cx-r,cy-r,2*r,2*r))
            for angle in range(0,360,45):
                a=math.radians(angle)
                line(cx+math.cos(a)*(r+8),cy+math.sin(a)*(r+8),cx+math.cos(a)*(r+15),cy+math.sin(a)*(r+15))
        def moon():
            path=QPainterPath(); path.moveTo(66,19)
            path.cubicTo(25,10,15,64,49,76)
            path.cubicTo(67,83,82,71,85,59)
            path.cubicTo(51,68,42,34,66,19)
            p.drawPath(path)
        def cloud():
            path=QPainterPath(); path.moveTo(24,66); path.lineTo(77,66)
            path.cubicTo(96,65,96,40,76,40)
            path.cubicTo(67,14,33,18,28,42)
            path.cubicTo(6,38,5,65,24,66)
            p.drawPath(path)
        kind=self.kind
        if not self.accent and kind not in ('clear', 'partly'):
            # A matching celestial badge distinguishes day/night for overcast,
            # precipitation, wind, fog, and even the unknown-condition fallback.
            if self.night:
                p.save(); p.translate(54, -2); p.scale(.42, .42); moon(); p.restore()
            else:
                sun(77, 21, 6)
        if kind == 'clear':
            moon() if self.night else sun()
        elif kind == 'partly':
            p.save(); p.translate(1,-10); p.scale(.8,.8)
            moon() if self.night else sun(42,40,14)
            p.restore()
            p.setBrush(QColor(self.background)); cloud()
        elif kind in ('cloud','rain','snow','storm','ice'):
            p.setBrush(QColor(self.background)); cloud(); p.setBrush(Qt.BrushStyle.NoBrush)
            if kind == 'rain':
                for x in (32,52,72): line(x,76,x-5,88)
            elif kind == 'snow':
                for x in (32,52,72):
                    line(x,77,x,89); line(x-5,80,x+5,86); line(x-5,86,x+5,80)
            elif kind == 'storm':
                path=QPainterPath(); path.moveTo(55,70); path.lineTo(42,84); path.lineTo(54,84); path.lineTo(47,96); p.drawPath(path)
            elif kind == 'ice':
                for x in (33,63):
                    path=QPainterPath(); path.moveTo(x,75); path.lineTo(x+6,82); path.lineTo(x,89); path.lineTo(x-6,82); path.closeSubpath(); p.drawPath(path)
        elif kind in ('sunrise','sunset'):
            p.drawArc(QRectF(27,35,46,46),0,180*16)
            line(15,61,85,61); line(22,74,78,74)
            for a in (210,250,290,330):
                radians=math.radians(a); line(50+math.cos(radians)*31,58+math.sin(radians)*31,50+math.cos(radians)*39,58+math.sin(radians)*39)
            line(50,18,50,42)
            if kind == 'sunrise': line(43,25,50,18); line(57,25,50,18)
            else: line(43,35,50,42); line(57,35,50,42)
        elif kind in ('wind','fog'):
            if kind=='fog':
                for y,x in ((30,22),(45,12),(60,22),(75,12)): line(x,y,100-x,y)
            else:
                for y,end in ((32,74),(50,85),(68,63)):
                    path=QPainterPath(); path.moveTo(15,y); path.lineTo(end-8,y); path.cubicTo(end+14,y,end+14,y-20,end,y-20); p.drawPath(path)
        elif kind=='humidity':
            path=QPainterPath(); path.moveTo(50,13); path.cubicTo(42,30,23,48,23,63); path.cubicTo(23,96,77,96,77,63); path.cubicTo(77,48,58,30,50,13); p.drawPath(path)
        elif kind=='tornado':
            for y,x in ((22,15),(35,24),(48,33),(61,42),(74,50)): line(x,y,88-(y-22)/2,y)
        else:
            p.drawEllipse(QRectF(20,20,60,60)); path=QPainterPath(); path.moveTo(40,40); path.cubicTo(40,24,67,27,62,44); path.cubicTo(60,50,50,51,50,59); p.drawPath(path); p.drawEllipse(QRectF(48,68,4,4))


class QuietSidebar(QScrollArea):
    def __init__(self, parent=None, font_size=24):
        super().__init__(parent)
        self.font_size=font_size
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f'QScrollArea, QWidget#quietContent {{ background:{BACKGROUND}; border:0; }} QLabel {{ background:transparent; color:{PRIMARY}; border:0; }}')
        self.content=QWidget(); self.content.setObjectName('quietContent'); self.setWidget(self.content)
        self.layout=QVBoxLayout(self.content); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.labels=[]
        def label(text='', muted=False, wrap=False):
            l=QLabel(text); l.setTextFormat(Qt.TextFormat.PlainText); l.setWordWrap(wrap)
            l.setMinimumWidth(0); l.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            if muted: l.setStyleSheet(f'color:{SECONDARY};')
            self.labels.append(l); return l
        self.time_row=QHBoxLayout(); self.time_row.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignBaseline)
        self.clock_label=label(); self.period_label=label(muted=True)
        self.clock_label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        self.period_label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        self.time_row.addWidget(self.clock_label); self.time_row.addWidget(self.period_label)
        self.layout.addLayout(self.time_row)
        self.day_label=label(); self.date_label=label(muted=True,wrap=True)
        self.layout.addWidget(self.day_label); self.layout.addWidget(self.date_label)
        self.dividers=[]
        def divider():
            frame=QFrame(); frame.setFixedHeight(1); frame.setStyleSheet('background:#454645;'); self.dividers.append(frame)
            self.layout.addWidget(frame)
        divider()
        self.weather_panel=QWidget(); self.weather_layout=QVBoxLayout(self.weather_panel); self.weather_layout.setContentsMargins(0,0,0,0)
        self.location_label=label('MEDFORD AIRPORT',muted=True)
        self.weather_layout.addWidget(self.location_label)
        self.grid=QGridLayout(); self.grid.setColumnStretch(0,1); self.grid.setColumnStretch(1,1)
        self.icon=LineIcon(accent=False)
        self.temperature_label=label('—')
        self.condition_label=label('Waiting for weather',muted=True,wrap=True)
        self.feels_label=label('Feels like —',muted=True,wrap=True)
        self.grid.addWidget(self.icon,0,0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(self.temperature_label,0,1,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(self.condition_label,1,0,Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(self.feels_label,1,1,Qt.AlignmentFlag.AlignTop)
        self.weather_layout.addLayout(self.grid)
        self.detail_rows=[]
        self.detail_icons=[]
        for name,kind in [('Humidity','humidity'),('Wind','wind')]:
            row=QHBoxLayout(); icon=LineIcon(kind); title=label(name,muted=True); value=label('—',wrap=True)
            row.addWidget(icon); row.addWidget(title,1); row.addWidget(value,1)
            value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            self.weather_layout.addLayout(row); self.detail_rows.append((row,title,value)); self.detail_icons.append(icon)
        self.humidity_label=self.detail_rows[0][2]; self.wind_label=self.detail_rows[1][2]
        self.layout.addWidget(self.weather_panel)
        divider()
        self.solar_row=QHBoxLayout(); self.solar_icons=[]; self.solar_labels=[]; self.solar_titles=[]
        for title,kind in [('Sunrise','sunrise'),('Sunset','sunset')]:
            cell=QVBoxLayout(); header=QHBoxLayout(); icon=LineIcon(kind); heading=label(title,muted=True)
            header.addWidget(icon); header.addWidget(heading,1); cell.addLayout(header)
            value=label('—'); cell.addWidget(value); self.solar_row.addLayout(cell,1)
            self.solar_icons.append(icon); self.solar_labels.append(value); self.solar_titles.append(heading)
        self.layout.addLayout(self.solar_row)
        self.event_panel=NextSession(self.content)
        self.layout.addWidget(self.event_panel)
        self.source_label=label('NWS · KMFR',muted=True)
        self.status_label=label('Observation unavailable',muted=True,wrap=True)
        self.layout.addWidget(self.source_label); self.layout.addWidget(self.status_label)
        self.health_notice = HealthNotice(self.content)
        self.layout.addWidget(self.health_notice)
        self.layout.addStretch(1)
        self._summary={}; self._weather_lines=['']*7
        self.update_clock(); self.apply_metrics()

    def update_clock(self):
        now=datetime.now(MEDFORD_TIMEZONE)
        self.clock_label.setText(now.strftime('%I:%M').lstrip('0'))
        self.period_label.setText(now.strftime('%p'))
        self.day_label.setText(now.strftime('%A'))
        self.date_label.setText(f'{now.strftime("%B")} {now.day}, {now.year}')

    def set_weather(self, lines, summary=None, icon_hint=None):
        self._weather_lines=(lines+['']*7)[:7]; self._summary=summary or {}
        self.temperature_label.setText(lines[1] if lines[1] and 'unavailable' not in lines[1].lower() else '—')
        self.condition_label.setText(lines[2] or 'Conditions unavailable')
        self.feels_label.setText(lines[3].strip())
        self.feels_label.setVisible(bool(lines[3].strip()))
        humidity=self._summary.get('humidity'); speed=self._summary.get('wind_speed'); direction=self._summary.get('wind_direction')
        self.humidity_label.setText(f'{humidity:.0f}%' if isinstance(humidity,(int,float)) else 'Unavailable')
        wind=f'{speed:.0f} mph' if isinstance(speed,(int,float)) else 'Unavailable'
        if isinstance(direction,(int,float)):
            points=('N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW')
            wind+=' · '+points[int((direction%360)/22.5+.5)%16]
        self.wind_label.setText(wind)
        now=datetime.now(MEDFORD_TIMEZONE)
        sunrise=self._summary.get('sunrise'); sunset=self._summary.get('sunset')
        night=now.hour<7 or now.hour>=19
        if isinstance(sunrise,int) and isinstance(sunset,int): night=not sunrise<=now.timestamp()<sunset
        kind,night=weather_symbol(lines[2],icon_hint,night)
        self.icon.set_symbol(kind,night)
        for label,key in zip(self.solar_labels,('sunrise','sunset')):
            epoch=self._summary.get(key)
            label.setText(datetime.fromtimestamp(epoch,MEDFORD_TIMEZONE).strftime('%I:%M %p').lstrip('0') if isinstance(epoch,int) else 'Unavailable')
        status=lines[6] or 'Observation unavailable'
        self.status_label.setText(status.replace(' · Fetched','\nFetched').replace(' · Update failed','\nUpdate failed'))
        self.status_label.setStyleSheet(f'color:{AMBER if "STALE" in status or "failed" in status else SECONDARY};')
        self.weather_panel.setVisible(True)
        self.apply_metrics()

    def set_event_view(self, view):
        self.event_panel.set_view(view, getattr(self, "primary", PRIMARY),
                                  getattr(self, "secondary", SECONDARY), getattr(self, "brightness", None))
        self.apply_metrics()

    def set_health_issues(self, issues):
        self.health_notice.set_health(issues, getattr(self, "brightness", None))
        self.apply_metrics()

    def set_weather_enabled(self, enabled):
        for widget in (self.weather_panel, self.source_label, self.status_label,
                       *self.solar_icons, *self.solar_titles, *self.solar_labels,
                       *self.dividers):
            widget.setVisible(enabled)
        if self.event_panel.view and not hasattr(self, "brightness"):
            self.source_label.hide()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'labels'): self.apply_metrics()

    def apply_metrics(self):
        width=max(200,self.viewport().width()); height=max(300,self.viewport().height())
        scale=min(width/691,height/1080)*(max(8,self.font_size)/24)**.4
        scale=max(.48,min(1.7,scale))
        # Keep the requested typography, including enlarged solar times. Reserve
        # complete wrapped text height; unusually long descriptions can scroll.
        self._set_metrics(scale)
        self.layout.activate()
        self.content.setMinimumHeight(max(0,self.layout.totalHeightForWidth(width)))
        self.content.updateGeometry()

    def _set_metrics(self,scale):
        self.scale=scale
        compact=bool(self.event_panel.view)
        if compact:
            self.source_label.hide()
            status=self._weather_lines[6] or 'Observation unavailable'
            self.status_label.setText('NWS · KMFR · '+status.replace(' · Fetched','\nFetched').replace(' · Update failed','\nUpdate failed'))
        margin=round(46*scale); gap=max(4,round((3 if compact else 12)*scale))
        bottom = 6 if compact else 8 if self.health_notice.issues else 30
        self.layout.setContentsMargins(margin,round((12 if compact else 45)*scale),margin,round(bottom*scale)); self.layout.setSpacing(gap)
        self.weather_layout.setSpacing(round((4 if compact else 22)*scale)); self.grid.setHorizontalSpacing(round(24*scale)); self.grid.setVerticalSpacing(round((6 if compact else 10)*scale))
        self.time_row.setSpacing(round(12*scale)); self.solar_row.setSpacing(round(30*scale))
        def font(label,pixels,weight=QFont.Weight.Normal):
            f=QFont('DejaVu Sans'); f.setPixelSize(max(12,round(pixels*scale))); f.setWeight(weight); label.setFont(f)
        font(self.clock_label,108,QFont.Weight.Light); font(self.period_label,23)
        font(self.day_label,75); font(self.date_label,23)
        # Reserve a consistent weekday size that fits even the longest name.
        weekday_font=self.day_label.font()
        weekdays=('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
        weekday_width=max(1,self.viewport().width()-2*margin)
        while weekday_font.pixelSize()>12 and max(QFontMetrics(weekday_font).horizontalAdvance(day) for day in weekdays)>weekday_width:
            weekday_font.setPixelSize(weekday_font.pixelSize()-1)
        self.day_label.setFont(weekday_font)
        font(self.location_label,16,QFont.Weight.Medium)
        # Keep the entire temperature visible, even -123°F or a large font setting.
        column=max(60,(self.viewport().width()-2*margin-round(24*scale))/2)
        pixels=max(24,round(100*scale)); f=QFont('DejaVu Sans'); f.setWeight(QFont.Weight.Light)
        while pixels>12:
            f.setPixelSize(pixels)
            if QFontMetrics(f).horizontalAdvance(self.temperature_label.text())<=column: break
            pixels-=1
        self.temperature_label.setFont(f)
        self.icon.setFixedSize(round(pixels*1.22),round(pixels*1.22))
        font(self.condition_label,46); font(self.feels_label,21)
        for row,title,value in self.detail_rows:
            row.setSpacing(round(12*scale)); font(title,31.5); font(value,33)
        for icon in self.detail_icons: icon.setFixedSize(round(36*scale),round(36*scale))
        for icon in self.solar_icons: icon.setFixedSize(round(54*scale),round(54*scale))
        for heading in self.solar_titles: font(heading,36)
        solar_column = max(40, (self.viewport().width()-2*margin-round(30*scale))/2)
        for value in self.solar_labels:
            font(value,54)
            fitted = value.font()
            while fitted.pixelSize()>12 and QFontMetrics(fitted).horizontalAdvance(value.text())>solar_column:
                fitted.setPixelSize(fitted.pixelSize()-1)
            value.setFont(fitted)
        font(self.source_label,15); font(self.status_label,14)
        # QLabel/Grid height-for-width can otherwise underestimate long text
        # with an Ignored horizontal size policy. Reserve explicit wrapped height.
        def wrap_height(label, width):
            bounds=QFontMetrics(label.font()).boundingRect(
                QRect(0,0,max(1,int(width)),10000),int(Qt.TextFlag.TextWordWrap),label.text())
            label.setMinimumHeight(bounds.height()+4 if label.text() else 0)
        wrap_height(self.condition_label,column)
        wrap_height(self.feels_label,column)
        available=self.viewport().width()-2*margin
        self.health_notice.set_metrics(14*scale, available)
        self.event_panel.set_metrics(scale, available)
        wrap_height(self.date_label,available)
        wrap_height(self.status_label,available)
        detail_column=(available-round(36*scale)-2*round(12*scale))/2
        for _,_,value in self.detail_rows: wrap_height(value,detail_column)
        for frame in self.dividers:
            self.layout.setStretch(self.layout.indexOf(frame),0)
