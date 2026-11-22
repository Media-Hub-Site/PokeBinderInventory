import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, 
    QGridLayout, QFrame, QPushButton, QApplication, QSizePolicy,
    QStackedWidget, QGraphicsOpacityEffect, QLineEdit, QComboBox,
    QDialog, QMessageBox, QColorDialog
)
from PyQt6.QtCore import Qt, QMimeData, QPoint, QPointF, QSize, QEasingCurve, QPropertyAnimation, QRect, QRectF, QTimer
from PyQt6.QtGui import QDrag, QPixmap, QCursor, QAction, QPainter, QLinearGradient, QColor, QPen, QShortcut, QKeySequence
from sqlalchemy import func

from MyQtApp.config import ASSETS_DIR, IMAGES_DIR, BINDER_DATA_FILE
from ..session import SessionLocal
from ..models import Cartas, UsuarioCarta
from ..app.getImgs import get_pixmap_from_zip, get_webp_pixmap, get_card_placeholder_pixmap
from ..app.price_updater import (
    obtener_precios_multiples_cartas_bd,
    PriceUpdaterThread,
    PRICE_SOURCE_ORDER,
)
from MyQtApp.i18n import t, language_manager
from MyQtApp.ui.CardWidget import CardZoomOverlay, VariantBadgeButton, LanguageBadgeLabel, InfoIconLabel
from MyQtApp.ui.BinderCoverWidget import BinderCoverWidget, BINDER_DESIGNS, resolve_design_key
from MyQtApp.ui.BinderBookAnimations import (
    BinderSpreadFrame,
    PageFlipAnimationOverlay,
    BinderOpenAnimationOverlay,
    CardSlideInOverlay,
    BinderPageMinimap,
    render_transparent_cover_pixmap,
)
from MyQtApp.ui.toast import show_toast


# --- CONSTANTS & CONFIGURATION ---

BINDER_MODES = {
    "2x2": {
        "rows": 2,
        "cols": 2,
        "slot_w": 130,
        "slot_h": 180,
        "card_w": 120,
        "card_h": 170
    },
    "3x3": {
        "rows": 3,
        "cols": 3,
        "slot_w": 110,
        "slot_h": 155,
        "card_w": 100,
        "card_h": 145
    },
    "3x4": {
        "rows": 3,
        "cols": 4,
        "slot_w": 85,
        "slot_h": 120,
        "card_w": 75,
        "card_h": 105
    },
    "4x4": {
        "rows": 4,
        "cols": 4,
        "slot_w": 85,
        "slot_h": 120,
        "card_w": 75,
        "card_h": 105
    }
}

