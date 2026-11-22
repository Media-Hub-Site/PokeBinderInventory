import json
import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox, QDialog, QStackedWidget, QGridLayout,
    QComboBox, QColorDialog, QApplication, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QColor, QDrag
from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QMimeData, QTimer, pyqtSignal
from sqlalchemy import and_, func

from MyQtApp.config import USER_DATA_DIR, load_settings
from MyQtApp.session import SessionLocal
from MyQtApp.models import Mazo, MazoCarta, Cartas, UsuarioCarta
from MyQtApp.app.getImgs import (
    get_webp_pixmap, get_pixmap_from_zip, get_card_placeholder_pixmap,
    CardImageLoaderManager
)
from MyQtApp.app.db_services import obtener_categorias_usuario
from MyQtApp.i18n import t, language_manager
from MyQtApp.ui.toast import show_toast
from MyQtApp.ui.CardWidget import CardZoomOverlay
from MyQtApp.ui.BinderCoverWidget import BINDER_DESIGNS, resolve_design_key
from MyQtApp.ui.DeckBoxWidget import DeckBoxWidget, DeckBoxOpenAnimationOverlay
from MyQtApp.ui.FilterVisualBar import EnergyTypeFilterBar


DECK_BOXES_STYLE_FILE = os.path.join(USER_DATA_DIR, "deck_boxes.json")
_DEFAULT_DESIGN_KEYS = list(BINDER_DESIGNS.keys())


