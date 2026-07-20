# src/modules/athlete_manager.py
"""AthleteWindow + AthleteManager — player profile editor."""

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QObject, Slot

from .player_io import load_player_data, save_player_data, players_json_path


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
QPushButton[role="expand"] {
    background-color: #161621; color: #EEEEF8;
    border: 1px solid #222230; border-radius: 8px;
    padding: 10px 14px; text-align: left; font-weight: bold;
}
QPushButton[role="expand"]:hover { background-color: #1D1D2C; border-color: #303050; }
QPushButton[role="expand"][checked="true"] {
    background-color: #13213F; color: #C0D8FF; border-color: #4282FF;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #161621; color: #EEEEF8;
    border: 1px solid #222230; border-radius: 6px; padding: 4px 8px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #4282FF;
}
QScrollBar:vertical { background: #0D0D14; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #222230; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #303050; }
"""

PLAYER_COLORS = [
    "#2563EB", "#16A34A", "#DC2626", "#D97706",
    "#7C3AED", "#DB2777", "#0891B2", "#65A30D",
    "#EA580C", "#9333EA", "#0D9488", "#B45309",
]


# =============================================================================
# ACCORDION ITEM
# =============================================================================

class AthleteAccordionItem(QWidget):
    """One accordion row: header button that toggles an expanded form."""

    def __init__(self, marker_id: int, profile: dict, color: str, parent=None):
        super().__init__(parent)
        self.marker_id = marker_id
        self.color     = color
        self._expanded = False
        self._setup(profile)

    def _setup(self, profile: dict):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(0)

        # ── Header button ──────────────────────────────────────────────────
        name = profile.get("name", f"p{self.marker_id}")
        self.header = QPushButton(f"  ● {name}")
        self.header.setProperty("role", "expand")
        self.header.setProperty("checked", "false")
        self.header.setStyleSheet(
            f"QPushButton[role='expand'] {{ color: {self.color}; }}")
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header)

        # ── Form (hidden by default) ───────────────────────────────────────
        self.form_widget = QWidget()
        self.form_widget.setStyleSheet(
            "QWidget { background-color: #161621; border: 1px solid #222230;"
            " border-top: none; border-radius: 0 0 8px 8px; }")
        self.form_widget.setVisible(False)
        form_layout = QVBoxLayout(self.form_widget)
        form_layout.setContentsMargins(16, 12, 16, 12)
        form_layout.setSpacing(8)

        # Name
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("Nome:"))
        self.edit_name = QLineEdit(name)
        self.edit_name.setPlaceholderText(f"p{self.marker_id}")
        row_name.addWidget(self.edit_name)
        form_layout.addLayout(row_name)

        # Age
        row_age = QHBoxLayout()
        row_age.addWidget(QLabel("Idade:"))
        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 99)
        self.spin_age.setSpecialValueText("—")
        if profile.get("age"):
            self.spin_age.setValue(int(profile["age"]))
        row_age.addWidget(self.spin_age)
        form_layout.addLayout(row_age)

        # Sex
        row_sex = QHBoxLayout()
        row_sex.addWidget(QLabel("Sexo:"))
        self.combo_sex = QComboBox()
        self.combo_sex.addItems(["—", "M", "F", "Outro"])
        sex_val = profile.get("sex")
        if sex_val in ("M", "F", "Outro"):
            self.combo_sex.setCurrentText(sex_val)
        row_sex.addWidget(self.combo_sex)
        form_layout.addLayout(row_sex)

        # Weight
        row_weight = QHBoxLayout()
        row_weight.addWidget(QLabel("Peso (kg):"))
        self.spin_weight = QDoubleSpinBox()
        self.spin_weight.setRange(0.0, 200.0)
        self.spin_weight.setSingleStep(0.5)
        self.spin_weight.setDecimals(1)
        self.spin_weight.setSpecialValueText("—")
        if profile.get("weight"):
            self.spin_weight.setValue(float(profile["weight"]))
        row_weight.addWidget(self.spin_weight)
        form_layout.addLayout(row_weight)

        # Save button
        self.btn_save = QPushButton("Salvar")
        self.btn_save.setProperty("role", "primary")
        form_layout.addWidget(self.btn_save)

        layout.addWidget(self.form_widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self.form_widget.setVisible(self._expanded)
        self.header.setProperty("checked", "true" if self._expanded else "false")
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)

    def get_profile(self) -> dict:
        age    = self.spin_age.value() or None
        weight = self.spin_weight.value() or None
        sex    = self.combo_sex.currentText()
        sex    = sex if sex in ("M", "F", "Outro") else None
        return {
            "name":   self.edit_name.text().strip() or f"p{self.marker_id}",
            "age":    age,
            "sex":    sex,
            "weight": weight,
        }

    def update_header_name(self, name: str):
        self.header.setText(f"  ● {name}")


# =============================================================================
# ATHLETE WINDOW
# =============================================================================

class AthleteWindow(QMainWindow):
    def __init__(self, video_path: str, project_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Athletes")
        self.setMinimumSize(480, 600)
        self.setStyleSheet(_DARK_SS)

        self.video_path   = video_path
        self.project_path = project_path
        self._items: dict[int, AthleteAccordionItem] = {}

        self._init_ui()
        self._load()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header
        lbl_title = QLabel("Athletes")
        lbl_title.setStyleSheet(
            "color: #EEEEF8; font-size: 22px; font-weight: bold; letter-spacing: 1px;")
        root.addWidget(lbl_title)

        self.lbl_project = QLabel("")
        self.lbl_project.setStyleSheet("color: #6868A0; font-size: 11px;")
        root.addWidget(self.lbl_project)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #222230;")
        root.addWidget(sep)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_content = QWidget()
        self.scroll_layout  = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.addStretch(1)
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, stretch=1)

        # Status label
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #6868A0; font-size: 11px;")
        root.addWidget(self.lbl_status)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load(self):
        if self.project_path:
            self.lbl_project.setText(f"Projeto: {os.path.basename(self.project_path)}")

        # Find marker IDs from the pixel_coordinates CSV
        marker_ids = self._discover_markers()

        if not marker_ids:
            self.lbl_status.setText(
                "Nenhum marcador encontrado.\nRode o Tracker e o Pixel Data primeiro.")
            return

        profiles = load_player_data(self.project_path, self.video_path)

        # Clear old items
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()

        for i, mid in enumerate(sorted(marker_ids)):
            profile = profiles.get(mid, {"name": f"p{mid}", "age": None, "sex": None, "weight": None})
            color   = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            widget  = AthleteAccordionItem(mid, profile, color)
            widget.btn_save.clicked.connect(lambda _, m=mid: self._save_one(m))
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, widget)
            self._items[mid] = widget

        self.lbl_status.setText(f"{len(marker_ids)} atleta(s) carregado(s)")

    def _discover_markers(self) -> list[int]:
        """Find marker IDs from the pixel_coordinates CSV."""
        if not self.project_path or not self.video_path:
            return []
        pixel_dir = os.path.join(self.project_path, "data", "pixel_coordinates")
        if not os.path.isdir(pixel_dir):
            return []
        stem = os.path.splitext(os.path.basename(self.video_path))[0]
        base = stem[:-8] if stem.endswith("_tracked") else stem
        candidates = [
            os.path.join(pixel_dir, f"{base}_tracked.csv"),
            os.path.join(pixel_dir, f"{stem}_tracked.csv"),
        ]
        # fuzzy fallback
        try:
            for f in sorted(os.listdir(pixel_dir)):
                if f.endswith(".csv") and f.startswith(base):
                    candidates.append(os.path.join(pixel_dir, f))
        except OSError:
            pass

        import pandas as pd
        for path in candidates:
            if os.path.isfile(path):
                try:
                    df = pd.read_csv(path, nrows=1)
                    mids = sorted({int(c[1:-2]) for c in df.columns
                                   if c.startswith("p") and c.endswith("_x")})
                    if mids:
                        return mids
                except Exception:
                    pass

        # Fall back to existing JSON keys
        data = load_player_data(self.project_path, self.video_path)
        return sorted(data.keys()) if data else []

    def _save_one(self, marker_id: int):
        item    = self._items.get(marker_id)
        if not item:
            return
        profile = item.get_profile()
        save_player_data(self.project_path, self.video_path, {marker_id: profile})
        item.update_header_name(profile["name"])
        self.lbl_status.setText(f"✓ p{marker_id} salvo")


# =============================================================================
# MANAGER (QML BRIDGE)
# =============================================================================

class AthleteManager(QObject):
    def __init__(self, videos_manager, parent=None):
        super().__init__(parent)
        self._videos_manager = videos_manager
        self._window: AthleteWindow | None = None

    @Slot()
    def open_tool(self):
        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path:
            return
        if self._window is not None:
            self._window.deleteLater()
        self._window = AthleteWindow(video_path=video_path, project_path=project_path)
        self._window.show()

    def get_athlete_profile(self, project_path: str, video_path: str,
                            marker_id: int) -> dict:
        """Returns {"name", "age", "sex", "weight"} for a marker_id (values may be None)."""
        from .player_io import load_player_data
        data    = load_player_data(project_path, video_path)
        profile = data.get(marker_id, {})
        return {
            "name":   profile.get("name",   f"p{marker_id}"),
            "age":    profile.get("age"),
            "sex":    profile.get("sex"),
            "weight": profile.get("weight"),
        }
