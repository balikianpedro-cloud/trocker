# src/modules/trajectories.py
"""
Trajectories & Heatmap viewer for Trocker.
Standalone window with player filtering, Kalman / Rolling Mean smoothing,
and PNG export.
"""

import os
import json
import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from scipy.ndimage import gaussian_filter

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QInputDialog, QFileDialog, QMessageBox, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QObject, Slot
from PySide6.QtGui import QDoubleValidator

from .reports_plots import PLAYER_COLORS, MPL_LIGHT, SPEED_ZONES


# =============================================================================
# DARK THEME (same as reports.py)
# =============================================================================

_DARK_SS = """
QWidget { background-color: #0D0D14; color: #EEEEF8; font-size: 12px; }
QLabel  { color: #A0A0C0; background: transparent; }
QPushButton {
    background-color: #1D1D2C; color: #A0A0C0;
    border: 1px solid #222230; border-radius: 7px; padding: 6px 14px;
}
QPushButton:hover  { background-color: #242438; color: #EEEEF8; border-color: #303050; }
QPushButton:pressed { background-color: #13213F; color: #C0D8FF; }
QPushButton[role="primary"] {
    background-color: #4282FF; color: #FFFFFF;
    border-color: transparent; font-weight: bold;
}
QPushButton[role="primary"]:hover { background-color: #6098FF; }
QPushButton[role="chip"][active="true"] {
    background-color: #0A2463; color: #FFFFFF; border-color: #4282FF;
}
QPushButton[role="chip"][active="false"] {
    background-color: #1D1D2C; color: #A0A0C0; border-color: #222230;
}
QPushButton[role="chip"]:hover { border-color: #303050; }
QPushButton[role="toggle"][active="true"] {
    background-color: rgba(10,36,99,0.25); color: #C0D8FF; border-color: #4282FF;
}
QPushButton[role="toggle"][active="false"] {
    background-color: #1D1D2C; color: #A0A0C0; border-color: #222230;
}
QPushButton[role="toggle"]:hover { border-color: #303050; color: #EEEEF8; }
QPushButton[role="mode"][active="true"] {
    background-color: #4282FF; color: #FFFFFF; border-color: transparent;
}
QPushButton[role="mode"][active="false"] {
    background-color: #1D1D2C; color: #A0A0C0; border-color: #222230;
}
QLineEdit {
    background-color: #161621; color: #EEEEF8;
    border: 1px solid #222230; border-radius: 6px; padding: 4px 8px;
}
QScrollBar:vertical   { background: #0D0D14; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #222230; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #303050; }
"""


# =============================================================================
# TRAJECTORIES WINDOW
# =============================================================================

