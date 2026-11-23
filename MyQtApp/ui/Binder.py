import copy
import json
import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, 
    QGridLayout, QFrame, QPushButton, QApplication, QSizePolicy,
    QStackedWidget, QGraphicsOpacityEffect, QLineEdit, QComboBox,
    QDialog, QMessageBox, QColorDialog, QMenu, QFileDialog, QTabWidget
)
from PyQt6.QtCore import Qt, QMimeData, QPoint, QPointF, QSize, QEasingCurve, QPropertyAnimation, QRect, QRectF, QTimer, pyqtSignal
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
from MyQtApp.ui.BinderCoverWidget import (
    BinderCoverWidget, BINDER_DESIGNS, resolve_design_key,
    BINDER_COVERS_DIR, get_design_default_interior_color
)
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
                mime_data.setProperty("variante", getattr(self, "variante", "Normal") or "Normal")
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
        # Adaptar contraste del bolsillo al color interior de la hoja (Issue #28)
        is_light_page = False
        try:
            p = self.parent()
            if p is not None and hasattr(p, "interior_color") and p.interior_color:
                ic = QColor(p.interior_color)
                if ic.isValid():
                    luma = 0.299 * ic.red() + 0.587 * ic.green() + 0.114 * ic.blue()
                    is_light_page = luma > 155
        except Exception:
            is_light_page = False

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
                border_col = "rgba(15, 23, 42, 0.25)" if is_light_page else "rgba(255, 255, 255, 0.22)"
                bg_col = "rgba(15, 23, 42, 0.04)" if is_light_page else "rgba(255, 255, 255, 0.04)"
                self.setStyleSheet(f"""
                    QLabel {{
                        background-color: {bg_col};
                        border: 1.5px solid {border_col};
                        border-radius: 7px;
                    }}
                """)
        else:
            self.selected = False
            empty_bg = "rgba(15, 23, 42, 0.05)" if is_light_page else "rgba(255, 255, 255, 0.05)"
            empty_border = "rgba(15, 23, 42, 0.28)" if is_light_page else "rgba(255, 255, 255, 0.22)"
            hover_bg = "rgba(244, 143, 177, 0.16)" if is_light_page else "rgba(255, 255, 255, 0.11)"
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {empty_bg};
                    border: 1.5px dashed {empty_border};
                    border-radius: 7px;
                }}
                QLabel:hover {{
                    background-color: {hover_bg};
                    border: 1.5px dashed rgba(244, 143, 177, 0.85);
                }}
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

    def clear_card(self, animate_remove: bool = False):
        old_pix = None
        if animate_remove:
            try:
                from MyQtApp.config import load_settings
                if load_settings().get("animaciones", True) and self.pixmap() and not self.pixmap().isNull():
                    old_pix = self.pixmap().copy()
            except Exception:
                old_pix = None

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

        if old_pix is not None and not old_pix.isNull():
            try:
                self._slide_out_overlay = CardSlideInOverlay(self, old_pix, reverse=True)
            except Exception as e:
                print(f"Error en animación de salida de carta: {e}")


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
            variante = event.mimeData().property("variante") or "Normal"
            
            if card_id:
                # Tell the main view to handle the drop (update logic and UI)
                if self.binder_view:
                    self.binder_view.handle_drop(
                        self.page_index, self.slot_index, card_id, 
                        source_slot=source_slot, nombre_archivo=nombre_archivo, idioma=idioma,
                        variante=variante
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
                mime_data.setProperty("variante", getattr(self, "variante", "Normal") or "Normal")
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
    card_removed_from_binder = pyqtSignal(str)  # emits source_slot (e.g. "0_3")

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.coleccion_activa = None  # None = Todas las colecciones
        self.orden_activo = None      # None | "rarity" | "type" | "idioma"
        self.setAcceptDrops(True)

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

        # Banner de zona de soltado para devolver cartas desde el binder (Issue #23)
        self.drop_remove_banner = QLabel(t("Suelta aquí para quitar del binder"))
        self.drop_remove_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_remove_banner.setWordWrap(True)
        self.drop_remove_banner.setStyleSheet("""
            QLabel {
                background-color: #fee2e2;
                color: #b91c1c;
                border: 2px dashed #ef4444;
                border-radius: 10px;
                padding: 8px 6px;
                font-size: 11px;
                font-weight: 700;
            }
        """)
        self.drop_remove_banner.hide()
        layout.addWidget(self.drop_remove_banner)

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

        # 2. Botones "Colección" y "Ordenar" con letra oscura de alto contraste (Issue #42)
        btns_row = QHBoxLayout()
        btns_row.setContentsMargins(0, 0, 0, 0)
        btns_row.setSpacing(6)

        sidebar_btn_style = """
            QPushButton {
                background-color: #ffd6e0;
                color: #3b1723;
                border-radius: 9px;
                padding: 5px 8px;
                font-weight: 700;
                font-size: 12px;
                border: 1.5px solid #e08fa0;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #f7a8b8;
                color: #2b0f18;
                border-color: #d44854;
            }
            QPushButton:pressed {
                background-color: #f29ca4;
                color: #1f0a11;
            }
        """

        self.btn_coleccion = QPushButton(t("Colección"))
        self.btn_coleccion.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_coleccion.setStyleSheet(sidebar_btn_style)
        self._apply_dark_text_button_palette(self.btn_coleccion)
        self.btn_coleccion.clicked.connect(self._mostrar_menu_coleccion)
        btns_row.addWidget(self.btn_coleccion, 1)

        self.btn_ordenar = QPushButton(t("Ordenar"))
        self.btn_ordenar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ordenar.setStyleSheet(sidebar_btn_style)
        self._apply_dark_text_button_palette(self.btn_ordenar)
        self.btn_ordenar.clicked.connect(self._mostrar_menu_ordenar)
        btns_row.addWidget(self.btn_ordenar, 1)

        layout.addLayout(btns_row)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #fff7f8; border: none;")

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(4, 6, 4, 6)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.load_cards()

    def _apply_dark_text_button_palette(self, btn: QPushButton):
        from PyQt6.QtGui import QPalette
        pal = btn.palette()
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#3b1723"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#3b1723"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#3b1723"))
        btn.setPalette(pal)

    def _create_styled_popup_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setMinimumWidth(165)
        menu.setMaximumWidth(220)
        from PyQt6.QtGui import QPalette
        pal = menu.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#e25b70"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        menu.setPalette(pal)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 16px 6px 10px;
                border-radius: 5px;
                color: #f8fafc;
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
            QMenu::separator {
                height: 1px;
                background: #334155;
                margin: 4px 8px;
            }
        """)
        return menu

    def _mostrar_menu_coleccion(self):
        """Despliega menú de tamaño prudente para filtrar por una colección creada en específico (Issue #42)."""
        from MyQtApp.app.db_services import obtener_categorias_usuario
        cats = obtener_categorias_usuario(self.usuario)
        if self.coleccion_activa and self.coleccion_activa not in cats:
            self.coleccion_activa = None

        menu = self._create_styled_popup_menu()

        act_todas = QAction(t("Todas"), menu)
        act_todas.setCheckable(True)
        act_todas.setChecked(self.coleccion_activa is None)
        act_todas.triggered.connect(lambda: self._seleccionar_coleccion_filtro(None))
        menu.addAction(act_todas)

        if cats:
            menu.addSeparator()
            for cat in cats:
                act_cat = QAction(cat, menu)
                act_cat.setCheckable(True)
                act_cat.setChecked(self.coleccion_activa == cat)
                act_cat.triggered.connect(lambda checked=False, c=cat: self._seleccionar_coleccion_filtro(c))
                menu.addAction(act_cat)

        menu.exec(self.btn_coleccion.mapToGlobal(QPoint(0, self.btn_coleccion.height() + 2)))

    def _seleccionar_coleccion_filtro(self, coleccion):
        self.coleccion_activa = coleccion
        if coleccion:
            self.btn_coleccion.setToolTip(f"{t('Colección')}: {coleccion}")
        else:
            self.btn_coleccion.setToolTip(t("Colección"))
        self.load_cards()

    def _mostrar_menu_ordenar(self):
        """Despliega menú para ordenar las cartas por Rareza, Energía e Idioma (Issue #42)."""
        menu = self._create_styled_popup_menu()

        opciones = [
            (t("Rareza"), "rarity"),
            (t("Energía"), "type"),
            (t("Idioma"), "idioma"),
        ]
        for label, key in opciones:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.orden_activo == key)
            act.triggered.connect(lambda checked=False, k=key: self._seleccionar_orden(k))
            menu.addAction(act)

        if self.orden_activo is not None:
            menu.addSeparator()
            act_reset = QAction(t("Por defecto"), menu)
            act_reset.triggered.connect(lambda: self._seleccionar_orden(None))
            menu.addAction(act_reset)

        menu.exec(self.btn_ordenar.mapToGlobal(QPoint(0, self.btn_ordenar.height() + 2)))

    def _seleccionar_orden(self, clave_orden):
        if self.orden_activo == clave_orden and clave_orden is not None:
            # Si vuelve a pulsar el mismo criterio activo, alterna a por defecto
            self.orden_activo = None
        else:
            self.orden_activo = clave_orden
        self.load_cards()

    def retranslate_ui(self):
        self.header.setText(t("Colección"))
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        if hasattr(self, "btn_coleccion"):
            self.btn_coleccion.setText(t("Colección"))
        if hasattr(self, "btn_ordenar"):
            self.btn_ordenar.setText(t("Ordenar"))

    def cargar_opciones_filtros(self):
        """Método mantenido por compatibilidad con llamadas externas."""
        pass

    def _create_single_card_widget(self, carta, variante_db="Normal"):
        """Crea el widget de carta individual con su idioma y variante respectivos, igual que en Colecciones (Issue #43)."""
        id_api = carta.id_api
        card_lang = getattr(carta, "idioma", None) or "es"
        variante = variante_db or "Normal"
        nombre = carta.nombre or ""
        nombre_archivo = nombre.lower().replace(" ", "_")
        card_size = (120, 170)

        pixmap = get_webp_pixmap(id_api, nombre, card_lang, size=card_size, allow_lang_fallback=False)
        if not pixmap:
            pixmap = get_webp_pixmap(id_api, nombre, card_lang, size=card_size, allow_lang_fallback=True)
        if not pixmap:
            pixmap = get_pixmap_from_zip(nombre_archivo, size=card_size, id_api=id_api)
        if not pixmap:
            ruta_alt = os.path.join(IMAGES_DIR, f"{nombre_archivo}_{id_api}.webp")
            if os.path.exists(ruta_alt):
                pixmap = QPixmap(ruta_alt).scaled(
                    card_size[0], card_size[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
        if not pixmap or pixmap.isNull():
            pixmap = get_card_placeholder_pixmap(card_size, nombre)

        card_lbl = DraggableCardLabel(id_api, nombre_archivo, pixmap)
        card_lbl.setFixedSize(card_size[0], card_size[1])
        card_lbl.idioma = card_lang
        card_lbl.variante = variante

        # Botón vertical de variante (arriba a la izquierda, igual que en Colecciones)
        variant_badge = VariantBadgeButton(id_api, variante, card_lbl)
        variant_badge.move(3, 3)
        variant_badge.raise_()

        def _on_var_changed(_cid, nueva_var):
            card_lbl.variante = nueva_var
            self._actualizar_variante_bd(id_api, card_lang, nueva_var)

        variant_badge.variant_changed.connect(_on_var_changed)

        # Botón de información (arriba a la derecha, igual que en Colecciones)
        info_btn = InfoIconLabel(carta, card_lbl)
        info_btn.move(card_size[0] - 26, 3)
        info_btn.raise_()

        # Insignia distintiva de idioma (abajo a la izquierda, igual que en Colecciones)
        lang_badge = LanguageBadgeLabel(card_lang, card_lbl)
        badge_h = lang_badge.height()
        lang_badge.move(3, card_size[1] - badge_h - 3)
        lang_badge.raise_()

        # Indicador geométrico de rareza (abajo a la derecha, igual que en Colecciones)
        from MyQtApp.ui.FilterVisualBar import RaritySymbolBadge
        rarity_badge = RaritySymbolBadge(getattr(carta, "rarity", None), card_lbl)
        rarity_badge.move(card_size[0] - rarity_badge.width() - 3, card_size[1] - rarity_badge.height() - 3)
        rarity_badge.raise_()

        price_val = f"${carta.price:.2f}" if (carta.price and carta.price > 0) else "N/A"
        card_lbl.setToolTip(
            f"<b>{nombre}</b><br/>ID: {id_api}<br/>Idioma: {card_lang.upper()}<br/>"
            f"Tipo: {carta.type or 'N/A'}<br/>Rareza: {carta.rarity or 'N/A'}<br/>Precio: {price_val} USD"
        )
        return card_lbl

    def _actualizar_variante_bd(self, id_api: str, card_lang: str, nueva_variante: str):
        session = SessionLocal()
        try:
            rel = (
                session.query(UsuarioCarta)
                .filter(
                    UsuarioCarta.usuario_nombre == self.usuario,
                    UsuarioCarta.carta_id == id_api,
                    func.coalesce(UsuarioCarta.idioma, "es") == card_lang,
                )
                .first()
            )
            if rel:
                rel.variante = nueva_variante
                session.commit()
                show_toast(f"Variante actualizada: {nueva_variante}", "info")
        except Exception as e:
            session.rollback()
            print(f"Error actualizando variante desde sidebar de binder: {e}")
        finally:
            session.close()

    def load_cards(self):
        session = SessionLocal()
        try:
            from sqlalchemy import and_, func
            from MyQtApp.app.db_services import obtener_categorias_usuario

            if self.coleccion_activa:
                cats = obtener_categorias_usuario(self.usuario)
                if self.coleccion_activa not in cats:
                    self.coleccion_activa = None

            query = (
                session.query(Cartas, UsuarioCarta.variante)
                .join(UsuarioCarta, and_(
                    Cartas.id_api == UsuarioCarta.carta_id,
                    func.coalesce(Cartas.idioma, 'es') == func.coalesce(UsuarioCarta.idioma, 'es')
                ))
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
            )

            # 1. Filtrar por colección específica si está seleccionada (Issue #42)
            if self.coleccion_activa:
                query = query.filter(UsuarioCarta.categoria == self.coleccion_activa)

            # 2. Buscar por nombre
            texto = self.buscador.text().strip().lower()
            if texto:
                query = query.filter(func.lower(Cartas.nombre).like(f"%{texto}%"))

            rows = query.all()

            # 3. Ordenar por Rareza, Energía o Idioma si está activo (Issue #42)
            if self.orden_activo == "rarity":
                rows.sort(key=lambda r: ((r[0].rarity or "zzz").lower(), (r[0].nombre or "").lower()))
            elif self.orden_activo == "type":
                rows.sort(key=lambda r: ((r[0].type or "zzz").lower(), (r[0].nombre or "").lower()))
            elif self.orden_activo == "idioma":
                rows.sort(key=lambda r: ((r[0].idioma or "es").lower(), (r[0].nombre or "").lower()))

            # Limpiar área de cartas
            for i in reversed(range(self.cards_layout.count())):
                item = self.cards_layout.itemAt(i)
                if item and item.widget():
                    item.widget().deleteLater()

            for carta, variante_db in rows:
                item_widget = self._create_single_card_widget(carta, variante_db)
                if item_widget:
                    self.cards_layout.addWidget(item_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        finally:
            session.close()

    def refresh(self):
        self.cargar_opciones_filtros()
        self.load_cards()

    def _is_binder_drag(self, event) -> bool:
        try:
            md = event.mimeData()
            return bool(md and md.hasText() and md.property("source") == "binder" and md.property("source_slot"))
        except Exception:
            return False

    def dragEnterEvent(self, event):
        if self._is_binder_drag(event):
            self.drop_remove_banner.show()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._is_binder_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_remove_banner.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_remove_banner.hide()
        if self._is_binder_drag(event):
            source_slot = event.mimeData().property("source_slot")
            if source_slot:
                self.card_removed_from_binder.emit(str(source_slot))
            event.acceptProposedAction()
        else:
            event.ignore()


class BinderPage(QWidget):
    def __init__(self, page_index, binder_view, rows, cols, slot_w, slot_h, card_w, card_h, is_left=True, interior_color=None, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.binder_view = binder_view
        self.rows = rows
        self.cols = cols
        self.is_left = is_left
        self.interior_color = interior_color or "#18181e"

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
                    parent=self,
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

        # Base de hoja personalizable estilo Ultra PRO (negro mate por defecto o color elegido)
        base_col = QColor(self.interior_color)
        if not base_col.isValid():
            base_col = QColor(24, 24, 30)
        c_top = base_col.lighter(120)
        c_top.setAlpha(242)
        c_mid = QColor(base_col)
        c_mid.setAlpha(246)
        c_bot = base_col.darker(122)
        c_bot.setAlpha(250)

        # Determinar contraste de costuras según luminosidad del color interior
        luma = 0.299 * base_col.red() + 0.587 * base_col.green() + 0.114 * base_col.blue()
        seam_col = QColor(20, 20, 30, 50) if luma > 155 else QColor(255, 255, 255, 26)
        border_col = QColor(20, 20, 30, 70) if luma > 155 else QColor(255, 255, 255, 40)

        sheet_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        sheet_grad.setColorAt(0.0, c_top)
        sheet_grad.setColorAt(0.5, c_mid)
        sheet_grad.setColorAt(1.0, c_bot)
        painter.setBrush(sheet_grad)
        painter.setPen(QPen(border_col, 1.2))
        painter.drawRoundedRect(rect, 7, 7)

        # Costuras termoselladas sutiles entre los bolsillos
        seam_pen = QPen(seam_col, 1.0, Qt.PenStyle.DotLine)
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
    open_binder_in_print_requested = pyqtSignal(str, str)  # (folder_id, mode: "print" | "csv")

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
        self.inventory.card_removed_from_binder.connect(self.quitar_carta_arrastrada)
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

        self.btn_edit_current_folder = QPushButton(t("Editar"))
        self.btn_edit_current_folder.setFixedHeight(30)
        self.btn_edit_current_folder.setProperty("class", "pill")
        self.btn_edit_current_folder.setToolTip(t("Editar portada, imagen, colores y opciones del binder actual"))
        self.btn_edit_current_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_current_folder.clicked.connect(self.editar_carpeta_actual)
        header_layout.addWidget(self.btn_edit_current_folder)

        header_layout.addStretch()

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
                        custom_image, _interior, locked = self._get_current_folder_extra()
                        cover_w = max(140, int(board_local.width() * 0.5))
                        cover_h = max(180, int(board_local.height()))
                        cover_pix = render_transparent_cover_pixmap(
                            name, design, color, mode, cover_w, cover_h,
                            custom_image=custom_image, locked=locked
                        )

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

    def _get_current_folder_extra(self) -> tuple[str | None, str, bool]:
        """Retorna (custom_image, interior_color, locked) de la carpeta actual."""
        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id, {})
        design = resolve_design_key(folder.get("design", "Charizard Fuego"))
        custom_image = folder.get("custom_image") or None
        interior_color = folder.get("interior_color") or get_design_default_interior_color(design)
        locked = bool(folder.get("locked", False))
        return custom_image, interior_color, locked

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
            custom_image, _interior, locked = self._get_current_folder_extra()
            cover_w = max(140, int(board_local.width() * 0.5))
            cover_h = max(180, int(board_local.height()))
            cover_pix = render_transparent_cover_pixmap(
                name, design, color, mode, cover_w, cover_h,
                custom_image=custom_image, locked=locked
            )

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
                "TCGMatch": ("#eff6ff", "#1d4ed8", "#93c5fd"),
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
            pill.setToolTip(t("Presiona 'Cotizar Mercado' para comparar precios entre TCGPlayer, TCGMatch y PokemonTCG"))
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
        """Crea la tarjeta visual de un Binder con portada física realista Ultra PRO y menú '...' (sin emojis)."""
        name = f_data.get("name", "Carpeta")
        color = f_data.get("color", "auto")
        design = resolve_design_key(f_data.get("design", "Charizard Fuego"))
        mode = f_data.get("mode", "3x3")
        custom_image = f_data.get("custom_image") or None
        locked = bool(f_data.get("locked", False))

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

        # Portada física realista del Binder (Issue #13 / #21)
        cover = BinderCoverWidget(
            name=name,
            design=design,
            color=color,
            mode=mode,
            custom_image=custom_image,
            locked=locked,
            parent=frame,
        )
        cover.setFixedSize(196, 212)
        self._folder_cover_widgets[f_id] = cover
        layout.addWidget(cover, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Resumen de precio acumulativo de mercado
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

        # Fila inferior: cantidad de cartas + menú '...' de acciones del binder (Issue #21)
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(2, 0, 2, 0)
        bottom_row.setSpacing(6)

        lbl_count = QLabel(f"{cant_cartas} cartas  |  {mode}")
        lbl_count.setStyleSheet("font-size: 11px; font-weight: 600; color: #703043; border: none; background: transparent;")
        bottom_row.addWidget(lbl_count)
        bottom_row.addStretch()

        btn_more = QPushButton("...")
        btn_more.setFixedSize(30, 24)
        btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_more.setToolTip(t("Opciones del binder"))
        btn_more.setStyleSheet("""
            QPushButton {
                background: #fff0f4;
                color: #703043;
                border: 1.5px solid #f2c4ce;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 800;
                padding: 0 0 4px 0;
            }
            QPushButton:hover {
                background: #f7a8b8;
                color: #ffffff;
                border-color: #f56b7b;
            }
        """)
        btn_more.clicked.connect(
            lambda ch=False, target_id=f_id, anchor=btn_more: self._abrir_menu_carpeta(target_id, anchor)
        )
        bottom_row.addWidget(btn_more)

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

    def _abrir_menu_carpeta(self, folder_id: str, anchor_btn: QPushButton):
        """Despliega el menú contextual '...' con acciones sobre el binder."""
        folders = self.get_user_folders()
        f_data = folders.get(folder_id)
        if not f_data:
            return
        name = f_data.get("name", "Carpeta")
        is_locked = bool(f_data.get("locked", False))

        menu = QMenu(self)
        from PyQt6.QtGui import QPalette
        pal = menu.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#e25b70"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        menu.setPalette(pal)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 18px 6px 12px;
                border-radius: 5px;
                color: #f8fafc;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #e25b70;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #64748b;
            }
            QMenu::separator {
                height: 1px;
                background: #334155;
                margin: 4px 8px;
            }
        """)

        act_lock = QAction(t("Desbloquear") if is_locked else t("Bloquear"), menu)
        act_lock.triggered.connect(lambda: self._toggle_bloquear_carpeta(folder_id))
        menu.addAction(act_lock)

        act_edit = QAction(t("Editar"), menu)
        act_edit.setEnabled(not is_locked)
        act_edit.triggered.connect(lambda: self.abrir_dialogo_editar_carpeta(folder_id))
        menu.addAction(act_edit)

        act_dup = QAction(t("Duplicar"), menu)
        act_dup.triggered.connect(lambda: self._duplicar_carpeta(folder_id))
        menu.addAction(act_dup)

        menu.addSeparator()

        act_print = QAction(t("Imprimir"), menu)
        act_print.triggered.connect(lambda: self.open_binder_in_print_requested.emit(folder_id, "print"))
        menu.addAction(act_print)

        menu.addSeparator()

        act_del = QAction(t("Eliminar"), menu)
        act_del.setEnabled(not is_locked)
        act_del.triggered.connect(lambda: self._eliminar_carpeta_directa(folder_id, name))
        menu.addAction(act_del)

        menu.exec(anchor_btn.mapToGlobal(QPoint(0, anchor_btn.height() + 2)))

    def _toggle_bloquear_carpeta(self, folder_id: str):
        folders = self.get_user_folders()
        f_data = folders.get(folder_id)
        if not f_data:
            return
        new_state = not bool(f_data.get("locked", False))
        f_data["locked"] = new_state
        self.save_binder_data()
        self.render_folders_grid()
        msg = t("Binder bloqueado (protegido contra edición y eliminación)") if new_state else t("Binder desbloqueado")
        show_toast(msg, "info")

    def _duplicar_carpeta(self, folder_id: str):
        folders = self.get_user_folders()
        orig = folders.get(folder_id)
        if not orig:
            return
        import time
        new_id = f"folder_{int(time.time() * 1000)}"
        cloned = copy.deepcopy(orig)
        cloned["name"] = f"{orig.get('name', 'Binder')} (Copia)"
        cloned["locked"] = False
        folders[new_id] = cloned
        self.save_binder_data()
        self.render_folders_grid()
        self.update_folder_combo()
        show_toast(f"{t('Binder duplicado')}: {cloned['name']}", "success")

    def editar_carpeta_actual(self):
        if not self.current_folder_id:
            return
        folders = self.get_user_folders()
        f_data = folders.get(self.current_folder_id, {})
        if f_data.get("locked", False):
            show_toast(t("Este binder está bloqueado. Desbloquéalo desde Mis Binders para editarlo."), "warning", 3000)
            return
        self.abrir_dialogo_editar_carpeta(self.current_folder_id)

    def _eliminar_carpeta_directa(self, folder_id, folder_name):
        folders = self.get_user_folders()
        if len(folders) <= 0:
            return
        if folders.get(folder_id, {}).get("locked", False):
            show_toast(t("Este binder está bloqueado y no se puede eliminar."), "warning", 2500)
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

    def on_folder_selected(self, index):
        folder_id = self.combo_folders.currentData()
        if not folder_id or folder_id == self.current_folder_id:
            return
        self.abrir_carpeta(folder_id)

    def abrir_dialogo_crear_carpeta(self):
        self._abrir_dialogo_binder(edit_folder_id=None)

    def abrir_dialogo_editar_carpeta(self, folder_id: str):
        folders = self.get_user_folders()
        if folder_id not in folders:
            return
        if folders[folder_id].get("locked", False):
            show_toast(t("Este binder está bloqueado. Desbloquéalo primero para editarlo."), "warning", 2500)
            return
        self._abrir_dialogo_binder(edit_folder_id=folder_id)

    def _abrir_dialogo_binder(self, edit_folder_id: str | None = None):
        folders = self.get_user_folders()
        editing = edit_folder_id is not None and edit_folder_id in folders
        existing = folders.get(edit_folder_id, {}) if editing else {}

        dlg = QDialog(self)
        dlg.setWindowTitle(t("Editar Binder") if editing else t("Crear Nuevo Binder"))
        dlg.setFixedSize(640, 475)
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
                padding: 6px 10px;
                background-color: #ffffff;
                color: #5a2a3a;
                font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #ffffff;
                selection-background-color: #e25b70;
                selection-color: #ffffff;
                border: 1.5px solid #f7a8b8;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                color: #ffffff;
                background-color: #0f172a;
                padding: 6px 10px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #e25b70;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #f56b7b;
            }
            QTabWidget::pane {
                border: 1.5px solid #f2c4ce;
                border-radius: 10px;
                background-color: #ffffff;
                padding: 6px;
            }
            QTabBar::tab {
                background-color: #ffeef2;
                color: #703043;
                border: 1.5px solid #f2c4ce;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 6px 16px;
                font-weight: 700;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #f56b7b;
                color: #ffffff;
                border-color: #e25b70;
            }
        """)

        outer_layout = QHBoxLayout(dlg)
        outer_layout.setContentsMargins(20, 18, 20, 18)
        outer_layout.setSpacing(18)

        default_design = resolve_design_key(existing.get("design", list(BINDER_DESIGNS.keys())[0]))
        init_name = existing.get("name", "") if editing else ""
        init_mode = existing.get("mode", "3x3") if editing else "3x3"
        init_color = existing.get("color", "auto") if editing else "auto"
        init_custom_image = existing.get("custom_image") if editing else None
        init_interior = (
            existing.get("interior_color")
            if editing and existing.get("interior_color")
            else get_design_default_interior_color(default_design)
        )
        is_custom_initially = bool(
            editing and (init_custom_image or (init_color and init_color not in ("", "auto", "#ffeef2")))
        )

        # --- Columna Izquierda: Vista previa física en vivo + muestra de color interior ---
        preview_panel = QFrame()
        preview_panel.setFixedWidth(218)
        preview_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 14px;
            }
        """)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        lbl_prev_title = QLabel(t("Vista Previa"))
        lbl_prev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_prev_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #8c5464; border: none; background: transparent;")
        preview_layout.addWidget(lbl_prev_title)

        live_preview = BinderCoverWidget(
            name=init_name or "Mi Binder",
            design=default_design,
            color=init_color,
            mode=init_mode,
            custom_image=init_custom_image,
            parent=preview_panel,
        )
        live_preview.setFixedSize(190, 246)
        preview_layout.addWidget(live_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_int_prev_title = QLabel(t("Color interior de hojas"))
        lbl_int_prev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_int_prev_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #8c5464; border: none; background: transparent;")
        preview_layout.addWidget(lbl_int_prev_title)

        interior_swatch = QLabel()
        interior_swatch.setFixedHeight(32)
        interior_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(interior_swatch)
        preview_layout.addStretch()

        outer_layout.addWidget(preview_panel)

        # --- Columna Derecha: Formulario con Predefinidos / Personalizar + Color interior ---
        form_layout = QVBoxLayout()
        form_layout.setSpacing(8)

        lbl_heading = QLabel(t("Editar Binder") if editing else t("Configura tu Binder"))
        lbl_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #5a2a3a;")
        form_layout.addWidget(lbl_heading)

        # Nombre + Tamaño en fila compacta
        row_top = QHBoxLayout()
        row_top.setSpacing(10)

        col_name = QVBoxLayout()
        col_name.setSpacing(4)
        col_name.addWidget(QLabel(t("Nombre de la carpeta")))
        txt_nombre = QLineEdit()
        txt_nombre.setText(init_name)
        txt_nombre.setPlaceholderText(t("Ej: Charizards, Set 151, Intercambios..."))
        col_name.addWidget(txt_nombre)
        row_top.addLayout(col_name, 2)

        def _style_combo_popup_white_text(cb: QComboBox):
            from PyQt6.QtGui import QPalette
            view = cb.view()
            if view is not None:
                pal = view.palette()
                pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
                pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
                pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
                pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
                pal.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
                pal.setColor(QPalette.ColorRole.Highlight, QColor("#e25b70"))
                pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
                view.setPalette(pal)
            for i in range(cb.count()):
                cb.setItemData(i, QColor("#ffffff"), Qt.ItemDataRole.ForegroundRole)

        col_mode = QVBoxLayout()
        col_mode.setSpacing(4)
        col_mode.addWidget(QLabel(t("Bolsillos")))
        combo_tamano = QComboBox()
        combo_tamano.addItems(["3x3", "2x2", "3x4", "4x4"])
        _style_combo_popup_white_text(combo_tamano)
        idx_m = combo_tamano.findText(init_mode)
        if idx_m >= 0:
            combo_tamano.setCurrentIndex(idx_m)
        col_mode.addWidget(combo_tamano)
        row_top.addLayout(col_mode, 1)

        form_layout.addLayout(row_top)

        # Estado mutable del diálogo
        state = {
            "custom_color": init_color if (init_color and init_color not in ("auto", "#ffeef2")) else "#1e1b26",
            "custom_image": init_custom_image,
            "interior_color": init_interior,
            "interior_overridden": bool(editing and existing.get("interior_color")),
        }

        # Pestañas: Predefinidos vs Personalizar
        tabs = QTabWidget()

        # -- Tab 1: Predefinidos --
        tab_predef = QWidget()
        tab_predef.setStyleSheet("background: transparent;")
        predef_layout = QVBoxLayout(tab_predef)
        predef_layout.setContentsMargins(10, 10, 10, 10)
        predef_layout.setSpacing(8)

        predef_layout.addWidget(QLabel(t("Diseño predefinido (asigna portada, color e interior)")))
        combo_diseno = QComboBox()
        combo_diseno.addItems(list(BINDER_DESIGNS.keys()))
        _style_combo_popup_white_text(combo_diseno)
        idx_d = combo_diseno.findText(default_design)
        if idx_d >= 0:
            combo_diseno.setCurrentIndex(idx_d)
        predef_layout.addWidget(combo_diseno)

        lbl_predef_hint = QLabel(
            t("Cada diseño aplica automáticamente su color de carpeta, ilustración y color interior recomendado.")
        )
        lbl_predef_hint.setWordWrap(True)
        lbl_predef_hint.setStyleSheet("font-size: 11px; font-weight: 400; color: #8c5464;")
        predef_layout.addWidget(lbl_predef_hint)
        predef_layout.addStretch()
        tabs.addTab(tab_predef, t("Predefinidos"))

        # -- Tab 2: Personalizar --
        tab_custom = QWidget()
        tab_custom.setStyleSheet("background: transparent;")
        custom_layout = QVBoxLayout(tab_custom)
        custom_layout.setContentsMargins(10, 10, 10, 10)
        custom_layout.setSpacing(8)

        custom_layout.addWidget(QLabel(t("Color completo de la carpeta")))
        btn_cover_color = QPushButton()
        btn_cover_color.setFixedHeight(32)
        btn_cover_color.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_layout.addWidget(btn_cover_color)

        custom_layout.addWidget(QLabel(t("Imagen de portada (opcional, soporta PNG transparente)")))
        img_row = QHBoxLayout()
        img_row.setSpacing(8)
        btn_pick_img = QPushButton(t("Elegir imagen..."))
        btn_pick_img.setFixedHeight(32)
        btn_pick_img.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pick_img.setProperty("class", "pill")

        btn_clear_img = QPushButton(t("Quitar imagen"))
        btn_clear_img.setFixedHeight(32)
        btn_clear_img.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_img.setProperty("class", "pill")

        img_row.addWidget(btn_pick_img, 1)
        img_row.addWidget(btn_clear_img)
        custom_layout.addLayout(img_row)

        lbl_img_file = QLabel("")
        lbl_img_file.setStyleSheet("font-size: 11px; font-weight: 400; color: #703043;")
        custom_layout.addWidget(lbl_img_file)
        custom_layout.addStretch()
        tabs.addTab(tab_custom, t("Personalizar"))

        if is_custom_initially:
            tabs.setCurrentIndex(1)

        form_layout.addWidget(tabs)

        # Sección: Color del interior del binder (aplica a ambos modos)
        form_layout.addWidget(QLabel(t("Color del interior del binder (fondo de las páginas)")))
        int_row = QHBoxLayout()
        int_row.setSpacing(8)
        btn_interior_color = QPushButton()
        btn_interior_color.setFixedHeight(32)
        btn_interior_color.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_reset_interior = QPushButton(t("Por defecto"))
        btn_reset_interior.setFixedHeight(32)
        btn_reset_interior.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset_interior.setProperty("class", "pill")

        int_row.addWidget(btn_interior_color, 1)
        int_row.addWidget(btn_reset_interior)
        form_layout.addLayout(int_row)

        def _contrast_text(hex_col: str) -> str:
            c = QColor(hex_col)
            if not c.isValid():
                return "#ffffff"
            luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            return "#1e293b" if luma > 160 else "#ffffff"

        def refresh_ui():
            is_custom = tabs.currentIndex() == 1
            cur_design = combo_diseno.currentText()
            if not state["interior_overridden"] and not is_custom:
                state["interior_color"] = get_design_default_interior_color(cur_design)

            # Botón color de portada (Personalizar)
            cc = state["custom_color"]
            btn_cover_color.setText(f"{t('Color de carpeta')}: {cc.upper()}")
            btn_cover_color.setStyleSheet(
                f"background-color: {cc}; color: {_contrast_text(cc)}; "
                f"border: 2px solid #5a2a3a; border-radius: 9px; font-weight: 700;"
            )

            # Etiqueta archivo imagen personalizada
            if state["custom_image"]:
                lbl_img_file.setText(f"{t('Imagen')}: {os.path.basename(state['custom_image'])}")
                btn_clear_img.setEnabled(True)
            else:
                lbl_img_file.setText(t("Sin imagen personalizada (se usará color liso minimalista)"))
                btn_clear_img.setEnabled(False)

            # Botón y swatch de color interior
            ic = state["interior_color"]
            ic_txt = _contrast_text(ic)
            btn_interior_color.setText(f"{t('Interior')}: {ic.upper()}")
            btn_interior_color.setStyleSheet(
                f"background-color: {ic}; color: {ic_txt}; "
                f"border: 2px solid #5a2a3a; border-radius: 9px; font-weight: 700;"
            )
            interior_swatch.setText(ic.upper())
            interior_swatch.setStyleSheet(
                f"background-color: {ic}; color: {ic_txt}; "
                f"border: 1.5px solid #cbd5e1; border-radius: 8px; font-size: 11px; font-weight: 700;"
            )

            # Actualizar vista previa 3D
            if is_custom:
                live_preview.set_binder_props(
                    name=txt_nombre.text().strip() or "Mi Binder",
                    design="Ultra PRO Minimalista",
                    color=state["custom_color"],
                    mode=combo_tamano.currentText(),
                    custom_image=state["custom_image"],
                )
            else:
                live_preview.set_binder_props(
                    name=txt_nombre.text().strip() or "Mi Binder",
                    design=cur_design,
                    color="auto",
                    mode=combo_tamano.currentText(),
                    custom_image=None,
                )

        def choose_cover_color():
            initial = QColor(state["custom_color"])
            c = QColorDialog.getColor(initial, dlg, t("Color de portada"))
            if c.isValid():
                state["custom_color"] = c.name()
                refresh_ui()

        def choose_custom_image():
            file_path, _ = QFileDialog.getOpenFileName(
                dlg,
                t("Seleccionar imagen para portada del Binder"),
                "",
                "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)"
            )
            if file_path and os.path.exists(file_path):
                state["custom_image"] = file_path
                refresh_ui()

        def clear_custom_image():
            state["custom_image"] = None
            refresh_ui()

        def choose_interior_color():
            initial = QColor(state["interior_color"])
            c = QColorDialog.getColor(initial, dlg, t("Color del interior del binder"))
            if c.isValid():
                state["interior_color"] = c.name()
                state["interior_overridden"] = True
                refresh_ui()

        def reset_interior_color():
            state["interior_overridden"] = False
            state["interior_color"] = (
                "#18181e" if tabs.currentIndex() == 1
                else get_design_default_interior_color(combo_diseno.currentText())
            )
            refresh_ui()

        btn_cover_color.clicked.connect(choose_cover_color)
        btn_pick_img.clicked.connect(choose_custom_image)
        btn_clear_img.clicked.connect(clear_custom_image)
        btn_interior_color.clicked.connect(choose_interior_color)
        btn_reset_interior.clicked.connect(reset_interior_color)
        txt_nombre.textChanged.connect(lambda _: refresh_ui())
        combo_diseno.currentTextChanged.connect(lambda _: refresh_ui())
        combo_tamano.currentTextChanged.connect(lambda _: refresh_ui())
        tabs.currentChanged.connect(lambda _: refresh_ui())

        refresh_ui()

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

        btn_save = QPushButton(t("Guardar Cambios") if editing else t("Crear Carpeta"))
        btn_save.setFixedHeight(36)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
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

        def on_save():
            nombre = txt_nombre.text().strip()
            if not nombre:
                QMessageBox.warning(dlg, t("Aviso"), t("Debes ingresar un nombre para la carpeta."))
                return

            is_custom = tabs.currentIndex() == 1
            final_design = "Ultra PRO Minimalista" if is_custom else combo_diseno.currentText()
            final_color = state["custom_color"] if is_custom else "auto"
            final_interior = state["interior_color"]
            final_mode = combo_tamano.currentText()

            # Persistir imagen personalizada en BINDER_COVERS_DIR para que no se pierda si mueven el archivo original
            final_custom_image = None
            if is_custom and state["custom_image"]:
                src_path = state["custom_image"]
                if os.path.isabs(src_path) and os.path.exists(src_path):
                    try:
                        os.makedirs(BINDER_COVERS_DIR, exist_ok=True)
                        abs_covers = os.path.abspath(BINDER_COVERS_DIR)
                        if os.path.abspath(src_path).startswith(abs_covers):
                            final_custom_image = os.path.basename(src_path)
                        else:
                            import time
                            ext = os.path.splitext(src_path)[1].lower() or ".png"
                            fname = f"cover_{int(time.time() * 1000)}{ext}"
                            shutil.copy2(src_path, os.path.join(BINDER_COVERS_DIR, fname))
                            final_custom_image = fname
                    except Exception as e:
                        print(f"Error copiando imagen personalizada de binder: {e}")
                        final_custom_image = src_path
                else:
                    final_custom_image = src_path

            if editing:
                f_obj = folders[edit_folder_id]
                f_obj["name"] = nombre
                f_obj["design"] = final_design
                f_obj["color"] = final_color
                f_obj["custom_image"] = final_custom_image
                f_obj["interior_color"] = final_interior
                f_obj["mode"] = final_mode
                f_obj.setdefault("cards", {"2x2": {}, "3x3": {}, "3x4": {}, "4x4": {}})
                for m_key in ("2x2", "3x3", "3x4", "4x4"):
                    f_obj["cards"].setdefault(m_key, {})

                self.save_binder_data()
                self.render_folders_grid()
                self.update_folder_combo()

                # Si estamos editando el binder actualmente abierto, refrescar en vivo
                if self.current_folder_id == edit_folder_id and self.main_stack.currentWidget() == self.binder_pages_widget:
                    self.current_mode = final_mode
                    self.update_spread(direction=0)

                show_toast(f"{t('Binder actualizado')}: {nombre}", "success")
                dlg.accept()
            else:
                import time
                new_id = f"folder_{int(time.time() * 1000)}"
                folders[new_id] = {
                    "name": nombre,
                    "color": final_color,
                    "design": final_design,
                    "custom_image": final_custom_image,
                    "interior_color": final_interior,
                    "locked": False,
                    "mode": final_mode,
                    "cards": {
                        "2x2": {},
                        "3x3": {},
                        "3x4": {},
                        "4x4": {}
                    }
                }
                self.save_binder_data()
                self.current_folder_id = new_id
                self.current_mode = final_mode
                self.current_spread_index = 0
                self.render_folders_grid()
                show_toast(f"Carpeta '{nombre}' creada con éxito", "info")
                dlg.accept()
                self.abrir_carpeta(new_id)

        btn_save.clicked.connect(on_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
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
            slot.clear_card(animate_remove=True)

        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()

    def quitar_carta_arrastrada(self, source_slot_key: str):
        """Quita una carta del binder cuando el usuario la arrastra de vuelta a su colección (Issue #23)."""
        if not source_slot_key or "_" not in source_slot_key:
            return
        try:
            page_str, slot_str = source_slot_key.split("_", 1)
            page_idx = int(page_str)
            slot_idx = int(slot_str)
        except Exception:
            return

        self.set_card_at(page_idx, slot_idx, None)

        target_slot = None
        for page in (self.page_left, self.page_right):
            if page and page.page_index == page_idx:
                target_slot = page.get_slot(slot_idx)
                break

        if target_slot is not None:
            target_slot.set_selected(False)
            target_slot.clear_card(animate_remove=True)

        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()
        show_toast(t("Carta devuelta a tu colección"), "info")

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
        _custom_img, interior_color, _locked = self._get_current_folder_extra()
        spread_widget = BinderSpreadFrame(
            design=design,
            color=color,
            can_go_prev=(spread_index > 0),
            interior_color=interior_color,
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
            interior_color=interior_color,
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
            interior_color=interior_color,
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
