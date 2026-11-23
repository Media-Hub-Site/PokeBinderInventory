import os
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QToolTip,
    QDialog, QFrame, QScrollArea, QMenu
)
from PyQt6.QtGui import (
    QPixmap, QCursor, QColor, QPainter, QPainterPath, QTransform,
    QRadialGradient, QLinearGradient, QPen, QBrush, QIcon, QAction
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPropertyAnimation, QParallelAnimationGroup,
    QPoint, QPointF, QRect, QRectF, QEasingCurve, QTimer, QDateTime, pyqtProperty
)
from MyQtApp.config import (
    ICONS_DIR, IMAGES_DIR, EXE_DIR, VARIANT_COLOR_MAP,
    normalize_lang_code, normalize_variant_name
)
from MyQtApp.i18n import t, language_manager
from MyQtApp.app.getImgs import (
    get_pixmap_from_zip, get_webp_pixmap, get_hd_pixmap,
    get_card_placeholder_pixmap, HDImageDownloaderThread
)
from MyQtApp.app.price_updater import (
    obtener_precios_carta_bd, SingleCardPriceThread, PRICE_SOURCE_ORDER
)
from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas


class LanguageBadgeLabel(QLabel):
    """Etiqueta distintiva con el idioma de la carta (ej. ES, EN, JA, FR, PT, ZH)."""
    def __init__(self, idioma="es", parent=None):
        super().__init__(parent)
        lang_code = normalize_lang_code(idioma).upper()
        flag_map = {
            "ES": "🇪🇸 ES",
            "EN": "🇬🇧 EN",
            "JA": "🇯🇵 JA",
            "FR": "🇫🇷 FR",
            "PT": "🇵🇹 PT",
            "ZH": "🇨🇳 ZH"
        }
        display_text = flag_map.get(lang_code, f"🌐 {lang_code}")
        self.setText(display_text)
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(15, 23, 42, 0.88);
                color: #f8fafc;
                font-weight: bold;
                font-size: 10px;
                border: 1px solid rgba(56, 189, 248, 0.6);
                border-radius: 4px;
                padding: 1px 5px;
            }
        """)
        self.adjustSize()


def _create_variant_swatch_icon(color_hex: str, border_hex: str) -> QIcon:
    """Crea un ícono cuadrado redondeado con el color de la variante para el menú desplegable."""
    pix = QPixmap(14, 14)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(QPen(QColor(border_hex), 1.5))
    painter.drawRoundedRect(1, 1, 12, 12, 3, 3)
    painter.end()
    return QIcon(pix)


class VariantBadgeButton(QPushButton):

    """Botón/Badge rectangular vertical con menú desplegable para seleccionar la variante de la carta."""
    variant_changed = pyqtSignal(str, str)  # (id_api, nueva_variante)

    def __init__(self, id_api, variante_actual="Normal", parent=None):
        super().__init__(parent)
        self.id_api = id_api
        self.variante_actual = normalize_variant_name(variante_actual)
        self.setFixedSize(14, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_appearance()
        self.clicked.connect(self.open_variant_menu)

    def update_appearance(self):
        self.variante_actual = normalize_variant_name(self.variante_actual)
        info = VARIANT_COLOR_MAP.get(self.variante_actual, VARIANT_COLOR_MAP["Normal"])
        color = info["color"]
        border = info["border"]
        name = info["name"]
        self.setToolTip(f"Variante: {name}\n(Haz clic para elegir variante)")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 1.5px solid {border};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 2px solid #ffffff;
            }}
        """)

    def set_variante(self, variante: str):
        self.variante_actual = normalize_variant_name(variante)
        self.update_appearance()

    def open_variant_menu(self):
        menu = QMenu(self)
        from PyQt6.QtGui import QPalette
        pal = menu.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#e25b70"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        menu.setPalette(pal)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #ffffff;
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 5px 18px 5px 8px;
                border-radius: 5px;
                color: #ffffff;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #e25b70;
                color: #ffffff;
            }
            QMenu::item:checked {
                font-weight: bold;
                color: #ffffff;
                background-color: rgba(242, 156, 164, 0.25);
            }
        """)
        for key, info in VARIANT_COLOR_MAP.items():
            icon = _create_variant_swatch_icon(info["color"], info["border"])
            act = QAction(icon, info["name"], menu)
            act.setCheckable(True)
            act.setChecked(key == self.variante_actual)
            act.triggered.connect(lambda checked=False, v=key: self._select_variant(v))
            menu.addAction(act)

        menu.exec(self.mapToGlobal(QPoint(0, self.height() + 2)))

    def _select_variant(self, nueva_variante: str):
        nueva_variante = normalize_variant_name(nueva_variante)
        if nueva_variante == self.variante_actual:
            return
        self.variante_actual = nueva_variante
        self.update_appearance()
        self.variant_changed.emit(self.id_api, nueva_variante)


class VariantLegendBar(QWidget):
    """Barra horizontal explicativa de los colores de Variantes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(12)

        lbl_title = QLabel("Variantes:", self)
        lbl_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #38bdf8;")
        layout.addWidget(lbl_title)

        for key, info in VARIANT_COLOR_MAP.items():
            item_widget = QWidget(self)
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)

            badge = QLabel(self)
            badge.setFixedSize(10, 18)
            badge.setStyleSheet(f"background-color: {info['color']}; border: 1px solid {info['border']}; border-radius: 3px;")
            
            txt = QLabel(f"{info['name']}", self)
            txt.setStyleSheet("font-size: 11px; color: #f8fafc; font-weight: 500;")

            item_layout.addWidget(badge)
            item_layout.addWidget(txt)
            layout.addWidget(item_widget)

        layout.addStretch()
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 10px;
            }
        """)


class CardItemWidget(QWidget):
    def __init__(self, carta, pixmap, size, variante="Normal", parent=None):
        super().__init__(parent)
        self.carta = carta
        self.id_api = getattr(carta, 'id_api', None)
        self.idioma = getattr(carta, 'idioma', None) or language_manager.current_language
        self.setFixedSize(size[0], size[1])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = ClickableLabel(self.id_api, self)
        self.image_label.setScaledContents(True)
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(size[0], size[1])
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        # Botón rectangular vertical de variante (arriba a la izquierda)
        self.variant_badge = VariantBadgeButton(self.id_api, variante, self)
        self.variant_badge.move(3, 3)
        self.variant_badge.raise_()

        # Botón de información (arriba a la derecha)
        self.info_btn = InfoIconLabel(carta, self)
        self.info_btn.move(size[0] - 26, 3)
        self.info_btn.raise_()

        # Insignia distintiva de idioma (abajo a la izquierda)
        self.lang_badge = LanguageBadgeLabel(self.idioma, self)
        badge_h = self.lang_badge.height()
        self.lang_badge.move(3, size[1] - badge_h - 3)
        self.lang_badge.raise_()

        # Indicador geométrico de rareza apto para daltonismo (abajo a la derecha)
        from MyQtApp.ui.FilterVisualBar import RaritySymbolBadge
        self.rarity_badge = RaritySymbolBadge(getattr(carta, "rarity", None), self)
        self.rarity_badge.move(size[0] - self.rarity_badge.width() - 3, size[1] - self.rarity_badge.height() - 3)
        self.rarity_badge.raise_()

    def set_card_pixmap(self, pixmap: QPixmap):
        """Actualiza la imagen de la carta en vivo (usado tras descarga asíncrona .webp)."""
        if pixmap and not pixmap.isNull():
            self.image_label.setPixmap(pixmap)
            self.variant_badge.raise_()
            self.info_btn.raise_()
            self.lang_badge.raise_()
            if hasattr(self, "rarity_badge") and self.rarity_badge:
                self.rarity_badge.raise_()



class InteractiveCard3DWidget(QWidget):
    """Widget de carta 3D física con canto de grosor, brillo espectral prismático y física de inercia."""

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

        self._front_pixmap = QPixmap()
        self._back_pixmap = QPixmap()
        self._load_back_pixmap()

        self._rot_x = 0.0
        self._rot_y = 0.0
        self._target_rot_x = 0.0
        self._target_rot_y = 0.0
        self._flip_angle = 0.0

        self._card_w = 340
        self._card_h = 476
        self._is_dragging = False

        # Temporizador a 60 FPS para suavizado de inercia y física de masa
        self._physics_timer = QTimer(self)
        self._physics_timer.setInterval(16)
        self._physics_timer.timeout.connect(self._update_physics)
        self._physics_timer.start()

    def _load_back_pixmap(self):
        candidate_paths = [
            os.path.join(ICONS_DIR, "carta.jpg"),
            os.path.join(ICONS_DIR, "carta.png"),
            os.path.join(EXE_DIR, "assets", "card_back.png"),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._back_pixmap = pix
                    return

    def set_card_size(self, w: int, h: int):
        self._card_w = w
        self._card_h = h
        padding = 80
        self.setFixedSize(w + padding * 2, h + padding * 2)
        self.update()

    @pyqtProperty(float)
    def flipAngle(self):
        return self._flip_angle

    @flipAngle.setter
    def flipAngle(self, val):
        self._flip_angle = float(val)
        self.update()

    def set_front_pixmap(self, pixmap: QPixmap):
        self._front_pixmap = pixmap
        self.update()

    def flip_card(self):
        target = 180.0 if self._flip_angle < 90.0 else 0.0
        self.anim_flip = QPropertyAnimation(self, b"flipAngle", self)
        self.anim_flip.setDuration(600)
        self.anim_flip.setStartValue(self._flip_angle)
        self.anim_flip.setEndValue(target)
        self.anim_flip.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim_flip.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._update_tilt_target(event.pos())

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._update_tilt_target(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._target_rot_x = 0.0
            self._target_rot_y = 0.0

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.flip_card()

    def _update_tilt_target(self, pos: QPoint):
        w = max(1, self.width())
        h = max(1, self.height())

        nx = max(-1.0, min(1.0, (pos.x() - w / 2.0) / (w / 2.0)))
        ny = max(-1.0, min(1.0, (pos.y() - h / 2.0) / (h / 2.0)))

        self._target_rot_y = nx * 34.0
        self._target_rot_x = -ny * 34.0

    def _update_physics(self):
        diff_x = self._target_rot_x - self._rot_x
        diff_y = self._target_rot_y - self._rot_y

        if abs(diff_x) > 0.01 or abs(diff_y) > 0.01:
            self._rot_x += diff_x * 0.20
            self._rot_y += diff_y * 0.20
            self.update()
        elif self._rot_x != self._target_rot_x or self._rot_y != self._target_rot_y:
            self._rot_x = self._target_rot_x
            self._rot_y = self._target_rot_y
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        current_flip = self._flip_angle % 360
        is_back = (90.0 <= current_flip <= 270.0)

        pix = self._back_pixmap if is_back else self._front_pixmap
        if not pix or pix.isNull():
            return

        w = float(self.width())
        h = float(self.height())
        cw = float(self._card_w)
        ch = float(self._card_h)
        cx = (w - cw) / 2.0
        cy = (h - ch) / 2.0

        effective_flip = current_flip if not is_back else (current_flip - 180.0)

        # 1. SOMBRA PROYECTADA DINÁMICA (Sin bordes duros)
        shadow_dx = -self._rot_y * 0.75 + 10.0
        shadow_dy = self._rot_x * 0.75 + 16.0

        shadow_transform = QTransform()
        shadow_transform.translate(w / 2.0 + shadow_dx, h / 2.0 + shadow_dy)
        shadow_transform.rotate((self._rot_y + effective_flip) * 0.9, Qt.Axis.YAxis)
        shadow_transform.rotate(self._rot_x * 0.9, Qt.Axis.XAxis)
        shadow_transform.setMatrix(
            shadow_transform.m11(), shadow_transform.m12(), shadow_transform.m13(),
            shadow_transform.m21(), shadow_transform.m22(), shadow_transform.m23(),
            shadow_transform.m31(), shadow_transform.m32(), shadow_transform.m33() - 0.0012
        )
        shadow_transform.translate(-w / 2.0, -h / 2.0)

        painter.setTransform(shadow_transform)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 16, 16)

        # 2. CANTO FÍSICO 3D (Grosor lateral de cartón)
        thickness = 5.0
        for i in range(int(thickness), 0, -1):
            edge_dx = (self._rot_y / 34.0) * i * 0.85
            edge_dy = (-self._rot_x / 34.0) * i * 0.85

            edge_transform = QTransform()
            edge_transform.translate(w / 2.0 + edge_dx, h / 2.0 + edge_dy)
            edge_transform.rotate(self._rot_y + effective_flip, Qt.Axis.YAxis)
            edge_transform.rotate(self._rot_x, Qt.Axis.XAxis)
            edge_transform.setMatrix(
                edge_transform.m11(), edge_transform.m12(), edge_transform.m13(),
                edge_transform.m21(), edge_transform.m22(), edge_transform.m23(),
                edge_transform.m31(), edge_transform.m32(), edge_transform.m33() - 0.0012
            )
            edge_transform.translate(-w / 2.0, -h / 2.0)

            painter.setTransform(edge_transform)
            edge_color = QColor(230, 235, 245) if not is_back else QColor(35, 25, 55)
            painter.setBrush(edge_color)
            painter.setPen(QPen(QColor(15, 23, 42, 140), 1))
            painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 16, 16)

        # 3. CARTA 3D PRINCIPAL CON RECORTE REDONDEADO PERFECTO
        card_transform = QTransform()
        card_transform.translate(w / 2.0, h / 2.0)
        card_transform.rotate(self._rot_y + effective_flip, Qt.Axis.YAxis)
        card_transform.rotate(self._rot_x, Qt.Axis.XAxis)
        card_transform.setMatrix(
            card_transform.m11(), card_transform.m12(), card_transform.m13(),
            card_transform.m21(), card_transform.m22(), card_transform.m23(),
            card_transform.m31(), card_transform.m32(), card_transform.m33() - 0.0012
        )
        card_transform.translate(-w / 2.0, -h / 2.0)

        painter.setTransform(card_transform)

        # Path de esquinas redondeadas impecable
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(cx, cy, cw, ch), 14, 14)

        painter.save()
        painter.setClipPath(clip_path)
        scaled_pix = pix.scaled(int(cw), int(ch), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(int(cx), int(cy), scaled_pix)
        painter.restore()

        # Borde exterior blanco fino alrededor de la carta
        border_pen = QPen(QColor(255, 255, 255, 180), 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 14, 14)

        # 4. CAPA HOLOGRÁFICA PRISMÁTICA (FOIL RAINBOW & SPECULAR GLARE)
        if not is_back:
            tilt_magnitude = (abs(self._rot_x) + abs(self._rot_y)) / 48.0
            tilt_magnitude = min(1.0, tilt_magnitude)

            # Destello radial
            glare_x = cx + (0.5 + (self._rot_y / 70.0)) * cw
            glare_y = cy + (0.5 - (self._rot_x / 70.0)) * ch

            glare_grad = QRadialGradient(glare_x, glare_y, max(cw, ch) * 0.75)
            glare_grad.setColorAt(0.0, QColor(255, 255, 255, int(140 * tilt_magnitude + 30)))
            glare_grad.setColorAt(0.45, QColor(255, 255, 255, int(45 * tilt_magnitude)))
            glare_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

            painter.save()
            painter.setClipPath(clip_path)
            painter.setBrush(glare_grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 14, 14)

            # Arcoíris holográfico reactivo al ángulo (Foil Prismático + Cosmos Sparkles - Etapa 3)
            if tilt_magnitude > 0.03:
                # Banda prismática que se desplaza dinámicamente con la inclinación del cursor
                shift_x = (self._rot_y / 34.0) * cw * 0.85
                shift_y = (-self._rot_x / 34.0) * ch * 0.85
                rainbow_grad = QLinearGradient(
                    cx - cw * 0.25 + shift_x,
                    cy - ch * 0.25 + shift_y,
                    cx + cw * 1.15 + shift_x,
                    cy + ch * 1.15 + shift_y,
                )
                rainbow_grad.setSpread(QLinearGradient.Spread.ReflectSpread)
                alpha = int(88 * tilt_magnitude)
                rainbow_grad.setColorAt(0.00, QColor(236, 72, 153, alpha))
                rainbow_grad.setColorAt(0.20, QColor(56, 189, 248, alpha))
                rainbow_grad.setColorAt(0.40, QColor(74, 222, 128, alpha))
                rainbow_grad.setColorAt(0.60, QColor(250, 204, 21, alpha))
                rainbow_grad.setColorAt(0.80, QColor(168, 85, 247, alpha))
                rainbow_grad.setColorAt(1.00, QColor(244, 114, 182, alpha))

                painter.setBrush(rainbow_grad)
                painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 14, 14)

                # Haz metálico diagonal fino que barre la carta al girarla
                beam_pos = 0.5 + (self._rot_y - self._rot_x) / 95.0
                beam_x = cx + beam_pos * cw
                beam_grad = QLinearGradient(beam_x - cw * 0.22, cy, beam_x + cw * 0.22, cy + ch * 0.35)
                beam_a = int(105 * tilt_magnitude)
                beam_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
                beam_grad.setColorAt(0.5, QColor(255, 255, 255, beam_a))
                beam_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(beam_grad)
                painter.drawRoundedRect(QRectF(cx, cy, cw, ch), 14, 14)

                # Destellos micro-holográficos (Cosmos Holo Sparkles) que brillan al pasar el haz
                sparkles = (
                    (0.18, 0.22), (0.36, 0.16), (0.68, 0.20), (0.82, 0.28),
                    (0.24, 0.38), (0.52, 0.34), (0.76, 0.44), (0.15, 0.54),
                    (0.42, 0.52), (0.64, 0.58), (0.85, 0.62), (0.28, 0.72),
                    (0.55, 0.75), (0.78, 0.80), (0.20, 0.86), (0.48, 0.88),
                )
                for sx_r, sy_r in sparkles:
                    sx = cx + sx_r * cw
                    sy = cy + sy_r * ch
                    dist = abs((sx_r + sy_r * 0.35) - (beam_pos + 0.18))
                    intensity = max(0.0, 1.0 - dist / 0.26) * tilt_magnitude
                    if intensity > 0.18:
                        sp_a = int(235 * intensity)
                        rad = 2.0 + 3.2 * intensity
                        painter.setPen(QPen(QColor(255, 255, 255, sp_a), 1.1))
                        painter.drawLine(QPointF(sx - rad, sy), QPointF(sx + rad, sy))
                        painter.drawLine(QPointF(sx, sy - rad), QPointF(sx, sy + rad))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(255, 255, 255, sp_a))
                        painter.drawEllipse(QPointF(sx, sy), 1.4 * intensity + 0.6, 1.4 * intensity + 0.6)

            painter.restore()


class CardZoomOverlay(QWidget):
    """Overlay de pantalla completa con manipulación interactiva 3D."""
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setObjectName("CardZoomOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGeometry(parent_window.rect())

        self._bg_alpha = 0
        self.setStyleSheet("QWidget#CardZoomOverlay { background-color: rgba(8, 12, 20, 0); }")

        # Contenedor interactivo 3D de la carta (Totalmente transparente sin recuadros negros)
        self.card_3d = InteractiveCard3DWidget(self)

        # Barra de botones de control flotantes
        self.controls_widget = QWidget(self)
        self.controls_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 220);
                border: 1.5px solid rgba(255, 255, 255, 0.2);
                border-radius: 20px;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 230);
                color: #f8fafc;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 12px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
            }
        """)
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(12, 6, 12, 6)
        controls_layout.setSpacing(12)

        self.btn_flip = QPushButton("🔄 Voltear Carta", self.controls_widget)
        self.btn_flip.clicked.connect(self.card_3d.flip_card)
        controls_layout.addWidget(self.btn_flip)

        self.hint_label = QLabel("💡 Arrastra la carta para inclinar en 3D • Doble clic para voltear", self.controls_widget)
        controls_layout.addWidget(self.hint_label)

        self.btn_close = QPushButton("❌ Cerrar", self.controls_widget)
        self.btn_close.clicked.connect(self.close_zoom)
        controls_layout.addWidget(self.btn_close)

        self.controls_widget.adjustSize()

        # Cartel de estado de carga HD
        self.lbl_loading = QLabel("⏳ Cargando carta en HD...", self)
        self.lbl_loading.setStyleSheet("""
            QLabel {
                background-color: rgba(14, 165, 233, 0.90);
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border: 1.5px solid rgba(255, 255, 255, 0.4);
                border-radius: 14px;
                padding: 6px 18px;
            }
        """)
        self.lbl_loading.adjustSize()
        self.lbl_loading.hide()

        self._closing = False
        self.origin_rect = QRect()
        self._opened_timestamp = 0
        self._current_id_api = None

        self.hide()

    @pyqtProperty(int)
    def bgAlpha(self):
        return self._bg_alpha

    @bgAlpha.setter
    def bgAlpha(self, val):
        self._bg_alpha = int(val)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._bg_alpha > 0:
            painter.fillRect(self.rect(), QColor(8, 12, 20, self._bg_alpha))
        super().paintEvent(event)

    def show_zoom(self, pixmap: QPixmap, origin_global_rect: QRect, id_api: str = None, nombre_archivo: str = None, set_id: str = None, number: str = None, idioma: str = None):
        if not self.parent_window or pixmap.isNull():
            return

        self._current_id_api = id_api
        self._opened_timestamp = QDateTime.currentMSecsSinceEpoch()
        self._closing = False
        self.setGeometry(self.parent_window.rect())
        self.show()
        self.raise_()

        # Mostrar indicador flotante "Cargando carta en HD..."
        self.lbl_loading.setText("⏳ Cargando carta en HD...")
        self.lbl_loading.adjustSize()
        lbl_w = self.lbl_loading.width()
        lbl_h = self.lbl_loading.height()
        lbl_x = (self.width() - lbl_w) // 2
        lbl_y = 16
        self.lbl_loading.setGeometry(lbl_x, lbl_y, lbl_w, lbl_h)
        self.lbl_loading.show()

        # Calcular tamaño proporcional enfocado con espacio adecuado para botones
        avail_h = max(300, self.height() - 120)
        max_h = min(int(avail_h * 0.82), 450)
        max_w = int(max_h * (2.5 / 3.5))

        self.card_3d.set_front_pixmap(pixmap)
        self.card_3d.set_card_size(max_w, max_h)

        # Mapear posición de inicio a coordenadas locales de este overlay
        top_left = self.mapFromGlobal(origin_global_rect.topLeft())
        self.origin_rect = QRect(top_left, origin_global_rect.size())

        # Mapear posición de destino centrada (calculando offset de la carta visual)
        total_w = self.card_3d.width()
        total_h = self.card_3d.height()

        visual_card_top = (self.height() - max_h - 40) // 2
        visual_card_left = (self.width() - max_w) // 2

        center_x = visual_card_left - 80
        center_y = visual_card_top - 80

        self.target_rect = QRect(center_x, center_y, total_w, total_h)

        # Posicionar barra de botones abajo centrada sin superponerse con la carta
        ctrl_w = self.controls_widget.sizeHint().width()
        ctrl_h = self.controls_widget.sizeHint().height()
        ctrl_x = (self.width() - ctrl_w) // 2
        ctrl_y = visual_card_top + max_h + 14
        if ctrl_y + ctrl_h > self.height() - 10:
            ctrl_y = self.height() - ctrl_h - 10

        self.controls_widget.setGeometry(ctrl_x, ctrl_y, ctrl_w, ctrl_h)

        self.card_3d.setGeometry(self.origin_rect)
        self.bgAlpha = 0

        # Animación de entrada
        self.anim_geom_in = QPropertyAnimation(self.card_3d, b"geometry", self)
        self.anim_geom_in.setDuration(320)
        self.anim_geom_in.setStartValue(self.origin_rect)
        self.anim_geom_in.setEndValue(self.target_rect)
        self.anim_geom_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_bg_in = QPropertyAnimation(self, b"bgAlpha", self)
        self.anim_bg_in.setDuration(300)
        self.anim_bg_in.setStartValue(0)
        self.anim_bg_in.setEndValue(225)
        self.anim_bg_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.group_in = QParallelAnimationGroup(self)
        self.group_in.addAnimation(self.anim_geom_in)
        self.group_in.addAnimation(self.anim_bg_in)

        def on_in_finished():
            if not self._closing:
                self.bgAlpha = 225
                self.card_3d.setGeometry(self.target_rect)

        self.group_in.finished.connect(on_in_finished)
        self.group_in.start()

        # Iniciar carga/descarga de imagen Full HD (.png) en segundo plano en assets/images_hd
        if id_api:
            card_lang = idioma
            if not card_lang:
                try:
                    session = SessionLocal()
                    c_db = session.query(Cartas).filter(Cartas.id_api == id_api).first()
                    session.close()
                    if c_db and c_db.idioma:
                        card_lang = c_db.idioma
                except Exception:
                    pass

            if not card_lang:
                card_lang = language_manager.current_language

            # 1. Comprobar si ya existe la versión HD en PNG guardada localmente en assets/images_hd
            existing_hd = get_hd_pixmap(id_api, nombre_archivo, card_lang)
            if existing_hd and not existing_hd.isNull():
                self.card_3d.set_front_pixmap(existing_hd)
                if hasattr(self, 'lbl_loading'):
                    self.lbl_loading.hide()
            else:
                # 2. Si no existe en HD, mostrar "Cargando carta en HD..." e iniciar descarga
                if hasattr(self, 'lbl_loading'):
                    self.lbl_loading.setText("⏳ Cargando carta en HD...")
                    self.lbl_loading.adjustSize()
                    lbl_w = self.lbl_loading.width()
                    lbl_h = self.lbl_loading.height()
                    lbl_x = (self.width() - lbl_w) // 2
                    lbl_y = 20
                    self.lbl_loading.setGeometry(lbl_x, lbl_y, lbl_w, lbl_h)
                    self.lbl_loading.show()

                if hasattr(self, 'hd_thread') and self.hd_thread:
                    try:
                        self.hd_thread.image_loaded.disconnect()
                    except Exception:
                        pass

                self.hd_thread = HDImageDownloaderThread(
                    id_api, set_id=set_id, number=number, nombre_archivo=nombre_archivo, idioma=card_lang, parent=None
                )
                self.hd_thread.image_loaded.connect(self._on_hd_loaded)
                self.hd_thread.finished.connect(self.hd_thread.deleteLater)
                self.hd_thread.start()

    def _on_hd_loaded(self, hd_pixmap: QPixmap, returned_id_api: str):
        if self._closing or returned_id_api != self._current_id_api or hd_pixmap.isNull():
            return

        self.card_3d.set_front_pixmap(hd_pixmap)
        if hasattr(self, 'lbl_loading'):
            self.lbl_loading.hide()

    def mousePressEvent(self, event):
        # Ignorar toques/soltadas que ocurran durante el primer toque (350 ms) o en el widget 3d/controles
        if (QDateTime.currentMSecsSinceEpoch() - self._opened_timestamp) < 350:
            return
        if self.card_3d.geometry().contains(event.pos()) or self.controls_widget.geometry().contains(event.pos()):
            return
        self.close_zoom()

    def close_zoom(self):
        if self._closing:
            return
        self._closing = True

        if hasattr(self, 'lbl_loading'):
            self.lbl_loading.hide()

        if hasattr(self, 'hd_thread') and self.hd_thread:
            try:
                self.hd_thread.image_loaded.disconnect()
            except Exception:
                pass

        if hasattr(self, 'group_in') and self.group_in:
            self.group_in.stop()

        # Animación lenta y fluida de regreso (Fade Out)
        self.anim_geom_out = QPropertyAnimation(self.card_3d, b"geometry", self)
        self.anim_geom_out.setDuration(380)
        self.anim_geom_out.setStartValue(self.card_3d.geometry())
        self.anim_geom_out.setEndValue(self.origin_rect)
        self.anim_geom_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_bg_out = QPropertyAnimation(self, b"bgAlpha", self)
        self.anim_bg_out.setDuration(380)
        self.anim_bg_out.setStartValue(self.bgAlpha)
        self.anim_bg_out.setEndValue(0)
        self.anim_bg_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.group_out = QParallelAnimationGroup(self)
        self.group_out.addAnimation(self.anim_geom_out)
        self.group_out.addAnimation(self.anim_bg_out)

        def al_completar():
            self.hide()
            self.deleteLater()

        self.group_out.finished.connect(al_completar)
        self.group_out.start()


