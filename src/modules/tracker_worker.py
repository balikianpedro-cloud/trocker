# src/modules/tracker_worker.py
# QThread wrapper that runs tracker_engine.process_video in the background.

from PySide6.QtCore import QObject, QThread, Signal, Slot, Property
from .tracker_engine import initialize_yolo_and_tracker, process_video


class _Worker(QThread):
    """Internal thread — do not use directly."""

    progressChanged = Signal(int)
    statusChanged   = Signal(str)
    finished        = Signal(dict)   # result dict from process_video
    failed          = Signal(str)    # error message

    def __init__(self, config: dict, advanced_params: dict):
        super().__init__()
        self._config          = config
        self._advanced_params = advanced_params

    def run(self):
        try:
            model, tracker = initialize_yolo_and_tracker(
                model_name    = self._config["model_name"],
                tracker_name  = self._config["tracker_name"],
                config        = self._config,
                advanced_params = self._advanced_params,
            )
            result = process_video(
                video_path  = self._config["video_path"],
                model       = model,
                tracker     = tracker,
                config      = self._config,
                progress_cb = self.progressChanged.emit,
                status_cb   = self.statusChanged.emit,
            )
            self.finished.emit(result)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))


class TrackerWorker(QObject):
    """
    Exposed to QML as 'trackerWorker'.
    QML calls start() to begin processing; listens to signals for feedback.
    """

    # ── Signals ──────────────────────────────────────────────────────────────
    progressChanged = Signal(int,  arguments=["progress"])
    statusChanged   = Signal(str,  arguments=["status"])
    runningChanged  = Signal(bool, arguments=["running"])
    finished        = Signal(str,  arguments=["videoPath"])   # tracked video path
    failed          = Signal(str,  arguments=["error"])

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0
        self._status   = ""
        self._running  = False
        self._thread: _Worker | None = None

    # ── Properties ───────────────────────────────────────────────────────────
    @Property(int, notify=progressChanged)
    def progress(self):
        return self._progress

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(bool, notify=runningChanged)
    def running(self):
        return self._running

    # ── Slots (callable from QML) ────────────────────────────────────────────
    @Slot(str, str, str, float, float, str, int, str, "QVariantList", int, float, float, int, int)
    def start(self, video_path: str, model_name: str, tracker_name: str,
              conf: float, iou: float, device: str, vid_stride: int,
              coord_type: str, classes: list, track_buffer: int,
              match_thresh: float, max_cos_dist: float, n_init: int,
              imgsz: int):
        if self._running:
            return

        import os
        project_path = None
        parts = video_path.replace("\\", "/").split("/")
        if "videos" in parts:
            idx = parts.index("videos")
            project_path = "/".join(parts[:idx])

        config = {
            "video_path":   video_path,
            "project_path": project_path,
            "model_name":   model_name,
            "tracker_name": tracker_name,
            "conf":         conf,
            "iou":          iou,
            "device":       device,
            "vid_stride":   vid_stride,
            "coord_type":   coord_type,
            "classes":      [int(c) for c in classes] if classes else [],
            "imgsz":        imgsz,
        }

        advanced_params = {
            "track_buffer": track_buffer,
            "match_thresh": match_thresh,
            "max_cos_dist": max_cos_dist,
            "n_init":       n_init,
        }

        self._thread = _Worker(config=config, advanced_params=advanced_params)
        self._thread.progressChanged.connect(self._on_progress)
        self._thread.statusChanged.connect(self._on_status)
        self._thread.finished.connect(self._on_finished)
        self._thread.failed.connect(self._on_failed)

        self._set_running(True)
        self._thread.start()

    @Slot()
    def cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
            self._thread.wait()
        self._set_running(False)
        self._on_status("Cancelled.")

    # ── Internal ─────────────────────────────────────────────────────────────
    def _set_running(self, val: bool):
        if self._running != val:
            self._running = val
            self.runningChanged.emit(val)

    def _on_progress(self, v: int):
        self._progress = v
        self.progressChanged.emit(v)

    def _on_status(self, msg: str):
        self._status = msg
        self.statusChanged.emit(msg)

    def _on_finished(self, result: dict):
        self._set_running(False)
        self.finished.emit(result.get("video_path", ""))

    def _on_failed(self, err: str):
        self._set_running(False)
        self.failed.emit(err)
