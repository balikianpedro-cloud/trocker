import os
import json
import cv2
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsScene, QGraphicsPolygonItem, QMessageBox
)
from PySide6.QtGui import QPixmap, QImage, QColor, QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF, QEventLoop, Signal

from modules.edit_video import InteractiveFrameView


class TriggerZoneSelector(QWidget):
    """Janela para o usuário desenhar um polígono de trigger zone no frame do vídeo."""
    closed = Signal()   # emitido quando a janela fechar (confirm ou X)

    def __init__(self, frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Definir Trigger Zone")
        self.setWindowFlags(Qt.WindowType.Window)
        self.confirmed = False
        self.points    = []
        self.polygon_item = None

        h, w = frame.shape[:2]
        self.setMinimumSize(min(w, 1280), min(h, 720) + 50)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # View interativa (zoom + pan)
        self.scene = QGraphicsScene()
        self.view  = InteractiveFrameView()
        self.view.setScene(self.scene)
        layout.addWidget(self.view, stretch=1)

        # Converte frame BGR → QPixmap
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h2, w2, ch = rgb.shape
        qimg = QImage(rgb.data, w2, h2, ch * w2, QImage.Format.Format_RGB888)
        self.pixmap = QPixmap.fromImage(qimg)
        self._pix_item = self.scene.addPixmap(self.pixmap)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # Barra de botões
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 8, 8)
        self.lbl = QLabel("Clique para adicionar pontos (mínimo 3). Scroll=zoom, Middle=pan.")
        bar.addWidget(self.lbl, stretch=1)
        btn_reset = QPushButton("Resetar")
        btn_reset.clicked.connect(self._reset)
        bar.addWidget(btn_reset)
        btn_confirm = QPushButton("Confirmar Zona")
        btn_confirm.clicked.connect(self._confirm)
        bar.addWidget(btn_confirm)
        layout.addLayout(bar)

        self._setup_scene_click()

    def _setup_scene_click(self):
        original = self.scene.mousePressEvent
        def on_click(event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.points.append(event.scenePos())
                self._draw()
            original(event)
        self.scene.mousePressEvent = on_click

    def _draw(self):
        if self.polygon_item:
            self.scene.removeItem(self.polygon_item)
            self.polygon_item = None
        if len(self.points) < 2:
            return
        poly = QPolygonF(self.points)
        self.polygon_item = QGraphicsPolygonItem(poly)
        self.polygon_item.setPen(QPen(QColor("#0A2463"), 2))
        self.polygon_item.setBrush(QColor(10, 36, 99, 50))
        self.scene.addItem(self.polygon_item)
        self.lbl.setText(f"{len(self.points)} ponto(s) marcado(s)")

    def _reset(self):
        self.points.clear()
        if self.polygon_item:
            self.scene.removeItem(self.polygon_item)
            self.polygon_item = None
        self.lbl.setText("Resetado. Clique para adicionar pontos.")

    def _confirm(self):
        if len(self.points) < 3:
            QMessageBox.warning(self, "Pontos insuficientes",
                                "Marque pelo menos 3 pontos para definir a zona.")
            return
        self.confirmed = True
        self.close()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def get_polygon_pixels(self) -> np.ndarray | None:
        """Retorna pontos em coordenadas de pixel do frame original (não da scene)."""
        if not self.points:
            return None
        # A scene tem o mesmo tamanho do pixmap original
        return np.array([(p.x(), p.y()) for p in self.points], dtype=np.float32)


# ── Funções utilitárias ────────────────────────────────────────────────────────

def _video_base(video_path: str) -> str:
    """Retorna o stem do vídeo sem sufixo _tracked."""
    stem = os.path.splitext(os.path.basename(video_path))[0]
    return stem[:-8] if stem.endswith("_tracked") else stem


def _find_homography_csv(video_path: str, project_path: str) -> str | None:
    stem = os.path.splitext(os.path.basename(video_path))[0]
    base = _video_base(video_path)
    hdir = os.path.join(project_path, "data", "homography")
    for name in [f"{stem}_homography.csv", f"{base}_homography.csv"]:
        p = os.path.join(hdir, name)
        if os.path.isfile(p):
            return p
    return None


def _find_homography_json(video_path: str, project_path: str) -> str | None:
    stem = os.path.splitext(os.path.basename(video_path))[0]
    base = _video_base(video_path)
    mdir = os.path.join(project_path, "metadata")
    for name in [f"{stem}_homography_matrix.json",
                 f"{base}_homography_matrix.json"]:
        p = os.path.join(mdir, name)
        if os.path.isfile(p):
            return p
    return None


def _zone_path(video_path: str, project_path: str) -> str:
    base = _video_base(video_path)
    return os.path.join(project_path, "metadata", f"{base}_trigger_zone.json")


def zone_exists(video_path: str, project_path: str) -> bool:
    return os.path.isfile(_zone_path(video_path, project_path))


def save_zone(video_path: str, project_path: str, polygon_px: np.ndarray):
    path = _zone_path(video_path, project_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"polygon_pixels": polygon_px.tolist()}, f)


