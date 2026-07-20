# src/modules/edit_video.py
# Adapted from Vaila's Tracker by Santiago Preto.
# Migrated from PyQt5 → PySide6.

import os
import cv2
import numpy as np
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QFileDialog, QListWidget, QListWidgetItem, QDialog,
    QDialogButtonBox, QCheckBox, QGraphicsView, QGraphicsScene,
    QGraphicsPolygonItem, QMessageBox, QProgressBar, QApplication,
)
from PySide6.QtCore import Qt, QRect, QPoint, QPointF, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QPolygonF


# =============================================================================
# INTERACTIVE FRAME VIEW (zoom + pan reutilizável)
# =============================================================================

class InteractiveFrameView(QGraphicsView):
    """
    QGraphicsView com zoom via scroll do mouse e pan via middle-click + drag.
    Reutilizável em qualquer janela que exibe um frame para seleção.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pan_active = False
        self._pan_start  = None
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_start  = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)


# =============================================================================
# POLYGON GRAPHICS (canvas de seleção de polígono)
# =============================================================================

class PolygonGraphics(QLabel):
    def __init__(self, frame, points, parent_dialog=None):
        super().__init__()
        self.orig_frame    = frame
        self.points        = points
        self.zoom          = 1.0
        self.parent_dialog = parent_dialog
        self.update_pixmap()
        self.setMouseTracking(True)

    def set_zoom(self, zoom):
        self.zoom = zoom
        self.update_pixmap()

    def update_pixmap(self):
        h, w, _ = self.orig_frame.shape
        scaled = cv2.resize(self.orig_frame,
                            (int(w * self.zoom), int(h * self.zoom)),
                            interpolation=cv2.INTER_AREA)
        if len(self.points) >= 4:
            mask = np.zeros((scaled.shape[0], scaled.shape[1]), dtype=np.uint8)
            pts  = np.array([(int(x * self.zoom), int(y * self.zoom))
                             for x, y in self.points], np.int32)
            cv2.fillPoly(mask, [pts], 255)
            preview = scaled.copy()
            inside  = getattr(self.parent_dialog, "inside", True)
            if inside:
                preview[mask == 255] = [0, 0, 0]
            else:
                overlay = np.zeros_like(preview)
                overlay[mask == 0] = [0, 0, 0]
                preview = cv2.addWeighted(preview, 1, overlay, 0.5, 0)
            self.setPixmap(QPixmap.fromImage(self._to_qimage(preview)))
        else:
            self.setPixmap(QPixmap.fromImage(self._to_qimage(scaled)))
        self.repaint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = int(event.position().x() / self.zoom)
            y = int(event.position().y() / self.zoom)
            self.points.append((x, y))
            self.update_pixmap()
        elif event.button() == Qt.MouseButton.RightButton and self.points:
            self.points.pop()
            self.update_pixmap()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.points:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        for pt in self.points:
            painter.drawEllipse(
                QPoint(int(pt[0] * self.zoom), int(pt[1] * self.zoom)), 4, 4)
        if len(self.points) > 1:
            for i in range(len(self.points) - 1):
                painter.drawLine(
                    QPoint(int(self.points[i][0]     * self.zoom),
                           int(self.points[i][1]     * self.zoom)),
                    QPoint(int(self.points[i + 1][0] * self.zoom),
                           int(self.points[i + 1][1] * self.zoom)),
                )
            if len(self.points) >= 4:
                painter.drawLine(
                    QPoint(int(self.points[-1][0] * self.zoom),
                           int(self.points[-1][1] * self.zoom)),
                    QPoint(int(self.points[0][0]  * self.zoom),
                           int(self.points[0][1]  * self.zoom)),
                )

    @staticmethod
    def _to_qimage(frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)


# =============================================================================
# POLYGON SELECTION DIALOG
# =============================================================================

class PolygonSelectionDialog(QDialog):
    def __init__(self, frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Polygon Selection")
        self.setMinimumSize(800, 600)
        self.frame            = frame
        self.points           = []    # área atual sendo desenhada
        self.confirmed_areas  = []    # lista de polígonos já confirmados
        self.inside           = True
        self.selection_width  = frame.shape[1]
        self.selection_height = frame.shape[0]
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)

        self.lbl_hint = QLabel(
            "Clique para adicionar pontos (mín. 4). "
            "Clique direito remove o último. "
            "Scroll = zoom, Scroll-click + arrastar = pan."
        )
        self.lbl_hint.setWordWrap(True)
        lay.addWidget(self.lbl_hint)

        self.scene = QGraphicsScene()
        self.view  = InteractiveFrameView()
        self.view.setScene(self.scene)
        self.view.setMinimumSize(800, 500)

        rgb  = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.pixmap = QPixmap.fromImage(qimg)
        self.scene.addPixmap(self.pixmap)
        self.view.fitInView(self.scene.sceneRect(),
                            Qt.AspectRatioMode.KeepAspectRatio)
        lay.addWidget(self.view, stretch=1)

        self._area_items   = []
        self._current_item = None

        bar = QHBoxLayout()
        self.lbl_count = QLabel("0 ponto(s) — 0 área(s) confirmada(s)")
        bar.addWidget(self.lbl_count, stretch=1)

        btn_confirm_area = QPushButton("✓ Confirmar Área")
        btn_confirm_area.setToolTip("Confirma a área atual e permite desenhar outra")
        btn_confirm_area.clicked.connect(self._confirm_area)
        bar.addWidget(btn_confirm_area)

        btn_reset_current = QPushButton("↺ Resetar Atual")
        btn_reset_current.clicked.connect(self._reset_current)
        bar.addWidget(btn_reset_current)

        btn_reset_all = QPushButton("✕ Limpar Tudo")
        btn_reset_all.clicked.connect(self._reset_all)
        bar.addWidget(btn_reset_all)

        lay.addLayout(bar)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.scene.mousePressEvent = self._on_scene_click

    def _on_scene_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.points.append((event.scenePos().x(), event.scenePos().y()))
            self._redraw_current()
        elif event.button() == Qt.MouseButton.RightButton and self.points:
            self.points.pop()
            self._redraw_current()

    def _redraw_current(self):
        if self._current_item:
            self.scene.removeItem(self._current_item)
            self._current_item = None
        if len(self.points) >= 2:
            poly = QPolygonF([QPointF(x, y) for x, y in self.points])
            self._current_item = QGraphicsPolygonItem(poly)
            self._current_item.setPen(QPen(QColor("#FF4560"), 2))
            self._current_item.setBrush(QColor(255, 69, 96, 40))
            self.scene.addItem(self._current_item)
        total = len(self.confirmed_areas)
        self.lbl_count.setText(
            f"{len(self.points)} ponto(s) atual — {total} área(s) confirmada(s)")

    def _confirm_area(self):
        if len(self.points) < 4:
            QMessageBox.warning(self, "Pontos insuficientes",
                                "Selecione pelo menos 4 pontos para confirmar a área.")
            return
        if self._current_item:
            self.scene.removeItem(self._current_item)
            self._current_item = None
        poly = QPolygonF([QPointF(x, y) for x, y in self.points])
        item = QGraphicsPolygonItem(poly)
        item.setPen(QPen(QColor("#0A2463"), 2))
        item.setBrush(QColor(10, 36, 99, 50))
        self.scene.addItem(item)
        self._area_items.append(item)
        self.confirmed_areas.append(self.points.copy())
        self.points = []
        self._current_item = None
        self.lbl_count.setText(
            f"0 ponto(s) atual — {len(self.confirmed_areas)} área(s) confirmada(s)")

    def _reset_current(self):
        self.points.clear()
        if self._current_item:
            self.scene.removeItem(self._current_item)
            self._current_item = None
        self.lbl_count.setText(
            f"0 ponto(s) atual — {len(self.confirmed_areas)} área(s) confirmada(s)")

    def _reset_all(self):
        self._reset_current()
        for item in self._area_items:
            self.scene.removeItem(item)
        self._area_items.clear()
        self.confirmed_areas.clear()
        self.lbl_count.setText("0 ponto(s) — 0 área(s) confirmada(s)")

    def _on_accept(self):
        if len(self.points) >= 4:
            self._confirm_area()
        if not self.confirmed_areas:
            QMessageBox.warning(self, "Sem áreas",
                                "Confirme pelo menos uma área antes de OK.")
            return
        self.points = self.confirmed_areas[0]
        self.selection_width  = int(self.pixmap.width())
        self.selection_height = int(self.pixmap.height())
        self.accept()


# =============================================================================
# CUSTOM SLIDER (com marcadores de corte)
# =============================================================================

class CustomSlider(QSlider):
    def __init__(self, orientation):
        super().__init__(orientation)
        self.initial_cut  = None
        self.final_cut    = None
        self.total_frames = 0

    def set_cut_range(self, initial, final, total):
        self.initial_cut  = initial
        self.final_cut    = final
        self.total_frames = total
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.initial_cut is None and self.final_cut is None:
            return
        painter = QPainter(self)
        rect = self.rect()
        h, w = rect.height(), rect.width()
        denom = max(self.total_frames - 1, 1)
        if self.initial_cut is not None:
            x1 = int(w * self.initial_cut / denom)
            painter.fillRect(QRect(0, 0, x1, h), QColor(180, 180, 180, 120))
        if self.final_cut is not None:
            x0 = int(w * (self.final_cut + 1) / denom)
            painter.fillRect(QRect(x0, 0, w - x0, h), QColor(180, 180, 180, 120))


# =============================================================================
# MAIN WINDOW
# =============================================================================

BTN_STYLE = """
    QPushButton {
        background-color: white; color: #222;
        padding: 4px 16px; border: 1px solid #DDD; border-radius: 4px;
    }
    QPushButton:hover { background-color: #fcba03; }
"""


class EditVideoWindow(QMainWindow):
    video_saved = Signal()

    def __init__(self, video_path=None, project_path=None):
        super().__init__()
        self.setWindowTitle("Edit Video")
        self.setGeometry(100, 100, 1100, 650)

        self.video_path      = video_path
        self.project_path    = project_path
        self.custom_save_path = None
        self.cap             = None
        self.total_frames    = 0
        self.fps             = 0
        self.current_frame   = 0
        self.initial_cut     = None
        self.final_cut       = None
        self.history         = []
        self.paint_masks     = []
        self.paint_mode      = None
        self.paint_points    = []

        self._init_ui()

        if self.video_path:
            self._load_video_from_path(self.video_path)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QVBoxLayout()

        # Where save
        top_row = QHBoxLayout()
        btn_where = QPushButton("Where to save")
        btn_where.setStyleSheet(BTN_STYLE)
        btn_where.clicked.connect(self._set_save_location)
        top_row.addWidget(btn_where)
        top_row.addStretch()
        left.addLayout(top_row)

        # Video preview
        self.video_view  = QGraphicsView()
        self.video_scene = QGraphicsScene()
        self.video_view.setScene(self.video_scene)
        self.video_view.setMinimumSize(880, 480)
        self.video_view.setStyleSheet("background-color: #111; border: none;")
        left.addWidget(self.video_view)

        # Slider
        slider_row = QHBoxLayout()
        self.slider = CustomSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider)
        slider_row.addWidget(self.slider)
        self.frame_label = QLabel("Frame: 0")
        self.time_label  = QLabel("Time: 00:00")
        slider_row.addWidget(self.frame_label)
        slider_row.addWidget(self.time_label)
        left.addLayout(slider_row)

        # Cut buttons
        cut_row = QHBoxLayout()
        self.btn_initial_cut = QPushButton("Initial Cut")
        self.btn_initial_cut.setStyleSheet(BTN_STYLE)
        self.btn_initial_cut.clicked.connect(self._set_initial_cut)
        self.btn_final_cut = QPushButton("Final Cut")
        self.btn_final_cut.setStyleSheet(BTN_STYLE)
        self.btn_final_cut.clicked.connect(self._set_final_cut)
        cut_row.addWidget(self.btn_initial_cut)
        cut_row.addWidget(self.btn_final_cut)
        left.addLayout(cut_row)

        # Load / Save
        ls_row = QHBoxLayout()
        btn_load = QPushButton("Load Video")
        btn_load.setStyleSheet(BTN_STYLE)
        btn_load.clicked.connect(self._load_video)
        self.btn_save = QPushButton("Save Video")
        self.btn_save.setStyleSheet(BTN_STYLE)
        self.btn_save.clicked.connect(self._save_video)
        ls_row.addWidget(btn_load)
        ls_row.addWidget(self.btn_save)
        left.addLayout(ls_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #DDD; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #fcba03; border-radius: 3px; }
        """)
        left.addWidget(self.progress_bar)

        main_layout.addLayout(left, 4)

        # ── Right panel ──────────────────────────────────────────────────────
        right = QVBoxLayout()

        self.btn_paint = QPushButton("🎨  Paint Area")
        self.btn_paint.setStyleSheet(BTN_STYLE)
        self.btn_paint.clicked.connect(self._open_paint_dialog)
        right.addWidget(self.btn_paint)

        right.addWidget(QLabel("Recent Changes:"))
        self.history_list = QListWidget()
        right.addWidget(self.history_list)

        btn_undo = QPushButton("Undo")
        btn_undo.setStyleSheet(BTN_STYLE)
        btn_undo.clicked.connect(self._undo)
        right.addWidget(btn_undo)
        right.addStretch()

        main_layout.addLayout(right, 1)

    # ── Video loading ─────────────────────────────────────────────────────────

    def _load_video(self):
        if self.video_path:
            QMessageBox.warning(self, "Video Already Loaded",
                                "A video is already loaded from the project context.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Video Files (*.mp4 *.avi *.mov)")
        if path:
            self._load_video_from_path(path)

    def _load_video_from_path(self, path):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.video_path  = path
        self.cap         = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Error", "Failed to open video file.")
            self.cap = None
            return
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps          = self.cap.get(cv2.CAP_PROP_FPS)
        self.slider.setMaximum(self.total_frames - 1)
        self.slider.setEnabled(True)
        self.current_frame = 0
        self._show_frame(0)

    # ── Frame display ─────────────────────────────────────────────────────────

    def _show_frame(self, idx):
        if not self.cap:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self.cap.read()
        if not ret:
            return
        self.current_frame = idx

        # Apply paint masks for preview
        preview = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        for mask in self.paint_masks:
            mstart, mend = mask["applied_range"]
            if mstart <= idx <= mend:
                sel_w, sel_h = mask.get("selection_size", (frame.shape[1], frame.shape[0]))
                pts = np.array(mask["points"], np.float32)
                pts[:, 0] *= 640 / sel_w
                pts[:, 1] *= 360 / sel_h
                pts = pts.astype(np.int32)
                if mask["mode"] == "inside":
                    cv2.fillPoly(preview, [pts], (0, 0, 0))
                else:
                    overlay = np.ones(preview.shape, dtype=np.uint8) * 0
                    cv2.fillPoly(overlay, [pts], (255, 255, 255))
                    preview = cv2.bitwise_and(preview, overlay)

        rgb   = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg  = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.video_scene.clear()
        self.video_scene.addPixmap(QPixmap.fromImage(qimg))
        self.video_view.fitInView(
            self.video_scene.itemsBoundingRect(),
            Qt.AspectRatioMode.KeepAspectRatio)

        self.frame_label.setText(f"Frame: {idx}")
        secs = int(idx / self.fps) if self.fps else 0
        self.time_label.setText(f"Time: {secs // 60:02}:{secs % 60:02}")

        self.slider.blockSignals(True)
        self.slider.setValue(idx)
        self.slider.blockSignals(False)
        self.slider.set_cut_range(self.initial_cut, self.final_cut, self.total_frames)

    def _on_slider(self, value):
        self._show_frame(value)

    # ── Cut ───────────────────────────────────────────────────────────────────

    def _set_initial_cut(self):
        self.initial_cut = self.current_frame
        self._add_history({"type": "initial_cut", "frame": self.current_frame})
        self._show_frame(self.current_frame)

    def _set_final_cut(self):
        self.final_cut = self.current_frame
        self._add_history({"type": "final_cut", "frame": self.current_frame})
        self._show_frame(self.current_frame)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def _open_paint_dialog(self):
        if not self.cap:
            QMessageBox.warning(self, "No video", "Load a video first.")
            return

        # Mode dialog: inside or outside
        dlg   = QDialog(self)
        dlg.setWindowTitle("Paint Area Mode")
        vbox  = QVBoxLayout(dlg)
        vbox.addWidget(QLabel("Paint the selected area:"))
        inside_cb  = QCheckBox("Inside polygon — paint black")
        outside_cb = QCheckBox("Outside polygon — paint black")
        inside_cb.setChecked(True)
        vbox.addWidget(inside_cb)
        vbox.addWidget(outside_cb)

        def _on_inside():
            if inside_cb.isChecked():
                outside_cb.setChecked(False)
        def _on_outside():
            if outside_cb.isChecked():
                inside_cb.setChecked(False)
        inside_cb.stateChanged.connect(_on_inside)
        outside_cb.stateChanged.connect(_on_outside)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vbox.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        mode = "inside" if inside_cb.isChecked() else "outside"

        # Grab frame for polygon selection
        ref_frame_idx = self.initial_cut or 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, ref_frame_idx)
        ret, frame = self.cap.read()
        if not ret:
            return

        poly_dlg        = PolygonSelectionDialog(frame, self)
        poly_dlg.inside = (mode == "inside")
        if (poly_dlg.exec() == QDialog.DialogCode.Accepted
                and poly_dlg.confirmed_areas):
            for area_points in poly_dlg.confirmed_areas:
                self.paint_mode   = mode
                self.paint_points = area_points
                self.paint_selection_size = (poly_dlg.selection_width,
                                             poly_dlg.selection_height)
                self._apply_paint()

    def _apply_paint(self):
        applied_range = (
            self.initial_cut or 0,
            self.final_cut   or self.total_frames - 1,
        )
        mask_entry = {
            "mode":           self.paint_mode,
            "points":         self.paint_points.copy(),
            "applied_range":  applied_range,
            "selection_size": getattr(self, "paint_selection_size",
                                      (640, 360)),
        }
        self.paint_masks.append(mask_entry)
        self._add_history({
            "type":  "paint",
            "mode":  self.paint_mode,
            **mask_entry,
        })
        self._show_frame(self.current_frame)

    # ── History / Undo ────────────────────────────────────────────────────────

    def _add_history(self, action):
        self.history.append(action)
        item = QListWidgetItem()
        if action["type"] == "initial_cut":
            item.setText(f"✂️ Initial Cut at frame {action['frame']}")
        elif action["type"] == "final_cut":
            item.setText(f"✂️ Final Cut at frame {action['frame']}")
        elif action["type"] == "paint":
            s, e = action["applied_range"]
            item.setText(f"🎨 Paint {action['mode']} — frames {s}–{e}")
        self.history_list.addItem(item)

    def _undo(self):
        if not self.history:
            return
        last = self.history.pop()
        if last["type"] == "initial_cut":
            self.initial_cut = None
        elif last["type"] == "final_cut":
            self.final_cut = None
        elif last["type"] == "paint" and self.paint_masks:
            self.paint_masks.pop()
        self.history_list.takeItem(self.history_list.count() - 1)
        self._show_frame(self.current_frame)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _set_save_location(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Location")
        if folder:
            self.custom_save_path = folder
            QMessageBox.information(self, "Save Location",
                                    f"Videos will be saved to:\n{folder}")
        else:
            self.custom_save_path = None

    def _save_video(self):
        if not self.cap or not self.video_path:
            QMessageBox.warning(self, "No video", "Load a video first.")
            return

        # Determine save path
        if self.custom_save_path:
            ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(self.custom_save_path, f"edited_{ts}.mp4")
        elif self.project_path:
            vid_dir = os.path.join(self.project_path, "videos")
            os.makedirs(vid_dir, exist_ok=True)
            base      = os.path.splitext(os.path.basename(self.video_path))[0]
            ts        = datetime.now().strftime("%Y%m%d_%H%M")
            save_path = os.path.join(vid_dir, f"{base}_edited_{ts}.mp4")
        else:
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Video As", "", "MP4 Files (*.mp4)")
            if not save_path:
                return

        cap   = cv2.VideoCapture(self.video_path)
        W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps   = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out    = cv2.VideoWriter(save_path, fourcc, fps, (W, H))

        start  = self.initial_cut if self.initial_cut is not None else 0
        end    = self.final_cut   if self.final_cut   is not None else total - 1
        n      = end - start + 1

        self.progress_bar.setVisible(True)
        self.btn_save.setEnabled(False)
        self.progress_bar.setValue(0)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        for i, idx in enumerate(range(start, end + 1)):
            ret, frame = cap.read()
            if not ret:
                break

            for mask in self.paint_masks:
                ms, me = mask["applied_range"]
                if ms <= idx <= me:
                    sel_w, sel_h = mask.get("selection_size", (W, H))
                    pts = np.array(mask["points"], np.float32)
                    pts[:, 0] *= W / sel_w
                    pts[:, 1] *= H / sel_h
                    pts = pts.astype(np.int32)
                    if mask["mode"] == "inside":
                        cv2.fillPoly(frame, [pts], (0, 0, 0))
                    else:
                        overlay = np.ones(frame.shape, dtype=np.uint8) * 0
                        cv2.fillPoly(overlay, [pts], (255, 255, 255))
                        frame = cv2.bitwise_and(frame, overlay)

            out.write(frame)
            self.progress_bar.setValue(int((i + 1) / n * 100))
            QApplication.processEvents()

        cap.release()
        out.release()
        self.progress_bar.setVisible(False)
        self.btn_save.setEnabled(True)
        QMessageBox.information(self, "Done", f"Video saved to:\n{save_path}")
        self.video_saved.emit()

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.video_scene.clear()
        self.paint_masks.clear()
        self.history.clear()
        super().closeEvent(event)


# =============================================================================
# FACTORY + MANAGER
# =============================================================================

def run_edit_video(video_path=None, project_path=None):
    return EditVideoWindow(video_path=video_path, project_path=project_path)


from PySide6.QtCore import QObject, Slot

class EditVideoManager(QObject):
    def __init__(self, videos_manager, parent=None):
        super().__init__(parent)
        self._videos_manager = videos_manager
        self._window         = None

    @Slot()
    def open_tool(self):
        video_path   = self._videos_manager.activeVideoPath
        project_path = self._videos_manager.activeProjectPath
        if not video_path or not project_path:
            return
        if self._window is not None:
            self._window.deleteLater()
        self._window = EditVideoWindow(
            video_path=video_path,
            project_path=project_path,
        )
        self._window.video_saved.connect(self._videos_manager.refreshVideos)
        self._window.show()
