# This module is an adaptation from Vaila's Tracker, developed by Santiago Preto.
# https://github.com/vaila-multimodaltoolbox/vaila

import sys
import os
import cv2

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox, QApplication, QLabel, QSizePolicy,
    QListWidget, QListWidgetItem, QSpinBox, QDialog, QDialogButtonBox,
    QButtonGroup, QRadioButton, QSlider, QGraphicsView, QGraphicsScene,
    QGroupBox, QFrame
)
from PySide6.QtCore import Qt, Signal, QRect, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QFont


# =============================================================================
# SHARED DARK STYLESHEET
# =============================================================================

_DARK_SS = """
QWidget {
    background-color: #0D0D14;
    color: #EEEEF8;
    font-size: 12px;
}
QLabel {
    color: #A0A0C0;
    background: transparent;
}
QPushButton {
    background-color: #1D1D2C;
    color: #A0A0C0;
    border: 1px solid #222230;
    border-radius: 7px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #242438;
    color: #EEEEF8;
    border-color: #303050;
}
QPushButton:pressed {
    background-color: #13213F;
    color: #C0D8FF;
}
QPushButton[role="primary"] {
    background-color: #4282FF;
    color: #FFFFFF;
    border-color: transparent;
    font-weight: bold;
}
QPushButton[role="primary"]:hover { background-color: #6098FF; }
QPushButton[role="danger"] {
    background-color: rgba(255,69,96,0.12);
    color: #FF4560;
    border-color: rgba(255,69,96,0.35);
}
QPushButton[role="danger"]:hover { background-color: rgba(255,69,96,0.22); }
QPushButton[role="success"] {
    background-color: rgba(45,212,128,0.12);
    color: #2DD480;
    border-color: rgba(45,212,128,0.35);
}
QPushButton[role="success"]:hover { background-color: rgba(45,212,128,0.22); }
QPushButton[role="warning"] {
    background-color: rgba(255,152,48,0.12);
    color: #FF9830;
    border-color: rgba(255,152,48,0.35);
}
QPushButton[role="warning"]:hover { background-color: rgba(255,152,48,0.22); }
QPushButton:checked {
    background-color: #13213F;
    color: #C0D8FF;
    border-color: #4282FF;
}
QSpinBox {
    background-color: #161621;
    color: #EEEEF8;
    border: 1px solid #222230;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #4282FF;
}
QSpinBox:focus { border-color: #4282FF; }
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #1D1D2C;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #242438;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #222230;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4282FF;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #6098FF; }
QSlider::sub-page:horizontal { background: #4282FF; border-radius: 2px; }
QSlider:disabled::groove:horizontal { background: #1D1D2C; }
QSlider:disabled::sub-page:horizontal { background: #1D1D2C; }
QSlider:disabled::handle:horizontal { background: #303050; }
QListWidget {
    background-color: #161621;
    border: 1px solid #222230;
    border-radius: 8px;
    outline: none;
}
QListWidget::item {
    padding: 5px 10px;
    border-radius: 4px;
    color: #A0A0C0;
}
QListWidget::item:hover { background-color: #1D1D2C; color: #EEEEF8; }
QGroupBox {
    background-color: #161621;
    border: 1px solid #222230;
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: bold;
    color: #6868A0;
    font-size: 10px;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #6868A0;
    font-size: 10px;
    letter-spacing: 1.2px;
}
QGraphicsView {
    background-color: #0D0D14;
    border: 1px solid #222230;
    border-radius: 8px;
}
QDialog { background-color: #0D0D14; }
QRadioButton { color: #A0A0C0; spacing: 8px; }
QRadioButton::indicator {
    width: 16px; height: 16px;
    border-radius: 8px;
    border: 2px solid #303050;
    background: #161621;
}
QRadioButton::indicator:checked { background: #4282FF; border-color: #4282FF; }
QRadioButton:hover { color: #EEEEF8; }
QScrollBar:vertical {
    background: #0D0D14; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #222230; border-radius: 4px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #303050; }
QScrollBar:horizontal {
    background: #0D0D14; height: 8px; border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #222230; border-radius: 4px; min-width: 20px;
}
"""

# =============================================================================
# HELPERS
# =============================================================================

def _read_csv_robust(path):
    return pd.read_csv(path, engine="python", on_bad_lines="skip", encoding="utf-8")


def detect_markers(df):
    """Detecta IDs de markers a partir das colunas do DataFrame."""
    markers = set()
    for col in df.columns:
        if col.startswith("p"):
            if col.endswith("_x"):
                markers.add(int(col[1:-2]))
            elif col.endswith("_xmin"):
                markers.add(int(col[1:-5]))
    return sorted(markers)


def get_marker_coords(df, marker_id):
    x_col, y_col = f"p{marker_id}_x", f"p{marker_id}_y"
    if x_col not in df.columns or y_col not in df.columns:
        return None, None
    return df[x_col].values, df[y_col].values


def _find_csv_options(video_path, project_path):
    """
    Retorna lista de opções de CSV para o vídeo dado.
    Busca por múltiplas variantes do nome e faz fuzzy match no diretório.
    """
    import re
    pixel_dir  = os.path.join(project_path, "data", "pixel_coordinates")
    bboxes_dir = os.path.join(project_path, "data", "bboxes")
    if not os.path.isdir(pixel_dir):
        return []

    stem = os.path.splitext(os.path.basename(video_path))[0]
    base = stem[:-8] if stem.endswith("_tracked") else stem

    # Also strip timestamp suffixes like _edited_YYYYMMDD_HHMM from base
    short_base = re.sub(r"_edited_\d{8}_\d{4}$", "", base)
    short_stem = re.sub(r"_edited_\d{8}_\d{4}$", "", stem)

    # All prefixes to try (most specific first)
    prefixes = dict.fromkeys([base, stem, short_base, short_stem])

    # Named candidates: (filename, label, is_field_keypoints)
    named_candidates = []
    for p in prefixes:
        named_candidates += [
            (f"{p}_tracked.csv",         "Tracked coordinates", False),
            (f"{p}_field_keypoints.csv",  "Field keypoints",    True),
            (f"{p}.csv",                  "Coordinates",        False),
        ]

    options, seen = [], set()

    def _add(filename, label, is_kp):
        path = os.path.join(pixel_dir, filename)
        if path in seen or not os.path.isfile(path):
            return
        seen.add(path)
        bbox_path = None
        if not is_kp:
            bp = os.path.join(bboxes_dir,
                              filename.replace("_tracked.csv", "_bboxes.csv")
                                      .replace(".csv", "_bboxes.csv")
                                      .replace("_bboxes_bboxes.csv", "_bboxes.csv"))
            if os.path.isfile(bp):
                bbox_path = bp
        options.append({"label": label, "filename": filename,
                        "path": path, "bboxes_path": bbox_path,
                        "is_field_keypoints": is_kp})

    for filename, label, is_kp in named_candidates:
        _add(filename, label, is_kp)

    # Fuzzy fallback: any CSV whose stem starts with one of our prefixes
    if not options:
        all_csvs = [f for f in os.listdir(pixel_dir) if f.lower().endswith(".csv")]
        for f in sorted(all_csvs):
            f_stem = os.path.splitext(f)[0]
            for p in prefixes:
                if p and f_stem.startswith(p):
                    is_kp = "keypoints" in f
                    _add(f, "Tracked coordinates" if not is_kp else "Field keypoints", is_kp)
                    break

    return options