def load_zone(video_path: str, project_path: str) -> np.ndarray | None:
    path = _zone_path(video_path, project_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return np.array(data["polygon_pixels"], dtype=np.float32)


# ── Fluxo principal ────────────────────────────────────────────────────────────

def select_trigger_zone(video_path: str, project_path: str,
                        parent=None) -> bool:
    """
    Abre o seletor de zona, salva em JSON e retorna True se confirmado.
    Chamado pela HomographyWindow.
    """
    if not video_path or not os.path.exists(video_path):
        QMessageBox.warning(parent, "Sem vídeo", "Selecione um vídeo primeiro.")
        return False

    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        QMessageBox.critical(parent, "Erro",
                             "Não foi possível ler o frame do vídeo.")
        return False

    selector = TriggerZoneSelector(frame, parent=parent)
    selector.show()
    selector.raise_()
    selector.activateWindow()

    loop = QEventLoop()
    selector.closed.connect(loop.quit)
    loop.exec()

    if not selector.confirmed:
        return False

    polygon_px = selector.get_polygon_pixels()
    if polygon_px is None:
        return False

    save_zone(video_path, project_path, polygon_px)
    QMessageBox.information(
        parent, "Zona definida",
        f"Trigger zone salva com {len(polygon_px)} pontos.\n"
        "Clique em 'Aplicar Trigger Zone' para filtrar os dados."
    )
    return True


def apply_trigger_zone(video_path: str, project_path: str,
                       parent=None) -> bool:
    """
    Lê o CSV de homografia, zera NaN os pontos fora da trigger zone
    e salva no mesmo arquivo. Retorna True se bem-sucedido.
    """
    # Verifica pré-requisitos
    homography_csv = _find_homography_csv(video_path, project_path)
    if not homography_csv:
        QMessageBox.warning(parent, "Sem dados",
                            "CSV de homografia não encontrado.\n"
                            "Execute a homografia primeiro.")
        return False

    homography_json = _find_homography_json(video_path, project_path)
    if not homography_json:
        QMessageBox.warning(parent, "Sem matriz",
                            "JSON da matriz de homografia não encontrado.")
        return False

    polygon_px = load_zone(video_path, project_path)
    if polygon_px is None:
        QMessageBox.warning(parent, "Sem zona",
                            "Defina a trigger zone primeiro.")
        return False

    # Transforma polígono de pixels → coordenadas reais (metros)
    with open(homography_json, "r", encoding="utf-8") as f:
        params = json.load(f)
    h_matrix = np.array(params["homography_matrix"], dtype=np.float32)
    polygon_real = cv2.perspectiveTransform(
        polygon_px[None, :, :], h_matrix)[0]

    # Filtra CSV — pontos fora da zona viram NaN
    df = pd.read_csv(homography_csv)
    players = sorted({c[1:-2] for c in df.columns
                      if c.startswith("p") and c.endswith("_x")})
    total_cleared = 0
    for pid in players:
        x_col, y_col = f"p{pid}_x", f"p{pid}_y"
        if x_col not in df.columns:
            continue
        for idx in df.index:
            x, y = df.at[idx, x_col], df.at[idx, y_col]
            if pd.notna(x) and pd.notna(y):
                inside = cv2.pointPolygonTest(
                    polygon_real, (float(x), float(y)), False) >= 0
                if not inside:
                    df.at[idx, x_col] = np.nan
                    df.at[idx, y_col] = np.nan
                    total_cleared += 1

    df.to_csv(homography_csv, index=False)
    QMessageBox.information(
        parent, "Pronto",
        f"Trigger zone aplicada.\n"
        f"{total_cleared} pontos removidos fora da zona.\n"
        f"CSV atualizado: {os.path.basename(homography_csv)}"
    )
    return True


def open_trigger_zone_viewer(video_path: str, project_path: str, parent=None):
    """
    Abre visualizador do vídeo com trigger zone e jogadores filtrados.
    Só disponível quando zone_exists() e CSV de pixel_coordinates existirem.
    """
    import pandas as pd
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSlider, QPushButton, QLabel, QApplication, QGraphicsScene
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygon, QImage, QPixmap
    from PySide6.QtCore import QPoint
    from modules.edit_video import InteractiveFrameView

    # ── Pré-requisitos ────────────────────────────────────────────────────
    polygon_px = load_zone(video_path, project_path)
    if polygon_px is None:
        QMessageBox.warning(parent, "Sem zona",
                            "Defina a trigger zone primeiro.")
        return

    # Encontra CSV de pixel_coordinates
    pixel_dir = os.path.join(project_path, "data", "pixel_coordinates")
    stem = os.path.splitext(os.path.basename(video_path))[0]
    base = stem[:-8] if stem.endswith("_tracked") else stem
    csv_path = None
    for candidate in [
        os.path.join(pixel_dir, f"{base}_tracked.csv"),
        os.path.join(pixel_dir, f"{stem}_tracked.csv"),
    ]:
        if os.path.isfile(candidate):
            csv_path = candidate
            break
    if csv_path is None:
        # fuzzy fallback
        try:
            for f in sorted(os.listdir(pixel_dir)):
                if f.endswith(".csv") and f.startswith(base):
                    csv_path = os.path.join(pixel_dir, f)
                    break
        except OSError:
            pass
    if csv_path is None:
        QMessageBox.warning(parent, "Sem dados",
                            "CSV de pixel_coordinates não encontrado.\n"
                            "Execute o Tracker e o Pixel Data primeiro.")
        return

    df = pd.read_csv(csv_path, engine="python", on_bad_lines="skip")
    marker_ids = sorted({int(c[1:-2]) for c in df.columns
                         if c.startswith("p") and c.endswith("_x")})

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        QMessageBox.critical(parent, "Erro", "Não foi possível abrir o vídeo.")
        return
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_video    = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Paleta de cores para jogadores
    COLORS = [
        (37, 99, 235), (22, 163, 74), (220, 38, 38), (217, 119, 6),
        (124, 58, 237), (219, 39, 119), (8, 145, 178), (101, 163, 13),
    ]

    # Polígono como lista de QPoint para desenho e teste
    poly_qpoints = [QPoint(int(p[0]), int(p[1])) for p in polygon_px]
    poly_q = QPolygon(poly_qpoints)

    # ── Janela ────────────────────────────────────────────────────────────
    win = QMainWindow(parent)
    win.setWindowTitle("Trigger Zone Viewer")
    win.setMinimumSize(1000, 650)
    win.setStyleSheet("QWidget { background-color: #0D0D14; color: #EEEEF8; }")

    central = QWidget()
    win.setCentralWidget(central)
    root = QVBoxLayout(central)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # Label de vídeo (substituído por InteractiveFrameView)
    scene = QGraphicsScene()
    view = InteractiveFrameView()
    view.setScene(scene)
    view.setStyleSheet("background: #000; border: none;")
    root.addWidget(view, stretch=1)
    
    # Item fixo para evitar recriar pixmaps a todo momento
    pixmap_item = scene.addPixmap(QPixmap())

    # Controles
    ctrl_bar = QWidget()
    ctrl_bar.setStyleSheet("background: #161621; border-top: 1px solid #222230;")
    ctrl_bar.setFixedHeight(52)
    ctrl = QHBoxLayout(ctrl_bar)
    ctrl.setContentsMargins(12, 8, 12, 8)
    ctrl.setSpacing(8)

    btn_play  = QPushButton("▶  Play")
    btn_play.setFixedWidth(100)
    btn_play.setStyleSheet(
        "QPushButton { background: #1D1D2C; color: #A0A0C0; border: 1px solid #222230;"
        " border-radius: 6px; padding: 4px 10px; }"
        "QPushButton:hover { color: #EEEEF8; background: #242438; }")

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, max(0, total_frames - 1))
    slider.setStyleSheet(
        "QSlider::groove:horizontal { height:4px; background:#222230; border-radius:2px; }"
        "QSlider::handle:horizontal { background:#4282FF; width:14px; height:14px;"
        " margin:-5px 0; border-radius:7px; }"
        "QSlider::sub-page:horizontal { background:#4282FF; border-radius:2px; }")

    lbl_frame = QLabel("Frame 1")
    lbl_frame.setStyleSheet("color: #6868A0; font-size: 11px; min-width: 80px;")

    lbl_zone = QLabel("Zona ativa")
    lbl_zone.setStyleSheet(
        "color: #2DD480; font-size: 11px; font-weight: bold; padding: 2px 8px;"
        " background: rgba(45,212,128,0.1); border-radius: 4px;")

    ctrl.addWidget(btn_play)
    ctrl.addWidget(slider, stretch=1)
    ctrl.addWidget(lbl_frame)
    ctrl.addWidget(lbl_zone)
    root.addWidget(ctrl_bar)
    # ── Estado ────────────────────────────────────────────────────────────
    state = {"frame": 0, "playing": False, "first_render": True}
    timer = QTimer()
    timer.setInterval(max(16, int(1000 / fps_video)))

    def render(frame_idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            return

        h, w = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg  = QImage(frame_rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Desenha polígono da trigger zone
        pen = QPen(QColor("#0A2463"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor(10, 36, 99, 40))
        painter.drawPolygon(poly_q)

        # Busca dados do frame
        row = df[df["frame"] == frame_idx]

        for i, mid in enumerate(marker_ids):
            x_col, y_col = f"p{mid}_x", f"p{mid}_y"
            if x_col not in df.columns or row.empty:
                continue
            val_x = row[x_col].values[0] if not row.empty else float("nan")
            val_y = row[y_col].values[0] if not row.empty else float("nan")
            if pd.isna(val_x) or pd.isna(val_y):
                continue

            px_coord, py_coord = int(val_x), int(val_y)

            # Testa se está dentro do polígono
            inside = poly_q.containsPoint(QPoint(px_coord, py_coord),
                                           Qt.FillRule.OddEvenFill)
            if not inside:
                continue  # Não desenha se estiver fora da zona

            r, g, b = COLORS[i % len(COLORS)]
            color = QColor(r, g, b)

            # Ponto do jogador
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            painter.drawEllipse(QPoint(px_coord, py_coord), 6, 6)

            # Label com ID
            painter.setFont(QFont("Arial", 13, QFont.Weight.Bold))
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(px_coord + 9, py_coord + 5, str(mid))
            painter.setPen(QPen(color))
            painter.drawText(px_coord + 8, py_coord + 4, str(mid))

        painter.end()

        pixmap_item.setPixmap(pixmap)
        if state.get("first_render", True):
            view.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            state["first_render"] = False

        lbl_frame.setText(f"Frame {frame_idx + 1} / {total_frames}")

        slider.blockSignals(True)
        slider.setValue(frame_idx)
        slider.blockSignals(False)

    def on_timer():
        if state["frame"] + 1 >= total_frames:
            toggle_play()
            return
        state["frame"] += 1
        render(state["frame"])

    def toggle_play():
        state["playing"] = not state["playing"]
        if state["playing"]:
            btn_play.setText("⏸  Pause")
            timer.start()
        else:
            btn_play.setText("▶  Play")
            timer.stop()

    def on_slider(v):
        state["frame"] = v
        render(v)

    timer.timeout.connect(on_timer)
    btn_play.clicked.connect(toggle_play)
    slider.valueChanged.connect(on_slider)

    def on_close(event):
        timer.stop()
        cap.release()
        event.accept()
    win.closeEvent = on_close

    render(0)
    win.show()
    win.raise_()
    win.activateWindow()
    return win
