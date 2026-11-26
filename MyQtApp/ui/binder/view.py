"""Vista principal y gestión de carpetas del Binder."""

import copy
import json
import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QFrame, QPushButton, QApplication, QSizePolicy,
    QStackedWidget, QGraphicsOpacityEffect, QLineEdit, QComboBox,
    QDialog, QMessageBox, QColorDialog, QMenu, QFileDialog, QTabWidget,
)
from PyQt6.QtCore import (
    Qt, QMimeData, QPoint, QPointF, QSize, QEasingCurve,
    QPropertyAnimation, QRect, QRectF, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QDrag, QPixmap, QCursor, QAction, QPainter, QPainterPath,
    QLinearGradient, QColor, QPen, QFont, QShortcut, QKeySequence,
)
from sqlalchemy import func

from MyQtApp.config import ASSETS_DIR, IMAGES_DIR, BINDER_DATA_FILE
from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas, UsuarioCarta
from MyQtApp.app.getImgs import get_pixmap_from_zip, get_webp_pixmap, get_card_placeholder_pixmap
from MyQtApp.app.price_updater import (
    obtener_precios_multiples_cartas_bd,
    PriceUpdaterThread,
    PRICE_SOURCE_ORDER,
    format_price,
    get_active_currency,
)
from MyQtApp.i18n import t, language_manager
from MyQtApp.ui.CardWidget import CardZoomOverlay, VariantBadgeButton, LanguageBadgeLabel, InfoIconLabel
from MyQtApp.ui.BinderCoverWidget import (
    BinderCoverWidget, BINDER_DESIGNS, resolve_design_key,
    BINDER_COVERS_DIR, get_design_default_interior_color,
)
from MyQtApp.ui.AdvancedCoverStudio import (
    AdvancedCoverStudioDialog, Interactive3DViewerDialog, normalize_advanced_design,
    render_inside_cover_surface,
)
from MyQtApp.ui.BinderBookAnimations import (
    BinderSpreadFrame,
    PageFlipAnimationOverlay,
    BinderOpenAnimationOverlay,
    CardSlideInOverlay,
    BinderPageMinimap,
    render_transparent_cover_pixmap,
)
from MyQtApp.ui.pixmap_cache import get_cached_pixmap
from MyQtApp.ui.toast import show_toast
from MyQtApp.ui.binder.constants import BINDER_MODES
from MyQtApp.ui.binder.widgets import (
    DraggableCardLabel,
    BinderSlot,
    BinderPage,
    BinderInsideCoverWidget,
)
from MyQtApp.ui.binder.sidebar import InventorySidebar