def _load_deck_box_styles() -> dict:
    if not os.path.exists(DECK_BOXES_STYLE_FILE):
        return {}
    try:
        with open(DECK_BOXES_STYLE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_deck_box_styles(data: dict):
    try:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        with open(DECK_BOXES_STYLE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando estilos de portamazos: {e}")


class DeckCardTileWidget(QFrame):
    """
    Tarjeta visual compacta de una carta dentro del Mazo (cuadrícula superior hasta 20 cols x 2 filas).
    Muestra la carta, badge de cantidad, botones - / + para copias y X para quitar del mazo.
    """
    quantity_changed = pyqtSignal()
    removed = pyqtSignal(str)  # card_key

    def __init__(self, card_data: dict, quantity: int = 1, parent=None):
        super().__init__(parent)
        self.card_data = card_data
        self.card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"
        self._quantity = max(1, int(quantity))

        self.setFixedSize(78, 118)
        self.setStyleSheet("""
            DeckCardTileWidget {
                background-color: rgba(15, 23, 42, 0.88);
                border: 1.5px solid rgba(247, 168, 184, 0.45);
                border-radius: 8px;
            }
            DeckCardTileWidget:hover {
                border-color: #f56b7b;
            }
        """)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(2)

        # Imagen de la carta
        self.lbl_img = QLabel(self)
        self.lbl_img.setFixedSize(70, 90)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setScaledContents(True)
        self.lbl_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_img.setToolTip(f"{card_data.get('nombre', 'Carta')} ({card_data.get('edition', '')})")

        lang = card_data.get("idioma", "es")
        id_api = card_data.get("id_api")
        nombre = card_data.get("nombre", "")

        pix = get_webp_pixmap(id_api, nombre, lang, size=(70, 90))
        if not pix:
            pix = get_pixmap_from_zip(nombre, size=(70, 90), id_api=id_api)
        if not pix or pix.isNull():
            pix = get_card_placeholder_pixmap((70, 90), nombre)
        self.lbl_img.setPixmap(pix)
        vbox.addWidget(self.lbl_img, alignment=Qt.AlignmentFlag.AlignCenter)

        # Badge flotante de copias sobre la esquina superior izquierda
        self.lbl_qty_badge = QLabel(f"x{self._quantity}", self)
        self.lbl_qty_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qty_badge.setFixedSize(26, 17)
        self.lbl_qty_badge.move(4, 4)
        self.lbl_qty_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(15, 23, 42, 225);
                color: #fde047;
                font-size: 10px;
                font-weight: 800;
                border: 1px solid #f59e0b;
                border-radius: 6px;
            }
        """)
        self.lbl_qty_badge.raise_()

        # Botón flotante X arriba a la derecha para quitar del mazo
        self.btn_remove = QPushButton("X", self)
        self.btn_remove.setFixedSize(18, 18)
        self.btn_remove.move(self.width() - 21, 3)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setToolTip(t("Quitar carta del mazo"))
        self.btn_remove.setStyleSheet("""
            QPushButton {
                background-color: rgba(220, 38, 38, 220);
                color: #ffffff;
                font-size: 9px;
                font-weight: 800;
                border: 1px solid #fca5a5;
                border-radius: 9px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        """)
        self.btn_remove.clicked.connect(lambda: self.removed.emit(self.card_key))
        self.btn_remove.raise_()

        # Barra inferior compacta: -  N  +
        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(2)

        btn_style = """
            QPushButton {
                background-color: #334155;
                color: #ffffff;
                font-size: 11px;
                font-weight: 800;
                border: none;
                border-radius: 4px;
                padding: 0;
            }
            QPushButton:hover { background-color: #f56b7b; }
        """

        btn_minus = QPushButton("-", self)
        btn_minus.setFixedSize(20, 18)
        btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minus.setStyleSheet(btn_style)
        btn_minus.clicked.connect(self.decrement)

        self.lbl_qty_small = QLabel(str(self._quantity), self)
        self.lbl_qty_small.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qty_small.setStyleSheet("color: #f8fafc; font-size: 10px; font-weight: 700; border: none; background: transparent;")

        btn_plus = QPushButton("+", self)
        btn_plus.setFixedSize(20, 18)
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.setStyleSheet(btn_style)
        btn_plus.clicked.connect(self.increment)

        ctrl_row.addWidget(btn_minus)
        ctrl_row.addWidget(self.lbl_qty_small, 1)
        ctrl_row.addWidget(btn_plus)
        vbox.addLayout(ctrl_row)

    def set_quantity(self, qty: int):
        self._quantity = max(1, min(99, int(qty)))
        self.lbl_qty_badge.setText(f"x{self._quantity}")
        self.lbl_qty_small.setText(str(self._quantity))
        self.quantity_changed.emit()

    def increment(self):
        if self._quantity < 99:
            self.set_quantity(self._quantity + 1)

    def decrement(self):
        if self._quantity <= 1:
            self.removed.emit(self.card_key)
        else:
            self.set_quantity(self._quantity - 1)

    def get_quantity(self) -> int:
        return self._quantity

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_zoom()
            return
        super().mouseDoubleClickEvent(event)

    def _open_zoom(self):
        parent_win = self.window()
        if not parent_win:
            return
        id_api = self.card_data.get("id_api")
        nombre = self.card_data.get("nombre", "")
        lang = self.card_data.get("idioma") or language_manager.current_language
        pix = get_webp_pixmap(id_api, nombre, lang, size=(450, 630))
        if not pix:
            pix = get_pixmap_from_zip(nombre, size=(450, 630), id_api=id_api)
        if not pix or pix.isNull():
            pix = self.lbl_img.pixmap()
        if pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(pix, origin_global, id_api=id_api, nombre_archivo=nombre.lower().replace(" ", "_"), idioma=lang)


class DeckDropZoneFrame(QFrame):
    """Zona superior receptora de Drag & Drop para las cartas del mazo (hasta 20 columnas x 2 filas)."""
    card_dropped = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("DeckDropZone")
        self._set_highlight(False)

    def _set_highlight(self, active: bool):
        if active:
            self.setStyleSheet("""
                QFrame#DeckDropZone {
                    background-color: rgba(30, 41, 59, 0.92);
                    border: 2px dashed #f56b7b;
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#DeckDropZone {
                    background-color: rgba(15, 23, 42, 0.80);
                    border: 1.5px solid #f2c4ce;
                    border-radius: 12px;
                }
            """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pokebinder-deckcard"):
            self._set_highlight(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_highlight(False)
        raw = event.mimeData().data("application/x-pokebinder-deckcard")
        if raw:
            try:
                card_data = json.loads(bytes(raw).decode("utf-8"))
                self.card_dropped.emit(card_data)
                event.acceptProposedAction()
                return
            except Exception as e:
                print(f"Error procesando drop de carta en mazo: {e}")
        event.ignore()


class DraggableCollectionCardWidget(QFrame):
    """Carta navegable de la colección del usuario; se puede arrastrar al mazo o agregar con clic/+."""
    quick_add_requested = pyqtSignal(dict)

    def __init__(self, card_data: dict, pixmap: QPixmap, in_deck_qty: int = 0, parent=None):
        super().__init__(parent)
        self.card_data = card_data
        self.card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"
        self._drag_start = QPoint()

        self.setFixedSize(108, 152)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet("""
            DraggableCollectionCardWidget {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 9px;
            }
            DraggableCollectionCardWidget:hover {
                border: 2px solid #f56b7b;
                background-color: #fff5f7;
            }
        """)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(0)

        self.lbl_img = QLabel(self)
        self.lbl_img.setFixedSize(100, 142)
        self.lbl_img.setScaledContents(True)
        self.lbl_img.setPixmap(pixmap)
        self.lbl_img.setToolTip(
            f"{card_data.get('nombre', 'Carta')} | {card_data.get('edition', '')}\n"
            f"Arrastra al mazo o haz doble clic para agregar"
        )
        vbox.addWidget(self.lbl_img, alignment=Qt.AlignmentFlag.AlignCenter)

        # Indicador de cuántas copias de esta carta ya están en el mazo
        self.lbl_in_deck = QLabel("", self)
        self.lbl_in_deck.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_in_deck.setFixedSize(30, 18)
        self.lbl_in_deck.move(5, 5)
        self.lbl_in_deck.setStyleSheet("""
            QLabel {
                background-color: rgba(16, 185, 129, 230);
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                border: 1px solid #a7f3d0;
                border-radius: 7px;
            }
        """)
        self.set_in_deck_qty(in_deck_qty)

        # Botón rápido + abajo a la derecha
        self.btn_add = QPushButton("+", self)
        self.btn_add.setFixedSize(22, 22)
        self.btn_add.move(self.width() - 26, self.height() - 26)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip(t("Agregar copia al mazo"))
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #f56b7b;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                border: 1.5px solid #ffffff;
                border-radius: 11px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #d44854;
            }
        """)
        self.btn_add.clicked.connect(lambda: self.quick_add_requested.emit(self.card_data))
        self.btn_add.raise_()

    def set_card_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.lbl_img.setPixmap(
                pixmap.scaled(100, 142, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            self.lbl_in_deck.raise_()
            self.btn_add.raise_()

    def set_in_deck_qty(self, qty: int):
        if qty > 0:
            self.lbl_in_deck.setText(f"x{qty}")
            self.lbl_in_deck.show()
            self.lbl_in_deck.raise_()
        else:
            self.lbl_in_deck.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.quick_add_requested.emit(self.card_data)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
            drag = QDrag(self)
            mime = QMimeData()
            payload = json.dumps(self.card_data, ensure_ascii=False).encode("utf-8")
            mime.setData("application/x-pokebinder-deckcard", payload)
            drag.setMimeData(mime)
            pix = self.lbl_img.pixmap()
            if pix and not pix.isNull():
                scaled = pix.scaled(76, 106, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                drag.setPixmap(scaled)
                drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))
            drag.exec(Qt.DropAction.CopyAction)


class DeckBoxCustomizeDialog(QDialog):
    """Diálogo con vista previa 3D en tiempo real para crear o personalizar un Portamazos."""

    def __init__(self, title="Crear Nuevo Portamazos", name="", design="Charizard Fuego", color="auto", card_count=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t(title))
        self.setFixedSize(560, 360)
        self._selected_color = color or "auto"

        self.setStyleSheet("""
            QDialog { background-color: #fff5f7; }
            QLabel { font-weight: 600; color: #5a2a3a; font-size: 12px; }
            QLineEdit, QComboBox {
                border: 1.5px solid #f29ca4;
                border-radius: 8px;
                padding: 6px 10px;
                background: #ffffff;
                color: #3f2730;
                font-size: 12px;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(20)

        preview_col = QVBoxLayout()
        preview_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_prev = QLabel(t("Vista previa 3D"))
        lbl_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_col.addWidget(lbl_prev)

        self.preview_box = DeckBoxWidget(
            name=name or "Mi Mazo",
            design=design,
            color=self._selected_color,
            card_count=card_count,
        )
        self.preview_box.setFixedSize(195, 240)
        preview_col.addWidget(self.preview_box, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(preview_col)

        form_col = QVBoxLayout()
        form_col.setSpacing(10)

        form_col.addWidget(QLabel(t("Nombre del Mazo")))
        self.input_name = QLineEdit(name)
        self.input_name.setPlaceholderText(t("Ej: Charizard ex Competitivo"))
        self.input_name.textChanged.connect(self._update_preview)
        form_col.addWidget(self.input_name)

        form_col.addWidget(QLabel(t("Diseño del Portamazos")))
        self.combo_design = QComboBox()
        for d_key in BINDER_DESIGNS.keys():
            self.combo_design.addItem(d_key, d_key)
        idx = self.combo_design.findData(resolve_design_key(design))
        if idx >= 0:
            self.combo_design.setCurrentIndex(idx)
        self.combo_design.currentIndexChanged.connect(self._update_preview)
        form_col.addWidget(self.combo_design)

        form_col.addWidget(QLabel(t("Color del Portamazos")))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)

        self.btn_color_auto = QPushButton(t("Automático del diseño"))
        self.btn_color_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color_auto.setFixedHeight(32)
        self.btn_color_auto.setStyleSheet("""
            QPushButton {
                background: #ffffff; color: #5a2a3a; border: 1.5px solid #f2b8c3;
                border-radius: 8px; padding: 2px 10px; font-weight: 600;
            }
            QPushButton:hover { background: #ffdfe6; }
        """)
        self.btn_color_auto.clicked.connect(self._reset_color_auto)
        color_row.addWidget(self.btn_color_auto)

        self.btn_color_pick = QPushButton(t("Elegir color"))
        self.btn_color_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color_pick.setFixedHeight(32)
        self.btn_color_pick.setStyleSheet("""
            QPushButton {
                background: #f7a8b8; color: #ffffff; border: 1.5px solid #f29ca4;
                border-radius: 8px; padding: 2px 12px; font-weight: 700;
            }
            QPushButton:hover { background: #f56b7b; }
        """)
        self.btn_color_pick.clicked.connect(self._pick_custom_color)
        color_row.addWidget(self.btn_color_pick)
        form_col.addLayout(color_row)

        form_col.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton(t("Cancelar"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #ffffff; color: #5a2a3a; border: 1.5px solid #f2b8c3;
                border-radius: 9px; padding: 4px 16px; font-weight: 600;
            }
            QPushButton:hover { background: #ffdfe6; }
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton(t("Guardar"))
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet("""
            QPushButton {
                background: #f56b7b; color: #ffffff; border: 1.5px solid #d44854;
                border-radius: 9px; padding: 4px 20px; font-weight: 700;
            }
            QPushButton:hover { background: #e05263; }
        """)
        btn_ok.clicked.connect(self._validate_and_accept)

        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        form_col.addLayout(btns)

        root.addLayout(form_col, 1)

    def _reset_color_auto(self):
        self._selected_color = "auto"
        self._update_preview()

    def _pick_custom_color(self):
        initial = QColor(self._selected_color) if self._selected_color != "auto" else QColor("#dc2626")
        col = QColorDialog.getColor(initial, self, t("Color personalizado del Portamazos"))
        if col.isValid():
            self._selected_color = col.name()
            self._update_preview()

    def _update_preview(self):
        self.preview_box.set_deck_props(
            name=self.input_name.text().strip() or "Mi Mazo",
            design=self.combo_design.currentData(),
            color=self._selected_color,
        )

    def _validate_and_accept(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, t("Nombre requerido"), t("Ingresa un nombre para el mazo."))
            return
        self.accept()

    def get_values(self) -> tuple[str, str, str]:
        return (
            self.input_name.text().strip(),
            self.combo_design.currentData(),
            self._selected_color,
        )


class MazosView(QWidget):
    """
    Sección de Mazos con Portamazos físicos 3D personalizables + Constructor Visual Drag & Drop:
      - Vista Home: Estantería de Portamazos 3D con apertura/cierre animado
      - Vista Editor:
          * Zona Superior: Cuadrícula visual de cartas del mazo (hasta 20 columnas x 2 filas) con - / + y X
          * Zona Inferior (mayor espacio): Navegador visual de tu colección para arrastrar cartas al mazo,
            con botón desplegable "Filtros" (nombre, rareza, tipo, edición, etapa, idioma, carpeta y barra de energías)
    """

    COL_PER_PAGE = 24
    DECK_MAX_COLS = 20

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()

        self.mazo_actual = None
        self.deck_tiles = {}          # card_key -> DeckCardTileWidget
        self.deck_order = []          # ordered list of card_keys
        self._deck_styles = _load_deck_box_styles()
        self._deck_box_widgets = {}   # mazo_id -> DeckBoxWidget
        self._active_overlay = None

        # Estado del navegador de colección inferior
        self.col_page = 0
        self.col_total = 0
        self.col_widgets_by_key = {}  # card_key -> list[DraggableCollectionCardWidget]
        self.col_image_loader = CardImageLoaderManager(max_threads=6, parent=self)
        self.col_image_loader.image_ready.connect(self._on_col_async_image_ready)

        self.init_ui()
        self.mostrar_estanteria_mazos(animate_close=False)

    def _get_deck_style(self, mazo_id: int) -> tuple[str, str]:
        entry = self._deck_styles.get(str(mazo_id))
        if isinstance(entry, dict):
            return resolve_design_key(entry.get("design", "Charizard Fuego")), entry.get("color", "auto")
        default_design = _DEFAULT_DESIGN_KEYS[int(mazo_id) % len(_DEFAULT_DESIGN_KEYS)]
        return default_design, "auto"

    def _set_deck_style(self, mazo_id: int, design: str, color: str):
        self._deck_styles[str(mazo_id)] = {
            "design": resolve_design_key(design),
            "color": color or "auto",
        }
        _save_deck_box_styles(self._deck_styles)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.main_stack = QStackedWidget(self)
        root_layout.addWidget(self.main_stack)

        self.decks_home_widget = QWidget()
        self._setup_home_view()
        self.main_stack.addWidget(self.decks_home_widget)

        self.deck_editor_widget = QWidget()
        self._setup_editor_view()
        self.main_stack.addWidget(self.deck_editor_widget)

    # ── PANTALLA 1: Estantería de Portamazos 3D ────────────────────────────────
    def _setup_home_view(self):
        layout = QVBoxLayout(self.decks_home_widget)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)

        self.home_header_widget = QWidget()
        self.home_header_widget.setStyleSheet("background: transparent; border: none;")
        top_bar = QHBoxLayout(self.home_header_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(14)

        lbl_title = QLabel(t("Mis Mazos"))
        lbl_title.setStyleSheet("font-size: 21px; font-weight: 700; color: #5a2a3a;")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        self.btn_nuevo_mazo_main = QPushButton(f"+ {t('Nuevo Mazo')}")
        self.btn_nuevo_mazo_main.setFixedHeight(38)
        self.btn_nuevo_mazo_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nuevo_mazo_main.setStyleSheet("""
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
        self.btn_nuevo_mazo_main.clicked.connect(self.crear_nuevo_mazo)
        top_bar.addWidget(self.btn_nuevo_mazo_main)
        layout.addWidget(self.home_header_widget)

        self.decks_scroll = QScrollArea()
        self.decks_scroll.setWidgetResizable(True)
        self.decks_scroll.setStyleSheet("background-color: transparent; border: none;")

        self.decks_container = QWidget()
        self.decks_container.setStyleSheet("background: transparent;")
        self.decks_grid = QGridLayout(self.decks_container)
        self.decks_grid.setSpacing(22)
        self.decks_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.decks_scroll.setWidget(self.decks_container)

        layout.addWidget(self.decks_scroll, 1)

    # ── PANTALLA 2: Constructor Visual del Mazo (Arriba: Mazo 20x2 | Abajo: Mi Colección) ──
    def _setup_editor_view(self):
        layout = QVBoxLayout(self.deck_editor_widget)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        # 1. Header compacto del Mazo
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self.btn_back_decks = QPushButton(t("Volver a Mazos"))
        self.btn_back_decks.setFixedHeight(30)
        self.btn_back_decks.setProperty("class", "pill")
        self.btn_back_decks.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_decks.clicked.connect(lambda: self.mostrar_estanteria_mazos(animate_close=True))
        header_row.addWidget(self.btn_back_decks)

        self.editor_mini_box = DeckBoxWidget(name="Mazo", design="Charizard Fuego", color="auto", card_count=0)
        self.editor_mini_box.setFixedSize(38, 46)
        self.editor_mini_box.setMinimumSize(38, 46)
        header_row.addWidget(self.editor_mini_box)

        self.lbl_mazo_nombre = QLabel(t("Selecciona un mazo"))
        self.lbl_mazo_nombre.setStyleSheet("font-size: 17px; font-weight: 700; color: #5a2a3a;")
        header_row.addWidget(self.lbl_mazo_nombre)

        header_row.addStretch()

        self.lbl_card_count = QLabel("0 / 60 cartas")
        self.lbl_card_count.setStyleSheet("font-size: 13px; font-weight: 700; color: #b45309;")
        header_row.addWidget(self.lbl_card_count)

        self.btn_customize_deck = QPushButton(t("Personalizar Portamazos"))
        self.btn_customize_deck.setFixedHeight(30)
        self.btn_customize_deck.setProperty("class", "pill")
        self.btn_customize_deck.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_customize_deck.clicked.connect(self.personalizar_mazo_actual)
        header_row.addWidget(self.btn_customize_deck)

        self.btn_guardar = QPushButton(t("Guardar Mazo"), self)
        self.btn_guardar.setFixedHeight(32)
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setStyleSheet("""
            QPushButton {
                background-color: #10b981; color: white; font-weight: 700;
                font-size: 12px; border-radius: 9px; padding: 4px 16px;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.btn_guardar.clicked.connect(self.guardar_mazo_actual)
        header_row.addWidget(self.btn_guardar)

        layout.addLayout(header_row)

        # 2. ZONA SUPERIOR: Cartas en el Mazo (hasta 20 columnas x 2 filas, acepta Drag & Drop)
        self.deck_drop_zone = DeckDropZoneFrame(self)
        self.deck_drop_zone.setFixedHeight(252)
        self.deck_drop_zone.card_dropped.connect(self._on_card_dropped_in_deck)

        drop_vbox = QVBoxLayout(self.deck_drop_zone)
        drop_vbox.setContentsMargins(8, 6, 8, 6)
        drop_vbox.setSpacing(4)

        self.deck_scroll = QScrollArea(self.deck_drop_zone)
        self.deck_scroll.setWidgetResizable(True)
        self.deck_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.deck_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.deck_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.deck_grid_container = QWidget()
        self.deck_grid_container.setStyleSheet("background: transparent;")
        self.deck_grid = QGridLayout(self.deck_grid_container)
        self.deck_grid.setContentsMargins(2, 2, 2, 2)
        self.deck_grid.setSpacing(6)
        self.deck_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.deck_scroll.setWidget(self.deck_grid_container)

        self.lbl_deck_empty_hint = QLabel(
            t("Arrastra cartas desde tu colección aquí abajo o haz doble clic para agregarlas a tu mazo")
        )
        self.lbl_deck_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_deck_empty_hint.setStyleSheet(
            "color: #cbd5e1; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )

        drop_vbox.addWidget(self.deck_scroll, 1)
        layout.addWidget(self.deck_drop_zone)

        # 3. ZONA INFERIOR (mayor espacio): Navegador Visual de Mi Colección + Filtros Desplegables
        col_panel = QFrame(self)
        col_panel.setObjectName("DeckCollectionPanel")
        col_panel.setStyleSheet("""
            QFrame#DeckCollectionPanel {
                background-color: #fff6f8;
                border: 1.5px solid #f3c8d1;
                border-radius: 12px;
            }
        """)
        col_vbox = QVBoxLayout(col_panel)
        col_vbox.setContentsMargins(10, 8, 10, 8)
        col_vbox.setSpacing(6)

        # Barra superior de Mi Colección con botón desplegable "Filtros"
        col_top_row = QHBoxLayout()
        col_top_row.setSpacing(8)

        lbl_col_title = QLabel(t("Mi Colección"))
        lbl_col_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;")
        col_top_row.addWidget(lbl_col_title)

        self.lbl_col_count = QLabel("")
        self.lbl_col_count.setStyleSheet("font-size: 11px; font-weight: 600; color: #8c5a69; border: none; background: transparent;")
        col_top_row.addWidget(self.lbl_col_count)

        col_top_row.addStretch()

        self.btn_toggle_filters = QPushButton(t("Filtros"))
        self.btn_toggle_filters.setCheckable(True)
        self.btn_toggle_filters.setChecked(False)
        self.btn_toggle_filters.setFixedHeight(28)
        self.btn_toggle_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_filters.clicked.connect(self._toggle_filters_drawer)
        self._refresh_filter_btn_style()
        col_top_row.addWidget(self.btn_toggle_filters)

        col_vbox.addLayout(col_top_row)

        # Panel desplegable de filtros (oculto inicialmente para maximizar espacio de cartas)
        self.filters_drawer = QFrame(col_panel)
        self.filters_drawer.setObjectName("DeckFiltersDrawer")
        self.filters_drawer.setStyleSheet("""
            QFrame#DeckFiltersDrawer {
                background-color: #ffeef2;
                border: 1px solid #f2b8c3;
                border-radius: 9px;
            }
        """)
        drawer_vbox = QVBoxLayout(self.filters_drawer)
        drawer_vbox.setContentsMargins(8, 6, 8, 6)
        drawer_vbox.setSpacing(6)

        # Fila 1 del drawer: Nombre + Carpeta + Idioma + Limpiar
        f_row1 = QHBoxLayout()
        f_row1.setSpacing(6)

        self.col_search = QLineEdit()
        self.col_search.setPlaceholderText(t("Filtrar por nombre..."))
        self.col_search.setFixedHeight(28)
        self.col_search.setStyleSheet("""
            QLineEdit {
                background: #ffffff; color: #3f2730; border: 1px solid #f29ca4;
                border-radius: 7px; padding: 2px 8px; font-size: 12px;
            }
        """)
        self.col_search_timer = QTimer(self)
        self.col_search_timer.setSingleShot(True)
        self.col_search_timer.timeout.connect(self._reset_col_page_and_load)
        self.col_search.textChanged.connect(lambda _: self.col_search_timer.start(220))
        f_row1.addWidget(self.col_search, 2)

        combo_f_style = """
            QComboBox {
                background: #ffffff; color: #3f2730; border: 1px solid #f29ca4;
                border-radius: 7px; padding: 2px 8px; font-size: 11px;
            }
        """

        self.col_combo_carpeta = QComboBox()
        self.col_combo_carpeta.setFixedHeight(28)
        self.col_combo_carpeta.setStyleSheet(combo_f_style)
        self.col_combo_carpeta.currentIndexChanged.connect(self._reset_col_page_and_load)
        f_row1.addWidget(self.col_combo_carpeta, 1)

        self.col_combo_idioma = QComboBox()
        self.col_combo_idioma.setFixedHeight(28)
        self.col_combo_idioma.setStyleSheet(combo_f_style)
        self.col_combo_idioma.addItem(f"{t('Idioma')}: {t('Todos')}", None)
        self.col_combo_idioma.addItem("Español", "es")
        self.col_combo_idioma.addItem("English", "en")
        self.col_combo_idioma.addItem("日本語", "ja")
        self.col_combo_idioma.addItem("Français", "fr")
        self.col_combo_idioma.addItem("Português", "pt")
        self.col_combo_idioma.addItem("繁體中文", "zh")
        self.col_combo_idioma.currentIndexChanged.connect(self._reset_col_page_and_load)
        f_row1.addWidget(self.col_combo_idioma, 1)

        btn_clean_f = QPushButton(t("Limpiar"))
        btn_clean_f.setFixedHeight(28)
        btn_clean_f.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clean_f.setStyleSheet("""
            QPushButton {
                background: #ffffff; color: #5a2a3a; border: 1px solid #f29ca4;
                border-radius: 7px; padding: 2px 10px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #ffdfe6; }
        """)
        btn_clean_f.clicked.connect(self._limpiar_filtros_coleccion)
        f_row1.addWidget(btn_clean_f)
        drawer_vbox.addLayout(f_row1)

        # Fila 2 del drawer: Rareza, Tipo, Edición, Etapa, Entrenador
        f_row2 = QHBoxLayout()
        f_row2.setSpacing(6)
        self.col_filtros = {}
        for etiqueta, columna in (
            ("Rareza", "rarity"),
            ("Tipo", "type"),
            ("Edición", "edition"),
            ("Etapa", "stage"),
            ("Entrenador", "trainer"),
        ):
            cb = QComboBox()
            cb.setFixedHeight(28)
            cb.setStyleSheet(combo_f_style)
            cb.addItem(f"{t(etiqueta)}: {t('Todos')}")
            cb.currentIndexChanged.connect(self._reset_col_page_and_load)
            self.col_filtros[columna] = cb
            f_row2.addWidget(cb, 1)
        drawer_vbox.addLayout(f_row2)

        # Fila 3 del drawer: Barra visual complementaria de Energías Pokémon (sin control de zoom)
        self.col_energy_bar = EnergyTypeFilterBar(self.filters_drawer)
        self.col_energy_bar.lbl_zoom.hide()
        for zb in self.col_energy_bar._zoom_buttons.values():
            zb.hide()
        self.col_energy_bar.type_selected.connect(self._on_col_energy_pill_selected)
        self.col_filtros["type"].currentIndexChanged.connect(self._sync_col_energy_from_combo)
        drawer_vbox.addWidget(self.col_energy_bar)

        self.filters_drawer.setVisible(False)
        col_vbox.addWidget(self.filters_drawer)

        # Cuadrícula desplazable de cartas de Mi Colección
        self.col_scroll = QScrollArea(col_panel)
        self.col_scroll.setWidgetResizable(True)
        self.col_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.col_grid_container = QWidget()
        self.col_grid_container.setStyleSheet("background: transparent;")
        self.col_grid = QGridLayout(self.col_grid_container)
        self.col_grid.setContentsMargins(2, 2, 2, 2)
        self.col_grid.setSpacing(8)
        self.col_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.col_scroll.setWidget(self.col_grid_container)
        col_vbox.addWidget(self.col_scroll, 1)

        # Paginación compacta de la colección
        pag_row = QHBoxLayout()
        pag_row.setContentsMargins(0, 0, 0, 0)
        pag_row.setSpacing(10)

        self.btn_col_prev = QPushButton(t("Anterior"))
        self.btn_col_prev.setFixedHeight(26)
        self.btn_col_prev.setProperty("class", "pill")
        self.btn_col_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_col_prev.clicked.connect(self._col_prev_page)

        self.lbl_col_page = QLabel("")
        self.lbl_col_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_col_page.setStyleSheet("font-size: 11px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;")

        self.btn_col_next = QPushButton(t("Siguiente"))
        self.btn_col_next.setFixedHeight(26)
        self.btn_col_next.setProperty("class", "pill")
        self.btn_col_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_col_next.clicked.connect(self._col_next_page)

        pag_row.addStretch()
        pag_row.addWidget(self.btn_col_prev)
        pag_row.addWidget(self.lbl_col_page)
        pag_row.addWidget(self.btn_col_next)
        pag_row.addStretch()
        col_vbox.addLayout(pag_row)

        layout.addWidget(col_panel, 1)

    # ── Helpers de Filtros Desplegables de Mi Colección ────────────────────────
    def _refresh_filter_btn_style(self):
        opened = self.btn_toggle_filters.isChecked()
        self.btn_toggle_filters.setText(t("Ocultar Filtros") if opened else t("Filtros"))
        if opened:
            self.btn_toggle_filters.setStyleSheet("""
                QPushButton {
                    background-color: #f56b7b; color: #ffffff; font-size: 11px; font-weight: 700;
                    border: 1.5px solid #d44854; border-radius: 9px; padding: 2px 14px;
                }
                QPushButton:hover { background-color: #e05263; }
            """)
        else:
            self.btn_toggle_filters.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff; color: #5a2a3a; font-size: 11px; font-weight: 700;
                    border: 1.5px solid #f2b8c3; border-radius: 9px; padding: 2px 14px;
                }
                QPushButton:hover { background-color: #ffdfe6; border-color: #f56b7b; }
            """)

    def _toggle_filters_drawer(self):
        self.filters_drawer.setVisible(self.btn_toggle_filters.isChecked())
        self._refresh_filter_btn_style()

    def _cargar_opciones_filtros_coleccion(self):
        # Carpetas de colección
        self.col_combo_carpeta.blockSignals(True)
        self.col_combo_carpeta.clear()
        self.col_combo_carpeta.addItem(f"{t('Carpeta')}: {t('Todas')}", None)
        for cat in obtener_categorias_usuario(self.usuario):
            self.col_combo_carpeta.addItem(cat, cat)
        self.col_combo_carpeta.blockSignals(False)

        # Combos dinámicos a partir de las cartas presentes en la colección del usuario
        for columna, combo in self.col_filtros.items():
            combo.blockSignals(True)
            first_lbl = combo.itemText(0)
            combo.clear()
            combo.addItem(first_lbl)
            vals = (
                self.session.query(getattr(Cartas, columna))
                .join(
                    UsuarioCarta,
                    and_(
                        Cartas.id_api == UsuarioCarta.carta_id,
                        func.coalesce(Cartas.idioma, "es") == func.coalesce(UsuarioCarta.idioma, "es"),
                    ),
                )
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
                .filter(getattr(Cartas, columna).isnot(None))
                .distinct()
                .all()
            )
            for v in sorted(x[0] for x in vals if x[0]):
                combo.addItem(v)
            combo.blockSignals(False)

    def _on_col_energy_pill_selected(self, type_val):
        combo = self.col_filtros.get("type")
        if not combo:
            return
        combo.blockSignals(True)
        if not type_val:
            combo.setCurrentIndex(0)
        else:
            idx = combo.findText(type_val, Qt.MatchFlag.MatchFixedString)
            if idx < 0 and type_val == "Lightning":
                idx = combo.findText("Electric", Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        self._reset_col_page_and_load()

    def _sync_col_energy_from_combo(self):
        combo = self.col_filtros.get("type")
        if combo:
            val = combo.currentText() if combo.currentIndex() > 0 else None
            self.col_energy_bar.set_active_type(val)

    def _limpiar_filtros_coleccion(self):
        self.col_search.blockSignals(True)
        self.col_search.clear()
        self.col_search.blockSignals(False)

        self.col_combo_carpeta.blockSignals(True)
        self.col_combo_carpeta.setCurrentIndex(0)
        self.col_combo_carpeta.blockSignals(False)

        self.col_combo_idioma.blockSignals(True)
        self.col_combo_idioma.setCurrentIndex(0)
        self.col_combo_idioma.blockSignals(False)

        for cb in self.col_filtros.values():
            cb.blockSignals(True)
            cb.setCurrentIndex(0)
            cb.blockSignals(False)
        self.col_energy_bar.set_active_type(None)
        self._reset_col_page_and_load()

    def _reset_col_page_and_load(self):
        self.col_page = 0
        self.cargar_coleccion_navegador()

    def _col_prev_page(self):
        if self.col_page > 0:
            self.col_page -= 1
            self.cargar_coleccion_navegador()

    def _col_next_page(self):
        total_pages = max(1, (self.col_total + self.COL_PER_PAGE - 1) // self.COL_PER_PAGE)
        if self.col_page < total_pages - 1:
            self.col_page += 1
            self.cargar_coleccion_navegador()

    def cargar_coleccion_navegador(self):
        """Carga las cartas de la colección del usuario en la cuadrícula inferior arrastrable."""
        self.col_widgets_by_key.clear()
        while self.col_grid.count():
            item = self.col_grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        q = (
            self.session.query(Cartas)
            .join(
                UsuarioCarta,
                and_(
                    Cartas.id_api == UsuarioCarta.carta_id,
                    func.coalesce(Cartas.idioma, "es") == func.coalesce(UsuarioCarta.idioma, "es"),
                ),
            )
            .filter(UsuarioCarta.usuario_nombre == self.usuario)
        )

        txt = self.col_search.text().strip().lower()
        if txt:
            q = q.filter(Cartas.nombre.ilike(f"%{txt}%"))

        carpeta = self.col_combo_carpeta.currentData()
        if carpeta:
            q = q.filter(UsuarioCarta.categoria == carpeta)

        lang = self.col_combo_idioma.currentData()
        if lang:
            q = q.filter(Cartas.idioma == lang)

        for columna, cb in self.col_filtros.items():
            if cb.currentIndex() > 0:
                q = q.filter(getattr(Cartas, columna) == cb.currentText())

        self.col_total = q.count()
        self.lbl_col_count.setText(f"({self.col_total} cartas)")

        cartas = (
            q.order_by(Cartas.nombre.asc())
            .limit(self.COL_PER_PAGE)
            .offset(self.col_page * self.COL_PER_PAGE)
            .all()
        )

        # Calcular columnas según ancho disponible (mínimo 6)
        avail_w = max(680, self.col_scroll.viewport().width() - 16)
        cols = max(6, avail_w // 118)

        row, col = 0, 0
        for carta in cartas:
            c_lang = carta.idioma or "es"
            card_key = f"{carta.id_api}:{c_lang}"
            card_data = {
                "id_api": carta.id_api,
                "nombre": carta.nombre,
                "idioma": c_lang,
                "edition": carta.edition or "",
            }

            pix = get_webp_pixmap(carta.id_api, carta.nombre, c_lang, size=(100, 142))
            needs_dl = False
            if not pix:
                pix = get_pixmap_from_zip(carta.nombre.lower().replace(" ", "_"), size=(100, 142), id_api=carta.id_api)
            if not pix or pix.isNull():
                pix = get_card_placeholder_pixmap((100, 142), carta.nombre)
                needs_dl = True

            in_deck_qty = self.deck_tiles[card_key].get_quantity() if card_key in self.deck_tiles else 0
            cw = DraggableCollectionCardWidget(card_data, pix, in_deck_qty=in_deck_qty, parent=self.col_grid_container)
            cw.quick_add_requested.connect(self._on_card_dropped_in_deck)
            self.col_grid.addWidget(cw, row, col)
            self.col_widgets_by_key.setdefault(card_key, []).append(cw)

            if needs_dl:
                self.col_image_loader.request_image(
                    card_key,
                    carta.id_api,
                    carta.nombre,
                    idioma=c_lang,
                    set_id=getattr(carta, "set_id", None),
                    number=getattr(carta, "number", None),
                )

            col += 1
            if col >= cols:
                col = 0
                row += 1

        total_pages = max(1, (self.col_total + self.COL_PER_PAGE - 1) // self.COL_PER_PAGE)
        self.lbl_col_page.setText(f"{t('Página')} {self.col_page + 1} {t('de')} {total_pages}")
        self.btn_col_prev.setEnabled(self.col_page > 0)
        self.btn_col_next.setEnabled(self.col_page < total_pages - 1)

    def _on_col_async_image_ready(self, card_key: str, local_path: str):
        widgets = self.col_widgets_by_key.get(card_key)
        if not widgets or not os.path.exists(local_path):
            return
        pix = QPixmap(local_path)
        if pix.isNull():
            return
        for w in list(widgets):
            try:
                w.set_card_pixmap(pix)
            except RuntimeError:
                pass

    def _sync_collection_badges_for_key(self, card_key: str):
        qty = self.deck_tiles[card_key].get_quantity() if card_key in self.deck_tiles else 0
        for w in self.col_widgets_by_key.get(card_key, []):
            try:
                w.set_in_deck_qty(qty)
            except RuntimeError:
                pass

    # ── Gestión de la Cuadrícula del Mazo (20 columnas x 2 filas) ──────────────
    def _reflow_deck_grid(self):
        while self.deck_grid.count():
            self.deck_grid.takeAt(0)

        if not self.deck_order:
            self.lbl_deck_empty_hint.show()
            self.deck_grid.addWidget(self.lbl_deck_empty_hint, 0, 0, Qt.AlignmentFlag.AlignCenter)
            return

        self.lbl_deck_empty_hint.hide()
        for idx, card_key in enumerate(self.deck_order):
            tile = self.deck_tiles.get(card_key)
            if not tile:
                continue
            r = idx // self.DECK_MAX_COLS
            c = idx % self.DECK_MAX_COLS
            self.deck_grid.addWidget(tile, r, c)

    def _on_card_dropped_in_deck(self, card_data: dict):
        if not self.mazo_actual:
            return
        self.agregar_carta_tile(card_data, quantity=1)

    def agregar_carta_tile(self, card_data: dict, quantity: int = 1):
        card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"
        if card_key in self.deck_tiles:
            tile = self.deck_tiles[card_key]
            tile.set_quantity(tile.get_quantity() + quantity)
        else:
            tile = DeckCardTileWidget(card_data, quantity=quantity, parent=self.deck_grid_container)
            tile.quantity_changed.connect(lambda k=card_key: self._on_tile_qty_changed(k))
            tile.removed.connect(self.remover_carta_tile)
            self.deck_tiles[card_key] = tile
            self.deck_order.append(card_key)
            self._reflow_deck_grid()
        self._sync_collection_badges_for_key(card_key)
        self.actualizar_conteo()

    def _on_tile_qty_changed(self, card_key: str):
        self._sync_collection_badges_for_key(card_key)
        self.actualizar_conteo()

    def remover_carta_tile(self, card_key: str):
        tile = self.deck_tiles.pop(card_key, None)
        if card_key in self.deck_order:
            self.deck_order.remove(card_key)
        if tile:
            tile.setParent(None)
            tile.deleteLater()
        self._reflow_deck_grid()
        self._sync_collection_badges_for_key(card_key)
        self.actualizar_conteo()

    def limpiar_editor(self):
        for tile in list(self.deck_tiles.values()):
            tile.setParent(None)
            tile.deleteLater()
        self.deck_tiles.clear()
        self.deck_order.clear()
        self._reflow_deck_grid()
        self.lbl_mazo_nombre.setText(t("Selecciona un mazo"))
        self.lbl_card_count.setText("0 / 60 cartas")

    def cargar_cartas_de_mazo(self, mazo: Mazo):
        self.limpiar_editor()
        self.lbl_mazo_nombre.setText(mazo.nombre)
        for mc in mazo.cartas:
            data = {
                "id_api": mc.id_api,
                "nombre": mc.nombre_carta,
                "idioma": mc.idioma,
                "edition": mc.edition or ""
            }
            self.agregar_carta_tile(data, quantity=mc.cantidad)
        self.actualizar_conteo()

    def actualizar_conteo(self):
        total = sum(w.get_quantity() for w in self.deck_tiles.values())
        self.lbl_card_count.setText(f"{total} / 60 cartas")
        self.editor_mini_box.set_deck_props(card_count=total)
        if total == 60:
            self.lbl_card_count.setStyleSheet("font-size: 13px; font-weight: 700; color: #15803d;")
        else:
            self.lbl_card_count.setStyleSheet("font-size: 13px; font-weight: 700; color: #b45309;")

    # ── Estantería de Portamazos + Animaciones 3D de Apertura / Cierre ─────────
    def cargar_mazos(self):
        self.session.expire_all()
        self._deck_box_widgets.clear()
        for i in reversed(range(self.decks_grid.count())):
            item = self.decks_grid.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        mazos = self.session.query(Mazo).filter(Mazo.usuario_nombre == self.usuario).all()
        if not mazos:
            self.home_header_widget.setVisible(False)
            self.decks_grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_first = QPushButton(f"¿Quieres crear un mazo?\n\n+ {t('Crear mi primer portamazos')}")
            btn_first.setFixedSize(360, 175)
            btn_first.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_first.setStyleSheet("""
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
            """)
            btn_first.clicked.connect(self.crear_nuevo_mazo)
            self.decks_grid.addWidget(btn_first, 0, 0, Qt.AlignmentFlag.AlignCenter)
            return

        self.home_header_widget.setVisible(True)
        self.decks_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        cols = 3
        row, col = 0, 0
        for m in mazos:
            card_w = self._crear_tarjeta_portamazos(m)
            self.decks_grid.addWidget(card_w, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _crear_tarjeta_portamazos(self, mazo: Mazo) -> QFrame:
        total_qty = sum(mc.cantidad for mc in mazo.cartas)
        design, color = self._get_deck_style(mazo.id)

        frame = QFrame()
        frame.setFixedSize(222, 300)
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

        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(6)

        deck_box = DeckBoxWidget(
            name=mazo.nombre,
            design=design,
            color=color,
            card_count=total_qty,
            parent=frame,
        )
        deck_box.setFixedSize(198, 224)
        self._deck_box_widgets[mazo.id] = deck_box
        vbox.addWidget(deck_box, alignment=Qt.AlignmentFlag.AlignHCenter)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(2, 0, 2, 0)
        bottom_row.setSpacing(6)

        lbl_cnt = QLabel(f"{total_qty} / 60")
        cnt_c = "#15803d" if total_qty == 60 else "#703043"
        lbl_cnt.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {cnt_c}; border: none; background: transparent;")
        bottom_row.addWidget(lbl_cnt)
        bottom_row.addStretch()

        btn_edit = QPushButton(t("Diseño"))
        btn_edit.setFixedHeight(22)
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setStyleSheet("""
            QPushButton {
                background: #fff0f4; color: #5a2a3a; border: 1px solid #f2b8c3;
                border-radius: 6px; padding: 0 8px; font-size: 10px; font-weight: 600;
            }
            QPushButton:hover { background: #f7a8b8; color: white; border-color: #f56b7b; }
        """)
        btn_edit.clicked.connect(lambda ch, mid=mazo.id: self.personalizar_mazo_por_id(mid))
        bottom_row.addWidget(btn_edit)

        btn_del = QPushButton(t("Eliminar"))
        btn_del.setFixedHeight(22)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent; color: #b91c1c; border: 1px solid #fecaca;
                border-radius: 6px; padding: 0 8px; font-size: 10px; font-weight: 600;
            }
            QPushButton:hover { background: #fee2e2; border-color: #ef4444; }
        """)
        btn_del.clicked.connect(lambda ch, mid=mazo.id: self.eliminar_mazo_por_id(mid))
        bottom_row.addWidget(btn_del)

        vbox.addLayout(bottom_row)

        def on_enter(ev):
            deck_box.set_hovered(True)
            QFrame.enterEvent(frame, ev)

        def on_leave(ev):
            deck_box.set_hovered(False)
            QFrame.leaveEvent(frame, ev)

        def on_click(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self.abrir_mazo(mazo.id, origin_widget=deck_box)

        frame.enterEvent = on_enter
        frame.leaveEvent = on_leave
        frame.mousePressEvent = on_click

        return frame

    def mostrar_estanteria_mazos(self, animate_close=False):
        animaciones_activas = load_settings().get("animaciones", True)
        if (
            animate_close
            and animaciones_activas
            and self.main_stack.currentWidget() is self.deck_editor_widget
            and self.mazo_actual is not None
        ):
            try:
                closing_id = self.mazo_actual.id
                closing_name = self.mazo_actual.nombre
                design, color = self._get_deck_style(closing_id)
                total_qty = sum(w.get_quantity() for w in self.deck_tiles.values())

                editor_pix = self.deck_editor_widget.grab()

                self.cargar_mazos()
                self.main_stack.setCurrentWidget(self.decks_home_widget)
                if self.decks_home_widget.layout():
                    self.decks_home_widget.layout().activate()
                if self.decks_container.layout():
                    self.decks_container.layout().activate()
                QApplication.processEvents()

                target_rect = None
                target_box = self._deck_box_widgets.get(closing_id)
                if target_box is not None:
                    tl = target_box.mapTo(self.main_stack, QPoint(0, 0))
                    target_rect = QRectF(float(tl.x()), float(tl.y()), float(target_box.width()), float(target_box.height()))

                shelf_pix = self.decks_home_widget.grab()

                if self._active_overlay:
                    try:
                        self._active_overlay.deleteLater()
                    except Exception:
                        pass
                ov = DeckBoxOpenAnimationOverlay(
                    parent=self.main_stack,
                    name=closing_name,
                    design=design,
                    color=color,
                    card_count=total_qty,
                    origin_rect=target_rect,
                    reverse=True,
                    shelf_pixmap=shelf_pix,
                    editor_pixmap=editor_pix,
                )
                self._active_overlay = ov
                ov.animation_finished.connect(lambda: setattr(self, "_active_overlay", None))
                return
            except Exception as e:
                print(f"Error en animación de cierre de portamazos: {e}")

        self.cargar_mazos()
        self.main_stack.setCurrentWidget(self.decks_home_widget)

    def abrir_mazo(self, mazo_id: int, origin_widget=None):
        mazo = self.session.query(Mazo).filter(Mazo.id == mazo_id).first()
        if not mazo:
            return

        animaciones_activas = load_settings().get("animaciones", True)
        shelf_pix = None
        origin_rect = None
        if animaciones_activas and self.main_stack.currentWidget() is self.decks_home_widget:
            shelf_pix = self.decks_home_widget.grab()
            if origin_widget is not None:
                try:
                    tl = origin_widget.mapTo(self.main_stack, QPoint(0, 0))
                    origin_rect = QRectF(float(tl.x()), float(tl.y()), float(origin_widget.width()), float(origin_widget.height()))
                except Exception:
                    origin_rect = None

        self.mazo_actual = mazo
        design, color = self._get_deck_style(mazo.id)
        total_qty = sum(mc.cantidad for mc in mazo.cartas)
        self.editor_mini_box.set_deck_props(name=mazo.nombre, design=design, color=color, card_count=total_qty)
        self.cargar_cartas_de_mazo(mazo)
        self._cargar_opciones_filtros_coleccion()
        self.col_page = 0
        self.cargar_coleccion_navegador()
        self.main_stack.setCurrentWidget(self.deck_editor_widget)

        if animaciones_activas:
            try:
                if self.deck_editor_widget.layout():
                    self.deck_editor_widget.layout().activate()
                QApplication.processEvents()
                editor_pix = self.deck_editor_widget.grab()

                if self._active_overlay:
                    try:
                        self._active_overlay.deleteLater()
                    except Exception:
                        pass
                ov = DeckBoxOpenAnimationOverlay(
                    parent=self.main_stack,
                    name=mazo.nombre,
                    design=design,
                    color=color,
                    card_count=total_qty,
                    origin_rect=origin_rect,
                    reverse=False,
                    shelf_pixmap=shelf_pix,
                    editor_pixmap=editor_pix,
                )
                self._active_overlay = ov
                ov.animation_finished.connect(lambda: setattr(self, "_active_overlay", None))
            except Exception as e:
                print(f"Error en animación de apertura de portamazos: {e}")

    def crear_nuevo_mazo(self):
        dlg = DeckBoxCustomizeDialog(title="Crear Nuevo Portamazos", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            nombre, design, color = dlg.get_values()
            nuevo = Mazo(usuario_nombre=self.usuario, nombre=nombre)
            self.session.add(nuevo)
            self.session.commit()
            self._set_deck_style(nuevo.id, design, color)
            self.cargar_mazos()
            show_toast(f"Portamazos '{nombre}' creado con éxito.", "success", 2500)

    def personalizar_mazo_por_id(self, mazo_id: int):
        mazo = self.session.query(Mazo).filter(Mazo.id == mazo_id).first()
        if not mazo:
            return
        design, color = self._get_deck_style(mazo.id)
        total_qty = sum(mc.cantidad for mc in mazo.cartas)
        dlg = DeckBoxCustomizeDialog(
            title="Personalizar Portamazos",
            name=mazo.nombre,
            design=design,
            color=color,
            card_count=total_qty,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name, new_design, new_color = dlg.get_values()
            mazo.nombre = new_name
            self.session.commit()
            self._set_deck_style(mazo.id, new_design, new_color)
            if self.mazo_actual and self.mazo_actual.id == mazo.id:
                self.lbl_mazo_nombre.setText(new_name)
                self.editor_mini_box.set_deck_props(name=new_name, design=new_design, color=new_color, card_count=total_qty)
            self.cargar_mazos()
            show_toast("Portamazos actualizado.", "success", 2200)

    def personalizar_mazo_actual(self):
        if self.mazo_actual:
            self.personalizar_mazo_por_id(self.mazo_actual.id)

    def eliminar_mazo_por_id(self, mazo_id: int):
        mazo = self.session.query(Mazo).filter(Mazo.id == mazo_id).first()
        if not mazo:
            return
        resp = QMessageBox.question(
            self,
            t("Eliminar Mazo"),
            f"¿Seguro que deseas eliminar '{mazo.nombre}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.session.delete(mazo)
            self.session.commit()
            self._deck_styles.pop(str(mazo_id), None)
            _save_deck_box_styles(self._deck_styles)
            if self.mazo_actual and self.mazo_actual.id == mazo_id:
                self.mazo_actual = None
                self.limpiar_editor()
            self.cargar_mazos()
            show_toast("Mazo eliminado.", "info", 2000)

    def guardar_mazo_actual(self):
        if not self.mazo_actual:
            return
        try:
            self.session.query(MazoCarta).filter(MazoCarta.mazo_id == self.mazo_actual.id).delete()
            for key in self.deck_order:
                tile = self.deck_tiles.get(key)
                if not tile:
                    continue
                d = tile.card_data
                mc = MazoCarta(
                    mazo_id=self.mazo_actual.id,
                    id_api=d.get("id_api"),
                    nombre_carta=d.get("nombre"),
                    cantidad=tile.get_quantity(),
                    idioma=d.get("idioma", "es"),
                    edition=d.get("edition", "")
                )
                self.session.add(mc)
            self.session.commit()
            show_toast("Mazo guardado correctamente.", "success", 2500)
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"Error guardando mazo: {e}")
