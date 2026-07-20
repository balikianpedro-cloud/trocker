# src/modules/tracker_engine.py
# Pure processing logic — no UI dependencies.
# Adapted from Vaila's Tracker by Santiago Preto.

import os
import csv
import logging
import random
import time
import inspect

import cv2
import numpy as np
import requests
import torch

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
torch.set_num_threads(1)

for _logger in ("ultralytics", "ultralytics.yolo",
                "ultralytics.yolo.models", "ultralytics.yolo.utils"):
    logging.getLogger(_logger).setLevel(logging.ERROR)


# ── Constants ────────────────────────────────────────────────────────────────

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "models")

YOLO_MODELS = {
    "yolo11n.pt": None,   # already downloaded in project root — resolved at runtime
    "yolo11s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
    "yolo11m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
    "yolo11l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt",
    "yolo11x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt",
}

REID_URL = ("https://huggingface.co/paulosantiago/osnet_x0_25_msmt17"
            "/resolve/main/osnet_x0_25_msmt17.pt")

_rng = random.Random(42)
COLORS = [(_rng.randint(0, 255), _rng.randint(0, 255), _rng.randint(0, 255))
          for _ in range(1000)]


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_color(track_id: int) -> tuple:
    return COLORS[track_id % len(COLORS)]


def _clamp(v, lo, hi):
    return max(lo, min(v, hi))


def _validate_bbox(x1, y1, x2, y2, w, h):
    x1 = _clamp(x1, 0, w - 1)
    y1 = _clamp(y1, 0, h - 1)
    x2 = _clamp(x2, x1 + 1, w - 1)
    y2 = _clamp(y2, y1 + 1, h - 1)
    return x1, y1, x2, y2


def _validate_point(x, y, w, h):
    return _clamp(x, 0, w - 1), _clamp(y, 0, h - 1)


def _resolve_model_path(model_name: str) -> str:
    """Return the absolute path for a model, downloading if necessary."""
    os.makedirs(MODELS_DIR, exist_ok=True)

    # Check project root first (for yolo11n.pt pre-bundled)
    root_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        model_name,
    )
    if os.path.exists(root_path):
        return root_path

    model_path = os.path.join(MODELS_DIR, model_name)
    if os.path.exists(model_path):
        return model_path

    url = YOLO_MODELS.get(model_name)
    if url is None:
        raise FileNotFoundError(f"Model '{model_name}' not found and no download URL configured.")

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    with open(model_path, "wb") as f:
        f.write(resp.content)
    return model_path


def _resolve_reid_weights() -> str:
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, "osnet_x0_25_msmt17.pt")
    if not os.path.exists(path):
        resp = requests.get(REID_URL, timeout=120)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
    return path