class BinderView(QWidget):
    open_binder_in_print_requested = pyqtSignal(str, str)  # (folder_id, mode: "print" | "csv")
    inside_binder_changed = pyqtSignal(bool)

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
        self._card_meta_cache: dict[tuple[str, str], Cartas] = {}
        self.show_card_details = False
        self.move_pages_mode = False
        self._selected_move_page: int | None = None
        
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
        
        self.inventory = InventorySidebar(usuario, binder_view=self)
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

        self.main_stack.currentChanged.connect(self._on_main_stack_changed)

        # Mostrar carpetas inicialmente
        self.mostrar_vista_carpetas()
        language_manager.language_changed.connect(self.retranslate_ui)

    def is_inside_binder(self) -> bool:
        """Indica si actualmente se está visualizando el interior de una carpeta."""
        return self.main_stack.currentWidget() == self.binder_pages_widget

    def _on_main_stack_changed(self, index: int):
        self.inside_binder_changed.emit(self.is_inside_binder())

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

        self.btn_mover_hojas = QPushButton(t("Mover hojas"))
        self.btn_mover_hojas.setCheckable(True)
        self.btn_mover_hojas.setChecked(False)
        self.btn_mover_hojas.setFixedHeight(26)
        self.btn_mover_hojas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mover_hojas.setToolTip(
            t("Activa el modo para seleccionar o arrastrar una hoja completa hacia otra (intercambia sus cartas)")
        )
        self.btn_mover_hojas.clicked.connect(lambda: self.toggle_move_pages_mode())
        self._refresh_mover_hojas_btn_style()
        details_row.addWidget(self.btn_mover_hojas)

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
        self.page_minimap.page_swap_requested.connect(self.swap_pages)
        self.page_minimap.page_move_clicked.connect(self.on_page_move_clicked)
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
            if not page or not hasattr(page, "slots"):
                continue
            for slot in page.slots:
                slot.apply_details_visibility()

    def _refresh_mover_hojas_btn_style(self):
        if not hasattr(self, "btn_mover_hojas") or not self.btn_mover_hojas:
            return
        active = bool(self.move_pages_mode)
        self.btn_mover_hojas.setChecked(active)
        self.btn_mover_hojas.setText(t("Listo (Mover hojas)") if active else t("Mover hojas"))
        if active:
            self.btn_mover_hojas.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 700;
                    border: 1.5px solid #0369a1;
                    border-radius: 9px;
                    padding: 2px 14px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)
        else:
            self.btn_mover_hojas.setStyleSheet("""
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
                    background-color: #e0f2fe;
                    border-color: #38bdf8;
                }
            """)

    def _apply_move_mode_to_visible_pages(self):
        current_spread = self.spread_stack.currentWidget() if hasattr(self, "spread_stack") else None
        if current_spread and hasattr(current_spread, "set_drag_turn_enabled"):
            current_spread.set_drag_turn_enabled(not self.move_pages_mode)
        for page in (self.page_left, self.page_right):
            if page and isinstance(page, BinderPage) and hasattr(page, "set_move_mode"):
                page.set_move_mode(
                    self.move_pages_mode,
                    selected=(self._selected_move_page == page.page_index),
                )

    def toggle_move_pages_mode(self, force_state: bool | None = None):
        """Activa o desactiva el modo de arrastre/intercambio completo de hojas del binder."""
        new_state = (not self.move_pages_mode) if force_state is None else bool(force_state)
        self.move_pages_mode = new_state
        self._selected_move_page = None
        self._refresh_mover_hojas_btn_style()
        self._apply_move_mode_to_visible_pages()
        self.refresh_page_minimap()
        if new_state and self.main_stack.currentWidget() is self.binder_pages_widget:
            show_toast(
                t("Arrastra una hoja (o haz clic en dos hojas en la barra inferior H1, H2...) para intercambiarlas"),
                "info",
                2800,
            )

    def on_page_move_clicked(self, page_idx: int):
        """Permite seleccionar origen y destino haciendo clic en hojas o píldoras H1, H2..."""
        if not self.move_pages_mode or page_idx < 0:
            return
        if self._selected_move_page is None:
            self._selected_move_page = page_idx
            self._apply_move_mode_to_visible_pages()
            self.refresh_page_minimap()
            show_toast(f"{t('Hoja')} {page_idx + 1} seleccionada. Ahora elige o arrastra hacia la hoja destino.", "info", 2200)
        elif self._selected_move_page == page_idx:
            self._selected_move_page = None
            self._apply_move_mode_to_visible_pages()
            self.refresh_page_minimap()
        else:
            src_page = self._selected_move_page
            self.swap_pages(src_page, page_idx)

    def swap_pages(self, page_a: int, page_b: int) -> bool:
        """
        Intercambia completamente todas las cartas entre dos hojas del binder (page_a <-> page_b).
        Si la hoja destino estaba vacía, mueve las cartas de page_a a page_b y deja page_a vacía.
        """
        if page_a < 0 or page_b < 0 or page_a == page_b or not self.current_folder_id:
            return False

        cards_dict = self._get_current_cards_dict(self.current_mode)
        prefix_a = f"{page_a}_"
        prefix_b = f"{page_b}_"

        entries_a: dict[str, object] = {}
        entries_b: dict[str, object] = {}
        keys_to_delete = []

        for key, val in cards_dict.items():
            if key.startswith(prefix_a):
                slot_part = key[len(prefix_a):]
                entries_a[slot_part] = copy.deepcopy(val) if isinstance(val, dict) else val
                keys_to_delete.append(key)
            elif key.startswith(prefix_b):
                slot_part = key[len(prefix_b):]
                entries_b[slot_part] = copy.deepcopy(val) if isinstance(val, dict) else val
                keys_to_delete.append(key)

        if not entries_a and not entries_b:
            self._selected_move_page = None
            self._apply_move_mode_to_visible_pages()
            self.refresh_page_minimap()
            return False

        for k in keys_to_delete:
            cards_dict.pop(k, None)

        for slot_part, val in entries_a.items():
            cards_dict[f"{page_b}_{slot_part}"] = val
        for slot_part, val in entries_b.items():
            cards_dict[f"{page_a}_{slot_part}"] = val

        self._selected_move_page = None
        self.save_binder_data()
        self.update_spread(direction=0)
        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()

        if entries_a and entries_b:
            show_toast(f"{t('Hoja')} {page_a + 1} ↔ {t('Hoja')} {page_b + 1} intercambiadas", "info")
        else:
            show_toast(f"{t('Hoja')} {page_a + 1} movida a {t('Hoja')} {page_b + 1}", "info")
        return True

    def mostrar_vista_carpetas(self, animate_close=False):
        """Muestra la vista de catálogo/selección de carpetas, con animación 3D de cierre al volver."""
        if getattr(self, "move_pages_mode", False):
            self.toggle_move_pages_mode(False)
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
                        adv_design = self.get_user_folders().get(closing_folder_id, {}).get("advanced_design")
                        cover_w = max(140, int(board_local.width() * 0.5))
                        cover_h = max(180, int(board_local.height()))
                        cover_pix = render_transparent_cover_pixmap(
                            name, design, color, mode, cover_w, cover_h,
                            custom_image=custom_image, locked=locked, advanced_design=adv_design
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
                                self._active_open_overlay.cancel()
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
                        overlay.animation_finished.connect(
                            lambda target_ov=overlay: setattr(self, "_active_open_overlay", None) if self._active_open_overlay is target_ov else None
                        )
                        return
                except Exception as e:
                    print(f"Error en animación de cierre de binder: {e}")

        self.render_folders_grid()
        self.main_stack.setCurrentWidget(self.folders_view_widget)

    def stop_active_animations(self):
        """Detiene y limpia overlays de apertura/giro activos antes de cambiar de sección."""
        ov = self._active_open_overlay
        self._active_open_overlay = None
        if ov is not None:
            try:
                if hasattr(ov, "cancel"):
                    ov.cancel()
                else:
                    ov.hide()
                    ov.deleteLater()
            except Exception:
                pass

        flip_ov = self._active_flip_overlay
        self._active_flip_overlay = None
        if flip_ov is not None:
            try:
                if hasattr(flip_ov, "cancel"):
                    flip_ov.cancel()
                else:
                    flip_ov.hide()
                    flip_ov.deleteLater()
            except Exception:
                pass

        if getattr(self, "_drag_turn_state", None):
            try:
                ns = self._drag_turn_state.get("new_spread")
                if ns is not None:
                    ns.deleteLater()
            except Exception:
                pass
            self._drag_turn_state = None

        try:
            cur_sp = self.spread_stack.currentWidget() if hasattr(self, "spread_stack") else None
            if cur_sp is not None:
                cur_sp.setVisible(True)
        except Exception:
            pass
        try:
            if hasattr(self, "btn_prev"):
                self.btn_prev.setEnabled(self.current_spread_index > 0)
            if hasattr(self, "btn_next"):
                self.btn_next.setEnabled(True)
        except Exception:
            pass

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
        if getattr(self, "move_pages_mode", False):
            self.move_pages_mode = False
            self._selected_move_page = None
            self._refresh_mover_hojas_btn_style()
        self.update_folder_combo()
        self.aplicar_estilo_carpeta_actual()
        self.update_spread(direction=0)
        self.actualizar_resumen_precios_binder()
        self.inventory.update_usage_badges()
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
            adv_design = self.get_user_folders().get(self.current_folder_id, {}).get("advanced_design")
            cover_w = max(140, int(board_local.width() * 0.5))
            cover_h = max(180, int(board_local.height()))
            cover_pix = render_transparent_cover_pixmap(
                name, design, color, mode, cover_w, cover_h,
                custom_image=custom_image, locked=locked, advanced_design=adv_design
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
                    self._active_open_overlay.cancel()
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

            def _on_open_done(target_ov=overlay):
                if self._active_open_overlay is target_ov:
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
        active_curr = get_active_currency()

        self.lbl_binder_price_title.setText(f"{t('Valor del Binder')} ({total_cards} cartas):")

        if total_cards == 0:
            lbl = QLabel(format_price(0.0, "USD", target_currency=active_curr, include_code=True))
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
                "Cardmarket": ("#fef2f2", "#be123c", "#fda4af"),
                "PokemonTCG": ("#fef3c7", "#b45309", "#fcd34d"),
                "TCGCSV": ("#f5f3ff", "#6d28d9", "#c4b5fd"),
            }
            for src in ordered_sources:
                info = sources[src]
                bg, fg, bd = palette.get(src, ("#f8fafc", "#334155", "#cbd5e1"))
                moneda = str(info.get("moneda") or "USD").upper()
                if moneda == active_curr and info.get("orig", 0) > 0:
                    val_txt = format_price(info["orig"], moneda, target_currency=active_curr, include_code=True)
                else:
                    val_txt = format_price(info["usd"], "USD", target_currency=active_curr, include_code=True)
                txt = f"{src} = {val_txt}"
                pill = QLabel(txt)
                pill.setToolTip(f"{src}: {info['priced_count']}/{total_cards} cartas cotizadas")
                pill.setStyleSheet(
                    f"background-color: {bg}; color: {fg}; border: 1px solid {bd}; "
                    f"border-radius: 8px; padding: 3px 9px; font-size: 11px; font-weight: bold;"
                )
                self.binder_prices_pills_layout.addWidget(pill)
        else:
            base_usd = res["base_total_usd"]
            base_fmt = format_price(base_usd, "USD", target_currency=active_curr, include_code=True)
            pill = QLabel(f"Mercado Base = {base_fmt}")
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

        # Portada física realista del Binder (Issue #13 / #21 / #52)
        cover = BinderCoverWidget(
            name=name,
            design=design,
            color=color,
            mode=mode,
            custom_image=custom_image,
            locked=locked,
            advanced_design=f_data.get("advanced_design"),
            parent=frame,
        )
        cover.setFixedSize(196, 212)
        self._folder_cover_widgets[f_id] = cover
        layout.addWidget(cover, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Resumen de precio acumulativo de mercado
        price_res = self.calcular_precios_carpeta(f_data)
        src_map = price_res["sources"]
        active_curr = get_active_currency()
        if src_map:
            parts = []
            for src in PRICE_SOURCE_ORDER:
                if src in src_map:
                    info = src_map[src]
                    moneda = str(info.get("moneda") or "USD").upper()
                    if moneda == active_curr and info.get("orig", 0) > 0:
                        val_txt = format_price(info["orig"], moneda, target_currency=active_curr, include_code=False)
                    else:
                        val_txt = format_price(info["usd"], "USD", target_currency=active_curr, include_code=False)
                    parts.append(f"{src}: {val_txt}")
            price_summary_txt = f"{' | '.join(parts[:2])} {active_curr}"
        else:
            price_summary_txt = format_price(
                price_res["base_total_usd"], "USD", target_currency=active_curr, include_code=True
            )

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

        # Hover sincronizado con la portada física 3D + Long-Press para Vista 3D completa (Issue #52)
        long_press_timer = QTimer(frame)
        long_press_timer.setSingleShot(True)
        press_state = {"triggered": False}

        def on_long_press():
            press_state["triggered"] = True
            self._abrir_vista_3d_binder(f_id)

        long_press_timer.timeout.connect(on_long_press)

        def on_enter(event):
            cover.set_hovered(True)
            QFrame.enterEvent(frame, event)

        def on_leave(event):
            long_press_timer.stop()
            cover.set_hovered(False)
            QFrame.leaveEvent(frame, event)

        def on_frame_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                press_state["triggered"] = False
                long_press_timer.start(450)

        def on_frame_release(event):
            if event.button() == Qt.MouseButton.LeftButton:
                was_long = press_state["triggered"]
                long_press_timer.stop()
                if not was_long and frame.rect().contains(event.pos()):
                    self.abrir_carpeta(f_id, origin_widget=cover)

        frame.enterEvent = on_enter
        frame.leaveEvent = on_leave
        frame.mousePressEvent = on_frame_press
        frame.mouseReleaseEvent = on_frame_release
        frame.setToolTip(t("Clic para abrir  •  Mantén pulsado para ver en 3D"))

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

        act_3d = QAction(t("Ver en 3D"), menu)
        act_3d.triggered.connect(lambda: self._abrir_vista_3d_binder(folder_id))
        menu.addAction(act_3d)

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

    def _abrir_vista_3d_binder(self, folder_id: str):
        """Abre el Binder completo en el visor interactivo 3D (Issue #52)."""
        folders = self.get_user_folders()
        f_data = folders.get(folder_id)
        if not f_data:
            return
        name = f_data.get("name", "Mi Binder")
        design = resolve_design_key(f_data.get("design", "Charizard Fuego"))
        color = f_data.get("color", "auto")
        mode = f_data.get("mode", "3x3")
        custom_image = f_data.get("custom_image") or None
        locked = bool(f_data.get("locked", False))
        adv = normalize_advanced_design(f_data.get("advanced_design"))

        temp_cover = BinderCoverWidget(
            name=name,
            design=design,
            color=color,
            mode=mode,
            custom_image=custom_image,
            locked=locked,
            advanced_design=adv,
        )
        _cfg, _base, spine_col, _strap, _a1, _a2 = temp_cover._effective_colors()
        front_pix = temp_cover.render_face_pixmap("front", 380, 500, adv.get("back_color"), include_advanced=True)
        back_pix = temp_cover.render_face_pixmap("back", 380, 500, adv.get("back_color"), include_advanced=True)
        dlg = Interactive3DViewerDialog(
            title=name,
            front_pixmap=front_pix,
            back_pixmap=back_pix,
            spine_color=spine_col.name(),
            edge_color="#e2e8f0",
            item_type="binder",
            parent=self,
        )
        dlg.exec()

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
        self.inventory.update_usage_badges()
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

    def editar_interior_portada_actual(self):
        """Abre el estudio de diseño directamente en la cara interior de portada del Binder actual (Issue #59)."""
        if not self.current_folder_id:
            return
        folders = self.get_user_folders()
        folder = folders.get(self.current_folder_id)
        if not folder:
            return
        if folder.get("locked", False):
            show_toast(t("Este binder está bloqueado. Desbloquéalo desde Mis Binders para editarlo."), "warning", 3000)
            return

        name, design, color, mode = self._get_current_folder_theme()
        custom_image, interior_color, _locked = self._get_current_folder_extra()
        adv_design = folder.get("advanced_design")

        preview_w = BinderCoverWidget(
            name=name,
            design=design,
            color=color,
            mode=mode,
            custom_image=custom_image,
            advanced_design=adv_design,
        )
        studio = AdvancedCoverStudioDialog(
            item_type="binder",
            name=name,
            design_name=design,
            custom_color=color,
            custom_image=custom_image,
            advanced_design=adv_design,
            face_renderer=preview_w.render_face_pixmap,
            initial_face="inside",
            interior_color=interior_color,
            parent=self,
        )
        if studio.exec() == QDialog.DialogCode.Accepted:
            folder["advanced_design"] = studio.get_advanced_design()
            self.save_binder_data()
            self.render_folders_grid()
            self.update_spread(direction=0)
            show_toast(t("Interior de portada actualizado"), "success")

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
                self.inventory.update_usage_badges()

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
        init_advanced = normalize_advanced_design(existing.get("advanced_design") if editing else None)
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
            advanced_design=init_advanced,
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
            "advanced_design": init_advanced,
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
                    advanced_design=state["advanced_design"],
                )
            else:
                live_preview.set_binder_props(
                    name=txt_nombre.text().strip() or "Mi Binder",
                    design=cur_design,
                    color="auto",
                    mode=combo_tamano.currentText(),
                    custom_image=None,
                    advanced_design=state["advanced_design"],
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

        def open_advanced_studio():
            refresh_ui()
            studio = AdvancedCoverStudioDialog(
                item_type="binder",
                name=txt_nombre.text().strip() or "Mi Binder",
                design_name=combo_diseno.currentText(),
                custom_color=state["custom_color"],
                custom_image=state["custom_image"] if tabs.currentIndex() == 1 else None,
                advanced_design=state["advanced_design"],
                face_renderer=live_preview.render_face_pixmap,
                interior_color=state["interior_color"],
                parent=dlg,
            )
            if studio.exec() == QDialog.DialogCode.Accepted:
                state["advanced_design"] = studio.get_advanced_design()
                refresh_ui()

        btn_advanced = QPushButton(t("Avanzado"))
        btn_advanced.setFixedHeight(36)
        btn_advanced.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_advanced.setToolTip(t("Personalización avanzada con stickers, figuras, parte trasera y vista 3D"))
        btn_advanced.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #ffffff;
                border: 2px solid #0284c7;
                border-radius: 10px;
                padding: 4px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
        """)
        btn_advanced.clicked.connect(open_advanced_studio)

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
                old_mode = f_obj.get("mode", "3x3")
                f_obj["name"] = nombre
                f_obj["design"] = final_design
                f_obj["color"] = final_color
                f_obj["custom_image"] = final_custom_image
                f_obj["interior_color"] = final_interior
                f_obj["mode"] = final_mode
                f_obj["advanced_design"] = state["advanced_design"]
                f_obj.setdefault("cards", {"2x2": {}, "3x3": {}, "3x4": {}, "4x4": {}})
                for m_key in ("2x2", "3x3", "3x4", "4x4"):
                    f_obj["cards"].setdefault(m_key, {})

                if old_mode != final_mode:
                    self._reflow_folder_cards_for_mode(f_obj, old_mode, final_mode)

                self.save_binder_data()
                self.render_folders_grid()
                self.update_folder_combo()

                # Si estamos editando el binder actualmente abierto, refrescar en vivo
                if self.current_folder_id == edit_folder_id and self.main_stack.currentWidget() == self.binder_pages_widget:
                    self.current_mode = final_mode
                    if old_mode != final_mode:
                        self.current_spread_index = 0
                        if hasattr(self, "selected_slot"):
                            self.selected_slot = None
                        if hasattr(self, "btn_quitar"):
                            self.btn_quitar.setEnabled(False)
                    self.update_spread(direction=0)
                    self.actualizar_resumen_precios_binder()

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
                    "advanced_design": state["advanced_design"],
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
        btn_row.addWidget(btn_advanced)
        btn_row.addStretch()
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
                self.inventory.update_usage_badges()
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
            self.set_card_at(slot.page_index, slot.slot_index, None, save=False)
            slot.set_selected(False)
            slot.clear_card(animate_remove=True)

        self.save_binder_data()
        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()
        self.inventory.update_usage_badges()

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

        target_slot = self._get_visible_slot(page_idx, slot_idx)
        if target_slot is not None:
            target_slot.set_selected(False)
            target_slot.clear_card(animate_remove=True)

        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()
        self.inventory.update_usage_badges()
        show_toast(t("Carta devuelta a tu colección"), "info")

    def retranslate_ui(self):
        self.title_lbl.setText(t("Binder"))
        self.btn_prev.setText(t("Anterior"))
        self.btn_next.setText(t("Siguiente"))
        self.btn_quitar.setText(t("Quitar") if not self.get_selected_slots() else f"{t('Quitar')} ({len(self.get_selected_slots())})")
        self.lbl_pages.setText(self._format_spread_label(self.current_spread_index))
        self._refresh_ver_detalles_btn_style()
        self._refresh_mover_hojas_btn_style()
        self._apply_move_mode_to_visible_pages()
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
            
    def _reflow_folder_cards_for_mode(self, folder_obj: dict, old_mode: str, new_mode: str) -> None:
        """
        Reajusta (reflow) las cartas del binder al cambiar su cuadrícula (ej. 3x3 -> 2x2,
        2x2 -> 3x3, 3x4 -> 4x4, etc.) preservando el orden secuencial (página, bolsillo)
        para que todas las cartas se mantengan visibles y no existan cuadrículas separadas.
        """
        if not folder_obj or old_mode == new_mode or new_mode not in BINDER_MODES:
            return

        cards_by_mode = folder_obj.setdefault("cards", {})
        for m_key in BINDER_MODES:
            cards_by_mode.setdefault(m_key, {})

        old_cards = cards_by_mode.get(old_mode, {})
        if not old_cards:
            # Si el modo anterior estaba vacío, conservar lo que pudiera existir en new_mode
            return

        ordered_entries = []
        for raw_key, card_entry in old_cards.items():
            if card_entry is None:
                continue
            try:
                p_str, s_str = str(raw_key).split("_", 1)
                page_idx = int(p_str)
                slot_idx = int(s_str)
            except (ValueError, TypeError):
                page_idx, slot_idx = 10**9, 10**9
            ordered_entries.append((page_idx, slot_idx, str(raw_key), card_entry))

        ordered_entries.sort(key=lambda item: (item[0], item[1], item[2]))

        new_cfg = BINDER_MODES[new_mode]
        slots_per_page = max(1, int(new_cfg["rows"]) * int(new_cfg["cols"]))

        reflowed = {}
        for idx, (_p, _s, _k, card_entry) in enumerate(ordered_entries):
            new_page = idx // slots_per_page
            new_slot = idx % slots_per_page
            reflowed[f"{new_page}_{new_slot}"] = copy.deepcopy(card_entry)

        for m_key in BINDER_MODES:
            cards_by_mode[m_key] = {}
        cards_by_mode[new_mode] = reflowed

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
        
    def set_card_at(self, page, slot, card_id, save: bool = True):
        cards_dict = self._get_current_cards_dict(self.current_mode)
        key = f"{page}_{slot}"
        if card_id is None:
            if key in cards_dict:
                del cards_dict[key]
        else:
            cards_dict[key] = card_id
        if save:
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
        
    def _spread_page_indices(self, spread_index: int) -> tuple[int | None, int]:
        """Retorna (p_idx_left, p_idx_right). En el pliego 0, la izquierda es interior de portada (None) y la derecha es página 0."""
        if spread_index <= 0:
            return None, 0
        p1 = spread_index * 2 - 1
        return p1, p1 + 1

    def _format_spread_label(self, spread_index: int) -> str:
        p_left, p_right = self._spread_page_indices(spread_index)
        if p_left is None:
            return f"{t('Portada')}  |  {t('Página')} {p_right + 1}"
        return f"{t('Página')} {p_left + 1} - {p_right + 1}"

    def create_spread_widget(self, spread_index, mode=None):
        folder_name, design, color, _ = self._get_current_folder_theme()
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

        p_idx_1, p_idx_2 = self._spread_page_indices(spread_index)

        target_mode = mode if mode else self.current_mode
        cfg = BINDER_MODES[target_mode]

        if p_idx_1 is None:
            adv_design = self.get_user_folders().get(self.current_folder_id, {}).get("advanced_design")
            page_left = BinderInsideCoverWidget(
                rows=cfg["rows"],
                cols=cfg["cols"],
                slot_w=cfg["slot_w"],
                slot_h=cfg["slot_h"],
                folder_name=folder_name,
                interior_color=interior_color,
                advanced_design=adv_design,
                locked=_locked,
            )
            page_left.edit_inside_requested.connect(self.editar_interior_portada_actual)
        else:
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
            self.populate_page(page_left, p_idx_1, target_mode)

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
        self.populate_page(page_right, p_idx_2, target_mode)

        spread_widget.set_drag_turn_enabled(not getattr(self, "move_pages_mode", False))
        if isinstance(page_left, BinderPage):
            page_left.set_move_mode(
                getattr(self, "move_pages_mode", False),
                selected=(self._selected_move_page == page_left.page_index),
            )
        if isinstance(page_right, BinderPage):
            page_right.set_move_mode(
                getattr(self, "move_pages_mode", False),
                selected=(self._selected_move_page == page_right.page_index),
            )

        spread_widget.spread_layout.addWidget(page_left)
        spread_widget.spread_layout.addWidget(page_right)

        return spread_widget, page_left, page_right

    def update_spread(self, direction=0):
        new_spread, new_left, new_right = self.create_spread_widget(self.current_spread_index)

        # UI controls update
        self.lbl_pages.setText(self._format_spread_label(self.current_spread_index))
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
                self.lbl_pages.setText(self._format_spread_label(self.current_spread_index))
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

    def _get_card_meta(self, card_id: str, card_lang: str, session=None):
        """Retorna el objeto Cartas desde caché en memoria o consultando BD con expunge seguro."""
        key = (str(card_id), str(card_lang or "en"))
        cached = self._card_meta_cache.get(key)
        if cached is not None:
            return cached

        owns_session = session is None
        s = session if session is not None else SessionLocal()
        try:
            carta = s.query(Cartas).filter(Cartas.id_api == card_id, Cartas.idioma == card_lang).first()
            if not carta:
                carta = s.query(Cartas).filter(Cartas.id_api == card_id).first()
            if carta is not None:
                s.expunge(carta)
                self._card_meta_cache[key] = carta
                real_lang = carta.idioma or card_lang or "en"
                self._card_meta_cache[(str(card_id), str(real_lang))] = carta
            return carta
        finally:
            if owns_session:
                s.close()

    def _preload_cards_meta(self, entries: list[tuple[str, str]]) -> None:
        """Precarga en una sola consulta SQL todas las cartas de una página que no están en caché."""
        missing = []
        for cid, lang in entries:
            if cid and (str(cid), str(lang or "en")) not in self._card_meta_cache:
                missing.append((str(cid), str(lang or "en")))
        if not missing:
            return
        unique_ids = list({cid for cid, _ in missing})
        session = SessionLocal()
        try:
            rows = session.query(Cartas).filter(Cartas.id_api.in_(unique_ids)).all()
            by_id: dict[str, list[Cartas]] = {}
            for c in rows:
                session.expunge(c)
                self._card_meta_cache[(str(c.id_api), str(c.idioma or "en"))] = c
                by_id.setdefault(str(c.id_api), []).append(c)
            for cid, lang in missing:
                if (cid, lang) not in self._card_meta_cache:
                    cands = by_id.get(cid)
                    if cands:
                        self._card_meta_cache[(cid, lang)] = cands[0]
        finally:
            session.close()

    def populate_page(self, page_widget, page_idx, mode=None):
        target_mode = mode if mode else self.current_mode
        cfg = BINDER_MODES[target_mode]
        slots_per_page = cfg["rows"] * cfg["cols"]

        slot_entries = []
        to_preload = []
        for i in range(slots_per_page):
            card_info = self.get_card_at(page_idx, i, target_mode)
            slot = page_widget.get_slot(i)
            if card_info and slot:
                card_id, card_lang, card_var = self._parse_card_entry(card_info)
                if card_id:
                    slot_entries.append((slot, card_id, card_lang, card_var))
                    to_preload.append((card_id, card_lang))

        if to_preload:
            self._preload_cards_meta(to_preload)

        for slot, card_id, card_lang, card_var in slot_entries:
            carta = self._get_card_meta(card_id, card_lang)
            if carta:
                c_lang = carta.idioma or card_lang
                nombre = carta.nombre
                nombre_archivo = nombre.lower().replace(" ", "_")

                pixmap = get_webp_pixmap(card_id, nombre, c_lang, size=(cfg["card_w"], cfg["card_h"]))
                if not pixmap:
                    pixmap = get_pixmap_from_zip(nombre_archivo, size=(cfg["card_w"], cfg["card_h"]), id_api=card_id)
                if not pixmap:
                    ruta_alt = os.path.join(IMAGES_DIR, f"{nombre_archivo}_{card_id}.webp")
                    pixmap = get_cached_pixmap(ruta_alt, cfg["card_w"], cfg["card_h"])
                if not pixmap or pixmap.isNull():
                    pixmap = get_card_placeholder_pixmap((cfg["card_w"], cfg["card_h"]), nombre)

                slot.set_card(card_id, nombre_archivo, pixmap, idioma=c_lang, variante=card_var, carta=carta)

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


    def _get_visible_slot(self, page_idx: int, slot_idx: int):
        """Retorna el BinderSlot visible si page_idx está actualmente renderizado en pantalla."""
        p_l, p_r = self._spread_page_indices(self.current_spread_index)
        target_page_widget = None
        if p_l is not None and page_idx == p_l:
            target_page_widget = self.page_left
        elif page_idx == p_r:
            target_page_widget = self.page_right
        if target_page_widget is not None and hasattr(target_page_widget, "get_slot"):
            return target_page_widget.get_slot(slot_idx)
        return None

    def _parse_card_entry(self, card_info) -> tuple[str | None, str, str]:
        """Extrae (card_id, idioma, variante) de una entrada almacenada en binder_data."""
        card_id = None
        card_lang = "en"
        card_var = "Normal"
        if isinstance(card_info, dict):
            card_id = card_info.get("id_api")
            card_lang = card_info.get("idioma") or "en"
            card_var = card_info.get("variante") or "Normal"
        elif isinstance(card_info, str):
            if ":" in card_info:
                card_id, card_lang = card_info.split(":", 1)
            else:
                card_id = card_info
        return card_id, card_lang, card_var

    def _render_card_entry_into_slot(self, slot_widget, card_info, animate_insert: bool = False):
        """Carga los datos e imagen de card_info en slot_widget usando caché de metadatos e imágenes."""
        if not slot_widget or not card_info:
            return
        card_id, card_lang, card_var = self._parse_card_entry(card_info)
        if not card_id:
            return
        cfg = BINDER_MODES[self.current_mode]
        carta = self._get_card_meta(card_id, card_lang)
        if carta:
            n_archivo = carta.nombre.lower().replace(" ", "_")
            c_lang = carta.idioma or card_lang
            pixmap = get_webp_pixmap(card_id, carta.nombre, c_lang, size=(cfg["card_w"], cfg["card_h"]))
            if not pixmap:
                pixmap = get_pixmap_from_zip(n_archivo, size=(cfg["card_w"], cfg["card_h"]), id_api=card_id)
            if not pixmap:
                ruta_alt = os.path.join(IMAGES_DIR, f"{n_archivo}_{card_id}.webp")
                pixmap = get_cached_pixmap(ruta_alt, cfg["card_w"], cfg["card_h"])
            if not pixmap or pixmap.isNull():
                pixmap = get_card_placeholder_pixmap((cfg["card_w"], cfg["card_h"]), carta.nombre)
            slot_widget.set_card(
                card_id, n_archivo, pixmap,
                idioma=c_lang, variante=card_var, carta=carta, animate_insert=animate_insert
            )

    def get_used_card_counts_across_all_binders(self) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
        """
        Cuenta todas las copias colocadas de cada carta sumando TODOS los binders del usuario (Issue #24).
        Retorna (exact_counts[(id_api, idioma)], no_lang_counts[id_api]).
        """
        exact_counts: dict[tuple[str, str], int] = {}
        no_lang_counts: dict[str, int] = {}
        folders = self.get_user_folders()
        for f_data in folders.values():
            if not isinstance(f_data, dict):
                continue
            mode = f_data.get("mode", "3x3")
            cards_by_mode = f_data.get("cards", {})
            if not isinstance(cards_by_mode, dict):
                continue
            cards_dict = cards_by_mode.get(mode, {})
            if not isinstance(cards_dict, dict):
                continue
            for entry in cards_dict.values():
                if not entry:
                    continue
                if isinstance(entry, dict):
                    cid = entry.get("id_api")
                    if cid:
                        lang = entry.get("idioma")
                        if lang:
                            key = (str(cid), str(lang))
                            exact_counts[key] = exact_counts.get(key, 0) + 1
                        else:
                            no_lang_counts[str(cid)] = no_lang_counts.get(str(cid), 0) + 1
                elif isinstance(entry, str):
                    if ":" in entry:
                        cid, lang = entry.split(":", 1)
                        key = (cid, lang)
                        exact_counts[key] = exact_counts.get(key, 0) + 1
                    else:
                        no_lang_counts[entry] = no_lang_counts.get(entry, 0) + 1
        return exact_counts, no_lang_counts

    def get_owned_copies(self, card_id: str, idioma: str | None = None) -> int:
        """Retorna el total de copias que posee el usuario en su colección general para esa carta."""
        session = SessionLocal()
        try:
            q = session.query(UsuarioCarta).filter(
                UsuarioCarta.usuario_nombre == self.usuario,
                UsuarioCarta.carta_id == card_id,
            )
            if idioma:
                rel = q.filter(func.coalesce(UsuarioCarta.idioma, "es") == idioma).first()
                if rel:
                    return max(1, int(getattr(rel, "cantidad", 1) or 1))
            rows = q.all()
            if rows:
                return sum(max(1, int(getattr(r, "cantidad", 1) or 1)) for r in rows)
            return 0
        finally:
            session.close()

    def get_remaining_copies(self, card_id: str, idioma: str | None = None) -> int:
        """Retorna cuántas copias siguen disponibles para colocar considerando todos los binders."""
        owned = self.get_owned_copies(card_id, idioma)
        if owned <= 0:
            return 0
        exact_used, no_lang_used = self.get_used_card_counts_across_all_binders()
        if idioma:
            used = exact_used.get((card_id, idioma), 0) + no_lang_used.get(card_id, 0)
        else:
            used = sum(cnt for (cid, _), cnt in exact_used.items() if cid == card_id) + no_lang_used.get(card_id, 0)
        return max(0, owned - used)

    def handle_drop(self, page_idx, slot_idx, card_id, source_slot=None, nombre_archivo=None, idioma=None, variante="Normal"):
        if not idioma:
            idioma = "en"

        card_data_entry = {"id_api": card_id, "idioma": idioma, "variante": variante or "Normal"}
        existing_target = self.get_card_at(page_idx, slot_idx)

        # If the drag came from another slot in the binder
        if source_slot:
            try:
                src_page_str, src_slot_str = source_slot.split('_')
                src_page = int(src_page_str)
                src_slot = int(src_slot_str)

                # Soltar en el mismo bolsillo no hace nada
                if src_page == page_idx and src_slot == slot_idx:
                    return

                src_entry = self.get_card_at(src_page, src_slot)
                if src_entry is not None:
                    card_data_entry = copy.deepcopy(src_entry) if isinstance(src_entry, dict) else src_entry

                src_slot_widget = self._get_visible_slot(src_page, src_slot)
                if src_slot_widget:
                    src_slot_widget.set_selected(False)

                if existing_target is not None:
                    # Issue #60: Intercambiar posiciones en lugar de sobrescribir/eliminar la carta existente
                    swapped_entry = copy.deepcopy(existing_target) if isinstance(existing_target, dict) else existing_target
                    self.set_card_at(src_page, src_slot, swapped_entry, save=False)
                    if src_slot_widget:
                        self._render_card_entry_into_slot(src_slot_widget, swapped_entry, animate_insert=True)
                else:
                    self.set_card_at(src_page, src_slot, None, save=False)
                    if src_slot_widget:
                        src_slot_widget.clear_card()
            except Exception as e:
                print(f"Error resolving source slot during move: {e}")
        else:
            # Issue #24: Verificar límite compartido de copias disponibles en todos los binders
            same_as_target = False
            if existing_target is not None:
                t_id, t_lang, _t_var = self._parse_card_entry(existing_target)
                same_as_target = (t_id == card_id and (t_lang or "en") == idioma)
            if not same_as_target and self.get_remaining_copies(card_id, idioma) <= 0:
                show_toast(
                    t("No te quedan copias disponibles de esta carta (ya están repartidas en tus binders)."),
                    "warning",
                    2600,
                )
                return

        # Update target slot data and UI
        self.set_card_at(page_idx, slot_idx, card_data_entry, save=True)
        target_slot_widget = self._get_visible_slot(page_idx, slot_idx)
        if target_slot_widget:
            target_slot_widget.set_selected(False)
            self._render_card_entry_into_slot(target_slot_widget, card_data_entry, animate_insert=True)

        self.update_selection_state()
        self.actualizar_resumen_precios_binder()
        self.refresh_page_minimap()
        self.inventory.update_usage_badges()

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
        self.page_minimap.refresh(
            self.current_spread_index,
            page_counts,
            slots_per_page,
            page_move_mode=getattr(self, "move_pages_mode", False),
            selected_move_page=getattr(self, "_selected_move_page", None),
        )

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
        self.refresh_page_minimap()
        self.inventory.update_usage_badges()
        
    def next_spread(self):
        self.current_spread_index += 1
        self.update_spread(direction=1)

    # Should be called if Inventory changes (e.g. from Index)
    def refresh_inventory(self):
        self.inventory.refresh()
