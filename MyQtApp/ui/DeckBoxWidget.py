import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QFont, QPixmap, QPolygonF, QFontMetrics
)

from MyQtApp.config import load_settings, scale_anim_duration
from MyQtApp.ui.BinderCoverWidget import BINDER_DESIGNS, resolve_design_key, _load_theme_artwork as _load_artwork
from MyQtApp.ui.BinderBookAnimations import play_page_turn_sound


class DeckBoxWidget(QWidget):
    """
    Portamazos físico 3D realista estilo Ultra PRO Alcove Flip Deck Box para Pokémon TCG:
    - Cuerpo rígido de cuero sintético con profundidad lateral 3D
    - Tapa superior magnética abatible (flap en V) con costuras y broche
    - Ilustración Pokémon o emblema vectorial personalizable (mismos temas que Binder)
    - Color personalizado opcional
    - Placa inferior con nombre del mazo y contador de cartas (X / 60)
    - Animación suave Bookshelf Peek al pasar el mouse
    """

    def __init__(
        self,
        name: str = "Mi Mazo",
        design: str = "Charizard Fuego",
        color: str = "auto",
        card_count: int = 0,
        locked: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._name = name or "Mi Mazo"
        self._design = resolve_design_key(design)
        self._custom_color = color
        self._card_count = int(card_count)
        self._locked = bool(locked)
        self._hovered = False
        self._hover_progress = 0.0
        self._hover_anim = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(145, 185)

    def set_deck_props(self, name=None, design=None, color=None, card_count=None, locked=None):
        if name is not None:
            self._name = name or "Mi Mazo"
        if design is not None:
            self._design = resolve_design_key(design)
        if color is not None:
            self._custom_color = color
        if card_count is not None:
            self._card_count = int(card_count)
        if locked is not None:
            self._locked = bool(locked)
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
        accent = QColor(cfg["accent"])
        accent2 = QColor(cfg["accent2"])
        if self._custom_color and str(self._custom_color).lower() not in ("", "auto", "#ffeef2"):
            c = QColor(self._custom_color)
            if c.isValid():
                base = c
                spine = c.darker(150)
        return cfg, base, spine, accent, accent2

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.draw_deck_box(painter, QRectF(self.rect()), lid_open=0.0, cards_rise=0.0, hover_p=self._hover_progress)

    def draw_deck_box(
        self,
        painter: QPainter,
        bounds: QRectF,
        lid_open: float = 0.0,
        cards_rise: float = 0.0,
        hover_p: float = 0.0,
    ):
        """Dibuja el portamazos completo (soporta tapa abierta y cartas saliendo para animación 3D)."""
        cfg, base, spine, accent, accent2 = self._effective_colors()

        w = bounds.width()
        h = bounds.height()
        depth_x = 14.0 + 3.0 * hover_p
        depth_y = 8.0

        box_w = w - 24.0 - depth_x
        box_h = h - 24.0 - depth_y
        bx = bounds.left() + 10.0 - 1.8 * hover_p
        by = bounds.top() + 14.0 + depth_y - 5.5 * hover_p

        # 1. Sombra flotante debajo del portamazos
        shadow_poly = QPolygonF([
            QPointF(bx + 6, by + box_h + 4 + 5 * hover_p),
            QPointF(bx + box_w + depth_x + 4, by + box_h - depth_y + 6 + 5 * hover_p),
            QPointF(bx + box_w + depth_x + 2, by + box_h + 6 + 5 * hover_p),
            QPointF(bx + 4, by + box_h + 10 + 5 * hover_p),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 12, 20, int(48 + 42 * hover_p)))
        painter.drawPolygon(shadow_poly)

        # 2. Parte superior / cavidad interior (visible cuando la tapa empieza a abrirse)
        top_poly = QPolygonF([
            QPointF(bx + 4, by),
            QPointF(bx + depth_x + 4, by - depth_y),
            QPointF(bx + box_w + depth_x - 2, by - depth_y),
            QPointF(bx + box_w - 2, by),
        ])
        if lid_open > 0.02:
            # Interior oscuro aterciopelado del portamazos
            painter.setBrush(QColor("#14131a"))
            painter.setPen(QPen(spine.darker(140), 1.0))
            painter.drawPolygon(top_poly)

            # Mazo de cartas saliendo suavemente hacia arriba desde el interior
            if cards_rise > 0.01:
                stack_w = box_w * 0.78
                stack_h = box_h * 0.62
                sx = bx + (box_w - stack_w) * 0.5 + depth_x * 0.25
                sy = by - depth_y * 0.4 - stack_h * cards_rise * 0.85

                # 4 cartas escalonadas formando un bloque físico
                for layer in range(4):
                    off = (3 - layer) * 2.5
                    c_rect = QRectF(sx + off, sy - off * 0.6, stack_w, stack_h)
                    cg = QLinearGradient(c_rect.left(), c_rect.top(), c_rect.right(), c_rect.bottom())
                    if layer == 3:
                        cg.setColorAt(0.0, accent.lighter(115))
                        cg.setColorAt(0.5, base.lighter(110))
                        cg.setColorAt(1.0, spine)
                    else:
                        cg.setColorAt(0.0, QColor("#e2e8f0"))
                        cg.setColorAt(1.0, QColor("#94a3b8"))
                    painter.setBrush(cg)
                    painter.setPen(QPen(QColor("#1e293b"), 1.0))
                    painter.drawRoundedRect(c_rect, 6, 6)
        else:
            # Tapa superior cerrada en perspectiva 3D
            top_grad = QLinearGradient(bx, by - depth_y, bx + box_w + depth_x, by)
            top_grad.setColorAt(0.0, base.lighter(130))
            top_grad.setColorAt(1.0, base.lighter(105))
            painter.setBrush(top_grad)
            painter.setPen(QPen(spine.darker(120), 1.0))
            painter.drawPolygon(top_poly)

        # 3. Costado derecho 3D (grosor real del portamazos)
        side_poly = QPolygonF([
            QPointF(bx + box_w - 1, by),
            QPointF(bx + box_w + depth_x - 1, by - depth_y),
            QPointF(bx + box_w + depth_x - 1, by + box_h - depth_y - 2),
            QPointF(bx + box_w - 1, by + box_h - 2),
        ])
        side_grad = QLinearGradient(bx + box_w, by, bx + box_w + depth_x, by + box_h)
        side_grad.setColorAt(0.0, spine.lighter(115))
        side_grad.setColorAt(1.0, spine.darker(135))
        painter.setBrush(side_grad)
        painter.setPen(QPen(spine.darker(155), 1.1))
        painter.drawPolygon(side_poly)

        # Línea de unión lateral de la tapa
        flap_h = box_h * 0.34
        painter.setPen(QPen(QColor(0, 0, 0, 110), 1.2))
        painter.drawLine(
            QPointF(bx + box_w, by + flap_h * 0.55),
            QPointF(bx + box_w + depth_x - 1, by + flap_h * 0.55 - depth_y),
        )

        # 4. Cuerpo frontal principal del portamazos
        body_rect = QRectF(bx, by, box_w, box_h)
        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, 10, 10)

        body_grad = QLinearGradient(bx, by, bx + box_w, by + box_h)
        body_grad.setColorAt(0.0, base.lighter(116))
        body_grad.setColorAt(0.55, base)
        body_grad.setColorAt(1.0, base.darker(122))

        painter.save()
        painter.setClipPath(body_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_grad)
        painter.drawRect(body_rect)

        # Bandas de acento decorativas diagonales
        accent_band = QPainterPath()
        accent_band.moveTo(bx, by + box_h * 0.60)
        accent_band.lineTo(bx + box_w, by + box_h * 0.42)
        accent_band.lineTo(bx + box_w, by + box_h * 0.52)
        accent_band.lineTo(bx, by + box_h * 0.70)
        accent_band.closeSubpath()
        painter.fillPath(accent_band, QColor(accent.red(), accent.green(), accent.blue(), 75))

        # Ilustración Pokémon o emblema vectorial en el cuerpo frontal
        art_rect = QRectF(bx + 12, by + flap_h * 0.72, box_w - 24, box_h * 0.44)
        kind = cfg.get("kind", "artwork")
        if kind == "artwork":
            art_pix = _load_artwork(cfg.get("artwork"))
            if art_pix and not art_pix.isNull():
                # Medallón suave detrás del Pokémon
                rad = min(art_rect.width(), art_rect.height()) * 0.48
                med = QRadialGradient(art_rect.center(), rad)
                med.setColorAt(0.0, QColor(accent2.red(), accent2.green(), accent2.blue(), 130))
                med.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
                painter.setBrush(med)
                painter.drawEllipse(art_rect.center(), rad, rad)
                scaled_art = art_pix.scaled(
                    int(art_rect.width()), int(art_rect.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                ax = art_rect.center().x() - scaled_art.width() / 2.0
                ay = art_rect.center().y() - scaled_art.height() / 2.0
                painter.drawPixmap(QPointF(ax, ay), scaled_art)
        elif kind == "pokeball":
            self._draw_ball_emblem(painter, art_rect.center(), min(art_rect.width(), art_rect.height()) * 0.36, False)
        elif kind == "masterball":
            self._draw_ball_emblem(painter, art_rect.center(), min(art_rect.width(), art_rect.height()) * 0.36, True)
        else:
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(art_rect.adjusted(6, 4, -6, -4), 6, 6)
            painter.setPen(QColor(255, 255, 255, 170))
            f_min = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(f_min)
            painter.drawText(art_rect, Qt.AlignmentFlag.AlignCenter, "DECK BOX\nPRO")

        # Costura perimetral del cuerpo
        stitch = QPen(QColor(255, 255, 255, 55), 1.0, Qt.PenStyle.DashLine)
        stitch.setDashPattern([4, 3])
        painter.setPen(stitch)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect.adjusted(4, 4, -4, -4), 7, 7)

        # Placa metálica inferior con nombre del mazo y contador X / 60
        plate_h = 34.0
        plate_rect = QRectF(bx + 8, by + box_h - plate_h - 7, box_w - 16, plate_h)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
        painter.setBrush(QColor(15, 15, 22, 195))
        painter.drawRoundedRect(plate_rect, 6, 6)

        font_name = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font_name)
        painter.setPen(QColor("#ffffff"))
        fm = QFontMetrics(font_name)
        elided = fm.elidedText(self._name, Qt.TextElideMode.ElideRight, int(plate_rect.width() - 12))
        painter.drawText(QRectF(plate_rect.left() + 6, plate_rect.top() + 2, plate_rect.width() - 12, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        font_sub = QFont("Segoe UI", 7, QFont.Weight.DemiBold)
        painter.setFont(font_sub)
        cnt_color = QColor("#4ade80") if self._card_count == 60 else QColor("#fbbf24")
        painter.setPen(cnt_color)
        painter.drawText(QRectF(plate_rect.left() + 6, plate_rect.top() + 17, plate_rect.width() - 12, 14), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"DECK BOX  |  {self._card_count} / 60")

        # Brillo diagonal sutil sobre el cuerpo al hacer hover
        if hover_p > 0.02:
            sheen = QLinearGradient(bx, by, bx + box_w, by + box_h)
            sheen.setColorAt(0.0, QColor(255, 255, 255, int(45 * hover_p)))
            sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(sheen)
            painter.drawRect(body_rect)

        # Indicador vectorial discreto de bloqueo si el portamazos está protegido
        if self._locked:
            badge_s = 20.0
            lock_x = bx + box_w - badge_s - 8.0
            lock_y = by + 8.0
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
            painter.setBrush(QColor(15, 23, 42, 210))
            painter.drawRoundedRect(QRectF(lock_x, lock_y, badge_s, badge_s), 5, 5)
            # Arco del candado
            painter.setPen(QPen(QColor("#fbbf24"), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(lock_x + 5.5, lock_y + 3.5, 9.0, 8.5), 0, 180 * 16)
            # Cuerpo del candado
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#fbbf24"))
            painter.drawRoundedRect(QRectF(lock_x + 4.5, lock_y + 8.5, 11.0, 8.0), 2, 2)

        painter.restore()

        # Borde nítido del cuerpo frontal
        painter.setPen(QPen(spine.darker(130), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, 10, 10)

        # 5. Tapa magnética frontal abatible (Flap en V con rotación 3D en eje X según lid_open)
        angle_rad = max(0.0, min(1.0, lid_open)) * (math.pi * 0.88)
        cos_a = math.cos(angle_rad)
        flap_tip_y = by + flap_h * cos_a
        flap_side_y = by + (flap_h * 0.58) * cos_a
        persp_w_expand = math.sin(angle_rad) * 8.0

        flap_path = QPainterPath()
        flap_path.moveTo(bx + 1, by + 2)
        flap_path.lineTo(bx + box_w - 1, by + 2)
        flap_path.lineTo(bx + box_w - 1 + persp_w_expand, flap_side_y)
        flap_path.lineTo(bx + box_w * 0.5, flap_tip_y)
        flap_path.lineTo(bx + 1 - persp_w_expand, flap_side_y)
        flap_path.closeSubpath()

        # Sombra proyectada por la tapa sobre el frente cuando está cerrada o abriéndose
        if cos_a > 0.0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(90 * cos_a)))
            painter.drawPath(flap_path.translated(0, 3.5))

        if cos_a >= 0.0:
            # Cara exterior de la tapa magnética
            fg = QLinearGradient(bx, by, bx, flap_tip_y)
            fg.setColorAt(0.0, base.lighter(126))
            fg.setColorAt(1.0, base.darker(108))
            painter.setBrush(fg)
            painter.setPen(QPen(spine.darker(135), 1.2))
            painter.drawPath(flap_path)

            # Broche/emblema metálico en la punta de la V
            clasp_r = 5.5
            painter.setBrush(accent)
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
            painter.drawEllipse(QPointF(bx + box_w * 0.5, flap_tip_y - 9.0 * cos_a), clasp_r, clasp_r * max(0.3, cos_a))
        else:
            # Cara interior aterciopelada de la tapa cuando ya giró hacia arriba (>90°)
            painter.setBrush(QColor("#1e1b26"))
            painter.setPen(QPen(base.lighter(115), 1.2))
            painter.drawPath(flap_path)

    @staticmethod
    def _draw_ball_emblem(painter: QPainter, center: QPointF, r: float, is_master: bool):
        painter.save()
        top_c = QColor("#7e22ce") if is_master else QColor("#dc2626")
        clip = QPainterPath()
        clip.addEllipse(center, r, r)
        painter.setClipPath(clip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(top_c)
        painter.drawRect(QRectF(center.x() - r, center.y() - r, r * 2, r))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRect(QRectF(center.x() - r, center.y(), r * 2, r))
        painter.setBrush(QColor("#18181b"))
        painter.drawRect(QRectF(center.x() - r, center.y() - 3.0, r * 2, 6.0))
        painter.restore()

        painter.setPen(QPen(QColor("#18181b"), 1.8))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(center, r * 0.28, r * 0.28)
        if is_master:
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", max(8, int(r * 0.38)), QFont.Weight.Black))
            painter.drawText(QRectF(center.x() - r * 0.5, center.y() - r * 0.88, r, r * 0.55), Qt.AlignmentFlag.AlignCenter, "M")


class DeckBoxOpenAnimationOverlay(QWidget):
    """
    Animación 3D de apertura y cierre del Portamazos (Issue #19):
      - Apertura (reverse=False): El portamazos vuela al centro, abre su tapa magnética en 3D
        y las cartas emergen hacia arriba antes de revelar el editor del mazo.
      - Cierre (reverse=True): Las cartas se guardan dentro, la tapa se cierra y el portamazos
        vuela de regreso a su posición exacta en la estantería.
    """
    animation_finished = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        name: str,
        design: str,
        color: str,
        card_count: int,
        origin_rect: QRectF | None = None,
        reverse: bool = False,
        shelf_pixmap: QPixmap | None = None,
        editor_pixmap: QPixmap | None = None,
    ):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self._deck_renderer = DeckBoxWidget(name=name, design=design, color=color, card_count=card_count)
        self.origin_rect = QRectF(origin_rect) if origin_rect else None
        self.reverse = bool(reverse)
        self.shelf_pixmap = shelf_pixmap
        self.editor_pixmap = editor_pixmap

        self._progress = 1.0 if self.reverse else 0.0
        self._sfx = None
        self._sound_played = False

        self.show()
        self.raise_()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(scale_anim_duration(680 if self.reverse else 740, min_ms=220))
        self._anim.setStartValue(1.0 if self.reverse else 0.0)
        self._anim.setEndValue(0.0 if self.reverse else 1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_tick)
        self._anim.finished.connect(self._on_done)
        self._anim.start()

    def _on_tick(self, val):
        self._progress = float(val)
        if not self._sound_played:
            if (not self.reverse and self._progress >= 0.30) or (self.reverse and self._progress <= 0.72):
                self._sound_played = True
                self._sfx = play_page_turn_sound(self)
        self.update()

    def _on_done(self):
        self._deck_renderer.deleteLater()
        self.animation_finished.emit()
        self.hide()
        self.deleteLater()

    @staticmethod
    def _ease_out_cubic(x: float) -> float:
        return 1.0 - (1.0 - x) ** 3

    @staticmethod
    def _ease_in_out_cubic(x: float) -> float:
        return 4.0 * x * x * x if x < 0.5 else 1.0 - ((-2.0 * x + 2.0) ** 3) / 2.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        p = self._progress
        # 1. Cross-fade limpio de fondo entre estantería y editor
        blend = max(0.0, min(1.0, (p - 0.58) / 0.38))
        if self.shelf_pixmap and not self.shelf_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.shelf_pixmap)
        else:
            painter.fillRect(self.rect(), QColor("#fff5f7"))

        if self.editor_pixmap and not self.editor_pixmap.isNull() and blend > 0.005:
            painter.save()
            painter.setOpacity(blend)
            painter.drawPixmap(self.rect(), self.editor_pixmap)
            painter.restore()

        # Viñeta de enfoque sutil
        vig = int(65 * math.sin(p * math.pi))
        if vig > 2:
            painter.fillRect(self.rect(), QColor(15, 10, 18, vig))

        # Tamaño y posición centrada del portamazos abierto
        center_w = min(290.0, self.width() * 0.34)
        center_h = center_w * 1.24
        center_rect = QRectF(
            (self.width() - center_w) * 0.5,
            (self.height() - center_h) * 0.52,
            center_w,
            center_h,
        )

        # Fase 1 (0.0 -> 0.32): Vuelo hacia/desde la estantería
        if p < 0.32:
            t1 = self._ease_out_cubic(p / 0.32)
            start_r = self.origin_rect if (self.origin_rect and self.origin_rect.width() > 20) else QRectF(
                center_rect.center().x() - 90, center_rect.center().y() - 110, 180, 220
            )
            cur_r = QRectF(
                start_r.x() + (center_rect.x() - start_r.x()) * t1,
                start_r.y() + (center_rect.y() - start_r.y()) * t1,
                start_r.width() + (center_rect.width() - start_r.width()) * t1,
                start_r.height() + (center_rect.height() - start_r.height()) * t1,
            )
            self._deck_renderer.draw_deck_box(painter, cur_r, lid_open=0.0, cards_rise=0.0, hover_p=t1)
            return

        # Fase 2 (0.32 -> 1.0): Apertura 3D de la tapa magnética + cartas emergiendo + desvanecimiento al editor
        t2 = self._ease_in_out_cubic(min(1.0, (p - 0.32) / 0.48))
        lid_open = t2
        cards_rise = max(0.0, min(1.0, (t2 - 0.25) / 0.75))
        box_opacity = 1.0 if p < 0.78 else max(0.0, (1.0 - p) / 0.22)

        if box_opacity > 0.02:
            painter.save()
            painter.setOpacity(box_opacity)
            self._deck_renderer.draw_deck_box(painter, center_rect, lid_open=lid_open, cards_rise=cards_rise, hover_p=1.0)
            painter.restore()