# =============================================================================
# RANGE SLIDER
# =============================================================================

class RangeSliderWidget(QWidget):
    rangeChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_value   = 0
        self.max_value   = 100
        self.start_value = 0
        self.end_value   = 100
        self.dragging    = None
        self.setMinimumHeight(40)
        self.setMouseTracking(True)

    def setRange(self, min_val, max_val):
        self.min_value   = min_val
        self.max_value   = max_val
        self.start_value = min_val
        self.end_value   = max_val
        self.update()

    def setValues(self, start_val, end_val):
        self.start_value = max(self.min_value, min(start_val, self.max_value))
        self.end_value   = max(self.min_value, min(end_val,   self.max_value))
        if self.start_value > self.end_value:
            self.start_value, self.end_value = self.end_value, self.start_value
        self.update()
        self.rangeChanged.emit(self.start_value, self.end_value)

    def getValues(self):
        return self.start_value, self.end_value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect   = self.rect()
        width  = rect.width()
        height = rect.height()

        track = QRect(10, height // 2 - 4, width - 20, 8)
        painter.fillRect(track, QColor(34, 34, 48))
        painter.setPen(QPen(QColor(48, 48, 80), 1))
        painter.drawRect(track)

        rng = self.max_value - self.min_value
        if rng == 0:
            return

        sp = 10 + (self.start_value - self.min_value) / rng * (width - 20)
        ep = 10 + (self.end_value   - self.min_value) / rng * (width - 20)

        if sp < ep:
            sel = QRect(int(sp), height // 2 - 4, int(ep - sp), 8)
            painter.fillRect(sel, QColor(66, 130, 255))
            painter.setPen(QPen(QColor(96, 152, 255), 1))
            painter.drawRect(sel)

        hs = 16
        for pos in (sp, ep):
            shadow = QRect(int(pos - hs // 2) + 1, height // 2 - hs // 2 + 1, hs, hs)
            handle = QRect(int(pos - hs // 2),     height // 2 - hs // 2,     hs, hs)
            painter.setPen(QPen(QColor(19, 33, 63), 1))
            painter.setBrush(QBrush(QColor(29, 29, 44)))
            painter.drawEllipse(shadow)
            painter.setPen(QPen(QColor(66, 130, 255), 2))
            painter.setBrush(QBrush(QColor(36, 36, 56)))
            painter.drawEllipse(handle)
            painter.setPen(QPen(QColor(66, 130, 255), 3))
            painter.drawPoint(int(pos), height // 2)

        painter.setPen(QColor(104, 104, 160))
        painter.drawText(QRect(0, height // 2 + 15, width, 20),
                         Qt.AlignmentFlag.AlignCenter,
                         f"Frames: {self.start_value + 1} – {self.end_value + 1}")

    def _pos_to_value(self, x):
        rng = self.max_value - self.min_value
        if rng == 0:
            return self.min_value
        val = self.min_value + (x - 10) / (self.rect().width() - 20) * rng
        return max(self.min_value, min(self.max_value, val))

    def _handle_pos(self, value):
        rng = self.max_value - self.min_value
        if rng == 0:
            return 10
        return 10 + (value - self.min_value) / rng * (self.rect().width() - 20)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x  = event.position().x()
        sp = self._handle_pos(self.start_value)
        ep = self._handle_pos(self.end_value)
        hs = 16
        if abs(x - sp) <= hs:
            self.dragging = "start"
        elif abs(x - ep) <= hs:
            self.dragging = "end"
        else:
            self.dragging = "start" if abs(x - sp) < abs(x - ep) else "end"

    def mouseMoveEvent(self, event):
        if not self.dragging:
            return
        val = int(self._pos_to_value(event.position().x()))
        if self.dragging == "start" and val <= self.end_value:
            self.start_value = val
        elif self.dragging == "end" and val >= self.start_value:
            self.end_value = val
        self.update()
        self.rangeChanged.emit(self.start_value, self.end_value)

    def mouseReleaseEvent(self, event):
        self.dragging = None


# =============================================================================
# CSV SELECTION DIALOG
# =============================================================================

class CSVSelectionDialog(QDialog):
    def __init__(self, csv_options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select CSV File")
        self.setFixedSize(450, 220)
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
            btn.setProperty("csv_path",   opt["path"])
            btn.setProperty("bboxes_path", opt.get("bboxes_path"))
            btn.setProperty("is_field_keypoints", opt.get("is_field_keypoints", False))
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
            return {
                "path":              btn.property("csv_path"),
                "bboxes_path":       btn.property("bboxes_path"),
                "is_field_keypoints": btn.property("is_field_keypoints"),
            }
        return None


# =============================================================================
# REID WINDOW
# =============================================================================

class ReIDWindow(QMainWindow):
    data_updated = Signal()
    data_ready   = Signal(object, object)   # (df, bboxes_df)

    def __init__(self, video_path=None, project_path=None,
                 current_data=None, original_csv_path=None, current_bboxes_data=None):
        super().__init__()
        self.setWindowTitle("Advanced ReID Tool")
        self.setGeometry(100, 100, 1600, 1000)
        self.setStyleSheet(_DARK_SS)

        self.video_path           = video_path
        self.project_path         = project_path
        self.current_data         = current_data
        self.current_bboxes_data  = current_bboxes_data
        self.original_csv_path    = original_csv_path
        self.df                   = None
        self.bboxes_df            = None
        self.file_path            = None
        self.bboxes_file_path     = None
        self.temp_history         = []
        self.bboxes_temp_history  = []
        self.marker_status        = []
        self.lines_x              = {}
        self.lines_y              = {}
        self.all_markers          = []
        self.frames               = None
        self.field_keypoints_mode = False
        self._marker_colors       = {}   # mid → hex color from matplotlib

        # Mini-player state
        self._cap            = None
        self._total_frames   = 0
        self._current_frame  = 0
        self._playing        = False
        self._play_timer     = QTimer()
        self._play_timer.timeout.connect(self._play_tick)
        self._vline          = None   # linha vertical no gráfico

        self._init_ui()

        if self.current_data is not None:
            self._load_current_data()
        elif self.project_path:
            self._load_csv_from_project()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── Left panel: marker list ───────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(180)
        left.setStyleSheet("background-color: #161621; border-right: 1px solid #222230;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 12)
        left_layout.setSpacing(8)

        markers_lbl = QLabel("MARKERS")
        markers_lbl.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold; letter-spacing: 1.5px;")
        left_layout.addWidget(markers_lbl)

        self.marker_list_widget = QListWidget()
        self.marker_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        left_layout.addWidget(self.marker_list_widget)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)
        self.btn_all  = QPushButton("All")
        self.btn_none = QPushButton("None")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._select_none)
        sel_row.addWidget(self.btn_all)
        sel_row.addWidget(self.btn_none)
        left_layout.addLayout(sel_row)
        main_layout.addWidget(left)

        # ── Center panel: matplotlib + controls ───────────────────────────────
        center = QWidget()
        center.setStyleSheet("background-color: #0D0D14;")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 12, 16, 12)
        center_layout.setSpacing(8)

        # Status + open button row
        top_row = QHBoxLayout()
        self.file_status_label = QLabel("No CSV file loaded")
        self.file_status_label.setStyleSheet("color: #6868A0; font-style: italic;")
        top_row.addWidget(self.file_status_label)
        top_row.addStretch()
        open_btn = QPushButton("Open CSV")
        open_btn.setFixedWidth(100)
        open_btn.clicked.connect(self._open_file)
        top_row.addWidget(open_btn)
        center_layout.addLayout(top_row)

        # Matplotlib canvas
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8))
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setStyleSheet("background-color: #0D0D14;")
        center_layout.addWidget(self.canvas)

        # Frame range row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)
        slider_row.addWidget(QLabel("Range:"))

        self.start_frame_spin = QSpinBox()
        self.start_frame_spin.setMinimum(1)
        self.start_frame_spin.setMaximum(1)
        self.start_frame_spin.setFixedWidth(75)
        self.start_frame_spin.valueChanged.connect(self._on_start_frame_changed)
        slider_row.addWidget(self.start_frame_spin)

        self.frames_range = RangeSliderWidget()
        self.frames_range.rangeChanged.connect(self._on_range_changed)
        slider_row.addWidget(self.frames_range, stretch=1)

        self.end_frame_spin = QSpinBox()
        self.end_frame_spin.setMinimum(1)
        self.end_frame_spin.setMaximum(1)
        self.end_frame_spin.setFixedWidth(75)
        self.end_frame_spin.valueChanged.connect(self._on_end_frame_changed)
        slider_row.addWidget(self.end_frame_spin)
        center_layout.addLayout(slider_row)

        self.status_label = QLabel("")
        center_layout.addWidget(self.status_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        for attr, label, role, slot in [
            ("btn_fill",          "Fill Gaps",       "primary", self._fill_gaps),
            ("btn_merge",         "Merge",            "",        self._merge_markers),
            ("btn_merge_range",   "Merge Range",      "",        self._merge_markers_range),
            ("btn_swap",          "Swap",             "",        self._swap_markers),
            ("btn_erase_traj",    "Erase Traj.",      "warning", self._erase_trajectory),
            ("btn_delete_marker", "Delete Marker",    "danger",  self._delete_markers),
            ("btn_undo",          "Undo",             "",        self._undo),
            ("btn_save",          "Update / Close",   "success", self._update_and_close),
        ]:
            btn = QPushButton(label)
            if role:
                btn.setProperty("role", role)
            btn.clicked.connect(slot)
            setattr(self, attr, btn)
            btn_row.addWidget(btn)
        center_layout.addLayout(btn_row)

        main_layout.addWidget(center, stretch=2)

        # ── Right panel: tools + auto-detect ────────────────────────────────
        right = QWidget()
        right.setFixedWidth(260)
        right.setStyleSheet("background-color: #161621; border-left: 1px solid #222230;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 16, 12, 12)
        right_layout.setSpacing(10)

        # Título
        lbl_title = QLabel("TOOLS")
        lbl_title.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold; letter-spacing: 1.5px;")
        right_layout.addWidget(lbl_title)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #222230;")
        right_layout.addWidget(sep)

        # Painel de sugestões automáticas
        lbl_suggestions = QLabel("AUTO-DETECT IDs")
        lbl_suggestions.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold; letter-spacing: 1.5px;")
        right_layout.addWidget(lbl_suggestions)

        self.suggestions_list = QListWidget()
        self.suggestions_list.setStyleSheet("""
            QListWidget { background-color: #0D0D14; border: 1px solid #222230; border-radius: 6px; }
            QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #1A1A28; color: #A0A0C0; font-size: 10px; }
            QListWidget::item:hover { background-color: #1D1D2C; }
        """)
        right_layout.addWidget(self.suggestions_list, stretch=1)

        self.suggestions_info = QLabel("")
        self.suggestions_info.setWordWrap(True)
        self.suggestions_info.setStyleSheet(
            "color: #6868A0; font-size: 10px; padding: 4px;")
        right_layout.addWidget(self.suggestions_info)

        main_layout.addWidget(right)
        self.canvas.mpl_connect("key_press_event", self._on_key)
        self.canvas.mpl_connect("button_press_event", self._on_graph_click)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _init_from_df(self):
        """Inicializa estado interno após df estar carregado."""
        self.all_markers = detect_markers(self.df)
        self.frames      = self.df["frame"].values
        self.marker_status        = [True] * len(self.all_markers)
        self.lines_x, self.lines_y = {}, {}
        self._vline               = None
        self.temp_history         = []
        self.bboxes_temp_history  = []
        self.fig.set_size_inches(20, 10, forward=True)
        self._init_matplotlib_widgets()
        n = len(self.df)
        self.frames_range.setRange(0, n - 1)
        self.frames_range.setValues(0, n - 1)
        self.start_frame_spin.setMaximum(n)
        self.end_frame_spin.setMaximum(n)
        self.start_frame_spin.setValue(1)
        self.end_frame_spin.setValue(n)
        self._update_plot()           # creates lines + populates _marker_colors
        self._update_marker_list_widget()   # now colors are available
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.updateGeometry()
        self.canvas.repaint()

        # Init mini-player se tiver vídeo
        self._init_video_player()

        # Popula painel de sugestões automáticas
        self._populate_suggestions()

    # ── Auto-detect ID groups ──────────────────────────────────────────────

    def _auto_detect_id_groups(self):
        """
        Detecta automaticamente quais IDs provavelmente sao o mesmo jogador.
        Calibrado com dados reais: dist < 30px separa corretos de errados.
        Usa tambem vetor de velocidade e penalidade por area congestionada.
        """
        if self.df is None or not self.all_markers:
            return []

        fps = 24.0
        if self._cap is not None and self._cap.isOpened():
            fps = self._cap.get(cv2.CAP_PROP_FPS) or 24.0

        max_gap_frames = int(fps * 3)
        max_dist       = 30   # px — calibrado nos dados reais

        # Coleta info de cada marker
        marker_info = {}
        for mid in self.all_markers:
            x_col, y_col = f"p{mid}_x", f"p{mid}_y"
            if x_col not in self.df.columns:
                continue
            valid = self.df[self.df[x_col].notna()]
            if valid.empty:
                continue
            x = valid[x_col].values.astype(float)
            y = valid[y_col].values.astype(float)
            frames = valid["frame"].values
            n = min(20, len(x))
            vx_end   = (x[-1]  - x[-n])  / n
            vy_end   = (y[-1]  - y[-n])  / n
            vx_start = (x[n-1] - x[0])   / n
            vy_start = (y[n-1] - y[0])   / n
            marker_info[mid] = {
                "first_frame": int(frames[0]),
                "last_frame":  int(frames[-1]),
                "first_x": float(x[0]),   "first_y": float(y[0]),
                "last_x":  float(x[-1]),  "last_y":  float(y[-1]),
                "vx_end": vx_end, "vy_end": vy_end,
                "vx_start": vx_start, "vy_start": vy_start,
                "x": x, "y": y, "frames": frames,
            }

        pairs = []
        mids  = list(marker_info.keys())

        for i, a in enumerate(mids):
            for b in mids[i+1:]:
                ia, ib = marker_info[a], marker_info[b]

                # Sem sobreposicao temporal
                if not (ia["last_frame"] < ib["first_frame"] or
                        ib["last_frame"] < ia["first_frame"]):
                    continue

                # Quem vem primeiro
                if ia["last_frame"] < ib["first_frame"]:
                    first, second, id_f, id_s = ia, ib, a, b
                else:
                    first, second, id_f, id_s = ib, ia, b, a

                gap = second["first_frame"] - first["last_frame"]
                if gap > max_gap_frames:
                    continue

                dist = ((first["last_x"] - second["first_x"])**2 +
                        (first["last_y"] - second["first_y"])**2) ** 0.5
                if dist > max_dist:
                    continue

                # Vetor de velocidade: cos entre fim do primeiro e inicio do segundo
                dot   = (first["vx_end"]   * second["vx_start"] +
                         first["vy_end"]   * second["vy_start"])
                mag_a = (first["vx_end"]**2  + first["vy_end"]**2)  ** 0.5
                mag_b = (second["vx_start"]**2 + second["vy_start"]**2) ** 0.5
                vel_cos = dot / (mag_a * mag_b) if mag_a > 0 and mag_b > 0 else 0.0

                # Penalidade se outro marker estava proximo na transicao
                transition_frame = first["last_frame"]
                tx, ty = first["last_x"], first["last_y"]
                min_other_dist = float("inf")
                for mid2, im2 in marker_info.items():
                    if mid2 in (id_f, id_s):
                        continue
                    if im2["first_frame"] <= transition_frame <= im2["last_frame"]:
                        idx = int(np.searchsorted(im2["frames"], transition_frame))
                        if idx < len(im2["x"]):
                            d2 = ((tx - im2["x"][idx])**2 +
                                  (ty - im2["y"][idx])**2) ** 0.5
                            min_other_dist = min(min_other_dist, d2)

                crowded = (min_other_dist != float("inf") and
                           min_other_dist < dist * 2)

                # Score: menor = melhor
                score = ((dist / max_dist) * 0.5 +
                         (gap / max_gap_frames) * 0.3 +
                         (-vel_cos * 0.1) +
                         (0.2 if crowded else 0.0))

                confidence = ("✓ Alta"  if score < 0.35 else
                              "⚠ Média" if score < 0.65 else
                              "✗ Baixa")

                pairs.append({
                    "first": id_f, "second": id_s,
                    "gap": gap, "dist": dist,
                    "vel_cos": vel_cos, "crowded": crowded,
                    "score": score, "confidence": confidence,
                })

        pairs.sort(key=lambda p: p["score"])

        # Union-Find — agrupa em cadeias
        parent = {mid: mid for mid in mids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        used_pairs = []
        for p in pairs:
            if find(p["first"]) != find(p["second"]):
                union(p["first"], p["second"])
                used_pairs.append(p)

        groups = {}
        for mid in mids:
            groups.setdefault(find(mid), []).append(mid)

        suggestions = []
        for members in groups.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda m: marker_info[m]["first_frame"])
            group_pairs = [p for p in used_pairs
                           if p["first"] in members and p["second"] in members]
            avg_score = (sum(p["score"] for p in group_pairs) / len(group_pairs)
                         if group_pairs else 1.0)
            confidence = ("✓ Alta"  if avg_score < 0.35 else
                          "⚠ Média" if avg_score < 0.65 else
                          "✗ Baixa")
            suggestions.append({
                "ids": members, "pairs": group_pairs,
                "confidence": confidence, "avg_score": avg_score,
            })

        suggestions.sort(key=lambda s: s["avg_score"])
        return suggestions

    def _populate_suggestions(self):
        """Popula o painel de sugestões automáticas de IDs."""
        if not hasattr(self, "suggestions_list"):
            return
        self.suggestions_list.clear()
        suggestions = self._auto_detect_id_groups()
        if not suggestions:
            self.suggestions_info.setText("Nenhuma troca de ID detectada.")
            return

        self.suggestions_info.setText(
            f"{len(suggestions)} grupo(s) detectado(s).\n"
            "Selecione os IDs na lista lateral e use Merge para corrigir."
        )

        for s in suggestions:
            ids_str = " → ".join(str(i) for i in s["ids"])
            pairs_detail = []
            for p in s["pairs"]:
                pairs_detail.append(
                    f"  {p['first']}→{p['second']}: gap={p['gap']}f dist={p['dist']:.0f}px"
                )
            detail = "\n".join(pairs_detail)
            text = f"{s['confidence']}  IDs: {ids_str}\n{detail}"
            item = QListWidgetItem(text)
            if "Alta" in s["confidence"]:
                item.setForeground(QColor("#2DD480"))
            elif "Média" in s["confidence"]:
                item.setForeground(QColor("#FF9830"))
            else:
                item.setForeground(QColor("#FF4560"))
            self.suggestions_list.addItem(item)

    def _load_bboxes(self, bboxes_path=None, from_data=None):
        """Carrega bboxes de dados em memória ou de arquivo."""
        if from_data is not None:
            try:
                self.bboxes_df       = from_data.copy()
                self.bboxes_file_path = bboxes_path
                self._verify_markers_match()
            except Exception as e:
                QMessageBox.warning(self, "Bounding Boxes Error", f"Could not load bboxes: {e}")
                self.bboxes_df = self.bboxes_file_path = None
        elif bboxes_path and os.path.isfile(bboxes_path):
            try:
                self.bboxes_df       = _read_csv_robust(bboxes_path)
                self.bboxes_file_path = bboxes_path
                self._verify_markers_match()
            except Exception as e:
                QMessageBox.warning(self, "Bounding Boxes Error", f"Could not load bboxes: {e}")
                self.bboxes_df = self.bboxes_file_path = None
        else:
            self.bboxes_df = self.bboxes_file_path = None

    def _verify_markers_match(self):
        if self.bboxes_df is None:
            return
        if detect_markers(self.df) != detect_markers(self.bboxes_df):
            QMessageBox.warning(self, "Warning",
                "Marker IDs in tracked data and bounding boxes do not match.")

    def _load_current_data(self):
        """Carrega dados em memória passados pelo getpixelcoord."""
        try:
            self.df = self.current_data.copy()

            if self.original_csv_path and os.path.exists(self.original_csv_path):
                self.file_path        = self.original_csv_path
                self.field_keypoints_mode = "_field_keypoints.csv" in self.original_csv_path
            elif self.project_path and self.video_path:
                stem = os.path.splitext(os.path.basename(self.video_path))[0]
                base = stem[:-8] if stem.endswith("_tracked") else stem
                pixel_dir = os.path.join(self.project_path, "data", "pixel_coordinates")
                self.file_path        = os.path.join(pixel_dir, f"{base}_tracked.csv")
                self.field_keypoints_mode = False

            # Bboxes
            if not self.field_keypoints_mode and self.project_path and self.video_path:
                stem = os.path.splitext(os.path.basename(self.video_path))[0]
                base = stem[:-8] if stem.endswith("_tracked") else stem
                bboxes_path = os.path.join(self.project_path, "data", "bboxes", f"{base}_bboxes.csv")
                self._load_bboxes(bboxes_path=bboxes_path, from_data=self.current_bboxes_data)

            self._init_from_df()
            self._set_status_ok()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading current data: {e}")
            if self.project_path:
                self._load_csv_from_project()

    def _load_csv_from_project(self):
        """Carrega CSV do projeto usando lógica robusta de resolução de arquivo."""
        if not self.project_path or not self.video_path:
            self.file_status_label.setText("No video provided to match a CSV file.")
            return

        options = _find_csv_options(self.video_path, self.project_path)

        if not options:
            stem = os.path.splitext(os.path.basename(self.video_path))[0]
            self.file_status_label.setText(f"No CSV files found for {stem}")
            QMessageBox.warning(self, "Auto-load Warning",
                f"No CSV files found.\nYou can manually load CSV files.")
            return

        if len(options) == 1:
            self._load_option(options[0])
        else:
            dialog = CSVSelectionDialog(options, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                opt = dialog.get_selected_option()
                if opt:
                    sel = next((o for o in options if o["path"] == opt["path"]), None)
                    if sel:
                        self._load_option(sel)
            else:
                self.file_status_label.setText("No CSV file selected")

    def _load_option(self, opt):
        """Carrega uma opção de CSV (tracked ou field keypoints) com seus bboxes."""
        try:
            self.df                   = _read_csv_robust(opt["path"])
            self.file_path            = opt["path"]
            self.field_keypoints_mode = opt.get("is_field_keypoints", False)

            if not self.field_keypoints_mode:
                self._load_bboxes(bboxes_path=opt.get("bboxes_path"))

            self._init_from_df()
            self._set_status_ok(filename=os.path.basename(opt["path"]))

        except Exception as e:
            msg = f"Error loading CSV: {e}"
            self.file_status_label.setText(msg)
            QMessageBox.critical(self, "Error", msg)

    def _open_file(self):
        """Abre CSV manualmente (modo standalone)."""
        if self.project_path and self.df is not None:
            QMessageBox.warning(self, "CSV Already Loaded",
                "A CSV is already loaded from the project context.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Markers File", "", "CSV Files (*.csv)")
        if not path:
            return

        is_kp = "_field_keypoints.csv" in path
        self.field_keypoints_mode = is_kp

        bbox_path = None
        if "_tracked.csv" in path and not is_kp:
            bp = path.replace("_tracked.csv", "_bboxes.csv").replace(
                "pixel_coordinates", "bboxes")
            if os.path.isfile(bp):
                bbox_path = bp
            else:
                QMessageBox.warning(self, "Warning",
                    "No corresponding bboxes CSV found. Only tracked data will be modified.")

        try:
            self.df        = _read_csv_robust(path)
            self.file_path = path
            if not is_kp:
                self._load_bboxes(bboxes_path=bbox_path)
            self._init_from_df()
            self._set_status_ok(filename=os.path.basename(path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading file: {e}")

    def _set_status_ok(self, filename=None):
        parts = []
        if filename:
            parts.append(f"CSV loaded: {filename}")
        else:
            parts.append("Current data loaded")
        if self.field_keypoints_mode:
            parts.append("field keypoints")
        elif self.bboxes_df is not None:
            parts.append("with bounding boxes")
        else:
            parts.append("tracked only")
        self.file_status_label.setText(" — ".join(parts))
        self.file_status_label.setStyleSheet(
            "color: #2DD480; font-weight: bold;")

    # ── Matplotlib ────────────────────────────────────────────────────────────

    def _init_matplotlib_widgets(self):
        self.fig.clf()
        self.ax1 = self.fig.add_subplot(2, 1, 1)
        self.ax2 = self.fig.add_subplot(2, 1, 2)
        plt.subplots_adjust(left=0.07, bottom=0.15, right=0.95, top=0.90, hspace=0.4)
        self._apply_mpl_dark_theme()
        self.canvas.draw()

    def _apply_mpl_dark_theme(self):
        """Apply consistent dark styling to all matplotlib axes."""
        self.fig.set_facecolor("#0D0D14")
        for ax in (self.ax1, self.ax2):
            ax.set_facecolor("#161621")
            ax.tick_params(colors="#6868A0", labelsize=9)
            ax.xaxis.label.set_color("#A0A0C0")
            ax.yaxis.label.set_color("#A0A0C0")
            ax.title.set_color("#EEEEF8")
            for spine in ax.spines.values():
                spine.set_edgecolor("#222230")

    def _update_plot(self):
        if self.df is None:
            return
        start, end   = self.frames_range.getValues()
        selected     = self._get_selected_markers()

        for mid in self.all_markers:
            if mid not in self.lines_x:
                x, y = get_marker_coords(self.df, mid)
                if x is not None:
                    self.lines_x[mid], = self.ax1.plot([], [], lw=1)
                    self.lines_y[mid], = self.ax2.plot([], [], lw=1)
                    self._marker_colors[mid] = self.lines_x[mid].get_color()

        for mid in list(self.lines_x):
            if mid not in self.all_markers:
                self.lines_x[mid].remove(); del self.lines_x[mid]
                self.lines_y[mid].remove(); del self.lines_y[mid]
                continue
            x, y = get_marker_coords(self.df, mid)
            if x is None:
                self.lines_x[mid].set_visible(False)
                self.lines_y[mid].set_visible(False)
                continue
            vis = mid in selected
            self.lines_x[mid].set_visible(vis)
            self.lines_y[mid].set_visible(vis)
            if vis:
                self.lines_x[mid].set_data(self.frames[start:end + 1], x[start:end + 1])
                self.lines_y[mid].set_data(self.frames[start:end + 1], y[start:end + 1])

        for ax, title, ylabel in [
            (self.ax1, "X Coordinates of Markers", "X Position"),
            (self.ax2, "Y Coordinates of Markers", "Y Position"),
        ]:
            ax.set_xlim(start + 1, end + 1)
            ax.relim(); ax.autoscale_view()
            ax.grid(True, color="#222230", linewidth=0.5, linestyle="--", alpha=0.7)
            ax.set_title(title, color="#EEEEF8", fontsize=10)
            ax.set_xlabel("Frame", color="#A0A0C0", fontsize=9)
            ax.set_ylabel(ylabel, color="#A0A0C0", fontsize=9)

        self._update_vline()
        self.canvas.draw_idle()

    def _update_vline(self):
        """Atualiza (ou cria) a linha vertical vermelha no frame atual do player."""
        if self._total_frames == 0:
            return
        frame_num = self._current_frame + 1  # 1-based para corresponder ao eixo X
        for ax in (self.ax1, self.ax2):
            # Remove linhas anteriores
            for line in ax.lines:
                if getattr(line, "_is_vline", False):
                    line.remove()
            vl = ax.axvline(x=frame_num, color="red", linewidth=1.5,
                            linestyle="--", alpha=0.8, zorder=10)
            vl._is_vline = True

    def _on_graph_click(self, event):
        """Clique no gráfico → salta o mini-player para esse frame."""
        if event.xdata is None or self._total_frames == 0:
            return
        frame = max(0, min(self._total_frames - 1, int(round(event.xdata)) - 1))
        self._seek_video(frame)

    # ── Mini video player ─────────────────────────────────────────────────────

    def _init_video_player(self):
        """Abre o vídeo no mini-player se disponível."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        path = self.video_path
        if not path or not os.path.isfile(path):
            if hasattr(self, "video_frame_label"):
                self.video_frame_label.setText("No video found")
            return

        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            if hasattr(self, "video_frame_label"):
                self.video_frame_label.setText("Could not open video")
            self._cap = None
            return

        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._current_frame = 0
        if hasattr(self, "video_slider"):
            self.video_slider.setMaximum(self._total_frames - 1)
            self.video_slider.setEnabled(True)
        self._update_video_display()

    def _update_video_display(self):
        """Renderiza o frame atual no mini-player com redimensionamento correto."""
        if not hasattr(self, "video_view") or self._cap is None or not self._cap.isOpened():
            return

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._current_frame)
        ret, frame = self._cap.read()
        if not ret:
            return

        # Redimensiona para o tamanho do painel antes de criar QImage
        view_w = max(self.video_view.width() - 4, 320)
        view_h = max(self.video_view.height() - 4, 240)
        orig_h, orig_w = frame.shape[:2]
        scale = min(view_w / orig_w, view_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch  = frame_rgb.shape
        qimg      = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap    = QPixmap.fromImage(qimg)

        # Sobrepõe markers se habilitado (já no tamanho redimensionado)
        show_ov = (not hasattr(self, "btn_toggle_overlay") or self.btn_toggle_overlay.isChecked())
        if show_ov and self.df is not None:
            pixmap = self._draw_markers_on_pixmap(pixmap, self._current_frame, scale)

        self.video_scene.clear()
        self.video_scene.addPixmap(pixmap)
        self.video_view.fitInView(self.video_scene.sceneRect(),
                                  Qt.AspectRatioMode.KeepAspectRatio)

        self.video_slider.blockSignals(True)
        self.video_slider.setValue(self._current_frame)
        self.video_slider.blockSignals(False)

        self.video_frame_label.setText(
            f"Frame: {self._current_frame + 1} / {self._total_frames}")

        self._update_video_marker_info()

    def _draw_markers_on_pixmap(self, pixmap, frame_idx, scale=1.0):
        """Desenha marcadores sobre o pixmap do mini-player."""
        if self.df is None:
            return pixmap

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = self._get_selected_markers()

        for mid in self.all_markers:
            x_col, y_col = f"p{mid}_x", f"p{mid}_y"
            if x_col not in self.df.columns:
                continue
            row = self.df[self.df["frame"] == frame_idx]
            if row.empty:
                continue
            x = row[x_col].values[0]
            y = row[y_col].values[0]
            if pd.isna(x) or pd.isna(y):
                continue

            x = float(x) * scale
            y = float(y) * scale

            is_selected = mid in selected
            color = QColor(255, 80, 80) if is_selected else QColor(80, 200, 80)
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), 4, 4)
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QPointF(x + 7, y + 4), str(mid))
            painter.setPen(QPen(color))
            painter.drawText(QPointF(x + 6, y + 3), str(mid))

        painter.end()
        return pixmap

    def _update_video_marker_info(self):
        """Mostra quais markers estão presentes no frame atual."""
        if not hasattr(self, "video_marker_info"):
            return
        if self.df is None:
            self.video_marker_info.setText("")
            return
        row = self.df[self.df["frame"] == self._current_frame]
        if row.empty:
            self.video_marker_info.setText("No data for this frame")
            return
        present = []
        missing = []
        for mid in self.all_markers:
            x = row.get(f"p{mid}_x", [None]).values[0]
            if pd.notna(x):
                present.append(str(mid))
            else:
                missing.append(str(mid))
        txt = f"<b>Present:</b> {', '.join(present) or '—'}"
        if missing:
            txt += f"<br><span style='color:#e53935'><b>Missing:</b> {', '.join(missing)}</span>"
        self.video_marker_info.setText(txt)

    def _seek_video(self, frame):
        """Vai para um frame específico no mini-player."""
        self._current_frame = max(0, min(self._total_frames - 1, frame))
        self._update_video_display()
        self._update_vline()
        self.canvas.draw_idle()

    def _on_video_slider_changed(self, value):
        self._seek_video(value)

    def _video_prev(self):
        self._seek_video(self._current_frame - 1)

    def _video_next(self):
        self._seek_video(self._current_frame + 1)

    def _toggle_video_play(self):
        if self._cap is None:
            return
        self._playing = not self._playing
        if self._playing:
            if hasattr(self, "btn_play_reid"):
                self.btn_play_reid.setText("⏸")
            self._update_video_play_speed()
            self._play_timer.start()
        else:
            self._playing = False
            self._play_timer.stop()
            if hasattr(self, "btn_play_reid"):
                self.btn_play_reid.setText("▶")

    def _update_video_play_speed(self):
        if hasattr(self, "video_speed_spin"):
            fps = self.video_speed_spin.value()
        else:
            fps = 10
        self._play_timer.setInterval(max(1, int(1000 / fps)))

    def _play_tick(self):
        if self._current_frame < self._total_frames - 1:
            self._seek_video(self._current_frame + 1)
        else:
            self._toggle_video_play()

    def _jump_to_range_start(self):
        """Salta o player para o início do range selecionado."""
        start, _ = self.frames_range.getValues()
        if self.frames is not None and start < len(self.frames):
            frame_num = int(self.frames[start])
            self._seek_video(frame_num)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(80, self._update_video_display)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_video_display()

    def closeEvent(self, event):
        """Garante que o vídeo é liberado ao fechar."""
        self._play_timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        super().closeEvent(event)

    # ── Marker list ───────────────────────────────────────────────────────────

    def _update_marker_list_widget(self):
        self.marker_list_widget.blockSignals(True)
        self.marker_list_widget.clear()
        for idx, mid in enumerate(self.all_markers):
            item = QListWidgetItem(f"  Marker {mid}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if self.marker_status[idx] else Qt.CheckState.Unchecked)
            hex_color = self._marker_colors.get(mid)
            if hex_color:
                item.setForeground(QBrush(QColor(hex_color)))
            self.marker_list_widget.addItem(item)
        self.marker_list_widget.blockSignals(False)
        self.marker_list_widget.itemChanged.connect(self._on_marker_check_changed)

    def _on_marker_check_changed(self, item):
        idx = self.marker_list_widget.row(item)
        self.marker_status[idx] = (item.checkState() == Qt.CheckState.Checked)
        self._update_plot()

    def _get_selected_markers(self):
        return [self.all_markers[i] for i, v in enumerate(self.marker_status) if v]

    def _select_all(self):
        self.marker_list_widget.blockSignals(True)
        for i in range(self.marker_list_widget.count()):
            self.marker_status[i] = True
            self.marker_list_widget.item(i).setCheckState(Qt.CheckState.Checked)
        self.marker_list_widget.blockSignals(False)
        self._update_plot()

    def _select_none(self):
        self.marker_list_widget.blockSignals(True)
        for i in range(self.marker_list_widget.count()):
            self.marker_status[i] = False
            self.marker_list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.marker_list_widget.blockSignals(False)
        self._update_plot()

    # ── Operations helpers ────────────────────────────────────────────────────

    def _flash_status(self, msg: str, color: str = "#2DD480"):
        """Mostra mensagem no status_label por 3 segundos."""
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        QTimer.singleShot(3000, lambda: (
            self.status_label.setText(""),
            self.status_label.setStyleSheet("")
        ))

    def _snapshot(self):
        self.temp_history.append(self.df.copy())
        if self.bboxes_df is not None and not self.field_keypoints_mode:
            self.bboxes_temp_history.append(self.bboxes_df.copy())

    def _interpolate(self, df, col, start, end, n_frames):
        method = "pchip" if n_frames > 5 else "linear"
        try:
            df.loc[start:end, col] = df.loc[start:end, col].interpolate(
                method=method, limit_direction="both")
        except Exception:
            df.loc[start:end, col] = df.loc[start:end, col].interpolate(
                method="linear", limit_direction="both")

    # ── Operations ────────────────────────────────────────────────────────────

    def _fill_gaps(self):
        if self.df is None:
            return
        selected = self._get_selected_markers()
        if not selected:
            QMessageBox.information(self, "Info", "Select at least one marker.")
            return
        start, end = self.frames_range.getValues()
        n = end - start + 1
        self._snapshot()

        for mid in selected:
            for col in (f"p{mid}_x", f"p{mid}_y"):
                self._interpolate(self.df, col, start, end, n)
            if self.bboxes_df is not None and not self.field_keypoints_mode:
                cols = [f"p{mid}_{s}" for s in ("xmin", "ymin", "xmax", "ymax")]
                if all(c in self.bboxes_df.columns for c in cols):
                    for col in cols:
                        self._interpolate(self.bboxes_df, col, start, end, n)
        self._update_plot()
        self._flash_status(f"Fill Gaps aplicado em {len(selected)} markers")

    def _merge_markers(self):
        if self.df is None:
            return
        selected = self._get_selected_markers()
        if len(selected) < 2:
            QMessageBox.information(self, "Info", "Select at least two markers to merge.")
            return
        start, end = self.frames_range.getValues()
        self._snapshot()
        target = min(selected)

        for src in selected:
            if src == target:
                continue
            for f in range(start, end + 1):
                for c in ("_x", "_y"):
                    sc, tc = f"p{src}{c}", f"p{target}{c}"
                    if pd.notna(self.df.at[f, sc]):
                        self.df.at[f, tc] = self.df.at[f, sc]
                if self.bboxes_df is not None and not self.field_keypoints_mode:
                    for c in ("_xmin", "_ymin", "_xmax", "_ymax"):
                        sc, tc = f"p{src}{c}", f"p{target}{c}"
                        if sc in self.bboxes_df.columns and tc in self.bboxes_df.columns:
                            if pd.notna(self.bboxes_df.at[f, sc]):
                                self.bboxes_df.at[f, tc] = self.bboxes_df.at[f, sc]

            self.df.drop(columns=[f"p{src}_x", f"p{src}_y"], inplace=True)
            if self.bboxes_df is not None and not self.field_keypoints_mode:
                for c in ("_xmin", "_ymin", "_xmax", "_ymax"):
                    col = f"p{src}{c}"
                    if col in self.bboxes_df.columns:
                        self.bboxes_df.drop(columns=col, inplace=True)

            self._remove_marker_from_state(src)

        self._update_marker_list_widget()
        self._update_plot()
        self._flash_status(f"Merge concluído → marker {target}")

    def _merge_markers_range(self):
        """
        Merge de dois IDs dentro do range selecionado no slider.
        O usuário escolhe qual ID deve continuar (dst) e qual deve ser zerado (src).
        """
        checked = [self.all_markers[i] for i, s in enumerate(self.marker_status) if s]
        if len(checked) != 2:
            QMessageBox.warning(self, "Merge Range",
                "Selecione exatamente 2 markers no painel esquerdo\n"
                "para usar o Merge Range.")
            return

        start_frame, end_frame = self.frames_range.getValues()
        id_a, id_b = checked[0], checked[1]

        # Dialog to pick which ID is the primary (dst)
        dlg = QDialog(self)
        dlg.setWindowTitle("Merge Range — Escolher ID principal")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(_DARK_SS)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        info = QLabel(
            f"Range selecionado: frames {start_frame + 1} – {end_frame + 1}\n\n"
            f"Qual ID deve CONTINUAR existindo nesse range?\n"
            f"(O outro terá seus dados transferidos e será zerado)")
        info.setWordWrap(True)
        info.setStyleSheet("color: #EEEEF8; font-size: 12px;")
        layout.addWidget(info)

        btn_group = QButtonGroup(dlg)
        radio_a = QRadioButton(f"ID {id_a}  →  mantém ID {id_a}, zera ID {id_b}")
        radio_b = QRadioButton(f"ID {id_b}  →  mantém ID {id_b}, zera ID {id_a}")
        radio_a.setChecked(True)
        btn_group.addButton(radio_a)
        btn_group.addButton(radio_b)
        layout.addWidget(radio_a)
        layout.addWidget(radio_b)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dst_id, src_id = (id_a, id_b) if radio_a.isChecked() else (id_b, id_a)

        reply = QMessageBox.question(
            self, "Confirmar Merge Range",
            f"Dentro do range (frames {start_frame + 1}–{end_frame + 1}):\n\n"
            f"• Dados do ID {src_id} → copiados para ID {dst_id} "
            f"(onde ID {dst_id} for NaN)\n"
            f"• ID {src_id} → zerado nesse range\n"
            f"• Fora do range: nenhuma alteração\n\n"
            f"Esta ação pode ser desfeita com Undo.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._snapshot()

        src_x, src_y = f"p{src_id}_x", f"p{src_id}_y"
        dst_x, dst_y = f"p{dst_id}_x", f"p{dst_id}_y"

        if src_x not in self.df.columns or dst_x not in self.df.columns:
            QMessageBox.critical(self, "Erro",
                f"Colunas p{src_id} ou p{dst_id} não encontradas no CSV.")
            if self.temp_history:
                self.temp_history.pop()
            return

        frame_mask = (self.df["frame"] >= start_frame) & (self.df["frame"] <= end_frame)

        copy_mask = frame_mask & self.df[src_x].notna() & self.df[dst_x].isna()
        self.df.loc[copy_mask, dst_x] = self.df.loc[copy_mask, src_x].values
        self.df.loc[copy_mask, dst_y] = self.df.loc[copy_mask, src_y].values

        self.df.loc[frame_mask, src_x] = np.nan
        self.df.loc[frame_mask, src_y] = np.nan

        if self.bboxes_df is not None and not self.field_keypoints_mode:
            bbox_mask = (
                (self.bboxes_df["frame"] >= start_frame) &
                (self.bboxes_df["frame"] <= end_frame)
            )
            for suffix in ("_xmin", "_ymin", "_xmax", "_ymax"):
                sc = f"p{src_id}{suffix}"
                dc = f"p{dst_id}{suffix}"
                if sc not in self.bboxes_df.columns or dc not in self.bboxes_df.columns:
                    continue
                bbox_copy = bbox_mask & self.bboxes_df[sc].notna() & self.bboxes_df[dc].isna()
                self.bboxes_df.loc[bbox_copy, dc] = self.bboxes_df.loc[bbox_copy, sc].values
                self.bboxes_df.loc[bbox_mask, sc] = np.nan

        self._update_plot()
        n_frames = end_frame - start_frame + 1
        self._flash_status(
            f"Merge Range: ID {src_id} → ID {dst_id} "
            f"({n_frames} frames). Undo disponível.")

    def _swap_markers(self):
        if self.df is None:
            return
        selected = self._get_selected_markers()
        if len(selected) != 2:
            QMessageBox.information(self, "Info", "Select exactly two markers.")
            return
        start, end = self.frames_range.getValues()
        self._snapshot()
        m1, m2 = selected

        for f in range(start, end + 1):
            for c in ("_x", "_y"):
                c1, c2 = f"p{m1}{c}", f"p{m2}{c}"
                self.df.at[f, c1], self.df.at[f, c2] = self.df.at[f, c2], self.df.at[f, c1]
            if self.bboxes_df is not None and not self.field_keypoints_mode:
                for c in ("_xmin", "_ymin", "_xmax", "_ymax"):
                    c1, c2 = f"p{m1}{c}", f"p{m2}{c}"
                    if c1 in self.bboxes_df.columns and c2 in self.bboxes_df.columns:
                        self.bboxes_df.at[f, c1], self.bboxes_df.at[f, c2] = (
                            self.bboxes_df.at[f, c2], self.bboxes_df.at[f, c1])
        self._update_plot()
        self._flash_status(f"Swap concluído entre markers {m1} e {m2}")

    def _erase_trajectory(self):
        if self.df is None:
            return
        selected = self._get_selected_markers()
        if not selected:
            return
        start, end = self.frames_range.getValues()
        self._snapshot()

        for m in selected:
            for c in ("_x", "_y"):
                col = f"p{m}{c}"
                if col in self.df.columns:
                    self.df.loc[start:end, col] = float("nan")
            if self.bboxes_df is not None and not self.field_keypoints_mode:
                for c in ("_xmin", "_ymin", "_xmax", "_ymax"):
                    col = f"p{m}{c}"
                    if col in self.bboxes_df.columns:
                        self.bboxes_df.loc[start:end, col] = float("nan")
        self._update_plot()
        self._flash_status(f"Trajetória apagada em {len(selected)} markers", color="#FF9830")

    def _delete_markers(self):
        if self.df is None:
            return
        selected = self._get_selected_markers()
        if not selected:
            return
        self._snapshot()

        for m in selected:
            for c in ("_x", "_y"):
                col = f"p{m}{c}"
                if col in self.df.columns:
                    self.df.drop(columns=col, inplace=True)
            if self.bboxes_df is not None and not self.field_keypoints_mode:
                for c in ("_xmin", "_ymin", "_xmax", "_ymax"):
                    col = f"p{m}{c}"
                    if col in self.bboxes_df.columns:
                        self.bboxes_df.drop(columns=col, inplace=True)
            self._remove_marker_from_state(m)

        self._update_marker_list_widget()
        self._update_plot()
        self._flash_status(f"Markers deletados: {selected}", color="#FF4560")

    def _remove_marker_from_state(self, mid):
        if mid in self.all_markers:
            idx = self.all_markers.index(mid)
            del self.all_markers[idx]
            del self.marker_status[idx]
        for store in (self.lines_x, self.lines_y):
            if mid in store:
                store[mid].remove()
                del store[mid]

    def _undo(self):
        if not self.temp_history:
            QMessageBox.information(self, "Info", "No actions to undo.")
            return
        self.df = self.temp_history.pop().copy()
        if self.bboxes_temp_history and not self.field_keypoints_mode:
            self.bboxes_df = self.bboxes_temp_history.pop().copy()
        self.all_markers   = detect_markers(self.df)
        self.marker_status = [True] * len(self.all_markers)
        self.lines_x, self.lines_y = {}, {}
        self._init_matplotlib_widgets()
        self._update_marker_list_widget()
        n = len(self.df)
        self.frames_range.setRange(0, n - 1)
        self.frames_range.setValues(0, n - 1)
        self.start_frame_spin.setMaximum(n); self.start_frame_spin.setValue(1)
        self.end_frame_spin.setMaximum(n);   self.end_frame_spin.setValue(n)
        self._update_plot()
        self._flash_status("Undo aplicado")

    def _update_and_close(self):
        if self.df is None:
            QMessageBox.warning(self, "No Data", "No marker data to update.")
            return
        self.data_ready.emit(
            self.df.copy(),
            self.bboxes_df.copy() if self.bboxes_df is not None else None)
        self.close()

    # ── Range slider / spin box sync ──────────────────────────────────────────

    def _on_key(self, event):
        start, end = self.frames_range.getValues()
        if event.key == "right" and start + 1 < end:
            self.frames_range.setValues(start + 1, end)
        elif event.key == "left" and start - 1 >= 0:
            self.frames_range.setValues(start - 1, end)

    def _on_start_frame_changed(self, value):
        start, end = self.frames_range.getValues()
        if value - 1 <= end:
            self.frames_range.setValues(value - 1, end)
            self._update_plot()

    def _on_end_frame_changed(self, value):
        start, end = self.frames_range.getValues()
        if value - 1 >= start:
            self.frames_range.setValues(start, value - 1)
            self._update_plot()

    def _on_range_changed(self, start, end):
        self.start_frame_spin.blockSignals(True)
        self.end_frame_spin.blockSignals(True)
        self.start_frame_spin.setValue(start + 1)
        self.end_frame_spin.setValue(end + 1)
        self.start_frame_spin.blockSignals(False)
        self.end_frame_spin.blockSignals(False)
        self._update_plot()


# =============================================================================
# FACTORY
# =============================================================================

def run_reid(video_path=None, project_path=None, current_data=None,
             original_csv_path=None, current_bboxes_data=None):
    return ReIDWindow(
        video_path=video_path,
        project_path=project_path,
        current_data=current_data,
        original_csv_path=original_csv_path,
        current_bboxes_data=current_bboxes_data,
    )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReIDWindow()
    window.show()
    sys.exit(app.exec())


# =============================================================================
# BRIDGE (QML ↔ Python)
# =============================================================================

from PySide6.QtCore import QObject, Slot as _Slot

class ReidManager(QObject):
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
        self._window = ReIDWindow(
            video_path=video_path,
            project_path=project_path,
        )
        # Conecta data_ready para salvar diretamente no CSV do projeto
        self._window.data_ready.connect(self._on_data_ready)
        self._window.show()

    def _on_data_ready(self, df, bboxes_df):
        """Salva o CSV editado diretamente no disco quando aberto pelo manager."""
        import pandas as pd
        import os
        import numpy as np

        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path or df is None:
            return

        stem = os.path.splitext(os.path.basename(video_path))[0]
        base = stem[:-8] if stem.endswith("_tracked") else stem

        # Salva CSV de pixel coordinates
        pixel_dir = os.path.join(project_path, "data", "pixel_coordinates")
        os.makedirs(pixel_dir, exist_ok=True)
        csv_path = os.path.join(pixel_dir, f"{base}_tracked.csv")
        try:
            df.to_csv(csv_path, index=False)
        except Exception as e:
            print(f"[ReidManager] Erro ao salvar CSV: {e}")
            return

        # Salva bboxes se existir
        if bboxes_df is not None:
            bboxes_dir = os.path.join(project_path, "data", "bboxes")
            os.makedirs(bboxes_dir, exist_ok=True)
            bboxes_path = os.path.join(bboxes_dir, f"{base}_bboxes.csv")
            try:
                bboxes_df.to_csv(bboxes_path, index=False)
            except Exception as e:
                print(f"[ReidManager] Erro ao salvar bboxes: {e}")

        print(f"[ReidManager] Salvo: {csv_path}")
