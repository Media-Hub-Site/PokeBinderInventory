import math
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QApplication
from PyQt6.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, QVariantAnimation,
    QEasingCurve, pyqtSignal, QUrl, QMimeData
)
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QPixmap, QPolygonF, QTransform, QRegion, QDrag
)

try:
    from PyQt6.QtMultimedia import QSoundEffect
    _HAS_MULTIMEDIA = True
except Exception:
    _HAS_MULTIMEDIA = False

from MyQtApp.config import SOUNDS_DIR, scale_anim_duration
from MyQtApp.ui.BinderCoverWidget import BINDER_DESIGNS, resolve_design_key


def resolve_binder_palette(design: str, color: str = "auto") -> tuple[QColor, QColor, QColor]:
    """Retorna (base_color, spine_color, accent_color) para el diseño del binder."""
    key = resolve_design_key(design)
    theme = BINDER_DESIGNS.get(key, BINDER_DESIGNS["Charizard Fuego"])
    base = QColor(theme["base"])
    spine = QColor(theme["spine"])
    accent = QColor(theme["accent"])
    if color and color != "auto":
        c = QColor(color)
        if c.isValid():
            base = c
            spine = c.darker(145)
    return base, spine, accent


def play_page_turn_sound(parent_widget=None):
    """Reproduce suavemente el sonido de cambio de página/mica si está disponible."""
    if not _HAS_MULTIMEDIA:
        return None
    wav_path = os.path.join(SOUNDS_DIR, "paginas.wav")
    if not os.path.exists(wav_path):
        return None
    try:
        sfx = QSoundEffect(parent_widget)
        sfx.setSource(QUrl.fromLocalFile(wav_path))
        sfx.setVolume(0.45)
        sfx.play()
        return sfx
    except Exception:
        return None


