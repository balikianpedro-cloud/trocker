"""
TROCKER Homography Module (PySide6)
===================================
Migrated from PyQt5 to PySide6.
"""

import pandas as pd
import os
import json
import numpy as np
import sys
import cv2
import csv

from PySide6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsTextItem, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QGraphicsPolygonItem, QFileDialog, QMessageBox, QDialog, QLineEdit, QHBoxLayout,
    QScrollArea, QFrame
)
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem
from PySide6.QtCore import Qt, QPointF, QRectF, Signal

from modules.trigger_zone import zone_exists

# =============================================================================
# CSV RESOLUTION
# =============================================================================

def find_csv_for_video(video_path: str, project_path: str) -> str | None:
    """
    Encontra o CSV de pixel_coordinates correto para um vídeo no projeto.

    Problema: o vídeo ativo pode ser o original OU o _tracked.mp4 gerado pelo
    Trocker. O CSV sempre tem o padrão {nome_original}_tracked.csv. Esta função
    resolve o caminho correto independente de qual variante do nome for passada.

    Estratégia (em ordem de prioridade):
      1. Prefere CSV editado pelo ReID (sufixo _reid) se existir
      2. Tenta nome direto: {video_name}_tracked.csv
      3. Remove sufixo _tracked do vídeo e tenta: {base}_tracked.csv
      4. Busca fuzzy: qualquer CSV em pixel_coordinates cujo stem começa com
         o stem base (útil se o usuário renomeou o arquivo)
      5. Se só houver um CSV na pasta, usa ele (projeto de um único vídeo)
      6. Abre diálogo para o usuário escolher manualmente

    Retorna o caminho absoluto do CSV ou None se o usuário cancelar.
    """
    if not project_path or not os.path.isdir(project_path):
        return None

    pixel_dir = os.path.join(project_path, "data", "pixel_coordinates")
    if not os.path.isdir(pixel_dir):
        return None

    # Stem do vídeo recebido, sem extensão
    video_stem = os.path.splitext(os.path.basename(video_path))[0]  # ex: YOYO_tracked

    # Base sem sufixo _tracked (o nome do vídeo original)
    base_stem = video_stem
    if base_stem.endswith("_tracked"):
        base_stem = base_stem[:-8]  # ex: YOYO

    # --- Candidatos em ordem de prioridade ---
    candidates = [
        # 1. ReID editado (base)
        os.path.join(pixel_dir, f"{base_stem}_reid.csv"),
        # 2. ReID editado (com _tracked no nome)
        os.path.join(pixel_dir, f"{base_stem}_tracked_reid.csv"),
        # 3. Padrão direto com o stem recebido
        os.path.join(pixel_dir, f"{video_stem}_tracked.csv"),
        # 4. Padrão com o base (remove _tracked duplicado)
        os.path.join(pixel_dir, f"{base_stem}_tracked.csv"),
        # 5. Apenas o base (sem _tracked)
        os.path.join(pixel_dir, f"{base_stem}.csv"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    # 6. Busca fuzzy num único os.listdir: CSVs com prefixo base_stem, ou qualquer um se só houver um
    try:
        all_in_dir = [
            os.path.join(pixel_dir, f)
            for f in os.listdir(pixel_dir)
            if f.endswith(".csv")
        ]
        prefix_matches = [p for p in all_in_dir if os.path.basename(p).startswith(base_stem)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            prefix_matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return prefix_matches[0]
        # 7. Só tem um CSV na pasta inteira → usa ele
        if len(all_in_dir) == 1:
            return all_in_dir[0]
    except OSError:
        pass

    # 8. Não encontrou nada → deixa o chamador decidir (retorna None)
    return None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def check_colinearity(points, tolerance=1e-6):
    if len(points) < 3:
        return False, []
    
    points = np.array(points)
    colinear_groups = []
    
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            for k in range(j + 1, len(points)):
                p1, p2, p3 = points[i], points[j], points[k]
                area = abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])) / 2
                
                if area < tolerance:
                    colinear_indices = [i, j, k]
                    for m in range(len(points)):
                        if m not in colinear_indices:
                            p4 = points[m]
                            area_with_4 = abs((p2[0] - p1[0]) * (p4[1] - p1[1]) - (p4[0] - p1[0]) * (p2[1] - p1[1])) / 2
                            if area_with_4 < tolerance:
                                colinear_indices.append(m)
                    
                    colinear_groups.append(colinear_indices)
    
    for group in colinear_groups:
        if len(group) >= 3:
            return True, group
    
    return False, []

def check_polygon_area(points, min_area=1.0):
    if len(points) < 3:
        return False, 0.0
    
    points = np.array(points)
    area = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    
    area = abs(area) / 2.0
    return area >= min_area, area

def validate_homography_points(src_points, dst_points, min_points=4, min_area=1.0):
    if len(src_points) < min_points or len(dst_points) < min_points:
        return {
            'valid': False,
            'reason': f'Insufficient points: {len(src_points)}/{min_points} required',
            'colinear': False,
            'all_points_colinear': False,
            'area_sufficient': True,
            'area': 0.0,
            'colinear_indices': [],
            'colinear_count': 0
        }
    
    is_colinear, colinear_indices = check_colinearity(dst_points)
    area_sufficient, area = check_polygon_area(dst_points, min_area)
    
    all_points_colinear = is_colinear and len(colinear_indices) == len(dst_points)
    valid = not all_points_colinear
    
    reason = "Valid configuration"
    if all_points_colinear:
        reason = f"All points are colinear: indices {colinear_indices} - degenerate configuration"
    elif is_colinear and not all_points_colinear:
        reason = f"Valid configuration with {len(colinear_indices)} collinear points out of {len(dst_points)} total points"
    
    return {
        'valid': valid,
        'reason': reason,
        'colinear': is_colinear,
        'all_points_colinear': all_points_colinear,
        'area_sufficient': area_sufficient,
        'area': area,
        'colinear_indices': colinear_indices if is_colinear else [],
        'colinear_count': len(colinear_indices) if is_colinear else 0,
        'non_colinear_count': len(dst_points) - len(colinear_indices) if is_colinear else len(dst_points)
    }

