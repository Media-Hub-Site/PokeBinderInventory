import os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QFont, QPixmap, QFontMetrics
)

from MyQtApp.config import (
    BUNDLE_DIR, EXE_DIR, PERFIL_DIR, PROJECT_ROOT, USER_DATA_DIR,
    load_settings, scale_anim_duration
)
from MyQtApp.ui.AdvancedCoverStudio import (
    normalize_advanced_design, render_advanced_elements, render_back_cover_surface
)

BINDER_COVERS_DIR = os.path.join(USER_DATA_DIR, "binder_covers")


# Temas físicos de Binder estilo Ultra PRO Pokémon Portfolio (sin emojis)
BINDER_DESIGNS = {
    "Charizard Fuego": {
        "base": "#1e1b26",
        "accent": "#dc2626",
        "accent2": "#f97316",
        "strap": "#b91c1c",
        "spine": "#110f17",
        "text": "#ffffff",
        "interior": "#1c1922",
        "artwork": "charizard.webp",
        "kind": "artwork",
    },
    "Blastoise Océano": {
        "base": "#0f2942",
        "accent": "#0284c7",
        "accent2": "#38bdf8",
        "strap": "#0369a1",
        "spine": "#08192b",
        "text": "#ffffff",
        "interior": "#0e1e30",
        "artwork": "blastoise.webp",
        "kind": "artwork",
    },
    "Pikachu Eléctrico": {
        "base": "#2b2518",
        "accent": "#eab308",
        "accent2": "#facc15",
        "strap": "#ca8a04",
        "spine": "#1a160d",
        "text": "#ffffff",
        "interior": "#221e14",
        "artwork": "pikachu.webp",
        "kind": "artwork",
    },
    "Umbreon Nocturno": {
        "base": "#18181b",
        "accent": "#eab308",
        "accent2": "#38bdf8",
        "strap": "#27272a",
        "spine": "#09090b",
        "text": "#f8fafc",
        "interior": "#141418",
        "artwork": "umbreon.webp",
        "kind": "artwork",
    },
    "Sylveon Pastel": {
        "base": "#f48fb1",
        "accent": "#f8bbd0",
        "accent2": "#90caf9",
        "strap": "#ec407a",
        "spine": "#c2185b",
        "text": "#ffffff",
        "interior": "#36202a",
        "artwork": "sylveon.webp",
        "kind": "artwork",
    },
    "Snorlax Clásico": {
        "base": "#164e63",
        "accent": "#0e7490",
        "accent2": "#fef3c7",
        "strap": "#083344",
        "spine": "#0b2c38",
        "text": "#ffffff",
        "interior": "#122933",
        "artwork": "snorlax.webp",
        "kind": "artwork",
    },
    "Pokéball Clásico": {
        "base": "#dc2626",
        "accent": "#ffffff",
        "accent2": "#18181b",
        "strap": "#18181b",
        "spine": "#991b1b",
        "text": "#ffffff",
        "interior": "#1e1719",
        "artwork": None,
        "kind": "pokeball",
    },
    "Master Ball Élite": {
        "base": "#581c87",
        "accent": "#d946ef",
        "accent2": "#f3e8ff",
        "strap": "#3b0764",
        "spine": "#2e1065",
        "text": "#ffffff",
        "interior": "#1f122d",
        "artwork": None,
        "kind": "masterball",
    },
    "Ultra PRO Minimalista": {
        "base": "#27272a",
        "accent": "#a1a1aa",
        "accent2": "#e4e4e7",
        "strap": "#18181b",
        "spine": "#18181b",
        "text": "#ffffff",
        "interior": "#18181e",
        "artwork": None,
        "kind": "minimal",
    },
}

# Mapeo de nombres heredados de versiones anteriores para retrocompatibilidad
LEGACY_DESIGN_MAP = {
    "Clásico": "Sylveon Pastel",
    "Clásico Rosa": "Sylveon Pastel",
    "Ultra Pro Negro": "Ultra PRO Minimalista",
    "Pokéball Rojo": "Pokéball Clásico",
    "Master Ball Púrpura": "Master Ball Élite",
    "Pikachu Amarillo": "Pikachu Eléctrico",
}

