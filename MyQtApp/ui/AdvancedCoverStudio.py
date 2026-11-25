from __future__ import annotations

import copy
import math
import os
import shutil
import uuid

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QFont, QPixmap, QPolygonF, QTransform, QImage
)
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSpinBox, QLineEdit, QColorDialog, QFileDialog,
    QListWidget, QListWidgetItem, QFrame, QScrollArea, QGridLayout,
    QSizePolicy, QMessageBox, QButtonGroup
)

from MyQtApp.config import (
    BUNDLE_DIR, EXE_DIR, PERFIL_DIR, PROJECT_ROOT, USER_DATA_DIR
)
from MyQtApp.i18n import t

CUSTOM_STICKERS_DIR = os.path.join(USER_DATA_DIR, "custom_stickers")

STICKER_PRESETS = [
    ("pokeball", "Pokéball", "#dc2626"),
    ("superball", "Super Ball", "#2563eb"),
    ("ultraball", "Ultra Ball", "#eab308"),
    ("masterball", "Master Ball", "#9333ea"),
    ("bolt", "Rayo", "#facc15"),
    ("flame", "Fuego", "#ef4444"),
    ("water", "Agua", "#0ea5e9"),
    ("leaf", "Planta", "#22c55e"),
    ("star", "Estrella", "#fbbf24"),
    ("crown", "Corona", "#f59e0b"),
    ("shield", "Escudo", "#6366f1"),
    ("heart", "Corazón", "#ec4899"),
    ("sparkle", "Destello", "#a855f7"),
    ("diamond", "Diamante", "#38bdf8"),
]

SHAPE_PRESETS = [
    ("rect", "Rectángulo"),
    ("rounded_rect", "Redondeado"),
    ("circle", "Círculo"),
    ("triangle", "Triángulo"),
    ("diamond_shape", "Rombo"),
    ("star_shape", "Estrella 5P"),
    ("hexagon", "Hexágono"),
    ("stripe", "Franja"),
    ("frame", "Marco"),
]

POKEMON_STICKER_FILES = [
    ("charizard.webp", "Charizard"),
    ("blastoise.webp", "Blastoise"),
    ("pikachu.webp", "Pikachu"),
    ("umbreon.webp", "Umbreon"),
    ("sylveon.webp", "Sylveon"),
    ("snorlax.webp", "Snorlax"),
]

_sticker_pixmap_cache: dict[str, QPixmap | None] = {}


def normalize_advanced_design(raw: dict | None) -> dict:
    if not isinstance(raw, dict):
        return {
            "front": [],
            "back": [],
            "inside": [],
            "back_color": None,
            "inside_color": None,
            "inside_show_pocket": True,
            "inside_show_title": True,
            "inside_title": None,
            "inside_subtitle": None,
        }
    return {
        "front": [copy.deepcopy(el) for el in raw.get("front", []) if isinstance(el, dict)],
        "back": [copy.deepcopy(el) for el in raw.get("back", []) if isinstance(el, dict)],
        "inside": [copy.deepcopy(el) for el in raw.get("inside", []) if isinstance(el, dict)],
        "back_color": raw.get("back_color") or None,
        "inside_color": raw.get("inside_color") or None,
        "inside_show_pocket": bool(raw.get("inside_show_pocket", True)),
        "inside_show_title": bool(raw.get("inside_show_title", True)),
        "inside_title": raw.get("inside_title") if raw.get("inside_title") is not None else None,
        "inside_subtitle": raw.get("inside_subtitle") if raw.get("inside_subtitle") is not None else None,
    }


def has_advanced_elements(raw: dict | None) -> bool:
    if not isinstance(raw, dict):
        return False
    return bool(
        raw.get("front")
        or raw.get("back")
        or raw.get("inside")
        or raw.get("back_color")
        or raw.get("inside_color")
        or raw.get("inside_title")
        or raw.get("inside_subtitle")
        or raw.get("inside_show_pocket") is False
        or raw.get("inside_show_title") is False
    )