# =============================================================================
# CALIBRATION GATE (reprojection error)
#
# See Especificacao_Tecnica_E01-E07_Gate_Calibracao_Trocker.docx, section 2.
# Thresholds below are engineering proposals, not validated requirements yet —
# they must be recalibrated against the real-data validation plan before any
# use outside development (see arquitetura doc, section 20.8).
# =============================================================================

class CalibrationStatus:
    VALID = "VALID"
    REVIEW = "REVIEW"
    INVALID = "INVALID"

def compute_reprojection_error(h_matrix, src_points, dst_points):
    """
    Reprojects src_points (image/pixel) through h_matrix and compares the
    result to dst_points (world/meters), point by point.

    Returns per-point errors plus mean and max error, in the same units as
    dst_points (meters, in the DLT calibration flow).
    """
    src = np.array(src_points, dtype=np.float64).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(src, np.array(h_matrix, dtype=np.float64))
    projected = projected.reshape(-1, 2)
    dst = np.array(dst_points, dtype=np.float64).reshape(-1, 2)
    per_point_error = np.linalg.norm(projected - dst, axis=1)
    return {
        'per_point_error_m': [round(float(e), 4) for e in per_point_error],
        'mean_error_m': float(np.mean(per_point_error)),
        'max_error_m': float(np.max(per_point_error)),
    }

def calibration_gate(mean_error_m, max_error_m,
                      limit_valid=0.10, limit_review=0.15,
                      limit_max_valid=0.20, limit_max_review=0.30):
    """
    Classifies a calibration as VALID / REVIEW / INVALID based on reprojection
    error. INVALID must block release of any metric/physiological output
    downstream (distance, speed, VO2) — the caller is responsible for
    enforcing that block; this function only classifies.
    """
    if mean_error_m > limit_review or max_error_m > limit_max_review:
        status = CalibrationStatus.INVALID
        reason = (f"mean_error {mean_error_m:.3f} m > {limit_review} m, or "
                  f"max_error {max_error_m:.3f} m > {limit_max_review} m")
    elif mean_error_m > limit_valid or max_error_m > limit_max_valid:
        status = CalibrationStatus.REVIEW
        reason = (f"mean_error {mean_error_m:.3f} m in ({limit_valid}, {limit_review}] m, or "
                  f"max_error {max_error_m:.3f} m in ({limit_max_valid}, {limit_max_review}] m")
    else:
        status = CalibrationStatus.VALID
        reason = f"mean_error {mean_error_m:.3f} m, max_error {max_error_m:.3f} m within limits"

    return {
        'status': status,
        'reason': reason,
        'mean_error_m': round(float(mean_error_m), 4),
        'max_error_m': round(float(max_error_m), 4),
        'thresholds_m': {
            'limit_valid': limit_valid,
            'limit_review': limit_review,
            'limit_max_valid': limit_max_valid,
            'limit_max_review': limit_max_review,
        },
    }

# =============================================================================
# DIALOG AND UI CLASSES
# =============================================================================

class FieldDimensionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Field Dimensions")
        self.setModal(True)
        self.length_edit = QLineEdit(self)
        self.width_edit = QLineEdit(self)
        self.length_edit.setPlaceholderText("105.0")
        self.width_edit.setPlaceholderText("68.0")
        layout = QVBoxLayout()
        l1 = QHBoxLayout()
        l1.addWidget(QLabel("Field length (in meters):"))
        l1.addWidget(self.length_edit)
        l2 = QHBoxLayout()
        l2.addWidget(QLabel("Field width (in meters):"))
        l2.addWidget(self.width_edit)
        layout.addLayout(l1)
        layout.addLayout(l2)
        self.continue_btn = QPushButton("Continue")
        self.continue_btn.clicked.connect(self.accept)
        layout.addWidget(self.continue_btn)
        self.setLayout(layout)
    def get_values(self):
        try:
            length = float(self.length_edit.text()) if self.length_edit.text() else 105.0
            width = float(self.width_edit.text()) if self.width_edit.text() else 68.0
            return length, width
        except Exception:
            return None, None

class DraggableGridPoint(QGraphicsEllipseItem):
    def __init__(self, x, y, radius=18, parent_window=None):
        """Ponto arrastável - radius grande para area de clique confortável"""
        super().__init__(x - radius, y - radius, radius * 2, radius * 2)
        self.visual_radius = 5   # ponto visível menor (antes 10)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.radius = radius
        self.parent_window = parent_window

        # Área de hit invisível (maior, facilita o drag)
        self.setBrush(QColor(0, 0, 0, 0))
        self.setPen(QPen(QColor(0, 0, 0, 0), 0))

        # Círculo visual laranja vibrante com borda branca
        self.visual_circle = QGraphicsEllipseItem(
            x - self.visual_radius, y - self.visual_radius,
            self.visual_radius * 2, self.visual_radius * 2, self
        )
        self.visual_circle.setBrush(QColor(255, 140, 0, 230))   # laranja
        self.visual_circle.setPen(QPen(QColor(255, 255, 255), 2))
        self.visual_circle.setZValue(11)

        # Halo externo (anel) para ainda mais visibilidade
        halo_r = self.visual_radius + 4
        self.halo = QGraphicsEllipseItem(
            x - halo_r, y - halo_r, halo_r * 2, halo_r * 2, self
        )
        self.halo.setBrush(QColor(0, 0, 0, 0))
        self.halo.setPen(QPen(QColor(255, 200, 0, 160), 1.5))
        self.halo.setZValue(9)
        
    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
        
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.parent_window:
            self.parent_window.update_grid()
        
    def get_center_pos(self):
        rect = self.rect()
        scene_rect = self.mapRectToScene(rect)
        return scene_rect.center()

