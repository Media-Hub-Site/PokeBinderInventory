import json
import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QSpinBox,
    QMessageBox, QDialog, QStackedWidget, QGridLayout, QComboBox,
    QColorDialog, QApplication
)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QPoint, QRectF, pyqtSignal

from MyQtApp.config import USER_DATA_DIR, load_settings
from MyQtApp.session import SessionLocal
from MyQtApp.models import Mazo, MazoCarta, Cartas
from MyQtApp.app.getImgs import get_webp_pixmap, get_pixmap_from_zip
from MyQtApp.i18n import t
from MyQtApp.ui.toast import show_toast
from MyQtApp.ui.PrintView import ImportDecklistDialog
from MyQtApp.ui.BinderCoverWidget import BINDER_DESIGNS, resolve_design_key
from MyQtApp.ui.DeckBoxWidget import DeckBoxWidget, DeckBoxOpenAnimationOverlay


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


class DeckCardRowWidget(QFrame):
    """Fila limpia (sin emojis) para una carta dentro del editor de mazo."""
    quantity_changed = pyqtSignal()
    removed = pyqtSignal(str)  # card_key

    def __init__(self, card_data, quantity=1, parent=None):
        super().__init__(parent)
        self.card_data = card_data
        self.card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"

        self.setStyleSheet("""
            DeckCardRowWidget {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 8px;
                padding: 4px;
            }
            DeckCardRowWidget:hover { border-color: #38bdf8; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.lbl_img = QLabel(self)
        self.lbl_img.setFixedSize(40, 56)
        self.lbl_img.setScaledContents(True)

        lang = card_data.get("idioma", "es")
        id_api = card_data.get("id_api")
        nombre = card_data.get("nombre")

        pix = get_webp_pixmap(id_api, nombre, lang, size=(40, 56))
        if not pix:
            pix = get_pixmap_from_zip(nombre, size=(40, 56), id_api=id_api)
        if pix:
            self.lbl_img.setPixmap(pix)
        else:
            self.lbl_img.setText("TCG")
            self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_img.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: bold; font-size: 10px; border-radius: 4px;")

        layout.addWidget(self.lbl_img)

        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(2)
        lbl_n = QLabel(nombre or "Carta", self)
        lbl_n.setStyleSheet("font-weight: bold; font-size: 12px; color: #f8fafc; border: none;")
        lbl_s = QLabel(f"ID: {id_api} | {card_data.get('edition', '')}", self)
        lbl_s.setStyleSheet("font-size: 10px; color: #94a3b8; border: none;")
        info_vbox.addWidget(lbl_n)
        info_vbox.addWidget(lbl_s)
        layout.addLayout(info_vbox, stretch=1)

        self.spin_qty = QSpinBox(self)
        self.spin_qty.setRange(1, 99)
        self.spin_qty.setValue(quantity)
        self.spin_qty.setFixedSize(48, 26)
        self.spin_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_qty.setStyleSheet("""
            QSpinBox {
                background-color: #0f172a; color: #38bdf8; font-weight: bold;
                border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 4px;
            }
        """)
        self.spin_qty.valueChanged.connect(lambda _: self.quantity_changed.emit())
        layout.addWidget(self.spin_qty)

        btn_del = QPushButton("X", self)
        btn_del.setFixedSize(26, 26)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip(t("Quitar carta"))
        btn_del.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: bold;
                border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 4px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.45); color: white; }
        """)
        btn_del.clicked.connect(lambda: self.removed.emit(self.card_key))
        layout.addWidget(btn_del)

    def get_quantity(self):
        return self.spin_qty.value()


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

        # Izquierda: Vista previa 3D viva del Portamazos
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

        # Derecha: Controles de personalización
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
    Sección de Mazos remodelada con Portamazos físicos 3D personalizables (Issue #19, sin emojis):
      - Vista Home: Estantería de Portamazos 3D con diseños y colores propios + hover Bookshelf Peek
      - Apertura y cierre 3D: La tapa magnética del portamazos se abre/cierra revelando las cartas
      - Vista Editor: Edición completa de cartas, búsqueda en colección, importación y guardado
    """

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()

        self.mazo_actual = None
        self.card_rows = {}  # card_key -> DeckCardRowWidget
        self._deck_styles = _load_deck_box_styles()
        self._deck_box_widgets = {}  # mazo_id -> DeckBoxWidget
        self._active_overlay = None

        self.init_ui()
        self.mostrar_estanteria_mazos(animate_close=False)

    def _get_deck_style(self, mazo_id: int) -> tuple[str, str]:
        entry = self._deck_styles.get(str(mazo_id))
        if isinstance(entry, dict):
            return resolve_design_key(entry.get("design", "Charizard Fuego")), entry.get("color", "auto")
        # Asignar diseño variado por defecto a mazos antiguos sin estilo guardado
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

        # Pantalla 1: Estantería de Portamazos 3D
        self.decks_home_widget = QWidget()
        self._setup_home_view()
        self.main_stack.addWidget(self.decks_home_widget)

        # Pantalla 2: Editor interno del Mazo
        self.deck_editor_widget = QWidget()
        self._setup_editor_view()
        self.main_stack.addWidget(self.deck_editor_widget)

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

    def _setup_editor_view(self):
        layout = QVBoxLayout(self.deck_editor_widget)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        # Barra superior del editor
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self.btn_back_decks = QPushButton(t("Volver a Mazos"))
        self.btn_back_decks.setFixedHeight(32)
        self.btn_back_decks.setProperty("class", "pill")
        self.btn_back_decks.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_decks.clicked.connect(lambda: self.mostrar_estanteria_mazos(animate_close=True))
        header_row.addWidget(self.btn_back_decks)

        self.editor_mini_box = DeckBoxWidget(name="Mazo", design="Charizard Fuego", color="auto", card_count=0)
        self.editor_mini_box.setFixedSize(44, 54)
        self.editor_mini_box.setMinimumSize(44, 54)
        header_row.addWidget(self.editor_mini_box)

        self.lbl_mazo_nombre = QLabel(t("Selecciona un mazo"))
        self.lbl_mazo_nombre.setStyleSheet("font-size: 18px; font-weight: 700; color: #5a2a3a;")
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

        layout.addLayout(header_row)

        # Fila de búsqueda en colección + importar desde texto
        row_search = QHBoxLayout()
        row_search.setSpacing(8)

        self.input_card_search = QLineEdit(self)
        self.input_card_search.setPlaceholderText(t("Buscar carta en mi colección..."))
        self.input_card_search.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff; color: #3f2730;
                border: 1.5px solid #f29ca4; border-radius: 8px; padding: 8px 10px;
            }
            QLineEdit:focus { border-color: #f56b7b; }
        """)
        self.input_card_search.textChanged.connect(self.on_card_search_text_changed)
        row_search.addWidget(self.input_card_search, stretch=1)

        btn_import = QPushButton(t("Importar desde Texto"), self)
        btn_import.setFixedHeight(34)
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold; border-radius: 8px; padding: 6px 14px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        btn_import.clicked.connect(self.importar_mazo_texto)
        row_search.addWidget(btn_import)

        layout.addLayout(row_search)

        # Sugerencias de cartas
        self.list_card_suggestions = QListWidget(self)
        self.list_card_suggestions.setMaximumHeight(130)
        self.list_card_suggestions.hide()
        self.list_card_suggestions.setStyleSheet("""
            QListWidget {
                background-color: #0f172a; color: #f8fafc; border: 1.5px solid #38bdf8; border-radius: 8px;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:hover { background-color: #1e293b; color: #38bdf8; }
            QListWidget::item:selected { background-color: #0284c7; color: white; }
        """)
        self.list_card_suggestions.itemClicked.connect(self.on_suggestion_clicked)
        layout.addWidget(self.list_card_suggestions)

        # Lista de cartas del mazo
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(15, 23, 42, 0.72);
                border: 1.5px solid #f2c4ce;
                border-radius: 12px;
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_vbox = QVBoxLayout(self.cards_container)
        self.cards_vbox.setContentsMargins(10, 10, 10, 10)
        self.cards_vbox.setSpacing(6)
        self.cards_vbox.addStretch()

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

        # Barra inferior de guardado
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.btn_guardar = QPushButton(t("Guardar Mazo"), self)
        self.btn_guardar.setFixedSize(220, 40)
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setStyleSheet("""
            QPushButton {
                background-color: #10b981; color: white; font-weight: bold; font-size: 14px; border-radius: 10px;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.btn_guardar.clicked.connect(self.guardar_mazo_actual)
        bottom_row.addWidget(self.btn_guardar)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

    def cargar_mazos(self):
        """Renderiza la estantería de Portamazos 3D físicos del usuario."""
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

        status_txt = f"{total_qty} / 60"
        lbl_cnt = QLabel(status_txt)
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
                total_qty = sum(w.get_quantity() for w in self.card_rows.values())

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

    def limpiar_editor(self):
        for widget in list(self.card_rows.values()):
            self.cards_vbox.removeWidget(widget)
            widget.deleteLater()
        self.card_rows.clear()
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
            self.agregar_carta_row(data, quantity=mc.cantidad)
        self.actualizar_conteo()

    def agregar_carta_row(self, card_data, quantity=1):
        card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"
        if card_key in self.card_rows:
            widget = self.card_rows[card_key]
            widget.spin_qty.setValue(widget.spin_qty.value() + quantity)
        else:
            widget = DeckCardRowWidget(card_data, quantity=quantity, parent=self)
            widget.quantity_changed.connect(self.actualizar_conteo)
            widget.removed.connect(self.remover_carta_row)
            count = self.cards_vbox.count()
            self.cards_vbox.insertWidget(max(0, count - 1), widget)
            self.card_rows[card_key] = widget
        self.actualizar_conteo()

    def remover_carta_row(self, card_key):
        if card_key in self.card_rows:
            widget = self.card_rows.pop(card_key)
            self.cards_vbox.removeWidget(widget)
            widget.deleteLater()
            self.actualizar_conteo()

    def actualizar_conteo(self):
        total = sum(w.get_quantity() for w in self.card_rows.values())
        self.lbl_card_count.setText(f"{total} / 60 cartas")
        self.editor_mini_box.set_deck_props(card_count=total)
        if total == 60:
            self.lbl_card_count.setStyleSheet("font-size: 13px; font-weight: 700; color: #15803d;")
        else:
            self.lbl_card_count.setStyleSheet("font-size: 13px; font-weight: 700; color: #b45309;")

    def on_card_search_text_changed(self, text):
        text = text.strip()
        if len(text) < 2:
            self.list_card_suggestions.hide()
            return

        from MyQtApp.models import UsuarioCarta

        resultados = (
            self.session.query(Cartas)
            .join(UsuarioCarta, (Cartas.id_api == UsuarioCarta.carta_id) & (Cartas.idioma == UsuarioCarta.idioma))
            .filter(UsuarioCarta.usuario_nombre == self.usuario)
            .filter(Cartas.nombre.ilike(f"%{text}%"))
            .limit(10)
            .all()
        )
        if not resultados:
            resultados = (
                self.session.query(Cartas)
                .join(UsuarioCarta, Cartas.id_api == UsuarioCarta.carta_id)
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
                .filter(Cartas.nombre.ilike(f"%{text}%"))
                .limit(10)
                .all()
            )

        self.list_card_suggestions.clear()
        if not resultados:
            item = QListWidgetItem(t("No tienes esta carta en tu colección"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_card_suggestions.addItem(item)
            self.list_card_suggestions.show()
            return

        for c in resultados:
            item_text = f"{c.nombre} ({c.edition or c.id_api}) [{c.idioma or 'es'}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, {
                "id_api": c.id_api,
                "nombre": c.nombre,
                "idioma": c.idioma or "es",
                "edition": c.edition or ""
            })
            self.list_card_suggestions.addItem(item)
        self.list_card_suggestions.show()

    def on_suggestion_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and self.mazo_actual:
            self.agregar_carta_row(data, quantity=1)
        self.input_card_search.clear()
        self.list_card_suggestions.hide()

    def importar_mazo_texto(self):
        if not self.mazo_actual:
            QMessageBox.warning(self, t("Error"), "Debes seleccionar o crear un mazo primero.")
            return

        dialog = ImportDecklistDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            texto = dialog.get_text()
            if not texto:
                return

            from MyQtApp.models import UsuarioCarta
            agregadas = 0
            for linea in texto.splitlines():
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                match = re.match(r"^(\d+)\s+(.+)$", linea)
                if match:
                    qty = int(match.group(1))
                    card_search = match.group(2).strip()
                else:
                    qty = 1
                    card_search = linea

                carta = (
                    self.session.query(Cartas)
                    .join(UsuarioCarta, (Cartas.id_api == UsuarioCarta.carta_id) & (Cartas.idioma == UsuarioCarta.idioma))
                    .filter(UsuarioCarta.usuario_nombre == self.usuario)
                    .filter(Cartas.nombre.ilike(f"%{card_search}%"))
                    .first()
                )
                if not carta:
                    carta = self.session.query(Cartas).filter(Cartas.nombre.ilike(f"%{card_search}%")).first()
                if not carta:
                    first_word = card_search.split()[0]
                    carta = self.session.query(Cartas).filter(Cartas.nombre.ilike(f"%{first_word}%")).first()

                if carta:
                    self.agregar_carta_row({
                        "id_api": carta.id_api,
                        "nombre": carta.nombre,
                        "idioma": carta.idioma or "es",
                        "edition": carta.edition or ""
                    }, quantity=qty)
                    agregadas += qty

            if agregadas > 0:
                show_toast(f"Se importaron {agregadas} cartas al mazo.", "success", 2500)
            else:
                QMessageBox.warning(self, t("Importar desde Texto"), "No se encontraron coincidencias para la lista.")

    def guardar_mazo_actual(self):
        if not self.mazo_actual:
            return
        try:
            self.session.query(MazoCarta).filter(MazoCarta.mazo_id == self.mazo_actual.id).delete()
            for widget in self.card_rows.values():
                d = widget.card_data
                mc = MazoCarta(
                    mazo_id=self.mazo_actual.id,
                    id_api=d.get("id_api"),
                    nombre_carta=d.get("nombre"),
                    cantidad=widget.get_quantity(),
                    idioma=d.get("idioma", "es"),
                    edition=d.get("edition", "")
                )
                self.session.add(mc)
            self.session.commit()
            show_toast("Mazo guardado correctamente.", "success", 2500)
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"Error guardando mazo: {e}")
