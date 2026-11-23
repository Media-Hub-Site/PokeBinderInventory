import json
import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QSpinBox, QCheckBox, QScrollArea, QGridLayout, QFrame,
    QFileDialog, QDialog, QTextEdit, QDialogButtonBox, QMessageBox
)
from PyQt6.QtGui import QPixmap, QPdfWriter, QPainter, QPageSize, QPageLayout, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QMarginsF, QRectF, pyqtSignal
from sqlalchemy import and_, func

from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas, Mazo, MazoCarta, UsuarioCarta
from MyQtApp.config import IMAGES_DIR, IMAGES_WEBP_DIR, BINDER_DATA_FILE
from MyQtApp.app.getImgs import get_webp_pixmap, get_pixmap_from_zip, get_hd_pixmap
from MyQtApp.app.db_services import obtener_categorias_usuario
from MyQtApp.i18n import t
from MyQtApp.ui.toast import show_toast


def _plain_label(text: str) -> str:
    """Elimina emojis/símbolos pictográficos que pudieran venir de traducciones heredadas."""
    cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+", "", str(text or ""))
    return " ".join(cleaned.split())


class ImportDecklistDialog(QDialog):
    """Diálogo para pegar e importar una lista de cartas en formato texto (ej. '4 Pikachu SVI 63' o '4 Miraidon')."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Importar desde Texto"))
        self.resize(480, 360)

        layout = QVBoxLayout(self)

        lbl = QLabel(t("Pega tu lista de cartas aquí (ejemplo: '4 Pikachu' o '4 Pikachu SVI 063'):"), self)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-weight: bold; color: #f8fafc;")
        layout.addWidget(lbl)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("4 Pikachu\n3 Miraidon ex\n2 Nest Ball\n...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0f172a;
                color: #e2e8f0;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 8px;
                font-family: monospace;
                padding: 8px;
            }
        """)
        layout.addWidget(self.text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_text(self):
        return self.text_edit.toPlainText().strip()


class PrintCardItemWidget(QFrame):
    """Widget que representa una carta en la cola de impresión con miniatura y controles de cantidad."""
    quantity_changed = pyqtSignal()
    removed = pyqtSignal(str)  # card_key

    def __init__(self, card_data, quantity=1, parent=None):
        super().__init__(parent)
        self.card_data = card_data  # dict with id_api, nombre, idioma, edition
        self.card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            PrintCardItemWidget {
                background-color: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 10px;
                padding: 6px;
            }
            PrintCardItemWidget:hover {
                border-color: #38bdf8;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Miniatura de carta
        self.lbl_img = QLabel(self)
        self.lbl_img.setFixedSize(54, 75)
        self.lbl_img.setScaledContents(True)

        lang = card_data.get("idioma", "es")
        id_api = card_data.get("id_api")
        nombre = card_data.get("nombre")

        pix = get_webp_pixmap(id_api, nombre, lang, size=(54, 75))
        if not pix:
            pix = get_pixmap_from_zip(nombre, size=(54, 75), id_api=id_api)
        if pix:
            self.lbl_img.setPixmap(pix)
        else:
            self.lbl_img.setText("TCG")
            self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_img.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: bold; font-size: 11px; border-radius: 4px;")

        layout.addWidget(self.lbl_img)

        # Info de carta
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(2)

        lbl_nombre = QLabel(nombre or "Carta sin nombre", self)
        lbl_nombre.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc;")

        set_info = card_data.get("edition") or card_data.get("set_id") or ""
        lbl_sub = QLabel(f"ID: {id_api} | {set_info}", self)
        lbl_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")

        info_vbox.addWidget(lbl_nombre)
        info_vbox.addWidget(lbl_sub)
        info_vbox.addStretch()

        layout.addLayout(info_vbox, stretch=1)

        # Controles de cantidad
        qty_layout = QHBoxLayout()
        qty_layout.setSpacing(4)

        btn_minus = QPushButton("-", self)
        btn_minus.setFixedSize(28, 28)
        btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minus.setStyleSheet("""
            QPushButton {
                background: #334155; color: white; font-weight: bold; border-radius: 6px; font-size: 14px;
            }
            QPushButton:hover { background: #475569; }
        """)

        self.spin_qty = QSpinBox(self)
        self.spin_qty.setRange(1, 99)
        self.spin_qty.setValue(quantity)
        self.spin_qty.setFixedSize(50, 28)
        self.spin_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_qty.setStyleSheet("""
            QSpinBox {
                background-color: #0f172a; color: #38bdf8; font-weight: bold;
                border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px;
            }
        """)

        btn_plus = QPushButton("+", self)
        btn_plus.setFixedSize(28, 28)
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.setStyleSheet("""
            QPushButton {
                background: #334155; color: white; font-weight: bold; border-radius: 6px; font-size: 14px;
            }
            QPushButton:hover { background: #475569; }
        """)

        btn_del = QPushButton("X", self)
        btn_del.setFixedSize(28, 28)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip(t("Eliminar"))
        btn_del.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: bold;
                border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 6px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.4); color: white; }
        """)

        btn_minus.clicked.connect(self.decrement)
        btn_plus.clicked.connect(self.increment)
        btn_del.clicked.connect(lambda: self.removed.emit(self.card_key))
        self.spin_qty.valueChanged.connect(lambda _: self.quantity_changed.emit())

        qty_layout.addWidget(btn_minus)
        qty_layout.addWidget(self.spin_qty)
        qty_layout.addWidget(btn_plus)
        qty_layout.addWidget(btn_del)

        layout.addLayout(qty_layout)

    def decrement(self):
        val = self.spin_qty.value()
        if val > 1:
            self.spin_qty.setValue(val - 1)

    def increment(self):
        val = self.spin_qty.value()
        self.spin_qty.setValue(val + 1)

    def get_quantity(self):
        return self.spin_qty.value()


class PrintView(QWidget):
    """Sección de impresión de proxies en PDF desde Mazos, Colección, Carpetas de Colección o Binders."""
    def __init__(self, usuario="admin", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.session = SessionLocal()
        self.queue_items = {}  # dict mapping card_key -> PrintCardItemWidget

        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self.refrescar_items_origen()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ── Columna Izquierda: Selección de Origen, Configuración y Acciones ──
        left_panel = QWidget(self)
        left_panel.setFixedWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Título (sin emojis)
        lbl_title = QLabel(t("Imprimir Proxies"), self)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #38bdf8;")
        left_layout.addWidget(lbl_title)

        # 1. Selector de Origen (Mazos, Colección, Carpetas de Colección, Binders)
        source_box = QWidget(self)
        source_box.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 10px;
                padding: 10px;
            }
        """)
        source_vbox = QVBoxLayout(source_box)
        source_vbox.setSpacing(8)

        lbl_source = QLabel(t("Seleccionar para Imprimir"), self)
        lbl_source.setStyleSheet("font-weight: bold; font-size: 12px; color: #f8fafc; border: none; padding: 0;")
        source_vbox.addWidget(lbl_source)

        combo_style = """
            QComboBox {
                background-color: #0f172a;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 8px;
            }
            QComboBox:focus { border-color: #38bdf8; }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #ffffff;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                border: 1px solid #38bdf8;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                color: #ffffff;
                padding: 6px 8px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
        """

        self.combo_origen_tipo = QComboBox(self)
        self.combo_origen_tipo.addItem(_plain_label(t("Mazos")), "mazo")
        self.combo_origen_tipo.addItem(_plain_label(t("Colecciones")), "coleccion")
        self.combo_origen_tipo.addItem(_plain_label(t("Sub-colecciones")), "carpeta_coleccion")
        self.combo_origen_tipo.addItem(_plain_label(t("Binders")), "binder")
        self.combo_origen_tipo.setStyleSheet(combo_style)
        self._apply_dark_combo_palette(self.combo_origen_tipo)
        self.combo_origen_tipo.currentIndexChanged.connect(self.refrescar_items_origen)
        source_vbox.addWidget(self.combo_origen_tipo)

        self.combo_origen_item = QComboBox(self)
        self.combo_origen_item.setStyleSheet(combo_style)
        self._apply_dark_combo_palette(self.combo_origen_item)
        source_vbox.addWidget(self.combo_origen_item)

        # Alias retrocompatible por si alguna referencia externa consulta combo_mazos
        self.combo_mazos = self.combo_origen_item

        btn_load_source = QPushButton(_plain_label(t("Cargar a la Cola")), self)
        btn_load_source.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_load_source.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold; border-radius: 6px; padding: 10px; font-size: 13px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        btn_load_source.clicked.connect(self.cargar_origen_seleccionado_a_cola)
        source_vbox.addWidget(btn_load_source)

        btn_import_text = QPushButton(_plain_label(t("Importar desde Texto")), self)
        btn_import_text.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import_text.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: #ffffff; font-weight: bold; border-radius: 6px; padding: 8px;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_import_text.clicked.connect(self.abrir_dialogo_importar_mazo)
        source_vbox.addWidget(btn_import_text)

        left_layout.addWidget(source_box)

        # 2. Opciones de PDF y formato de impresión
        config_box = QWidget(self)
        config_box.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 10px;
                padding: 10px;
            }
        """)
        config_vbox = QVBoxLayout(config_box)
        config_vbox.setSpacing(8)

        lbl_cfg_title = QLabel(_plain_label(t("Ajustes de PDF")), self)
        lbl_cfg_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #38bdf8; border: none; padding: 0;")
        config_vbox.addWidget(lbl_cfg_title)

        combo_small_style = """
            QComboBox {
                background-color: #0f172a; color: #ffffff; border: 1px solid #334155; border-radius: 4px; padding: 4px 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a; color: #ffffff;
                selection-background-color: #0284c7; selection-color: #ffffff;
                border: 1px solid #38bdf8;
            }
            QComboBox QAbstractItemView::item { color: #ffffff; padding: 5px 8px; }
        """

        # Tamaño de papel
        row_paper = QHBoxLayout()
        lbl_paper = QLabel(_plain_label(t("Tamaño de papel")) + ":", self)
        lbl_paper.setStyleSheet("color: #ffffff; font-size: 11px; border: none; padding: 0;")
        self.combo_paper = QComboBox(self)
        self.combo_paper.addItems(["A4 (210 x 297 mm)", "Letter (215.9 x 279.4 mm)"])
        self.combo_paper.setStyleSheet(combo_small_style)
        self._apply_dark_combo_palette(self.combo_paper)
        row_paper.addWidget(lbl_paper)
        row_paper.addWidget(self.combo_paper)
        config_vbox.addLayout(row_paper)

        # Marcas de corte
        self.chk_crop_marks = QCheckBox(_plain_label(t("Marcas de corte")), self)
        self.chk_crop_marks.setChecked(True)
        self.chk_crop_marks.setStyleSheet("color: #ffffff; font-size: 11px; border: none; padding: 0;")
        config_vbox.addWidget(self.chk_crop_marks)

        # Espaciado
        self.chk_spacing = QCheckBox(_plain_label(t("Espacio entre cartas")) + " (1mm)", self)
        self.chk_spacing.setChecked(False)
        self.chk_spacing.setStyleSheet("color: #ffffff; font-size: 11px; border: none; padding: 0;")
        config_vbox.addWidget(self.chk_spacing)

        left_layout.addWidget(config_box)

        # Resumen de estadísticas
        self.lbl_stats = QLabel("Total: 0 cartas | 0 páginas PDF (3x3 grid)", self)
        self.lbl_stats.setStyleSheet("font-size: 12px; font-weight: bold; color: #f59e0b;")
        left_layout.addWidget(self.lbl_stats)

        # Botón de Generación de PDF
        self.btn_generate_pdf = QPushButton(_plain_label(t("Generar PDF")), self)
        self.btn_generate_pdf.setFixedSize(340, 46)
        self.btn_generate_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate_pdf.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_generate_pdf.clicked.connect(self.generar_pdf)
        left_layout.addWidget(self.btn_generate_pdf)

        self.btn_export_csv = QPushButton(_plain_label(t("Exportar CSV")), self)
        self.btn_export_csv.setFixedSize(340, 38)
        self.btn_export_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_csv.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_export_csv.clicked.connect(self.exportar_cola_csv)
        left_layout.addWidget(self.btn_export_csv)

        btn_clear = QPushButton(_plain_label(t("Limpiar Cola")), self)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: bold;
                border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 6px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.4); color: white; }
        """)
        btn_clear.clicked.connect(self.limpiar_cola)
        left_layout.addWidget(btn_clear)

        left_layout.addStretch()
        main_layout.addWidget(left_panel)

        # ── Columna Derecha: Cola de cartas agregadas ──
        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        lbl_queue_header = QLabel(_plain_label(t("Cola de Impresión")), self)
        lbl_queue_header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffffff; "
            "background-color: rgba(15, 23, 42, 0.85); border-radius: 8px; padding: 6px 12px;"
        )
        right_layout.addWidget(lbl_queue_header)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: rgba(15, 23, 42, 0.5);
                border: 1px solid rgba(56, 189, 248, 0.2);
                border-radius: 10px;
            }
        """)

        self.queue_container = QWidget()
        self.queue_vbox = QVBoxLayout(self.queue_container)
        self.queue_vbox.setContentsMargins(10, 10, 10, 10)
        self.queue_vbox.setSpacing(8)
        self.queue_vbox.addStretch()

        self.scroll_area.setWidget(self.queue_container)
        right_layout.addWidget(self.scroll_area)

        main_layout.addWidget(right_panel, stretch=1)

        self.refrescar_items_origen()
        self.actualizar_estadisticas()

    def _apply_dark_combo_palette(self, combo: QComboBox):
        """Fuerza texto blanco sobre fondo oscuro en el popup de QComboBox en Windows 11."""
        from PyQt6.QtGui import QPalette
        view = combo.view()
        if view is not None:
            pal = view.palette()
            pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
            pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#0284c7"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            view.setPalette(pal)

    def _load_user_binders(self) -> dict:
        if not os.path.exists(BINDER_DATA_FILE):
            return {}
        try:
            with open(BINDER_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            user_data = data.get(self.usuario, {})
            if isinstance(user_data, dict):
                return user_data.get("folders", {})
        except Exception as e:
            print(f"Error leyendo binders para PrintView: {e}")
        return {}

    def refrescar_mazos_combo(self):
        """Alias retrocompatible."""
        self.refrescar_items_origen()

    def refrescar_items_origen(self):
        """Actualiza el combo secundario según el tipo de origen elegido (Mazos, Colección, Carpetas o Binders)."""
        self.combo_origen_item.clear()
        self.session.expire_all()
        tipo = self.combo_origen_tipo.currentData()

        if tipo == "mazo":
            mazos = self.session.query(Mazo).filter(Mazo.usuario_nombre == self.usuario).all()
            if not mazos:
                self.combo_origen_item.addItem(t("Sin mazos creados"), None)
            else:
                for m in mazos:
                    total_qty = sum(mc.cantidad for mc in m.cartas)
                    self.combo_origen_item.addItem(f"{m.nombre} ({total_qty} cartas)", m.id)

        elif tipo == "coleccion":
            total_col = (
                self.session.query(UsuarioCarta)
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
                .count()
            )
            if total_col == 0:
                self.combo_origen_item.addItem(t("Colección vacía"), None)
            else:
                self.combo_origen_item.addItem(f"{t('Toda mi Colección')} ({total_col} cartas)", "__ALL__")

        elif tipo == "carpeta_coleccion":
            cats = obtener_categorias_usuario(self.usuario)
            if not cats:
                self.combo_origen_item.addItem(t("Sin carpetas de colección"), None)
            else:
                for cat in cats:
                    cnt = (
                        self.session.query(UsuarioCarta)
                        .filter(
                            UsuarioCarta.usuario_nombre == self.usuario,
                            UsuarioCarta.categoria == cat,
                        )
                        .count()
                    )
                    self.combo_origen_item.addItem(f"{cat} ({cnt} cartas)", cat)

        elif tipo == "binder":
            binders = self._load_user_binders()
            if not binders:
                self.combo_origen_item.addItem(t("Sin binders creados"), None)
            else:
                for f_id, f_data in binders.items():
                    name = f_data.get("name", f_id)
                    mode = f_data.get("mode", "3x3")
                    cards_dict = f_data.get("cards", {}).get(mode, {})
                    self.combo_origen_item.addItem(f"{name} ({len(cards_dict)} cartas)", f_id)

    def cargar_mazo_seleccionado_a_cola(self):
        """Alias retrocompatible."""
        self.cargar_origen_seleccionado_a_cola()

    def cargar_origen_seleccionado_a_cola(self):
        tipo = self.combo_origen_tipo.currentData()
        item_val = self.combo_origen_item.currentData()
        if item_val is None:
            show_toast("No hay ningún elemento seleccionado para cargar.", "warning", 2000)
            return

        agregadas = 0
        etiqueta = self.combo_origen_item.currentText()

        if tipo == "mazo":
            mazo = self.session.query(Mazo).filter(Mazo.id == item_val).first()
            if not mazo or not mazo.cartas:
                show_toast("El mazo seleccionado está vacío.", "warning", 2000)
                return
            for mc in mazo.cartas:
                self.agregar_carta_a_cola({
                    "id_api": mc.id_api,
                    "nombre": mc.nombre_carta,
                    "idioma": mc.idioma,
                    "edition": mc.edition or ""
                }, quantity=mc.cantidad)
                agregadas += mc.cantidad
            etiqueta = mazo.nombre

        elif tipo in ("coleccion", "carpeta_coleccion"):
            q = (
                self.session.query(Cartas, UsuarioCarta)
                .join(
                    UsuarioCarta,
                    and_(
                        Cartas.id_api == UsuarioCarta.carta_id,
                        func.coalesce(Cartas.idioma, "es") == func.coalesce(UsuarioCarta.idioma, "es"),
                    ),
                )
                .filter(UsuarioCarta.usuario_nombre == self.usuario)
            )
            if tipo == "carpeta_coleccion":
                q = q.filter(UsuarioCarta.categoria == item_val)

            rows = q.all()
            if not rows:
                show_toast("No se encontraron cartas en la selección.", "warning", 2000)
                return

            for carta, _uc in rows:
                self.agregar_carta_a_cola({
                    "id_api": carta.id_api,
                    "nombre": carta.nombre,
                    "idioma": carta.idioma or "es",
                    "edition": carta.edition or "",
                }, quantity=1)
                agregadas += 1

        elif tipo == "binder":
            binders = self._load_user_binders()
            f_data = binders.get(item_val)
            if not f_data:
                show_toast("No se encontró el binder seleccionado.", "warning", 2000)
                return
            mode = f_data.get("mode", "3x3")
            cards_dict = f_data.get("cards", {}).get(mode, {})
            if not cards_dict:
                show_toast("El binder seleccionado está vacío.", "warning", 2000)
                return

            for slot_val in cards_dict.values():
                cid = None
                lang = "en"
                if isinstance(slot_val, dict):
                    cid = slot_val.get("id_api")
                    lang = slot_val.get("idioma", "en")
                elif isinstance(slot_val, str) and slot_val:
                    if ":" in slot_val:
                        cid, lang = slot_val.split(":", 1)
                    else:
                        cid = slot_val
                if not cid:
                    continue

                carta = (
                    self.session.query(Cartas)
                    .filter(Cartas.id_api == cid, Cartas.idioma == lang)
                    .first()
                )
                if not carta:
                    carta = self.session.query(Cartas).filter(Cartas.id_api == cid).first()
                if carta:
                    self.agregar_carta_a_cola({
                        "id_api": carta.id_api,
                        "nombre": carta.nombre,
                        "idioma": carta.idioma or lang,
                        "edition": carta.edition or "",
                    }, quantity=1)
                    agregadas += 1
            etiqueta = f_data.get("name", etiqueta)

        if agregadas > 0:
            show_toast(f"'{etiqueta}' cargado a la cola ({agregadas} cartas).", "success", 2500)
        else:
            show_toast("No se encontraron cartas para cargar.", "warning", 2000)

    def agregar_carta_a_cola(self, card_data, quantity=1):
        card_key = f"{card_data.get('id_api')}:{card_data.get('idioma', 'es')}"

        if card_key in self.queue_items:
            widget = self.queue_items[card_key]
            widget.spin_qty.setValue(widget.spin_qty.value() + quantity)
        else:
            widget = PrintCardItemWidget(card_data, quantity=quantity, parent=self)
            widget.quantity_changed.connect(self.actualizar_estadisticas)
            widget.removed.connect(self.remover_carta_de_cola)

            count = self.queue_vbox.count()
            self.queue_vbox.insertWidget(max(0, count - 1), widget)
            self.queue_items[card_key] = widget

        self.actualizar_estadisticas()

    def remover_carta_de_cola(self, card_key):
        if card_key in self.queue_items:
            widget = self.queue_items.pop(card_key)
            self.queue_vbox.removeWidget(widget)
            widget.deleteLater()
            self.actualizar_estadisticas()

    def limpiar_cola(self):
        for card_key, widget in list(self.queue_items.items()):
            self.queue_vbox.removeWidget(widget)
            widget.deleteLater()
        self.queue_items.clear()
        self.actualizar_estadisticas()

    def abrir_dialogo_importar_mazo(self):
        dialog = ImportDecklistDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            texto = dialog.get_text()
            if not texto:
                return

            lineas = texto.splitlines()
            agregadas = 0

            for linea in lineas:
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

                carta = self.session.query(Cartas).filter(Cartas.nombre.ilike(f"%{card_search}%")).first()
                if not carta:
                    first_word = card_search.split()[0]
                    carta = self.session.query(Cartas).filter(Cartas.nombre.ilike(f"%{first_word}%")).first()

                if carta:
                    self.agregar_carta_a_cola({
                        "id_api": carta.id_api,
                        "nombre": carta.nombre,
                        "idioma": carta.idioma or "es",
                        "edition": carta.edition or ""
                    }, quantity=qty)
                    agregadas += qty

            if agregadas > 0:
                show_toast(f"Se agregaron {agregadas} cartas a la cola.", "success", 2500)
            else:
                QMessageBox.warning(self, t("Importar desde Texto"), "No se encontraron coincidencias para la lista.")

    def actualizar_estadisticas(self):
        total_cards = sum(widget.get_quantity() for widget in self.queue_items.values())
        pages = (total_cards + 8) // 9 if total_cards > 0 else 0

        self.lbl_stats.setText(f"Total: {total_cards} cartas | {pages} páginas PDF (3x3 grid)")
        self.btn_generate_pdf.setEnabled(total_cards > 0)

    def generar_pdf(self):
        if not self.queue_items:
            QMessageBox.warning(self, t("Error"), "La cola de impresión está vacía.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar PDF de Proxies",
            os.path.expanduser("~/Desktop/TCG_Proxies.pdf"),
            "Archivos PDF (*.pdf)"
        )
        if not file_path:
            return

        try:
            dpi = 300
            writer = QPdfWriter(file_path)
            writer.setResolution(dpi)

            is_letter = "Letter" in self.combo_paper.currentText()
            page_size_id = QPageSize.PageSizeId.Letter if is_letter else QPageSize.PageSizeId.A4
            writer.setPageSize(QPageSize(page_size_id))

            layout_margin = QMarginsF(0, 0, 0, 0)
            writer.setPageLayout(QPageLayout(QPageSize(page_size_id), QPageLayout.Orientation.Portrait, layout_margin))

            paper_w_mm = 215.9 if is_letter else 210.0
            paper_h_mm = 279.4 if is_letter else 297.0

            card_w_mm = 63.0
            card_h_mm = 88.0

            spacing_mm = 1.0 if self.chk_spacing.isChecked() else 0.0
            draw_crop_marks = self.chk_crop_marks.isChecked()

            grid_w_mm = (3 * card_w_mm) + (2 * spacing_mm)
            grid_h_mm = (3 * card_h_mm) + (2 * spacing_mm)

            margin_x_mm = (paper_w_mm - grid_w_mm) / 2.0
            margin_y_mm = (paper_h_mm - grid_h_mm) / 2.0

            mm_to_px = dpi / 25.4

            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            cards_list = []
            for widget in self.queue_items.values():
                card_info = widget.card_data
                qty = widget.get_quantity()
                for _ in range(qty):
                    cards_list.append(card_info)

            for idx, card in enumerate(cards_list):
                pos_in_page = idx % 9

                if idx > 0 and pos_in_page == 0:
                    writer.newPage()

                row = pos_in_page // 3
                col = pos_in_page % 3

                x_mm = margin_x_mm + col * (card_w_mm + spacing_mm)
                y_mm = margin_y_mm + row * (card_h_mm + spacing_mm)

                x_px = x_mm * mm_to_px
                y_px = y_mm * mm_to_px
                w_px = card_w_mm * mm_to_px
                h_px = card_h_mm * mm_to_px

                lang = card.get("idioma", "es")
                id_api = card.get("id_api")
                nombre = card.get("nombre")

                pix = get_hd_pixmap(id_api, nombre, lang)
                if not pix:
                    pix = get_webp_pixmap(id_api, nombre, lang)
                if not pix:
                    pix = get_pixmap_from_zip(nombre, id_api=id_api)

                target_rect = QRectF(x_px, y_px, w_px, h_px)

                if pix and not pix.isNull():
                    painter.drawPixmap(target_rect.toRect(), pix)
                else:
                    painter.setPen(QPen(QColor("#cbd5e1"), 2))
                    painter.drawRect(target_rect)
                    painter.setFont(QFont("Arial", 10))
                    painter.drawText(target_rect, Qt.AlignmentFlag.AlignCenter, f"{nombre}\n({id_api})")

                if draw_crop_marks:
                    pen_mark = QPen(QColor(100, 100, 100), 1.5, Qt.PenStyle.DashLine)
                    painter.setPen(pen_mark)

                    mark_len_px = 4.0 * mm_to_px

                    x1, y1 = x_px, y_px
                    x2, y2 = x_px + w_px, y_px + h_px

                    painter.drawLine(int(x1 - mark_len_px), int(y1), int(x1), int(y1))
                    painter.drawLine(int(x1), int(y1 - mark_len_px), int(x1), int(y1))

                    painter.drawLine(int(x2), int(y1), int(x2 + mark_len_px), int(y1))
                    painter.drawLine(int(x2), int(y1 - mark_len_px), int(x2), int(y1))

                    painter.drawLine(int(x1 - mark_len_px), int(y2), int(x1), int(y2))
                    painter.drawLine(int(x1), int(y2), int(x1), int(y2 + mark_len_px))

                    painter.drawLine(int(x2), int(y2), int(x2 + mark_len_px), int(y2))
                    painter.drawLine(int(x2), int(y2), int(x2), int(y2 + mark_len_px))

            painter.end()

            show_toast("PDF generado con éxito.", "success", 3500)
            QMessageBox.information(
                self,
                "PDF Creado",
                f"El archivo PDF se ha generado correctamente en:\n{file_path}\n\nListo para imprimir a 100% de escala."
            )

        except Exception as e:
            QMessageBox.critical(self, "Error generando PDF", f"Ocurrió un error al crear el archivo PDF:\n{str(e)}")

    def cargar_binder_automatico(self, binder_id: str):
        """Selecciona automáticamente un Binder y carga sus cartas en la cola de impresión/exportación."""
        self.limpiar_cola()
        idx_tipo = self.combo_origen_tipo.findData("binder")
        if idx_tipo >= 0:
            self.combo_origen_tipo.blockSignals(True)
            self.combo_origen_tipo.setCurrentIndex(idx_tipo)
            self.combo_origen_tipo.blockSignals(False)
        self.refrescar_items_origen()

        idx_item = self.combo_origen_item.findData(binder_id)
        if idx_item >= 0:
            self.combo_origen_item.setCurrentIndex(idx_item)
            self.cargar_origen_seleccionado_a_cola()
        else:
            show_toast("No se encontró el binder para cargar en Print.", "warning", 2500)

    def exportar_cola_csv(self):
        """Exporta las cartas actualmente en la cola de Print a un archivo CSV."""
        if not self.print_queue:
            show_toast("La cola está vacía. Agrega cartas antes de exportar CSV.", "warning", 2500)
            return

        import csv
        default_name = "PokeBinder_Export.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            t("Exportar CSV"),
            default_name,
            "Archivos CSV (*.csv)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Nombre", "Idioma", "Edicion", "Cantidad"])
                for item in self.print_queue:
                    cd = item["card_data"]
                    writer.writerow([
                        cd.get("id_api", ""),
                        cd.get("nombre", ""),
                        cd.get("idioma", "es"),
                        cd.get("edition", ""),
                        item.get("quantity", 1),
                    ])
            show_toast("Archivo CSV exportado con éxito.", "success", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error exportando CSV", f"No se pudo guardar el archivo CSV:\n{str(e)}")
