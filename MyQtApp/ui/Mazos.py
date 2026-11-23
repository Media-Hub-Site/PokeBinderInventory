import json
import os
import re
import shutil
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox, QDialog, QStackedWidget, QGridLayout,
    QComboBox, QColorDialog, QApplication, QSizePolicy, QMenu,
    QFileDialog, QTabWidget
)
from PyQt6.QtGui import QPixmap, QColor, QDrag, QAction, QPalette
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
from MyQtApp.ui.DeckBoxWidget import DeckBoxWidget, DeckBoxOpenAnimationOverlay, DECK_COVERS_DIR
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

    def __init__(self, card_data: dict, pixmap: QPixmap, in_deck_qty: int = 0, card_size=(100, 142), parent=None):
        super().__init__(parent)
        self.card_data = card_data
        self.card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"
        self.card_size = card_size
        self._drag_start = QPoint()

        cw, ch = card_size
        self.setFixedSize(cw + 8, ch + 10)
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
        self.lbl_img.setFixedSize(cw, ch)
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
            cw, ch = self.card_size
            self.lbl_img.setPixmap(
                pixmap.scaled(cw, ch, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
    """Diálogo con vista previa 3D en tiempo real para crear o personalizar un Portamazos (Predefinidos / Personalizar)."""

    def __init__(
        self,
        title="Crear Nuevo Portamazos",
        name="",
        design="Charizard Fuego",
        color="auto",
        card_count=0,
        custom_image=None,
        editing=False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t(title))
        self.setFixedSize(640, 420)

        default_design = resolve_design_key(design or list(BINDER_DESIGNS.keys())[0])
        init_color = color or "auto"
        init_custom_image = custom_image or None
        is_custom_initially = bool(
            editing and (init_custom_image or (init_color and str(init_color).lower() not in ("", "auto", "#ffeef2")))
        )

        self._state = {
            "custom_color": init_color if (init_color and str(init_color).lower() not in ("", "auto", "#ffeef2")) else "#1e1b26",
            "custom_image": init_custom_image,
        }
        self._final_values = (name, default_design, init_color, init_custom_image)

        self.setStyleSheet("""
            QDialog { background-color: #fff5f7; }
            QLabel { font-weight: 600; color: #5a2a3a; font-size: 12px; }
            QLineEdit, QComboBox {
                border: 2px solid #f7a8b8;
                border-radius: 9px;
                padding: 6px 10px;
                background: #ffffff;
                color: #3f2730;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #f56b7b;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #ffffff;
                selection-background-color: #e25b70;
                selection-color: #ffffff;
                border: 1px solid #f29ca4;
                outline: 0;
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

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(18)

        # --- Columna Izquierda: Vista previa 3D física en vivo ---
        preview_panel = QFrame()
        preview_panel.setFixedWidth(218)
        preview_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 14px;
            }
        """)
        preview_col = QVBoxLayout(preview_panel)
        preview_col.setContentsMargins(12, 12, 12, 12)
        preview_col.setSpacing(8)

        lbl_prev = QLabel(t("Vista previa 3D"))
        lbl_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_prev.setStyleSheet("font-size: 12px; font-weight: 700; color: #8c5464; border: none; background: transparent;")
        preview_col.addWidget(lbl_prev)

        self.preview_box = DeckBoxWidget(
            name=name or "Mi Mazo",
            design=default_design,
            color=init_color,
            card_count=card_count,
            custom_image=init_custom_image,
            parent=preview_panel,
        )
        self.preview_box.setFixedSize(192, 240)
        preview_col.addWidget(self.preview_box, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_col.addStretch()
        root.addWidget(preview_panel)

        # --- Columna Derecha: Formulario con Predefinidos / Personalizar ---
        form_col = QVBoxLayout()
        form_col.setSpacing(8)

        lbl_heading = QLabel(t("Editar Portamazos") if editing else t("Configura tu Portamazos"))
        lbl_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #5a2a3a;")
        form_col.addWidget(lbl_heading)

        form_col.addWidget(QLabel(t("Nombre del Mazo")))
        self.input_name = QLineEdit(name)
        self.input_name.setPlaceholderText(t("Ej: Charizard ex Competitivo"))
        self.input_name.textChanged.connect(self._update_preview)
        form_col.addWidget(self.input_name)

        # Pestañas: Predefinidos vs Personalizar (Issue #50)
        self.tabs = QTabWidget()

        # -- Tab 1: Predefinidos --
        tab_predef = QWidget()
        tab_predef.setStyleSheet("background: transparent;")
        predef_layout = QVBoxLayout(tab_predef)
        predef_layout.setContentsMargins(10, 10, 10, 10)
        predef_layout.setSpacing(8)

        predef_layout.addWidget(QLabel(t("Diseño predefinido (asigna portada y colores)")))
        self.combo_design = QComboBox()
        for d_key in BINDER_DESIGNS.keys():
            self.combo_design.addItem(d_key, d_key)
        self._style_combo_popup_white_text(self.combo_design)
        idx = self.combo_design.findData(default_design)
        if idx >= 0:
            self.combo_design.setCurrentIndex(idx)
        self.combo_design.currentIndexChanged.connect(self._update_preview)
        predef_layout.addWidget(self.combo_design)

        lbl_predef_hint = QLabel(
            t("Cada diseño aplica automáticamente su color de portamazos e ilustración temática.")
        )
        lbl_predef_hint.setWordWrap(True)
        lbl_predef_hint.setStyleSheet("font-size: 11px; font-weight: 400; color: #8c5464;")
        predef_layout.addWidget(lbl_predef_hint)
        predef_layout.addStretch()
        self.tabs.addTab(tab_predef, t("Predefinidos"))

        # -- Tab 2: Personalizar --
        tab_custom = QWidget()
        tab_custom.setStyleSheet("background: transparent;")
        custom_layout = QVBoxLayout(tab_custom)
        custom_layout.setContentsMargins(10, 10, 10, 10)
        custom_layout.setSpacing(8)

        custom_layout.addWidget(QLabel(t("Color completo del portamazos")))
        self.btn_cover_color = QPushButton()
        self.btn_cover_color.setFixedHeight(32)
        self.btn_cover_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cover_color.clicked.connect(self._pick_custom_color)
        custom_layout.addWidget(self.btn_cover_color)

        custom_layout.addWidget(QLabel(t("Imagen de portada (opcional, soporta PNG transparente)")))
        img_row = QHBoxLayout()
        img_row.setSpacing(8)

        self.btn_pick_img = QPushButton(t("Elegir imagen..."))
        self.btn_pick_img.setFixedHeight(32)
        self.btn_pick_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_img.setProperty("class", "pill")
        self.btn_pick_img.clicked.connect(self._choose_custom_image)

        self.btn_clear_img = QPushButton(t("Quitar imagen"))
        self.btn_clear_img.setFixedHeight(32)
        self.btn_clear_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_img.setProperty("class", "pill")
        self.btn_clear_img.clicked.connect(self._clear_custom_image)

        img_row.addWidget(self.btn_pick_img, 1)
        img_row.addWidget(self.btn_clear_img)
        custom_layout.addLayout(img_row)

        self.lbl_img_file = QLabel("")
        self.lbl_img_file.setWordWrap(True)
        self.lbl_img_file.setStyleSheet("font-size: 11px; font-weight: 400; color: #703043;")
        custom_layout.addWidget(self.lbl_img_file)
        custom_layout.addStretch()
        self.tabs.addTab(tab_custom, t("Personalizar"))

        if is_custom_initially:
            self.tabs.setCurrentIndex(1)
        self.tabs.currentChanged.connect(lambda _: self._update_preview())
        form_col.addWidget(self.tabs)

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

        btn_ok = QPushButton(t("Guardar Cambios") if editing else t("Crear Portamazos"))
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
        self._update_preview()

    @staticmethod
    def _style_combo_popup_white_text(cb: QComboBox):
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

    @staticmethod
    def _contrast_text(hex_col: str) -> str:
        c = QColor(hex_col)
        if not c.isValid():
            return "#ffffff"
        luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        return "#1e293b" if luma > 160 else "#ffffff"

    def _pick_custom_color(self):
        initial = QColor(self._state["custom_color"])
        col = QColorDialog.getColor(initial, self, t("Color personalizado del Portamazos"))
        if col.isValid():
            self._state["custom_color"] = col.name()
            self._update_preview()

    def _choose_custom_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            t("Seleccionar imagen para portada del Portamazos"),
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_path and os.path.exists(file_path):
            self._state["custom_image"] = file_path
            self._update_preview()

    def _clear_custom_image(self):
        self._state["custom_image"] = None
        self._update_preview()

    def _update_preview(self):
        is_custom = self.tabs.currentIndex() == 1
        cc = self._state["custom_color"]
        self.btn_cover_color.setText(f"{t('Color del portamazos')}: {cc.upper()}")
        self.btn_cover_color.setStyleSheet(
            f"background-color: {cc}; color: {self._contrast_text(cc)}; "
            f"border: 2px solid #5a2a3a; border-radius: 9px; font-weight: 700;"
        )

        if self._state["custom_image"]:
            self.lbl_img_file.setText(f"{t('Imagen')}: {os.path.basename(self._state['custom_image'])}")
            self.btn_clear_img.setEnabled(True)
        else:
            self.lbl_img_file.setText(t("Sin imagen personalizada (se usará color liso minimalista)"))
            self.btn_clear_img.setEnabled(False)

        if is_custom:
            self.preview_box.set_deck_props(
                name=self.input_name.text().strip() or "Mi Mazo",
                design="Ultra PRO Minimalista",
                color=cc,
                custom_image=self._state["custom_image"],
            )
        else:
            self.preview_box.set_deck_props(
                name=self.input_name.text().strip() or "Mi Mazo",
                design=self.combo_design.currentData(),
                color="auto",
                custom_image=None,
            )

    def _validate_and_accept(self):
        nombre = self.input_name.text().strip()
        if not nombre:
            QMessageBox.warning(self, t("Nombre requerido"), t("Ingresa un nombre para el mazo."))
            return

        is_custom = self.tabs.currentIndex() == 1
        final_design = "Ultra PRO Minimalista" if is_custom else self.combo_design.currentData()
        final_color = self._state["custom_color"] if is_custom else "auto"

        # Persistir imagen personalizada en DECK_COVERS_DIR para que no se pierda si mueven el archivo original
        final_custom_image = None
        if is_custom and self._state["custom_image"]:
            src_path = self._state["custom_image"]
            if os.path.isabs(src_path) and os.path.exists(src_path):
                try:
                    os.makedirs(DECK_COVERS_DIR, exist_ok=True)
                    abs_covers = os.path.abspath(DECK_COVERS_DIR)
                    if os.path.abspath(src_path).startswith(abs_covers):
                        final_custom_image = os.path.basename(src_path)
                    else:
                        ext = os.path.splitext(src_path)[1].lower() or ".png"
                        fname = f"deck_cover_{int(time.time() * 1000)}{ext}"
                        shutil.copy2(src_path, os.path.join(DECK_COVERS_DIR, fname))
                        final_custom_image = fname
                except Exception as e:
                    print(f"Error copiando imagen personalizada de portamazos: {e}")
                    final_custom_image = src_path
            else:
                final_custom_image = src_path

        self._final_values = (nombre, final_design, final_color, final_custom_image)
        self.accept()

    def get_values(self) -> tuple[str, str, str, str | None]:
        return self._final_values


class MazosView(QWidget):
    open_deck_in_print_requested = pyqtSignal(int, str)  # (mazo_id, mode: "print" | "csv")

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
        self.col_coleccion_activa = None  # None significa "Todas"
        self.col_orden_activo = None      # "rarity" | "type" | "idioma" | None
        self.col_widgets_by_key = {}  # card_key -> list[DraggableCollectionCardWidget]
        self._col_ordered_widgets = []
        self._last_col_grid_cols = 0
        self._col_resize_timer = QTimer(self)
        self._col_resize_timer.setSingleShot(True)
        self._col_resize_timer.timeout.connect(self._check_col_grid_reflow)
        self.col_image_loader = CardImageLoaderManager(max_threads=6, parent=self)
        self.col_image_loader.image_ready.connect(self._on_col_async_image_ready)

        self.init_ui()
        self.mostrar_estanteria_mazos(animate_close=False)

    def _get_deck_style(self, mazo_id: int) -> tuple[str, str, bool, str | None]:
        entry = self._deck_styles.get(str(mazo_id))
        if isinstance(entry, dict):
            design = resolve_design_key(entry.get("design", "Charizard Fuego"))
            color = entry.get("color", "auto")
            locked = bool(entry.get("locked", False))
            custom_image = entry.get("custom_image") or None
            return design, color, locked, custom_image
        default_design = _DEFAULT_DESIGN_KEYS[int(mazo_id) % len(_DEFAULT_DESIGN_KEYS)]
        return default_design, "auto", False, None

    def _set_deck_style(self, mazo_id: int, design: str, color: str, locked: bool = None, custom_image="UNSET"):
        entry = self._deck_styles.setdefault(str(mazo_id), {})
        entry["design"] = resolve_design_key(design)
        entry["color"] = color or "auto"
        if locked is not None:
            entry["locked"] = bool(locked)
        if custom_image != "UNSET":
            entry["custom_image"] = custom_image or None
        _save_deck_box_styles(self._deck_styles)

    def _is_deck_locked(self, mazo_id: int) -> bool:
        entry = self._deck_styles.get(str(mazo_id))
        return bool(entry.get("locked", False)) if isinstance(entry, dict) else False

    def _toggle_bloquear_mazo(self, mazo_id: int):
        entry = self._deck_styles.setdefault(str(mazo_id), {})
        new_state = not bool(entry.get("locked", False))
        entry["locked"] = new_state
        _save_deck_box_styles(self._deck_styles)
        self.cargar_mazos()
        msg = t("Mazo bloqueado (protegido contra edición y eliminación)") if new_state else t("Mazo desbloqueado")
        show_toast(msg, "info", 2400)

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

        # Barra superior de Mi Colección: Título + Buscador + Botones Colección / Ordenar + Selector de Vista
        col_top_row = QHBoxLayout()
        col_top_row.setSpacing(8)

        lbl_col_title = QLabel(t("Mi Colección"))
        lbl_col_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;")
        col_top_row.addWidget(lbl_col_title)

        self.lbl_col_count = QLabel("")
        self.lbl_col_count.setStyleSheet("font-size: 11px; font-weight: 600; color: #8c5a69; border: none; background: transparent;")
        col_top_row.addWidget(self.lbl_col_count)

        self.col_search = QLineEdit()
        self.col_search.setPlaceholderText(t("Buscar carta por nombre..."))
        self.col_search.setFixedHeight(28)
        self.col_search.setStyleSheet("""
            QLineEdit {
                background: #ffffff; color: #3f2730; border: 1.5px solid #f29ca4;
                border-radius: 8px; padding: 2px 10px; font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #f56b7b;
            }
        """)
        self.col_search_timer = QTimer(self)
        self.col_search_timer.setSingleShot(True)
        self.col_search_timer.timeout.connect(self._reset_col_page_and_load)
        self.col_search.textChanged.connect(lambda _: self.col_search_timer.start(220))
        col_top_row.addWidget(self.col_search, 1)

        # Botones "Colección" y "Ordenar" desplegables con letra oscura de alto contraste (Issue #46)
        deck_filter_btn_style = """
            QPushButton {
                background-color: #ffd6e0;
                color: #3b1723;
                border-radius: 8px;
                padding: 4px 10px;
                font-weight: 700;
                font-size: 12px;
                border: 1.5px solid #e08fa0;
                min-height: 28px;
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

        self.btn_col_coleccion = QPushButton(t("Colección"))
        self.btn_col_coleccion.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_col_coleccion.setStyleSheet(deck_filter_btn_style)
        self._apply_dark_text_button_palette(self.btn_col_coleccion)
        self.btn_col_coleccion.clicked.connect(self._mostrar_menu_col_coleccion)
        col_top_row.addWidget(self.btn_col_coleccion)

        self.btn_col_ordenar = QPushButton(t("Ordenar"))
        self.btn_col_ordenar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_col_ordenar.setStyleSheet(deck_filter_btn_style)
        self._apply_dark_text_button_palette(self.btn_col_ordenar)
        self.btn_col_ordenar.clicked.connect(self._mostrar_menu_col_ordenar)
        col_top_row.addWidget(self.btn_col_ordenar)

        # Selector de Vista (Compacto, Normal, Grande) (Issue #45)
        lbl_vista = QLabel(t("Vista"))
        lbl_vista.setStyleSheet("font-size: 11px; font-weight: 700; color: #5a2a3a; margin-left: 6px; border: none; background: transparent;")
        col_top_row.addWidget(lbl_vista)

        self._zoom_buttons = {}
        for key, label in [("Pequeño", "Compacto"), ("Normal", "Normal"), ("Grande", "Grande")]:
            zbtn = QPushButton(t(label))
            zbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            zbtn.setFixedHeight(26)
            zbtn.clicked.connect(lambda ch=False, k=key: self._set_deck_zoom(k))
            self._zoom_buttons[key] = zbtn
            col_top_row.addWidget(zbtn)
        self._update_zoom_buttons_style()

        col_vbox.addLayout(col_top_row)

        # Cuadrícula desplazable de cartas de Mi Colección (Issue #45)
        self.col_scroll = QScrollArea(col_panel)
        self.col_scroll.setWidgetResizable(True)
        self.col_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.col_grid_container = QWidget()
        self.col_grid_container.setStyleSheet("background: transparent;")
        self.col_grid = QGridLayout(self.col_grid_container)
        self.col_grid.setContentsMargins(6, 6, 6, 6)
        self.col_grid.setSpacing(10)
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

    # ── Helpers de Filtros y Orden de Mi Colección (Issues #45 y #46) ──────────
    def _apply_dark_text_button_palette(self, btn: QPushButton):
        pal = btn.palette()
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#3b1723"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#3b1723"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#3b1723"))
        btn.setPalette(pal)

    def _create_styled_popup_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setMinimumWidth(165)
        menu.setMaximumWidth(220)
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

    def _mostrar_menu_col_coleccion(self):
        """Despliega menú desplegable para filtrar por colecciones/carpetas creadas (Issue #46)."""
        cats = obtener_categorias_usuario(self.usuario)
        if self.col_coleccion_activa and self.col_coleccion_activa not in cats:
            self.col_coleccion_activa = None

        menu = self._create_styled_popup_menu()

        act_todas = QAction(t("Todas"), menu)
        act_todas.setCheckable(True)
        act_todas.setChecked(self.col_coleccion_activa is None)
        act_todas.triggered.connect(lambda: self._seleccionar_col_coleccion(None))
        menu.addAction(act_todas)

        if cats:
            menu.addSeparator()
            for cat in cats:
                act_cat = QAction(cat, menu)
                act_cat.setCheckable(True)
                act_cat.setChecked(self.col_coleccion_activa == cat)
                act_cat.triggered.connect(lambda checked=False, c=cat: self._seleccionar_col_coleccion(c))
                menu.addAction(act_cat)

        menu.exec(self.btn_col_coleccion.mapToGlobal(QPoint(0, self.btn_col_coleccion.height() + 2)))

    def _seleccionar_col_coleccion(self, coleccion):
        self.col_coleccion_activa = coleccion
        if coleccion:
            self.btn_col_coleccion.setText(f"{t('Colección')}: {coleccion}")
            self.btn_col_coleccion.setToolTip(f"{t('Colección')}: {coleccion}")
        else:
            self.btn_col_coleccion.setText(t("Colección"))
            self.btn_col_coleccion.setToolTip(t("Colección"))
        self._reset_col_page_and_load()

    def _mostrar_menu_col_ordenar(self):
        """Despliega menú desplegable para ordenar cartas por Rareza, Energía e Idioma (Issue #46)."""
        menu = self._create_styled_popup_menu()

        opciones = [
            (t("Rareza"), "rarity"),
            (t("Energía"), "type"),
            (t("Idioma"), "idioma"),
        ]
        for label, key in opciones:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.col_orden_activo == key)
            act.triggered.connect(lambda checked=False, k=key: self._seleccionar_col_orden(k))
            menu.addAction(act)

        if self.col_orden_activo is not None:
            menu.addSeparator()
            act_reset = QAction(t("Por defecto"), menu)
            act_reset.triggered.connect(lambda: self._seleccionar_col_orden(None))
            menu.addAction(act_reset)

        menu.exec(self.btn_col_ordenar.mapToGlobal(QPoint(0, self.btn_col_ordenar.height() + 2)))

    def _seleccionar_col_orden(self, clave_orden):
        if self.col_orden_activo == clave_orden and clave_orden is not None:
            self.col_orden_activo = None
        else:
            self.col_orden_activo = clave_orden
        self._reset_col_page_and_load()

    def _get_deck_card_size_and_cols(self) -> tuple[tuple[int, int], int]:
        """Calcula el tamaño de carta y número de columnas según la vista activa (Issue #45)."""
        tam = load_settings().get("tamano_cartas", "Normal")
        if tam == "Pequeño":
            return (90, 127), 7
        elif tam == "Grande":
            return (150, 212), 4
        else:
            return (120, 170), 5

    def _set_deck_zoom(self, size_key: str):
        """Cambia el tamaño de vista (Compacto / Normal / Grande) y guarda en ajustes."""
        from MyQtApp.config import save_settings
        settings = load_settings()
        if settings.get("tamano_cartas") == size_key:
            return
        settings["tamano_cartas"] = size_key
        save_settings(settings)
        self._update_zoom_buttons_style()
        self.cargar_coleccion_navegador()

    def _update_zoom_buttons_style(self):
        active_zoom = load_settings().get("tamano_cartas", "Normal")
        for key, btn in self._zoom_buttons.items():
            is_active = (key == active_zoom)
            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f56b7b;
                        color: #ffffff;
                        font-size: 11px;
                        font-weight: 700;
                        border: 1.5px solid #d44854;
                        border-radius: 8px;
                        padding: 2px 10px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #5a2a3a;
                        font-size: 11px;
                        font-weight: 600;
                        border: 1.5px solid #f2b8c3;
                        border-radius: 8px;
                        padding: 2px 10px;
                    }
                    QPushButton:hover {
                        background-color: #ffdfe6;
                        border-color: #f56b7b;
                    }
                """)

    def _cargar_opciones_filtros_coleccion(self):
        """Mantenido por compatibilidad con llamadas existentes."""
        pass

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

    def _compute_col_grid_cols(self, card_w: int, default_cols: int) -> int:
        """Calcula cuántas columnas caben realmente en el viewport del navegador de colección (Issue #51)."""
        viewport_w = self.col_scroll.viewport().width() if hasattr(self, "col_scroll") else 0
        stack_avail = (self.main_stack.width() - 68) if hasattr(self, "main_stack") else 0
        effective_w = viewport_w if viewport_w > 200 else max(viewport_w, stack_avail)
        if effective_w <= 200:
            return default_cols
        spacing = self.col_grid.horizontalSpacing()
        if spacing < 0:
            spacing = 10
        m_left, _, m_right, _ = self.col_grid.getContentsMargins()
        inner_w = max(100, effective_w - m_left - m_right - 4)
        tile_w = (card_w + 8) + spacing
        return max(3, (inner_w + spacing) // tile_w)

    def _check_col_grid_reflow(self):
        """Reacomoda las tarjetas ya creadas si el ancho disponible cambió (Issue #51)."""
        if not self._col_ordered_widgets:
            return
        if self.main_stack.currentWidget() is not self.deck_editor_widget:
            return
        card_size, default_cols = self._get_deck_card_size_and_cols()
        cols = self._compute_col_grid_cols(card_size[0], default_cols)
        if cols == self._last_col_grid_cols:
            return
        self._last_col_grid_cols = cols

        while self.col_grid.count():
            self.col_grid.takeAt(0)

        row, col = 0, 0
        alive = []
        for cw in self._col_ordered_widgets:
            try:
                _ = cw.isVisible()
            except RuntimeError:
                continue
            self.col_grid.addWidget(cw, row, col)
            alive.append(cw)
            col += 1
            if col >= cols:
                col = 0
                row += 1
        self._col_ordered_widgets = alive

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "main_stack") and self.main_stack.currentWidget() is self.deck_editor_widget:
            self._col_resize_timer.start(60)

    def cargar_coleccion_navegador(self):
        """Carga las cartas de la colección del usuario con ajuste de vista y ordenamiento (Issues #45, #46 y #51)."""
        self.col_widgets_by_key.clear()
        self._col_ordered_widgets.clear()
        while self.col_grid.count():
            item = self.col_grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._update_zoom_buttons_style()

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

        if self.col_coleccion_activa:
            q = q.filter(UsuarioCarta.categoria == self.col_coleccion_activa)

        # Aplicar orden activo (Rareza, Energía, Idioma) o por defecto (Nombre)
        if self.col_orden_activo == "rarity":
            q = q.order_by(Cartas.rarity.asc(), Cartas.nombre.asc())
        elif self.col_orden_activo == "type":
            q = q.order_by(Cartas.type.asc(), Cartas.nombre.asc())
        elif self.col_orden_activo == "idioma":
            q = q.order_by(Cartas.idioma.asc(), Cartas.nombre.asc())
        else:
            q = q.order_by(Cartas.nombre.asc())

        self.col_total = q.count()
        self.lbl_col_count.setText(f"({self.col_total} cartas)")

        card_size, default_cols = self._get_deck_card_size_and_cols()
        cw, ch = card_size

        cartas = (
            q.limit(self.COL_PER_PAGE)
            .offset(self.col_page * self.COL_PER_PAGE)
            .all()
        )

        cols = self._compute_col_grid_cols(cw, default_cols)
        self._last_col_grid_cols = cols

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

            pix = get_webp_pixmap(carta.id_api, carta.nombre, c_lang, size=card_size)
            needs_dl = False
            if not pix:
                pix = get_pixmap_from_zip(carta.nombre.lower().replace(" ", "_"), size=card_size, id_api=carta.id_api)
            if not pix or pix.isNull():
                pix = get_card_placeholder_pixmap(card_size, carta.nombre)
                needs_dl = True

            in_deck_qty = self.deck_tiles[card_key].get_quantity() if card_key in self.deck_tiles else 0
            card_widget = DraggableCollectionCardWidget(
                card_data, pix, in_deck_qty=in_deck_qty, card_size=card_size, parent=self.col_grid_container
            )
            card_widget.quick_add_requested.connect(self._on_card_dropped_in_deck)
            self.col_grid.addWidget(card_widget, row, col)
            self._col_ordered_widgets.append(card_widget)
            self.col_widgets_by_key.setdefault(card_key, []).append(card_widget)

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
        design, color, locked, custom_image = self._get_deck_style(mazo.id)

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
            locked=locked,
            custom_image=custom_image,
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

        btn_more = QPushButton("...")
        btn_more.setFixedSize(30, 24)
        btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_more.setToolTip(t("Opciones del mazo"))
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
            lambda ch=False, mid=mazo.id, mname=mazo.nombre, anchor=btn_more: self._abrir_menu_mazo(mid, mname, anchor)
        )
        bottom_row.addWidget(btn_more)

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
                design, color, _locked, custom_image = self._get_deck_style(closing_id)
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
                    custom_image=custom_image,
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
        design, color, locked, custom_image = self._get_deck_style(mazo.id)
        total_qty = sum(mc.cantidad for mc in mazo.cartas)
        self.editor_mini_box.set_deck_props(
            name=mazo.nombre,
            design=design,
            color=color,
            card_count=total_qty,
            locked=locked,
            custom_image=custom_image,
        )
        self.btn_customize_deck.setEnabled(not locked)
        self.cargar_cartas_de_mazo(mazo)
        self._cargar_opciones_filtros_coleccion()
        self.col_page = 0

        # Mostrar y activar geometría del editor ANTES de poblar la cuadrícula para evitar espacios vacíos (Issue #51)
        self.main_stack.setCurrentWidget(self.deck_editor_widget)
        if self.deck_editor_widget.layout():
            self.deck_editor_widget.layout().activate()
        QApplication.processEvents()

        self.cargar_coleccion_navegador()
        if self.deck_editor_widget.layout():
            self.deck_editor_widget.layout().activate()
        QApplication.processEvents()
        QTimer.singleShot(0, self._check_col_grid_reflow)

        if animaciones_activas:
            try:
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
                    custom_image=custom_image,
                )
                self._active_overlay = ov
                ov.animation_finished.connect(lambda: setattr(self, "_active_overlay", None))
            except Exception as e:
                print(f"Error en animación de apertura de portamazos: {e}")

    def crear_nuevo_mazo(self):
        dlg = DeckBoxCustomizeDialog(title="Crear Nuevo Portamazos", editing=False, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            nombre, design, color, custom_image = dlg.get_values()
            nuevo = Mazo(usuario_nombre=self.usuario, nombre=nombre)
            self.session.add(nuevo)
            self.session.commit()
            self._set_deck_style(nuevo.id, design, color, locked=False, custom_image=custom_image)
            self.cargar_mazos()
            show_toast(f"Portamazos '{nombre}' creado con éxito.", "success", 2500)

    def personalizar_mazo_por_id(self, mazo_id: int):
        if self._is_deck_locked(mazo_id):
            show_toast(t("Este mazo está bloqueado y protegido."), "warning", 2400)
            return
        mazo = self.session.query(Mazo).filter(Mazo.id == mazo_id).first()
        if not mazo:
            return
        design, color, locked, custom_image = self._get_deck_style(mazo.id)
        total_qty = sum(mc.cantidad for mc in mazo.cartas)
        dlg = DeckBoxCustomizeDialog(
            title="Personalizar Portamazos",
            name=mazo.nombre,
            design=design,
            color=color,
            card_count=total_qty,
            custom_image=custom_image,
            editing=True,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name, new_design, new_color, new_custom_image = dlg.get_values()
            mazo.nombre = new_name
            self.session.commit()
            self._set_deck_style(mazo.id, new_design, new_color, locked=locked, custom_image=new_custom_image)
            if self.mazo_actual and self.mazo_actual.id == mazo.id:
                self.lbl_mazo_nombre.setText(new_name)
                self.editor_mini_box.set_deck_props(
                    name=new_name,
                    design=new_design,
                    color=new_color,
                    card_count=total_qty,
                    locked=locked,
                    custom_image=new_custom_image,
                )
            self.cargar_mazos()
            show_toast("Portamazos actualizado.", "success", 2200)

    def personalizar_mazo_actual(self):
        if self.mazo_actual:
            self.personalizar_mazo_por_id(self.mazo_actual.id)

    def _abrir_menu_mazo(self, mazo_id: int, mazo_nombre: str, anchor_btn: QPushButton):
        """Despliega el menú contextual '...' con las opciones del mazo (Issue #48)."""
        is_locked = self._is_deck_locked(mazo_id)

        menu = QMenu(self)
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

        # 1. Bloquear / Desbloquear
        act_lock = QAction(t("Desbloquear") if is_locked else t("Bloquear"), menu)
        act_lock.triggered.connect(lambda: self._toggle_bloquear_mazo(mazo_id))
        menu.addAction(act_lock)

        # 2. Editar
        act_edit = QAction(t("Editar"), menu)
        act_edit.setEnabled(not is_locked)
        act_edit.triggered.connect(lambda: self.personalizar_mazo_por_id(mazo_id))
        menu.addAction(act_edit)

        # 3. Duplicar
        act_dup = QAction(t("Duplicar"), menu)
        act_dup.triggered.connect(lambda: self._duplicar_mazo(mazo_id))
        menu.addAction(act_dup)

        menu.addSeparator()

        # 4. Imprimir
        act_print = QAction(t("Imprimir"), menu)
        act_print.triggered.connect(lambda: self.open_deck_in_print_requested.emit(mazo_id, "print"))
        menu.addAction(act_print)

        menu.addSeparator()

        # 5. Eliminar
        act_del = QAction(t("Eliminar"), menu)
        act_del.setEnabled(not is_locked)
        act_del.triggered.connect(lambda: self.eliminar_mazo_por_id(mazo_id))
        menu.addAction(act_del)

        menu.exec(anchor_btn.mapToGlobal(QPoint(0, anchor_btn.height() + 2)))

    def _duplicar_mazo(self, mazo_id: int):
        """Crea una copia idéntica del mazo y sus cartas asignadas."""
        self.session.expire_all()
        mazo_orig = self.session.query(Mazo).filter(Mazo.id == mazo_id).first()
        if not mazo_orig:
            show_toast("No se encontró el mazo original.", "warning")
            return

        try:
            nuevo_nombre = f"{mazo_orig.nombre} (Copia)"
            nuevo_mazo = Mazo(nombre=nuevo_nombre, usuario_nombre=self.usuario)
            self.session.add(nuevo_mazo)
            self.session.flush()

            # Duplicar cartas del mazo
            for mc in mazo_orig.cartas:
                nueva_carta = MazoCarta(
                    mazo_id=nuevo_mazo.id,
                    id_api=mc.id_api,
                    nombre_carta=mc.nombre_carta,
                    cantidad=mc.cantidad,
                    idioma=mc.idioma,
                    edition=mc.edition or ""
                )
                self.session.add(nueva_carta)

            self.session.commit()

            # Copiar estilo visual del mazo
            design, color, _locked, custom_image = self._get_deck_style(mazo_id)
            self._set_deck_style(nuevo_mazo.id, design, color, locked=False, custom_image=custom_image)

            self.cargar_mazos()
            show_toast(f"Mazo duplicado: '{nuevo_nombre}'", "success", 2500)
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"Error al duplicar el mazo: {e}")

    def eliminar_mazo_por_id(self, mazo_id: int):
        if self._is_deck_locked(mazo_id):
            show_toast(t("Este mazo está bloqueado y protegido."), "warning", 2400)
            return
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