def draw_binder_rings(painter: QPainter, spine_x: float, top_y: float, bottom_y: float, ring_count: int = 3):
    """Dibuja anillas metálicas cromadas realistas en el lomo central del binder."""
    height = max(60.0, bottom_y - top_y)
    if ring_count == 3:
        ratios = (0.18, 0.50, 0.82)
    else:
        ratios = tuple((i + 1) / (ring_count + 1) for i in range(ring_count))

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    for r in ratios:
        cy = top_y + height * r

        # Orificios perforados en las micas izquierda y derecha
        for side in (-1, 1):
            hx = spine_x + side * 19.0
            painter.setPen(QPen(QColor(255, 255, 255, 55), 1.0))
            painter.setBrush(QColor(12, 12, 16, 220))
            painter.drawEllipse(QPointF(hx, cy), 4.5, 4.5)

        # Sombra proyectada de la anilla sobre el lomo
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 115))
        painter.drawRoundedRect(QRectF(spine_x - 20.5, cy - 3.0, 41.0, 9.5), 4.5, 4.5)

        # Aro metálico cromado (gradiente vertical simulando cilindro reflectante)
        ring_rect = QRectF(spine_x - 20.0, cy - 5.2, 40.0, 9.2)
        chrome = QLinearGradient(ring_rect.left(), ring_rect.top(), ring_rect.left(), ring_rect.bottom())
        chrome.setColorAt(0.0, QColor("#52525b"))
        chrome.setColorAt(0.22, QColor("#e4e4e7"))
        chrome.setColorAt(0.42, QColor("#ffffff"))
        chrome.setColorAt(0.68, QColor("#a1a1aa"))
        chrome.setColorAt(1.0, QColor("#27272a"))

        painter.setBrush(chrome)
        painter.setPen(QPen(QColor("#18181b"), 1.0))
        painter.drawRoundedRect(ring_rect, 4.5, 4.5)

        # Reflejo horizontal sutil en el centro superior del aro
        shine_rect = QRectF(spine_x - 13.0, cy - 3.6, 26.0, 2.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.drawRoundedRect(shine_rect, 1.0, 1.0)

        # Bisagra/remache central metálico sutil
        painter.setBrush(QColor(60, 60, 68, 120))
        painter.drawRect(QRectF(spine_x - 0.8, cy - 4.8, 1.6, 8.4))

    painter.restore()


def _paint_binder_board_background(
    painter: QPainter,
    rect: QRectF,
    base_color: QColor,
    spine_color: QColor,
    accent_color: QColor,
    draw_rings: bool = True,
    hover_corner: str | None = None,
    interior_color: str | None = None,
    binder_type: str = "normal",
):
    """Dibuja el cuerpo físico del binder abierto: tapas, grosor de hojas, fondo interior y anillas."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    is_toploader = binder_type == "toploader"

    outer = rect.adjusted(6, 4, -6, -8)
    cx = outer.center().x()

    # 1. Sombra proyectada sobre la mesa
    shadow_path = QPainterPath()
    shadow_path.addRoundedRect(outer.translated(0, 5), 14, 14)
    painter.fillPath(shadow_path, QColor(0, 0, 0, 65))

    # 2. Tapa dura exterior (cuero / polipiel del tema del binder)
    board_grad = QLinearGradient(outer.left(), outer.top(), outer.right(), outer.bottom())
    board_grad.setColorAt(0.0, base_color.lighter(115))
    board_grad.setColorAt(0.48, base_color)
    board_grad.setColorAt(0.50, spine_color.darker(115))
    board_grad.setColorAt(0.52, base_color)
    board_grad.setColorAt(1.0, base_color.darker(118))

    board_path = QPainterPath()
    board_path.addRoundedRect(outer, 13, 13)
    painter.fillPath(board_path, board_grad)
    painter.setPen(QPen(QColor("#38bdf8") if is_toploader else spine_color.darker(130), 1.6))
    painter.drawPath(board_path)

    # Costura perimetral (Ultra PRO) o cierre zip metálico (TopLoader)
    stitch_rect = outer.adjusted(4.5, 4.5, -4.5, -4.5)
    if is_toploader:
        stitch_pen = QPen(QColor(186, 230, 253, 95), 1.4, Qt.PenStyle.DashLine)
        stitch_pen.setDashPattern([2.5, 2.5])
    else:
        stitch_pen = QPen(QColor(255, 255, 255, 50), 1.0, Qt.PenStyle.DashLine)
        stitch_pen.setDashPattern([4, 3])
    painter.setPen(stitch_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(stitch_rect, 10, 10)

    # 3. Grosor 3D de hojas apiladas en los bordes exteriores (izquierdo y derecho)
    inner = outer.adjusted(12, 9, -12, -9)
    for layer in range(3):
        offset = (3 - layer) * (2.4 if is_toploader else 2.0)
        alpha = (175 if is_toploader else 155) - layer * 25
        # Borde izquierdo apilado
        painter.setPen(Qt.PenStyle.NoPen)
        edge_col = QColor(210, 236, 252, alpha) if is_toploader else QColor(235, 232, 238, alpha)
        painter.setBrush(edge_col)
        painter.drawRoundedRect(
            QRectF(inner.left() - offset, inner.top() + layer * 1.2, 4.0, inner.height() - layer * 2.4),
            1.5, 1.5
        )
        # Borde derecho apilado
        painter.drawRoundedRect(
            QRectF(inner.right() + offset - 4.0, inner.top() + layer * 1.2, 4.0, inner.height() - layer * 2.4),
            1.5, 1.5
        )

    # 4. Contorno interior del binder: ligeramente más oscuro que el color de las hojas (Issue #28)
    ic = QColor(interior_color) if interior_color else QColor("#18181e")
    if not ic.isValid():
        ic = QColor("#18181e")
    luma = 0.299 * ic.red() + 0.587 * ic.green() + 0.114 * ic.blue()
    inner_center = ic.darker(114)
    inner_edge = ic.darker(134)

    inner_grad = QRadialGradient(cx, inner.center().y(), inner.width() * 0.65)
    inner_grad.setColorAt(0.0, inner_center)
    inner_grad.setColorAt(1.0, inner_edge)
    painter.setBrush(inner_grad)
    border_pen_col = QColor(15, 23, 42, 42) if luma > 155 else QColor(255, 255, 255, 24)
    painter.setPen(QPen(border_pen_col, 1.0))
    painter.drawRoundedRect(inner, 8, 8)

    # 5. Hendidura / sombra del lomo central (suavizada para colores claros)
    gutter_w = 50.0
    gutter_rect = QRectF(cx - gutter_w / 2.0, inner.top(), gutter_w, inner.height())
    gutter = QLinearGradient(gutter_rect.left(), 0, gutter_rect.right(), 0)
    g_mid = 48 if luma > 155 else 95
    g_peak = 90 if luma > 155 else 175
    gutter.setColorAt(0.0, QColor(0, 0, 0, 0))
    gutter.setColorAt(0.32, QColor(0, 0, 0, g_mid))
    gutter.setColorAt(0.50, QColor(0, 0, 0, g_peak))
    gutter.setColorAt(0.68, QColor(0, 0, 0, g_mid))
    gutter.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(gutter_rect, gutter)

    # Línea de pliegue del lomo
    painter.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
    painter.drawLine(QPointF(cx, inner.top() + 4), QPointF(cx, inner.bottom() - 4))

    # 6. Indicador sutil de esquina interactiva ("arrastra para pasar página")
    if hover_corner == "right":
        peel = QPainterPath()
        rx, by = inner.right() - 2, inner.bottom() - 2
        peel.moveTo(rx, by - 36)
        peel.lineTo(rx - 36, by)
        peel.lineTo(rx, by)
        peel.closeSubpath()
        pg = QLinearGradient(rx - 34, by - 34, rx, by)
        pg.setColorAt(0.0, QColor(255, 255, 255, 140))
        pg.setColorAt(0.5, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 110))
        pg.setColorAt(1.0, QColor(255, 255, 255, 30))
        painter.fillPath(peel, pg)
    elif hover_corner == "left":
        peel = QPainterPath()
        lx, by = inner.left() + 2, inner.bottom() - 2
        peel.moveTo(lx, by - 36)
        peel.lineTo(lx + 36, by)
        peel.lineTo(lx, by)
        peel.closeSubpath()
        pg = QLinearGradient(lx + 34, by - 34, lx, by)
        pg.setColorAt(0.0, QColor(255, 255, 255, 140))
        pg.setColorAt(0.5, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 110))
        pg.setColorAt(1.0, QColor(255, 255, 255, 30))
        painter.fillPath(peel, pg)

    # 7. Anillas metálicas cromadas centrales
    if draw_rings:
        draw_binder_rings(painter, cx, inner.top() + 14, inner.bottom() - 14, ring_count=3)

    painter.restore()


class BinderSpreadFrame(QWidget):
    """
    Contenedor físico del pliego abierto (2 páginas + tapa dura + lomo + anillas cromadas).
    Soporta detección de arrastre desde las esquinas/bordes exteriores para pasar página con el mouse.
    """
    drag_turn_started = pyqtSignal(int, float)   # direction (+1/-1), start_x_local
    drag_turn_moved = pyqtSignal(float)          # current_x_local
    drag_turn_released = pyqtSignal(float)       # end_x_local

    def __init__(self, design="Charizard Fuego", color="auto", can_go_prev=False, interior_color=None, binder_type="normal", parent=None):
        super().__init__(parent)
        self.base_color, self.spine_color, self.accent_color = resolve_binder_palette(design, color)
        self.interior_color = interior_color
        self.binder_type = "toploader" if binder_type == "toploader" else "normal"
        self.can_go_prev = can_go_prev
        self._hover_corner = None
        self._dragging_turn = False
        self._drag_direction = 0
        self._drag_turn_enabled = True
        self.setMouseTracking(True)

        self.spread_layout = QHBoxLayout(self)
        self.spread_layout.setSpacing(44)
        self.spread_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spread_layout.setContentsMargins(24, 18, 24, 18)

    def set_drag_turn_enabled(self, enabled: bool):
        self._drag_turn_enabled = bool(enabled)
        if not self._drag_turn_enabled and self._hover_corner is not None:
            self._hover_corner = None
            self.unsetCursor()
            self.update()

    def set_theme(self, design: str, color: str = "auto", interior_color: str = None):
        self.base_color, self.spine_color, self.accent_color = resolve_binder_palette(design, color)
        if interior_color is not None:
            self.interior_color = interior_color
        self.update()

    def get_board_rect(self) -> QRectF:
        """Retorna el rectángulo ajustado exactamente alrededor de las 2 páginas."""
        if self.spread_layout.count() >= 2:
            w1 = self.spread_layout.itemAt(0).widget()
            w2 = self.spread_layout.itemAt(1).widget()
            if w1 and w2 and w1.width() > 0 and w2.width() > 0:
                g1 = w1.geometry()
                g2 = w2.geometry()
                union = g1.united(g2)
                return QRectF(union.adjusted(-22, -16, 22, 18))
        return QRectF(self.rect())

    def get_pages_inner_rect(self) -> QRect:
        """Retorna el QRect exacto que abarca la página izquierda y la página derecha."""
        if self.spread_layout.count() >= 2:
            w1 = self.spread_layout.itemAt(0).widget()
            w2 = self.spread_layout.itemAt(1).widget()
            if w1 and w2 and w1.width() > 0 and w2.width() > 0:
                return w1.geometry().united(w2.geometry())
        return self.rect().adjusted(24, 18, -24, -18)

    def paintEvent(self, event):
        painter = QPainter(self)
        _paint_binder_board_background(
            painter,
            self.get_board_rect(),
            self.base_color,
            self.spine_color,
            self.accent_color,
            draw_rings=True,
            hover_corner=self._hover_corner,
            interior_color=self.interior_color,
            binder_type=getattr(self, "binder_type", "normal"),
        )

    def _detect_edge_zone(self, pos: QPoint) -> str | None:
        board = self.get_board_rect()
        if not board.contains(QPointF(pos)):
            return None
        edge_w = 48.0
        if pos.x() >= board.right() - edge_w:
            return "right"
        if self.can_go_prev and pos.x() <= board.left() + edge_w:
            return "left"
        return None

    def mouseMoveEvent(self, event):
        if self._dragging_turn:
            self.drag_turn_moved.emit(float(event.position().x()))
            event.accept()
            return

        if not getattr(self, "_drag_turn_enabled", True):
            super().mouseMoveEvent(event)
            return

        zone = self._detect_edge_zone(event.position().toPoint())
        if zone != self._hover_corner:
            self._hover_corner = zone
            if zone:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if not self._dragging_turn and self._hover_corner is not None:
            self._hover_corner = None
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and getattr(self, "_drag_turn_enabled", True):
            zone = self._detect_edge_zone(event.position().toPoint())
            if zone == "right":
                self._dragging_turn = True
                self._drag_direction = 1
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.drag_turn_started.emit(1, float(event.position().x()))
                event.accept()
                return
            elif zone == "left" and self.can_go_prev:
                self._dragging_turn = True
                self._drag_direction = -1
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.drag_turn_started.emit(-1, float(event.position().x()))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_turn and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_turn = False
            self._drag_direction = 0
            self.unsetCursor()
            self.drag_turn_released.emit(float(event.position().x()))
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _draw_quad_pixmap(
    painter: QPainter,
    pixmap: QPixmap,
    src_rect: QRectF,
    dst_poly: QPolygonF,
):
    """Dibuja una porción rectangular de un QPixmap proyectada en un cuadrilátero 3D usando homografía."""
    if pixmap.isNull() or src_rect.width() < 0.5 or src_rect.height() < 0.5:
        return
    src_poly = QPolygonF([
        QPointF(src_rect.left(), src_rect.top()),
        QPointF(src_rect.right(), src_rect.top()),
        QPointF(src_rect.right(), src_rect.bottom()),
        QPointF(src_rect.left(), src_rect.bottom()),
    ])
    transform = QTransform()
    if not QTransform.quadToQuad(src_poly, dst_poly, transform):
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setTransform(transform, True)
    painter.drawPixmap(src_rect, pixmap, src_rect)
    painter.restore()


class PageFlipAnimationOverlay(QWidget):
    """
    Overlay 3D de cambio de página realista con deformación curva en múltiples franjas,
    iluminación dinámica, brillo especular sobre micas plásticas, sombras proyectadas
    y soporte tanto para animación automática como para arrastre manual con el mouse.
    """
    flip_completed = pyqtSignal(bool)  # True = completado (cambió página), False = cancelado (volvió)

    NUM_STRIPS = 14

    def __init__(
        self,
        parent: QWidget,
        old_left_pix: QPixmap,
        old_right_pix: QPixmap,
        new_left_pix: QPixmap,
        new_right_pix: QPixmap,
        board_rect: QRectF,
        left_page_rect: QRectF,
        right_page_rect: QRectF,
        direction: int,
        design: str = "Charizard Fuego",
        color: str = "auto",
    ):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.old_left_pix = old_left_pix
        self.old_right_pix = old_right_pix
        self.new_left_pix = new_left_pix
        self.new_right_pix = new_right_pix
        self.board_rect = QRectF(board_rect)
        self.left_page_rect = QRectF(left_page_rect)
        self.right_page_rect = QRectF(right_page_rect)
        self.direction = 1 if direction >= 0 else -1
        self.base_color, self.spine_color, self.accent_color = resolve_binder_palette(design, color)

        self._progress = 0.0
        self._anim = None
        self._sfx = None
        self._sound_played = False
        self._finished = False

        self.show()
        self.raise_()

    def set_progress(self, value: float):
        if self._finished:
            return
        self._progress = max(0.0, min(1.0, float(value)))
        if not self._sound_played and self._progress >= 0.25:
            self._sound_played = True
            self._sfx = play_page_turn_sound(self)
        self.update()

    def progress(self) -> float:
        return self._progress

    def start_auto_flip(self, duration_ms: int = 520, start_val: float = 0.0, end_val: float = 1.0):
        """Anima automáticamente el giro desde start_val hasta end_val."""
        if self._finished:
            return
        if self._anim and self._anim.state() == QVariantAnimation.State.Running:
            self._anim.stop()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(scale_anim_duration(int(duration_ms), min_ms=110))
        self._anim.setStartValue(float(start_val))
        self._anim.setEndValue(float(end_val))
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic if start_val == 0.0 else QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_val)
        completed_flag = end_val >= 0.5
        self._anim.finished.connect(lambda: self._finish(completed_flag))
        self._anim.start()

    def _on_anim_val(self, val):
        self.set_progress(float(val))

    def _finish(self, completed: bool):
        if self._finished:
            return
        self._finished = True
        self.flip_completed.emit(completed)
        self.hide()
        self.deleteLater()

    def cancel(self):
        """Detiene el giro de página de forma segura sin emitir señales."""
        if self._finished:
            return
        self._finished = True
        try:
            if self._anim is not None:
                self._anim.blockSignals(True)
                self._anim.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Cuerpo físico del binder de fondo (sin anillas aún; las anillas van al final encima)
        _paint_binder_board_background(
            painter,
            self.board_rect,
            self.base_color,
            self.spine_color,
            self.accent_color,
            draw_rings=False,
        )

        # 2. Páginas estáticas inferiores
        if self.direction == 1:
            # Avanzando: izquierda estática = old_left, derecha revelada debajo = new_right
            painter.drawPixmap(self.left_page_rect, self.old_left_pix, QRectF(self.old_left_pix.rect()))
            painter.drawPixmap(self.right_page_rect, self.new_right_pix, QRectF(self.new_right_pix.rect()))
            front_pix = self.old_right_pix
            back_pix = self.new_left_pix
            page_w = self.right_page_rect.width()
            page_h = self.right_page_rect.height()
            top_y = self.right_page_rect.top()
        else:
            # Retrocediendo: derecha estática = old_right, izquierda revelada debajo = new_left
            painter.drawPixmap(self.left_page_rect, self.new_left_pix, QRectF(self.new_left_pix.rect()))
            painter.drawPixmap(self.right_page_rect, self.old_right_pix, QRectF(self.old_right_pix.rect()))
            front_pix = self.old_left_pix
            back_pix = self.new_right_pix
            page_w = self.left_page_rect.width()
            page_h = self.left_page_rect.height()
            top_y = self.left_page_rect.top()

        spine_x = (self.left_page_rect.right() + self.right_page_rect.left()) * 0.5
        cy = top_y + page_h * 0.5
        t = self._progress
        theta = t * math.pi

        # 3. Sombra dinámica proyectada por la hoja que se levanta sobre la página inferior
        shadow_alpha = int(125 * math.sin(theta))
        if shadow_alpha > 2:
            if self.direction == 1:
                if t < 0.5:
                    # Sombra sobre la página derecha recién descubierta
                    sh_w = max(18.0, page_w * (1.0 - t * 1.4))
                    sh_rect = QRectF(spine_x, top_y, sh_w, page_h)
                    sg = QLinearGradient(sh_rect.left(), 0, sh_rect.right(), 0)
                    sg.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
                    sg.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(sh_rect, sg)
                else:
                    # Sombra cayendo sobre la página izquierda antigua
                    sh_w = max(18.0, page_w * ((t - 0.5) * 2.0))
                    sh_rect = QRectF(spine_x - sh_w, top_y, sh_w, page_h)
                    sg = QLinearGradient(sh_rect.right(), 0, sh_rect.left(), 0)
                    sg.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
                    sg.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(sh_rect, sg)
            else:
                if t < 0.5:
                    sh_w = max(18.0, page_w * (1.0 - t * 1.4))
                    sh_rect = QRectF(spine_x - sh_w, top_y, sh_w, page_h)
                    sg = QLinearGradient(sh_rect.right(), 0, sh_rect.left(), 0)
                    sg.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
                    sg.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(sh_rect, sg)
                else:
                    sh_w = max(18.0, page_w * ((t - 0.5) * 2.0))
                    sh_rect = QRectF(spine_x, top_y, sh_w, page_h)
                    sg = QLinearGradient(sh_rect.left(), 0, sh_rect.right(), 0)
                    sg.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
                    sg.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(sh_rect, sg)

        # 4. Malla curva 3D de la hoja giratoria (N franjas verticales con curvatura orgánica)
        N = self.NUM_STRIPS
        # Anclaje en el borde interior de la página (justo junto a las anillas)
        half_gap = (self.right_page_rect.left() - self.left_page_rect.right()) * 0.5
        anchor_offset = half_gap * math.cos(theta)
        start_x = spine_x + (anchor_offset if self.direction == 1 else -anchor_offset)

        ds = page_w / N
        curl_strength = math.sin(theta) * 0.36  # Curvatura flexible de la mica plástica

        pts_x = [0.0] * (N + 1)
        pts_z = [0.0] * (N + 1)
        phis = [0.0] * N

        for i in range(N):
            u_mid = (i + 0.5) / N
            # La zona cercana al lomo inicia antes y el borde exterior se arquea suavemente
            phi = theta - curl_strength * (u_mid - 0.32)
            phi = max(0.0, min(math.pi, phi))
            phis[i] = phi
            pts_x[i + 1] = pts_x[i] + ds * math.cos(phi)
            pts_z[i + 1] = pts_z[i] + ds * math.sin(phi)

        # Proyección en perspectiva 3D
        cam_dist = max(480.0, page_w * 3.4)
        sx = [0.0] * (N + 1)
        top_ys = [0.0] * (N + 1)
        bot_ys = [0.0] * (N + 1)

        for k in range(N + 1):
            persp = cam_dist / max(120.0, cam_dist - pts_z[k])
            if self.direction == 1:
                sx[k] = start_x + pts_x[k] * persp
            else:
                sx[k] = start_x - pts_x[k] * persp
            hh = (page_h * 0.5) * persp
            top_ys[k] = cy - hh
            bot_ys[k] = cy + hh

        # Ordenar dibujado: si la hoja ya cruzó 90°, dibujar de afuera hacia adentro para Z correcto
        indices = range(N) if t < 0.5 else range(N - 1, -1, -1)

        fw = front_pix.width()
        fh = front_pix.height()
        bw = back_pix.width()
        bh = back_pix.height()

        for i in indices:
            x0, x1 = sx[i], sx[i + 1]
            if abs(x1 - x0) < 0.65:
                # Borde de canto de la hoja vista de perfil
                painter.setPen(QPen(QColor(220, 220, 230, 180), 1.2))
                painter.drawLine(QPointF(x0, top_ys[i]), QPointF(x0, bot_ys[i]))
                continue

            # Determinar si esta franja muestra la cara frontal o trasera
            showing_front = (x1 > x0) if self.direction == 1 else (x1 < x0)

            if showing_front:
                if self.direction == 1:
                    u0 = i / N
                    u1 = (i + 1) / N
                    src_rect = QRectF(u0 * fw, 0, (u1 - u0) * fw, fh)
                    dst_poly = QPolygonF([
                        QPointF(x0, top_ys[i]),
                        QPointF(x1, top_ys[i + 1]),
                        QPointF(x1, bot_ys[i + 1]),
                        QPointF(x0, bot_ys[i]),
                    ])
                else:
                    # En dirección -1, el strip 0 está pegado al lomo (lado derecho de old_left)
                    u0 = 1.0 - (i + 1) / N
                    u1 = 1.0 - i / N
                    src_rect = QRectF(u0 * fw, 0, (u1 - u0) * fw, fh)
                    dst_poly = QPolygonF([
                        QPointF(x1, top_ys[i + 1]),
                        QPointF(x0, top_ys[i]),
                        QPointF(x0, bot_ys[i]),
                        QPointF(x1, bot_ys[i + 1]),
                    ])
                _draw_quad_pixmap(painter, front_pix, src_rect, dst_poly)
            else:
                if self.direction == 1:
                    # Reverso (new_left): el borde cercano al lomo (i=0) corresponde al lado derecho de new_left
                    u0 = 1.0 - (i + 1) / N
                    u1 = 1.0 - i / N
                    src_rect = QRectF(u0 * bw, 0, (u1 - u0) * bw, bh)
                    dst_poly = QPolygonF([
                        QPointF(x1, top_ys[i + 1]),
                        QPointF(x0, top_ys[i]),
                        QPointF(x0, bot_ys[i]),
                        QPointF(x1, bot_ys[i + 1]),
                    ])
                else:
                    # Reverso (new_right): el borde cercano al lomo (i=0) corresponde al lado izquierdo de new_right
                    u0 = i / N
                    u1 = (i + 1) / N
                    src_rect = QRectF(u0 * bw, 0, (u1 - u0) * bw, bh)
                    dst_poly = QPolygonF([
                        QPointF(x0, top_ys[i]),
                        QPointF(x1, top_ys[i + 1]),
                        QPointF(x1, bot_ys[i + 1]),
                        QPointF(x0, bot_ys[i]),
                    ])
                _draw_quad_pixmap(painter, back_pix, src_rect, dst_poly)

            # Iluminación dinámica + brillo especular de mica plástica Ultra PRO
            phi = phis[i]
            quad = QPolygonF([
                QPointF(x0, top_ys[i]),
                QPointF(x1, top_ys[i + 1]),
                QPointF(x1, bot_ys[i + 1]),
                QPointF(x0, bot_ys[i]),
            ])
            # Sombreado de curvatura
            shade = abs(math.sin(phi)) * 0.34
            if shade > 0.02:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, int(shade * 140)))
                painter.drawPolygon(quad)

            # Reflejo especular deslizándose por el plástico protector cuando pasa cerca de 55°-125°
            glare = max(0.0, 1.0 - abs(phi - 1.15) / 0.55)
            if glare > 0.05:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, int(glare * 62)))
                painter.drawPolygon(quad)

        # 5. Anillas cromadas centrales encima de todo para que la página gire alrededor de ellas
        inner_board = self.board_rect.adjusted(18, 13, -18, -17)
        draw_binder_rings(painter, spine_x, inner_board.top() + 14, inner_board.bottom() - 14, ring_count=3)


def render_transparent_cover_pixmap(
    name: str, design: str, color: str, mode: str, width: int, height: int,
    custom_image: str = None, locked: bool = False, advanced_design: dict = None,
    binder_type: str = "normal"
) -> QPixmap:
    """Renderiza la portada física BinderCoverWidget sobre un QPixmap transparente (sin bordes blancos)."""
    from MyQtApp.ui.BinderCoverWidget import BinderCoverWidget

    w = max(120, int(width))
    h = max(160, int(height))
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)

    temp = BinderCoverWidget(
        name=name, design=design, color=color, mode=mode,
        custom_image=custom_image, locked=locked, advanced_design=advanced_design,
        binder_type=binder_type,
    )
    temp.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    temp.resize(w, h)
    # RenderFlag(0) omite el fondo opaco de ventana y dibuja únicamente paintEvent sobre el fondo transparente
    temp.render(pix, QPoint(0, 0), QRegion(), QWidget.RenderFlag(0))
    temp.deleteLater()
    return pix


class BinderOpenAnimationOverlay(QWidget):
    """
    Animación 3D cinematográfica de apertura y cierre de Binder (como abrir/cerrar un libro físico real):
      - Apertura (reverse=False):
          Fase 1 (0.0 -> 0.28): La portada cerrada vuela desde la estantería al centro sobre el fondo limpio.
          Fase 2 (0.28 -> 1.0): La tapa gira 180° en perspectiva 3D revelando el pliego abierto sin fondo duplicado.
      - Cierre (reverse=True):
          Fase 1 (1.0 -> 0.28): La tapa gira de 180° a 0° cerrando el binder.
          Fase 2 (0.28 -> 0.0): El binder cerrado vuela suavemente de regreso a su posición exacta en la estantería.
    """
    animation_finished = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        cover_pixmap: QPixmap,
        spread_pixmap: QPixmap,
        board_rect: QRectF,
        origin_rect: QRectF | None = None,
        design: str = "Charizard Fuego",
        color: str = "auto",
        reverse: bool = False,
        shelf_pixmap: QPixmap | None = None,
        pages_bg_pixmap: QPixmap | None = None,
    ):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.cover_pixmap = cover_pixmap
        self.spread_pixmap = spread_pixmap
        self.board_rect = QRectF(board_rect)
        self.origin_rect = QRectF(origin_rect) if origin_rect else None
        self.base_color, self.spine_color, self.accent_color = resolve_binder_palette(design, color)
        self.reverse = bool(reverse)
        self.shelf_pixmap = shelf_pixmap
        self.pages_bg_pixmap = pages_bg_pixmap

        self._progress = 1.0 if self.reverse else 0.0
        self._sfx = None
        self._sound_played = False

        # Pre-construir textura del forro interior de la tapa
        self._inner_lining_pix = self._build_inner_lining_pixmap(
            max(120, int(self.board_rect.width() * 0.5)),
            max(160, int(self.board_rect.height())),
        )

        self._finished = False
        self.show()
        self.raise_()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(scale_anim_duration(720 if self.reverse else 780, min_ms=220))
        self._anim.setStartValue(1.0 if self.reverse else 0.0)
        self._anim.setEndValue(0.0 if self.reverse else 1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_tick)
        self._anim.finished.connect(self._on_done)
        self._anim.start()

    def _build_inner_lining_pixmap(self, w: int, h: int) -> QPixmap:
        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(2, 2, w - 4, h - 4)
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, self.base_color.darker(155))
        grad.setColorAt(0.5, QColor("#1c1b22"))
        grad.setColorAt(1.0, self.spine_color.darker(140))

        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, grad)
        p.setPen(QPen(self.base_color.lighter(115), 2.0))
        p.drawPath(path)

        # Bolsillo interior diagonal de tapa Ultra PRO
        pocket = QPainterPath()
        pocket.moveTo(rect.left() + 14, rect.bottom() - 14)
        pocket.lineTo(rect.right() - 14, rect.bottom() - 14)
        pocket.lineTo(rect.right() - 14, rect.top() + h * 0.55)
        pocket.lineTo(rect.left() + 14, rect.top() + h * 0.72)
        pocket.closeSubpath()
        p.fillPath(pocket, QColor(255, 255, 255, 14))
        p.setPen(QPen(QColor(255, 255, 255, 36), 1.2))
        p.drawPath(pocket)

        # Costura interior
        stitch = QPen(QColor(255, 255, 255, 38), 1.0, Qt.PenStyle.DashLine)
        stitch.setDashPattern([4, 3])
        p.setPen(stitch)
        p.drawRoundedRect(rect.adjusted(7, 7, -7, -7), 9, 9)

        p.end()
        return pix

    def _on_tick(self, val):
        if self._finished:
            return
        self._progress = float(val)
        if not self._sound_played:
            if (not self.reverse and self._progress >= 0.34) or (self.reverse and self._progress <= 0.72):
                self._sound_played = True
                self._sfx = play_page_turn_sound(self)
        self.update()

    def _on_done(self):
        if self._finished:
            return
        self._finished = True
        self.animation_finished.emit()
        self.hide()
        self.deleteLater()

    def cancel(self):
        """Detiene la animación de apertura/cierre de forma segura sin emitir señales."""
        if self._finished:
            return
        self._finished = True
        try:
            if self._anim is not None:
                self._anim.blockSignals(True)
                self._anim.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    @staticmethod
    def _ease_out_cubic(x: float) -> float:
        return 1.0 - (1.0 - x) ** 3

    @staticmethod
    def _ease_in_out_cubic(x: float) -> float:
        if x < 0.5:
            return 4.0 * x * x * x
        return 1.0 - ((-2.0 * x + 2.0) ** 3) / 2.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        p = self._progress
        half_w = self.board_rect.width() * 0.5
        full_h = self.board_rect.height()
        target_cx = self.board_rect.center().x()
        target_top = self.board_rect.top()

        # 0. Fondo opaco limpio (cross-fade entre la estantería y el escritorio vacío del binder)
        # Esto evita que se vea el binder abierto por detrás durante el vuelo o cierre
        blend = max(0.0, min(1.0, (p - 0.12) / 0.32))
        if self.shelf_pixmap and not self.shelf_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.shelf_pixmap)
        else:
            painter.fillRect(self.rect(), QColor("#fff5f7"))

        if self.pages_bg_pixmap and not self.pages_bg_pixmap.isNull() and blend > 0.005:
            painter.save()
            painter.setOpacity(blend)
            painter.drawPixmap(self.rect(), self.pages_bg_pixmap)
            painter.restore()

        # Sutil viñeta de enfoque cinematográfico durante el movimiento (0 en los extremos p=0 y p=1)
        vignette_alpha = int(55 * math.sin(p * math.pi))
        if vignette_alpha > 2:
            painter.fillRect(self.rect(), QColor(18, 12, 16, vignette_alpha))

        # Posición de la portada cerrada centrada en pantalla antes de abrirse / tras cerrarse
        closed_rect = QRectF(
            target_cx - half_w * 0.5,
            target_top,
            half_w,
            full_h,
        )

        # --- FASE 1 (0.0 -> 0.28): Vuelo de la carpeta cerrada desde/hacia la estantería ---
        if p < 0.28:
            t1 = self._ease_out_cubic(p / 0.28)
            if self.origin_rect and self.origin_rect.width() > 20:
                start_r = self.origin_rect
            else:
                start_r = QRectF(
                    target_cx - half_w * 0.35,
                    target_top + full_h * 0.15,
                    half_w * 0.70,
                    full_h * 0.70,
                )

            cur_r = QRectF(
                start_r.x() + (closed_rect.x() - start_r.x()) * t1,
                start_r.y() + (closed_rect.y() - start_r.y()) * t1,
                start_r.width() + (closed_rect.width() - start_r.width()) * t1,
                start_r.height() + (closed_rect.height() - start_r.height()) * t1,
            )

            # Sombra suave bajo la portada flotante
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(85 * t1 + 20)))
            painter.drawRoundedRect(cur_r.adjusted(6, 10, -4, 4), 14, 14)

            painter.drawPixmap(cur_r, self.cover_pixmap, QRectF(self.cover_pixmap.rect()))
            return

        # --- FASE 2 (0.28 -> 1.0): Apertura / Cierre 3D de la tapa sobre el lomo ---
        t2 = self._ease_in_out_cubic((p - 0.28) / 0.72)
        angle_rad = t2 * math.pi  # 0 -> pi (180°)

        # El lomo se desliza suavemente desde closed_rect.left() hasta target_cx
        spine_x = closed_rect.left() + (target_cx - closed_rect.left()) * t2

        # 1. Mitad derecha del pliego abierto (visible debajo mientras se levanta/cierra la tapa)
        right_dst = QRectF(spine_x, target_top, half_w, full_h)
        sp_w = self.spread_pixmap.width()
        sp_h = self.spread_pixmap.height()
        right_src = QRectF(sp_w * 0.5, 0, sp_w * 0.5, sp_h)
        left_src = QRectF(0, 0, sp_w * 0.5, sp_h)

        # Sombra bajo la mitad derecha
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 65))
        painter.drawRoundedRect(right_dst.adjusted(2, 8, -2, 4), 12, 12)

        painter.drawPixmap(right_dst, self.spread_pixmap, right_src)

        # Sombra interior que la tapa proyecta sobre la página derecha al irse abriendo/cerrando
        if t2 < 0.75:
            cover_shadow_alpha = int(165 * (1.0 - t2 / 0.75))
            sg = QLinearGradient(right_dst.left(), 0, right_dst.right(), 0)
            sg.setColorAt(0.0, QColor(0, 0, 0, cover_shadow_alpha))
            sg.setColorAt(0.7, QColor(0, 0, 0, int(cover_shadow_alpha * 0.45)))
            sg.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(right_dst, sg)

        # 2. Cuando la tapa supera ~72% de apertura, revelar suavemente la página izquierda final
        if t2 > 0.72:
            left_dst = QRectF(spine_x - half_w, target_top, half_w, full_h)
            reveal_alpha = min(1.0, (t2 - 0.72) / 0.28)
            painter.save()
            painter.setOpacity(reveal_alpha)
            painter.drawPixmap(left_dst, self.spread_pixmap, left_src)
            painter.restore()

        # 3. Tapa giratoria en perspectiva 3D (de 0° a 180°)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        outer_x = spine_x + half_w * cos_a
        persp_lift = sin_a * full_h * 0.085

        if abs(outer_x - spine_x) >= 1.2:
            if angle_rad < math.pi * 0.5:
                # Cara exterior (portada del binder)
                dst_poly = QPolygonF([
                    QPointF(spine_x, target_top),
                    QPointF(outer_x, target_top - persp_lift),
                    QPointF(outer_x, target_top + full_h + persp_lift),
                    QPointF(spine_x, target_top + full_h),
                ])
                _draw_quad_pixmap(painter, self.cover_pixmap, QRectF(self.cover_pixmap.rect()), dst_poly)

                # Reflejo de luz deslizándose por la portada al abrirse/cerrarse
                glare_alpha = int(75 * sin_a)
                if glare_alpha > 4:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, glare_alpha))
                    painter.drawPolygon(dst_poly)
            else:
                # Cara interior de la tapa (forro oscuro) que se funde hacia la página izquierda
                lining_opacity = max(0.0, 1.0 - max(0.0, (t2 - 0.72) / 0.26))
                if lining_opacity > 0.02:
                    dst_poly = QPolygonF([
                        QPointF(outer_x, target_top - persp_lift),
                        QPointF(spine_x, target_top),
                        QPointF(spine_x, target_top + full_h),
                        QPointF(outer_x, target_top + full_h + persp_lift),
                    ])
                    painter.save()
                    painter.setOpacity(lining_opacity)
                    _draw_quad_pixmap(
                        painter,
                        self._inner_lining_pix,
                        QRectF(self._inner_lining_pix.rect()),
                        dst_poly,
                    )
                    # Sombra de inclinación
                    shade_alpha = int(90 * sin_a)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(0, 0, 0, shade_alpha))
                    painter.drawPolygon(dst_poly)
                    painter.restore()


def play_sleeve_insert_sound(parent_widget=None):
    """Reproduce un sonido suave de encaje cuando se inserta una carta en una mica."""
    if not _HAS_MULTIMEDIA:
        return None
    wav_path = os.path.join(SOUNDS_DIR, "click.wav")
    if not os.path.exists(wav_path):
        return None
    try:
        sfx = QSoundEffect(parent_widget)
        sfx.setSource(QUrl.fromLocalFile(wav_path))
        sfx.setVolume(0.28)
        sfx.play()
        return sfx
    except Exception:
        return None


class CardSlideInOverlay(QWidget):
    """
    Animación táctil de inserción de carta dentro del bolsillo plástico (Card Slide-In).
    La carta entra desde la ranura superior de la mica deslizándose suavemente hasta encajar,
    con un reflejo de plástico recorriendo el frente y un destello sutil en el borde superior.
    """
    animation_finished = pyqtSignal()

    def __init__(self, slot_widget: QWidget, card_pixmap: QPixmap, reverse: bool = False):
        super().__init__(slot_widget)
        self.setGeometry(slot_widget.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.card_pixmap = card_pixmap
        self.reverse = bool(reverse)
        self._progress = 1.0 if self.reverse else 0.0
        self._sfx = play_sleeve_insert_sound(self)

        self._finished = False
        self.show()
        self.raise_()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(scale_anim_duration(230, min_ms=100))
        if self.reverse:
            self._anim.setStartValue(1.0)
            self._anim.setEndValue(0.0)
            self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        else:
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_tick)
        self._anim.finished.connect(self._on_done)
        self._anim.start()

    def _on_tick(self, val):
        self._progress = float(val)
        self.update()

    def _on_done(self):
        self.animation_finished.emit()
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        if self.card_pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Clip al interior del bolsillo redondeado para que la carta entre o salga desde la ranura superior
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 6.0, 6.0)
        painter.setClipPath(clip_path)

        t = self._progress
        pw = self.card_pixmap.width()
        ph = self.card_pixmap.height()
        target_x = (self.width() - pw) * 0.5
        target_y = (self.height() - ph) * 0.5

        # Deslizar desde arriba (-48% de la altura) hasta su posición centrada (o viceversa si reverse=True)
        offset_factor = 0.58 if self.reverse else 0.48
        start_y = target_y - ph * offset_factor
        cur_y = start_y + (target_y - start_y) * t

        # Sutil fondo oscuro del bolsillo detrás mientras desliza (se atenúa al salir)
        bg_alpha = int(190 * t) if self.reverse else 220
        if bg_alpha > 4:
            painter.fillRect(self.rect(), QColor(22, 22, 28, bg_alpha))

        # Carta deslizándose
        painter.save()
        card_opacity = max(0.0, min(1.0, t if self.reverse else (0.45 + 0.55 * t)))
        painter.setOpacity(card_opacity)
        painter.drawPixmap(QPointF(target_x, cur_y), self.card_pixmap)
        painter.restore()

        # Reflejo translúcido de la mica plástica pasando por encima de la carta
        glare_y = self.height() * (0.15 + 0.70 * t)
        glare_rect = QRectF(0, glare_y - 18, self.width(), 36)
        gg = QLinearGradient(0, glare_rect.top(), 0, glare_rect.bottom())
        alpha_glare = int(75 * math.sin(t * math.pi))
        gg.setColorAt(0.0, QColor(255, 255, 255, 0))
        gg.setColorAt(0.5, QColor(255, 255, 255, alpha_glare))
        gg.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(glare_rect, gg)

        # Borde brillante de la ranura superior de la funda plástica
        lip_alpha = int(160 * (1.0 - t))
        if lip_alpha > 4:
            painter.setPen(QPen(QColor(255, 255, 255, lip_alpha), 1.6))
            painter.drawLine(QPointF(4, 3), QPointF(self.width() - 4, 3))


class _SpreadMinimapPill(QWidget):
    """Miniatura compacta de un pliego (2 páginas) dentro del mini-mapa del binder."""
    clicked = pyqtSignal(int)

    def __init__(self, spread_idx: int, left_ratio: float, right_ratio: float, is_active: bool, parent=None):
        super().__init__(parent)
        self.spread_idx = spread_idx
        self.left_ratio = max(0.0, min(1.0, float(left_ratio)))
        self.right_ratio = max(0.0, min(1.0, float(right_ratio)))
        self.is_active = bool(is_active)
        self._hovered = False

        self.setFixedSize(56, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        p1 = spread_idx * 2 + 1
        p2 = p1 + 1
        self.setToolTip(f"Ir a páginas {p1} - {p2}")

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.spread_idx)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.8, 0.8, self.width() - 1.6, self.height() - 1.6)

        if self.is_active:
            bg = QColor("#f56b7b")
            border = QColor("#d44854")
            txt_color = QColor("#ffffff")
        elif self._hovered:
            bg = QColor("#ffdfe6")
            border = QColor("#f56b7b")
            txt_color = QColor("#5a2a3a")
        else:
            bg = QColor("#ffffff")
            border = QColor("#f2b8c3")
            txt_color = QColor("#5a2a3a")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.4 if self.is_active else 1.0))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        # Números de página (Spread 0 = Portada | 1, Spread >= 1 = 2-3, 4-5, ...)
        if self.spread_idx == 0:
            lbl_txt = "1"
        else:
            p1 = self.spread_idx * 2
            p2 = p1 + 1
            lbl_txt = f"{p1}-{p2}"
        painter.setPen(txt_color)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(self.is_active)
        painter.setFont(font)
        painter.drawText(QRectF(2, 1, self.width() - 4, 15), Qt.AlignmentFlag.AlignCenter, lbl_txt)

        # Dos mini barras de ocupación (página izquierda y página derecha)
        bar_y = self.height() - 6.0
        bar_w = (self.width() - 14.0) * 0.5
        ratios = (0.0, self.right_ratio) if self.spread_idx == 0 else (self.left_ratio, self.right_ratio)
        for idx, ratio in enumerate(ratios):
            bx = 5.0 + idx * (bar_w + 4.0)
            track_color = QColor(255, 255, 255, 75) if self.is_active else QColor("#f3d5dc")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_color)
            painter.drawRoundedRect(QRectF(bx, bar_y, bar_w, 3.0), 1.5, 1.5)
            if ratio > 0.0:
                fill_color = QColor("#fef08a") if self.is_active else QColor("#f56b7b")
                painter.setBrush(fill_color)
                painter.drawRoundedRect(QRectF(bx, bar_y, max(3.0, bar_w * ratio), 3.0), 1.5, 1.5)


_MINIMAP_PAGE_MIME = "application/x-pokebinder-page"


class _SinglePageMovePill(QWidget):
    """Miniatura individual de una hoja (H1, H2, ...) para arrastrar o intercambiar hojas en modo Mover."""
    clicked = pyqtSignal(int)
    swap_requested = pyqtSignal(int, int)

    def __init__(self, page_idx: int, fill_ratio: float, is_visible: bool, is_selected: bool, parent=None):
        super().__init__(parent)
        self.page_idx = int(page_idx)
        self.fill_ratio = max(0.0, min(1.0, float(fill_ratio)))
        self.is_visible = bool(is_visible)
        self.is_selected = bool(is_selected)
        self._hovered = False
        self._drop_hover = False
        self._drag_start = None

        self.setFixedSize(46, 28)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(f"Hoja {self.page_idx + 1} — Arrastra sobre otra hoja o haz clic para intercambiar")

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start is not None and (event.position().toPoint() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
            self._drag_start = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_MINIMAP_PAGE_MIME, str(self.page_idx).encode("utf-8"))
            drag.setMimeData(mime)
            pix = self.grab()
            if not pix.isNull():
                drag.setPixmap(pix)
                drag.setHotSpot(QPoint(pix.width() // 2, pix.height() // 2))
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self.clicked.emit(self.page_idx)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MINIMAP_PAGE_MIME):
            self._drop_hover = True
            self.update()
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_hover = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_hover = False
        self.update()
        if event.mimeData().hasFormat(_MINIMAP_PAGE_MIME):
            try:
                src_page = int(bytes(event.mimeData().data(_MINIMAP_PAGE_MIME)).decode("utf-8"))
            except Exception:
                event.ignore()
                return
            if src_page != self.page_idx:
                self.swap_requested.emit(src_page, self.page_idx)
            event.acceptProposedAction()
            return
        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.8, 0.8, self.width() - 1.6, self.height() - 1.6)

        if self._drop_hover:
            bg = QColor("#e0f2fe")
            border = QColor("#0284c7")
            txt_col = QColor("#0369a1")
        elif self.is_selected:
            bg = QColor("#f59e0b")
            border = QColor("#b45309")
            txt_col = QColor("#ffffff")
        elif self.is_visible:
            bg = QColor("#38bdf8")
            border = QColor("#0284c7")
            txt_col = QColor("#ffffff")
        elif self._hovered:
            bg = QColor("#e0f2fe")
            border = QColor("#38bdf8")
            txt_col = QColor("#0f172a")
        else:
            bg = QColor("#ffffff")
            border = QColor("#94a3b8")
            txt_col = QColor("#334155")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.8 if (self.is_selected or self._drop_hover or self.is_visible) else 1.0))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        painter.setPen(txt_col)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(self.is_visible or self.is_selected)
        painter.setFont(font)
        painter.drawText(QRectF(2, 1, self.width() - 4, 16), Qt.AlignmentFlag.AlignCenter, f"H{self.page_idx + 1}")

        # Barra de ocupación de la hoja
        bar_y = self.height() - 6.0
        bar_w = self.width() - 10.0
        bx = 5.0
        track_col = QColor(255, 255, 255, 90) if (self.is_visible or self.is_selected) else QColor("#e2e8f0")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_col)
        painter.drawRoundedRect(QRectF(bx, bar_y, bar_w, 3.0), 1.5, 1.5)
        if self.fill_ratio > 0.0:
            fill_col = QColor("#fef08a") if (self.is_visible or self.is_selected) else QColor("#0284c7")
            painter.setBrush(fill_col)
            painter.drawRoundedRect(QRectF(bx, bar_y, max(3.0, bar_w * self.fill_ratio), 3.0), 1.5, 1.5)


class BinderPageMinimap(QWidget):
    """
    Tira compacta horizontal de salto rápido de páginas para el Binder (Etapa 3).
    Muestra mini-pliegos con indicador de ocupación de cartas y permite saltar directo con animación 3D,
    o en modo mover hojas muestra H1, H2, ... para arrastrar e intercambiar hojas completas.
    """
    spread_selected = pyqtSignal(int)
    page_swap_requested = pyqtSignal(int, int)
    page_move_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)

        from PyQt6.QtWidgets import QScrollArea
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(32)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._pills_layout = QHBoxLayout(self._container)
        self._pills_layout.setContentsMargins(2, 2, 2, 2)
        self._pills_layout.setSpacing(5)
        self._pills_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self._container)

        outer.addWidget(self.scroll, 1)

    def refresh(
        self,
        current_spread: int,
        page_counts: dict[int, int],
        slots_per_page: int,
        page_move_mode: bool = False,
        selected_move_page: int | None = None,
    ):
        """Reconstruye las miniaturas de pliegos u hojas individuales según ocupación actual."""
        while self._pills_layout.count():
            item = self._pills_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        max_occupied_page = max(page_counts.keys()) if page_counts else 0
        denom = max(1, int(slots_per_page))

        if page_move_mode:
            visible_pages = {0} if current_spread <= 0 else {current_spread * 2 - 1, current_spread * 2}
            total_pages = max(12, max_occupied_page + 4, max(visible_pages) + 2)
            active_pill = None
            for p_idx in range(total_pages):
                ratio = page_counts.get(p_idx, 0) / denom
                pill = _SinglePageMovePill(
                    p_idx,
                    ratio,
                    is_visible=(p_idx in visible_pages),
                    is_selected=(selected_move_page == p_idx),
                )
                pill.clicked.connect(self.page_move_clicked.emit)
                pill.swap_requested.connect(self.page_swap_requested.emit)
                self._pills_layout.addWidget(pill)
                if p_idx in visible_pages and active_pill is None:
                    active_pill = pill
            if active_pill is not None:
                self.scroll.ensureWidgetVisible(active_pill, 40, 0)
            return

        max_occupied_spread = 0 if max_occupied_page == 0 else (max_occupied_page + 1) // 2
        total_spreads = max(6, current_spread + 2, max_occupied_spread + 2)

        active_pill = None
        for s_idx in range(total_spreads):
            if s_idx == 0:
                r1 = 0.0
                r2 = page_counts.get(0, 0) / denom
            else:
                p1 = s_idx * 2 - 1
                p2 = p1 + 1
                r1 = page_counts.get(p1, 0) / denom
                r2 = page_counts.get(p2, 0) / denom
            pill = _SpreadMinimapPill(s_idx, r1, r2, is_active=(s_idx == current_spread))
            pill.clicked.connect(self.spread_selected.emit)
            self._pills_layout.addWidget(pill)
            if s_idx == current_spread:
                active_pill = pill

        if active_pill is not None:
            self.scroll.ensureWidgetVisible(active_pill, 40, 0)