def resolve_sticker_pixmap(path_or_name: str | None) -> QPixmap | None:
    if not path_or_name:
        return None
    if path_or_name in _sticker_pixmap_cache:
        return _sticker_pixmap_cache[path_or_name]

    candidates = [
        path_or_name,
        os.path.join(CUSTOM_STICKERS_DIR, path_or_name),
        os.path.join(PERFIL_DIR, path_or_name),
        os.path.join(BUNDLE_DIR, "assets", "perfil", path_or_name),
        os.path.join(EXE_DIR, "assets", "perfil", path_or_name),
        os.path.join(PROJECT_ROOT, "assets", "perfil", path_or_name),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            pix = QPixmap(p)
            if not pix.isNull():
                _sticker_pixmap_cache[path_or_name] = pix
                return pix
    _sticker_pixmap_cache[path_or_name] = None
    return None


def _star_poly(cx: float, cy: float, r_out: float, r_in: float, pts: int = 5) -> QPolygonF:
    poly = QPolygonF()
    for i in range(pts * 2):
        ang = -math.pi / 2.0 + i * math.pi / pts
        r = r_out if i % 2 == 0 else r_in
        poly.append(QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    return poly


def _regular_poly(cx: float, cy: float, r: float, sides: int, angle_offset: float = -math.pi / 2.0) -> QPolygonF:
    poly = QPolygonF()
    for i in range(sides):
        ang = angle_offset + (2.0 * math.pi * i) / sides
        poly.append(QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    return poly


def _draw_vector_sticker(painter: QPainter, key: str, rect: QRectF, color: QColor, border_col: QColor, border_w: float):
    cx = rect.center().x()
    cy = rect.center().y()
    r = min(rect.width(), rect.height()) * 0.46

    if key in ("pokeball", "superball", "ultraball", "masterball"):
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r, r)
        painter.setClipPath(clip)
        top_colors = {
            "pokeball": QColor("#dc2626"),
            "superball": QColor("#2563eb"),
            "ultraball": QColor("#18181b"),
            "masterball": QColor("#7e22ce"),
        }
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(top_colors[key])
        painter.drawRect(QRectF(cx - r, cy - r, r * 2, r))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRect(QRectF(cx - r, cy, r * 2, r))
        if key == "superball":
            painter.setBrush(QColor("#ef4444"))
            painter.drawPolygon(QPolygonF([
                QPointF(cx - r * 0.85, cy - r * 0.65),
                QPointF(cx - r * 0.35, cy - r * 0.18),
                QPointF(cx - r * 0.65, cy - r * 0.85),
            ]))
            painter.drawPolygon(QPolygonF([
                QPointF(cx + r * 0.85, cy - r * 0.65),
                QPointF(cx + r * 0.35, cy - r * 0.18),
                QPointF(cx + r * 0.65, cy - r * 0.85),
            ]))
        elif key == "ultraball":
            painter.setBrush(QColor("#eab308"))
            painter.drawRect(QRectF(cx - r * 0.55, cy - r * 0.95, r * 0.22, r * 0.85))
            painter.drawRect(QRectF(cx + r * 0.33, cy - r * 0.95, r * 0.22, r * 0.85))
        elif key == "masterball":
            painter.setBrush(QColor("#ec4899"))
            painter.drawEllipse(QPointF(cx - r * 0.52, cy - r * 0.42), r * 0.28, r * 0.20)
            painter.drawEllipse(QPointF(cx + r * 0.52, cy - r * 0.42), r * 0.28, r * 0.20)
        painter.setBrush(QColor("#18181b"))
        painter.drawRect(QRectF(cx - r, cy - r * 0.13, r * 2, r * 0.26))
        painter.restore()
        painter.setPen(QPen(QColor("#18181b"), max(1.5, r * 0.09)))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(cx, cy), r * 0.28, r * 0.28)
        painter.setPen(QPen(QColor("#18181b"), max(1.2, r * 0.08)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)
        return

    painter.setBrush(color)
    painter.setPen(QPen(border_col, border_w) if border_w > 0 else Qt.PenStyle.NoPen)

    if key == "star":
        painter.drawPolygon(_star_poly(cx, cy, r, r * 0.44, 5))
    elif key == "sparkle":
        painter.drawPolygon(_star_poly(cx, cy, r, r * 0.28, 4))
    elif key == "bolt":
        poly = QPolygonF([
            QPointF(cx + r * 0.18, cy - r),
            QPointF(cx - r * 0.48, cy + r * 0.08),
            QPointF(cx - r * 0.02, cy + r * 0.08),
            QPointF(cx - r * 0.22, cy + r),
            QPointF(cx + r * 0.52, cy - r * 0.10),
            QPointF(cx + r * 0.05, cy - r * 0.10),
        ])
        painter.drawPolygon(poly)
    elif key == "flame":
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.cubicTo(cx + r * 0.85, cy - r * 0.3, cx + r * 0.85, cy + r * 0.75, cx, cy + r)
        path.cubicTo(cx - r * 0.85, cy + r * 0.75, cx - r * 0.85, cy - r * 0.2, cx, cy - r)
        painter.drawPath(path)
    elif key == "water":
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.cubicTo(cx + r * 0.9, cy + r * 0.1, cx + r * 0.75, cy + r * 0.95, cx, cy + r)
        path.cubicTo(cx - r * 0.75, cy + r * 0.95, cx - r * 0.9, cy + r * 0.1, cx, cy - r)
        painter.drawPath(path)
    elif key == "leaf":
        path = QPainterPath()
        path.moveTo(cx + r * 0.8, cy - r * 0.8)
        path.cubicTo(cx + r * 0.9, cy + r * 0.6, cx - r * 0.2, cy + r * 0.95, cx - r * 0.8, cy + r * 0.8)
        path.cubicTo(cx - r * 0.9, cy - r * 0.6, cx + r * 0.2, cy - r * 0.95, cx + r * 0.8, cy - r * 0.8)
        painter.drawPath(path)
    elif key == "crown":
        poly = QPolygonF([
            QPointF(cx - r * 0.85, cy + r * 0.55),
            QPointF(cx - r * 0.9, cy - r * 0.45),
            QPointF(cx - r * 0.4, cy + r * 0.05),
            QPointF(cx, cy - r * 0.72),
            QPointF(cx + r * 0.4, cy + r * 0.05),
            QPointF(cx + r * 0.9, cy - r * 0.45),
            QPointF(cx + r * 0.85, cy + r * 0.55),
        ])
        painter.drawPolygon(poly)
    elif key == "shield":
        path = QPainterPath()
        path.moveTo(cx, cy - r * 0.92)
        path.lineTo(cx + r * 0.85, cy - r * 0.55)
        path.cubicTo(cx + r * 0.82, cy + r * 0.35, cx + r * 0.25, cy + r * 0.85, cx, cy + r * 0.95)
        path.cubicTo(cx - r * 0.25, cy + r * 0.85, cx - r * 0.82, cy + r * 0.35, cx - r * 0.85, cy - r * 0.55)
        path.closeSubpath()
        painter.drawPath(path)
    elif key == "heart":
        path = QPainterPath()
        path.moveTo(cx, cy + r * 0.85)
        path.cubicTo(cx - r * 1.25, cy + r * 0.1, cx - r * 0.85, cy - r * 0.95, cx, cy - r * 0.35)
        path.cubicTo(cx + r * 0.85, cy - r * 0.95, cx + r * 1.25, cy + r * 0.1, cx, cy + r * 0.85)
        painter.drawPath(path)
    elif key == "diamond":
        poly = QPolygonF([
            QPointF(cx - r * 0.55, cy - r * 0.65),
            QPointF(cx + r * 0.55, cy - r * 0.65),
            QPointF(cx + r * 0.95, cy - r * 0.15),
            QPointF(cx, cy + r * 0.85),
            QPointF(cx - r * 0.95, cy - r * 0.15),
        ])
        painter.drawPolygon(poly)


def render_advanced_elements(painter: QPainter, target_rect: QRectF, elements: list[dict] | None):
    """Dibuja la lista de stickers, figuras geométricas, imágenes y texto sobre target_rect."""
    if not elements or target_rect.width() <= 2 or target_rect.height() <= 2:
        return

    for el in elements:
        if not isinstance(el, dict):
            continue
        cx = target_rect.left() + float(el.get("x", 0.5)) * target_rect.width()
        cy = target_rect.top() + float(el.get("y", 0.5)) * target_rect.height()
        ew = max(8.0, float(el.get("w", 0.22)) * target_rect.width())
        eh = max(8.0, float(el.get("h", 0.22)) * target_rect.height())
        rot = float(el.get("rotation", 0.0))
        opacity = max(0.05, min(1.0, float(el.get("opacity", 1.0))))
        fill_col = QColor(el.get("color", "#fbbf24"))
        if not fill_col.isValid():
            fill_col = QColor("#fbbf24")
        border_col = QColor(el.get("border_color", "#ffffff"))
        if not border_col.isValid():
            border_col = QColor("#ffffff")
        border_w = max(0.0, float(el.get("border_width", 2.0)))

        painter.save()
        painter.setOpacity(painter.opacity() * opacity)
        painter.translate(cx, cy)
        if rot:
            painter.rotate(rot)
        local_rect = QRectF(-ew / 2.0, -eh / 2.0, ew, eh)

        kind = el.get("kind", "sticker")
        if kind == "sticker":
            _draw_vector_sticker(painter, el.get("key", "pokeball"), local_rect, fill_col, border_col, border_w)
        elif kind == "image":
            pix = resolve_sticker_pixmap(el.get("image_path") or el.get("key"))
            if pix and not pix.isNull():
                scaled = pix.scaled(
                    int(max(8, ew)), int(max(8, eh)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawPixmap(
                    QPointF(-scaled.width() / 2.0, -scaled.height() / 2.0),
                    scaled,
                )
        elif kind == "shape":
            shape_key = el.get("key", "circle")
            if shape_key == "frame":
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(fill_col, max(2.5, border_w + 2.0)))
                painter.drawRoundedRect(local_rect, 8, 8)
            else:
                painter.setBrush(fill_col)
                painter.setPen(QPen(border_col, border_w) if border_w > 0 else Qt.PenStyle.NoPen)
                if shape_key == "rect":
                    painter.drawRect(local_rect)
                elif shape_key == "rounded_rect":
                    painter.drawRoundedRect(local_rect, min(ew, eh) * 0.22, min(ew, eh) * 0.22)
                elif shape_key == "circle":
                    painter.drawEllipse(local_rect)
                elif shape_key == "triangle":
                    painter.drawPolygon(_regular_poly(0, 0, min(ew, eh) * 0.48, 3))
                elif shape_key == "diamond_shape":
                    painter.drawPolygon(QPolygonF([
                        QPointF(0, -eh * 0.48),
                        QPointF(ew * 0.48, 0),
                        QPointF(0, eh * 0.48),
                        QPointF(-ew * 0.48, 0),
                    ]))
                elif shape_key == "star_shape":
                    r = min(ew, eh) * 0.48
                    painter.drawPolygon(_star_poly(0, 0, r, r * 0.45, 5))
                elif shape_key == "hexagon":
                    painter.drawPolygon(_regular_poly(0, 0, min(ew, eh) * 0.48, 6))
                elif shape_key == "stripe":
                    painter.drawRoundedRect(QRectF(-ew * 0.5, -eh * 0.18, ew, eh * 0.36), 4, 4)
        elif kind == "text":
            txt = str(el.get("text") or "PokeBinder")
            font_px = max(9, int(eh * 0.52))
            font = QFont("Segoe UI", font_px, QFont.Weight.Black)
            painter.setFont(font)
            if border_w > 0:
                painter.setPen(QPen(border_col, max(1.0, border_w)))
                painter.drawText(local_rect.translated(1.5, 1.5), Qt.AlignmentFlag.AlignCenter, txt)
            painter.setPen(fill_col)
            painter.drawText(local_rect, Qt.AlignmentFlag.AlignCenter, txt)

        painter.restore()


def render_back_cover_surface(
    painter: QPainter,
    rect: QRectF,
    base_color: QColor,
    spine_color: QColor,
    strap_color: QColor,
    item_type: str = "binder",
    elements: list[dict] | None = None,
    name: str = "",
):
    """Dibuja la cara trasera (contraportada) del Binder o Portamazos + stickers traseros."""
    path = QPainterPath()
    path.addRoundedRect(rect, 12, 12)
    painter.save()
    painter.setClipPath(path)

    grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
    grad.setColorAt(0.0, base_color.lighter(110))
    grad.setColorAt(0.55, base_color)
    grad.setColorAt(1.0, base_color.darker(125))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(rect)

    # Textura / lomo en el lado derecho al mirar desde atrás
    if item_type == "binder":
        spine_w = max(14.0, rect.width() * 0.105)
        strap_w = max(12.0, rect.width() * 0.09)
        spine_x = rect.right() - spine_w
        painter.setBrush(spine_color)
        painter.drawRect(QRectF(spine_x, rect.top(), spine_w, rect.height()))
        strap_x = rect.left() + 12.0
        painter.setBrush(strap_color)
        painter.drawRect(QRectF(strap_x, rect.top(), strap_w, rect.height()))
    else:
        # Costura trasera estilo Alcove Flip Deck Box
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(10, 10, -10, -10), 8, 8)
        painter.setPen(QPen(QColor(0, 0, 0, 110), 2.0))
        painter.drawLine(
            QPointF(rect.left(), rect.top() + rect.height() * 0.32),
            QPointF(rect.right(), rect.top() + rect.height() * 0.32),
        )

    # Sello discreto trasero
    painter.setPen(QColor(255, 255, 255, 70))
    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    painter.drawText(
        QRectF(rect.left(), rect.bottom() - 28, rect.width(), 20),
        Qt.AlignmentFlag.AlignCenter,
        f"POKEBINDER  •  {name[:24]}" if name else "POKEBINDER STUDIO",
    )

    render_advanced_elements(painter, rect, elements)
    painter.restore()

    painter.setPen(QPen(QColor(255, 255, 255, 85), 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, 12, 12)


def render_inside_cover_surface(
    painter: QPainter,
    rect: QRectF,
    interior_color: str | None,
    folder_name: str = "Mi Binder",
    advanced_design: dict | None = None,
    include_advanced: bool = True,
):
    """Dibuja la cara interior de portada del Binder con su bolsillo, emblema y stickers avanzados."""
    adv = normalize_advanced_design(advanced_design)
    effective_color = adv.get("inside_color") or interior_color or "#18181e"

    base_col = QColor(effective_color)
    if not base_col.isValid():
        base_col = QColor(24, 24, 30)

    luma = 0.299 * base_col.red() + 0.587 * base_col.green() + 0.114 * base_col.blue()
    text_col = QColor(45, 30, 40, 175) if luma > 155 else QColor(255, 255, 255, 165)
    seam_col = QColor(20, 20, 30, 55) if luma > 155 else QColor(255, 255, 255, 38)

    grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
    grad.setColorAt(0.0, base_col.darker(118))
    grad.setColorAt(0.6, base_col.darker(108))
    grad.setColorAt(1.0, base_col.darker(126))
    painter.setBrush(grad)
    painter.setPen(QPen(seam_col, 1.2))
    painter.drawRoundedRect(rect, 7, 7)

    # Costura interior perimetral simulando forro de cuero/gamuza de portada
    painter.setPen(QPen(seam_col, 1.0, Qt.PenStyle.DashLine))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(10, 10, -10, -10), 6, 6)

    # Bolsillo interior inferior de portada
    if adv.get("inside_show_pocket", True):
        pocket_h = rect.height() * 0.24
        pocket_rect = QRectF(rect.left() + 14, rect.bottom() - pocket_h - 14, rect.width() - 28, pocket_h)
        pocket_path = QPainterPath()
        pocket_path.moveTo(pocket_rect.left(), pocket_rect.top() + 14)
        pocket_path.lineTo(pocket_rect.right(), pocket_rect.top())
        pocket_path.lineTo(pocket_rect.right(), pocket_rect.bottom())
        pocket_path.lineTo(pocket_rect.left(), pocket_rect.bottom())
        pocket_path.closeSubpath()
        painter.setPen(QPen(seam_col, 1.1))
        painter.setBrush(base_col.darker(132))
        painter.drawPath(pocket_path)

    # Emblema de título / subtítulo del interior de portada
    if adv.get("inside_show_title", True):
        custom_title = adv.get("inside_title")
        display_title = custom_title if (custom_title is not None and str(custom_title).strip()) else (folder_name or "Mi Binder")
        custom_sub = adv.get("inside_subtitle")
        display_sub = custom_sub if custom_sub is not None else "POKEBINDER  •  INTERIOR PORTADA"

        painter.setPen(text_col)
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(
            QRectF(rect.left() + 18, rect.top() + rect.height() * 0.34, rect.width() - 36, 32),
            Qt.AlignmentFlag.AlignCenter,
            display_title,
        )
        if display_sub:
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            painter.setPen(QColor(text_col.red(), text_col.green(), text_col.blue(), 120))
            painter.drawText(
                QRectF(rect.left() + 18, rect.top() + rect.height() * 0.34 + 28, rect.width() - 36, 22),
                Qt.AlignmentFlag.AlignCenter,
                display_sub,
            )

    if include_advanced:
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, 7, 7)
        painter.save()
        painter.setClipPath(clip_path)
        render_advanced_elements(painter, rect, adv.get("inside", []))
        painter.restore()


class _EditableCoverCanvas(QWidget):
    """Lienzo interactivo para arrastrar, escalar y seleccionar stickers/figuras."""
    selection_changed = pyqtSignal(int)
    elements_modified = pyqtSignal()

    def __init__(self, preview_provider, parent=None):
        super().__init__(parent)
        self._preview_provider = preview_provider
        self._face = "front"
        self._elements: list[dict] = []
        self._selected_idx = -1
        self._drag_mode = None  # "move" | "resize"
        self._drag_start = QPointF()
        self._orig_el = None
        self.setMinimumSize(320, 420)
        self.setMouseTracking(True)

    def set_state(self, face: str, elements: list[dict], selected_idx: int = -1):
        self._face = face
        self._elements = elements
        self._selected_idx = selected_idx if 0 <= selected_idx < len(elements) else -1
        self.update()

    def _cover_rect(self) -> QRectF:
        pad = 14.0
        avail_w = max(80.0, self.width() - pad * 2)
        avail_h = max(80.0, self.height() - pad * 2)
        ratio = 0.75 if self._preview_provider("is_binder") else 0.82
        if avail_w / avail_h > ratio:
            ch = avail_h
            cw = ch * ratio
        else:
            cw = avail_w
            ch = cw / ratio
        return QRectF((self.width() - cw) / 2.0, (self.height() - ch) / 2.0, cw, ch)

    def _el_rect(self, el: dict, cr: QRectF) -> QRectF:
        cx = cr.left() + float(el.get("x", 0.5)) * cr.width()
        cy = cr.top() + float(el.get("y", 0.5)) * cr.height()
        ew = max(14.0, float(el.get("w", 0.22)) * cr.width())
        eh = max(14.0, float(el.get("h", 0.22)) * cr.height())
        return QRectF(cx - ew / 2.0, cy - eh / 2.0, ew, eh)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        painter.fillRect(self.rect(), QColor("#f8ecf0"))
        cr = self._cover_rect()

        base_pix = self._preview_provider(
            "base_face_pixmap",
            self._face,
            int(cr.width()),
            int(cr.height()),
        )
        if base_pix and not base_pix.isNull():
            painter.drawPixmap(cr.topLeft(), base_pix)

        render_advanced_elements(painter, cr, self._elements)

        if 0 <= self._selected_idx < len(self._elements):
            sel_rect = self._el_rect(self._elements[self._selected_idx], cr)
            painter.setPen(QPen(QColor("#06b6d4"), 2.0, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel_rect)
            handle = QRectF(sel_rect.right() - 6, sel_rect.bottom() - 6, 12, 12)
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.setBrush(QColor("#06b6d4"))
            painter.drawEllipse(handle)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(event.position())
        cr = self._cover_rect()

        if 0 <= self._selected_idx < len(self._elements):
            sr = self._el_rect(self._elements[self._selected_idx], cr)
            handle = QRectF(sr.right() - 9, sr.bottom() - 9, 18, 18)
            if handle.contains(pos):
                self._drag_mode = "resize"
                self._drag_start = pos
                self._orig_el = copy.deepcopy(self._elements[self._selected_idx])
                return

        hit = -1
        for i in range(len(self._elements) - 1, -1, -1):
            if self._el_rect(self._elements[i], cr).contains(pos):
                hit = i
                break

        self._selected_idx = hit
        self.selection_changed.emit(hit)
        if hit >= 0:
            self._drag_mode = "move"
            self._drag_start = pos
            self._orig_el = copy.deepcopy(self._elements[hit])
        self.update()

    def mouseMoveEvent(self, event):
        if not self._drag_mode or self._orig_el is None or not (0 <= self._selected_idx < len(self._elements)):
            return
        pos = QPointF(event.position())
        cr = self._cover_rect()
        dx = (pos.x() - self._drag_start.x()) / max(1.0, cr.width())
        dy = (pos.y() - self._drag_start.y()) / max(1.0, cr.height())
        el = self._elements[self._selected_idx]

        if self._drag_mode == "move":
            el["x"] = max(0.05, min(0.95, float(self._orig_el.get("x", 0.5)) + dx))
            el["y"] = max(0.05, min(0.95, float(self._orig_el.get("y", 0.5)) + dy))
        elif self._drag_mode == "resize":
            delta = max(dx, dy) if abs(dx) >= abs(dy) else dy
            new_w = max(0.06, min(0.95, float(self._orig_el.get("w", 0.22)) + delta * 1.4))
            new_h = max(0.06, min(0.95, float(self._orig_el.get("h", 0.22)) + delta * 1.4))
            el["w"] = new_w
            el["h"] = new_h

        self.update()
        self.elements_modified.emit()

    def mouseReleaseEvent(self, event):
        self._drag_mode = None
        self._orig_el = None


class Interactive3DViewerDialog(QDialog):
    """
    Visor 3D interactivo (rotación libre 360° con el ratón) para inspeccionar
    el Binder o Portamazos completo (frente, lomo, hojas/grosor y parte trasera).
    """

    def __init__(
        self,
        title: str,
        front_pixmap: QPixmap,
        back_pixmap: QPixmap,
        spine_color: str = "#18181b",
        edge_color: str = "#e2e8f0",
        item_type: str = "binder",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"{t('Vista 3D')} — {title}")
        self.setMinimumSize(640, 620)
        self.resize(720, 680)
        self._front = front_pixmap
        self._back = back_pixmap
        self._spine_col = QColor(spine_color) if QColor(spine_color).isValid() else QColor("#18181b")
        self._edge_col = QColor(edge_color) if QColor(edge_color).isValid() else QColor("#e2e8f0")
        self._item_type = item_type

        self._yaw = -22.0   # grados (-180..180)
        self._pitch = 8.0   # grados (-35..35)
        self._auto_spin = False

        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #f56b7b;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        lbl_t = QLabel(f"{title}  •  {t('Arrastra para rotar 360° en 3D')}")
        lbl_t.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        hdr.addWidget(lbl_t)
        hdr.addStretch()
        layout.addLayout(hdr)

        self.canvas = _Viewer3DCanvas(self)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.canvas, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        btn_front = QPushButton(t("Frente"))
        btn_front.clicked.connect(lambda: self.set_angles(-15.0, 6.0))
        btn_spine = QPushButton(t("Lomo"))
        btn_spine.clicked.connect(lambda: self.set_angles(-88.0, 4.0))
        btn_back = QPushButton(t("Atrás"))
        btn_back.clicked.connect(lambda: self.set_angles(168.0, 6.0))
        self.btn_spin = QPushButton(t("Auto-girar"))
        self.btn_spin.setCheckable(True)
        self.btn_spin.toggled.connect(self._toggle_spin)
        btn_close = QPushButton(t("Cerrar"))
        btn_close.setStyleSheet("background-color: #f56b7b; border-color: #e11d48; color: #ffffff;")
        btn_close.clicked.connect(self.accept)

        controls.addWidget(btn_front)
        controls.addWidget(btn_spine)
        controls.addWidget(btn_back)
        controls.addWidget(self.btn_spin)
        controls.addStretch()
        controls.addWidget(btn_close)
        layout.addLayout(controls)

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(30)
        self._spin_timer.timeout.connect(self._on_spin_tick)

    def set_angles(self, yaw: float, pitch: float):
        self._yaw = yaw
        self._pitch = max(-35.0, min(35.0, pitch))
        self.canvas.update()

    def _toggle_spin(self, checked: bool):
        self._auto_spin = checked
        if checked:
            self._spin_timer.start()
        else:
            self._spin_timer.stop()

    def _on_spin_tick(self):
        self._yaw = (self._yaw + 1.4 + 180.0) % 360.0 - 180.0
        self.canvas.update()


class _Viewer3DCanvas(QWidget):
    def __init__(self, viewer: Interactive3DViewerDialog):
        super().__init__(viewer)
        self._viewer = viewer
        self._last_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._last_pos is not None:
            delta = event.position() - self._last_pos
            self._last_pos = event.position()
            yaw = self._viewer._yaw + delta.x() * 0.65
            while yaw > 180.0:
                yaw -= 360.0
            while yaw < -180.0:
                yaw += 360.0
            self._viewer._yaw = yaw
            self._viewer._pitch = max(-35.0, min(35.0, self._viewer._pitch - delta.y() * 0.4))
            self.update()

    def mouseReleaseEvent(self, event):
        self._last_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = float(self.width()), float(self.height())
        bg = QRadialGradient(w * 0.5, h * 0.45, max(w, h) * 0.65)
        bg.setColorAt(0.0, QColor("#1e293b"))
        bg.setColorAt(1.0, QColor("#0b1120"))
        painter.fillRect(self.rect(), bg)

        yaw = math.radians(self._viewer._yaw)
        pitch = math.radians(self._viewer._pitch)

        half_w = min(w, h) * (0.24 if self._viewer._item_type == "binder" else 0.25)
        half_h = half_w * (1.33 if self._viewer._item_type == "binder" else 1.22)
        half_d = half_w * (0.19 if self._viewer._item_type == "binder" else 0.46)

        # 8 vértices de caja 3D centrada
        pts_3d = [
            (-half_w, -half_h,  half_d),  # 0 Front TL
            ( half_w, -half_h,  half_d),  # 1 Front TR
            ( half_w,  half_h,  half_d),  # 2 Front BR
            (-half_w,  half_h,  half_d),  # 3 Front BL
            (-half_w, -half_h, -half_d),  # 4 Back TL
            ( half_w, -half_h, -half_d),  # 5 Back TR
            ( half_w,  half_h, -half_d),  # 6 Back BR
            (-half_w,  half_h, -half_d),  # 7 Back BL
        ]

        cy_a, sy_a = math.cos(yaw), math.sin(yaw)
        cp_a, sp_a = math.cos(pitch), math.sin(pitch)
        cam_dist = half_w * 6.5

        proj = []
        rot_z = []
        for x, y, z in pts_3d:
            # Rotación Y (yaw)
            rx = x * cy_a + z * sy_a
            rz = -x * sy_a + z * cy_a
            # Rotación X (pitch)
            ry = y * cp_a - rz * sp_a
            rz2 = y * sp_a + rz * cp_a
            scale = cam_dist / (cam_dist - rz2)
            proj.append(QPointF(w * 0.5 + rx * scale, h * 0.5 + ry * scale))
            rot_z.append(rz2)

        # Sombra base suave
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 95))
        painter.drawEllipse(QPointF(w * 0.5, h * 0.5 + half_h + 26), half_w * 1.15, 18.0)

        # Caras: (indices, tipo, color/pixmap)
        faces = [
            ((0, 1, 2, 3), "front", None),
            ((5, 4, 7, 6), "back", None),
            ((4, 0, 3, 7), "left", self._viewer._spine_col),
            ((1, 5, 6, 2), "right", self._viewer._edge_col),
            ((4, 5, 1, 0), "top", self._viewer._spine_col.lighter(115)),
            ((3, 2, 6, 7), "bottom", self._viewer._spine_col.darker(120)),
        ]

        def face_normal_z(idxs):
            p0, p1, p2 = proj[idxs[0]], proj[idxs[1]], proj[idxs[2]]
            return (p1.x() - p0.x()) * (p2.y() - p0.y()) - (p1.y() - p0.y()) * (p2.x() - p0.x())

        def face_depth(idxs):
            return sum(rot_z[i] for i in idxs) / 4.0

        visible_faces = [f for f in faces if face_normal_z(f[0]) > 0]
        visible_faces.sort(key=lambda f: face_depth(f[0]))

        for idxs, ftype, col in visible_faces:
            quad = QPolygonF([proj[i] for i in idxs])
            if ftype in ("front", "back"):
                pix = self._viewer._front if ftype == "front" else self._viewer._back
                if pix and not pix.isNull():
                    src_poly = QPolygonF([
                        QPointF(0, 0),
                        QPointF(pix.width(), 0),
                        QPointF(pix.width(), pix.height()),
                        QPointF(0, pix.height()),
                    ])
                    tr = QTransform()
                    if QTransform.quadToQuad(src_poly, quad, tr):
                        painter.save()
                        painter.setTransform(tr, True)
                        painter.drawPixmap(0, 0, pix)
                        painter.restore()
                        painter.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawPolygon(quad)
                        continue
            painter.setPen(QPen(QColor(15, 23, 42, 160), 1.0))
            painter.setBrush(col)
            painter.drawPolygon(quad)
            if ftype == "right" and self._viewer._item_type == "binder":
                # Líneas simulando páginas apiladas en el borde derecho
                painter.setPen(QPen(QColor(100, 116, 139, 130), 1.0))
                for t_frac in (0.25, 0.5, 0.75):
                    a = QPointF(
                        proj[idxs[0]].x() + (proj[idxs[1]].x() - proj[idxs[0]].x()) * t_frac,
                        proj[idxs[0]].y() + (proj[idxs[1]].y() - proj[idxs[0]].y()) * t_frac,
                    )
                    b = QPointF(
                        proj[idxs[3]].x() + (proj[idxs[2]].x() - proj[idxs[3]].x()) * t_frac,
                        proj[idxs[3]].y() + (proj[idxs[2]].y() - proj[idxs[3]].y()) * t_frac,
                    )
                    painter.drawLine(a, b)