class TrajectoriesWindow(QMainWindow):

    def __init__(self, video_path=None, project_path=None):
        super().__init__()
        self.setWindowTitle("Trajectories & Heatmap")
        self.setGeometry(100, 100, 1300, 820)
        self.setStyleSheet(_DARK_SS)

        self.video_path   = video_path
        self.project_path = project_path

        # Data state
        self.df             = None
        self.fps            = 30.0
        self.field_length   = None
        self.field_width    = None
        self.player_names   = {}
        self.all_mids       = []
        self.active_mids    = set()
        self._chip_btns     = {}

        # Filter state
        self._kalman_active  = False
        self._rolling_active = False
        self._rolling_window = 5
        self._df_filtered    = None   # cached filtered dataframe

        # Plot mode: "trajectory" | "heatmap"
        self._mode = "trajectory"

        self._init_ui()
        self._auto_load()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── LEFT PANEL — Players ───────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(180)
        left.setStyleSheet("background-color: #161621; border-right: 1px solid #222230;")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(10, 16, 10, 10)
        left_lay.setSpacing(6)

        lbl_players = QLabel("PLAYERS")
        lbl_players.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold; letter-spacing: 1.2px;")
        left_lay.addWidget(lbl_players)

        # Chips scroll area
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chips_scroll.setStyleSheet("background: transparent;")
        self._chips_widget = QWidget()
        self._chips_widget.setStyleSheet("background: transparent;")
        self._chips_layout = QVBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        self._chips_layout.addStretch(1)
        chips_scroll.setWidget(self._chips_widget)
        left_lay.addWidget(chips_scroll, stretch=1)

        # All / None buttons
        all_none_row = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_all.setFixedHeight(26)
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("None")
        btn_none.setFixedHeight(26)
        btn_none.clicked.connect(self._select_none)
        all_none_row.addWidget(btn_all)
        all_none_row.addWidget(btn_none)
        left_lay.addLayout(all_none_row)

        root.addWidget(left)

        # ── CENTER — Canvas + mode bar ─────────────────────────────────────────
        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)

        # Matplotlib figure
        self._fig = Figure(facecolor="white")
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_lay.addWidget(self._canvas, stretch=1)

        # Mode toggle bar
        mode_bar = QWidget()
        mode_bar.setFixedHeight(44)
        mode_bar.setStyleSheet("background: #161621; border-top: 1px solid #222230;")
        mode_lay = QHBoxLayout(mode_bar)
        mode_lay.setContentsMargins(12, 6, 12, 6)
        mode_lay.setSpacing(8)

        self._btn_traj = QPushButton("📍  Trajectory")
        self._btn_traj.setProperty("role", "mode")
        self._btn_traj.setProperty("active", "true")
        self._btn_traj.setFixedHeight(30)
        self._btn_traj.clicked.connect(lambda: self._set_mode("trajectory"))

        self._btn_heat = QPushButton("🌡  Heatmap")
        self._btn_heat.setProperty("role", "mode")
        self._btn_heat.setProperty("active", "false")
        self._btn_heat.setFixedHeight(30)
        self._btn_heat.clicked.connect(lambda: self._set_mode("heatmap"))

        mode_lay.addStretch()
        mode_lay.addWidget(self._btn_traj)
        mode_lay.addWidget(self._btn_heat)
        mode_lay.addStretch()
        center_lay.addWidget(mode_bar)

        root.addWidget(center, stretch=1)

        # ── RIGHT PANEL — Filters ──────────────────────────────────────────────
        right = QWidget()
        right.setFixedWidth(180)
        right.setStyleSheet("background-color: #161621; border-left: 1px solid #222230;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(10, 16, 10, 10)
        right_lay.setSpacing(8)

        lbl_filters = QLabel("FILTERS")
        lbl_filters.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold; letter-spacing: 1.2px;")
        right_lay.addWidget(lbl_filters)

        # FPS input
        fps_row = QHBoxLayout()
        fps_row.setSpacing(6)
        fps_row.addWidget(QLabel("FPS"))
        self._fps_edit = QLineEdit(f"{self.fps:.2f}")
        self._fps_edit.setFixedHeight(28)
        self._fps_edit.setValidator(QDoubleValidator(1.0, 240.0, 2))
        self._fps_edit.textChanged.connect(self._on_fps_changed)
        fps_row.addWidget(self._fps_edit)
        right_lay.addLayout(fps_row)

        # Kalman toggle
        self._btn_kalman = QPushButton("Kalman Filter")
        self._btn_kalman.setProperty("role", "toggle")
        self._btn_kalman.setProperty("active", "false")
        self._btn_kalman.setFixedHeight(30)
        self._btn_kalman.setCheckable(True)
        self._btn_kalman.clicked.connect(self._toggle_kalman)
        right_lay.addWidget(self._btn_kalman)

        # Rolling Mean toggle
        self._btn_rolling = QPushButton("Rolling Mean")
        self._btn_rolling.setProperty("role", "toggle")
        self._btn_rolling.setProperty("active", "false")
        self._btn_rolling.setFixedHeight(30)
        self._btn_rolling.setCheckable(True)
        self._btn_rolling.clicked.connect(self._toggle_rolling)
        right_lay.addWidget(self._btn_rolling)

        # Status label
        self._lbl_filter_status = QLabel("No filters active")
        self._lbl_filter_status.setWordWrap(True)
        self._lbl_filter_status.setStyleSheet("color: #6868A0; font-size: 10px;")
        right_lay.addWidget(self._lbl_filter_status)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #222230;")
        right_lay.addWidget(sep)

        # Save filter button
        self._btn_save_filter = QPushButton("💾  Salvar Filtro")
        self._btn_save_filter.setFixedHeight(30)
        self._btn_save_filter.setEnabled(False)
        self._btn_save_filter.clicked.connect(self._save_filtered_csv)
        right_lay.addWidget(self._btn_save_filter)

        right_lay.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #222230;")
        right_lay.addWidget(sep2)

        # Save image
        btn_save_img = QPushButton("🖼  Salvar Imagem")
        btn_save_img.setFixedHeight(30)
        btn_save_img.clicked.connect(self._save_image)
        right_lay.addWidget(btn_save_img)

        root.addWidget(right)

    # ── FILTER BUTTONS ────────────────────────────────────────────────────────

    def _set_button_active(self, btn: QPushButton, active: bool):
        btn.setProperty("active", "true" if active else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _toggle_kalman(self):
        self._kalman_active = self._btn_kalman.isChecked()
        self._set_button_active(self._btn_kalman, self._kalman_active)
        self._invalidate_filter()

    def _toggle_rolling(self):
        if not self._rolling_active:
            # Ask for window size
            val, ok = QInputDialog.getInt(
                self, "Rolling Mean", "Window size (frames):",
                self._rolling_window, 3, 20)
            if not ok:
                self._btn_rolling.setChecked(False)
                return
            self._rolling_window = val
        self._rolling_active = self._btn_rolling.isChecked()
        self._set_button_active(self._btn_rolling, self._rolling_active)
        self._invalidate_filter()

    def _on_fps_changed(self, text):
        try:
            v = float(text)
            if v > 0:
                self.fps = v
        except ValueError:
            pass

    def _invalidate_filter(self):
        self._df_filtered = None
        active = []
        if self._kalman_active:
            active.append("Kalman")
        if self._rolling_active:
            active.append(f"Rolling Mean ({self._rolling_window})")
        if active:
            self._lbl_filter_status.setText("Active: " + ", ".join(active))
            self._lbl_filter_status.setStyleSheet("color: #2DD480; font-size: 10px;")
            self._btn_save_filter.setEnabled(True)
        else:
            self._lbl_filter_status.setText("No filters active")
            self._lbl_filter_status.setStyleSheet("color: #6868A0; font-size: 10px;")
            self._btn_save_filter.setEnabled(False)
        self._render()

    # ── PLAYER CHIPS ──────────────────────────────────────────────────────────

    def _populate_chips(self):
        # Remove existing chips (except stretch)
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chip_btns.clear()

        for i, mid in enumerate(self.all_mids):
            color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            name  = self.player_names.get(mid, f"p{mid}")
            btn   = QPushButton(name)
            btn.setProperty("role", "chip")
            btn.setProperty("active", "false")
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                f"QPushButton[role='chip'][active='true'] {{"
                f" border: 2px solid {color}; color: white; background-color: {color}; }}"
                f"QPushButton[role='chip'][active='false'] {{"
                f" border: 1px solid {color}60; color: {color}; background-color: transparent; }}")
            btn.clicked.connect(lambda _, m=mid: self._toggle_chip(m))
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, btn)
            self._chip_btns[mid] = btn

        # Select all by default
        for mid in self.all_mids:
            self._activate_chip(mid, True)

    def _toggle_chip(self, mid: int):
        if mid in self.active_mids:
            self._activate_chip(mid, False)
        else:
            self._activate_chip(mid, True)
        self._render()

    def _activate_chip(self, mid: int, active: bool):
        if active:
            self.active_mids.add(mid)
        else:
            self.active_mids.discard(mid)
        btn = self._chip_btns.get(mid)
        if btn:
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _select_all(self):
        for mid in self.all_mids:
            self._activate_chip(mid, True)
        self._render()

    def _select_none(self):
        for mid in self.all_mids:
            self._activate_chip(mid, False)
        self._render()

    # ── MODE TOGGLE ───────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._set_button_active(self._btn_traj, mode == "trajectory")
        self._set_button_active(self._btn_heat, mode == "heatmap")
        self._render()

    # ── DATA LOADING ──────────────────────────────────────────────────────────

    def _video_stem_base(self):
        stem = os.path.splitext(os.path.basename(self.video_path))[0]
        base = stem[:-8] if stem.endswith("_tracked") else stem
        return stem, base

    def _auto_load(self):
        if not self.project_path or not self.video_path:
            return

        stem, base = self._video_stem_base()
        homog_dir  = os.path.join(self.project_path, "data", "homography")

        # Find CSV
        csv_path = None
        candidates = [
            os.path.join(homog_dir, f"{base}_homography.csv"),
            os.path.join(homog_dir, f"{base}_tracked_homography.csv"),
            os.path.join(homog_dir, f"{stem}_homography.csv"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                csv_path = c
                break
        if csv_path is None and os.path.isdir(homog_dir):
            for f in sorted(os.listdir(homog_dir)):
                if f.startswith(base) and f.endswith("_homography.csv"):
                    csv_path = os.path.join(homog_dir, f)
                    break

        if csv_path is None:
            return

        try:
            self.df  = pd.read_csv(csv_path)
            self._csv_path = csv_path
        except Exception:
            return

        # Detect FPS from video
        try:
            cap = cv2.VideoCapture(self.video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if fps > 0:
                self.fps = fps
                self._fps_edit.setText(f"{fps:.2f}")
        except Exception:
            pass

        # Load field dimensions
        metadata_dir = os.path.join(self.project_path, "metadata")
        for candidate in [
            os.path.join(metadata_dir, f"{base}_homography_matrix.json"),
            os.path.join(metadata_dir, f"{base}_tracked_homography_matrix.json"),
            os.path.join(metadata_dir, f"{stem}_homography_matrix.json"),
        ]:
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fl = data.get("field_length")
                    fw = data.get("field_width")
                    if fl and fw:
                        self.field_length = float(fl)
                        self.field_width  = float(fw)
                except Exception:
                    pass
                break

        # Load player names
        try:
            pjson = os.path.join(metadata_dir, f"{base}_players.json")
            if os.path.isfile(pjson):
                with open(pjson, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                for k, v in pdata.items():
                    mid_key = int(k)
                    if isinstance(v, str):
                        self.player_names[mid_key] = v
                    elif isinstance(v, dict):
                        self.player_names[mid_key] = v.get("name", f"p{mid_key}")
        except Exception:
            pass

        # Detect marker IDs
        self.all_mids = sorted({
            int(c[1:-2]) for c in self.df.columns
            if c.startswith("p") and c.endswith("_x")
        })

        self._populate_chips()
        self._render()

    # ── FILTERS ───────────────────────────────────────────────────────────────

    def _get_filtered_df(self) -> "pd.DataFrame | None":
        if self.df is None:
            return None
        if self._df_filtered is None:
            df = self.df.copy()
            if self._kalman_active:
                df = self._kalman_filter_df(df, self.fps)
            if self._rolling_active:
                df = self._rolling_mean_df(df, self._rolling_window)
            self._df_filtered = df
        return self._df_filtered

    def _apply_kalman(self, data: np.ndarray, fps: float) -> np.ndarray:
        """Kalman filter 2D — ported from Trocker original plot_players.py."""
        if np.all(np.isnan(data)):
            return data

        x_filtered = np.full_like(data, np.nan)

        q_pos, q_vel, r = 0.1, 0.5, 1.0
        dt = 1.0 / fps

        valid_indices = np.where(~np.isnan(data))[0]
        if len(valid_indices) == 0:
            return x_filtered

        first_valid_idx = valid_indices[0]
        state = np.array([data[first_valid_idx], 0.0])

        F = np.array([[1, dt], [0, 1]])
        H = np.array([[1, 0]])
        P = np.array([[1, 0], [0, 10]])
        Q = np.array([[q_pos, 0], [0, q_vel]])
        R_mat = np.array([[r]])

        for i in valid_indices:
            state = F @ state
            P = F @ P @ F.T + Q
            z = np.array([[data[i]]])
            y = z - H @ state
            S = H @ P @ H.T + R_mat
            K = P @ H.T @ np.linalg.inv(S)
            state = state + (K @ y).flatten()
            P = (np.eye(2) - K @ H) @ P
            x_filtered[i] = state[0]

        return x_filtered

    def _kalman_filter_df(self, df: pd.DataFrame, fps: float) -> pd.DataFrame:
        filtered = df.copy()
        for col in df.columns:
            if col.endswith("_x") or col.endswith("_y"):
                data = df[col].values.astype(float)
                if not np.all(np.isnan(data)):
                    filtered[col] = self._apply_kalman(data, fps)
        return filtered

    def _rolling_mean_df(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        filtered = df.copy()
        for col in df.columns:
            if col.endswith("_x") or col.endswith("_y"):
                filtered[col] = df[col].rolling(
                    window=window, center=True, min_periods=1).mean()
        return filtered

    # ── RENDERING ─────────────────────────────────────────────────────────────

    def _render(self):
        df = self._get_filtered_df()
        if df is None or not self.active_mids:
            self._ax.cla()
            self._ax.set_facecolor("white")
            self._ax.text(0.5, 0.5, "No data", transform=self._ax.transAxes,
                          ha="center", va="center", color="#888888", fontsize=14)
            self._canvas.draw()
            return

        with plt.rc_context(MPL_LIGHT):
            if self._mode == "trajectory":
                self._render_trajectory(df)
            else:
                self._render_heatmap(df)
        self._canvas.draw()

    def _draw_field(self, ax):
        if self.field_length and self.field_width:
            rect = mpatches.Rectangle(
                (0, 0), self.field_length, self.field_width,
                linewidth=1.5, edgecolor="#555555", facecolor="none", linestyle="--")
            ax.add_patch(rect)

    def _extract_xy(self, df: pd.DataFrame, mid: int):
        x_col, y_col = f"p{mid}_x", f"p{mid}_y"
        if x_col not in df.columns:
            return None, None
        x = df[x_col].values.astype(float)
        y = df[y_col].values.astype(float)
        valid = ~(np.isnan(x) | np.isnan(y))
        if not np.any(valid):
            return None, None
        return x[valid], y[valid]

    def _render_trajectory(self, df: pd.DataFrame):
        ax = self._ax
        ax.cla()
        ax.set_facecolor("white")
        self._draw_field(ax)

        for i, mid in enumerate([m for m in self.all_mids if m in self.active_mids]):
            x, y = self._extract_xy(df, mid)
            if x is None:
                continue
            color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            name  = self.player_names.get(mid, f"p{mid}")
            ax.plot(x, y, color=color, linewidth=1.8, alpha=0.85, label=name)
            ax.scatter([x[0]],  [y[0]],  color="#16A34A", s=50, zorder=6)
            ax.scatter([x[-1]], [y[-1]], color="#DC2626", s=50, zorder=6)

        ax.set_title("Trajetórias", color="#111111", fontsize=12, fontweight="bold")
        ax.set_xlabel("X (m)", color="#1A1A1A", fontsize=9)
        ax.set_ylabel("Y (m)", color="#1A1A1A", fontsize=9)
        ax.tick_params(labelsize=8, colors="#1A1A1A")
        ax.grid(True, color="#EEEEEE", linewidth=0.8)
        if self.active_mids:
            ax.legend(fontsize=8, facecolor="white", edgecolor="#CCCCCC",
                      labelcolor="#1A1A1A")
        if self.field_length and self.field_width:
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlim(-2, self.field_length + 2)
            ax.set_ylim(-2, self.field_width + 2)
        else:
            ax.set_aspect("equal", adjustable="datalim")
            ax.autoscale()
        self._fig.tight_layout(pad=1.0)

    def _render_heatmap(self, df: pd.DataFrame):
        ax = self._ax
        ax.cla()
        ax.set_facecolor("white")

        all_x, all_y = [], []
        for mid in [m for m in self.all_mids if m in self.active_mids]:
            x, y = self._extract_xy(df, mid)
            if x is not None:
                all_x.extend(x.tolist())
                all_y.extend(y.tolist())

        if not all_x:
            ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                    ha="center", va="center", color="#888888", fontsize=14)
            return

        x_arr = np.array(all_x)
        y_arr = np.array(all_y)

        if self.field_length and self.field_width:
            x_range = [0, self.field_length]
            y_range = [0, self.field_width]
        else:
            x_range = [x_arr.min(), x_arr.max()]
            y_range = [y_arr.min(), y_arr.max()]

        h, xedges, yedges = np.histogram2d(x_arr, y_arr, bins=60,
                                            range=[x_range, y_range])
        h = gaussian_filter(h.T, sigma=2.0)
        extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
        ax.imshow(h, extent=extent, origin="lower", aspect="auto",
                  cmap="hot", interpolation="bilinear")

        self._draw_field(ax)

        ax.set_title("Heatmap Combinado", color="#111111", fontsize=12, fontweight="bold")
        ax.set_xlabel("X (m)", color="#1A1A1A", fontsize=9)
        ax.set_ylabel("Y (m)", color="#1A1A1A", fontsize=9)
        ax.tick_params(labelsize=8, colors="#1A1A1A")
        if self.field_length and self.field_width:
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlim(-2, self.field_length + 2)
            ax.set_ylim(-2, self.field_width + 2)
        self._fig.tight_layout(pad=1.0)

    # ── SAVE ──────────────────────────────────────────────────────────────────

    def _save_image(self):
        if not self.project_path:
            out_dir = os.path.expanduser("~")
        else:
            out_dir = os.path.join(self.project_path, "outputs")
            os.makedirs(out_dir, exist_ok=True)

        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Imagem", os.path.join(out_dir, "trajectories.png"),
            "PNG (*.png);;JPEG (*.jpg)")
        if path:
            self._fig.savefig(path, dpi=150, bbox_inches="tight",
                              facecolor="white")
            QMessageBox.information(self, "Salvo", f"Imagem salva em:\n{path}")

    def _save_filtered_csv(self):
        df = self._get_filtered_df()
        if df is None:
            return
        try:
            csv_path = getattr(self, "_csv_path", None)
            if csv_path is None:
                QMessageBox.warning(self, "Erro", "Caminho do CSV não encontrado.")
                return
            df.to_csv(csv_path, index=False)
            QMessageBox.information(self, "Salvo",
                                    f"CSV filtrado sobrescrito:\n{os.path.basename(csv_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível salvar:\n{e}")

    def closeEvent(self, event):
        plt.close(self._fig)
        event.accept()


# =============================================================================
# QML BRIDGE
# =============================================================================

class TrajectoriesManager(QObject):
    def __init__(self, videos_manager, parent=None):
        super().__init__(parent)
        self._videos_manager = videos_manager
        self._window = None

    @Slot()
    def open_tool(self):
        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path:
            return
        if self._window is not None:
            try:
                self._window.deleteLater()
            except Exception:
                pass
        self._window = TrajectoriesWindow(
            video_path=video_path,
            project_path=project_path,
        )
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
