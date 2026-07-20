import sys
import os
import cv2
import numpy as np
import pandas as pd
import glob

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QFileDialog, QMessageBox, QGraphicsView, QGraphicsScene,
    QApplication, QDialog, QButtonGroup, QRadioButton, QGraphicsRectItem,
    QGraphicsTextItem, QSpinBox, QLineEdit
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont, QBrush

from .reid import run_reid, _DARK_SS
from .player_io import players_json_path, load_player_names, save_player_names


# =============================================================================
# HELPERS
# =============================================================================

def _find_csv_for_video(video_path: str, project_path: str):
    """
    Resolve o CSV de pixel_coordinates para um vídeo, independente de o
    video_path ser o original ou o _tracked.mp4.

    Retorna lista de dicts {'label', 'path'} em ordem de prioridade,
    para o chamador decidir se mostra diálogo ou carrega direto.
    """
    pixel_dir = os.path.join(project_path, "data", "pixel_coordinates")
    bboxes_dir = os.path.join(project_path, "data", "bboxes")

    if not os.path.isdir(pixel_dir):
        return []

    stem = os.path.splitext(os.path.basename(video_path))[0]
    # Remove sufixo _tracked duplicado
    base = stem[:-8] if stem.endswith("_tracked") else stem

    options = []

    # Candidatos ordenados por prioridade
    candidates = [
        (f"{base}_tracked.csv",         "Tracked coordinates"),
        (f"{base}_field_keypoints.csv",  "Field keypoints"),
        (f"{stem}_tracked.csv",          "Tracked coordinates"),
        (f"{stem}_field_keypoints.csv",  "Field keypoints"),
    ]
    seen = set()
    for filename, label in candidates:
        path = os.path.join(pixel_dir, filename)
        if path not in seen and os.path.isfile(path):
            seen.add(path)
            # Bbox correspondente (só para tracked, não keypoints)
            bbox_path = None
            if "_tracked" in filename:
                bp = os.path.join(bboxes_dir, filename.replace("_tracked.csv", "_bboxes.csv"))
                if os.path.isfile(bp):
                    bbox_path = bp
            options.append({"label": label, "filename": filename,
                            "path": path, "bboxes_path": bbox_path,
                            "is_field_keypoints": "field_keypoints" in filename})

    # Fallback fuzzy: qualquer CSV que comece com o base
    if not options:
        try:
            for f in sorted(os.listdir(pixel_dir)):
                if f.endswith(".csv") and f.startswith(base):
                    path = os.path.join(pixel_dir, f)
                    if path not in seen:
                        seen.add(path)
                        options.append({"label": f, "filename": f, "path": path,
                                        "bboxes_path": None, "is_field_keypoints": False})
        except OSError:
            pass

    return options


def _read_csv_robust(path):
    """Lê CSV com tratamento de erros padronizado."""
    return pd.read_csv(path, engine="python", on_bad_lines="skip", encoding="utf-8")


# =============================================================================
# CSV SELECTION DIALOG
# =============================================================================

