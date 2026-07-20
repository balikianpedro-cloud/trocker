# src/modules/reports.py
# Reports module for Trocker — player metrics and visualizations.

import os
import json
import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QScrollArea, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QObject, Slot
from PySide6.QtGui import QColor

from .reports_plots import (
    PlayerMetrics, MPL_LIGHT, PLAYER_COLORS, SPEED_ZONES, _LEGEND_KW,
    plot_speed_over_time, plot_accel_over_time, plot_distance_over_time,
    plot_bar_comparison, plot_zone_bars, _style_ax,
)
from .reports_metrics import calc_sprint_count, calc_vo2max, calc_fatigue_index


# =============================================================================
# WHEEL REDIRECT (scroll area fix)
# =============================================================================

from PySide6.QtCore import QEvent

class _WheelRedirect(QObject):
    def __init__(self, scroll_area):
        super().__init__(scroll_area)
        self._sa = scroll_area
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            self._sa.verticalScrollBar().setValue(
                self._sa.verticalScrollBar().value() -
                event.angleDelta().y() // 2)
            return True
        return False


# =============================================================================
# DARK THEME
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
QPushButton[role="pill"][active="true"] {
    background-color: rgba(10,36,99,0.2); color: #C0D8FF; border-color: #185FA5;
}
QPushButton[role="pill"][active="false"] {
    background-color: #1D1D2C; color: #A0A0C0; border-color: #222230;
}
QPushButton[role="pill"]:hover { border-color: #303050; color: #EEEEF8; }
QScrollBar:vertical   { background: #0D0D14; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #222230; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #303050; }
"""


# =============================================================================
# METRIC REGISTRY
# =============================================================================

_METRICS = {
    "MOVIMENTO": [
        ("distance",        "Distância Total"),
        ("speed_over_time", "Velocidade no Tempo"),
        ("max_speed",       "Velocidade Máxima"),
        ("avg_speed",       "Velocidade Média"),
        ("acceleration",    "Aceleração no Tempo"),
        ("intensity_zones", "Zonas de Intensidade"),
        ("sprint_count",    "Contagem de Sprints"),
    ],
    "FISIOLÓGICO": [
        ("vo2max",        "VO2 Máximo"),
        ("fatigue_index", "Índice de Fadiga"),
    ],
}


# =============================================================================
# REPORTS WINDOW
# =============================================================================

class ReportsWindow(QMainWindow):
    def __init__(self, video_path=None, project_path=None, athlete_manager=None):
        super().__init__()
        self.setWindowTitle("Reports")
        self.setGeometry(80, 80, 1400, 900)
        self.setStyleSheet(_DARK_SS)

        self.video_path      = video_path
        self.project_path    = project_path
        self.athlete_manager = athlete_manager
        self.df              = None
        self.fps             = 24.0
        self.players         = {}
        self.player_names    = {}
        self.field_length    = None
        self.field_width     = None

        self._chip_btns: dict = {}
        self._pill_btns: dict = {}
        self._active_mids: set = set()
        self._active_keys: set = set()

        self._init_ui()
        self._auto_load()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # TOP BAR
        top_bar = QWidget()
        top_bar.setFixedHeight(56)
        top_bar.setStyleSheet("background-color: #161621; border-bottom: 1px solid #222230;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(10)

        self.csv_label = QLabel("Nenhum dado carregado")
        self.csv_label.setStyleSheet("color: #6868A0; font-style: italic; font-size: 11px;")
        top_layout.addWidget(self.csv_label)
        top_layout.addStretch()

        btn_load = QPushButton("Abrir CSV")
        btn_load.clicked.connect(self._open_csv)
        top_layout.addWidget(btn_load)
        root.addWidget(top_bar)

        # PLAYER CHIPS BAR
        self.chips_bar = QWidget()
        self.chips_bar.setFixedHeight(48)
        self.chips_bar.setStyleSheet("background-color: #0D0D14; border-bottom: 1px solid #222230;")
        self.chips_layout = QHBoxLayout(self.chips_bar)
        self.chips_layout.setContentsMargins(16, 0, 16, 0)
        self.chips_layout.setSpacing(8)
        self.chips_layout.addStretch(1)
        root.addWidget(self.chips_bar)

        # BODY
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left panel (200px)
        left = QWidget()
        left.setFixedWidth(200)
        left.setStyleSheet("background-color: #161621; border-right: 1px solid #222230;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 12)
        left_layout.setSpacing(4)

        for group_name, metrics in _METRICS.items():
            lbl = QLabel(group_name)
            lbl.setStyleSheet(
                "color: #6868A0; font-size: 10px; font-weight: bold;"
                " letter-spacing: 1.2px; padding-top: 10px;")
            left_layout.addWidget(lbl)
            for key, label in metrics:
                pill = QPushButton(label)
                pill.setProperty("role", "pill")
                pill.setProperty("active", "false")
                pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                pill.setFixedHeight(28)
                pill.clicked.connect(lambda _, k=key: self._toggle_metric(k))
                left_layout.addWidget(pill)
                self._pill_btns[key] = pill

        left_layout.addStretch(1)
        btn_refresh = QPushButton("Atualizar ↻")
        btn_refresh.setProperty("role", "primary")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self._refresh_selected)
        left_layout.addWidget(btn_refresh)
        body_layout.addWidget(left)

        # Right scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background-color: #0D0D14;")
        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background-color: #0D0D14;")
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(16, 16, 16, 16)
        self._scroll_layout.setSpacing(16)
        self._scroll_layout.addStretch(1)
        self.scroll_area.setWidget(self._scroll_content)
        body_layout.addWidget(self.scroll_area, stretch=1)

        # Redirect wheel events from content area to scroll bar
        self._wheel_redirect = _WheelRedirect(self.scroll_area)
        self._scroll_content.installEventFilter(self._wheel_redirect)

        root.addWidget(body, stretch=1)

    # ── CHIP / PILL TOGGLE ────────────────────────────────────────────────────

    def _toggle_chip(self, mid: int):
        if mid in self._active_mids:
            self._active_mids.discard(mid)
            active = "false"
        else:
            self._active_mids.add(mid)
            active = "true"
        btn = self._chip_btns.get(mid)
        if btn:
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_metric(self, key: str):
        if key in self._active_keys:
            self._active_keys.discard(key)
            active = "false"
        else:
            self._active_keys.add(key)
            active = "true"
        btn = self._pill_btns.get(key)
        if btn:
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

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
        candidates = [
            os.path.join(homog_dir, f"{base}_homography.csv"),
            os.path.join(homog_dir, f"{base}_tracked_homography.csv"),
            os.path.join(homog_dir, f"{stem}_homography.csv"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                self._load_csv(path)
                return
        if os.path.isdir(homog_dir):
            for f in sorted(os.listdir(homog_dir)):
                if f.startswith(base) and f.endswith("_homography.csv"):
                    self._load_csv(os.path.join(homog_dir, f))
                    return

    def _open_csv(self):
        start = os.path.join(self.project_path or "", "data", "homography")
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar CSV de Homografia", start, "CSV Files (*.csv)")
        if path:
            self._load_csv(path)

    def _load_csv(self, path: str):
        try:
            self.df = pd.read_csv(path)
            self.csv_label.setText(f"✓ {os.path.basename(path)}")
            self.csv_label.setStyleSheet("color: #2DD480; font-weight: bold; font-size: 11px;")
            if self.video_path and os.path.isfile(self.video_path):
                cap = cv2.VideoCapture(self.video_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                if fps > 0:
                    self.fps = fps
            self._load_player_names()
            self._load_field_dimensions()
            self._compute_metrics()
            self._populate_chips()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível carregar o CSV:\n{e}")

    def _load_field_dimensions(self):
        self.field_length = None
        self.field_width  = None
        if not self.project_path or not self.video_path:
            return
        stem, base   = self._video_stem_base()
        metadata_dir = os.path.join(self.project_path, "metadata")
        candidates   = [
            os.path.join(metadata_dir, f"{base}_homography_matrix.json"),
            os.path.join(metadata_dir, f"{base}_tracked_homography_matrix.json"),
            os.path.join(metadata_dir, f"{stem}_homography_matrix.json"),
        ]
        if os.path.isdir(metadata_dir):
            for f in os.listdir(metadata_dir):
                if f.startswith(base) and f.endswith("_homography_matrix.json"):
                    p = os.path.join(metadata_dir, f)
                    if p not in candidates:
                        candidates.append(p)
        for path in candidates:
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fl = data.get("field_length")
                    fw = data.get("field_width")
                    if fl and fw:
                        self.field_length = float(fl)
                        self.field_width  = float(fw)
                        return
                except Exception:
                    pass

    def _load_player_names(self):
        self.player_names = {}
        if not self.project_path or not self.video_path:
            return
        _, base = self._video_stem_base()
        path = os.path.join(self.project_path, "metadata", f"{base}_players.json")
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                mid = int(k)
                if isinstance(v, str):
                    self.player_names[mid] = v
                elif isinstance(v, dict):
                    self.player_names[mid] = v.get("name", f"p{mid}")
        except Exception:
            pass

    def _compute_metrics(self):
        if self.df is None:
            return
        mids = sorted({int(c[1:-2]) for c in self.df.columns
                       if c.startswith("p") and c.endswith("_x")})
        self.players = {}
        for mid in mids:
            x    = self.df[f"p{mid}_x"].values
            y    = self.df[f"p{mid}_y"].values
            name = self.player_names.get(mid, f"p{mid}")
            p    = PlayerMetrics(mid, x, y, self.fps, name)
            p.sprint_count = calc_sprint_count(p.speed_kmh, self.fps)
            self.players[mid] = p

    def _populate_chips(self):
        while self.chips_layout.count() > 1:
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chip_btns.clear()
        self._active_mids.clear()

        # Botões All / None no início
        btn_all = QPushButton("All")
        btn_all.setFixedHeight(30)
        btn_all.setFixedWidth(40)
        btn_all.setStyleSheet(
            "QPushButton { background: #1D1D2C; color: #A0A0C0; border: 1px solid #222230;"
            " border-radius: 6px; font-size: 11px; }"
            "QPushButton:hover { color: #EEEEF8; background: #242438; }")
        btn_all.clicked.connect(self._select_all_chips)
        self.chips_layout.insertWidget(0, btn_all)

        btn_none = QPushButton("None")
        btn_none.setFixedHeight(30)
        btn_none.setFixedWidth(44)
        btn_none.setStyleSheet(
            "QPushButton { background: #1D1D2C; color: #A0A0C0; border: 1px solid #222230;"
            " border-radius: 6px; font-size: 11px; }"
            "QPushButton:hover { color: #EEEEF8; background: #242438; }")
        btn_none.clicked.connect(self._select_none_chips)
        self.chips_layout.insertWidget(1, btn_none)

        # Separador fino
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #222230;")
        sep.setFixedWidth(1)
        self.chips_layout.insertWidget(2, sep)

        for i, (mid, p) in enumerate(self.players.items()):
            color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            btn   = QPushButton(p.name)
            btn.setProperty("role", "chip")
            btn.setProperty("active", "false")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                f"QPushButton[role='chip'][active='true'] {{"
                f" border: 2px solid {color}; color: white;"
                f" background-color: {color}; }}"
                f"QPushButton[role='chip'][active='false'] {{"
                f" border: 1px solid {color}60; color: {color};"
                f" background-color: transparent; }}")
            btn.clicked.connect(lambda _, m=mid: self._toggle_chip(m))
            self.chips_layout.insertWidget(self.chips_layout.count() - 1, btn)
            self._chip_btns[mid] = btn

        for mid in self.players:
            self._toggle_chip(mid)

    def _select_all_chips(self):
        for mid in list(self.players.keys()):
            if mid not in self._active_mids:
                self._toggle_chip(mid)

    def _select_none_chips(self):
        for mid in list(self._active_mids.copy()):
            self._toggle_chip(mid)

    # ── RENDERING ─────────────────────────────────────────────────────────────

    def _get_active_players(self) -> list:
        return [self.players[mid] for mid in sorted(self._active_mids)
                if mid in self.players]

    def _clear_scroll(self):
        plt.close("all")
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _make_canvas_widget(self, render_fn, figsize=(12, 4)) -> QWidget:
        with plt.rc_context(MPL_LIGHT):
            fig = Figure(figsize=figsize, facecolor="white")
            ax  = fig.add_subplot(111)
            render_fn(fig, ax)
            fig.tight_layout()
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(320)
        return canvas

    def _make_vo2max_widget(self, players: list, protocol_config: dict) -> QWidget:
        from math import ceil
        from PySide6.QtWidgets import QGridLayout
        container = QWidget()
        container.setStyleSheet(
            "QWidget { background-color: #161621; border-radius: 10px; }")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("VO2 Máximo")
        lbl.setStyleSheet("color: #EEEEF8; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl)

        COLS = 4
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, p in enumerate(players):
            profile = {}
            if self.athlete_manager:
                try:
                    profile = self.athlete_manager.get_athlete_profile(
                        self.project_path, self.video_path, p.marker_id)
                except Exception:
                    pass
            result = calc_vo2max(
                total_distance_m  = p.total_distance,
                age               = profile.get("age"),
                sex               = profile.get("sex"),
                protocol          = protocol_config["protocol"],
                endurance_level   = protocol_config.get("level"),
                endurance_shuttle = protocol_config.get("shuttle"),
            )
            color = PLAYER_COLORS[i % len(PLAYER_COLORS)]

            card = QWidget()
            card.setStyleSheet(
                "QWidget { background-color: #1D1D2C; border: 1px solid #222230;"
                " border-radius: 8px; }")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)

            lbl_name = QLabel(p.name)
            lbl_name.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
            card_layout.addWidget(lbl_name)

            val_text = f"{result['value']:.1f}" if result["value"] is not None else "—"
            lbl_val = QLabel(val_text)
            lbl_val.setStyleSheet(
                f"color: {result['color']}; font-size: 28px; font-weight: bold;")
            card_layout.addWidget(lbl_val)

            lbl_unit = QLabel("ml/kg/min")
            lbl_unit.setStyleSheet("color: #6868A0; font-size: 9px;")
            card_layout.addWidget(lbl_unit)

            lbl_cls = QLabel(result["classification"])
            lbl_cls.setStyleSheet(
                f"color: {result['color']}; font-weight: bold; font-size: 11px;")
            card_layout.addWidget(lbl_cls)

            formula_text = result.get("formula", "")
            if formula_text:
                lbl_formula = QLabel(formula_text)
                lbl_formula.setStyleSheet("color: #6868A0; font-size: 9px;")
                card_layout.addWidget(lbl_formula)

            if result.get("warning"):
                lbl_warn = QLabel(f"⚠ {result['warning']}")
                lbl_warn.setWordWrap(True)
                lbl_warn.setStyleSheet("color: #D97706; font-size: 9px;")
                card_layout.addWidget(lbl_warn)

            grid.addWidget(card, i // COLS, i % COLS)

        layout.addLayout(grid)
        return container

    def _make_fatigue_widget(self, players: list) -> QWidget:
        def _render(fig, ax):
            names  = [p.name  for p in players]
            res    = [calc_fatigue_index(p.speed_kmh) for p in players]
            values = [r["value"] for r in res]
            colors = [r["color"] for r in res]
            y_pos  = range(len(names))
            ax.barh(list(y_pos), values, color=colors, alpha=0.88,
                    edgecolor="white", linewidth=0.5)
            ax.set_yticks(list(y_pos))
            ax.set_yticklabels(names, fontsize=9, color="#1A1A1A")
            ax.axvline(10, color="#D97706", linewidth=0.8, linestyle="--", alpha=0.7)
            ax.axvline(20, color="#DC2626", linewidth=0.8, linestyle="--", alpha=0.7)
            for i, v in enumerate(values):
                ax.text(v + 0.3, i, f"{v:.1f}%", va="center",
                        color="#1A1A1A", fontsize=8)
            _style_ax(ax, "Índice de Fadiga", "%", "",
                      legend=False, grid_axis="x", clean_spines=True)

        h = max(3, len(players) * 0.8 + 1)
        return self._make_canvas_widget(_render, figsize=(10, h))

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #6868A0; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1.2px; padding: 4px 0 2px 0;")
        return lbl

    def _render_metric(self, key: str, players: list,
                       protocol_config: dict | None = None) -> QWidget:
        if key == "distance":
            return self._make_canvas_widget(
                lambda fig, ax: plot_bar_comparison(
                    players, "total_distance", "Distance (m)", "Distância Total", ax))
        if key == "speed_over_time":
            return self._make_canvas_widget(
                lambda fig, ax: plot_speed_over_time(players, ax))
        if key == "max_speed":
            return self._make_canvas_widget(
                lambda fig, ax: plot_bar_comparison(
                    players, "max_speed_kmh", "Speed (km/h)", "Velocidade Máxima", ax))
        if key == "avg_speed":
            return self._make_canvas_widget(
                lambda fig, ax: plot_bar_comparison(
                    players, "avg_speed_kmh", "Speed (km/h)", "Velocidade Média", ax))
        if key == "acceleration":
            return self._make_canvas_widget(
                lambda fig, ax: plot_accel_over_time(players, ax))
        if key == "intensity_zones":
            return self._make_canvas_widget(
                lambda fig, ax: plot_zone_bars(players, ax))
        if key == "sprint_count":
            return self._make_canvas_widget(
                lambda fig, ax: plot_bar_comparison(
                    players, "sprint_count", "Sprints", "Contagem de Sprints", ax))
        if key == "vo2max":
            return self._make_vo2max_widget(players, protocol_config)
        if key == "fatigue_index":
            return self._make_fatigue_widget(players)
        return QLabel(f"Métrica '{key}' não implementada.")

    def _refresh_selected(self):
        players = self._get_active_players()
        self._clear_scroll()

        if not players:
            lbl = QLabel("Selecione players e métricas, depois clique em Atualizar ↻")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #6868A0; font-size: 13px; padding: 40px;")
            self._scroll_layout.insertWidget(0, lbl)
            return

        if not self._active_keys:
            lbl = QLabel("Selecione pelo menos uma métrica no painel esquerdo.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #6868A0; font-size: 13px; padding: 40px;")
            self._scroll_layout.insertWidget(0, lbl)
            return

        # Se vo2max está selecionado, perguntar protocolo UMA vez antes de renderizar
        active_metric_keys = self._active_keys
        protocol_config = None
        if "vo2max" in active_metric_keys:
            protocol_config = _ask_vo2max_protocol(self)
            if protocol_config is None:
                return  # usuário cancelou

        idx = 0
        mov_keys = [k for k, _ in _METRICS["MOVIMENTO"] if k in active_metric_keys]
        if mov_keys:
            self._scroll_layout.insertWidget(idx, self._section_label("MOVIMENTO"))
            idx += 1
        for key in mov_keys:
            try:
                widget = self._render_metric(key, players, protocol_config)
            except Exception as e:
                widget = QLabel(f"[Erro: {key} — {e}]")
                widget.setStyleSheet("color: #DC2626; padding: 8px;")
            self._scroll_layout.insertWidget(idx, widget)
            idx += 1

        fis_keys = [k for k, _ in _METRICS["FISIOLÓGICO"] if k in active_metric_keys]
        if fis_keys:
            self._scroll_layout.insertWidget(idx, self._section_label("FISIOLÓGICO"))
            idx += 1
        for key in fis_keys:
            try:
                widget = self._render_metric(key, players, protocol_config)
            except Exception as e:
                widget = QLabel(f"[Erro: {key} — {e}]")
                widget.setStyleSheet("color: #DC2626; padding: 8px;")
            self._scroll_layout.insertWidget(idx, widget)
            idx += 1

    def _refresh(self):
        self._refresh_selected()

    def closeEvent(self, event):
        plt.close("all")
        super().closeEvent(event)


# =============================================================================
# VO₂max PROTOCOL DIALOG  (module-level helper, no self)
# =============================================================================

def _ask_vo2max_protocol(parent):
    """
    Diálogo de seleção de protocolo Yo-Yo para cálculo de VO₂max.
    Retorna dict {"protocol": str, "level": int|None, "shuttle": int|None}
    ou None se cancelar.
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
        QButtonGroup, QSpinBox, QDialogButtonBox, QWidget, QFrame
    )

    dlg = QDialog(parent)
    dlg.setWindowTitle("Configurar cálculo de VO₂max")
    dlg.setMinimumWidth(420)
    dlg.setStyleSheet("""
        QWidget { background-color: #0D0D14; color: #EEEEF8; font-size: 12px; }
        QLabel { color: #A0A0C0; }
        QRadioButton { color: #EEEEF8; padding: 6px; }
        QRadioButton::indicator { width: 16px; height: 16px; border-radius: 8px;
            border: 2px solid #303050; background: #161621; }
        QRadioButton::indicator:checked { background: #4282FF; border-color: #4282FF; }
        QSpinBox { background: #161621; color: #EEEEF8; border: 1px solid #222230;
            border-radius: 6px; padding: 4px 8px; }
        QFrame[frameShape="4"] { color: #222230; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)
    layout.setContentsMargins(20, 20, 20, 20)

    lbl = QLabel("Selecione o protocolo Yo-Yo aplicado no teste:")
    lbl.setStyleSheet("color: #EEEEF8; font-weight: bold; font-size: 13px;")
    layout.addWidget(lbl)

    sublbl = QLabel("Idade e sexo serão buscados automaticamente do cadastro de atletas.")
    sublbl.setStyleSheet("color: #6868A0; font-size: 11px;")
    layout.addWidget(sublbl)

    sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
    layout.addWidget(sep)

    btn_group = QButtonGroup(dlg)
    protocols = [
        ("ir1",       "Yo-Yo Intermittent Recovery Level 1  (IR1)",
                      "Mais comum · jovens e recreativos · fórmula: dist × 0.0084 + 36.4"),
        ("ir2",       "Yo-Yo Intermittent Recovery Level 2  (IR2)",
                      "Elite · fórmula: dist × 0.0136 + 45.3"),
        ("endurance", "Yo-Yo Endurance  (IE1 / IE2)",
                      "Endurance · requer nível e shuttle atingidos"),
    ]
    radios = {}
    endurance_widget = QWidget()
    end_layout = QHBoxLayout(endurance_widget)
    end_layout.setContentsMargins(24, 0, 0, 0)
    end_layout.addWidget(QLabel("Nível:"))
    spin_level   = QSpinBox(); spin_level.setRange(5, 21); spin_level.setValue(9)
    end_layout.addWidget(spin_level)
    end_layout.addWidget(QLabel("Shuttle:"))
    spin_shuttle = QSpinBox(); spin_shuttle.setRange(1, 16); spin_shuttle.setValue(2)
    end_layout.addWidget(spin_shuttle)
    end_layout.addStretch()
    endurance_widget.setVisible(False)

    for key, title, subtitle in protocols:
        rb = QRadioButton(title)
        rb.setStyleSheet("QRadioButton { font-weight: 500; }")
        sub = QLabel(subtitle)
        sub.setStyleSheet("color: #6868A0; font-size: 10px; padding-left: 28px;")
        btn_group.addButton(rb)
        radios[key] = rb
        layout.addWidget(rb)
        layout.addWidget(sub)
        if key == "endurance":
            layout.addWidget(endurance_widget)

    radios["ir1"].setChecked(True)

    def on_toggle():
        endurance_widget.setVisible(radios["endurance"].isChecked())
        dlg.adjustSize()

    for rb in radios.values():
        rb.toggled.connect(on_toggle)

    sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
    layout.addWidget(sep2)

    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    protocol = next(k for k, rb in radios.items() if rb.isChecked())
    return {
        "protocol": protocol,
        "level":    spin_level.value()   if protocol == "endurance" else None,
        "shuttle":  spin_shuttle.value() if protocol == "endurance" else None,
    }


# =============================================================================
# FACTORY + BRIDGE
# =============================================================================

def run_reports(video_path=None, project_path=None):
    return ReportsWindow(video_path=video_path, project_path=project_path)


class ReportsManager(QObject):
    def __init__(self, videos_manager, athlete_manager=None, parent=None):
        super().__init__(parent)
        self._videos_manager  = videos_manager
        self._athlete_manager = athlete_manager
        self._window = None

    @Slot()
    def open_tool(self):
        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path:
            return
        if self._window is not None:
            self._window.deleteLater()
        self._window = ReportsWindow(
            video_path=video_path,
            project_path=project_path,
            athlete_manager=self._athlete_manager,
        )
        self._window.show()
