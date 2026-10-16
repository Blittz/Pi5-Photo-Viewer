"""Read-only, nonblocking polling of the bot's private atomic event snapshot."""
from pathlib import Path
import json
import sys
from PyQt6.QtCore import QObject,QTimer,QProcess,pyqtSignal,pyqtSlot
from .health_monitor import ProbeJob
from .scheduled_events import EVENTS_FILE,validate_snapshot


class EventReadJob(ProbeJob):
    snapshotReady=pyqtSignal(dict)

    def __init__(self,path):
        super().__init__('events',[])
        self.path=Path(path)

    def start(self):
        # -m resolves the project's utils package using the normal viewer cwd.
        self.process.start(sys.executable,['-B','-m','utils.scheduled_events',str(self.path)])
        self.deadline.start(4000)

    def _failure_message(self):return 'Event data unavailable'

    def _timeout(self):self._finish(False,'Event data unavailable')

    def _completed(self,code,status):
        if self.done:
            self._cleanup();return
        try:
            if code!=0 or status!=QProcess.ExitStatus.NormalExit:raise ValueError('Read failed')
            # Worker validated the wire format; retain its sanitized representation.
            data=validate_snapshot(json.loads(bytes(self.process.readAllStandardOutput()).decode()))
            # Worker output must still have the bounded, expected shape.
            if not isinstance(data,dict) or data.get('schema_version')!=1:raise ValueError('Invalid data')
            self.snapshotReady.emit(data)
            self._finish(True,'')
        except (ValueError,KeyError,TypeError):self._finish(False,'Event data unavailable')


class EventClient(QObject):
    changed=pyqtSignal()

    def __init__(self,parent=None,path=EVENTS_FILE):
        super().__init__(parent)
        self.path=path;self.snapshot=None;self.read_failed=False
        self.job=None;self.stopped=False
        self.timer=QTimer(self);self.timer.setInterval(30000);self.timer.timeout.connect(self.refresh)
        self.timer.start();QTimer.singleShot(0,self.refresh)

    def refresh(self):
        if self.stopped or self.job is not None:return
        job=EventReadJob(self.path);self.job=job
        job.snapshotReady.connect(self._accept)
        job.resultReady.connect(self._result)
        job.reaped.connect(self._reaped)
        self.destroyed.connect(job.cancel)
        job.start()

    @pyqtSlot(dict)
    def _accept(self,data):
        if self.stopped:return
        self.snapshot=data;self.read_failed=False;self.changed.emit()

    @pyqtSlot(str,bool,str)
    def _result(self,key,ok,message):
        if not ok and not self.stopped:
            self.read_failed=True;self.changed.emit()

    @pyqtSlot(str)
    def _reaped(self,key):self.job=None

    def stop(self):
        self.stopped=True;self.timer.stop()
        if self.job is not None:self.job.cancel()