class ClickableLabel(QLabel):
    clicked = pyqtSignal(object, str)

    def __init__(self, id_carta, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_carta = id_carta
        self.seleccionada = False
        self._press_pos = None
        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.timeout.connect(self._on_long_press)
        self._is_long_press = False

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_long_press = False
                self._press_pos = event.pos()
                self._press_timer.start(450)
            super().mousePressEvent(event)
        except Exception as e:
            print(f"Error en mousePressEvent: {e}")

    def mouseMoveEvent(self, event):
        try:
            if self._press_timer.isActive() and self._press_pos is not None:
                if (event.pos() - self._press_pos).manhattanLength() > 10:
                    self._press_timer.stop()
            super().mouseMoveEvent(event)
        except Exception as e:
            print(f"Error en mouseMoveEvent: {e}")

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._press_timer.isActive():
                    self._press_timer.stop()
                    self.ejecutar_animacion_burbuja()
                    self.clicked.emit(self, self.id_carta)
                elif self._is_long_press:
                    self._is_long_press = False
            super().mouseReleaseEvent(event)
        except Exception as e:
            print(f"Error en mouseReleaseEvent: {e}")

    def _on_long_press(self):
        self._is_long_press = True
        parent_win = self.window()
        if not parent_win:
            return

        pix = self.pixmap()
        nombre_archivo = None
        set_id = None
        number = None
        idioma = None

        if self.id_carta:
            parent_widget = self.parent()
            carta_obj = getattr(parent_widget, 'carta', None) if parent_widget else None
            nombre = getattr(carta_obj, 'nombre', None)
            idioma = getattr(carta_obj, 'idioma', None)
            if nombre:
                nombre_archivo = nombre.lower().replace(" ", "_")
                set_id = getattr(carta_obj, 'set_id', None)
                number = getattr(carta_obj, 'number', None)
                card_lang = idioma or language_manager.current_language
                hi_pix = get_hd_pixmap(self.id_carta, nombre, card_lang, size=(450, 630))
                if not hi_pix:
                    hi_pix = get_webp_pixmap(self.id_carta, nombre, card_lang, size=(450, 630))
                if not hi_pix:
                    hi_pix = get_pixmap_from_zip(nombre_archivo, size=(450, 630), id_api=self.id_carta)
                if hi_pix:
                    pix = hi_pix
                    pix = hi_pix

        if pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(
                pix, origin_global,
                id_api=self.id_carta,
                nombre_archivo=nombre_archivo,
                set_id=set_id,
                number=number,
                idioma=idioma
            )

    def ejecutar_animacion_burbuja(self):
        parent = self.window()
        if not parent:
            return

        burbuja = QWidget(parent)
        burbuja.setStyleSheet("""
            background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 rgba(255, 255, 255, 220),
                stop:0.5 rgba(243, 200, 209, 130),
                stop:0.8 rgba(255, 182, 193, 60),
                stop:1 rgba(255, 255, 255, 0));
            border: 2px solid rgba(255, 255, 255, 200);
            border-radius: 999px;
        """)

        pos_global = self.mapTo(parent, QPoint(0, 0))
        w = self.width()
        h = self.height()
        centro = QPoint(pos_global.x() + w // 2, pos_global.y() + h // 2)

        tam_inicial = 8
        r_inicial = QRect(centro.x() - tam_inicial // 2, centro.y() - tam_inicial // 2, tam_inicial, tam_inicial)
        burbuja.setGeometry(r_inicial)
        burbuja.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        burbuja.show()

        opacidad = QGraphicsOpacityEffect(burbuja)
        burbuja.setGraphicsEffect(opacidad)

        tam_final = max(w, h) + 30
        r_final = QRect(centro.x() - tam_final // 2, centro.y() - tam_final // 2, tam_final, tam_final)

        anim_geom = QPropertyAnimation(burbuja, b"geometry", self)
        anim_geom.setDuration(350)
        anim_geom.setStartValue(r_inicial)
        anim_geom.setEndValue(r_final)
        anim_geom.setEasingCurve(QEasingCurve.Type.OutQuad)

        anim_opac = QPropertyAnimation(opacidad, b"opacity", self)
        anim_opac.setDuration(350)
        anim_opac.setStartValue(1.0)
        anim_opac.setEndValue(0.0)
        anim_opac.setEasingCurve(QEasingCurve.Type.InQuad)

        grupo = QParallelAnimationGroup(self)
        grupo.addAnimation(anim_geom)
        grupo.addAnimation(anim_opac)

        if not hasattr(self, '_burbujas_activas'):
            self._burbujas_activas = []
        item_ref = (burbuja, opacidad, grupo)
        self._burbujas_activas.append(item_ref)

        def limpiar():
            burbuja.deleteLater()
            if item_ref in self._burbujas_activas:
                self._burbujas_activas.remove(item_ref)

        grupo.finished.connect(limpiar)
        grupo.start()


class CardDetailDialog(QDialog):
    """Ventana de descripción de carta con comparación de precios en múltiples APIs/mercados."""

    prices_updated = pyqtSignal(dict)

    def __init__(self, carta, parent=None):
        super().__init__(parent)
        self.carta = carta
        self.id_api = getattr(carta, 'id_api', '')
        self.idioma = getattr(carta, 'idioma', 'es') or 'es'
        self.nombre = getattr(carta, 'nombre', 'Desconocido')
        self.set_name = getattr(carta, 'set_name', None) or t("No disponible")
        self.set_id = getattr(carta, 'set_id', None) or ""
        self.number = getattr(carta, 'number', None) or t("No disponible")
        self.price_thread = None

        self.setWindowTitle(f"{self.nombre} - {t('Comparación de Precios')}")
        self.setMinimumSize(640, 440)
        self.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QLabel {
                color: #4a1e2e;
            }
            QFrame#CardMetaBox, QFrame#PriceSectionBox {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 12px;
            }
            QFrame#PriceRowCard {
                background-color: #fff9fa;
                border: 1px solid #f2d0d8;
                border-radius: 10px;
            }
            QFrame#PriceRowBest {
                background-color: #f0fdf4;
                border: 1.5px solid #4ade80;
                border-radius: 10px;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(16)

        # --- Columna Izquierda: Imagen y Descripción de la Carta ---
        left_box = QFrame()
        left_box.setObjectName("CardMetaBox")
        left_box.setFixedWidth(235)
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(8)

        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setFixedSize(195, 272)
        pix = get_hd_pixmap(self.id_api, self.nombre, self.idioma, size=(195, 272))
        if not pix:
            pix = get_webp_pixmap(self.id_api, self.nombre, self.idioma, size=(195, 272))
        if not pix:
            pix = get_card_placeholder_pixmap((195, 272), self.nombre)
        img_lbl.setPixmap(pix)
        left_layout.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        lbl_title = QLabel(self.nombre)
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #5a2a3a;")
        left_layout.addWidget(lbl_title)

        set_str = f"{self.set_name} ({self.set_id})" if self.set_id else self.set_name
        meta_lines = [
            (t("ID"), self.id_api),
            (t("Idioma"), self.idioma.upper()),
            (t("Set / Serie:"), set_str),
            (t("Número:"), str(self.number)),
            (t("Tipo"), getattr(carta, 'type', None) or t("No disponible")),
            (t("Rareza"), getattr(carta, 'rarity', None) or t("No disponible")),
        ]
        etapa = getattr(carta, 'stage', None)
        if etapa and etapa not in ("Ninguno", "N/A"):
            meta_lines.append((t("Etapa"), etapa))

        for k, v in meta_lines:
            row_lbl = QLabel(f"<b>{k}:</b> {v}")
            row_lbl.setWordWrap(True)
            row_lbl.setStyleSheet("font-size: 11px; color: #6b3b4b;")
            left_layout.addWidget(row_lbl)

        left_layout.addStretch()
        main_layout.addWidget(left_box)

        # --- Columna Derecha: Comparación Multi-API ---
        right_box = QFrame()
        right_box.setObjectName("PriceSectionBox")
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(10)

        header_row = QHBoxLayout()
        lbl_p_title = QLabel(t("Comparación de Precios de Mercado"))
        lbl_p_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #5a2a3a;")
        header_row.addWidget(lbl_p_title)
        header_row.addStretch()

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #8c5464; font-weight: 600;")
        header_row.addWidget(self.lbl_status)
        right_layout.addLayout(header_row)

        # Resumen comparativo (Promedio / Rango)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("""
            background-color: #fff0f3;
            border: 1px solid #f2c4ce;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 12px;
            font-weight: 600;
            color: #5a2a3a;
        """)
        self.lbl_summary.setWordWrap(True)
        right_layout.addWidget(self.lbl_summary)

        # Contenedor desplazable de tarjetas por fuente API
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.prices_container = QWidget()
        self.prices_layout = QVBoxLayout(self.prices_container)
        self.prices_layout.setContentsMargins(0, 0, 0, 0)
        self.prices_layout.setSpacing(8)
        self.prices_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.prices_container)
        right_layout.addWidget(scroll, 1)

        # Botones inferiores
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_refresh = QPushButton(t("Actualizar precios en vivo"))
        self.btn_refresh.setProperty("class", "pill")
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.fetch_live_prices)
        btn_row.addWidget(self.btn_refresh)

        btn_row.addStretch()

        btn_close = QPushButton(t("Cerrar"))
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 4px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        right_layout.addLayout(btn_row)
        main_layout.addWidget(right_box, 1)

        # Cargar precios guardados en BD y disparar actualización si hay < 2 fuentes
        initial_prices = obtener_precios_carta_bd(self.id_api)
        self.render_prices(initial_prices)
        if len(initial_prices) < 2 and self.id_api:
            self.fetch_live_prices()

    def render_prices(self, prices_map: dict):
        while self.prices_layout.count():
            item = self.prices_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        valid_entries = [
            (src, info)
            for src in (PRICE_SOURCE_ORDER + [k for k in prices_map.keys() if k not in PRICE_SOURCE_ORDER])
            if src in prices_map and (prices_map[src].get("precio_usd", 0) > 0 or prices_map[src].get("precio_original", 0) > 0)
            for info in [prices_map[src]]
        ]

        if not valid_entries:
            base_price = getattr(self.carta, 'price', None)
            if base_price and float(base_price) > 0:
                self.lbl_summary.setText(f"Precio base registrado en BD: ${float(base_price):.2f} USD")
            else:
                self.lbl_summary.setText(t("Sin cotizaciones guardadas aún. Consultando mercados..."))
            lbl_empty = QLabel(t("Presiona 'Actualizar precios en vivo' para consultar TCGPlayer, TCGMatch, PokemonTCG y TCGCSV."))
            lbl_empty.setWordWrap(True)
            lbl_empty.setStyleSheet("font-size: 12px; color: #8c5464; padding: 12px;")
            self.prices_layout.addWidget(lbl_empty)
            return

        usd_values = [info["precio_usd"] for _, info in valid_entries if info.get("precio_usd", 0) > 0]
        min_usd = min(usd_values) if usd_values else 0.0
        max_usd = max(usd_values) if usd_values else 0.0
        avg_usd = sum(usd_values) / len(usd_values) if usd_values else 0.0

        if len(usd_values) >= 2:
            self.lbl_summary.setText(
                f"Fuentes activas: {len(valid_entries)}  |  Promedio: ${avg_usd:.2f} USD  |  Rango: ${min_usd:.2f} - ${max_usd:.2f} USD"
            )
        else:
            self.lbl_summary.setText(f"Fuente activa: {len(valid_entries)}  |  Valor de mercado: ${avg_usd:.2f} USD")

        for src, info in valid_entries:
            is_best = len(usd_values) >= 2 and info.get("precio_usd", 0) == min_usd
            card = QFrame()
            card.setObjectName("PriceRowBest" if is_best else "PriceRowCard")
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(12, 10, 12, 10)
            c_layout.setSpacing(4)

            top = QHBoxLayout()
            lbl_src = QLabel(src)
            lbl_src.setStyleSheet("font-size: 13px; font-weight: bold; color: #3a1a25;")
            top.addWidget(lbl_src)

            variante = info.get("variante") or "market"
            lbl_var = QLabel(variante)
            lbl_var.setStyleSheet(
                "font-size: 10px; font-weight: 600; color: #703043; background: #ffe4eb; "
                "padding: 2px 7px; border-radius: 6px;"
            )
            top.addWidget(lbl_var)

            if is_best:
                lbl_best = QLabel(t("Menor precio"))
                lbl_best.setStyleSheet(
                    "font-size: 10px; font-weight: bold; color: #166534; background: #dcfce7; "
                    "padding: 2px 7px; border-radius: 6px;"
                )
                top.addWidget(lbl_best)

            top.addStretch()

            moneda = info.get("moneda", "USD")
            orig = float(info.get("precio_original") or 0.0)
            usd = float(info.get("precio_usd") or 0.0)
            if moneda == "EUR":
                price_txt = f"€{orig:.2f} EUR  (~${usd:.2f} USD)"
            else:
                price_txt = f"${usd:.2f} USD"

            lbl_price = QLabel(price_txt)
            lbl_price.setStyleSheet("font-size: 14px; font-weight: bold; color: #15803d;")
            top.addWidget(lbl_price)
            c_layout.addLayout(top)

            # Detalle de rango Low / Mid / High si está disponible
            sub_parts = []
            sym = "€" if moneda == "EUR" else "$"
            if info.get("low") is not None:
                sub_parts.append(f"Mín: {sym}{info['low']:.2f}")
            if info.get("mid") is not None:
                sub_parts.append(f"Med: {sym}{info['mid']:.2f}")
            if info.get("high") is not None:
                sub_parts.append(f"Máx: {sym}{info['high']:.2f}")

            if sub_parts:
                lbl_sub = QLabel("   |   ".join(sub_parts))
                lbl_sub.setStyleSheet("font-size: 11px; color: #64748b;")
                c_layout.addWidget(lbl_sub)

            self.prices_layout.addWidget(card)

    def fetch_live_prices(self):
        if self.price_thread and self.price_thread.isRunning():
            return
        self.btn_refresh.setEnabled(False)
        self.lbl_status.setText(t("Consultando mercados en vivo..."))

        self.price_thread = SingleCardPriceThread(
            self.id_api,
            idioma=self.idioma,
            card_name=self.nombre,
            set_name=self.set_name,
            number=self.number,
            parent=self,
        )
        self.price_thread.prices_loaded.connect(self._on_prices_loaded)
        self.price_thread.error.connect(self._on_prices_error)
        self.price_thread.start()

    def _on_prices_loaded(self, returned_id: str, precios: dict):
        self.btn_refresh.setEnabled(True)
        if precios:
            self.lbl_status.setText(f"{len(precios)} mercados actualizados")
            merged = obtener_precios_carta_bd(self.id_api)
            merged.update(precios)
            self.render_prices(merged)
            self.prices_updated.emit(merged)
        else:
            self.lbl_status.setText(t("Sin precios nuevos en línea"))

    def _on_prices_error(self, err_msg: str):
        self.btn_refresh.setEnabled(True)
        self.lbl_status.setText(t("Error de conexión"))


class InfoIconLabel(QLabel):
    def __init__(self, carta, parent=None):
        super().__init__(parent)
        self.carta = carta
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        info_icon_path = os.path.join(ICONS_DIR, "info.png")
        if os.path.exists(info_icon_path):
            pix = QPixmap(info_icon_path).scaled(
                16, 16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pix)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.setText("i")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("""
            QLabel {
                background-color: rgba(15, 23, 42, 220);
                border: 1.5px solid rgba(56, 189, 248, 200);
                border-radius: 12px;
                padding: 2px;
            }
            QLabel:hover {
                background-color: rgba(56, 189, 248, 240);
                border: 1.5px solid #ffffff;
            }
        """)

        self.tooltip_html = self.build_tooltip_html(carta)
        self.setToolTip(self.tooltip_html)

    def build_tooltip_html(self, carta, preloaded_prices: dict = None):
        nombre = getattr(carta, 'nombre', 'Desconocido')
        id_api = getattr(carta, 'id_api', 'N/A')
        price = getattr(carta, 'price', None)
        precio_fmt = f"${price:.2f} USD" if (price is not None and price > 0) else t("No disponible")
        tipo = getattr(carta, 'type', None) or t("No disponible")
        set_nombre = getattr(carta, 'set_name', None) or t("No disponible")
        set_id = getattr(carta, 'set_id', None) or ""
        set_str = f"{set_nombre} ({set_id})" if set_id else set_nombre
        numero = getattr(carta, 'number', None) or t("No disponible")
        rareza = getattr(carta, 'rarity', None) or t("No disponible")
        etapa = getattr(carta, 'stage', None) or t("No disponible")
        edicion = getattr(carta, 'edition', None) or t("No disponible")
        entrenador = getattr(carta, 'trainer', None) or t("No disponible")
        especial = getattr(carta, 'especial_type', None) or t("No disponible")

        lbl_tipo = t("Tipo")
        lbl_set = t("Set / Serie:")
        lbl_num = t("Número:")
        lbl_rar = t("Rareza")
        lbl_eta = t("Etapa")
        lbl_pre = t("Precio mercado:")
        lbl_esp = t("Especial")
        lbl_ent = t("Entrenador")
        lbl_edi = t("Edición")

        # Consultar precios multi-API almacenados en BD
        multi_prices = preloaded_prices if preloaded_prices is not None else (
            obtener_precios_carta_bd(id_api) if id_api and id_api != 'N/A' else {}
        )

        price_rows_html = ""
        if multi_prices:
            ordered = [s for s in PRICE_SOURCE_ORDER if s in multi_prices] + [
                s for s in multi_prices.keys() if s not in PRICE_SOURCE_ORDER
            ]
            for src in ordered:
                p_info = multi_prices[src]
                moneda = p_info.get("moneda", "USD")
                usd = float(p_info.get("precio_usd") or 0.0)
                orig = float(p_info.get("precio_original") or 0.0)
                if usd <= 0 and orig <= 0:
                    continue
                val_str = f"€{orig:.2f} (~${usd:.2f})" if moneda == "EUR" else f"${usd:.2f} USD"
                price_rows_html += (
                    f"<tr>"
                    f"<td style='color: #94a3b8; padding-right: 10px;'><b>{src}:</b></td>"
                    f"<td style='color: #4ade80; font-size: 12px; font-weight: bold;'>{val_str}</td>"
                    f"</tr>"
                )
        if not price_rows_html:
            price_rows_html = (
                f"<tr>"
                f"<td style='color: #94a3b8; padding-right: 10px; padding-top: 4px;'><b>{lbl_pre}</b></td>"
                f"<td style='color: #4ade80; font-size: 13px; font-weight: bold; padding-top: 4px;'>{precio_fmt}</td>"
                f"</tr>"
            )

        html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; min-width: 240px; padding: 4px; color: #f8fafc;">
            <div style="font-size: 14px; font-weight: bold; color: #38bdf8; margin-bottom: 4px; border-bottom: 2px solid #0284c7; padding-bottom: 4px;">
                {nombre}
            </div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">
                ID: <span style="color: #cbd5e1;">{id_api}</span>
            </div>
            <table style="width: 100%; border-spacing: 0px 4px; font-size: 12px;">
                <tr>
                    <td style="color: #94a3b8; padding-right: 10px;"><b>{lbl_tipo}:</b></td>
                    <td style="color: #f8fafc; font-weight: 500;">{tipo}</td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding-right: 10px;"><b>{lbl_set}</b></td>
                    <td style="color: #f8fafc;">{set_str}</td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding-right: 10px;"><b>{lbl_num}</b></td>
                    <td style="color: #f8fafc;">{numero}</td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding-right: 10px;"><b>{lbl_rar}:</b></td>
                    <td style="color: #f8fafc;">{rareza}</td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding-right: 10px;"><b>{lbl_eta}:</b></td>
                    <td style="color: #f8fafc;">{etapa}</td>
                </tr>
                {"<tr><td style='color: #94a3b8; padding-right: 10px;'><b>" + lbl_esp + ":</b></td><td style='color: #f8fafc;'>" + especial + "</td></tr>" if especial not in ("Normal", "N/A", "Ninguno") else ""}
                {"<tr><td style='color: #94a3b8; padding-right: 10px;'><b>" + lbl_ent + ":</b></td><td style='color: #f8fafc;'>" + entrenador + "</td></tr>" if entrenador not in ("Desconocido", "N/A", "Ninguno") else ""}
                {"<tr><td style='color: #94a3b8; padding-right: 10px;'><b>" + lbl_edi + ":</b></td><td style='color: #f8fafc;'>" + edicion + "</td></tr>" if edicion not in ("Ninguno", "N/A") else ""}
                <tr><td colspan="2" style="border-top: 1px solid #334155; padding-top: 4px; color: #38bdf8; font-size: 11px; font-weight: bold;">Precios de Mercado</td></tr>
                {price_rows_html}
            </table>
            <div style="font-size: 10px; color: #94a3b8; margin-top: 6px; border-top: 1px solid #1e293b; padding-top: 4px;">
                Haz clic para comparar precios en vivo
            </div>
        </div>
        """
        return html.strip()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QToolTip.hideText()
            dlg = CardDetailDialog(self.carta, parent=self.window())

            def on_updated(precios):
                self.tooltip_html = self.build_tooltip_html(self.carta, preloaded_prices=precios)
                self.setToolTip(self.tooltip_html)

            dlg.prices_updated.connect(on_updated)
            dlg.exec()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        # Refrescar tooltip desde BD por si se actualizaron precios recientemente
        self.tooltip_html = self.build_tooltip_html(self.carta)
        self.setToolTip(self.tooltip_html)
        pos = QCursor.pos()
        pos.setX(pos.x() + 12)
        pos.setY(pos.y() + 12)
        QToolTip.showText(pos, self.tooltip_html, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)