class DLTPoint(QGraphicsEllipseItem):
    def __init__(self, x, y, point_id, parent_window=None):
        super().__init__(x - 6, y - 6, 12, 12)
        self.point_id = point_id
        self.parent_window = parent_window
        self.is_selected = False
        self.setBrush(QColor(255, 0, 0, 200))
        self.setPen(QPen(QColor(255, 255, 255), 2))
        self.setZValue(15)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        
        self.text_item = QGraphicsTextItem(str(point_id + 1), self)
        self.text_item.setDefaultTextColor(QColor(255, 255, 0))  # amarelo — visível sobre vermelho
        self.text_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        # Posiciona fora do círculo (acima e à direita)
        self.text_item.setPos(8, -18)
        self.text_item.setZValue(16)
        
    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.select_point()
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
        
    def select_point(self):
        if self.parent_window:
            for point in self.parent_window.dlt_points:
                if point != self:
                    point.deselect_point()
        self.is_selected = True
        self.setBrush(QColor(255, 255, 0, 200))
        self.setPen(QPen(QColor(255, 255, 255), 3))
        if self.parent_window:
            self.parent_window.highlight_coordinate_input(self.point_id)
        
    def deselect_point(self):
        self.is_selected = False
        self.setBrush(QColor(255, 0, 0, 200))
        self.setPen(QPen(QColor(255, 255, 255), 2))
        
    def get_center_pos(self):
        rect = self.rect()
        scene_rect = self.mapRectToScene(rect)
        return scene_rect.center()

