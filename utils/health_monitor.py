"""Debounced status aggregation and bounded, non-blocking system probes."""
import atexit
import json
import logging
from pathlib import Path
import sys
import time

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal, pyqtSlot
from .health_probe import EXPECTED_PHOTO_MOUNT

log = logging.getLogger(__name__)
CHECK_INTERVAL_MS = 30000
PROBE_TIMEOUT_MS = 6000
CONFIRM_FAILURES = 2
# Jobs outlive a closing window only until their killed child has been reaped.
# Strong ownership prevents garbage collection of callbacks during Qt teardown.
_ACTIVE_PROBES = set()


def _shutdown_probes():
    # Only interpreter shutdown may briefly wait to reap an already-killed child.
    # Normal UI checks and window closes remain entirely asynchronous.
    for job in list(_ACTIVE_PROBES):
        try:
            job.cancel()
            job.process.waitForFinished(100)
        except RuntimeError:
            pass  # Qt may already have deleted an object during app teardown.


atexit.register(_shutdown_probes)


class HealthState:
    def __init__(self):
        self.failures = {}
        self.issues = {}

    def record(self, key, ok, message=''):
        if ok is None:
            return  # Startup/pending is not a confirmed failure.
        if ok:
            self.failures[key] = 0
            self.issues.pop(key, None)
        else:
            self.failures[key] = min(CONFIRM_FAILURES, self.failures.get(key, 0) + 1)
            if self.failures[key] >= CONFIRM_FAILURES:
                self.issues[key] = message

    def messages(self):
        return tuple(self.issues[key] for key in ('share', 'weather', 'bot') if key in self.issues)


class ProbeJob(QObject):
    resultReady = pyqtSignal(str, bool, str)
    reaped = pyqtSignal(str)

    def __init__(self, key, arguments):
        super().__init__()  # Never destroy a running QProcess with its window.
        self.key, self.arguments = key, arguments
        self.done = False
        self.cleaned = False
        self.process = QProcess(self)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.process.finished.connect(self._completed)
        self.process.errorOccurred.connect(self._error)
        self.deadline.timeout.connect(self._timeout)
        _ACTIVE_PROBES.add(self)

    def start(self):
        probe = str(Path(__file__).with_name('health_probe.py'))
        self.process.start(sys.executable, [probe, self.key, *self.arguments])
        self.deadline.start(PROBE_TIMEOUT_MS)

    def _failure_message(self):
        return 'Photo share check failed' if self.key == 'share' else 'Photo bot service status unavailable'

    def _finish(self, ok, message):
        if not self.done:
            self.done = True
            self.deadline.stop()
            self.resultReady.emit(self.key, ok, message)
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._cleanup()
        else:
            self.process.kill()

    def _completed(self, code, status):
        if self.done:
            self._cleanup()
            return
        try:
            data = json.loads(bytes(self.process.readAllStandardOutput()).decode())
            if code != 0 or status != QProcess.ExitStatus.NormalExit or type(data['ok']) is not bool:
                raise ValueError('Invalid probe result')
            self._finish(data['ok'], str(data['message']))
        except (ValueError, KeyError, TypeError):
            self._finish(False, self._failure_message())

    def _error(self, error):
        self._finish(False, self._failure_message())

    def _timeout(self):
        self._finish(False, 'Photo share check timed out' if self.key == 'share'
                     else 'Photo bot service status unavailable')

    @pyqtSlot()
    def cancel(self):
        self.done = True
        self.deadline.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._cleanup()
        else:
            self.process.kill()

    def _cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        self.reaped.emit(self.key)
        _ACTIVE_PROBES.discard(self)
        self.deleteLater()


class HealthMonitor(QObject):
    issuesChanged = pyqtSignal(tuple)

    def __init__(self, folders, weather_check, parent=None):
        super().__init__(parent)
        self.folders = list(folders)
        self.weather_check = weather_check
        self.state = HealthState()
        self.started_at = time.monotonic()
        self._processes = {}
        self._published = ()
        self._stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        QTimer.singleShot(0, self.check)

    def check(self):
        if self._stopped:
            return
        ok, message = self.weather_check(time.monotonic() - self.started_at)
        self.record('weather', ok, message)
        self._start_probe('share', [str(EXPECTED_PHOTO_MOUNT), *self.folders])
        self._start_probe('bot', [])

    def record(self, key, ok, message=''):
        if self._stopped:
            return
        self.state.record(key, ok, message)
        messages = self.state.messages()
        if messages != self._published:
            log.info('Viewer health: %s', '; '.join(messages) if messages else 'recovered')
            self._published = messages
            self.issuesChanged.emit(messages)

    def _start_probe(self, key, arguments):
        if key in self._processes:
            return
        job = ProbeJob(key, arguments)
        self._processes[key] = job
        job.resultReady.connect(self.record)
        job.reaped.connect(self._probe_reaped)
        self.destroyed.connect(job.cancel)
        job.start()

    @pyqtSlot(str)
    def _probe_reaped(self, key):
        self._processes.pop(key, None)

    def stop(self):
        self._stopped = True
        self.timer.stop()
        for job in list(self._processes.values()):
            job.cancel()