class AdvancedCoverStudioDialog(QDialog):
    """
    Estudio Avanzado de Personalización para Binder o Portamazos:
    - Edición independiente de Cara Delantera y Cara Trasera
    - Stickers Pokémon vectoriales, stickers de arte Pokémon y stickers PNG personalizados
    - Figuras geométricas para componer diseños creativos y texto personalizado
    - Control de color, borde, rotación, opacidad, orden de capas y Vista 3D en tiempo real
    """

    def __init__(
        self,
        item_type: str = "binder",
        name: str = "Mi Diseño",
        design_name: str = "Charizard Fuego",
        custom_color: str = "auto",
        custom_image: str | None = None,
        advanced_design: dict | None = None,
        face_renderer=None,
        initial_face: str = "front",
        interior_color: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._item_type = item_type
        self._name = name or ("Mi Binder" if item_type == "binder" else "Mi Mazo")
        self._design_name = design_name
        self._custom_color = custom_color
        self._custom_image = custom_image
        self._face_renderer = face_renderer
        self._interior_color = interior_color or "#18181e"
        self._adv = normalize_advanced_design(advanced_design)
        self._face = "front"
        self._selected_idx = -1

        title_lbl = t("Estudio Avanzado de Binder") if item_type == "binder" else t("Estudio Avanzado de Portamazos")
        self.setWindowTitle(title_lbl)
        self.setMinimumSize(940, 620)
        self.resize(1020, 660)
        self.setStyleSheet("""
            QDialog {
                background-color: #fff6f8;
                color: #3f2730;
            }
            QLabel { color: #5a2a3a; font-weight: 600; }
            QPushButton {
                background-color: #ffffff;
                color: #5a2a3a;
                border: 1.5px solid #f2b8c3;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #ffe4eb;
                border-color: #f56b7b;
            }
            QPushButton:checked {
                background-color: #f56b7b;
                color: #ffffff;
                border-color: #e11d48;
            }
            QListWidget, QLineEdit, QSpinBox {
                background-color: #ffffff;
                color: #3f2730;
                border: 1.5px solid #f2b8c3;
                border-radius: 7px;
                padding: 4px;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        # --- Columna Izquierda: Paleta de Stickers, Figuras y Texto ---
        left_panel = QFrame()
        left_panel.setFixedWidth(250)
        left_panel.setStyleSheet("QFrame { background-color: #ffffff; border: 1.5px solid #f2c4ce; border-radius: 12px; }")
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(8)

        lbl_pal = QLabel(t("Stickers y Figuras"))
        lbl_pal.setStyleSheet("font-size: 13px; font-weight: 700; border: none;")
        left_lay.addWidget(lbl_pal)

        scroll_pal = QScrollArea()
        scroll_pal.setWidgetResizable(True)
        scroll_pal.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        pal_inner = QWidget()
        pal_vbox = QVBoxLayout(pal_inner)
        pal_vbox.setContentsMargins(0, 0, 2, 0)
        pal_vbox.setSpacing(8)

        # Stickers vectoriales
        lbl_st = QLabel(t("Stickers Pokémon"))
        lbl_st.setStyleSheet("font-size: 11px; color: #8c5464; border: none;")
        pal_vbox.addWidget(lbl_st)
        grid_st = QGridLayout()
        grid_st.setSpacing(5)
        for i, (key, label, col) in enumerate(STICKER_PRESETS):
            b = QPushButton(t(label))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda ch, k=key, c=col: self._add_element({
                "id": uuid.uuid4().hex[:8],
                "kind": "sticker",
                "key": k,
                "x": 0.5, "y": 0.45,
                "w": 0.24, "h": 0.24,
                "rotation": 0,
                "color": c,
                "border_color": "#ffffff",
                "border_width": 2,
                "opacity": 1.0,
            }))
            grid_st.addWidget(b, i // 2, i % 2)
        pal_vbox.addLayout(grid_st)

        # Stickers de ilustraciones Pokémon
        lbl_pk = QLabel(t("Ilustraciones Pokémon"))
        lbl_pk.setStyleSheet("font-size: 11px; color: #8c5464; border: none;")
        pal_vbox.addWidget(lbl_pk)
        grid_pk = QGridLayout()
        grid_pk.setSpacing(5)
        for i, (fname, label) in enumerate(POKEMON_STICKER_FILES):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda ch, fn=fname: self._add_element({
                "id": uuid.uuid4().hex[:8],
                "kind": "image",
                "image_path": fn,
                "x": 0.5, "y": 0.45,
                "w": 0.34, "h": 0.34,
                "rotation": 0,
                "color": "#ffffff",
                "border_color": "#ffffff",
                "border_width": 0,
                "opacity": 1.0,
            }))
            grid_pk.addWidget(b, i // 2, i % 2)
        pal_vbox.addLayout(grid_pk)

        btn_custom_sticker = QPushButton(t("+ Sticker Imagen Propia"))
        btn_custom_sticker.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_custom_sticker.clicked.connect(self._add_custom_image_sticker)
        pal_vbox.addWidget(btn_custom_sticker)

        # Figuras geométricas
        lbl_sh = QLabel(t("Figuras para Formas"))
        lbl_sh.setStyleSheet("font-size: 11px; color: #8c5464; border: none;")
        pal_vbox.addWidget(lbl_sh)
        grid_sh = QGridLayout()
        grid_sh.setSpacing(5)
        for i, (key, label) in enumerate(SHAPE_PRESETS):
            b = QPushButton(t(label))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda ch, k=key: self._add_element({
                "id": uuid.uuid4().hex[:8],
                "kind": "shape",
                "key": k,
                "x": 0.5, "y": 0.48,
                "w": 0.65 if k == "stripe" else (0.78 if k == "frame" else 0.26),
                "h": 0.16 if k == "stripe" else (0.82 if k == "frame" else 0.26),
                "rotation": -12 if k == "stripe" else 0,
                "color": "#f59e0b",
                "border_color": "#ffffff",
                "border_width": 2,
                "opacity": 0.9,
            }))
            grid_sh.addWidget(b, i // 2, i % 2)
        pal_vbox.addLayout(grid_sh)

        # Texto personalizado
        btn_add_text = QPushButton(t("+ Agregar Texto"))
        btn_add_text.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_text.clicked.connect(lambda: self._add_element({
            "id": uuid.uuid4().hex[:8],
            "kind": "text",
            "text": self._name,
            "x": 0.5, "y": 0.22,
            "w": 0.72, "h": 0.14,
            "rotation": 0,
            "color": "#ffffff",
            "border_color": "#0f172a",
            "border_width": 2,
            "opacity": 1.0,
        }))
        pal_vbox.addWidget(btn_add_text)
        pal_vbox.addStretch()

        scroll_pal.setWidget(pal_inner)
        left_lay.addWidget(scroll_pal, stretch=1)
        root.addWidget(left_panel)

        # --- Columna Central: Switch Frente/Atrás + Canvas + Botón Vista 3D ---
        center_col = QVBoxLayout()
        center_col.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        self.btn_face_front = QPushButton(t("Cara Delantera"))
        self.btn_face_front.setCheckable(True)
        self.btn_face_front.setChecked(True)
        self.btn_face_back = QPushButton(t("Parte Trasera"))
        self.btn_face_back.setCheckable(True)
        face_group = QButtonGroup(self)
        face_group.setExclusive(True)
        face_group.addButton(self.btn_face_front)
        face_group.addButton(self.btn_face_back)
        self.btn_face_front.clicked.connect(lambda: self._switch_face("front"))
        self.btn_face_back.clicked.connect(lambda: self._switch_face("back"))

        self.btn_face_inside = None
        if item_type == "binder":
            self.btn_face_inside = QPushButton(t("Interior Portada"))
            self.btn_face_inside.setCheckable(True)
            face_group.addButton(self.btn_face_inside)
            self.btn_face_inside.clicked.connect(lambda: self._switch_face("inside"))

        self.btn_back_color = QPushButton(t("Color Trasero"))
        self.btn_back_color.clicked.connect(self._pick_back_color)

        btn_3d = QPushButton(t("Vista 3D"))
        btn_3d.setStyleSheet(
            "background-color: #0ea5e9; color: #ffffff; border-color: #0284c7; font-weight: 700;"
        )
        btn_3d.clicked.connect(self._open_3d_preview)

        top_bar.addWidget(self.btn_face_front)
        top_bar.addWidget(self.btn_face_back)
        if self.btn_face_inside is not None:
            top_bar.addWidget(self.btn_face_inside)
        top_bar.addWidget(self.btn_back_color)
        top_bar.addStretch()
        top_bar.addWidget(btn_3d)
        center_col.addLayout(top_bar)

        # Barra de controles específicos para la cara interior de portada (Issue #59)
        self.inside_controls_bar = QWidget()
        inside_lay = QHBoxLayout(self.inside_controls_bar)
        inside_lay.setContentsMargins(0, 0, 0, 0)
        inside_lay.setSpacing(6)

        self.btn_inside_color = QPushButton(t("Color Interior"))
        self.btn_inside_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inside_color.clicked.connect(self._pick_inside_color)
        inside_lay.addWidget(self.btn_inside_color)

        self.btn_toggle_pocket = QPushButton(t("Bolsillo"))
        self.btn_toggle_pocket.setCheckable(True)
        self.btn_toggle_pocket.setChecked(self._adv.get("inside_show_pocket", True))
        self.btn_toggle_pocket.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pocket.toggled.connect(self._on_inside_pocket_toggled)
        inside_lay.addWidget(self.btn_toggle_pocket)

        self.btn_toggle_title = QPushButton(t("Emblema"))
        self.btn_toggle_title.setCheckable(True)
        self.btn_toggle_title.setChecked(self._adv.get("inside_show_title", True))
        self.btn_toggle_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_title.toggled.connect(self._on_inside_title_toggled)
        inside_lay.addWidget(self.btn_toggle_title)

        self.txt_inside_title = QLineEdit()
        self.txt_inside_title.setPlaceholderText(t("Título interior (opcional)..."))
        self.txt_inside_title.setText(self._adv.get("inside_title") or "")
        self.txt_inside_title.textChanged.connect(self._on_inside_title_text_changed)
        inside_lay.addWidget(self.txt_inside_title, stretch=1)

        self.inside_controls_bar.setVisible(False)
        center_col.addWidget(self.inside_controls_bar)

        self.canvas = _EditableCoverCanvas(self._provide_preview, self)
        self.canvas.selection_changed.connect(self._on_canvas_selection)
        self.canvas.elements_modified.connect(self._sync_inspector_from_selection)
        center_col.addWidget(self.canvas, stretch=1)

        hint = QLabel(t("Arrastra un sticker o figura para moverlo • Usa el círculo azul inferior para cambiar su tamaño"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 11px; color: #8c5464;")
        center_col.addWidget(hint)
        root.addLayout(center_col, stretch=1)

        # --- Columna Derecha: Capas, Inspector y Guardar ---
        right_panel = QFrame()
        right_panel.setFixedWidth(260)
        right_panel.setStyleSheet("QFrame { background-color: #ffffff; border: 1.5px solid #f2c4ce; border-radius: 12px; }")
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(10, 10, 10, 10)
        right_lay.setSpacing(8)

        lbl_layers = QLabel(t("Capas de esta cara"))
        lbl_layers.setStyleSheet("font-size: 13px; font-weight: 700; border: none;")
        right_lay.addWidget(lbl_layers)

        self.layer_list = QListWidget()
        self.layer_list.setFixedHeight(130)
        self.layer_list.currentRowChanged.connect(self._on_layer_row_changed)
        right_lay.addWidget(self.layer_list)

        layer_btns = QHBoxLayout()
        btn_up = QPushButton("▲")
        btn_up.setToolTip(t("Subir capa"))
        btn_up.clicked.connect(lambda: self._move_layer(1))
        btn_dn = QPushButton("▼")
        btn_dn.setToolTip(t("Bajar capa"))
        btn_dn.clicked.connect(lambda: self._move_layer(-1))
        btn_dup = QPushButton(t("Duplicar"))
        btn_dup.clicked.connect(self._duplicate_selected)
        btn_del = QPushButton(t("Eliminar"))
        btn_del.clicked.connect(self._delete_selected)
        layer_btns.addWidget(btn_up)
        layer_btns.addWidget(btn_dn)
        layer_btns.addWidget(btn_dup)
        layer_btns.addWidget(btn_del)
        right_lay.addLayout(layer_btns)

        # Propiedades del elemento seleccionado
        lbl_props = QLabel(t("Propiedades del elemento"))
        lbl_props.setStyleSheet("font-size: 12px; font-weight: 700; border: none;")
        right_lay.addWidget(lbl_props)

        self.txt_el_text = QLineEdit()
        self.txt_el_text.setPlaceholderText(t("Texto..."))
        self.txt_el_text.textChanged.connect(self._on_text_edited)
        right_lay.addWidget(self.txt_el_text)

        col_row = QHBoxLayout()
        self.btn_el_color = QPushButton(t("Color"))
        self.btn_el_color.clicked.connect(self._pick_element_color)
        self.btn_el_border = QPushButton(t("Borde"))
        self.btn_el_border.clicked.connect(self._pick_element_border)
        col_row.addWidget(self.btn_el_color)
        col_row.addWidget(self.btn_el_border)
        right_lay.addLayout(col_row)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel(t("Rotación:")))
        self.slider_rot = QSlider(Qt.Orientation.Horizontal)
        self.slider_rot.setRange(-180, 180)
        self.slider_rot.valueChanged.connect(self._on_rot_changed)
        self.lbl_rot_val = QLabel("0°")
        self.lbl_rot_val.setFixedWidth(36)
        rot_row.addWidget(self.slider_rot)
        rot_row.addWidget(self.lbl_rot_val)
        right_lay.addLayout(rot_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(t("Tamaño:")))
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(6, 95)
        self.slider_size.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.slider_size)
        right_lay.addLayout(size_row)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel(t("Opacidad:")))
        self.slider_op = QSlider(Qt.Orientation.Horizontal)
        self.slider_op.setRange(15, 100)
        self.slider_op.setValue(100)
        self.slider_op.valueChanged.connect(self._on_opacity_changed)
        op_row.addWidget(self.slider_op)
        right_lay.addLayout(op_row)

        right_lay.addStretch()

        btn_clear_face = QPushButton(t("Limpiar esta cara"))
        btn_clear_face.clicked.connect(self._clear_current_face)
        right_lay.addWidget(btn_clear_face)

        actions_row = QHBoxLayout()
        btn_cancel = QPushButton(t("Cancelar"))
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(t("Aplicar Diseño"))
        btn_ok.setStyleSheet(
            "background-color: #f56b7b; color: #ffffff; border-color: #e11d48; font-weight: 700;"
        )
        btn_ok.clicked.connect(self.accept)
        actions_row.addWidget(btn_cancel)
        actions_row.addWidget(btn_ok)
        right_lay.addLayout(actions_row)

        root.addWidget(right_panel)

        if initial_face == "inside" and self.btn_face_inside is not None:
            self.btn_face_inside.setChecked(True)
            self._face = "inside"
            self.inside_controls_bar.setVisible(True)
        elif initial_face == "back":
            self.btn_face_back.setChecked(True)
            self._face = "back"

        self._refresh_canvas_and_layers()

    def _current_list(self) -> list[dict]:
        return self._adv.setdefault(self._face, [])

    def _provide_preview(self, req: str, *args):
        if req == "is_binder":
            return self._item_type == "binder"
        if req == "base_face_pixmap":
            face, w, h = args
            if face == "inside":
                pix = QPixmap(max(16, int(w)), max(16, int(h)))
                pix.fill(Qt.GlobalColor.transparent)
                p = QPainter(pix)
                try:
                    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    render_inside_cover_surface(
                        p,
                        QRectF(0.0, 0.0, float(pix.width()), float(pix.height())),
                        self._interior_color,
                        self._name,
                        advanced_design=self._adv,
                        include_advanced=False,
                    )
                finally:
                    p.end()
                return pix
            if self._face_renderer:
                return self._face_renderer(face, w, h, self._adv.get("back_color"), include_advanced=False)
            pix = QPixmap(w, h)
            pix.fill(QColor("#1e293b"))
            return pix
        return None

    def _switch_face(self, face: str):
        self._face = face
        self._selected_idx = -1
        if hasattr(self, "inside_controls_bar"):
            self.inside_controls_bar.setVisible(face == "inside" and self._item_type == "binder")
        self._refresh_canvas_and_layers()

    def _pick_inside_color(self):
        init = QColor(self._adv.get("inside_color") or self._interior_color or "#18181e")
        c = QColorDialog.getColor(init, self, t("Color de interior de portada"))
        if c.isValid():
            self._adv["inside_color"] = c.name()
            self.canvas.update()

    def _on_inside_pocket_toggled(self, checked: bool):
        self._adv["inside_show_pocket"] = bool(checked)
        self.canvas.update()

    def _on_inside_title_toggled(self, checked: bool):
        self._adv["inside_show_title"] = bool(checked)
        self.canvas.update()

    def _on_inside_title_text_changed(self, txt: str):
        clean = txt.strip()
        self._adv["inside_title"] = clean if clean else None
        self.canvas.update()

    def _add_element(self, el: dict):
        lst = self._current_list()
        lst.append(el)
        self._selected_idx = len(lst) - 1
        self._refresh_canvas_and_layers()

    def _add_custom_image_sticker(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            t("Seleccionar imagen para Sticker"),
            "",
            "Imágenes (*.png *.webp *.jpg *.jpeg)"
        )
        if not fpath or not os.path.exists(fpath):
            return
        os.makedirs(CUSTOM_STICKERS_DIR, exist_ok=True)
        ext = os.path.splitext(fpath)[1].lower() or ".png"
        dest_name = f"sticker_{uuid.uuid4().hex[:10]}{ext}"
        dest_path = os.path.join(CUSTOM_STICKERS_DIR, dest_name)
        try:
            shutil.copy2(fpath, dest_path)
            stored = dest_name
        except Exception:
            stored = fpath
        self._add_element({
            "id": uuid.uuid4().hex[:8],
            "kind": "image",
            "image_path": stored,
            "x": 0.5, "y": 0.45,
            "w": 0.28, "h": 0.28,
            "rotation": 0,
            "color": "#ffffff",
            "border_color": "#ffffff",
            "border_width": 0,
            "opacity": 1.0,
        })

    def _pick_back_color(self):
        init = QColor(self._adv.get("back_color") or "#1e293b")
        c = QColorDialog.getColor(init, self, t("Color de la parte trasera"))
        if c.isValid():
            self._adv["back_color"] = c.name()
            if self._face != "back":
                self.btn_face_back.setChecked(True)
                self._switch_face("back")
            else:
                self.canvas.update()

    def _refresh_canvas_and_layers(self):
        lst = self._current_list()
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for i, el in enumerate(lst):
            kind = el.get("kind", "sticker")
            label = el.get("text") if kind == "text" else (
                os.path.basename(el.get("image_path", "")) if kind == "image" else el.get("key", kind)
            )
            self.layer_list.addItem(f"{i + 1}. {kind.title()}: {label}")
        if 0 <= self._selected_idx < len(lst):
            self.layer_list.setCurrentRow(self._selected_idx)
        self.layer_list.blockSignals(False)

        self.canvas.set_state(self._face, lst, self._selected_idx)
        self._sync_inspector_from_selection()

    def _on_canvas_selection(self, idx: int):
        self._selected_idx = idx
        self.layer_list.blockSignals(True)
        self.layer_list.setCurrentRow(idx if idx >= 0 else -1)
        self.layer_list.blockSignals(False)
        self._sync_inspector_from_selection()

    def _on_layer_row_changed(self, row: int):
        self._selected_idx = row
        self.canvas.set_state(self._face, self._current_list(), self._selected_idx)
        self._sync_inspector_from_selection()

    def _sync_inspector_from_selection(self):
        lst = self._current_list()
        has_sel = 0 <= self._selected_idx < len(lst)
        for w in (self.btn_el_color, self.btn_el_border, self.slider_rot, self.slider_size, self.slider_op):
            w.setEnabled(has_sel)
        if not has_sel:
            self.txt_el_text.setEnabled(False)
            return

        el = lst[self._selected_idx]
        is_text = el.get("kind") == "text"
        self.txt_el_text.setEnabled(is_text)
        self.txt_el_text.blockSignals(True)
        self.txt_el_text.setText(el.get("text", "") if is_text else "")
        self.txt_el_text.blockSignals(False)

        rot = int(el.get("rotation", 0))
        self.slider_rot.blockSignals(True)
        self.slider_rot.setValue(rot)
        self.slider_rot.blockSignals(False)
        self.lbl_rot_val.setText(f"{rot}°")

        sz = int(max(el.get("w", 0.22), el.get("h", 0.22)) * 100)
        self.slider_size.blockSignals(True)
        self.slider_size.setValue(max(6, min(95, sz)))
        self.slider_size.blockSignals(False)

        op = int(float(el.get("opacity", 1.0)) * 100)
        self.slider_op.blockSignals(True)
        self.slider_op.setValue(max(15, min(100, op)))
        self.slider_op.blockSignals(False)

    def _selected_el(self) -> dict | None:
        lst = self._current_list()
        if 0 <= self._selected_idx < len(lst):
            return lst[self._selected_idx]
        return None

    def _on_text_edited(self, txt: str):
        el = self._selected_el()
        if el and el.get("kind") == "text":
            el["text"] = txt
            self.canvas.update()
            if 0 <= self._selected_idx < self.layer_list.count():
                self.layer_list.item(self._selected_idx).setText(f"{self._selected_idx + 1}. Text: {txt}")

    def _pick_element_color(self):
        el = self._selected_el()
        if not el:
            return
        c = QColorDialog.getColor(QColor(el.get("color", "#fbbf24")), self, t("Color del elemento"))
        if c.isValid():
            el["color"] = c.name()
            self.canvas.update()

    def _pick_element_border(self):
        el = self._selected_el()
        if not el:
            return
        c = QColorDialog.getColor(QColor(el.get("border_color", "#ffffff")), self, t("Color del borde"))
        if c.isValid():
            el["border_color"] = c.name()
            self.canvas.update()

    def _on_rot_changed(self, val: int):
        el = self._selected_el()
        if el:
            el["rotation"] = val
            self.lbl_rot_val.setText(f"{val}°")
            self.canvas.update()

    def _on_size_changed(self, val: int):
        el = self._selected_el()
        if el:
            ratio = float(el.get("h", 0.22)) / max(0.01, float(el.get("w", 0.22)))
            nw = val / 100.0
            nh = max(0.06, min(0.95, nw * ratio))
            el["w"] = nw
            el["h"] = nh
            self.canvas.update()

    def _on_opacity_changed(self, val: int):
        el = self._selected_el()
        if el:
            el["opacity"] = val / 100.0
            self.canvas.update()

    def _move_layer(self, direction: int):
        lst = self._current_list()
        idx = self._selected_idx
        new_idx = idx + direction
        if 0 <= idx < len(lst) and 0 <= new_idx < len(lst):
            lst[idx], lst[new_idx] = lst[new_idx], lst[idx]
            self._selected_idx = new_idx
            self._refresh_canvas_and_layers()

    def _duplicate_selected(self):
        el = self._selected_el()
        if not el:
            return
        dup = copy.deepcopy(el)
        dup["id"] = uuid.uuid4().hex[:8]
        dup["x"] = min(0.92, float(dup.get("x", 0.5)) + 0.05)
        dup["y"] = min(0.92, float(dup.get("y", 0.5)) + 0.05)
        self._add_element(dup)

    def _delete_selected(self):
        lst = self._current_list()
        if 0 <= self._selected_idx < len(lst):
            lst.pop(self._selected_idx)
            self._selected_idx = min(self._selected_idx, len(lst) - 1)
            self._refresh_canvas_and_layers()

    def _clear_current_face(self):
        self._adv[self._face] = []
        self._selected_idx = -1
        self._refresh_canvas_and_layers()

    def _open_3d_preview(self):
        if not self._face_renderer:
            return
        front_pix = self._face_renderer("front", 360, 480, self._adv.get("back_color"), include_advanced=True, adv_override=self._adv)
        back_pix = self._face_renderer("back", 360, 480, self._adv.get("back_color"), include_advanced=True, adv_override=self._adv)
        dlg = Interactive3DViewerDialog(
            title=self._name,
            front_pixmap=front_pix,
            back_pixmap=back_pix,
            item_type=self._item_type,
            parent=self,
        )
        dlg.exec()

    def get_advanced_design(self) -> dict:
        return copy.deepcopy(self._adv)