def get_video_properties(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid dimensions {w}x{h}")
    return {"width": w, "height": h, "fps": fps, "frame_count": n}


def _select_codec(path: str, fps: float, w: int, h: int):
    """Try codecs in order; return (VideoWriter, actual_path)."""
    candidates = [("mp4v", ".mp4"), ("H264", ".mp4"), ("avc1", ".mp4"),
                  ("XVID", ".avi"), ("MJPG", ".avi")]
    base = os.path.splitext(path)[0]
    for codec, ext in candidates:
        out_path = base + ext
        fourcc   = cv2.VideoWriter_fourcc(*codec)
        writer   = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
        if writer.isOpened():
            return writer, out_path
        writer.release()
    raise RuntimeError("No compatible video codec found on this system.")


# ── CSV helpers ──────────────────────────────────────────────────────────────

def _write_csv_row(path: str, row: list):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow(row)


def _rewrite_header(path: str, header: list):
    """Read existing data rows, rewrite file with new header prepended."""
    try:
        with open(path, "r", newline="") as f:
            rows = list(csv.reader(f))[1:]          # skip old header
    except FileNotFoundError:
        rows = []
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _coords_header(ids):
    h = ["frame"]
    for pid in sorted(ids):
        h += [f"p{pid}_x", f"p{pid}_y"]
    return h


def _bboxes_header(ids):
    h = ["frame"]
    for pid in sorted(ids):
        h += [f"p{pid}_xmin", f"p{pid}_ymin", f"p{pid}_xmax", f"p{pid}_ymax"]
    return h


# ── Core: model + tracker init ───────────────────────────────────────────────

def initialize_yolo_and_tracker(model_name: str, tracker_name: str,
                                 config: dict, advanced_params: dict = None):
    """
    Returns (model, tracker).
    Raises on any failure — let the caller decide how to surface the error.
    """
    from ultralytics import YOLO
    from boxmot import BotSort, ByteTrack, StrongSort
    from pathlib import Path

    if advanced_params is None:
        advanced_params = {}

    def _filter(cls, params):
        allowed = set(inspect.signature(cls.__init__).parameters) - {"self"}
        return {k: v for k, v in params.items() if k in allowed}

    model_path = _resolve_model_path(model_name)
    model = YOLO(model_path)
    device = config.get("device", "cpu")
    model.to("cuda" if device == "cuda" and torch.cuda.is_available() else "cpu")

    if tracker_name == "bytetrack":
        params = {"track_buffer": 30, "match_thresh": 0.8}
        params.update(_filter(ByteTrack, advanced_params))
        tracker = ByteTrack(**params)

    elif tracker_name == "botsort":
        reid = Path(_resolve_reid_weights())
        # BoTSORT exige device como índice numérico ("0") ou "cpu", não "cuda"
        botsort_device = "0" if device == "cuda" else "cpu"
        params = {
            "reid_weights": reid,
            "device":       botsort_device,
            "half":         True,
        }
        params.update(_filter(BotSort, advanced_params))
        tracker = BotSort(**params)

    elif tracker_name == "strongsort":
        reid = Path(_resolve_reid_weights())
        # StrongSORT exige device como índice numérico ("0") ou "cpu", não "cuda"
        strongsort_device = "0" if device == "cuda" else "cpu"
        params = {
            "reid_weights": reid,
            "device":       strongsort_device,
            "half":         True,
            "max_cos_dist": 0.5,
            "max_iou_dist": 0.7,
            "max_age":      30,
            "n_init":       1,
            "nn_budget":    100,
        }
        # Mapeia parâmetros da interface para nomes do StrongSORT.
        # max_age vai direto em params (não passa por _filter porque é kwargs→BaseTracker).
        # match_thresh → max_iou_dist é parâmetro explícito, passa pelo _filter normalmente.
        if "track_buffer" in advanced_params:
            params["max_age"] = advanced_params.pop("track_buffer")
        if "match_thresh" in advanced_params:
            advanced_params["max_iou_dist"] = advanced_params.pop("match_thresh")
        params.update(_filter(StrongSort, advanced_params))
        tracker = StrongSort(**params)

    else:
        raise ValueError(f"Unknown tracker: {tracker_name}")

    return model, tracker


# ── Core: video processing ───────────────────────────────────────────────────

def process_video(video_path: str, model, tracker, config: dict,
                  progress_cb=None, status_cb=None) -> dict:
    """
    Run detection + tracking on *video_path*.

    progress_cb(int)   — called with 0‥100
    status_cb(str)     — called with human-readable status messages

    Returns dict with keys: video_path, csv_path, bboxes_csv_path
    """
    def _progress(v):
        if progress_cb:
            progress_cb(int(v))

    def _status(msg):
        if status_cb:
            status_cb(str(msg))

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    props = get_video_properties(video_path)
    W, H, fps = props["width"], props["height"], props["fps"]
    total = props["frame_count"]

    # ── Output paths ──────────────────────────────────────────────────────────
    proj_path = config.get("project_path")
    if proj_path:
        vid_dir    = os.path.join(proj_path, "videos")
        coords_dir = os.path.join(proj_path, "data", "pixel_coordinates")
        bboxes_dir = os.path.join(proj_path, "data", "bboxes")
    else:
        base       = config.get("output_path") or os.path.dirname(video_path)
        vid_dir    = base
        coords_dir = os.path.join(base, "data", "pixel_coordinates")
        bboxes_dir = os.path.join(base, "data", "bboxes")

    for d in (vid_dir, coords_dir, bboxes_dir):
        os.makedirs(d, exist_ok=True)

    out_video_base = os.path.join(vid_dir,    f"{video_name}_tracked")
    out_csv        = os.path.join(coords_dir, f"{video_name}_tracked.csv")
    out_bboxes     = os.path.join(bboxes_dir, f"{video_name}_bboxes.csv")

    # ── Video writer ──────────────────────────────────────────────────────────
    writer, out_video_path = _select_codec(out_video_base, fps, W, H)

    # ── CSV init ──────────────────────────────────────────────────────────────
    player_ids: set = set()
    _rewrite_header(out_csv,    _coords_header(player_ids))
    _rewrite_header(out_bboxes, _bboxes_header(player_ids))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        writer.release()
        raise RuntimeError(f"Cannot open video for reading: {video_path}")

    device     = config.get("device", "cpu")
    classes    = config.get("classes") or []
    coord_type = config.get("coord_type", "Center-Bottom")

    _progress(10)
    _status(f"Processing {W}x{H} @ {fps:.1f} fps …")

    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Resize if frame dimensions drifted (e.g. corrupt packets)
        if frame.shape[1] != W or frame.shape[0] != H:
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_LINEAR)

        # ── Detection ────────────────────────────────────────────────────────
        results = model(
            frame,
            device=device,
            conf=config.get("conf", 0.15),
            iou=config.get("iou", 0.50),
            imgsz=config.get("imgsz", 1280),
            verbose=False,
        )
        dets = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0].item())
                cls  = int(box.cls[0].item()) if box.cls is not None else 0
                if not classes or cls in classes:
                    dets.append([x1, y1, x2, y2, conf, cls])

        # ── Tracking ─────────────────────────────────────────────────────────
        tracked = tracker.update(np.array(dets), frame) if dets else []

        positions: dict = {}
        bboxes:    dict = {}
        new_ids_found = False

        for track in tracked:
            if len(track) < 5:
                continue
            tid = int(track[4])
            x1, y1, x2, y2 = map(int, track[:4])
            x1, y1, x2, y2 = _validate_bbox(x1, y1, x2, y2, W, H)

            bboxes[tid] = (x1, y1, x2, y2)

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2 if coord_type == "Center-Center" else y2
            cx, cy = _validate_point(cx, cy, W, H)
            positions[tid] = (cx, cy)

            if tid not in player_ids:
                player_ids.add(tid)
                new_ids_found = True

            color = get_color(tid)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"ID {tid}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Rewrite CSV headers only when a new ID appears
        if new_ids_found:
            _rewrite_header(out_csv,    _coords_header(player_ids))
            _rewrite_header(out_bboxes, _bboxes_header(player_ids))

        # Append this frame's data
        coord_row  = [frame_idx]
        bboxes_row = [frame_idx]
        for pid in sorted(player_ids):
            if pid in positions:
                coord_row  += list(positions[pid])
                bboxes_row += list(bboxes[pid])
            else:
                coord_row  += [None, None]
                bboxes_row += [None, None, None, None]
        _write_csv_row(out_csv,    coord_row)
        _write_csv_row(out_bboxes, bboxes_row)

        writer.write(frame)
        frame_idx += 1

        if frame_idx % 10 == 0:
            pct = 10 + int((frame_idx / total) * 80) if total > 0 else 50
            _progress(min(pct, 90))
            _status(f"Frame {frame_idx} — {len(tracked)} object(s) tracked")

    cap.release()
    writer.release()

    _progress(100)
    _status("Done.")

    return {
        "video_path":      out_video_path,
        "csv_path":        out_csv,
        "bboxes_csv_path": out_bboxes,
    }