class PointSelectorWindow(QMainWindow):
    closed = Signal()

    def __init__(self, frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust Points")
        self.setGeometry(100, 100, 1600, 800)
        self.frame = frame
        self.grid_points = []
        self.dlt_points = []
        self.grid_items = []
        self.dlt_coordinates = []
        self.result = None
        self.field_length = None
        self.field_width = None
        self.zoom = 1.0
        self.grid_size = 5
        self.current_mode = "grid"
        self._pan_start = None
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        left_panel = QWidget()
        left_panel.setFixedWidth(350)
        left_panel.setStyleSheet("""
            QWidget { background-color: #1e1e24; color: #e0e0e0; }
            QLabel { color: #e0e0e0; background-color: transparent; }
            QLineEdit {
                background-color: #2c2c36;
                color: #f0f0f0;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #0071e3; }
            QScrollArea { background-color: #1e1e24; border: none; }
        """)
        left_layout = QVBoxLayout(left_panel)

        self.mode_toggle_btn = QPushButton("Switch to DLT")
        self.mode_toggle_btn.setFixedHeight(40)
        self.mode_toggle_btn.clicked.connect(self.toggle_mode)
        self.mode_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #2c2c36;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0071e3; border-color: #0071e3; color: #fff; }
            QPushButton:pressed { background-color: #005bb5; }
        """)
        left_layout.addWidget(self.mode_toggle_btn)
        
        image_label = QLabel()
        image_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "rectangle.png")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(320, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
        else:
            image_label.setText("Campo\n(Placeholder)")
            image_label.setStyleSheet("color: #aaa; font-style: italic; border: 1px solid #444; background-color: #2c2c36; min-height: 100px;")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(image_label)
        
        left_layout.addSpacing(20)
        
        self.length_label = QLabel("Field width (in meters):")
        self.length_label.setStyleSheet("font-weight: bold; color: #c0c0c0; font-size: 13px;")
        self.length_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(self.length_label)
        
        self.length_edit = QLineEdit()
        self.length_edit.setPlaceholderText("68.0")
        self.length_edit.setStyleSheet("QLineEdit { background-color: #ffffff; color: #111111; padding: 5px; border-radius: 3px; font-size: 12px; }")
        left_layout.addWidget(self.length_edit)
        
        left_layout.addSpacing(10)
        
        self.width_label = QLabel("Field length (in meters):")
        self.width_label.setStyleSheet("font-weight: bold; color: #c0c0c0; font-size: 13px;")
        self.width_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(self.width_label)
        
        self.width_edit = QLineEdit()
        self.width_edit.setPlaceholderText("105.0")
        self.width_edit.setStyleSheet("QLineEdit { background-color: #ffffff; color: #111111; padding: 5px; border-radius: 3px; font-size: 12px; }")
        left_layout.addWidget(self.width_edit)
        
        self.dlt_panel = QWidget()
        dlt_layout = QVBoxLayout(self.dlt_panel)
        dlt_layout.setContentsMargins(0, 0, 0, 0)
        
        self.dlt_title = QLabel("DLT Coordinates:")
        self.dlt_title.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 14px;")
        dlt_layout.addWidget(self.dlt_title)
        
        self.dlt_scroll = QWidget()
        self.dlt_scroll_layout = QVBoxLayout(self.dlt_scroll)
        self.dlt_scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.dlt_scroll)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)
        scroll_area.setMaximumHeight(400)
        
        dlt_layout.addWidget(scroll_area)
        self.dlt_panel.setVisible(False)
        left_layout.addWidget(self.dlt_panel)
        
        left_layout.addStretch(1)
        
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #141418;")
        right_layout = QVBoxLayout(right_panel)

        self.instructions = QLabel("Drag the orange circles to adjust the grid corners\nThe grid represents the field boundaries\nUse scroll wheel to zoom in/out")
        self.instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instructions.setStyleSheet("font-size: 13px; padding: 8px; color: #a0a0a0;")
        right_layout.addWidget(self.instructions)

        height, width, channel = frame.shape
        bytes_per_line = 3 * width
        qimg = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()
        self.pixmap = QPixmap.fromImage(qimg)
        self.view = QGraphicsView()
        self.view.setStyleSheet("background-color: #0d0d10; border: none;")
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.scene.addPixmap(self.pixmap)
        right_layout.addWidget(self.view)

        btn_style = """
            QPushButton {
                background-color: #2c2c36; color: #e0e0e0;
                border: 1px solid #555; border-radius: 8px;
                padding: 8px 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0071e3; border-color: #0071e3; color: #fff; }
            QPushButton:pressed { background-color: #005bb5; }
        """
        button_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.setStyleSheet(btn_style)
        self.confirm_btn.clicked.connect(self.confirm)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setFixedHeight(40)
        self.reset_btn.setStyleSheet(btn_style)
        self.reset_btn.clicked.connect(self.reset_points)

        button_layout.addWidget(self.confirm_btn)
        button_layout.addWidget(self.reset_btn)
        right_layout.addLayout(button_layout)
        
        main_layout.addWidget(left_panel, 2)
        main_layout.addWidget(right_panel, 3)
        
        self.view.setMouseTracking(True)
        self.view.viewport().installEventFilter(self)
        
        self.create_initial_grid()
        self.view.fitInView(QRectF(0, 0, width, height), Qt.AspectRatioMode.KeepAspectRatio)
        
    def toggle_mode(self):
        if self.current_mode == "grid":
            self.switch_to_dlt_mode()
        else:
            self.switch_to_grid_mode()
            
    def switch_to_dlt_mode(self):
        self.current_mode = "dlt"
        self.mode_toggle_btn.setText("Switch to Grid")
        self.instructions.setText("Click anywhere on the image to add DLT points\nClick on existing points to remove them\nUse scroll wheel to zoom in/out")
        self.length_label.setVisible(False)
        self.length_edit.setVisible(False)
        self.width_label.setVisible(False)
        self.width_edit.setVisible(False)
        self.dlt_panel.setVisible(True)
        self.clear_grid_mode()
        self.setup_dlt_mode()
        
    def switch_to_grid_mode(self):
        self.current_mode = "grid"
        self.mode_toggle_btn.setText("Switch to DLT")
        self.instructions.setText("Drag the gray circles to adjust the grid corners\nThe grid represents the field boundaries\nUse scroll wheel to zoom in/out")
        self.length_label.setVisible(True)
        self.length_edit.setVisible(True)
        self.width_label.setVisible(True)
        self.width_edit.setVisible(True)
        self.dlt_panel.setVisible(False)
        self.clear_dlt_mode()
        self.create_initial_grid()
        
    def clear_grid_mode(self):
        for item in self.grid_items:
            self.scene.removeItem(item)
        self.grid_items.clear()
        for point in self.grid_points:
            self.scene.removeItem(point)
        self.grid_points.clear()
        
    def clear_dlt_mode(self):
        for point in self.dlt_points:
            self.scene.removeItem(point)
        self.dlt_points.clear()
        for i in reversed(range(self.dlt_scroll_layout.count())):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.dlt_coordinates.clear()
        
    def setup_dlt_mode(self):
        pass
        
    def eventFilter(self, source, event):
        if source is self.view.viewport():
            t = event.type()
            
            if t == event.Type.Wheel:
                if event.angleDelta().y() > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()
                return True
                
            elif t == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._pan_start = event.pos()
                    self.view.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
                elif event.button() == Qt.MouseButton.LeftButton and self.current_mode == "dlt":
                    pos = self.view.mapToScene(event.pos())
                    self.handle_dlt_click(pos)
                    return True
                    
            elif t == event.Type.MouseMove:
                if self._pan_start is not None:
                    delta = event.pos() - self._pan_start
                    self._pan_start = event.pos()
                    self.view.horizontalScrollBar().setValue(
                        self.view.horizontalScrollBar().value() - delta.x())
                    self.view.verticalScrollBar().setValue(
                        self.view.verticalScrollBar().value() - delta.y())
                    return True
                    
            elif t == event.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._pan_start = None
                    self.view.setCursor(Qt.CursorShape.ArrowCursor)
                    return True
                    
        return super().eventFilter(source, event)
        
    def handle_dlt_click(self, scene_pos):
        for i, point in enumerate(self.dlt_points):
            if point.contains(scene_pos):
                self.remove_dlt_point(i)
                return
        self.add_dlt_point(scene_pos.x(), scene_pos.y())
        
    def add_dlt_point(self, x, y):
        point_id = len(self.dlt_points)
        point = DLTPoint(x, y, point_id, self)
        self.scene.addItem(point)
        self.dlt_points.append(point)
        self.add_coordinate_inputs(point_id)
        
    def remove_dlt_point(self, point_id):
        point = self.dlt_points[point_id]
        self.scene.removeItem(point)
        self.dlt_points.pop(point_id)
        self.remove_coordinate_inputs(point_id)
        for i, point in enumerate(self.dlt_points):
            point.point_id = i
            point.text_item.setPlainText(str(i + 1))
        self.update_dlt_coordinates()
        
    def add_coordinate_inputs(self, point_id):
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: #2c2c36; border: 1px solid #444; border-radius: 8px; margin: 2px; }")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        label = QLabel(f"Point {point_id + 1}:")
        label.setFixedWidth(70)
        label.setStyleSheet("font-weight: bold; font-size: 12px; color: #e0e0e0;")
        layout.addWidget(label)
        real_x_edit = QLineEdit()
        real_x_edit.setPlaceholderText("Real X")
        real_x_edit.setFixedWidth(100)
        real_x_edit.setStyleSheet("QLineEdit { padding: 8px; font-size: 12px; border: 1px solid #555; border-radius: 5px; background-color: #1e1e24; color: #f0f0f0; } QLineEdit:focus { border-color: #0071e3; }")
        layout.addWidget(real_x_edit)
        real_y_edit = QLineEdit()
        real_y_edit.setPlaceholderText("Real Y")
        real_y_edit.setFixedWidth(100)
        real_y_edit.setStyleSheet("QLineEdit { padding: 8px; font-size: 12px; border: 1px solid #555; border-radius: 5px; background-color: #1e1e24; color: #f0f0f0; } QLineEdit:focus { border-color: #0071e3; }")
        layout.addWidget(real_y_edit)
        container.real_x_edit = real_x_edit
        container.real_y_edit = real_y_edit
        container.point_id = point_id
        real_x_edit.textChanged.connect(self.update_dlt_coordinates)
        real_y_edit.textChanged.connect(self.update_dlt_coordinates)
        self.dlt_scroll_layout.addWidget(container)
        
    def highlight_coordinate_input(self, point_id):
        for i in range(self.dlt_scroll_layout.count()):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'point_id'):
                widget.setStyleSheet("")
        for i in range(self.dlt_scroll_layout.count()):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'point_id') and widget.point_id == point_id:
                widget.setStyleSheet("QWidget { background-color: #2a3a1e; border: 2px solid #4caf50; border-radius: 5px; padding: 5px; }")
                break
                
    def remove_coordinate_inputs(self, point_id):
        for i in range(self.dlt_scroll_layout.count()):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'point_id') and widget.point_id == point_id:
                widget.setParent(None)
                break
        for i in range(self.dlt_scroll_layout.count()):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'point_id') and widget.point_id > point_id:
                widget.point_id -= 1
                label = widget.findChild(QLabel)
                if label:
                    label.setText(f"Point {widget.point_id + 1}:")
                    
    def update_dlt_coordinates(self):
        self.dlt_coordinates.clear()
        for i in range(self.dlt_scroll_layout.count()):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'point_id'):
                point_id = widget.point_id
                if point_id < len(self.dlt_points):
                    point = self.dlt_points[point_id]
                    center = point.get_center_pos()
                    real_x_text = widget.real_x_edit.text().strip()
                    real_y_text = widget.real_y_edit.text().strip()
                    if real_x_text and real_y_text:
                        try:
                            real_x = float(real_x_text)
                            real_y = float(real_y_text)
                            self.dlt_coordinates.append((center.x(), center.y(), real_x, real_y))
                        except ValueError:
                            pass
                            
    def create_initial_grid(self):
        for item in self.grid_items:
            self.scene.removeItem(item)
        self.grid_items.clear()
        for point in self.grid_points:
            self.scene.removeItem(point)
        self.grid_points.clear()
        
        frame_width = self.pixmap.width()
        frame_height = self.pixmap.height()
        margin = min(frame_width, frame_height) * 0.1
        grid_width = frame_width - 2 * margin
        grid_height = frame_height - 2 * margin
        
        corners = [
            (margin, margin + grid_height),
            (margin, margin),
            (margin + grid_width, margin),
            (margin + grid_width, margin + grid_height)
        ]
        
        for i, (x, y) in enumerate(corners):
            point = DraggableGridPoint(x, y, parent_window=self)
            self.scene.addItem(point)
            self.grid_points.append(point)
            
        self.update_grid()
        
    def update_grid(self):
        if len(self.grid_points) != 4:
            return
            
        grid_lines_to_remove = []
        for item in self.grid_items:
            if isinstance(item, (QGraphicsLineItem, QGraphicsPolygonItem)):
                grid_lines_to_remove.append(item)
        for item in grid_lines_to_remove:
            self.scene.removeItem(item)
            self.grid_items.remove(item)
            
        positions = [point.get_center_pos() for point in self.grid_points]
        bl, tl, tr, br = positions
        
        grid_rect = QGraphicsPolygonItem()
        grid_polygon = QPolygonF([tl, tr, br, bl])
        grid_rect.setPolygon(grid_polygon)
        grid_rect.setBrush(QColor(128, 128, 128, 100))
        grid_rect.setPen(QPen(QColor(128, 128, 128, 150), 2))
        grid_rect.setZValue(0)
        self.scene.addItem(grid_rect)
        self.grid_items.append(grid_rect)
        
        pen = QPen(QColor(128, 128, 128, 180), 2)
        for i in range(self.grid_size):
            t = i / (self.grid_size - 1)
            top_point = QPointF(tl.x() + t * (tr.x() - tl.x()), tl.y() + t * (tr.y() - tl.y()))
            bottom_point = QPointF(bl.x() + t * (br.x() - bl.x()), bl.y() + t * (br.y() - bl.y()))
            line = self.scene.addLine(top_point.x(), top_point.y(), bottom_point.x(), bottom_point.y(), pen)
            line.setZValue(1)
            self.grid_items.append(line)
            
        for i in range(self.grid_size):
            t = i / (self.grid_size - 1)
            left_point = QPointF(bl.x() + t * (tl.x() - bl.x()), bl.y() + t * (tl.y() - bl.y()))
            right_point = QPointF(br.x() + t * (tr.x() - br.x()), br.y() + t * (tr.y() - br.y()))
            line = self.scene.addLine(left_point.x(), left_point.y(), right_point.x(), right_point.y(), pen)
            line.setZValue(1)
            self.grid_items.append(line)
            
    def get_field_dimensions(self):
        try:
            # length_edit agora representa width, width_edit representa length
            width  = float(self.length_edit.text()) if self.length_edit.text() else 68.0
            length = float(self.width_edit.text())  if self.width_edit.text()  else 105.0
            return length, width
        except ValueError:
            return None, None
            
    def zoom_in(self):
        self.zoom = min(3.0, self.zoom * 1.2)
        self.view.scale(1.2, 1.2)
        
    def zoom_out(self):
        self.zoom = max(0.2, self.zoom / 1.2)
        self.view.scale(1/1.2, 1/1.2)
        
    def reset_points(self):
        for item in self.grid_items:
            self.scene.removeItem(item)
        self.grid_items.clear()
        for point in self.grid_points:
            self.scene.removeItem(point)
        self.grid_points.clear()
        for point in self.dlt_points:
            self.scene.removeItem(point)
        self.dlt_points.clear()
        for i in reversed(range(self.dlt_scroll_layout.count())):
            widget = self.dlt_scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.dlt_coordinates.clear()
        self.create_initial_grid()
        self.zoom = 1.0
        self.view.resetTransform()
        self.view.fitInView(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()), Qt.AspectRatioMode.KeepAspectRatio)
        
    def confirm(self):
        if self.current_mode == "grid":
            self.confirm_grid_mode()
        else:
            self.confirm_dlt_mode()
            
    def confirm_grid_mode(self):
        field_length, field_width = self.get_field_dimensions()
        if field_length is None or field_width is None:
            QMessageBox.critical(self, "Error", "Please enter valid field dimensions.")
            return
        corner_points = [(p.get_center_pos().x(), p.get_center_pos().y()) for p in self.grid_points]
        self.result = np.array(corner_points, dtype=np.float32)
        self.field_length = field_length
        self.field_width = field_width
        self.close()
        
    def confirm_dlt_mode(self):
        self.update_dlt_coordinates()
        if len(self.dlt_coordinates) < 4:
            QMessageBox.critical(self, "Error", "At least 4 DLT points with valid coordinates are required.")
            return
        src_points = []
        dst_points = []
        for img_x, img_y, real_x, real_y in self.dlt_coordinates:
            src_points.append([img_x, img_y])
            dst_points.append([real_x, real_y])
        validation = validate_homography_points(src_points, dst_points, min_points=4, min_area=1.0)
        if not validation['valid']:
            QMessageBox.critical(self, "Invalid Configuration", f"Point configuration is invalid: {validation['reason']}\nPlease ensure at least 4 non-collinear points are selected.")
            return
        self.result = {
            'src_points': np.array(src_points, dtype=np.float32),
            'dst_points': np.array(dst_points, dtype=np.float32),
            'mode': 'dlt',
            'validation': validation
        }
        if dst_points:
            x_coords = [p[0] for p in dst_points]
            y_coords = [p[1] for p in dst_points]
            self.field_length = max(x_coords)
            self.field_width = max(y_coords)
        self.close()
        
    def get_points(self):
        return self.result
        
    def get_field_dimensions_result(self):
        return self.field_length, self.field_width

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

def select_points_qt(frame, parent=None):
    from PySide6.QtCore import QEventLoop
    selector = PointSelectorWindow(frame, parent)
    selector.setWindowModality(Qt.WindowModality.ApplicationModal)
    selector.show()
    selector.raise_()
    selector.activateWindow()

    loop = QEventLoop()
    selector.closed.connect(loop.quit)
    loop.exec()

    return selector.get_points(), selector.get_field_dimensions_result()

def apply_homography(csv_path, image, output_path_csv, output_path_json, parent=None):
    df = pd.read_csv(csv_path)
    result = select_points_qt(image.copy(), parent)
    
    if result[0] is None:
        QMessageBox.warning(parent, "Canceled", "Selection of points was canceled.")
        return
        
    result_data, (field_length, field_width) = result
    
    if isinstance(result_data, dict) and result_data.get('mode') == 'dlt':
        src_points = result_data['src_points']
        dst_points = result_data['dst_points']
        validation = result_data['validation']
        h_matrix, _ = cv2.findHomography(src_points, dst_points, method=0)
        params = {
            "src_points": src_points.tolist(),
            "dst_points": dst_points.tolist(),
            "field_length": field_length,
            "field_width": field_width,
            "homography_matrix": h_matrix.tolist(),
            "mode": "dlt",
            "validation": {
                "valid": bool(validation['valid']),
                "reason": str(validation['reason']),
                "colinear": bool(validation['colinear']),
                "all_points_colinear": bool(validation['all_points_colinear']),
                "area_sufficient": bool(validation['area_sufficient']),
                "area": float(validation['area']),
                "colinear_indices": [int(i) for i in validation['colinear_indices']],
                "colinear_count": int(validation['colinear_count']),
                "non_colinear_count": int(validation['non_colinear_count'])
            }
        }

        reproj = compute_reprojection_error(h_matrix, src_points, dst_points)
        gate = calibration_gate(reproj['mean_error_m'], reproj['max_error_m'])
        params["reprojection_error"] = reproj
        params["calibration_gate"] = gate

        if gate['status'] == CalibrationStatus.INVALID:
            QMessageBox.critical(
                parent, "Calibration rejected",
                "Calibration error too high — result blocked.\n\n"
                f"Mean reprojection error: {gate['mean_error_m']} m\n"
                f"Max reprojection error: {gate['max_error_m']} m\n\n"
                "Re-select the reference points (recommended: 6-8 well-distributed points) "
                "before transforming this video."
            )
            return
        elif gate['status'] == CalibrationStatus.REVIEW:
            QMessageBox.warning(
                parent, "Calibration needs review",
                "Calibration accepted with caveat — result flagged for manual review.\n\n"
                f"Mean reprojection error: {gate['mean_error_m']} m\n"
                f"Max reprojection error: {gate['max_error_m']} m"
            )
    else:
        src_points = result_data
        dst_points = np.array([
            [0, 0],
            [0, field_width],
            [field_length, field_width],
            [field_length, 0]
        ], dtype=np.float32)
        h_matrix, _ = cv2.findHomography(src_points, dst_points)
        params = {
            "src_points": src_points.tolist(),
            "field_length": field_length,
            "field_width": field_width,
            "homography_matrix": h_matrix.tolist(),
            "mode": "grid",
            "calibration_gate": {
                "status": "NOT_EVALUATED",
                "reason": "Grid mode assumes the four field corners as ground truth; "
                          "there is no independent reference to compute reprojection error against.",
            },
        }

    transformed_frames = []
    for _, row in df.iterrows():
        frame_data = {'frame': int(row['frame'])}
        for col in df.columns:
            if '_x' in col:
                base = col[:-2]
                x, y = row[f'{base}_x'], row[f'{base}_y']
                if not np.isnan(x) and not np.isnan(y):
                    pt = np.array([[[x, y]]], dtype=np.float32)
                    transformed = cv2.perspectiveTransform(pt, h_matrix)[0][0]
                    frame_data[f'{base}_x'] = round(transformed[0], 2)
                    frame_data[f'{base}_y'] = round(transformed[1], 2)
                else:
                    frame_data[f'{base}_x'] = np.nan
                    frame_data[f'{base}_y'] = np.nan
        transformed_frames.append(frame_data)
        
    df_transformed = pd.DataFrame(transformed_frames)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)
    df_transformed.to_csv(output_path_csv, index=False)
    
    with open(output_path_json, 'w') as f:
        json.dump(params, f)
        
    mode_text = "DLT" if isinstance(result_data, dict) and result_data.get('mode') == 'dlt' else "Grid"
    gate_line = ""
    gate_info = params.get("calibration_gate")
    if gate_info and gate_info.get("status") not in (None, "NOT_EVALUATED"):
        gate_line = (f"\nCalibration status: {gate_info['status']} "
                     f"(mean error {gate_info['mean_error_m']} m, max error {gate_info['max_error_m']} m)\n")
    QMessageBox.information(parent, "Transformation completed",
        f"{mode_text} transformation completed successfully!\n"
        f"{gate_line}\n"
        f"Transformed coordinates saved in:\n{output_path_csv}\n\n"
        f"Parameters saved in:\n{output_path_json}")

def preselected_homography(parent=None, csv_path=None, project_path=None):
    if not csv_path:
        csv_path, _ = QFileDialog.getOpenFileName(parent, "Select CSV to transform", "", "CSV files (*.csv)")
        if not csv_path:
            return
            
    json_path, _ = QFileDialog.getOpenFileName(parent, "Select Homography Params JSON", "", "JSON files (*.json)")
    if not json_path:
        return
        
    try:
        with open(json_path, 'r') as f:
            params = json.load(f)
            
        required_keys = ['src_points', 'field_length', 'field_width', 'homography_matrix']
        missing_keys = [key for key in required_keys if key not in params]
        if missing_keys:
            QMessageBox.critical(parent, "Invalid JSON", f"Missing required keys in JSON: {missing_keys}")
            return
            
        h_matrix = np.array(params['homography_matrix'], dtype=np.float32)

        gate_info = params.get("calibration_gate")
        if gate_info and gate_info.get("status") == CalibrationStatus.INVALID:
            QMessageBox.critical(
                parent, "Calibration rejected",
                "This homography file was marked INVALID by the calibration gate "
                f"(mean error {gate_info.get('mean_error_m')} m, "
                f"max error {gate_info.get('max_error_m')} m) and cannot be reused.\n\n"
                "Redo the calibration with better-distributed reference points."
            )
            return
        elif gate_info and gate_info.get("status") == CalibrationStatus.REVIEW:
            QMessageBox.warning(
                parent, "Calibration needs review",
                "This homography file was flagged REVIEW by the calibration gate "
                f"(mean error {gate_info.get('mean_error_m')} m, "
                f"max error {gate_info.get('max_error_m')} m). Proceeding, but treat "
                "the result with caution."
            )

        df = pd.read_csv(csv_path)
        x_columns = [col for col in df.columns if col.endswith('_x')]
        
        if not x_columns:
            QMessageBox.warning(parent, "No Coordinates", "No coordinate columns found in CSV (columns ending with '_x')")
            return
            
        missing_y_columns = []
        for x_col in x_columns:
            base = x_col[:-2]
            y_col = f"{base}_y"
            if y_col not in df.columns:
                missing_y_columns.append(y_col)
                
        if missing_y_columns:
            QMessageBox.warning(parent, "Missing Y Columns", f"Missing corresponding Y columns: {missing_y_columns}")
            return
            
        transformed_frames = []
        transformation_count = 0
        null_count = 0
        
        for _, row in df.iterrows():
            frame_data = {}
            for col in df.columns:
                if not col.endswith('_x') and not col.endswith('_y'):
                    frame_data[col] = row[col]
                    
            for x_col in x_columns:
                base = x_col[:-2]
                y_col = f"{base}_y"
                x_val = row[x_col]
                y_val = row[y_col]
                x_is_valid = False
                y_is_valid = False
                
                try:
                    if pd.notna(x_val) and str(x_val).strip() != '':
                        x_float = float(x_val)
                        if not np.isnan(x_float) and not np.isinf(x_float):
                            x_is_valid = True
                    if pd.notna(y_val) and str(y_val).strip() != '':
                        y_float = float(y_val)
                        if not np.isnan(y_float) and not np.isinf(y_float):
                            y_is_valid = True
                except (ValueError, TypeError):
                    pass
                    
                if x_is_valid and y_is_valid:
                    try:
                        pt = np.array([[[x_float, y_float]]], dtype=np.float32)
                        transformed = cv2.perspectiveTransform(pt, h_matrix)[0][0]
                        frame_data[x_col] = round(transformed[0], 2)
                        frame_data[y_col] = round(transformed[1], 2)
                        transformation_count += 1
                    except Exception as e:
                        frame_data[x_col] = np.nan
                        frame_data[y_col] = np.nan
                        null_count += 1
                else:
                    frame_data[x_col] = np.nan
                    frame_data[y_col] = np.nan
                    null_count += 1
                    
            transformed_frames.append(frame_data)
            
        df_transformed = pd.DataFrame(transformed_frames)
        for col in df.columns:
            if col not in df_transformed.columns:
                df_transformed[col] = df[col]
        df_transformed = df_transformed[df.columns]
        
        if project_path:
            homography_dir = os.path.join(project_path, "data", "homography")
            os.makedirs(homography_dir, exist_ok=True)
            csv_basename = os.path.splitext(os.path.basename(csv_path))[0]
            if csv_basename.endswith('_tracked'):
                video_name = csv_basename[:-8]
            else:
                video_name = csv_basename
            output_csv = os.path.join(homography_dir, f"{video_name}_homography.csv")
        else:
            output_folder = QFileDialog.getExistingDirectory(parent, "Select Output Folder")
            if not output_folder:
                return
            base_name = os.path.splitext(os.path.basename(csv_path))[0]
            output_csv = os.path.join(output_folder, f"{base_name}_homography.csv")
            
        df_transformed.to_csv(output_csv, index=False)
        success_msg = (f"Transformation completed successfully!\n\n"
                      f"File saved: {output_csv}\n\n"
                      f"Statistics:\n"
                      f"• Total rows: {len(df)}\n"
                      f"• Coordinate columns: {len(x_columns)}\n"
                      f"• Successful transformations: {transformation_count}\n"
                      f"• Null/missing values: {null_count}")
        QMessageBox.information(parent, "Transformation Completed", success_msg)
        
    except json.JSONDecodeError as e:
        QMessageBox.critical(parent, "JSON Error", f"Invalid JSON file: {e}")
    except FileNotFoundError as e:
        QMessageBox.critical(parent, "File Error", f"File not found: {e}")
    except Exception as e:
        QMessageBox.critical(parent, "Error applying homography", f"Unexpected error: {str(e)}\n\nPlease check that:\n1. The JSON file is from a fixed camera homography\n2. The CSV file has coordinate columns ending with '_x' and '_y'\n3. The homography matrix is valid")

class HomographyWindow(QWidget):
    def __init__(self, video_path=None, project_path=None):
        super().__init__()
        self.setWindowTitle("Homography Tool")
        self.setFixedSize(400, 300)
        self.video_path = video_path
        self.project_path = project_path
        self.csv_path = None
        
        layout = QVBoxLayout()
        title_label = QLabel("Select your camera type:")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("QLabel { font-size: 18px; font-weight: bold; color: #333333; margin: 15px 0px; padding: 5px; }")
        layout.addWidget(title_label)
        
        self.video_status_label = QLabel("No video loaded")
        self.video_status_label.setStyleSheet("QLabel { color: #666666; font-style: italic; margin: 5px 0px; }")
        layout.addWidget(self.video_status_label)
        
        self.csv_status_label = QLabel("No CSV file loaded")
        self.csv_status_label.setStyleSheet("QLabel { color: #666666; font-style: italic; margin: 5px 0px; }")
        layout.addWidget(self.csv_status_label)
        
        self.broadcast_btn = QPushButton("Broadcast camera")
        self.broadcast_btn.setFixedHeight(40)
        self.broadcast_btn.setEnabled(False)
        self.broadcast_btn.setToolTip("Em breve")
        layout.addWidget(self.broadcast_btn)
        
        self.manual_btn = QPushButton("Fixed camera")
        self.manual_btn.setFixedHeight(40)
        self.manual_btn.clicked.connect(self.manual_homography_project)
        layout.addWidget(self.manual_btn)
        
        self.preselected_btn = QPushButton("Pre-selected Points")
        self.preselected_btn.setFixedHeight(40)
        self.preselected_btn.setEnabled(False)
        self.preselected_btn.clicked.connect(self.preselected_homography_project)
        layout.addWidget(self.preselected_btn)

        self.setLayout(layout)
        
        if self.project_path:
            self.load_files_from_project()

    def load_files_from_project(self):
        if not self.project_path:
            return

        # ── Vídeo ────────────────────────────────────────────────────────────
        if self.video_path and os.path.exists(self.video_path):
            filename = os.path.basename(self.video_path)
            self.video_status_label.setText(f"Video loaded: {filename}")
            self.video_status_label.setStyleSheet("QLabel { color: #4CAF50; font-weight: bold; margin: 5px 0px; }")
        else:
            self.video_status_label.setText("No video loaded")
            self.video_status_label.setStyleSheet("QLabel { color: #666666; font-style: italic; margin: 10px 0px; }")

        # ── CSV (usa lógica robusta) ───────────────────────────────────────────
        found_csv = find_csv_for_video(self.video_path or "", self.project_path)
        if found_csv:
            self.csv_path = found_csv
            filename = os.path.basename(self.csv_path)
            self.csv_status_label.setText(f"CSV loaded: {filename}")
            self.csv_status_label.setStyleSheet("QLabel { color: #4CAF50; font-weight: bold; margin: 5px 0px; }")
            self.preselected_btn.setEnabled(True)
        else:
            self.csv_path = None
            self.csv_status_label.setText("No CSV file found — run Tracker first")
            self.csv_status_label.setStyleSheet("QLabel { color: #FF5722; font-style: italic; margin: 5px 0px; }")
            self.preselected_btn.setEnabled(False)

    def manual_homography_project(self):
        if not self.video_path or not os.path.exists(self.video_path):
            QMessageBox.warning(self, "No Video", "No video is selected. Please select a video in the main application first.")
            return
            
        if not self.csv_path or not os.path.exists(self.csv_path):
            QMessageBox.warning(self, "No CSV", "No CSV file found in the project. Please run pixel coordinate extraction first.")
            return
            
        cap = cv2.VideoCapture(self.video_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            QMessageBox.critical(self, "Error", "Unable to capture first frame of video.")
            return
            
        homography_dir = os.path.join(self.project_path, "data", "homography")
        metadata_dir = os.path.join(self.project_path, "metadata")
        os.makedirs(homography_dir, exist_ok=True)
        os.makedirs(metadata_dir, exist_ok=True)
        
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        output_csv = os.path.join(homography_dir, f"{video_name}_homography.csv")
        output_json = os.path.join(metadata_dir, f"{video_name}_homography_matrix.json")
        
        apply_homography(self.csv_path, frame, output_csv, output_json, self)

    def preselected_homography_project(self):
        if not self.csv_path or not os.path.exists(self.csv_path):
            QMessageBox.warning(self, "No CSV", "No CSV file found in the project. Please run pixel coordinate extraction first.")
            return
        preselected_homography(self, self.csv_path, self.project_path)

def run_homography(video_path=None, project_path=None):
    window = HomographyWindow(video_path=video_path, project_path=project_path)
    return window

from PySide6.QtCore import QObject, Slot

class HomographyManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.window = None

    @Slot(str, str)
    def open_tool(self, video_path, project_path):
        if self.window is not None:
            self.window.close()
            self.window.deleteLater()
            self.window = None
        self.window = HomographyWindow(video_path=video_path, project_path=project_path)
        self.window.show()

    @Slot(str, str)
    def open_preselected(self, video_path, project_path):
        """Chama diretamente o fluxo de Pre-selected Points com resolução robusta do CSV"""
        csv_path = find_csv_for_video(video_path, project_path)
        preselected_homography(parent=None, csv_path=csv_path, project_path=project_path)

    @Slot(str, str)
    def open_trigger_zone(self, video_path: str, project_path: str):
        from modules.trigger_zone import select_trigger_zone
        select_trigger_zone(video_path, project_path, parent=None)

    @Slot(str, str)
    def apply_trigger_zone_slot(self, video_path: str, project_path: str):
        from modules.trigger_zone import apply_trigger_zone as _apply_tz
        _apply_tz(video_path, project_path, parent=None)

    @Slot(str, str)
    def open_zone_viewer(self, video_path: str, project_path: str):
        from modules.trigger_zone import open_trigger_zone_viewer, zone_exists
        if not zone_exists(video_path, project_path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Sem zona",
                                "Aplique a trigger zone primeiro.")
            return
        self._zone_viewer = open_trigger_zone_viewer(
            video_path, project_path, parent=None)