class CSVSelectionDialog(QDialog):
    def __init__(self, csv_options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select CSV File")
        self.setFixedSize(450, 200)
        self.setModal(True)
        self.csv_options = csv_options
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title = QLabel("Please select which CSV file to load:")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #EEEEF8;")
        layout.addWidget(title)

        self.button_group = QButtonGroup(self)
        for opt in self.csv_options:
            btn = QRadioButton(f"{opt['label']}: {opt['filename']}")
            btn.setProperty("csv_path", opt["path"])
            btn.setProperty("bboxes_path", opt.get("bboxes_path"))
            btn.setStyleSheet("QRadioButton { font-size: 12px; padding: 8px; color: #A0A0C0; }"
                              "QRadioButton:hover { background-color: #1D1D2C; color: #EEEEF8; border-radius: 4px; }")
            self.button_group.addButton(btn)
            layout.addWidget(btn)

        if self.button_group.buttons():
            self.button_group.buttons()[0].setChecked(True)

        layout.addStretch()

        btn_style = """
            QPushButton {
                background-color: #1D1D2C; border: 1px solid #222230; color: #A0A0C0;
                border-radius: 8px; font-weight: bold; font-size: 13px;
                padding: 8px 16px; min-width: 80px;
            }
            QPushButton:hover { background-color: #242438; color: #EEEEF8; border-color: #303050; }
            QPushButton:pressed { background-color: #13213F; color: #C0D8FF; }
        """
        row = QHBoxLayout()
        row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(btn_style)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(btn_style)
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

    def get_selected_option(self):
        btn = self.button_group.checkedButton()
        if btn:
            return {"path": btn.property("csv_path"),
                    "bboxes_path": btn.property("bboxes_path")}
        return None


# =============================================================================
# MAIN WINDOW
# =============================================================================

class GetPixelCoordWindow(QMainWindow):
    data_updated = Signal()

    def __init__(self, video_path=None, project_path=None):
        super().__init__()
        self.setWindowTitle("Get Pixel Coord")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(_DARK_SS)

        self.video_path    = video_path
        self.project_path  = project_path
        self.csv_path      = None
        self.bbox_csv_path = None
        self.cap           = None
        self.total_frames  = 0
        self.fps           = 0
        self.current_frame = 0
        self.markers       = {}   # {frame: [(x, y) | (None, None), ...]}
        self.bboxes        = {}   # {frame: [(xmin, ymin, xmax, ymax) | (None,…), ...]}
        self.selected_marker = 0
        self.zoom            = 1.0
        self.zoom_center     = None   # persiste centro do zoom entre frames
        self.marker_count    = 0
        self.marker_numbers  = []
        self.player_names    = {}
        self._playing        = False
        self._play_timer     = QTimer()
        self._play_timer.timeout.connect(self._play_tick)
        self._pan_start      = None   # middle-mouse-drag panning

        self._init_ui()

        if self.project_path:
            self._load_files_from_project()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top bar: status + controls ────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: #161621; border-bottom: 1px solid #222230;")
        top_bar.setFixedHeight(82)
        top_bar_layout = QVBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(12, 6, 12, 6)
        top_bar_layout.setSpacing(4)

        lbl_style_dim = "color: #6868A0; font-style: italic; font-size: 11px;"
        self.video_status_label = QLabel("No video loaded")
        self.video_status_label.setStyleSheet(lbl_style_dim)
        top_bar_layout.addWidget(self.video_status_label)

        self.csv_status_label = QLabel("No CSV file loaded")
        self.csv_status_label.setStyleSheet(lbl_style_dim)
        top_bar_layout.addWidget(self.csv_status_label)

        main_layout.addWidget(top_bar)

        # ── Toolbar: action buttons ───────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #161621; border-bottom: 1px solid #222230;")
        toolbar.setFixedHeight(44)
        controls = QHBoxLayout(toolbar)
        controls.setContentsMargins(8, 4, 8, 4)
        controls.setSpacing(4)

        for attr, label, tooltip, role, slot in [
            ("btn_reid",         "Graphic ReID",  "Open Advanced Re-Identification Tool", "primary", self.open_reid),
            ("btn_sort_markers", "Sort Markers",  "",                                     "",        self.sort_markers),
            ("btn_cycle_up",     "Marker ↑",      "Next marker (Tab)",                   "",        self.cycle_marker),
            ("btn_cycle_down",   "Marker ↓",      "Prev marker (Shift+Tab)",             "",        self.cycle_marker_down),
            ("btn_save_csv",     "Save",          "",                                     "success", self.save_csv),
            ("btn_edit_names",   "Edit Names",    "Renomear markers",                     "",        self.open_name_editor),
            ("btn_help",         "Help",          "",                                     "",        self.show_help),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            if role:
                btn.setProperty("role", role)
            btn.clicked.connect(slot)
            setattr(self, attr, btn)
            controls.addWidget(btn)

        controls.addStretch()

        self.btn_play = QPushButton("▶  Play")
        self.btn_play.setToolTip("Play/Pause (Space)")
        self.btn_play.setProperty("role", "primary")
        self.btn_play.clicked.connect(self.toggle_play)
        controls.addWidget(self.btn_play)

        main_layout.addWidget(toolbar)

        # ── HUD bar: active marker info (outside video, never hidden by zoom) ─
        hud_bar = QWidget()
        hud_bar.setStyleSheet(
            "background-color: #0D0D14; border-bottom: 1px solid #222230;")
        hud_bar.setFixedHeight(34)
        hud_layout = QHBoxLayout(hud_bar)
        hud_layout.setContentsMargins(14, 0, 14, 0)
        hud_layout.setSpacing(12)

        self.hud_marker_label = QLabel("—")
        self.hud_marker_label.setStyleSheet(
            "color: #FFD700; font-size: 14px; font-weight: bold;")
        hud_layout.addWidget(self.hud_marker_label)

        self.hud_sub_label = QLabel("No markers loaded")
        self.hud_sub_label.setStyleSheet("color: #6868A0; font-size: 10px;")
        hud_layout.addWidget(self.hud_sub_label)

        hud_layout.addStretch()
        hud_layout.addWidget(QLabel("Middle-click + drag to pan"))
        main_layout.addWidget(hud_bar)

        # ── Video display ─────────────────────────────────────────────────────
        self.graphics_view = QGraphicsView()
        self.graphics_scene = QGraphicsScene()
        self.graphics_view.setScene(self.graphics_scene)
        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graphics_view.setMouseTracking(True)
        self.graphics_view.setFrameShape(self.graphics_view.Shape.NoFrame)
        main_layout.addWidget(self.graphics_view, stretch=1)

        # ── Bottom nav: slider + frame spinbox + info ─────────────────────────
        nav_bar = QWidget()
        nav_bar.setStyleSheet("background-color: #161621; border-top: 1px solid #222230;")
        nav_bar.setFixedHeight(38)
        nav = QHBoxLayout(nav_bar)
        nav.setContentsMargins(10, 4, 10, 4)
        nav.setSpacing(8)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider_changed)
        nav.addWidget(self.slider)

        frame_lbl = QLabel("Frame:")
        frame_lbl.setStyleSheet("color: #6868A0; font-size: 11px;")
        nav.addWidget(frame_lbl)

        self.frame_spin = QSpinBox()
        self.frame_spin.setMinimum(1)
        self.frame_spin.setMaximum(1)
        self.frame_spin.setFixedWidth(75)
        self.frame_spin.valueChanged.connect(self._on_frame_spin_changed)
        nav.addWidget(self.frame_spin)

        self.lbl_marker_info = QLabel("Marker: 0/0 | Frame: (0/0)")
        self.lbl_marker_info.setStyleSheet("color: #6868A0; font-size: 11px; margin-left: 8px;")
        nav.addWidget(self.lbl_marker_info)
        main_layout.addWidget(nav_bar)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.graphics_view.viewport().installEventFilter(self)

    # ── Project loading ───────────────────────────────────────────────────────

    def _load_files_from_project(self):
        if not self.project_path:
            return

        # Vídeo
        if self.video_path and os.path.exists(self.video_path):
            self._load_video_from_path(self.video_path)
        else:
            self.video_status_label.setText("No video loaded")

        # CSV
        options = _find_csv_for_video(self.video_path or "", self.project_path)

        if not options:
            self.csv_status_label.setText("No CSV files found — run Tracker first")
        elif len(options) == 1:
            self._import_csv_from_path(options[0]["path"])
        else:
            dialog = CSVSelectionDialog(options, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                sel = dialog.get_selected_option()
                if sel:
                    self._import_csv_from_path(sel["path"])
            else:
                self.csv_status_label.setText("No CSV file selected")

        self._load_bounding_box_csv()

    # ── Video ─────────────────────────────────────────────────────────────────

    def _load_video_from_path(self, path):
        self.video_path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            self.video_status_label.setText("Error: failed to open video")
            QMessageBox.critical(self, "Error", "Failed to open video.")
            return

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.slider.setMaximum(self.total_frames - 1)
        self.slider.setEnabled(True)
        self.frame_spin.setMaximum(self.total_frames)
        self.current_frame = 0
        self.zoom_center = None
        self.markers = {i: [] for i in range(self.total_frames)}

        self.video_status_label.setText(f"Video loaded: {os.path.basename(path)}")
        self.video_status_label.setStyleSheet("color: #2DD480; font-weight: bold; font-size: 11px;")
        self._update_video_frame()

    # ── CSV import ────────────────────────────────────────────────────────────

    def _import_csv_from_path(self, path):
        self.csv_path = path
        try:
            df = _read_csv_robust(path)
            self.markers = {i: [] for i in range(self.total_frames)}

            nums = sorted({int(c[1:-2]) for c in df.columns
                           if c.startswith("p") and (c.endswith("_x") or c.endswith("_y"))})
            self.marker_numbers = nums
            self.marker_count   = len(nums)

            for _, row in df.iterrows():
                frame = int(row["frame"])
                self.markers[frame] = [
                    (None, None) if pd.isna(row.get(f"p{n}_x")) or pd.isna(row.get(f"p{n}_y"))
                    else (float(row[f"p{n}_x"]), float(row[f"p{n}_y"]))
                    for n in nums
                ]

            self.csv_status_label.setText(f"CSV loaded: {os.path.basename(path)}")
            self.csv_status_label.setStyleSheet("color: #2DD480; font-weight: bold; font-size: 11px;")
            self._update_video_frame()
            self._load_player_names()

        except Exception as e:
            msg = f"Failed to load CSV: {e}"
            self.csv_status_label.setText(msg)
            QMessageBox.critical(self, "Error", msg)

    # ── Bounding boxes ────────────────────────────────────────────────────────

    def _load_bounding_box_csv(self):
        self.bboxes = {}
        self.bbox_csv_path = None
        if not self.project_path or not self.video_path:
            return

        stem = os.path.splitext(os.path.basename(self.video_path))[0]
        base = stem[:-8] if stem.endswith("_tracked") else stem
        bbox_path = os.path.join(self.project_path, "data", "bboxes", f"{base}_bboxes.csv")
        if not os.path.isfile(bbox_path):
            return

        try:
            df = _read_csv_robust(bbox_path)
            self.bbox_csv_path = bbox_path
            self.bboxes = {i: [] for i in range(self.total_frames)}

            nums = sorted({int(c[1:-5]) for c in df.columns
                           if c.startswith("p") and c.endswith("_xmin")})

            for _, row in df.iterrows():
                frame = int(row["frame"])
                if frame >= self.total_frames:
                    continue
                self.bboxes[frame] = [
                    (None, None, None, None)
                    if any(pd.isna(row.get(f"p{n}_{s}")) for s in ("xmin", "ymin", "xmax", "ymax"))
                    else tuple(float(row[f"p{n}_{s}"]) for s in ("xmin", "ymin", "xmax", "ymax"))
                    for n in nums
                ]
        except Exception as e:
            print(f"Warning: could not load bounding box CSV: {e}")

    # ── Player names ──────────────────────────────────────────────────────────

    def _players_json_path(self):
        return players_json_path(self.project_path, self.video_path)

    def _load_player_names(self):
        names = load_player_names(self.project_path, self.video_path)
        if names:
            self.player_names = names

    def _save_player_names(self):
        save_player_names(self.project_path, self.video_path, self.player_names)

    # ── ReID integration ──────────────────────────────────────────────────────

    def open_reid(self):
        if not self.project_path:
            QMessageBox.information(self, "No Project",
                "REID requires a project context. Open from a project.")
            return
        if not self.video_path:
            QMessageBox.information(self, "No Video",
                "No video selected. Activate a video first.")
            return

        current_df      = self._markers_to_dataframe() if self.marker_numbers else None
        current_bboxes  = self._bboxes_to_dataframe()  if self.bboxes        else None

        self.reid_window = run_reid(
            video_path=self.video_path,
            project_path=self.project_path,
            current_data=current_df,
            original_csv_path=self.csv_path,
            current_bboxes_data=current_bboxes,
        )
        self.reid_window.data_ready.connect(self._receive_reid_data)
        self.reid_window.show()

    def _receive_reid_data(self, df, bboxes_df):
        try:
            self._dataframe_to_markers(df)
            if bboxes_df is not None:
                self._dataframe_to_bboxes(bboxes_df)
            self._update_video_frame()
            bbox_txt = " and bounding boxes" if self.bboxes else ""
            self.csv_status_label.setText(
                f"✓ Data updated from REID ({len(self.marker_numbers)} markers{bbox_txt})")
            self.csv_status_label.setStyleSheet("color: #2196F3; font-weight: bold; margin: 5px 0;")
        except Exception as e:
            QMessageBox.warning(self, "Data Update Error", f"Could not update data from REID: {e}")

    # ── Save ──────────────────────────────────────────────────────────────────

    def save_csv(self):
        if not self.markers:
            QMessageBox.warning(self, "No Data", "No marker data to save.")
            return

        if self.project_path and self.csv_path:
            try:
                self._save_csv_to_path(self.csv_path)
                if hasattr(self, "old_marker_numbers"):
                    self._save_sorted_bounding_box_csv()
                    delattr(self, "old_marker_numbers")
                QMessageBox.information(self, "Saved", f"Saved to: {self.csv_path}")
                self.data_updated.emit()
                return
            except Exception as e:
                QMessageBox.warning(self, "Save Error", f"Could not save to project: {e}")

        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                self._save_csv_to_path(path)
                if hasattr(self, "old_marker_numbers"):
                    self._save_sorted_bounding_box_csv()
                    delattr(self, "old_marker_numbers")
                QMessageBox.information(self, "Saved", f"CSV saved to: {path}")
                self.data_updated.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error saving file: {e}")

    def _save_csv_to_path(self, path):
        nums = self.marker_numbers or list(range(1, self.marker_count + 1))
        cols = ["frame"] + [f"p{n}_{c}" for n in nums for c in ("x", "y")]
        data = []
        for frame, pts in self.markers.items():
            row = [frame]
            for i in range(len(nums)):
                if i < len(pts) and pts[i][0] is not None:
                    row += [pts[i][0], pts[i][1]]
                else:
                    row += ["", ""]
            data.append(row)
        pd.DataFrame(data, columns=cols).to_csv(path, index=False)

    def _save_sorted_bounding_box_csv(self):
        if not self.project_path or not self.video_path or not self.bboxes:
            return
        stem = os.path.splitext(os.path.basename(self.video_path))[0]
        base = stem[:-8] if stem.endswith("_tracked") else stem
        bbox_path = os.path.join(self.project_path, "data", "bboxes", f"{base}_bboxes.csv")
        if not os.path.exists(bbox_path):
            return
        try:
            df = self._bboxes_to_dataframe()
            if df is not None:
                df.to_csv(bbox_path, index=False)
        except Exception as e:
            print(f"Warning: could not save bounding box CSV: {e}")

    # ── Data conversion helpers ───────────────────────────────────────────────

    def _markers_to_dataframe(self):
        if not self.marker_numbers or self.total_frames <= 0:
            return None
        nums = self.marker_numbers
        cols = ["frame"] + [f"p{n}_{c}" for n in nums for c in ("x", "y")]
        data = []
        for frame in range(self.total_frames):
            row = [frame]
            pts = self.markers.get(frame, [])
            for i, n in enumerate(nums):
                if i < len(pts) and pts[i][0] is not None:
                    row += [float(pts[i][0]), float(pts[i][1])]
                else:
                    row += [np.nan, np.nan]
            data.append(row)
        return pd.DataFrame(data, columns=cols)

    def _dataframe_to_markers(self, df):
        nums = sorted({int(c[1:-2]) for c in df.columns
                       if c.startswith("p") and c.endswith("_x")})
        self.marker_numbers = nums
        self.marker_count   = len(nums)
        self.markers = {i: [] for i in range(self.total_frames)}
        for _, row in df.iterrows():
            frame = int(row["frame"])
            if frame >= self.total_frames:
                continue
            self.markers[frame] = [
                (None, None) if pd.isna(row.get(f"p{n}_x")) or pd.isna(row.get(f"p{n}_y"))
                else (float(row[f"p{n}_x"]), float(row[f"p{n}_y"]))
                for n in nums
            ]

    def _bboxes_to_dataframe(self):
        if not self.marker_numbers or self.total_frames <= 0 or not self.bboxes:
            return None
        nums = self.marker_numbers
        cols = ["frame"] + [f"p{n}_{s}" for n in nums
                            for s in ("xmin", "ymin", "xmax", "ymax")]
        data = []
        for frame in range(self.total_frames):
            row  = [frame]
            bbs  = self.bboxes.get(frame, [])
            for i, n in enumerate(nums):
                if i < len(bbs) and bbs[i][0] is not None:
                    row += [float(v) for v in bbs[i]]
                else:
                    row += [np.nan] * 4
            data.append(row)
        return pd.DataFrame(data, columns=cols)

    def _dataframe_to_bboxes(self, df):
        nums = sorted({int(c[1:-5]) for c in df.columns
                       if c.startswith("p") and c.endswith("_xmin")})
        self.bboxes = {i: [] for i in range(self.total_frames)}
        for _, row in df.iterrows():
            frame = int(row["frame"])
            if frame >= self.total_frames:
                continue
            self.bboxes[frame] = [
                (None, None, None, None)
                if any(pd.isna(row.get(f"p{n}_{s}")) for s in ("xmin", "ymin", "xmax", "ymax"))
                else tuple(float(row[f"p{n}_{s}"]) for s in ("xmin", "ymin", "xmax", "ymax"))
                for n in nums
            ]

    # ── Video rendering ───────────────────────────────────────────────────────

    def _update_video_frame(self):
        if not self.cap or not self.cap.isOpened():
            return

        # Preserva pan entre frames
        if self.graphics_scene.items():
            self.zoom_center = self.graphics_view.mapToScene(
                self.graphics_view.viewport().rect().center())

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if not ret:
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch  = frame_rgb.shape
        qimg      = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap    = QPixmap.fromImage(qimg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pts = self.markers.get(self.current_frame, [])
        for idx, (x, y) in enumerate(pts):
            if x is None:
                continue
            is_selected = idx == self.selected_marker

            if is_selected:
                # Halo externo amarelo para destacar marker ativo
                painter.setPen(QPen(QColor(255, 215, 0, 180), 3))
                painter.setBrush(QColor(255, 215, 0, 60))
                painter.drawEllipse(QPointF(x, y), 10, 10)
                # Ponto central sólido
                painter.setPen(QPen(QColor(255, 215, 0), 2))
                painter.setBrush(QColor(255, 215, 0))
                painter.drawEllipse(QPointF(x, y), 5, 5)
            else:
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.setBrush(QColor(0, 255, 0, 200))
                painter.drawEllipse(QPointF(x, y), 4, 4)

            # Label do marker
            mid = self.marker_numbers[idx] if (
                self.marker_numbers and idx < len(self.marker_numbers)) else idx + 1
            label = self.player_names.get(mid, str(mid))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            # Sombra do texto
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QPointF(x + 9, y + 5), label)
            # Texto principal
            color = QColor(255, 215, 0) if is_selected else QColor(0, 255, 0)
            painter.setPen(QPen(color))
            painter.drawText(QPointF(x + 8, y + 4), label)

        painter.end()

        self.graphics_scene.clear()
        self.graphics_scene.addPixmap(pixmap)

        self._update_hud_label()
        self._apply_zoom(self.zoom, self.zoom_center)

        # Sincroniza slider e frame_spin sem loop
        self.slider.blockSignals(True)
        self.frame_spin.blockSignals(True)
        self.slider.setValue(self.current_frame)
        self.frame_spin.setValue(self.current_frame + 1)
        self.slider.blockSignals(False)
        self.frame_spin.blockSignals(False)

        n_val = self.marker_numbers[self.selected_marker] if (
            self.marker_numbers and 0 <= self.selected_marker < len(self.marker_numbers)) else None
        n_txt = f" [ID: {n_val}]" if n_val is not None else ""
        self.lbl_marker_info.setText(
            f"Marker: ({self.selected_marker + 1}/{self.marker_count}){n_txt} "
            f"| Frame: ({self.current_frame + 1}/{self.total_frames})")

    def _update_hud_label(self):
        """Atualiza a barra HUD acima do vídeo com o marker ativo."""
        if self.marker_count == 0:
            self.hud_marker_label.setText("—")
            self.hud_sub_label.setText("No markers loaded")
            return
        n_val = self.marker_numbers[self.selected_marker] if (
            self.marker_numbers and 0 <= self.selected_marker < len(self.marker_numbers)
        ) else self.selected_marker + 1
        display_name = self.player_names.get(n_val, f"Marker {n_val}")
        self.hud_marker_label.setText(display_name)
        self.hud_sub_label.setText(
            f"ID {n_val}  ·  {self.selected_marker + 1} / {self.marker_count}  —  Tab to cycle")

    def _apply_zoom(self, zoom_level, center=None):
        if not self.graphics_scene.items():
            return
        # Only re-apply transform when zoom level actually changed — avoids visual jump each frame
        current_scale = self.graphics_view.transform().m11()
        if abs(current_scale - zoom_level) > 0.001:
            self.graphics_view.resetTransform()
            if zoom_level != 1.0:
                self.graphics_view.scale(zoom_level, zoom_level)
        if center is not None:
            self.graphics_view.centerOn(center)

    # ── Navigation & markers ──────────────────────────────────────────────────

    def _on_slider_changed(self, value):
        self.current_frame = value
        self._update_video_frame()

    def _on_frame_spin_changed(self, value):
        # value é 1-based
        frame = value - 1
        if frame != self.current_frame:
            self.current_frame = frame
            self._update_video_frame()

    # ── Play / Pause ──────────────────────────────────────────────────────────

    def toggle_play(self):
        if not self.cap or not self.cap.isOpened():
            return
        self._playing = not self._playing
        if self._playing:
            self.btn_play.setText("⏸ Pause")
            self._update_play_speed()
            self._play_timer.start()
        else:
            self._playing = False
            self._play_timer.stop()
            self.btn_play.setText("▶ Play")

    def _set_speed(self, multiplier: float, clicked_btn):
        self._speed_multiplier = multiplier
        for btn in self._speed_btns:
            btn.setChecked(btn is clicked_btn)
        self._update_play_speed()

    def _update_play_speed(self):
        interval = max(1, int(1000 / self.fps)) if self.fps > 0 else 33
        self._play_timer.setInterval(interval)

    def _play_tick(self):
        if self.current_frame < self.total_frames - 1:
            self.current_frame += 1
            self._update_video_frame()
        else:
            self.toggle_play()

    def eventFilter(self, obj, event):
        if obj is self.graphics_view.viewport():
            t = event.type()
            if t == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._pan_start = event.pos()
                    self.graphics_view.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
                pos   = self.graphics_view.mapToScene(event.pos())
                x, y  = pos.x(), pos.y()
                if event.button() == Qt.MouseButton.LeftButton:
                    self._set_marker(x, y)
                elif event.button() == Qt.MouseButton.RightButton:
                    self._remove_marker()
                self.setFocus()
            elif t == event.Type.MouseMove:
                if self._pan_start is not None:
                    delta = event.pos() - self._pan_start
                    self._pan_start = event.pos()
                    self.graphics_view.horizontalScrollBar().setValue(
                        self.graphics_view.horizontalScrollBar().value() - delta.x())
                    self.graphics_view.verticalScrollBar().setValue(
                        self.graphics_view.verticalScrollBar().value() - delta.y())
                    return True
            elif t == event.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._pan_start = None
                    self.graphics_view.setCursor(Qt.CursorShape.ArrowCursor)
                    return True
            elif t == event.Type.Wheel:
                if event.angleDelta().y() > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()

        if event.type() == event.Type.KeyPress:
            k = event.key()
            actions = {
                Qt.Key.Key_Up:       lambda: self.skip_frames(60),
                Qt.Key.Key_Down:     lambda: self.skip_frames(-60),
                Qt.Key.Key_Right:    self.next_frame,
                Qt.Key.Key_Left:     self.prev_frame,
                Qt.Key.Key_A:        self.add_marker,
                Qt.Key.Key_R:        self._remove_marker,
                Qt.Key.Key_Tab:      self.cycle_marker,
                Qt.Key.Key_Backtab:  self.cycle_marker_down,   # Shift+Tab
                Qt.Key.Key_Space:    self.toggle_play,
                Qt.Key.Key_Equal:    self.zoom_in,
                Qt.Key.Key_Minus:    self.zoom_out,
            }
            if k in actions:
                actions[k]()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        k = event.key()
        actions = {
            Qt.Key.Key_Tab:     self.cycle_marker,
            Qt.Key.Key_Backtab: self.cycle_marker_down,
            Qt.Key.Key_Space:   self.toggle_play,
            Qt.Key.Key_Right:   self.next_frame,
            Qt.Key.Key_Left:    self.prev_frame,
            Qt.Key.Key_Up:      lambda: self.skip_frames(60),
            Qt.Key.Key_Down:    lambda: self.skip_frames(-60),
            Qt.Key.Key_A:       self.add_marker,
            Qt.Key.Key_R:       self._remove_marker,
            Qt.Key.Key_Equal:   self.zoom_in,
            Qt.Key.Key_Minus:   self.zoom_out,
        }
        if k in actions:
            actions[k]()
        else:
            super().keyPressEvent(event)

    def _set_marker(self, x, y):
        pts = self.markers.get(self.current_frame, [])
        while len(pts) <= self.selected_marker:
            pts.append((None, None))
        pts[self.selected_marker] = (x, y)
        self.markers[self.current_frame] = pts
        self._update_video_frame()

    def add_marker(self):
        self.marker_count += 1
        next_n = (max(self.marker_numbers) + 1) if self.marker_numbers else self.marker_count
        self.marker_numbers.append(next_n)
        for f in self.markers:
            pts = self.markers[f]
            while len(pts) < self.marker_count:
                pts.append((None, None))
        self.selected_marker = self.marker_count - 1
        self._update_video_frame()

    def _remove_marker(self):
        pts = self.markers.get(self.current_frame, [])
        if 0 <= self.selected_marker < len(pts):
            pts[self.selected_marker] = (None, None)
            self.markers[self.current_frame] = pts
        self._update_video_frame()

    def cycle_marker(self):
        if self.marker_count:
            self.selected_marker = (self.selected_marker + 1) % self.marker_count
            self._update_video_frame()

    def cycle_marker_down(self):
        if self.marker_count:
            self.selected_marker = (self.selected_marker - 1) % self.marker_count
            self._update_video_frame()

    def next_frame(self):
        if self.current_frame < self.total_frames - 1:
            self.current_frame += 1
            self._update_video_frame()

    def prev_frame(self):
        if self.current_frame > 0:
            self.current_frame -= 1
            self._update_video_frame()

    def skip_frames(self, n):
        self.current_frame = max(0, min(self.total_frames - 1, self.current_frame + n))
        self._update_video_frame()

    def zoom_in(self):
        self.zoom = min(3.0, self.zoom * 1.2)
        # Persiste o centro visual atual
        self.zoom_center = self.graphics_view.mapToScene(
            self.graphics_view.viewport().rect().center())
        self._apply_zoom(self.zoom, self.zoom_center)

    def zoom_out(self):
        self.zoom = max(0.2, self.zoom / 1.2)
        self.zoom_center = self.graphics_view.mapToScene(
            self.graphics_view.viewport().rect().center())
        self._apply_zoom(self.zoom, self.zoom_center)

    # ── Sort markers ──────────────────────────────────────────────────────────

    def sort_markers(self):
        if not self.marker_numbers:
            QMessageBox.warning(self, "No Markers", "No markers found to sort.")
            return
        sequential = list(range(1, len(self.marker_numbers) + 1))
        if self.marker_numbers == sequential:
            QMessageBox.information(self, "Already Sorted", "Markers are already sequential.")
            return

        reply = QMessageBox.question(
            self, "Sort Markers",
            f"Current: {self.marker_numbers}\nNew order: {sequential}\n\nAll data preserved, only column names change.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.old_marker_numbers = self.marker_numbers.copy()
        if self.bboxes:
            self._sort_bboxes_in_memory()
        self.marker_numbers = sequential
        self.marker_count   = len(sequential)
        if self.selected_marker >= self.marker_count:
            self.selected_marker = self.marker_count - 1
        QMessageBox.information(self, "Markers Sorted",
            f"Reordered to: {self.marker_numbers}\n"
            "Both CSVs updated on next Save.")
        self._update_video_frame()

    def _sort_bboxes_in_memory(self):
        if not self.bboxes or not hasattr(self, "old_marker_numbers"):
            return
        new_bboxes = {}
        for frame, bbs in self.bboxes.items():
            new_bboxes[frame] = [
                bbs[i] if i < len(bbs) else (None, None, None, None)
                for i in range(len(self.old_marker_numbers))
            ]
        self.bboxes = new_bboxes

    # ── Name editor ───────────────────────────────────────────────────────────

    def open_name_editor(self):
        """Diálogo para editar o nome de cada marker."""
        if not self.marker_numbers:
            QMessageBox.warning(self, "No Markers", "Load a CSV first.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Player Names")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("""
            QWidget { background-color: #0D0D14; color: #EEEEF8; }
            QLineEdit {
                background-color: #1D1D2C; color: #EEEEF8;
                border: 1px solid #303050; border-radius: 6px;
                padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #4282FF; }
            QPushButton {
                background-color: #1D1D2C; color: #A0A0C0;
                border: 1px solid #222230; border-radius: 6px; padding: 6px 14px;
            }
            QPushButton:hover { background-color: #242438; color: #EEEEF8; }
            QPushButton[role="primary"] {
                background-color: #4282FF; color: #fff; border-color: transparent;
                font-weight: bold;
            }
            QPushButton[role="primary"]:hover { background-color: #6098FF; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Defina um nome para cada marker:")
        title.setStyleSheet("color: #EEEEF8; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(title)

        fields = {}
        for mid in self.marker_numbers:
            row = QHBoxLayout()
            lbl = QLabel(f"Marker {mid}:")
            lbl.setFixedWidth(80)
            lbl.setStyleSheet("color: #A0A0C0;")
            field = QLineEdit()
            field.setPlaceholderText(f"p{mid}")
            field.setText(self.player_names.get(mid, ""))
            row.addWidget(lbl)
            row.addWidget(field)
            layout.addLayout(row)
            fields[mid] = field

        layout.addSpacing(8)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_save   = QPushButton("Salvar")
        btn_save.setProperty("role", "primary")
        btn_cancel.clicked.connect(dlg.reject)
        btn_save.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            for mid, field in fields.items():
                name = field.text().strip()
                if name:
                    self.player_names[mid] = name
                else:
                    self.player_names.pop(mid, None)
            self._save_player_names()
            self._update_video_frame()
            self._update_hud_label()

    # ── Help ─────────────────────────────────────────────────────────────────

    def show_help(self):
        QMessageBox.information(self, "Help — Controls", """
<b>Buttons:</b>
<ul>
<li><b>Graphic ReID</b>: Advanced Re-Identification tool</li>
<li><b>Sort Markers</b>: Renumber to p1, p2, p3…</li>
<li><b>Marker ↑/↓</b>: Cycle selected marker</li>
<li><b>▶ Play / ⏸ Pause</b>: Playback at selected speed</li>
</ul>
<b>Keyboard:</b>
<ul>
<li><b>Tab</b>: Next marker</li>
<li><b>Shift+Tab</b>: Previous marker</li>
<li><b>Space</b>: Play / Pause</li>
<li><b>← →</b>: Prev / next frame</li>
<li><b>↑ ↓</b>: ±60 frames</li>
<li><b>A</b>: Add marker</li>
<li><b>R</b>: Remove current frame coordinate</li>
<li><b>= / -</b>: Zoom in / out (position preserved)</li>
</ul>
<b>Mouse:</b>
<ul>
<li><b>Left-click</b>: Set marker position</li>
<li><b>Right-click</b>: Remove marker position</li>
<li><b>Scroll wheel</b>: Zoom (position preserved)</li>
</ul>
<b>HUD (top-left overlay):</b>
<ul>
<li>Shows the currently active marker ID at all times</li>
</ul>
""")


# =============================================================================
# FACTORY
# =============================================================================

def run_getpixelcoord(video_path=None, project_path=None):
    return GetPixelCoordWindow(video_path=video_path, project_path=project_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GetPixelCoordWindow()
    window.show()
    sys.exit(app.exec())


# =============================================================================
# BRIDGE (QML ↔ Python)
# =============================================================================

from PySide6.QtCore import QObject, Slot as _Slot

class GetPixelCoordManager(QObject):
    def __init__(self, videos_manager, projects_manager, parent=None):
        super().__init__(parent)
        self._videos_manager   = videos_manager
        self._projects_manager = projects_manager
        self._window           = None

    @_Slot()
    def open_tool(self):
        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path:
            return
        if self._window is not None:
            self._window.deleteLater()
            self._window = None
        self._window = GetPixelCoordWindow(
            video_path=video_path,
            project_path=project_path,
        )
        self._window.show()