_artwork_cache = {}


def _load_theme_artwork(filename: str) -> QPixmap | None:
    if not filename:
        return None
    if filename in _artwork_cache:
        return _artwork_cache[filename]

    candidates = [
        os.path.join(PERFIL_DIR, filename),
        os.path.join(BUNDLE_DIR, "assets", "perfil", filename),
        os.path.join(EXE_DIR, "assets", "perfil", filename),
        os.path.join(PROJECT_ROOT, "assets", "perfil", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                _artwork_cache[filename] = pix
                return pix
    _artwork_cache[filename] = None
    return None


def resolve_design_key(design_name: str) -> str:
    if design_name in BINDER_DESIGNS:
        return design_name
    return LEGACY_DESIGN_MAP.get(design_name, "Charizard Fuego")


def get_design_default_interior_color(design_name: str) -> str:
    cfg = BINDER_DESIGNS.get(resolve_design_key(design_name), BINDER_DESIGNS["Charizard Fuego"])
    return cfg.get("interior", "#18181e")


def resolve_custom_cover_pixmap(image_path: str | None) -> QPixmap | None:
    """Carga una imagen personalizada de portada (ruta absoluta o relativa en binder_covers)."""
    if not image_path:
        return None
    candidates = [image_path]
    if not os.path.isabs(image_path):
        candidates.append(os.path.join(BINDER_COVERS_DIR, image_path))
        candidates.append(os.path.join(USER_DATA_DIR, image_path))
    for path in candidates:
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                return pix
    return None


class BinderCoverWidget(QWidget):
    """
    Renderiza una portada física realista de Binder/Portfolio estilo Ultra PRO Pokémon TCG:
    - Hojas apiladas visibles en el borde derecho (profundidad 3D)
    - Lomo izquierdo con costura y pliegue de apertura
    - Ilustración Pokémon, imagen personalizada (con soporte PNG transparente) o emblema vectorial
    - Banda elástica vertical de cierre en el costado derecho
    - Placa inferior con nombre del binder y formato de bolsillos (3x3, 2x2, etc.)
    """

    def __init__(
        self,
        name: str = "Mi Binder",
        design: str = "Charizard Fuego",
        color: str = None,
        mode: str = "3x3",
        custom_image: str = None,
        locked: bool = False,
        advanced_design: dict = None,
        binder_type: str = "normal",
        parent=None,
    ):
        super().__init__(parent)
        self._name = name or "Mi Binder"
        self._design = resolve_design_key(design)
        self._custom_color = color
        self._mode = mode or "3x3"
        self._custom_image = custom_image or None
        self._custom_pixmap = resolve_custom_cover_pixmap(self._custom_image)
        self._locked = bool(locked)
        self._advanced_design = normalize_advanced_design(advanced_design)
        self._binder_type = "toploader" if binder_type == "toploader" else "normal"
        self._hovered = False
        self._hover_progress = 0.0
        self._hover_anim = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(150, 195)

    def set_binder_props(
        self,
        name: str = None,
        design: str = None,
        color: str = None,
        mode: str = None,
        custom_image="UNSET",
        locked: bool = None,
        advanced_design="UNSET",
        binder_type: str = None,
    ):
        if name is not None:
            self._name = name or "Mi Binder"
        if design is not None:
            self._design = resolve_design_key(design)
        if color is not None:
            self._custom_color = color
        if mode is not None:
            self._mode = mode
        if custom_image != "UNSET":
            self._custom_image = custom_image or None
            self._custom_pixmap = resolve_custom_cover_pixmap(self._custom_image)
        if locked is not None:
            self._locked = bool(locked)
        if advanced_design != "UNSET":
            self._advanced_design = normalize_advanced_design(advanced_design)
        if binder_type is not None:
            self._binder_type = "toploader" if binder_type == "toploader" else "normal"
        self.update()

    def set_hovered(self, hovered: bool):
        if self._hovered == hovered:
            return
        self._hovered = hovered
        target = 1.0 if hovered else 0.0
        if not load_settings().get("animaciones", True):
            self._hover_progress = target
            self.update()
            return

        if self._hover_anim and self._hover_anim.state() == QVariantAnimation.State.Running:
            self._hover_anim.stop()
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(scale_anim_duration(180, min_ms=70))
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_tick)
        self._hover_anim.start()

    def _on_hover_tick(self, val):
        self._hover_progress = float(val)
        self.update()

    def _effective_colors(self):
        cfg = BINDER_DESIGNS.get(self._design, BINDER_DESIGNS["Charizard Fuego"])
        base = QColor(cfg["base"])
        spine = QColor(cfg["spine"])
        strap = QColor(cfg["strap"])
        accent = QColor(cfg["accent"])
        accent2 = QColor(cfg["accent2"])

        # Si el usuario eligió un color personalizado (distinto del default pastel antiguo #ffeef2)
        if self._custom_color and self._custom_color.lower() not in ("", "#ffeef2", "auto"):
            c = QColor(self._custom_color)
            if c.isValid():
                base = c
                spine = c.darker(145)
                strap = c.darker(165)

        return cfg, base, spine, strap, accent, accent2

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        hp = self._hover_progress
        is_toploader = getattr(self, "_binder_type", "normal") == "toploader"
        margin_x = 10.0
        margin_y = 9.0
        pages_thickness = (10.0 if is_toploader else 7.0) + 2.8 * hp

        cover_x = margin_x - 2.2 * hp
        cover_y = margin_y - 5.5 * hp
        cover_w = w - margin_x * 2 - (9.0 if is_toploader else 7.0)
        cover_h = h - margin_y * 2 - 4.0

        cfg, base, spine, strap, accent, accent2 = self._effective_colors()

        # 1. Sombra proyectada dinámica (se profundiza al sobresalir de la estantería)
        shadow_rect = QRectF(
            cover_x + 4.0 + 2.5 * hp,
            cover_y + 6.0 + 5.5 * hp,
            cover_w + pages_thickness,
            cover_h,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 15, 25, int(38 + 42 * hp)))
        painter.drawRoundedRect(shadow_rect, 11, 11)

        # 2. Tapa trasera + bloque de hojas blancas apiladas en el borde derecho
        back_cover_rect = QRectF(cover_x + pages_thickness, cover_y + 3, cover_w, cover_h - 2)
        painter.setBrush(spine)
        painter.drawRoundedRect(back_cover_rect, 10, 10)

        pages_rect = QRectF(cover_x + cover_w - 6, cover_y + 5, pages_thickness + 4, cover_h - 8)
        page_grad = QLinearGradient(pages_rect.left(), 0, pages_rect.right(), 0)
        if is_toploader:
            page_grad.setColorAt(0.0, QColor("#bae6fd"))
            page_grad.setColorAt(0.5, QColor("#f0f9ff"))
            page_grad.setColorAt(1.0, QColor("#dbeafe"))
        else:
            page_grad.setColorAt(0.0, QColor("#e2e8f0"))
            page_grad.setColorAt(0.5, QColor("#ffffff"))
            page_grad.setColorAt(1.0, QColor("#cbd5e1"))
        painter.setBrush(page_grad)
        painter.drawRoundedRect(pages_rect, 4, 4)

        # Líneas finas de hojas internas (más espaciadas si son toploaders gruesos)
        painter.setPen(QPen(QColor(56, 189, 248, 160) if is_toploader else QColor(148, 163, 184, 130), 0.9 if is_toploader else 0.7))
        for offset in ((2.0, 5.0, 8.0) if is_toploader else (2.0, 4.0, 6.0)):
            lx = cover_x + cover_w + offset - 1.5
            painter.drawLine(QPointF(lx, cover_y + 8), QPointF(lx, cover_y + cover_h - 6))

        # 3. Portada principal con gradiente tipo cuero/textura Ultra PRO
        cover_rect = QRectF(cover_x, cover_y, cover_w, cover_h)
        cover_path = QPainterPath()
        cover_path.addRoundedRect(cover_rect, 10, 10)

        cover_grad = QLinearGradient(cover_x, cover_y, cover_x + cover_w, cover_y + cover_h)
        cover_grad.setColorAt(0.0, base.lighter(118))
        cover_grad.setColorAt(0.55, base)
        cover_grad.setColorAt(1.0, base.darker(122))

        painter.save()
        painter.setClipPath(cover_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cover_grad)
        painter.drawRect(cover_rect)

        # Franja diagonal decorativa estilo portfolio oficial
        diag_path = QPainterPath()
        diag_path.moveTo(cover_x + cover_w * 0.15, cover_y)
        diag_path.lineTo(cover_x + cover_w, cover_y)
        diag_path.lineTo(cover_x + cover_w, cover_y + cover_h * 0.58)
        diag_path.lineTo(cover_x + cover_w * 0.15, cover_y + cover_h * 0.25)
        diag_path.closeSubpath()
        accent_grad = QLinearGradient(cover_x, cover_y, cover_x + cover_w, cover_y + cover_h * 0.5)
        c_acc1 = QColor(accent)
        c_acc1.setAlpha(75)
        c_acc2 = QColor(accent2)
        c_acc2.setAlpha(28)
        accent_grad.setColorAt(0.0, c_acc1)
        accent_grad.setColorAt(1.0, c_acc2)
        painter.setBrush(accent_grad)
        painter.drawPath(diag_path)

        # 4. Arte central del diseño (Ilustración Pokémon o Emblema Vectorial)
        spine_w = max(14.0, cover_w * 0.105)
        strap_w = max(12.0, cover_w * 0.09)
        strap_x = cover_x + cover_w - strap_w - 11.0
        art_area_x = cover_x + spine_w + 8.0
        art_area_w = (strap_x - 6.0) - art_area_x
        art_area_y = cover_y + 12.0
        art_area_h = cover_h * 0.62
        art_center = QPointF(art_area_x + art_area_w / 2.0, art_area_y + art_area_h / 2.0)

        kind = cfg.get("kind", "artwork")
        minimal_rect = QRectF(art_area_x + 4, art_area_y + 6, art_area_w - 8, art_area_h - 8)
        has_custom_pixmap = bool(self._custom_pixmap and not self._custom_pixmap.isNull())
        if has_custom_pixmap:
            # Imagen personalizada dibujada encima del color base completo (respeta transparencias PNG)
            target_rect = QRectF(art_area_x - 2.0, art_area_y - 2.0, art_area_w + 4.0, art_area_h + 6.0)
            scaled = self._custom_pixmap.scaled(
                int(max(16, target_rect.width())),
                int(max(16, target_rect.height())),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = target_rect.center().x() - scaled.width() / 2.0
            py = target_rect.center().y() - scaled.height() / 2.0
            painter.drawPixmap(QPointF(px, py), scaled)
        elif kind == "pokeball":
            self._draw_pokeball_cover(painter, cover_x + spine_w, cover_y, cover_w - spine_w, cover_h, art_center, min(art_area_w, art_area_h) * 0.44)
        elif kind == "masterball":
            self._draw_masterball_cover(painter, art_center, min(art_area_w, art_area_h) * 0.44)
        elif kind == "minimal":
            self._draw_minimal_cover(painter, minimal_rect, accent2)
        else:
            self._draw_artwork_cover(painter, cfg.get("artwork"), QRectF(art_area_x, art_area_y, art_area_w, art_area_h), art_center, accent, accent2)

        # 5. Lomo izquierdo encuadernado con costura
        spine_rect = QRectF(cover_x, cover_y, spine_w, cover_h)
        spine_grad = QLinearGradient(cover_x, 0, cover_x + spine_w, 0)
        spine_grad.setColorAt(0.0, spine.darker(120))
        spine_grad.setColorAt(0.75, spine)
        spine_grad.setColorAt(1.0, spine.darker(140))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(spine_grad)
        painter.drawRect(spine_rect)

        # Línea de hendidura del lomo y puntadas sutiles
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
        painter.drawLine(QPointF(cover_x + spine_w + 1.0, cover_y), QPointF(cover_x + spine_w + 1.0, cover_y + cover_h))
        stitch_pen = QPen(QColor(255, 255, 255, 85), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(stitch_pen)
        painter.drawLine(QPointF(cover_x + spine_w - 3.0, cover_y + 8), QPointF(cover_x + spine_w - 3.0, cover_y + cover_h - 8))

        # 6. Banda elástica vertical de cierre (sello clásico de Ultra PRO)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRect(QRectF(strap_x - 3.0, cover_y, 3.0, cover_h))

        strap_grad = QLinearGradient(strap_x, 0, strap_x + strap_w, 0)
        strap_grad.setColorAt(0.0, strap.darker(120))
        strap_grad.setColorAt(0.5, strap.lighter(115))
        strap_grad.setColorAt(1.0, strap.darker(130))
        painter.setBrush(strap_grad)
        painter.drawRect(QRectF(strap_x, cover_y, strap_w, cover_h))

        # Sutil textura de costura del elástico
        painter.setPen(QPen(QColor(255, 255, 255, 35), 0.8))
        painter.drawLine(QPointF(strap_x + 2.0, cover_y), QPointF(strap_x + 2.0, cover_y + cover_h))
        painter.drawLine(QPointF(strap_x + strap_w - 2.0, cover_y), QPointF(strap_x + strap_w - 2.0, cover_y + cover_h))

        # 7. Stickers y figuras de edición avanzada (debajo de textos y placa del binder - Issue #62)
        front_elements = self._advanced_design.get("front") or []
        non_text_elements = [e for e in front_elements if isinstance(e, dict) and e.get("kind") != "text"]
        text_elements = [e for e in front_elements if isinstance(e, dict) and e.get("kind") == "text"]
        if non_text_elements:
            render_advanced_elements(painter, cover_rect, non_text_elements)

        # 7b. Texto central del diseño minimalista (siempre encima de stickers y figuras)
        if not has_custom_pixmap and kind == "minimal":
            self._draw_minimal_cover_text(painter, minimal_rect)

        # 7c. Placa inferior limpia con nombre del Binder y formato (3x3, 2x2...)
        plate_h = 44.0
        plate_y = cover_y + cover_h - plate_h - 8.0
        plate_rect = QRectF(cover_x + spine_w + 6.0, plate_y, strap_x - (cover_x + spine_w + 12.0), plate_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 165))
        painter.drawRoundedRect(plate_rect, 7, 7)

        # Nombre del binder
        name_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        elided_name = fm.elidedText(self._name, Qt.TextElideMode.ElideRight, int(plate_rect.width() - 12))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRectF(plate_rect.left() + 6, plate_rect.top() + 4, plate_rect.width() - 12, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_name,
        )

        # Subtítulo con formato de bolsillos y tipo (Pro-Binder vs TopLoader)
        sub_font = QFont("Segoe UI", 7, QFont.Weight.DemiBold)
        painter.setFont(sub_font)
        painter.setPen(QColor("#7dd3fc") if is_toploader else QColor("#e2e8f0"))
        kind_tag = "TOPLOADER" if is_toploader else "PRO-BINDER"
        painter.drawText(
            QRectF(plate_rect.left() + 6, plate_rect.top() + 22, plate_rect.width() - 12, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{kind_tag}  |  {self._mode}",
        )

        # 7d. Costura/cremallera e insignia superior 'TOPLOADER' si corresponde (Issue #79)
        if is_toploader:
            zip_pen = QPen(QColor(186, 230, 253, 135), 1.4, Qt.PenStyle.DashLine)
            zip_pen.setDashPattern([2.5, 2.5])
            painter.setPen(zip_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            zip_margin = 3.5
            painter.drawLine(QPointF(cover_x + spine_w + 2, cover_y + zip_margin), QPointF(cover_x + cover_w - zip_margin, cover_y + zip_margin))
            painter.drawLine(QPointF(cover_x + cover_w - zip_margin, cover_y + zip_margin), QPointF(cover_x + cover_w - zip_margin, cover_y + cover_h - zip_margin))
            painter.drawLine(QPointF(cover_x + spine_w + 2, cover_y + cover_h - zip_margin), QPointF(cover_x + cover_w - zip_margin, cover_y + cover_h - zip_margin))

            badge_w = min(74.0, max(54.0, cover_w * 0.42))
            badge_rect = QRectF(cover_x + spine_w + 6.0, cover_y + 8.0, badge_w, 16.0)
            painter.setPen(QPen(QColor("#7dd3fc"), 1.0))
            painter.setBrush(QColor(12, 74, 110, 215))
            painter.drawRoundedRect(badge_rect, 4, 4)
            tl_font = QFont("Segoe UI", 6, QFont.Weight.Bold)
            painter.setFont(tl_font)
            painter.setPen(QColor("#e0f2fe"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "TOPLOADER")

        # 7e. Textos libres del usuario e indicador de bloqueo en la capa superior final
        if text_elements:
            render_advanced_elements(painter, cover_rect, text_elements)

        if self._locked:
            badge_s = 22.0
            bx = strap_x - badge_s - 6.0
            by = cover_y + 8.0
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
            painter.setBrush(QColor(15, 23, 42, 200))
            painter.drawRoundedRect(QRectF(bx, by, badge_s, badge_s), 6, 6)
            # Arco del candado
            painter.setPen(QPen(QColor("#fbbf24"), 1.7))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(bx + 6.5, by + 4.0, 9.0, 9.0), 0, 180 * 16)
            # Cuerpo del candado
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#fbbf24"))
            painter.drawRoundedRect(QRectF(bx + 5.0, by + 9.5, 12.0, 8.5), 2, 2)

        painter.restore()

        # 8. Borde exterior refinado
        border_col = QColor("#f56b7b") if self._hovered else QColor(255, 255, 255, 70)
        painter.setPen(QPen(border_col, 2.0 if self._hovered else 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(cover_rect, 10, 10)

    def _draw_artwork_cover(self, painter: QPainter, artwork_file: str, art_rect: QRectF, center: QPointF, accent: QColor, accent2: QColor):
        # Aura radial sutil detrás de la ilustración Pokémon
        radius = min(art_rect.width(), art_rect.height()) * 0.54
        glow = QRadialGradient(center, radius)
        g1 = QColor(accent2)
        g1.setAlpha(155)
        g2 = QColor(accent)
        g2.setAlpha(45)
        glow.setColorAt(0.0, g1)
        glow.setColorAt(0.65, g2)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius, radius)

        # Anillo geométrico metálico sutil
        ring_r = radius * 0.84
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.4))
        painter.setBrush(QColor(15, 23, 42, 65))
        painter.drawEllipse(center, ring_r, ring_r)

        pix = _load_theme_artwork(artwork_file)
        if pix and not pix.isNull():
            clip = QPainterPath()
            inner_r = ring_r - 2.0
            clip.addEllipse(center, inner_r, inner_r)
            painter.save()
            painter.setClipPath(clip)
            size_px = int(inner_r * 2)
            scaled = pix.scaled(size_px, size_px, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            dx = center.x() - scaled.width() / 2.0
            dy = center.y() - scaled.height() / 2.0
            painter.drawPixmap(int(dx), int(dy), scaled)
            painter.restore()

    def _draw_pokeball_cover(self, painter: QPainter, x: float, y: float, w: float, h: float, center: QPointF, r: float):
        # Mitad inferior blanca sutil de la portada
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(248, 250, 252, 235))
        painter.drawRect(QRectF(x, center.y(), w, h - (center.y() - y)))
        # Banda negra horizontal
        painter.setBrush(QColor("#18181b"))
        painter.drawRect(QRectF(x, center.y() - 5.0, w, 10.0))
        # Botón central 3D
        painter.setBrush(QColor("#18181b"))
        painter.drawEllipse(center, r * 0.48, r * 0.48)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(center, r * 0.34, r * 0.34)
        painter.setPen(QPen(QColor("#94a3b8"), 1.5))
        painter.drawEllipse(center, r * 0.18, r * 0.18)

    def _draw_masterball_cover(self, painter: QPainter, center: QPointF, r: float):
        # Esfera Master Ball estilizada
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(center, r, r)
        painter.setClipPath(clip)

        # Superior púrpura + inferior blanca
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#7e22ce"))
        painter.drawRect(QRectF(center.x() - r, center.y() - r, r * 2, r))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRect(QRectF(center.x() - r, center.y(), r * 2, r))

        # Óvalos fucsia característicos de Master Ball
        painter.setBrush(QColor("#ec4899"))
        painter.drawEllipse(QPointF(center.x() - r * 0.62, center.y() - r * 0.45), r * 0.34, r * 0.24)
        painter.drawEllipse(QPointF(center.x() + r * 0.62, center.y() - r * 0.45), r * 0.34, r * 0.24)

        # Banda central oscura
        painter.setBrush(QColor("#1e1b4b"))
        painter.drawRect(QRectF(center.x() - r, center.y() - 4.0, r * 2, 8.0))
        painter.restore()

        # Botón central y letra M
        painter.setPen(QPen(QColor("#1e1b4b"), 2.0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(center, r * 0.28, r * 0.28)

        painter.setPen(QColor("#ffffff"))
        m_font = QFont("Segoe UI", max(10, int(r * 0.36)), QFont.Weight.Black)
        painter.setFont(m_font)
        painter.drawText(
            QRectF(center.x() - r * 0.5, center.y() - r * 0.92, r, r * 0.6),
            Qt.AlignmentFlag.AlignCenter,
            "M",
        )

    def _draw_minimal_cover(self, painter: QPainter, rect: QRectF, accent_color: QColor):
        pen_outer = QPen(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 130), 1.5)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 8, 8)
        inner = rect.adjusted(6, 6, -6, -6)
        pen_inner = QPen(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 75), 1.0)
        painter.setPen(pen_inner)
        painter.drawRoundedRect(inner, 6, 6)

    def _draw_minimal_cover_text(self, painter: QPainter, rect: QRectF):
        inner = rect.adjusted(6, 6, -6, -6)
        painter.setPen(QColor(255, 255, 255, 160))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, "POKEBINDER\nCOLLECTION")

    def render_face_pixmap(
        self,
        face: str = "front",
        width: int = 360,
        height: int = 480,
        back_color: str = None,
        include_advanced: bool = True,
        adv_override: dict = None,
    ) -> QPixmap:
        """Renderiza la cara delantera o trasera plana (para el Estudio Avanzado y Visor 3D)."""
        pix = QPixmap(max(40, width), max(40, height))
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        adv = normalize_advanced_design(adv_override) if adv_override is not None else self._advanced_design
        cfg, base, spine, strap, accent, accent2 = self._effective_colors()
        rect = QRectF(0.0, 0.0, float(pix.width()), float(pix.height()))

        if face == "back":
            b_col = QColor(back_color or adv.get("back_color") or "")
            if not b_col.isValid():
                b_col = base
            elements = adv.get("back") if include_advanced else []
            render_back_cover_surface(
                painter, rect, b_col, spine, strap,
                item_type="binder", elements=elements, name=self._name,
            )
            painter.end()
            return pix

        # Cara delantera limpia ocupando todo el rectángulo (sin desplazamiento de estantería)
        cover_path = QPainterPath()
        cover_path.addRoundedRect(rect, 12, 12)
        cover_grad = QLinearGradient(0, 0, rect.width(), rect.height())
        cover_grad.setColorAt(0.0, base.lighter(118))
        cover_grad.setColorAt(0.55, base)
        cover_grad.setColorAt(1.0, base.darker(122))

        painter.save()
        painter.setClipPath(cover_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cover_grad)
        painter.drawRect(rect)

        diag_path = QPainterPath()
        diag_path.moveTo(rect.width() * 0.15, 0)
        diag_path.lineTo(rect.width(), 0)
        diag_path.lineTo(rect.width(), rect.height() * 0.58)
        diag_path.lineTo(rect.width() * 0.15, rect.height() * 0.25)
        diag_path.closeSubpath()
        c_acc1 = QColor(accent); c_acc1.setAlpha(75)
        c_acc2 = QColor(accent2); c_acc2.setAlpha(28)
        ag = QLinearGradient(0, 0, rect.width(), rect.height() * 0.5)
        ag.setColorAt(0.0, c_acc1); ag.setColorAt(1.0, c_acc2)
        painter.setBrush(ag)
        painter.drawPath(diag_path)

        spine_w = max(16.0, rect.width() * 0.105)
        strap_w = max(14.0, rect.width() * 0.09)
        strap_x = rect.width() - strap_w - 14.0
        art_x = spine_w + 10.0
        art_w = (strap_x - 8.0) - art_x
        art_y = 16.0
        art_h = rect.height() * 0.62
        art_center = QPointF(art_x + art_w / 2.0, art_y + art_h / 2.0)

        kind = cfg.get("kind", "artwork")
        minimal_rect = QRectF(art_x + 4, art_y + 6, art_w - 8, art_h - 8)
        has_custom_pixmap = bool(self._custom_pixmap and not self._custom_pixmap.isNull())
        if has_custom_pixmap:
            tr = QRectF(art_x, art_y, art_w, art_h)
            sc = self._custom_pixmap.scaled(
                int(max(16, tr.width())), int(max(16, tr.height())),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(QPointF(tr.center().x() - sc.width() / 2.0, tr.center().y() - sc.height() / 2.0), sc)
        elif kind == "pokeball":
            self._draw_pokeball_cover(painter, spine_w, 0, rect.width() - spine_w, rect.height(), art_center, min(art_w, art_h) * 0.44)
        elif kind == "masterball":
            self._draw_masterball_cover(painter, art_center, min(art_w, art_h) * 0.44)
        elif kind == "minimal":
            self._draw_minimal_cover(painter, minimal_rect, accent2)
        else:
            self._draw_artwork_cover(painter, cfg.get("artwork"), QRectF(art_x, art_y, art_w, art_h), art_center, accent, accent2)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(spine)
        painter.drawRect(QRectF(0, 0, spine_w, rect.height()))
        painter.setBrush(strap)
        painter.drawRect(QRectF(strap_x, 0, strap_w, rect.height()))

        front_elements = (adv.get("front") or []) if include_advanced else []
        non_text_elements = [e for e in front_elements if isinstance(e, dict) and e.get("kind") != "text"]
        text_elements = [e for e in front_elements if isinstance(e, dict) and e.get("kind") == "text"]
        if non_text_elements:
            render_advanced_elements(painter, rect, non_text_elements)

        if not has_custom_pixmap and kind == "minimal":
            self._draw_minimal_cover_text(painter, minimal_rect)

        plate_h = 54.0
        plate_rect = QRectF(spine_w + 8.0, rect.height() - plate_h - 12.0, strap_x - (spine_w + 16.0), plate_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 165))
        painter.drawRoundedRect(plate_rect, 8, 8)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.drawText(plate_rect.adjusted(10, 6, -10, -22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._name)
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(plate_rect.adjusted(10, 26, -10, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"PRO-BINDER  |  {self._mode}")

        if text_elements:
            render_advanced_elements(painter, rect, text_elements)

        if self._locked:
            badge_s = 22.0
            bx = strap_x - badge_s - 6.0
            by = 8.0
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
            painter.setBrush(QColor(15, 23, 42, 200))
            painter.drawRoundedRect(QRectF(bx, by, badge_s, badge_s), 6, 6)
            painter.setPen(QPen(QColor("#fbbf24"), 1.7))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(bx + 6.5, by + 4.0, 9.0, 9.0), 0, 180 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#fbbf24"))
            painter.drawRoundedRect(QRectF(bx + 5.0, by + 9.5, 12.0, 8.5), 2, 2)

        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 85), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()
        return pix