class DraggableCardLabel(QLabel):
    def __init__(self, id_api, nombre_archivo, pixmap, parent=None):
        super().__init__(parent)
        self.id_api = id_api
        self.nombre_archivo = nombre_archivo
        self.drag_start_position = QPoint()
        self.setPixmap(pixmap)
        self.setScaledContents(True)
        self.setFixedSize(100, 140)  # Adjust size as needed
        self.setStyleSheet("border: 1px solid #ddd; border-radius: 5px;")
        
        self.long_press_timer = QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._on_long_press)

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start_position = event.pos()
                self.long_press_timer.start(260)
            super().mousePressEvent(event)
        except Exception as e:
            print(f"Error en DraggableCardLabel mousePressEvent: {e}")

    def mouseMoveEvent(self, event):
        try:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return
            if getattr(self, 'drag_start_position', None) and (event.pos() - self.drag_start_position).manhattanLength() >= QApplication.startDragDistance():
                self.long_press_timer.stop()

                drag = QDrag(self)
                mime_data = QMimeData()
                
                # Pass card ID and source info
                mime_data.setText(self.id_api)
                mime_data.setProperty("source", "inventory")
                mime_data.setProperty("nombre_archivo", self.nombre_archivo)
                mime_data.setProperty("idioma", getattr(self, "idioma", "en") or "en")
                drag.setMimeData(mime_data)

                # Set drag pixmap
                if self.pixmap() and not self.pixmap().isNull():
                    drag.setPixmap(self.pixmap().scaled(80, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                drag.setHotSpot(event.pos())

                drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        except Exception as e:
            print(f"Error en DraggableCardLabel mouseMoveEvent: {e}")

    def mouseReleaseEvent(self, event):
        try:
            if self.long_press_timer.isActive():
                self.long_press_timer.stop()
            super().mouseReleaseEvent(event)
        except Exception as e:
            print(f"Error en DraggableCardLabel mouseReleaseEvent: {e}")


    def _on_long_press(self):
        parent_win = self.window()
        pix = self.pixmap()
        idioma = getattr(self, 'idioma', None)
        if not idioma and self.id_api:
            try:
                session = SessionLocal()
                c_db = session.query(Cartas).filter(Cartas.id_api == self.id_api).first()
                session.close()
                if c_db and c_db.idioma:
                    idioma = c_db.idioma
            except Exception:
                pass

        card_lang = idioma or language_manager.current_language
        if self.nombre_archivo:
            hi_pix = get_webp_pixmap(self.id_api, self.nombre_archivo, card_lang, size=(450, 630))
            if not hi_pix:
                hi_pix = get_pixmap_from_zip(self.nombre_archivo, size=(450, 630), id_api=self.id_api)
            if hi_pix:
                pix = hi_pix
        if parent_win and pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(pix, origin_global, id_api=self.id_api, nombre_archivo=self.nombre_archivo, idioma=idioma)

class BinderSlot(QLabel):
    def __init__(self, page_index, slot_index, parent=None, binder_view=None, slot_w=120, slot_h=170, card_w=110, card_h=160):
        super().__init__(parent)
        self.page_index = page_index
        self.slot_index = slot_index
        self.binder_view = binder_view
        self.id_api = None
        self.nombre_archivo = None
        self.idioma = None
        self.variante = "Normal"
        self.selected = False
        self.slot_w = slot_w
        self.slot_h = slot_h
        self.card_w = card_w
        self.card_h = card_h
        self.drag_start_position = QPoint()
        self.variant_badge = None
        self.lang_badge = None
        self.info_btn = None
        self.carta_obj = None
        
        self.setFixedSize(slot_w, slot_h)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.update_style()

        self.long_press_timer = QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._on_long_press)

    def set_selected(self, val: bool):
        if not self.id_api:
            self.selected = False
        else:
            self.selected = val
        self.update_style()
        if self.binder_view and hasattr(self.binder_view, 'update_selection_state'):
            self.binder_view.update_selection_state()

    def _on_long_press(self):
        if not self.id_api:
            return
        parent_win = self.window()
        pix = self.pixmap()
        idioma = getattr(self, 'idioma', None)
        if not idioma and self.id_api:
            try:
                session = SessionLocal()
                c_db = session.query(Cartas).filter(Cartas.id_api == self.id_api).first()
                session.close()
                if c_db and c_db.idioma:
                    idioma = c_db.idioma
            except Exception:
                pass

        card_lang = idioma or language_manager.current_language
        if self.nombre_archivo:
            hi_pix = get_webp_pixmap(self.id_api, self.nombre_archivo, card_lang, size=(450, 630))
            if not hi_pix:
                hi_pix = get_pixmap_from_zip(self.nombre_archivo, size=(450, 630), id_api=self.id_api)
            if hi_pix:
                pix = hi_pix
        if parent_win and pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(pix, origin_global, id_api=self.id_api, nombre_archivo=self.nombre_archivo, idioma=idioma)

    def update_style(self):
        if self.id_api:
            if self.selected:
                self.setStyleSheet("""
                    QLabel {
                        background-color: rgba(225, 29, 72, 0.28);
                        border: 3px solid #f43f5e;
                        border-radius: 7px;
                    }
                """)
            else:
                self.setStyleSheet("""
                    QLabel {
                        background-color: rgba(255, 255, 255, 0.04);
                        border: 1.5px solid rgba(255, 255, 255, 0.22);
                        border-radius: 7px;
                    }
                """)
        else:
            self.selected = False
            self.setStyleSheet("""
                QLabel {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1.5px dashed rgba(255, 255, 255, 0.22);
                    border-radius: 7px;
                }
                QLabel:hover {
                    background-color: rgba(255, 255, 255, 0.11);
                    border: 1.5px dashed rgba(244, 143, 177, 0.70);
                }
            """)
            self.clear()

    def set_card(self, id_api, nombre_archivo, pixmap, idioma=None, variante="Normal", carta=None, animate_insert=False):
        self.id_api = id_api
        self.nombre_archivo = nombre_archivo
        self.idioma = idioma
        self.variante = variante or "Normal"
        self.carta_obj = carta
        self.selected = False
        scaled_pix = None
        if pixmap:
            scaled_pix = pixmap.scaled(
                self.card_w, self.card_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled_pix)

        # Botón vertical de variante (arriba a la izquierda)
        if not self.variant_badge:
            self.variant_badge = VariantBadgeButton(self.id_api, self.variante, self)
            self.variant_badge.variant_changed.connect(self._on_slot_variant_changed)
        else:
            self.variant_badge.id_api = self.id_api
            self.variant_badge.set_variante(self.variante)
        self.variant_badge.move(3, 3)

        # Burbuja de información de la carta (arriba a la derecha, Issue #17)
        if self.info_btn:
            self.info_btn.deleteLater()
            self.info_btn = None
        if carta is not None:
            self.info_btn = InfoIconLabel(carta, self)
            self.info_btn.move(self.slot_w - 26, 3)

        # Insignia de idioma (abajo a la izquierda)
        if self.idioma:
            if not self.lang_badge:
                self.lang_badge = LanguageBadgeLabel(self.idioma, self)
            else:
                self.lang_badge.setText(self.idioma)
            bh = self.lang_badge.height()
            self.lang_badge.move(3, self.slot_h - bh - 3)
        elif self.lang_badge:
            self.lang_badge.hide()

        self.apply_details_visibility()
        self.update_style()

        # Animación táctil de inserción en mica (Card Slide-In) al soltar carta
        if animate_insert and scaled_pix and not scaled_pix.isNull():
            from MyQtApp.config import load_settings
            if load_settings().get("animaciones", True):
                if getattr(self, "_slide_overlay", None):
                    try:
                        self._slide_overlay.deleteLater()
                    except Exception:
                        pass
                overlay = CardSlideInOverlay(self, scaled_pix)
                self._slide_overlay = overlay
                def _on_slide_done():
                    self._slide_overlay = None
                    self.apply_details_visibility()
                overlay.animation_finished.connect(_on_slide_done)

    def apply_details_visibility(self):
        """Muestra u oculta variante, burbuja de info e idioma según el toggle 'Ver detalles' (Issue #17)."""
        show_details = bool(self.id_api and getattr(self.binder_view, "show_card_details", False))
        if self.variant_badge:
            if show_details:
                self.variant_badge.show()
                self.variant_badge.raise_()
            else:
                self.variant_badge.hide()
        if self.info_btn:
            if show_details:
                self.info_btn.show()
                self.info_btn.raise_()
            else:
                self.info_btn.hide()
        if self.lang_badge:
            if show_details and self.idioma:
                self.lang_badge.show()
                self.lang_badge.raise_()
            else:
                self.lang_badge.hide()

    def _on_slot_variant_changed(self, id_api, nueva_variante):
        self.variante = nueva_variante
        if self.binder_view and hasattr(self.binder_view, 'update_slot_variant'):
            self.binder_view.update_slot_variant(self.page_index, self.slot_index, nueva_variante)

    def clear_card(self):
        self.id_api = None
        self.nombre_archivo = None
        self.idioma = None
        self.variante = "Normal"
        self.carta_obj = None
        self.selected = False
        if self.variant_badge:
            self.variant_badge.hide()
        if self.info_btn:
            self.info_btn.hide()
        if self.lang_badge:
            self.lang_badge.hide()
        self.clear()
        self.update_style()


    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        try:
            card_id = event.mimeData().text()
            source = event.mimeData().property("source")
            source_slot = event.mimeData().property("source_slot")
            nombre_archivo = event.mimeData().property("nombre_archivo")
            idioma = event.mimeData().property("idioma")
            
            if card_id:
                # Tell the main view to handle the drop (update logic and UI)
                if self.binder_view:
                    self.binder_view.handle_drop(
                        self.page_index, self.slot_index, card_id, 
                        source_slot=source_slot, nombre_archivo=nombre_archivo, idioma=idioma
                    )
                event.accept()
        except Exception as e:
            print(f"Error en BinderSlot dropEvent: {e}")
     
    # Allow dragging FROM the slot too
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.id_api:
                self.drag_start_position = event.pos()
                self.long_press_timer.start(260)
        except Exception as e:
            print(f"Error en BinderSlot mousePressEvent: {e}")

    def mouseMoveEvent(self, event):
        try:
            if not self.id_api:
                return
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return
            if getattr(self, 'drag_start_position', None) and (event.pos() - self.drag_start_position).manhattanLength() >= QApplication.startDragDistance():
                self.long_press_timer.stop()

                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setText(self.id_api)
                mime_data.setProperty("source", "binder")
                mime_data.setProperty("source_slot", f"{self.page_index}_{self.slot_index}")
                mime_data.setProperty("nombre_archivo", self.nombre_archivo)
                mime_data.setProperty("idioma", getattr(self, "idioma", "en") or "en")
                drag.setMimeData(mime_data)
                
                if self.pixmap() and not self.pixmap().isNull():
                    drag.setPixmap(self.pixmap().scaled(80, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    drag.setHotSpot(event.pos())
                
                drag.exec(Qt.DropAction.CopyAction)
        except Exception as e:
            print(f"Error en BinderSlot mouseMoveEvent: {e}")


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.long_press_timer.isActive():
                self.long_press_timer.stop()
                if self.id_api:
                    self.set_selected(not self.selected)
        super().mouseReleaseEvent(event)


class InventorySidebar(QWidget):
    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header Title
        self.header = QLabel(t("Colección"))
        self.header.setStyleSheet(
            "font-weight: bold; color: #5a2a3a; font-size: 15px;"
            " border: none; background: transparent;"
        )
        layout.addWidget(self.header)

        # 1. Buscador (usa clase SearchInput del QSS global)
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        self.buscador.setProperty("class", "SearchInput")
        self.timer_busqueda = QTimer()
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(300)
        self.timer_busqueda.timeout.connect(self.load_cards)
        self.buscador.textChanged.connect(lambda: self.timer_busqueda.start())
        layout.addWidget(self.buscador)

        # 2. Botón Filtros (usa clase BinderNavBtn del QSS global)
        self.btn_toggle_filtros = QPushButton("Filtros")
        self.btn_toggle_filtros.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_filtros.setProperty("class", "BinderNavBtn")
        self.btn_toggle_filtros.clicked.connect(self.toggle_filters_panel)
        layout.addWidget(self.btn_toggle_filtros)

        # 3. Panel desplegable de filtros
        self.filters_panel = QWidget()
        self.filters_panel.setObjectName("binder_filters_panel")
        self.filters_panel.setStyleSheet("""
            QWidget#binder_filters_panel {
                background-color: #fff0f3;
                border: 1.5px solid #f2c4ce;
                border-radius: 10px;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: #703043;
                border: none;
                background: transparent;
            }
            QComboBox {
                background-color: white;
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 3px 8px;
                font-size: 12px;
                min-height: 30px;
            }
        """)
        self.filters_panel.setVisible(False)

        panel_layout = QVBoxLayout(self.filters_panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(6)

        self.filtros = {}
        campos = {
            "Idioma": "idioma",
            "Rareza": "rarity",
            "Tipo": "type",
            "Edición": "edition",
            "Etapa": "stage",
            "Entrenador": "trainer",
            "Especial": "especial_type"
        }

        for label_text, col_name in campos.items():
            lbl = QLabel(label_text)
            panel_layout.addWidget(lbl)
            combo = QComboBox()
            combo.addItem("Todos")
            self.filtros[col_name] = combo
            panel_layout.addWidget(combo)

        # Botón Aplicar (usa clase pill del QSS global)
        self.btn_aplicar_filtros = QPushButton("Aplicar Filtros")
        self.btn_aplicar_filtros.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_aplicar_filtros.setProperty("class", "pill")
        self.btn_aplicar_filtros.clicked.connect(self.load_cards)
        panel_layout.addWidget(self.btn_aplicar_filtros)

        layout.addWidget(self.filters_panel)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #fff7f8; border: none;")

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.cargar_opciones_filtros()
        self.load_cards()

    def retranslate_ui(self):
        self.header.setText(t("Colección"))
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        if hasattr(self, 'btn_aplicar_filtros'):
            self.btn_aplicar_filtros.setText(t('Aplicar'))


    def toggle_filters_panel(self):
        visible = not self.filters_panel.isVisible()
        self.filters_panel.setVisible(visible)
        if visible:
            self.btn_toggle_filtros.setText("Ocultar Filtros")
        else:
            self.btn_toggle_filtros.setText("Filtros")

    def cargar_opciones_filtros(self):
        session = SessionLocal()
        try:
            for col_name, combo in self.filtros.items():
                combo.clear()
                combo.addItem("Todos")
                valores = (
                    session.query(getattr(Cartas, col_name))
                    .join(UsuarioCarta, Cartas.id_api == UsuarioCarta.carta_id)
                    .filter(UsuarioCarta.usuario_nombre == self.usuario)
                    .filter(getattr(Cartas, col_name).isnot(None))
                    .distinct()
                    .all()
                )
                sorted_vals = sorted(v[0] for v in valores if v[0])
                for val in sorted_vals:
                    combo.addItem(val)
        finally:
            session.close()

    def _create_card_row_widget(self, id_api, map_idiomas):
        idiomas_disponibles = list(map_idiomas.keys())
        if not idiomas_disponibles:
            return None

        lang_upper_map = {"es": "ES", "en": "EN", "ja": "JA", "fr": "FR", "pt": "PT", "zh": "ZH", "zh-tw": "ZH"}
        flag_emoji_map = {"es": "🇪🇸", "en": "🇬🇧", "ja": "🇯🇵", "fr": "🇫🇷", "pt": "🇵🇹", "zh": "🇨🇳", "zh-tw": "🇨🇳"}

        item_container = QWidget()
        item_layout = QHBoxLayout(item_container)
        item_layout.setContentsMargins(4, 2, 4, 2)
        item_layout.setSpacing(8)

        lang_badge_btn = QPushButton()
        lang_badge_btn.setFixedWidth(44)
        lang_badge_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        first_lang = idiomas_disponibles[0]
        first_carta = map_idiomas[first_lang]
        nombre_archivo = first_carta.nombre.lower().replace(" ", "_")

        pixmap = get_webp_pixmap(id_api, first_carta.nombre, first_lang, size=(100, 140))
        if not pixmap:
            pixmap = get_pixmap_from_zip(nombre_archivo, size=(100, 140), id_api=id_api)
        if not pixmap:
            ruta_alt = os.path.join(IMAGES_DIR, f"{nombre_archivo}_{id_api}.webp")
            if os.path.exists(ruta_alt):
                pixmap = QPixmap(ruta_alt)
        if not pixmap or pixmap.isNull():
            pixmap = get_card_placeholder_pixmap((100, 140), first_carta.nombre)

        card_lbl = DraggableCardLabel(id_api, nombre_archivo, pixmap)
        card_lbl.idioma = first_lang

        state = {
            "index": 0,
            "idiomas": idiomas_disponibles
        }

        def update_display(idx_val):
            state["index"] = idx_val
            current_l = state["idiomas"][idx_val]
            c_obj = map_idiomas[current_l]
            n_arch = c_obj.nombre.lower().replace(" ", "_")

            l_upper = lang_upper_map.get(current_l.lower(), current_l.upper())
            f_emoji = flag_emoji_map.get(current_l.lower(), "🌐")

            if len(state["idiomas"]) > 1:
                lang_badge_btn.setText(f"{l_upper} 🔄\n{f_emoji}")
                lang_badge_btn.setToolTip(f"Idioma actual: {l_upper}\n(Haz clic para cambiar entre idiomas en tu colección)")
            else:
                lang_badge_btn.setText(f"{l_upper}\n{f_emoji}")
                lang_badge_btn.setToolTip(f"Idioma disponible: {l_upper}")

            lang_badge_btn.setStyleSheet("""
                QPushButton {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f43f5e, stop:1 #e11d48);
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1.5px solid #fda4af;
                    border-radius: 8px;
                    padding: 4px 2px;
                }
                QPushButton:hover {
                    background-color: #be123c;
                    border-color: #ffffff;
                }
            """)

            pix = get_webp_pixmap(id_api, c_obj.nombre, current_l, size=(100, 140))
            if not pix:
                pix = get_pixmap_from_zip(n_arch, size=(100, 140), id_api=id_api)
            if not pix:
                r_alt = os.path.join(IMAGES_DIR, f"{n_arch}_{id_api}.webp")
                if os.path.exists(r_alt):
                    pix = QPixmap(r_alt)
            if not pix or pix.isNull():
                pix = get_card_placeholder_pixmap((100, 140), c_obj.nombre)

            if pix and not pix.isNull():
                card_lbl.setPixmap(pix)

            card_lbl.idioma = current_l
            card_lbl.nombre_archivo = n_arch
            price_val = f"${c_obj.price:.2f}" if (c_obj.price and c_obj.price > 0) else "N/A"
            card_lbl.setToolTip(f"<b>{c_obj.nombre}</b> [{f_emoji}]<br/>ID: {id_api}<br/>Idioma: {l_upper}<br/>Tipo: {c_obj.type or 'N/A'}<br/>Rareza: {c_obj.rarity or 'N/A'}<br/>Precio: {price_val} USD")

        def cycle_language(checked=False):
            if len(state["idiomas"]) > 1:
                next_idx = (state["index"] + 1) % len(state["idiomas"])
                update_display(next_idx)

        lang_badge_btn.clicked.connect(cycle_language)
        update_display(0)

        item_layout.addWidget(lang_badge_btn)
        item_layout.addWidget(card_lbl)
        return item_container

    def load_cards(self):
        session = SessionLocal()
        try:
            from sqlalchemy import and_, func
            query = (
                session.query(Cartas)
                .join(UsuarioCarta, and_(
                    Cartas.id_api == UsuarioCarta.carta_id,
                    func.coalesce(Cartas.idioma, 'es') == func.coalesce(UsuarioCarta.idioma, 'es')
                ))
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
            )

            # 1. Buscar por nombre
            texto = self.buscador.text().strip().lower()
            if texto:
                query = query.filter(func.lower(Cartas.nombre).like(f"%{texto}%"))

            # 2. Filtros desplegables
            for col_name, combo in self.filtros.items():
                if combo.currentIndex() > 0:
                    val = combo.currentText()
                    query = query.filter(getattr(Cartas, col_name) == val)

            todas_cartas = query.all()

            # Agrupar cartas por id_api y registrar idiomas que el usuario realmente posee
            cartas_por_id = {}
            for carta in todas_cartas:
                id_api = carta.id_api
                card_lang = getattr(carta, 'idioma', 'es') or 'es'
                if id_api not in cartas_por_id:
                    cartas_por_id[id_api] = {}
                cartas_por_id[id_api][card_lang] = carta

            # Limpiar área de cartas
            for i in reversed(range(self.cards_layout.count())):
                item = self.cards_layout.itemAt(i)
                if item and item.widget():
                    item.widget().deleteLater()

            for id_api, map_idiomas in cartas_por_id.items():
                item_widget = self._create_card_row_widget(id_api, map_idiomas)
                if item_widget:
                    self.cards_layout.addWidget(item_widget)
        finally:
            session.close()

    def refresh(self):
        self.cargar_opciones_filtros()
        self.load_cards()


class BinderPage(QWidget):
    def __init__(self, page_index, binder_view, rows, cols, slot_w, slot_h, card_w, card_h, is_left=True, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.binder_view = binder_view
        self.rows = rows
        self.cols = cols
        self.is_left = is_left

        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self.slots = []
        for r in range(rows):
            for c in range(cols):
                slot_idx = r * cols + c
                slot = BinderSlot(
                    page_index,
                    slot_idx,
                    binder_view=binder_view,
                    slot_w=slot_w,
                    slot_h=slot_h,
                    card_w=card_w,
                    card_h=card_h
                )
                layout.addWidget(slot, r, c)
                self.slots.append(slot)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Base de hoja de polipropileno oscuro mate estilo Ultra PRO
        sheet_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        sheet_grad.setColorAt(0.0, QColor(34, 34, 42, 240))
        sheet_grad.setColorAt(0.5, QColor(24, 24, 30, 245))
        sheet_grad.setColorAt(1.0, QColor(18, 18, 24, 248))
        painter.setBrush(sheet_grad)
        painter.setPen(QPen(QColor(255, 255, 255, 36), 1.2))
        painter.drawRoundedRect(rect, 7, 7)

        # Costuras termoselladas sutiles entre los bolsillos
        seam_pen = QPen(QColor(255, 255, 255, 22), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(seam_pen)
        if self.cols > 1:
            for c in range(1, self.cols):
                x = rect.left() + (rect.width() * c / self.cols)
                painter.drawLine(QPointF(x, rect.top() + 6), QPointF(x, rect.bottom() - 6))
        if self.rows > 1:
            for r in range(1, self.rows):
                y = rect.top() + (rect.height() * r / self.rows)
                painter.drawLine(QPointF(rect.left() + 6, y), QPointF(rect.right() - 6, y))

        # Reflejo diagonal sutil simulando mica plástica transparente
        sheen = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 22))
        sheen.setColorAt(0.30, QColor(255, 255, 255, 5))
        sheen.setColorAt(0.55, QColor(255, 255, 255, 14))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sheen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # Pequeño sello circular holográfico discreto en la esquina inferior exterior
        hx = rect.left() + 12 if self.is_left else rect.right() - 12
        hy = rect.bottom() - 12
        holo = QLinearGradient(hx - 5, hy - 5, hx + 5, hy + 5)
        holo.setColorAt(0.0, QColor(180, 230, 255, 110))
        holo.setColorAt(0.5, QColor(255, 200, 240, 125))
        holo.setColorAt(1.0, QColor(210, 255, 210, 110))
        painter.setBrush(holo)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 0.8))
        painter.drawEllipse(QPointF(hx, hy), 4.5, 4.5)

    def get_slot(self, slot_index):
        if 0 <= slot_index < len(self.slots):
            return self.slots[slot_index]
        return None


class BinderView(QWidget):
    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.binder_data = {}
        self.current_folder_id = None
        self.current_spread_index = 0 # 0 means pages 0 and 1
        self.current_mode = "3x3" # mode determined by folder
        self._active_flip_overlay = None
        self._active_open_overlay = None
        self._drag_turn_state = None
        self._folder_cover_widgets = {}
        self.show_card_details = False
        
        self.load_binder_data()
        
        # Main Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Left Panel: Inventory ---
        left_container = QWidget()
        left_container.setFixedWidth(240) # Sidebar width
        left_container.setStyleSheet("""
            background-color: #ffeef2; 
            border-right: 2px solid #f3c8d1;
        """)
        left_layout = QVBoxLayout(left_container)
        
        self.inventory = InventorySidebar(usuario)
        left_layout.addWidget(self.inventory)
        
        main_layout.addWidget(left_container)
        
        # --- Right Panel: Stacked Widget (Vista Carpetas vs Vista Binder Páginas) ---
        self.main_stack = QStackedWidget()
        main_layout.addWidget(self.main_stack, 1)

        # 1. Pantalla: Vista de Carpetas (Gallery / Home de Carpetas)
        self.folders_view_widget = QWidget()
        self.setup_folders_view()
        self.main_stack.addWidget(self.folders_view_widget)

        # 2. Pantalla: Vista de Páginas del Binder
        self.binder_pages_widget = QWidget()
        self.setup_binder_pages_view()
        self.main_stack.addWidget(self.binder_pages_widget)

        # Mostrar carpetas inicialmente
        self.mostrar_vista_carpetas()
        language_manager.language_changed.connect(self.retranslate_ui)

    def setup_folders_view(self):
        """Configura la vista inicial de binders del usuario (limpia y sin emojis)."""
        layout = QVBoxLayout(self.folders_view_widget)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)

        # Header de Vista Binders (se oculta automáticamente cuando no hay carpetas)
        self.folders_header_widget = QWidget()
        self.folders_header_widget.setStyleSheet("background: transparent; border: none;")
        top_bar = QHBoxLayout(self.folders_header_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(14)

        self.lbl_folders_title = QLabel(t("Mis Binders"))
        self.lbl_folders_title.setStyleSheet("font-size: 21px; font-weight: 700; color: #5a2a3a;")
        top_bar.addWidget(self.lbl_folders_title)

        top_bar.addStretch()

        self.btn_crear_carpeta_main = QPushButton(f"+ {t('Nueva Carpeta')}")
        self.btn_crear_carpeta_main.setFixedHeight(38)
        self.btn_crear_carpeta_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crear_carpeta_main.setStyleSheet("""
            QPushButton {
                background-color: #f7a8b8;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                border: 2px solid #f29ca4;
                border-radius: 12px;
                padding: 4px 20px;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #f5475c;
            }
            QPushButton:pressed {
                background-color: #d44854;
            }
        """)
        self.btn_crear_carpeta_main.clicked.connect(self.abrir_dialogo_crear_carpeta)
        top_bar.addWidget(self.btn_crear_carpeta_main)

        layout.addWidget(self.folders_header_widget)

        # Scroll Area para el catálogo de binders o el botón único de creación inicial
        self.folders_scroll = QScrollArea()
        self.folders_scroll.setWidgetResizable(True)
        self.folders_scroll.setStyleSheet("background-color: transparent; border: none;")

        self.folders_container = QWidget()
        self.folders_container.setStyleSheet("background: transparent;")
        self.folders_grid = QGridLayout(self.folders_container)
        self.folders_grid.setSpacing(22)
        self.folders_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.folders_scroll.setWidget(self.folders_container)

        layout.addWidget(self.folders_scroll, 1)

    def setup_binder_pages_view(self):
        """Configura la vista interna del binder seleccionado."""
        right_layout = QVBoxLayout(self.binder_pages_widget)
        right_layout.setContentsMargins(20, 15, 20, 10)
        
        # Header layout for Title, Folder Selector and Back Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        # Botón Volver a mis carpetas
        self.btn_back_to_folders = QPushButton(t("Volver a Carpetas"))
        self.btn_back_to_folders.setFixedHeight(32)
        self.btn_back_to_folders.setProperty("class", "pill")
        self.btn_back_to_folders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_to_folders.clicked.connect(lambda: self.mostrar_vista_carpetas(animate_close=True))
        header_layout.addWidget(self.btn_back_to_folders)

        self.title_lbl = QLabel(t("Binder"))
        self.title_lbl.setStyleSheet("font-size: 17px; font-weight: bold; color: #5a2a3a;")
        header_layout.addWidget(self.title_lbl)

        self.combo_folders = QComboBox()
        self.combo_folders.setFixedHeight(30)
        self.combo_folders.setStyleSheet("""
            QComboBox {
                background-color: white;
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 2px 10px;
                font-weight: 600;
                color: #5a2a3a;
                min-width: 140px;
            }
        """)
        self.combo_folders.currentIndexChanged.connect(self.on_folder_selected)
        header_layout.addWidget(self.combo_folders)

        self.btn_new_folder = QPushButton(f"+ {t('Carpeta')}")
        self.btn_new_folder.setFixedHeight(30)
        self.btn_new_folder.setProperty("class", "pill")
        self.btn_new_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_folder.clicked.connect(self.abrir_dialogo_crear_carpeta)
        header_layout.addWidget(self.btn_new_folder)

        self.btn_manage_folders = QPushButton(t("Gestionar"))
        self.btn_manage_folders.setFixedHeight(30)
        self.btn_manage_folders.setProperty("class", "pill")
        self.btn_manage_folders.setToolTip(t("Administrar o eliminar carpetas"))
        self.btn_manage_folders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_folders.clicked.connect(self.abrir_dialogo_administrar_carpetas)
        header_layout.addWidget(self.btn_manage_folders)

        header_layout.addStretch()

        # Etiqueta informativa del modo fijo de la carpeta
        self.lbl_folder_info_badge = QLabel("")
        self.lbl_folder_info_badge.setStyleSheet("""
            background-color: #ffdce5;
            color: #703043;
            font-size: 12px;
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 10px;
            border: 1px solid #f2a7b7;
        """)
        header_layout.addWidget(self.lbl_folder_info_badge)

        right_layout.addLayout(header_layout)

        # Barra de Calculador de Precio Acumulativo del Binder por API (Issue #14)
        self.binder_price_bar = QFrame()
        self.binder_price_bar.setObjectName("BinderPriceBar")
        self.binder_price_bar.setStyleSheet("""
            QFrame#BinderPriceBar {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 10px;
            }
        """)
        price_bar_layout = QHBoxLayout(self.binder_price_bar)
        price_bar_layout.setContentsMargins(12, 6, 12, 6)
        price_bar_layout.setSpacing(10)

        self.lbl_binder_price_title = QLabel(f"{t('Valor del Binder')}:")
        self.lbl_binder_price_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #5a2a3a; border: none; background: transparent;")
        price_bar_layout.addWidget(self.lbl_binder_price_title)

        self.binder_prices_pills_container = QWidget()
        self.binder_prices_pills_container.setStyleSheet("background: transparent; border: none;")
        self.binder_prices_pills_layout = QHBoxLayout(self.binder_prices_pills_container)
        self.binder_prices_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.binder_prices_pills_layout.setSpacing(8)
        price_bar_layout.addWidget(self.binder_prices_pills_container, 1)

        self.btn_sync_binder_prices = QPushButton(t("Cotizar Mercado"))
        self.btn_sync_binder_prices.setFixedHeight(26)
        self.btn_sync_binder_prices.setProperty("class", "pill")
        self.btn_sync_binder_prices.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_binder_prices.clicked.connect(self.sincronizar_precios_binder_actual)
        price_bar_layout.addWidget(self.btn_sync_binder_prices)

        right_layout.addWidget(self.binder_price_bar)

        # Barra compacta con botón "Ver detalles" debajo de Valor del Binder (Issue #17, sin emojis)
        details_row = QHBoxLayout()
        details_row.setContentsMargins(2, 0, 2, 0)
        details_row.setSpacing(8)

        self.btn_ver_detalles = QPushButton(t("Ver detalles"))
        self.btn_ver_detalles.setCheckable(True)
        self.btn_ver_detalles.setChecked(False)
        self.btn_ver_detalles.setFixedHeight(26)
        self.btn_ver_detalles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_detalles.setToolTip(
            t("Activa o desactiva la variante, la burbuja de información y el idioma sobre las cartas del binder")
        )
        self.btn_ver_detalles.clicked.connect(self.toggle_binder_card_details)
        self._refresh_ver_detalles_btn_style()
        details_row.addWidget(self.btn_ver_detalles)
        details_row.addStretch()
        right_layout.addLayout(details_row)

        # Spread Stack Container (Stacked Widget to allow transition animations)
        self.spread_stack = QStackedWidget()
        right_layout.addWidget(self.spread_stack, 1) # Expand

        # References to current visible pages
        self.page_left = None
        self.page_right = None

        # Mini-mapa de salto rápido de páginas (Etapa 3)
        self.page_minimap = BinderPageMinimap(self)
        self.page_minimap.spread_selected.connect(self.jump_to_spread)
        right_layout.addWidget(self.page_minimap)

        # Pagination Controls
        controls_layout = QHBoxLayout()
        self.btn_prev = QPushButton(t("Anterior"))
        self.btn_next = QPushButton(t("Siguiente"))
        self.lbl_pages = QLabel(f"{t('Página')} 1 - 2")

        self.btn_quitar = QPushButton(t("Quitar"))
        self.btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quitar.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 12px;
                padding: 6px 16px;
                border: none;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            QPushButton:hover:enabled {
                background-color: #dc2626;
            }
        """)
        self.btn_quitar.setEnabled(False)
        self.btn_quitar.clicked.connect(self.quitar_cartas_seleccionadas)

        for btn in [self.btn_prev, self.btn_next]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "BinderNavBtn")
            
        self.btn_prev.clicked.connect(self.prev_spread)
        self.btn_next.clicked.connect(self.next_spread)
        
        controls_layout.addStretch()
        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.lbl_pages)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addSpacing(24)
        controls_layout.addWidget(self.btn_quitar)
        controls_layout.addStretch()
        
        right_layout.addLayout(controls_layout)

        # Indicador discreto de atajos de teclado (Etapa 1)
        self.lbl_shortcuts_hint = QLabel(
            f"{t('Atajos')}:  ← / → {t('Página')}   |   {t('Espacio')} {t('Zoom')}   |   Esc {t('Volver')}"
        )
        self.lbl_shortcuts_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_shortcuts_hint.setStyleSheet(
            "font-size: 11px; color: #8c5a69; background: transparent; border: none; padding-top: 2px;"
        )
        right_layout.addWidget(self.lbl_shortcuts_hint)

        self.binder_pages_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_binder_shortcuts()

    def _setup_binder_shortcuts(self):
        """Configura atajos de teclado ergonómicos para navegar el binder abierto."""
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._sc_prev = QShortcut(QKeySequence(Qt.Key.Key_Left), self, context=ctx)
        self._sc_prev.activated.connect(self._shortcut_prev_spread)

        self._sc_next = QShortcut(QKeySequence(Qt.Key.Key_Right), self, context=ctx)
        self._sc_next.activated.connect(self._shortcut_next_spread)

        self._sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self, context=ctx)
        self._sc_esc.activated.connect(self._shortcut_close_binder)

        self._sc_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self, context=ctx)
        self._sc_space.activated.connect(self._shortcut_zoom_selected)

        self._sc_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self, context=ctx)
        self._sc_enter.activated.connect(self._shortcut_zoom_selected)

    def _can_trigger_binder_shortcut(self, allow_in_input=False) -> bool:
        if self.main_stack.currentWidget() is not self.binder_pages_widget:
            return False
        if self._active_flip_overlay is not None or self._active_open_overlay is not None:
            return False
        if not allow_in_input:
            fw = QApplication.focusWidget()
            if isinstance(fw, (QLineEdit, QComboBox)):
                return False
        return True

    def _shortcut_prev_spread(self):
        if self._can_trigger_binder_shortcut() and self.current_spread_index > 0:
            self.prev_spread()

    def _shortcut_next_spread(self):
        if self._can_trigger_binder_shortcut():
            self.next_spread()

    def _shortcut_close_binder(self):
        if not self._can_trigger_binder_shortcut(allow_in_input=True):
            return
        fw = QApplication.focusWidget()
        if isinstance(fw, QLineEdit):
            fw.clearFocus()
            self.binder_pages_widget.setFocus()
            return
        self.mostrar_vista_carpetas(animate_close=True)

    def _shortcut_zoom_selected(self):
        if not self._can_trigger_binder_shortcut():
            return
        for page in (self.page_left, self.page_right):
            if not page:
                continue
            for slot in page.slots:
                if slot.selected and slot.id_api:
                    slot._on_long_press()
                    return

    def _refresh_ver_detalles_btn_style(self):
        """Actualiza el texto y estilo del botón 'Ver detalles' según su estado activo (Issue #17)."""
        if not hasattr(self, "btn_ver_detalles") or not self.btn_ver_detalles:
            return
        active = bool(self.show_card_details)
        self.btn_ver_detalles.setChecked(active)
        self.btn_ver_detalles.setText(t("Ocultar detalles") if active else t("Ver detalles"))
        if active:
            self.btn_ver_detalles.setStyleSheet("""
                QPushButton {
                    background-color: #f56b7b;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 700;
                    border: 1.5px solid #d44854;
                    border-radius: 9px;
                    padding: 2px 14px;
                }
                QPushButton:hover {
                    background-color: #e05263;
                }
            """)
        else:
            self.btn_ver_detalles.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #5a2a3a;
                    font-size: 11px;
                    font-weight: 700;
                    border: 1.5px solid #f2b8c3;
                    border-radius: 9px;
                    padding: 2px 14px;
                }
                QPushButton:hover {
                    background-color: #ffdfe6;
                    border-color: #f56b7b;
                }
            """)

    def toggle_binder_card_details(self):
        """Alterna la visibilidad de variante, burbuja de info e idioma en todas las cartas del binder."""
        self.show_card_details = not self.show_card_details
        self._refresh_ver_detalles_btn_style()
        for page in (self.page_left, self.page_right):
            if not page:
                continue
            for slot in page.slots:
                slot.apply_details_visibility()

    def mostrar_vista_carpetas(self, animate_close=False):
        """Muestra la vista de catálogo/selección de carpetas, con animación 3D de cierre al volver."""
        from MyQtApp.config import load_settings
        animaciones_activas = load_settings().get("animaciones", True)

        if (
            animate_close
            and animaciones_activas
            and self.main_stack.currentWidget() is self.binder_pages_widget
            and self.current_folder_id
        ):
            closing_folder_id = self.current_folder_id
            current_spread = self.spread_stack.currentWidget()
            if current_spread and isinstance(current_spread, BinderSpreadFrame):
                try:
                    board_local = current_spread.get_board_rect()
                    if board_local.width() >= 80 and board_local.height() >= 80:
                        spread_pix = current_spread.grab(board_local.toRect())
                        top_left_stack = current_spread.mapTo(self.main_stack, board_local.topLeft().toPoint())
                        board_in_stack = QRectF(
                            float(top_left_stack.x()),
                            float(top_left_stack.y()),
                            board_local.width(),
                            board_local.height(),
                        )

                        # Capturar el fondo limpio de la vista de páginas SIN el binder abierto detrás
                        current_spread.setVisible(False)
                        pages_bg_pix = self.binder_pages_widget.grab()
                        current_spread.setVisible(True)

                        name, design, color, mode = self._get_current_folder_theme()
                        cover_w = max(140, int(board_local.width() * 0.5))
                        cover_h = max(180, int(board_local.height()))
                        cover_pix = render_transparent_cover_pixmap(name, design, color, mode, cover_w, cover_h)

                        # Cambiar a la estantería y calcular el destino exacto de la carpeta
                        self.render_folders_grid()
                        self.main_stack.setCurrentWidget(self.folders_view_widget)
                        if self.folders_view_widget.layout():
                            self.folders_view_widget.layout().activate()
                        if self.folders_container.layout():
                            self.folders_container.layout().activate()
                        QApplication.processEvents()

                        target_rect_in_stack = None
                        target_cover = self._folder_cover_widgets.get(closing_folder_id)
                        if target_cover is not None:
                            try:
                                tl = target_cover.mapTo(self.main_stack, QPoint(0, 0))
                                target_rect_in_stack = QRectF(
                                    float(tl.x()),
                                    float(tl.y()),
                                    float(target_cover.width()),
                                    float(target_cover.height()),
                                )
                            except Exception:
                                target_rect_in_stack = None

                        shelf_pix = self.folders_view_widget.grab()

                        if self._active_open_overlay:
                            try:
                                self._active_open_overlay.deleteLater()
                            except Exception:
                                pass
                            self._active_open_overlay = None

                        overlay = BinderOpenAnimationOverlay(
                            parent=self.main_stack,
                            cover_pixmap=cover_pix,
                            spread_pixmap=spread_pix,
                            board_rect=board_in_stack,
                            origin_rect=target_rect_in_stack,
                            design=design,
                            color=color,
                            reverse=True,
                            shelf_pixmap=shelf_pix,
                            pages_bg_pixmap=pages_bg_pix,
                        )
                        self._active_open_overlay = overlay
                        overlay.animation_finished.connect(lambda: setattr(self, "_active_open_overlay", None))
                        return
                except Exception as e:
                    print(f"Error en animación de cierre de binder: {e}")

        self.render_folders_grid()
        self.main_stack.setCurrentWidget(self.folders_view_widget)

    def _get_current_folder_theme(self) -> tuple[str, str, str, str]:
        """Retorna (name, design, color, mode) de la carpeta actual."""
        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id, {})
        name = folder.get("name", "Binder")
        design = resolve_design_key(folder.get("design", "Charizard Fuego"))
        color = folder.get("color", "auto")
        mode = folder.get("mode", self.current_mode)
        return name, design, color, mode

    def abrir_carpeta(self, folder_id, origin_widget=None):
        """Abre la carpeta seleccionada con animación 3D de apertura de libro/binder."""
        folders = self.get_user_folders()
        if folder_id not in folders:
            return

        from MyQtApp.config import load_settings
        animaciones_activas = load_settings().get("animaciones", True)

        # Capturar posición inicial de la portada y foto de la estantería ANTES de cambiar de vista
        origin_rect_in_stack = None
        shelf_pix = None
        if animaciones_activas and self.main_stack.currentWidget() is self.folders_view_widget:
            shelf_pix = self.folders_view_widget.grab()
            if origin_widget is not None:
                try:
                    top_left = origin_widget.mapTo(self.main_stack, QPoint(0, 0))
                    origin_rect_in_stack = QRectF(
                        float(top_left.x()),
                        float(top_left.y()),
                        float(origin_widget.width()),
                        float(origin_widget.height()),
                    )
                except Exception:
                    origin_rect_in_stack = None

        self.current_folder_id = folder_id
        folder = folders[folder_id]
        self.current_mode = folder.get("mode", "3x3")
        self.current_spread_index = 0
        self.update_folder_combo()
        self.aplicar_estilo_carpeta_actual()
        self.update_spread(direction=0)
        self.actualizar_resumen_precios_binder()
        self.main_stack.setCurrentWidget(self.binder_pages_widget)
        self.binder_pages_widget.setFocus()

        if animaciones_activas:
            current_spread = self.spread_stack.currentWidget()
            if current_spread:
                self._run_book_open_animation(origin_rect_in_stack, shelf_pix)

    def _run_book_open_animation(self, origin_rect_in_stack=None, shelf_pix=None):
        """Lanza el overlay 3D de apertura del binder sin que se vea el binder abierto por detrás."""
        current_spread = self.spread_stack.currentWidget()
        try:
            if not current_spread or not isinstance(current_spread, BinderSpreadFrame):
                return

            # Asegurar geometría final calculada antes de capturar los pixmaps
            if self.binder_pages_widget.layout():
                self.binder_pages_widget.layout().activate()
            if current_spread.layout():
                current_spread.layout().activate()
            QApplication.processEvents()

            board_local = current_spread.get_board_rect()
            if board_local.width() < 80 or board_local.height() < 80:
                return

            # Capturar el pliego abierto exacto
            spread_pix = current_spread.grab(board_local.toRect())
            if spread_pix.isNull():
                return

            # Ocultar el pliego real durante la animación y capturar el escritorio limpio sin binder detrás
            current_spread.setVisible(False)
            pages_bg_pix = self.binder_pages_widget.grab()

            # Renderizar portada física transparente (sin esquinas blancas)
            name, design, color, mode = self._get_current_folder_theme()
            cover_w = max(140, int(board_local.width() * 0.5))
            cover_h = max(180, int(board_local.height()))
            cover_pix = render_transparent_cover_pixmap(name, design, color, mode, cover_w, cover_h)

            # Mapear el rectángulo del binder a coordenadas de self.main_stack
            top_left_stack = current_spread.mapTo(self.main_stack, board_local.topLeft().toPoint())
            board_in_stack = QRectF(
                float(top_left_stack.x()),
                float(top_left_stack.y()),
                board_local.width(),
                board_local.height(),
            )

            if self._active_open_overlay:
                try:
                    self._active_open_overlay.deleteLater()
                except Exception:
                    pass
                self._active_open_overlay = None

            overlay = BinderOpenAnimationOverlay(
                parent=self.main_stack,
                cover_pixmap=cover_pix,
                spread_pixmap=spread_pix,
                board_rect=board_in_stack,
                origin_rect=origin_rect_in_stack,
                design=design,
                color=color,
                reverse=False,
                shelf_pixmap=shelf_pix,
                pages_bg_pixmap=pages_bg_pix,
            )
            self._active_open_overlay = overlay

            def _on_open_done():
                self._active_open_overlay = None
                try:
                    if current_spread:
                        current_spread.setVisible(True)
                except RuntimeError:
                    pass

            overlay.animation_finished.connect(_on_open_done)
        except Exception as e:
            print(f"Error en animación de apertura de binder: {e}")
            try:
                if current_spread:
                    current_spread.setVisible(True)
            except Exception:
                pass

    def _extract_folder_card_entries(self, folder_data: dict) -> list[tuple[str, str]]:
        """Retorna lista de (id_api, idioma) de todas las cartas colocadas en el modo activo de la carpeta."""
        if not isinstance(folder_data, dict):
            return []
        mode = folder_data.get("mode", "3x3")
        cards_dict = folder_data.get("cards", {}).get(mode, {})
        entries = []
        for slot_val in cards_dict.values():
            if isinstance(slot_val, dict):
                cid = slot_val.get("id_api")
                lang = slot_val.get("idioma", "en")
                if cid:
                    entries.append((cid, lang))
            elif isinstance(slot_val, str) and slot_val:
                if ":" in slot_val:
                    cid, lang = slot_val.split(":", 1)
                    entries.append((cid, lang))
                else:
                    entries.append((slot_val, "en"))
        return entries

    def calcular_precios_carpeta(self, folder_data: dict) -> dict:
        """
        Calcula el valor acumulativo total de una carpeta/binder sumando el valor
        de cada carta dentro de ella, separado por cada fuente API disponible.
        """
        entries = self._extract_folder_card_entries(folder_data)
        card_ids = [cid for cid, _ in entries]
        if not card_ids:
            return {
                "total_cards": 0,
                "sources": {},
                "base_total_usd": 0.0,
                "base_priced_count": 0,
                "entries": [],
            }

        multi_prices, base_prices = obtener_precios_multiples_cartas_bd(card_ids)

        totals_by_source = {}
        base_total_usd = 0.0
        base_priced_count = 0

        for cid in card_ids:
            bp = base_prices.get(cid, 0.0)
            if bp > 0:
                base_total_usd += bp
                base_priced_count += 1

            c_sources = multi_prices.get(cid, {})
            for src, info in c_sources.items():
                usd = float(info.get("precio_usd") or 0.0)
                orig = float(info.get("precio_original") or 0.0)
                if usd <= 0 and orig <= 0:
                    continue
                bucket = totals_by_source.setdefault(
                    src,
                    {"usd": 0.0, "orig": 0.0, "moneda": info.get("moneda", "USD"), "priced_count": 0},
                )
                bucket["usd"] += usd
                bucket["orig"] += orig
                bucket["priced_count"] += 1

        for bucket in totals_by_source.values():
            bucket["usd"] = round(bucket["usd"], 2)
            bucket["orig"] = round(bucket["orig"], 2)

        return {
            "total_cards": len(card_ids),
            "sources": totals_by_source,
            "base_total_usd": round(base_total_usd, 2),
            "base_priced_count": base_priced_count,
            "entries": entries,
        }

    def actualizar_resumen_precios_binder(self):
        """Refresca la barra de valor acumulativo por API de la carpeta actualmente abierta."""
        if not hasattr(self, "binder_prices_pills_layout"):
            return

        while self.binder_prices_pills_layout.count():
            item = self.binder_prices_pills_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id)
        if not folder:
            return

        res = self.calcular_precios_carpeta(folder)
        total_cards = res["total_cards"]
        sources = res["sources"]

        self.lbl_binder_price_title.setText(f"{t('Valor del Binder')} ({total_cards} cartas):")

        if total_cards == 0:
            lbl = QLabel("$0.00 USD")
            lbl.setStyleSheet("font-size: 12px; color: #8c5464; font-weight: 600; border: none; background: transparent;")
            self.binder_prices_pills_layout.addWidget(lbl)
            self.binder_prices_pills_layout.addStretch()
            return

        ordered_sources = [s for s in PRICE_SOURCE_ORDER if s in sources] + [
            s for s in sources.keys() if s not in PRICE_SOURCE_ORDER
        ]

        if ordered_sources:
            palette = {
                "TCGPlayer": ("#ecfdf5", "#15803d", "#86efac"),
                "Cardmarket": ("#eff6ff", "#1d4ed8", "#93c5fd"),
                "PokemonTCG": ("#fef3c7", "#b45309", "#fcd34d"),
                "TCGCSV": ("#f5f3ff", "#6d28d9", "#c4b5fd"),
            }
            for src in ordered_sources:
                info = sources[src]
                bg, fg, bd = palette.get(src, ("#f8fafc", "#334155", "#cbd5e1"))
                if info["moneda"] == "EUR":
                    txt = f"{src} = €{info['orig']:,.2f} (~${info['usd']:,.2f})"
                else:
                    txt = f"{src} = ${info['usd']:,.2f}"
                pill = QLabel(txt)
                pill.setToolTip(f"{src}: {info['priced_count']}/{total_cards} cartas cotizadas")
                pill.setStyleSheet(
                    f"background-color: {bg}; color: {fg}; border: 1px solid {bd}; "
                    f"border-radius: 8px; padding: 3px 9px; font-size: 11px; font-weight: bold;"
                )
                self.binder_prices_pills_layout.addWidget(pill)
        else:
            base_usd = res["base_total_usd"]
            pill = QLabel(f"Mercado Base = ${base_usd:,.2f} USD")
            pill.setToolTip(t("Presiona 'Cotizar Mercado' para comparar precios entre TCGPlayer, Cardmarket y PokemonTCG"))
            pill.setStyleSheet(
                "background-color: #fff0f3; color: #703043; border: 1px solid #f2a7b7; "
                "border-radius: 8px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
            )
            self.binder_prices_pills_layout.addWidget(pill)

        self.binder_prices_pills_layout.addStretch()

    def sincronizar_precios_binder_actual(self):
        """Consulta múltiples APIs en vivo para todas las cartas de la carpeta abierta."""
        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id)
        if not folder:
            return
        entries = self._extract_folder_card_entries(folder)
        if not entries:
            show_toast(t("Esta carpeta no tiene cartas para cotizar"), "info")
            return

        self.btn_sync_binder_prices.setEnabled(False)
        self.btn_sync_binder_prices.setText(t("Cotizando..."))

        self.binder_price_thread = PriceUpdaterThread(entries, parent=self)
        self.binder_price_thread.progress.connect(
            lambda cur, tot: self.btn_sync_binder_prices.setText(f"{cur}/{tot}...")
        )
        self.binder_price_thread.finished.connect(self._on_binder_prices_synced)
        self.binder_price_thread.error.connect(self._on_binder_prices_error)
        self.binder_price_thread.start()

    def _on_binder_prices_synced(self, actualizadas: int):
        self.btn_sync_binder_prices.setEnabled(True)
        self.btn_sync_binder_prices.setText(t("Cotizar Mercado"))
        self.actualizar_resumen_precios_binder()
        show_toast(f"Precios del binder actualizados ({actualizadas} cartas)", "info")

    def _on_binder_prices_error(self, err_msg: str):
        self.btn_sync_binder_prices.setEnabled(True)
        self.btn_sync_binder_prices.setText(t("Cotizar Mercado"))
        show_toast(f"Error al cotizar carpeta: {err_msg}", "error")

    def render_folders_grid(self):
        """Dibuja los binders con diseños físicos realistas o un único botón grande si no hay carpetas."""
        self._folder_cover_widgets.clear()
        for i in reversed(range(self.folders_grid.count())):
            item = self.folders_grid.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        folders = self.get_user_folders()
        if not folders:
            # Estado vacío ultra limpio (Issue #12): un único botón grande preguntando si desea crear una carpeta, sin emojis
            self.folders_header_widget.setVisible(False)
            self.folders_grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_first_folder = QPushButton(f"¿Quieres crear una carpeta?\n\n+ {t('Crear mi primera carpeta')}")
            btn_first_folder.setFixedSize(360, 175)
            btn_first_folder.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_first_folder.setStyleSheet("""
                QPushButton {
                    background-color: #fff0f4;
                    color: #5a2a3a;
                    font-size: 16px;
                    font-weight: 700;
                    border: 2.5px dashed #f29ca4;
                    border-radius: 20px;
                    padding: 20px;
                }
                QPushButton:hover {
                    background-color: #f7a8b8;
                    color: #ffffff;
                    border: 2.5px solid #f56b7b;
                }
                QPushButton:pressed {
                    background-color: #f56b7b;
                    color: #ffffff;
                    border-color: #d44854;
                }
            """)
            btn_first_folder.clicked.connect(self.abrir_dialogo_crear_carpeta)
            self.folders_grid.addWidget(btn_first_folder, 0, 0, Qt.AlignmentFlag.AlignCenter)
            return

        self.folders_header_widget.setVisible(True)
        self.folders_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        cols = 3
        row = 0
        col = 0
        for f_id, f_data in folders.items():
            card_widget = self._crear_tarjeta_carpeta(f_id, f_data)
            self.folders_grid.addWidget(card_widget, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _crear_tarjeta_carpeta(self, f_id, f_data):
        """Crea la tarjeta visual de un Binder con portada física realista Ultra PRO (sin emojis)."""
        name = f_data.get("name", "Carpeta")
        color = f_data.get("color", "auto")
        design = resolve_design_key(f_data.get("design", "Charizard Fuego"))
        mode = f_data.get("mode", "3x3")

        cards_dict = f_data.get("cards", {}).get(mode, {})
        cant_cartas = len(cards_dict)

        frame = QFrame()
        frame.setFixedSize(218, 305)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 16px;
            }
            QFrame:hover {
                border: 2px solid #f56b7b;
                background-color: #fff9fa;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Portada física realista del Binder (Issue #13)
        cover = BinderCoverWidget(name=name, design=design, color=color, mode=mode, parent=frame)
        cover.setFixedSize(196, 212)
        self._folder_cover_widgets[f_id] = cover
        layout.addWidget(cover, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Resumen de precio acumulativo por API
        price_res = self.calcular_precios_carpeta(f_data)
        src_map = price_res["sources"]
        if src_map:
            parts = []
            for src in PRICE_SOURCE_ORDER:
                if src in src_map:
                    info = src_map[src]
                    if info["moneda"] == "EUR":
                        parts.append(f"{src}: €{info['orig']:,.2f}")
                    else:
                        parts.append(f"{src}: ${info['usd']:,.2f}")
            price_summary_txt = " | ".join(parts[:2])
        else:
            price_summary_txt = f"${price_res['base_total_usd']:,.2f} USD"

        lbl_folder_val = QLabel(price_summary_txt)
        lbl_folder_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_folder_val.setStyleSheet(
            "background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 7px; "
            "padding: 3px 6px; font-size: 10px; font-weight: 700; color: #15803d;"
        )
        layout.addWidget(lbl_folder_val)

        # Fila inferior: cantidad de cartas + acción discreta de eliminar
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(2, 0, 2, 0)
        bottom_row.setSpacing(6)

        lbl_count = QLabel(f"{cant_cartas} cartas  |  {mode}")
        lbl_count.setStyleSheet("font-size: 11px; font-weight: 600; color: #703043; border: none; background: transparent;")
        bottom_row.addWidget(lbl_count)
        bottom_row.addStretch()

        btn_del = QPushButton(t("Eliminar"))
        btn_del.setFixedHeight(22)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 6px;
                padding: 0 8px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #fee2e2;
                border-color: #ef4444;
            }
        """)
        btn_del.clicked.connect(lambda ch, target_id=f_id, target_name=name: self._eliminar_carpeta_directa(target_id, target_name))
        bottom_row.addWidget(btn_del)

        layout.addLayout(bottom_row)

        # Hover sincronizado con la portada física 3D
        def on_enter(event):
            cover.set_hovered(True)
            QFrame.enterEvent(frame, event)

        def on_leave(event):
            cover.set_hovered(False)
            QFrame.leaveEvent(frame, event)

        def on_frame_click(event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.abrir_carpeta(f_id, origin_widget=cover)

        frame.enterEvent = on_enter
        frame.leaveEvent = on_leave
        frame.mousePressEvent = on_frame_click

        return frame

    def _eliminar_carpeta_directa(self, folder_id, folder_name):
        folders = self.get_user_folders()
        if len(folders) <= 0:
            return
        resp = QMessageBox.question(
            self,
            t("Confirmar Eliminación"),
            f"{t('¿Seguro que deseas eliminar la carpeta')} '{folder_name}'? {t('Las cartas que contenía seguirán existiendo en tu colección general.')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            if folder_id in folders:
                del folders[folder_id]
                self.save_binder_data()
                if self.current_folder_id == folder_id:
                    self.current_folder_id = next(iter(folders.keys())) if folders else None
                show_toast(t("Carpeta eliminada"), "info")
                self.render_folders_grid()

    def update_folder_combo(self):
        """Llena el combo de carpetas del usuario."""
        self.combo_folders.blockSignals(True)
        self.combo_folders.clear()
        folders = self.get_user_folders()
        for f_id, f_data in folders.items():
            f_name = f_data.get("name", f_id)
            self.combo_folders.addItem(f_name, f_id)

        # Seleccionar la carpeta actual
        if self.current_folder_id:
            idx = self.combo_folders.findData(self.current_folder_id)
            if idx >= 0:
                self.combo_folders.setCurrentIndex(idx)
            else:
                if self.combo_folders.count() > 0:
                    self.combo_folders.setCurrentIndex(0)
                    self.current_folder_id = self.combo_folders.currentData()
        elif self.combo_folders.count() > 0:
            self.combo_folders.setCurrentIndex(0)
            self.current_folder_id = self.combo_folders.currentData()

        self.combo_folders.blockSignals(False)
        self.aplicar_estilo_carpeta_actual()

    def get_user_folders(self) -> dict:
        """Devuelve el diccionario de carpetas del usuario actual."""
        user_data = self.binder_data.setdefault(self.usuario, {})
        folders = user_data.setdefault("folders", {})
        return folders

    def aplicar_estilo_carpeta_actual(self):
        """Aplica el color y estilo visual definido para la carpeta actual."""
        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id, {})
        folder_mode = folder.get("mode")
        if folder_mode and folder_mode in BINDER_MODES:
            self.current_mode = folder_mode
        design_name = resolve_design_key(folder.get("design", "Charizard Fuego"))
        self.lbl_folder_info_badge.setText(f"{self.current_mode}  |  {design_name}")

    def on_folder_selected(self, index):
        folder_id = self.combo_folders.currentData()
        if not folder_id or folder_id == self.current_folder_id:
            return
        self.abrir_carpeta(folder_id)

    def abrir_dialogo_crear_carpeta(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Crear Nuevo Binder"))
        dlg.setFixedSize(580, 390)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QLabel {
                font-weight: 600;
                color: #5a2a3a;
                font-size: 12px;
            }
            QLineEdit, QComboBox {
                border: 2px solid #f7a8b8;
                border-radius: 10px;
                padding: 7px 10px;
                background-color: #ffffff;
                color: #5a2a3a;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #f56b7b;
            }
        """)

        outer_layout = QHBoxLayout(dlg)
        outer_layout.setContentsMargins(22, 20, 22, 20)
        outer_layout.setSpacing(20)

        # --- Columna Izquierda: Vista previa física en vivo del Binder (Issue #13) ---
        preview_panel = QFrame()
        preview_panel.setFixedWidth(215)
        preview_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 14px;
            }
        """)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 14, 12, 14)
        preview_layout.setSpacing(8)

        lbl_prev_title = QLabel(t("Vista Previa"))
        lbl_prev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_prev_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #8c5464; border: none; background: transparent;")
        preview_layout.addWidget(lbl_prev_title)

        default_design = list(BINDER_DESIGNS.keys())[0]
        live_preview = BinderCoverWidget(name="Mi Binder", design=default_design, color="auto", mode="3x3", parent=preview_panel)
        live_preview.setFixedSize(190, 248)
        preview_layout.addWidget(live_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addStretch()

        outer_layout.addWidget(preview_panel)

        # --- Columna Derecha: Formulario limpio y sin emojis ---
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        lbl_heading = QLabel(t("Configura tu Binder"))
        lbl_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #5a2a3a;")
        form_layout.addWidget(lbl_heading)

        form_layout.addWidget(QLabel(t("Nombre de la carpeta")))
        txt_nombre = QLineEdit()
        txt_nombre.setPlaceholderText(t("Ej: Charizards, Set 151, Intercambios..."))
        form_layout.addWidget(txt_nombre)

        form_layout.addWidget(QLabel(t("Tamaño de bolsillos")))
        combo_tamano = QComboBox()
        combo_tamano.addItems(["3x3", "2x2", "3x4", "4x4"])
        form_layout.addWidget(combo_tamano)

        form_layout.addWidget(QLabel(t("Diseño de portada")))
        combo_diseno = QComboBox()
        combo_diseno.addItems(list(BINDER_DESIGNS.keys()))
        form_layout.addWidget(combo_diseno)

        form_layout.addWidget(QLabel(t("Color de portada")))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)

        selected_color = ["auto"]

        btn_color = QPushButton(t("Color personalizado"))
        btn_color.setFixedHeight(32)
        btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_color.setProperty("class", "pill")

        btn_reset_color = QPushButton(t("Color del diseño"))
        btn_reset_color.setFixedHeight(32)
        btn_reset_color.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset_color.setProperty("class", "pill")

        def refresh_preview():
            live_preview.set_binder_props(
                name=txt_nombre.text().strip() or "Mi Binder",
                design=combo_diseno.currentText(),
                color=selected_color[0],
                mode=combo_tamano.currentText(),
            )

        def choose_color():
            c = QColorDialog.getColor(parent=dlg, title=t("Color de portada"))
            if c.isValid():
                selected_color[0] = c.name()
                btn_color.setText(selected_color[0].upper())
                btn_color.setStyleSheet(
                    f"background-color: {selected_color[0]}; color: #ffffff; "
                    f"border: 2px solid #5a2a3a; border-radius: 10px; font-weight: bold;"
                )
                refresh_preview()

        def reset_color():
            selected_color[0] = "auto"
            btn_color.setText(t("Color personalizado"))
            btn_color.setStyleSheet("")
            btn_color.setProperty("class", "pill")
            refresh_preview()

        btn_color.clicked.connect(choose_color)
        btn_reset_color.clicked.connect(reset_color)
        txt_nombre.textChanged.connect(lambda _: refresh_preview())
        combo_diseno.currentTextChanged.connect(lambda _: refresh_preview())
        combo_tamano.currentTextChanged.connect(lambda _: refresh_preview())

        color_row.addWidget(btn_color, 1)
        color_row.addWidget(btn_reset_color)
        form_layout.addLayout(color_row)

        form_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_cancel = QPushButton(t("Cancelar"))
        btn_cancel.setFixedHeight(36)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #703043;
                border: 2px solid #f2c4ce;
                border-radius: 10px;
                padding: 4px 16px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #ffeef2; }
        """)
        btn_cancel.clicked.connect(dlg.reject)

        btn_crear = QPushButton(t("Crear Carpeta"))
        btn_crear.setFixedHeight(36)
        btn_crear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_crear.setStyleSheet("""
            QPushButton {
                background-color: #f7a8b8;
                color: #ffffff;
                border: 2px solid #f29ca4;
                border-radius: 10px;
                padding: 4px 20px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #f5475c;
            }
        """)

        def on_crear():
            nombre = txt_nombre.text().strip()
            if not nombre:
                QMessageBox.warning(dlg, t("Aviso"), t("Debes ingresar un nombre para la carpeta."))
                return
            import time
            new_id = f"folder_{int(time.time() * 1000)}"
            folders = self.get_user_folders()
            folders[new_id] = {
                "name": nombre,
                "color": selected_color[0],
                "design": combo_diseno.currentText(),
                "mode": combo_tamano.currentText(),
                "cards": {
                    "2x2": {},
                    "3x3": {},
                    "3x4": {},
                    "4x4": {}
                }
            }
            self.save_binder_data()
            self.current_folder_id = new_id
            self.current_mode = combo_tamano.currentText()
            self.current_spread_index = 0
            self.render_folders_grid()
            show_toast(f"Carpeta '{nombre}' creada con éxito", "info")
            dlg.accept()
            self.abrir_carpeta(new_id)

        btn_crear.clicked.connect(on_crear)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_crear)
        form_layout.addLayout(btn_row)

        outer_layout.addLayout(form_layout, 1)
        dlg.exec()

    def abrir_dialogo_administrar_carpetas(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Administrar Carpetas"))
        dlg.setFixedSize(360, 240)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QLabel {
                font-weight: 600;
                color: #5a2a3a;
                font-size: 12px;
            }
            QComboBox {
                border: 2px solid #f7a8b8;
                border-radius: 10px;
                padding: 6px;
                background-color: white;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(QLabel(t("Selecciona una carpeta para eliminar:")))
        combo = QComboBox()
        folders = self.get_user_folders()
        for f_id, f_data in folders.items():
            combo.addItem(f_data.get('name', f_id), f_id)
        layout.addWidget(combo)

        btn_del = QPushButton(t("Eliminar Carpeta"))
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #dc2626;
                border: 1.5px solid #fca5a5;
                font-weight: bold;
                border-radius: 10px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #fecaca;
                border-color: #ef4444;
            }
        """)
        btn_del.setFixedHeight(34)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)

        def on_eliminar():
            if combo.count() <= 0:
                return
            target_id = combo.currentData()
            target_name = combo.currentText()
            resp = QMessageBox.question(
                dlg,
                t("Confirmar Eliminación"),
                f"{t('¿Seguro que deseas eliminar la carpeta')} '{target_name}'? {t('Las cartas que contenía dejarán de estar asignadas a este binder (seguirán en tu colección general).')}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.Yes:
                if target_id in folders:
                    del folders[target_id]
                self.save_binder_data()
                if self.current_folder_id == target_id:
                    self.current_folder_id = next(iter(folders.keys())) if folders else None
                show_toast(t("Carpeta eliminada"), "info")
                self.render_folders_grid()
                dlg.accept()
                if not folders or not self.current_folder_id:
                    self.mostrar_vista_carpetas()
                else:
                    self.update_folder_combo()
                    self.update_spread(direction=0)

        btn_del.clicked.connect(on_eliminar)
        layout.addWidget(btn_del)

        btn_close = QPushButton(t("Cerrar"))
        btn_close.setProperty("class", "pill")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(dlg.accept)
        layout.addStretch()
        layout.addWidget(btn_close)

        dlg.exec()

    def get_selected_slots(self):
        selected = []
        for page_w in [self.page_left, self.page_right]:
            if page_w and hasattr(page_w, 'slots'):
                for slot in page_w.slots:
                    if slot.id_api and slot.selected:
                        selected.append(slot)
        return selected

    def update_selection_state(self):
        selected_slots = self.get_selected_slots()
        count = len(selected_slots)
        if count > 0:
            self.btn_quitar.setText(f"{t('Quitar')} ({count})")
            self.btn_quitar.setEnabled(True)
        else:
            self.btn_quitar.setText(t("Quitar"))
            self.btn_quitar.setEnabled(False)

    def quitar_cartas_seleccionadas(self):
        selected_slots = self.get_selected_slots()
        if not selected_slots:
            return

        for slot in selected_slots:
            self.set_card_at(slot.page_index, slot.slot_index, None)
            slot.set_selected(False)
            slot.clear_card()

        self.update_selection_state()
        self.actualizar_resumen_precios_binder()

    def retranslate_ui(self):
        self.title_lbl.setText(t("Binder"))
        self.btn_prev.setText(t("Anterior"))
        self.btn_next.setText(t("Siguiente"))
        self.btn_quitar.setText(t("Quitar") if not self.get_selected_slots() else f"{t('Quitar')} ({len(self.get_selected_slots())})")
        p_idx_1 = self.current_spread_index * 2
        p_idx_2 = p_idx_1 + 1
        self.lbl_pages.setText(f"{t('Página')} {p_idx_1 + 1} - {p_idx_2 + 1}")
        if hasattr(self.inventory, 'retranslate_ui'):
            self.inventory.retranslate_ui()
        if hasattr(self, 'btn_back_to_folders'):
            self.btn_back_to_folders.setText(t("Volver a Carpetas"))
        if hasattr(self, 'lbl_folders_title'):
            self.lbl_folders_title.setText(t("Mis Binders"))
        if hasattr(self, 'btn_crear_carpeta_main'):
            self.btn_crear_carpeta_main.setText(f"+ {t('Nueva Carpeta')}")
        
    def load_binder_data(self):
        if os.path.exists(BINDER_DATA_FILE):
            try:
                with open(BINDER_DATA_FILE, 'r', encoding='utf-8') as f:
                    self.binder_data = json.load(f)
            except:
                self.binder_data = {}
        
        # Ensure user section exists
        if self.usuario not in self.binder_data:
            self.binder_data[self.usuario] = {}
            
        user_data = self.binder_data[self.usuario]
        
        # Si no tiene estructura de folders, migrar solo si existían cartas previas
        if "folders" not in user_data:
            existing_cards = {
                "2x2": user_data.get("2x2", {}),
                "3x3": user_data.get("3x3", {}),
                "3x4": user_data.get("3x4", user_data.get("4x3", {})),
                "4x4": user_data.get("4x4", {})
            }
            has_existing = any(len(v) > 0 for v in existing_cards.values())
            if has_existing:
                user_data["folders"] = {
                    "default": {
                        "name": "Mi Carpeta",
                        "color": "#ffeef2",
                        "design": "Clásico Rosa",
                        "mode": "3x3",
                        "cards": existing_cards
                    }
                }
            else:
                user_data["folders"] = {}
            self.save_binder_data()

    def save_binder_data(self):
        with open(BINDER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.binder_data, f, indent=4)
            
    def _get_current_cards_dict(self, mode=None) -> dict:
        folders = self.get_user_folders()
        folder = folders.setdefault(self.current_folder_id, {})
        cards_by_mode = folder.setdefault("cards", {})
        target_mode = mode if mode else self.current_mode
        return cards_by_mode.setdefault(target_mode, {})

    def get_card_at(self, page, slot, mode=None):
        cards_dict = self._get_current_cards_dict(mode)
        key = f"{page}_{slot}"
        return cards_dict.get(key)
        
    def set_card_at(self, page, slot, card_id):
        cards_dict = self._get_current_cards_dict(self.current_mode)
        key = f"{page}_{slot}"
        if card_id is None:
            if key in cards_dict:
                del cards_dict[key]
        else:
            cards_dict[key] = card_id
        self.save_binder_data()

    def change_mode(self, mode):
        if self.current_mode == mode:
            return
        
        # Respect global animation setting
        from MyQtApp.config import load_settings
        settings = load_settings()
        animaciones_activas = settings.get("animaciones", True)
        
        if not animaciones_activas:
            self.current_mode = mode
            # Update buttons styling
            for m, btn in self.mode_buttons.items():
                btn.setProperty("class", "pill selected" if m == mode else "pill")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.update_spread(direction=0)
        else:
            self.fade_zoom_transition(mode)

    def fade_zoom_transition(self, new_mode):
        current_spread = self.spread_stack.currentWidget()
        if not current_spread:
            self.current_mode = new_mode
            # Update buttons styling
            for m, btn in self.mode_buttons.items():
                btn.setProperty("class", "pill selected" if m == new_mode else "pill")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.update_spread(direction=0)
            return

        # Create new spread for the new mode
        new_spread, new_left, new_right = self.create_spread_widget(self.current_spread_index, mode=new_mode)
        self.spread_stack.addWidget(new_spread)
        
        # Determine current stack geometry
        width = self.spread_stack.width()
        height = self.spread_stack.height()
        if width <= 0 or height <= 0:
            width = 750
            height = 550
            
        normal_rect = current_spread.geometry()
        if normal_rect.width() <= 0:
            normal_rect = QRect(0, 0, width, height)
            
        # Old shrink target: slightly smaller
        shrink_rect = QRect(
            int(normal_rect.x() + normal_rect.width() * 0.05),
            int(normal_rect.y() + normal_rect.height() * 0.05),
            int(normal_rect.width() * 0.9),
            int(normal_rect.height() * 0.9)
        )
        
        # New start rect: start from 0.9 scale
        grow_start_rect = QRect(
            int(normal_rect.x() + normal_rect.width() * 0.05),
            int(normal_rect.y() + normal_rect.height() * 0.05),
            int(normal_rect.width() * 0.9),
            int(normal_rect.height() * 0.9)
        )
        
        new_spread.setGeometry(grow_start_rect)
        new_spread.show()
        
        # Disable buttons temporarily during transition
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        for btn in self.mode_buttons.values():
            btn.setEnabled(False)
            
        # Set up opacity effects
        eff_old = QGraphicsOpacityEffect(current_spread)
        current_spread.setGraphicsEffect(eff_old)
        
        eff_new = QGraphicsOpacityEffect(new_spread)
        new_spread.setGraphicsEffect(eff_new)
        
        eff_old.setOpacity(1.0)
        eff_new.setOpacity(0.0)
        
        duration = 220
        
        # Create animations
        self.anim_opacity_old = QPropertyAnimation(eff_old, b"opacity", self)
        self.anim_opacity_old.setDuration(duration)
        self.anim_opacity_old.setStartValue(1.0)
        self.anim_opacity_old.setEndValue(0.0)
        self.anim_opacity_old.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_opacity_new = QPropertyAnimation(eff_new, b"opacity", self)
        self.anim_opacity_new.setDuration(duration)
        self.anim_opacity_new.setStartValue(0.0)
        self.anim_opacity_new.setEndValue(1.0)
        self.anim_opacity_new.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_geom_old = QPropertyAnimation(current_spread, b"geometry", self)
        self.anim_geom_old.setDuration(duration)
        self.anim_geom_old.setStartValue(normal_rect)
        self.anim_geom_old.setEndValue(shrink_rect)
        self.anim_geom_old.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_geom_new = QPropertyAnimation(new_spread, b"geometry", self)
        self.anim_geom_new.setDuration(duration)
        self.anim_geom_new.setStartValue(grow_start_rect)
        self.anim_geom_new.setEndValue(normal_rect)
        self.anim_geom_new.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Start animations
        self.anim_opacity_old.start()
        self.anim_opacity_new.start()
        self.anim_geom_old.start()
        self.anim_geom_new.start()
        
        # Update references and state
        self.current_mode = new_mode
        self.page_left = new_left
        self.page_right = new_right
        
        def on_finished():
            self.spread_stack.setCurrentWidget(new_spread)
            self.spread_stack.removeWidget(current_spread)
            current_spread.deleteLater()
            
            # Reset geometry constraints to normal
            new_spread.setGeometry(normal_rect)
            
            # Remove graphics effects so normal rendering behaves correctly
            new_spread.setGraphicsEffect(None)
            
            # Re-enable controls
            self.btn_prev.setEnabled(self.current_spread_index > 0)
            self.btn_next.setEnabled(True)
            for btn in self.mode_buttons.values():
                btn.setEnabled(True)
                
            # Update mode buttons selected style
            for m, btn in self.mode_buttons.items():
                btn.setProperty("class", "pill selected" if m == new_mode else "pill")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                
        self.anim_opacity_new.finished.connect(on_finished)
        
    def create_spread_widget(self, spread_index, mode=None):
        _, design, color, _ = self._get_current_folder_theme()
        spread_widget = BinderSpreadFrame(
            design=design,
            color=color,
            can_go_prev=(spread_index > 0),
        )
        spread_widget.drag_turn_started.connect(self._on_drag_turn_started)
        spread_widget.drag_turn_moved.connect(self._on_drag_turn_moved)
        spread_widget.drag_turn_released.connect(self._on_drag_turn_released)

        p_idx_1 = spread_index * 2
        p_idx_2 = p_idx_1 + 1

        target_mode = mode if mode else self.current_mode
        cfg = BINDER_MODES[target_mode]

        page_left = BinderPage(
            p_idx_1, self,
            rows=cfg["rows"],
            cols=cfg["cols"],
            slot_w=cfg["slot_w"],
            slot_h=cfg["slot_h"],
            card_w=cfg["card_w"],
            card_h=cfg["card_h"],
            is_left=True,
        )
        page_right = BinderPage(
            p_idx_2, self,
            rows=cfg["rows"],
            cols=cfg["cols"],
            slot_w=cfg["slot_w"],
            slot_h=cfg["slot_h"],
            card_w=cfg["card_w"],
            card_h=cfg["card_h"],
            is_left=False,
        )

        # Populate slots
        self.populate_page(page_left, p_idx_1, target_mode)
        self.populate_page(page_right, p_idx_2, target_mode)

        spread_widget.spread_layout.addWidget(page_left)
        spread_widget.spread_layout.addWidget(page_right)

        return spread_widget, page_left, page_right

    def update_spread(self, direction=0):
        new_spread, new_left, new_right = self.create_spread_widget(self.current_spread_index)

        # UI controls update
        p_idx_1 = self.current_spread_index * 2
        p_idx_2 = p_idx_1 + 1
        self.lbl_pages.setText(f"{t('Página')} {p_idx_1 + 1} - {p_idx_2 + 1}")
        self.btn_prev.setEnabled(self.current_spread_index > 0)
        self.btn_next.setEnabled(True)
        self.refresh_page_minimap()

        # Respect global animation setting
        from MyQtApp.config import load_settings
        settings = load_settings()
        animaciones_activas = settings.get("animaciones", True)

        if direction == 0 or not animaciones_activas:
            while self.spread_stack.count() > 0:
                widget = self.spread_stack.widget(0)
                self.spread_stack.removeWidget(widget)
                widget.deleteLater()

            self.spread_stack.addWidget(new_spread)
            self.spread_stack.setCurrentWidget(new_spread)
            self.page_left = new_left
            self.page_right = new_right
        else:
            self.flip_page_transition(new_spread, direction, new_left, new_right)

    def _capture_spread_geometries(self, spread_widget, left_w, right_w):
        """Retorna (board_rect, left_rect, right_rect) mapeados a self.spread_stack."""
        board_local = spread_widget.get_board_rect()
        b_tl = spread_widget.mapTo(self.spread_stack, board_local.topLeft().toPoint())
        board_rect = QRectF(float(b_tl.x()), float(b_tl.y()), board_local.width(), board_local.height())

        l_tl = left_w.mapTo(self.spread_stack, QPoint(0, 0))
        left_rect = QRectF(float(l_tl.x()), float(l_tl.y()), float(left_w.width()), float(left_w.height()))

        r_tl = right_w.mapTo(self.spread_stack, QPoint(0, 0))
        right_rect = QRectF(float(r_tl.x()), float(r_tl.y()), float(right_w.width()), float(right_w.height()))
        return board_rect, left_rect, right_rect

    def flip_page_transition(self, new_spread, direction, new_left, new_right):
        """Transición 3D realista de cambio de página con curvatura orgánica, sombras y anillas."""
        current_spread = self.spread_stack.currentWidget()
        if (
            not current_spread
            or not isinstance(current_spread, BinderSpreadFrame)
            or not self.page_left
            or not self.page_right
        ):
            self.spread_stack.addWidget(new_spread)
            self.spread_stack.setCurrentWidget(new_spread)
            self.page_left = new_left
            self.page_right = new_right
            return

        if self._active_flip_overlay is not None:
            try:
                self._active_flip_overlay.deleteLater()
            except Exception:
                pass
            self._active_flip_overlay = None

        # Capturar las 2 páginas actuales
        old_left_pix = self.page_left.grab()
        old_right_pix = self.page_right.grab()
        board_rect, left_rect, right_rect = self._capture_spread_geometries(
            current_spread, self.page_left, self.page_right
        )

        # Preparar nuevo pliego con la misma geometría exacta para capturar sus páginas
        self.spread_stack.addWidget(new_spread)
        new_spread.setGeometry(current_spread.geometry())
        new_spread.layout().activate()
        new_left_pix = new_left.grab()
        new_right_pix = new_right.grab()

        # Cambiar el widget subyacente de inmediato; el overlay 3D cubre la transición sin parpadeo
        self.spread_stack.setCurrentWidget(new_spread)
        self.spread_stack.removeWidget(current_spread)
        current_spread.deleteLater()

        self.page_left = new_left
        self.page_right = new_right
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)

        _, design, color, _ = self._get_current_folder_theme()
        overlay = PageFlipAnimationOverlay(
            parent=self.spread_stack,
            old_left_pix=old_left_pix,
            old_right_pix=old_right_pix,
            new_left_pix=new_left_pix,
            new_right_pix=new_right_pix,
            board_rect=board_rect,
            left_page_rect=left_rect,
            right_page_rect=right_rect,
            direction=direction,
            design=design,
            color=color,
        )
        self._active_flip_overlay = overlay

        def on_flip_done(_completed):
            self._active_flip_overlay = None
            self.btn_prev.setEnabled(self.current_spread_index > 0)
            self.btn_next.setEnabled(True)

        overlay.flip_completed.connect(on_flip_done)
        overlay.start_auto_flip(duration_ms=520, start_val=0.0, end_val=1.0)

    def _on_drag_turn_started(self, direction: int, start_x: float):
        """Inicia un giro de página interactivo arrastrando con el mouse desde el borde del binder."""
        if self._active_flip_overlay is not None or self._drag_turn_state is not None:
            return
        if direction == -1 and self.current_spread_index <= 0:
            return

        from MyQtApp.config import load_settings
        if not load_settings().get("animaciones", True):
            if direction == 1:
                self.next_spread()
            else:
                self.prev_spread()
            return

        current_spread = self.spread_stack.currentWidget()
        if not current_spread or not isinstance(current_spread, BinderSpreadFrame):
            return

        target_spread_index = self.current_spread_index + direction
        new_spread, new_left, new_right = self.create_spread_widget(target_spread_index)

        old_left_pix = self.page_left.grab()
        old_right_pix = self.page_right.grab()
        board_rect, left_rect, right_rect = self._capture_spread_geometries(
            current_spread, self.page_left, self.page_right
        )

        # Maquetar offscreen para capturar el pliego destino
        new_spread.setGeometry(current_spread.geometry())
        new_spread.layout().activate()
        new_left_pix = new_left.grab()
        new_right_pix = new_right.grab()

        _, design, color, _ = self._get_current_folder_theme()
        overlay = PageFlipAnimationOverlay(
            parent=self.spread_stack,
            old_left_pix=old_left_pix,
            old_right_pix=old_right_pix,
            new_left_pix=new_left_pix,
            new_right_pix=new_right_pix,
            board_rect=board_rect,
            left_page_rect=left_rect,
            right_page_rect=right_rect,
            direction=direction,
            design=design,
            color=color,
        )
        overlay.set_progress(0.05)
        self._active_flip_overlay = overlay
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)

        self._drag_turn_state = {
            "direction": direction,
            "start_x": start_x,
            "board_width": max(200.0, board_rect.width() * 0.85),
            "target_index": target_spread_index,
            "new_spread": new_spread,
            "new_left": new_left,
            "new_right": new_right,
            "current_spread": current_spread,
            "overlay": overlay,
        }

    def _on_drag_turn_moved(self, current_x: float):
        """Actualiza el ángulo de la hoja en tiempo real según la posición del cursor."""
        state = self._drag_turn_state
        if not state:
            return
        dx = (state["start_x"] - current_x) if state["direction"] == 1 else (current_x - state["start_x"])
        prog = max(0.02, min(0.98, 0.05 + dx / state["board_width"]))
        state["overlay"].set_progress(prog)

    def _on_drag_turn_released(self, _end_x: float):
        """Al soltar el mouse, completa el giro si pasó el umbral o regresa suavemente la hoja."""
        state = self._drag_turn_state
        if not state:
            return
        self._drag_turn_state = None
        overlay = state["overlay"]
        prog = overlay.progress()
        complete = prog >= 0.30

        def on_finish(did_complete):
            self._active_flip_overlay = None
            if did_complete:
                self.current_spread_index = state["target_index"]
                self.spread_stack.addWidget(state["new_spread"])
                self.spread_stack.setCurrentWidget(state["new_spread"])
                self.spread_stack.removeWidget(state["current_spread"])
                state["current_spread"].deleteLater()
                self.page_left = state["new_left"]
                self.page_right = state["new_right"]
                p_idx_1 = self.current_spread_index * 2
                p_idx_2 = p_idx_1 + 1
                self.lbl_pages.setText(f"{t('Página')} {p_idx_1 + 1} - {p_idx_2 + 1}")
                self.refresh_page_minimap()
            else:
                state["new_spread"].deleteLater()
            self.btn_prev.setEnabled(self.current_spread_index > 0)
            self.btn_next.setEnabled(True)

        overlay.flip_completed.connect(on_finish)
        if complete:
            rem_ms = max(140, int(420 * (1.0 - prog)))
            overlay.start_auto_flip(duration_ms=rem_ms, start_val=prog, end_val=1.0)
        else:
            rem_ms = max(140, int(360 * prog))
            overlay.start_auto_flip(duration_ms=rem_ms, start_val=prog, end_val=0.0)

    def populate_page(self, page_widget, page_idx, mode=None):
        session = SessionLocal()
        try:
            target_mode = mode if mode else self.current_mode
            cfg = BINDER_MODES[target_mode]
            slots_per_page = cfg["rows"] * cfg["cols"]
            for i in range(slots_per_page):
                card_info = self.get_card_at(page_idx, i, target_mode)
                slot = page_widget.get_slot(i)
                if card_info and slot:
                    card_id = None
                    card_lang = "en"
                    card_var = "Normal"
                    if isinstance(card_info, dict):
                        card_id = card_info.get("id_api")
                        card_lang = card_info.get("idioma", "en")
                        card_var = card_info.get("variante", "Normal")
                    elif isinstance(card_info, str):
                        if ":" in card_info:
                            card_id, card_lang = card_info.split(":", 1)
                        else:
                            card_id = card_info

                    if card_id:
                        carta = session.query(Cartas).filter(Cartas.id_api == card_id, Cartas.idioma == card_lang).first()
                        if not carta:
                            carta = session.query(Cartas).filter(Cartas.id_api == card_id).first()

                        if carta:
                            c_lang = carta.idioma or card_lang
                            nombre = carta.nombre
                            nombre_archivo = nombre.lower().replace(" ", "_")

                            pixmap = get_webp_pixmap(card_id, nombre, c_lang, size=(cfg["card_w"], cfg["card_h"]))
                            if not pixmap:
                                pixmap = get_pixmap_from_zip(nombre_archivo, size=(cfg["card_w"], cfg["card_h"]), id_api=card_id)
                            if not pixmap:
                                ruta_alt = os.path.join(IMAGES_DIR, f"{nombre_archivo}_{card_id}.webp")
                                if os.path.exists(ruta_alt):
                                    pixmap = QPixmap(ruta_alt)
                            if not pixmap or pixmap.isNull():
                                pixmap = get_card_placeholder_pixmap((cfg["card_w"], cfg["card_h"]), nombre)

                            slot.set_card(card_id, nombre_archivo, pixmap, idioma=c_lang, variante=card_var, carta=carta)
        finally:
            session.close()

    def update_slot_variant(self, page, slot, nueva_variante):
        target_mode = self.current_mode
        cards_dict = self._get_current_cards_dict(target_mode)
        key = f"{page}_{slot}"
        existing = cards_dict.get(key)
        
        if isinstance(existing, dict):
            existing["variante"] = nueva_variante
            cards_dict[key] = existing
        elif isinstance(existing, str):
            cards_dict[key] = {
                "id_api": existing,
                "variante": nueva_variante
            }
        else:
            return

        self.save_binder_data()
        show_toast(f"Variante en Binder guardada: {nueva_variante}", "info")


    def handle_drop(self, page_idx, slot_idx, card_id, source_slot=None, nombre_archivo=None, idioma=None, variante="Normal"):
        if not idioma:
            idioma = "en"

        card_data_entry = {"id_api": card_id, "idioma": idioma, "variante": variante or "Normal"}

        # If the drag came from another slot in the binder
        if source_slot:
            try:
                src_page_str, src_slot_str = source_slot.split('_')
                src_page = int(src_page_str)
                src_slot = int(src_slot_str)
                
                # If target is different from source
                if src_page != page_idx or src_slot != slot_idx:
                    # Clear old slot in data
                    self.set_card_at(src_page, src_slot, None)
                    
                    # Clear old slot in UI (if it's on the currently visible pages)
                    src_page_widget = None
                    if src_page == self.current_spread_index * 2:
                        src_page_widget = self.page_left
                    elif src_page == self.current_spread_index * 2 + 1:
                        src_page_widget = self.page_right
                        
                    if src_page_widget:
                        slot = src_page_widget.get_slot(src_slot)
                        if slot:
                            slot.clear_card()
            except Exception as e:
                print(f"Error resolving source slot during move: {e}")

        # Update data
        self.set_card_at(page_idx, slot_idx, card_data_entry)
        
        # Find the specific slot widget
        target_page_widget = None
        if page_idx == self.current_spread_index * 2:
            target_page_widget = self.page_left
        elif page_idx == self.current_spread_index * 2 + 1:
            target_page_widget = self.page_right
            
        if target_page_widget:
            slot = target_page_widget.get_slot(slot_idx)
            if slot:
                cfg = BINDER_MODES[self.current_mode]
                session = SessionLocal()
                try:
                    carta = session.query(Cartas).filter(Cartas.id_api == card_id, Cartas.idioma == idioma).first()
                    if not carta:
                        carta = session.query(Cartas).filter(Cartas.id_api == card_id).first()

                    if carta:
                        n_archivo = carta.nombre.lower().replace(" ", "_")
                        c_lang = carta.idioma or idioma
                        pixmap = get_webp_pixmap(card_id, carta.nombre, c_lang, size=(cfg["card_w"], cfg["card_h"]))
                        if not pixmap:
                            pixmap = get_pixmap_from_zip(n_archivo, size=(cfg["card_w"], cfg["card_h"]), id_api=card_id)
                        if not pixmap:
                            ruta_alt = os.path.join(IMAGES_DIR, f"{n_archivo}_{card_id}.webp")
                            if os.path.exists(ruta_alt):
                                pixmap = QPixmap(ruta_alt)
                        if not pixmap or pixmap.isNull():
                            pixmap = get_card_placeholder_pixmap((cfg["card_w"], cfg["card_h"]), carta.nombre)
                        slot.set_card(card_id, n_archivo, pixmap, idioma=c_lang, variante=variante, carta=carta, animate_insert=True)
                finally:
                    session.close()

        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()

    def refresh_page_minimap(self):
        """Actualiza la tira de mini-pliegos con la ocupación actual de cartas por página."""
        if not hasattr(self, "page_minimap") or not self.page_minimap:
            return
        cards_dict = self._get_current_cards_dict(self.current_mode)
        page_counts = {}
        for key, val in cards_dict.items():
            if not val:
                continue
            try:
                p_str, _ = key.split("_", 1)
                p_idx = int(p_str)
                page_counts[p_idx] = page_counts.get(p_idx, 0) + 1
            except Exception:
                continue
        cfg = BINDER_MODES.get(self.current_mode, BINDER_MODES["3x3"])
        slots_per_page = cfg["rows"] * cfg["cols"]
        self.page_minimap.refresh(self.current_spread_index, page_counts, slots_per_page)

    def jump_to_spread(self, target_spread_index: int):
        """Salta directamente a un pliego del mini-mapa usando la animación 3D de giro de página."""
        if target_spread_index < 0 or target_spread_index == self.current_spread_index:
            return
        if self._active_flip_overlay is not None or self._active_open_overlay is not None:
            return
        direction = 1 if target_spread_index > self.current_spread_index else -1
        self.current_spread_index = target_spread_index
        self.update_spread(direction=direction)

    def prev_spread(self):
        if self.current_spread_index > 0:
            self.current_spread_index -= 1
            self.update_spread(direction=-1)
            
    def clear_binder(self):
        # Clear data for this user for the current mode in the current folder
        cards_dict = self._get_current_cards_dict(self.current_mode)
        cards_dict.clear()
        self.save_binder_data()
        self.update_spread(direction=0)
        self.actualizar_resumen_precios_binder()
        
    def next_spread(self):
        self.current_spread_index += 1
        self.update_spread(direction=1)

    # Should be called if Inventory changes (e.g. from Index)
    def refresh_inventory(self):
        self.inventory.refresh()
