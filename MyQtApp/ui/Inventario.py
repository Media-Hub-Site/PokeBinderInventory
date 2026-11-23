from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QScrollArea, QGridLayout,
    QHBoxLayout, QLineEdit, QComboBox, QPushButton, QGraphicsOpacityEffect,
    QSizePolicy, QDialog, QInputDialog, QMessageBox, QFrame, QMenu
)
from PyQt6.QtGui import QPixmap, QAction, QColor, QPalette
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QUrl, QEasingCurve, QPoint
from PyQt6.QtMultimedia import QSoundEffect
import os

from ..session import SessionLocal
from ..models import Cartas, UsuarioCarta
from ..app.getImgs import (
    get_pixmap_from_zip, get_webp_pixmap, get_card_placeholder_pixmap,
    CardImageLoaderManager
)
from MyQtApp.ui.CardWidget import ClickableLabel, CardItemWidget, VariantLegendBar
from MyQtApp.ui.FilterVisualBar import EnergyTypeFilterBar
from MyQtApp.ui.toast import show_toast
from sqlalchemy import func, and_
from MyQtApp.config import SOUNDS_DIR
from MyQtApp.i18n import t, language_manager


class GaleriaCartasInventario(QWidget):
    CARTAS_POR_PAGINA = 30

    def __init__(self, path_imagenes, nombre_usuario):
        super().__init__()
        self.nombre_usuario = nombre_usuario
        self.path_imagenes = path_imagenes
        self.session = SessionLocal()
        self.labels_por_id = {}
        self.card_widgets_por_key = {}
        self._current_card_size = (120, 170)
        self.cartas_seleccionadas = set()
        self.carpeta_activa = None
        self.current_page = 0
        self.total_cartas = 0

        self.image_loader = CardImageLoaderManager(max_threads=6, parent=self)
        self.image_loader.image_ready.connect(self._on_async_image_ready)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setSpacing(6)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(t("BuscadorPlaceholder"))
        self.buscador.setProperty("class", "SearchInput")
        self.buscador.setMinimumWidth(140)
        row1.addWidget(self.buscador, stretch=1)

        self.timer_busqueda = QTimer()
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.timeout.connect(self.reset_page_and_actualizar)
        self.buscador.textChanged.connect(self.on_text_changed)

        self.btn_limpiar = QPushButton(t("Limpiar Filtros"))
        self.btn_limpiar.setProperty("class", "CleanBtn")
        self.btn_limpiar.clicked.connect(self.limpiar_filtros)
        row1.addWidget(self.btn_limpiar)

        self.lbl_valor_total = QLabel(f"{t('Valor Inventario')} $0.00 USD")
        self.lbl_valor_total.setProperty("class", "ValorTotalLabel")
        row1.addWidget(self.lbl_valor_total)

        self.btn_sync_precios = QPushButton(t("Precios Real-Time"))
        self.btn_sync_precios.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_precios.setProperty("class", "SyncBtn")
        self.btn_sync_precios.clicked.connect(self.iniciar_sincronizacion_precios)
        row1.addWidget(self.btn_sync_precios)

        self.btn_seleccionar_todo = QPushButton(t("Seleccionar Todo"))
        self.btn_seleccionar_todo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_seleccionar_todo.setProperty("class", "SyncBtn")
        self.btn_seleccionar_todo.clicked.connect(self.toggle_seleccionar_pagina)
        row1.addWidget(self.btn_seleccionar_todo)

        header_vbox.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.filtros = {}
        campos = {
            "Rareza": "rarity",
            "Tipo": "type",
            "Edición": "edition",
            "Etapa": "stage",
            "Entrenador": "trainer",
            "Especial": "especial_type"
        }

        for etiqueta, columna in campos.items():
            combo = QComboBox()
            combo.addItem(f"{t(etiqueta)}: {t('Todos')}")
            combo.setProperty("class", "FilterCombo")
            combo.currentIndexChanged.connect(self.reset_page_and_actualizar)
            self.filtros[columna] = combo
            row2.addWidget(combo, stretch=1)

        # Filtro de Idioma
        self.combo_idioma = QComboBox()
        self.combo_idioma.setProperty("class", "FilterCombo")
        self.combo_idioma.addItem(f"{t('Idioma')}: {t('Todos')}", None)
        self.combo_idioma.addItem("Español", "es")
        self.combo_idioma.addItem("English", "en")
        self.combo_idioma.addItem("日本語", "ja")
        self.combo_idioma.addItem("Français", "fr")
        self.combo_idioma.addItem("Português", "pt")
        self.combo_idioma.addItem("繁體中文", "zh")
        self.combo_idioma.currentIndexChanged.connect(self.reset_page_and_actualizar)
        row2.addWidget(self.combo_idioma, stretch=1)

        header_vbox.addLayout(row2)

        # Barra complementaria de filtros visuales por Energía Pokémon + Zoom rápido (Etapa 2)
        self.energy_bar = EnergyTypeFilterBar(self)
        self.energy_bar.type_selected.connect(self._on_energy_pill_selected)
        self.energy_bar.zoom_changed.connect(self._on_zoom_changed)
        self.filtros["type"].currentIndexChanged.connect(self._sync_energy_bar_from_combo)
        header_vbox.addWidget(self.energy_bar)

        # Barra dedicada y vistosa de Carpetas de Colección (Issue #12 y #15, sin emojis)
        self.carpetas_bar = QFrame()
        self.carpetas_bar.setObjectName("CarpetasBar")
        self.carpetas_bar.setFixedHeight(42)
        self.carpetas_bar.setStyleSheet("""
            QFrame#CarpetasBar {
                background-color: #ffeef2;
                border: 1.5px solid #f3c8d1;
                border-radius: 10px;
            }
        """)
        carpetas_bar_layout = QHBoxLayout(self.carpetas_bar)
        carpetas_bar_layout.setContentsMargins(10, 3, 10, 3)
        carpetas_bar_layout.setSpacing(8)

        self.lbl_carpetas_titulo = QLabel(t("Colecciones"))
        self.lbl_carpetas_titulo.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;"
        )
        carpetas_bar_layout.addWidget(self.lbl_carpetas_titulo)

        # Contenedor horizontal desplazable de pastillas de colecciones
        self.carpetas_scroll = QScrollArea()
        self.carpetas_scroll.setWidgetResizable(True)
        self.carpetas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.carpetas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.carpetas_scroll.setFixedHeight(30)
        self.carpetas_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.carpetas_pills_widget = QWidget()
        self.carpetas_pills_widget.setStyleSheet("background: transparent;")
        self.carpetas_pills_layout = QHBoxLayout(self.carpetas_pills_widget)
        self.carpetas_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.carpetas_pills_layout.setSpacing(6)
        self.carpetas_scroll.setWidget(self.carpetas_pills_widget)
        carpetas_bar_layout.addWidget(self.carpetas_scroll, stretch=1)

        # Botón desplegable unificado para interactuar con la colección (Issue #40)
        self.btn_opciones_col = QPushButton(f"{t('Opciones')} ▾")
        self.btn_opciones_col.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_opciones_col.setFixedHeight(28)
        self.btn_opciones_col.setToolTip(t("Opciones para crear, asignar, quitar o eliminar en colecciones"))
        self.btn_opciones_col.setStyleSheet("""
            QPushButton {
                background-color: #f7a8b8;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                border: 1.5px solid #f29ca4;
                border-radius: 9px;
                padding: 2px 14px;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #f5475c;
            }
            QPushButton:pressed {
                background-color: #d44854;
            }
        """)
        self.btn_opciones_col.clicked.connect(self._mostrar_menu_opciones_coleccion)
        carpetas_bar_layout.addWidget(self.btn_opciones_col)

        header_vbox.addWidget(self.carpetas_bar)
        self.main_layout.addLayout(header_vbox)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self.container = QWidget()
        self.container.setObjectName("InventarioContainer")
        self.grid = QGridLayout(self.container)
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll, stretch=1)

        paginacion_layout = QHBoxLayout()
        self.btn_anterior = QPushButton(t("Anterior"))
        self.btn_anterior.setProperty("class", "PaginationBtn")
        self.btn_siguiente = QPushButton(t("Siguiente"))
        self.btn_siguiente.setProperty("class", "PaginationBtn")
        self.lbl_pagina = QLabel("")
        self.lbl_pagina.setProperty("class", "PaginationLabel")
        self.lbl_pagina.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_anterior.clicked.connect(self.pagina_anterior)
        self.btn_siguiente.clicked.connect(self.pagina_siguiente)
        paginacion_layout.addWidget(self.btn_anterior)
        paginacion_layout.addWidget(self.lbl_pagina)
        paginacion_layout.addWidget(self.btn_siguiente)
        self.main_layout.addLayout(paginacion_layout)

        self.sonido_pagina = QSoundEffect()
        self.sonido_pagina.setSource(QUrl.fromLocalFile(os.path.join(SOUNDS_DIR, "paginas.wav")))
        self.sonido_pagina.setVolume(0.5)

        self.cargar_filtros()
        self.actualizar_total_cartas()
        self.actualizar_valor_total()
        self.actualizar_galeria()
        language_manager.language_changed.connect(self.retranslate_ui)


    # ✅ SQLAlchemy: cargar combos
    def cargar_filtros(self):
        for columna, combo in self.filtros.items():
            valores = (
                self.session.query(getattr(Cartas, columna))
                .filter(getattr(Cartas, columna).isnot(None))
                .distinct()
                .all()
            )
            valores = sorted(v[0] for v in valores if v[0])
            for val in valores:
                combo.addItem(val)

        self.cargar_categorias_combo()

    def cargar_categorias_combo(self):
        """Refresca las pastillas interactivas de carpetas de la colección."""
        from MyQtApp.app.db_services import obtener_categorias_usuario
        cats = obtener_categorias_usuario(self.nombre_usuario)
        if self.carpeta_activa and self.carpeta_activa not in cats:
            self.carpeta_activa = None

        while self.carpetas_pills_layout.count():
            item = self.carpetas_pills_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        def _make_pill(label_text, cat_value):
            btn = QPushButton(label_text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            is_active = (self.carpeta_activa == cat_value)
            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f56b7b;
                        color: #ffffff;
                        font-weight: 700;
                        font-size: 11px;
                        border: 1.5px solid #e05263;
                        border-radius: 10px;
                        padding: 1px 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #5a2a3a;
                        font-weight: 600;
                        font-size: 11px;
                        border: 1.5px solid #f2b8c3;
                        border-radius: 10px;
                        padding: 1px 12px;
                    }
                    QPushButton:hover {
                        background-color: #ffdfe6;
                        border-color: #f56b7b;
                    }
                """)
            btn.clicked.connect(lambda ch, val=cat_value: self._seleccionar_carpeta_pill(val))
            return btn

        self.carpetas_pills_layout.addWidget(_make_pill(t("Todas"), None))
        for cat in cats:
            self.carpetas_pills_layout.addWidget(_make_pill(cat, cat))
        self.carpetas_pills_layout.addStretch()

        # Habilitar botones solo si estamos en una colección creada por el usuario (Issues #32 y #33)
        en_coleccion_propia = bool(self.carpeta_activa)
        if hasattr(self, "btn_eliminar_col"):
            self.btn_eliminar_col.setEnabled(en_coleccion_propia)
        if hasattr(self, "btn_quitar_col"):
            self.btn_quitar_col.setEnabled(en_coleccion_propia)

    def _seleccionar_carpeta_pill(self, cat_value):
        if self.carpeta_activa == cat_value:
            return
        self.carpeta_activa = cat_value
        self.cargar_categorias_combo()
        self.actualizar_valor_total()
        self.reset_page_and_actualizar()

    def _mostrar_menu_opciones_coleccion(self):
        """Despliega el menú con las 4 opciones de colección (Issue #40): Nuevo, Asignar, Quitar, Eliminar."""
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

        act_nuevo = QAction(t("Nuevo"), menu)
        act_nuevo.setToolTip("¿Desea crear una nueva colección?")
        act_nuevo.triggered.connect(self.abrir_creador_categorias)
        menu.addAction(act_nuevo)

        act_asignar = QAction(t("Asignar"), menu)
        act_asignar.setToolTip("¿Desea asignar a otra colección?")
        act_asignar.triggered.connect(self.asignar_cartas_a_coleccion)
        menu.addAction(act_asignar)

        act_quitar = QAction(t("Quitar"), menu)
        act_quitar.setToolTip("¿Desea quitar de la colección?")
        act_quitar.setEnabled(bool(self.carpeta_activa))
        act_quitar.triggered.connect(self.quitar_cartas_de_coleccion)
        menu.addAction(act_quitar)

        menu.addSeparator()

        act_eliminar = QAction(t("Eliminar"), menu)
        act_eliminar.setToolTip("¿Desea eliminar de todas las colecciones?")
        act_eliminar.triggered.connect(self.opcion_eliminar_coleccion)
        menu.addAction(act_eliminar)

        menu.exec(self.btn_opciones_col.mapToGlobal(QPoint(0, self.btn_opciones_col.height() + 2)))

    def abrir_creador_categorias(self):
        """Diálogo limpio para crear una nueva colección (Issue #33 y #40)."""
        from MyQtApp.app.db_services import crear_categoria_usuario
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Nueva Colección"))
        dlg.setFixedSize(380, 185)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QLabel {
                font-weight: 600;
                color: #5a2a3a;
                font-size: 13px;
            }
            QLineEdit {
                border: 2px solid #f7a8b8;
                border-radius: 10px;
                padding: 7px 10px;
                background-color: #ffffff;
                color: #5a2a3a;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #f56b7b;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        lbl_head = QLabel(t("¿Desea crear una nueva colección?"))
        lbl_head.setStyleSheet("font-size: 15px; font-weight: 700; color: #5a2a3a;")
        layout.addWidget(lbl_head)

        txt_nueva = QLineEdit()
        txt_nueva.setPlaceholderText(t("Nombre de colección (ej: Favoritas, Kalos, Charizards...)"))
        layout.addWidget(txt_nueva)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cerrar = QPushButton(t("Cancelar"))
        btn_cerrar.setFixedHeight(34)
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #703043;
                border: 2px solid #f2c4ce;
                border-radius: 10px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #ffeef2; }
        """)
        btn_cerrar.clicked.connect(dlg.reject)

        btn_crear = QPushButton(t("Crear Colección"))
        btn_crear.setFixedHeight(34)
        btn_crear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_crear.setStyleSheet("""
            QPushButton {
                background-color: #f7a8b8;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border: 2px solid #f29ca4;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #f5475c;
            }
        """)

        def on_crear():
            nombre = txt_nueva.text().strip()
            if not nombre:
                QMessageBox.warning(dlg, t("Aviso"), t("Ingresa un nombre para la colección."))
                return
            if crear_categoria_usuario(self.nombre_usuario, nombre):
                self.carpeta_activa = nombre
                self.cargar_categorias_combo()
                self.actualizar_valor_total()
                self.reset_page_and_actualizar()
                show_toast(f"Colección '{nombre}' creada", "success")
                dlg.accept()
            else:
                QMessageBox.warning(dlg, t("Aviso"), t("Ya existe una colección con ese nombre."))

        btn_crear.clicked.connect(on_crear)
        txt_nueva.returnPressed.connect(on_crear)

        btn_row.addWidget(btn_cerrar)
        btn_row.addWidget(btn_crear)
        layout.addStretch()
        layout.addLayout(btn_row)

        dlg.exec()

    def _confirmar_dialogo_continuar(self, titulo: str, mensaje: str) -> bool:
        """Diálogo de confirmación con botones Cancelar y Continuar."""
        box = QMessageBox(self)
        box.setWindowTitle(titulo)
        box.setText(mensaje)
        box.setIcon(QMessageBox.Icon.Warning)
        btn_cancel = box.addButton(t("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        btn_cont = box.addButton(t("Continuar"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_cont

    def eliminar_coleccion_activa(self):
        """Elimina la colección en la que el usuario está posicionado con doble advertencia (Issue #33)."""
        if not self.carpeta_activa:
            return
        nombre = self.carpeta_activa

        # 1ª confirmación
        if not self._confirmar_dialogo_continuar(
            t("Eliminar Colección"),
            f"¿Estás seguro de que deseas eliminar la colección '{nombre}'?\n"
            f"(Las cartas seguirán disponibles en la colección 'Todas')."
        ):
            return

        # 2ª advertencia irreversible
        if not self._confirmar_dialogo_continuar(
            t("Advertencia"),
            f"Esta acción es irreversible.\n¿Deseas continuar y eliminar permanentemente la colección '{nombre}'?"
        ):
            return

        from MyQtApp.app.db_services import eliminar_categoria_usuario
        eliminar_categoria_usuario(self.nombre_usuario, nombre)
        self.carpeta_activa = None
        self.cargar_categorias_combo()
        self.actualizar_valor_total()
        self.reset_page_and_actualizar()
        show_toast(f"Colección '{nombre}' eliminada", "info")

    def opcion_eliminar_coleccion(self):
        """Acción 'Eliminar' del menú de opciones de colección (Issue #40: '¿desea eliminar de todas las colecciones?')."""
        if self.cartas_seleccionadas:
            cartas = self.get_cartas_seleccionadas()
            if not self._confirmar_dialogo_continuar(
                t("Eliminar"),
                f"{t('¿Desea eliminar de todas las colecciones?')}\n\n"
                f"Se eliminarán {len(cartas)} carta(s) seleccionada(s) de tu inventario."
            ):
                return
            from MyQtApp.app.db_services import eliminar_cartas_usuario
            eliminados = eliminar_cartas_usuario(self.nombre_usuario, cartas)
            self.limpiar_seleccion()
            self.actualizar_valor_total()
            self.reset_page_and_actualizar()
            if eliminados:
                show_toast(f"{eliminados} carta(s) eliminada(s) de todas las colecciones", "info")
            return

        if self.carpeta_activa:
            self.eliminar_coleccion_activa()
        else:
            show_toast("Selecciona al menos una carta para eliminar de todas las colecciones (o elige una colección).", "warning", 2600)

    def asignar_cartas_a_coleccion(self):
        """Asigna las cartas seleccionadas en la vista actual a una colección creada por el usuario (Issue #32 y #40)."""
        if not self.cartas_seleccionadas:
            show_toast("Selecciona al menos una carta para asignar a otra colección.", "warning", 2200)
            return

        from MyQtApp.app.db_services import obtener_categorias_usuario
        cats = obtener_categorias_usuario(self.nombre_usuario)
        if not cats:
            show_toast("Primero crea una colección desde Opciones -> Nuevo.", "info", 2500)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(t("Asignar a colección"))
        dlg.setFixedSize(370, 195)
        dlg.setStyleSheet("""
            QDialog { background-color: #fff5f7; }
            QLabel { font-weight: 600; color: #5a2a3a; font-size: 13px; }
            QComboBox {
                border: 2px solid #f7a8b8; border-radius: 10px;
                padding: 6px 10px; background-color: #ffffff; color: #5a2a3a; font-size: 13px;
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
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        lbl_q = QLabel(t("¿Desea asignar a otra colección?"))
        lbl_q.setStyleSheet("font-size: 15px; font-weight: 700; color: #5a2a3a;")
        lay.addWidget(lbl_q)
        lay.addWidget(QLabel(t("Elige la colección de destino:")))
        combo = QComboBox()
        for c in cats:
            combo.addItem(c, c)
        view = combo.view()
        if view is not None:
            pal = view.palette()
            pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
            pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#e25b70"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            view.setPalette(pal)
        for i in range(combo.count()):
            combo.setItemData(i, QColor("#ffffff"), Qt.ItemDataRole.ForegroundRole)
        lay.addWidget(combo)

        brow = QHBoxLayout()
        btn_c = QPushButton(t("Cancelar"))
        btn_c.setFixedHeight(34)
        btn_c.clicked.connect(dlg.reject)
        btn_ok = QPushButton(t("Asignar"))
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet("background-color: #f56b7b; color: white; font-weight: 700; border-radius: 9px; padding: 2px 14px;")
        btn_ok.clicked.connect(dlg.accept)
        brow.addWidget(btn_c)
        brow.addWidget(btn_ok)
        lay.addStretch()
        lay.addLayout(brow)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        destino = combo.currentData()
        actualizadas = 0
        try:
            for key in list(self.cartas_seleccionadas):
                if ":" in key:
                    id_api, lang = key.split(":", 1)
                else:
                    id_api, lang = key, None
                q = self.session.query(UsuarioCarta).filter(
                    UsuarioCarta.usuario_nombre == self.nombre_usuario,
                    UsuarioCarta.carta_id == id_api,
                )
                if lang:
                    q = q.filter(func.coalesce(UsuarioCarta.idioma, "es") == lang)
                rel = q.first()
                if rel:
                    rel.categoria = destino
                    actualizadas += 1
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            print(f"Error asignando cartas a colección: {e}")

        self.limpiar_seleccion()
        self.actualizar_valor_total()
        self.reset_page_and_actualizar()
        show_toast(f"{actualizadas} carta(s) asignada(s) a '{destino}'", "success")

    def quitar_cartas_de_coleccion(self):
        """Quita las cartas seleccionadas de la colección actual (seguirán existiendo en 'Todas') (Issue #32 y #40)."""
        if not self.carpeta_activa:
            show_toast("Posiciónate en una colección específica para quitar cartas de ella.", "warning", 2200)
            return
        if not self.cartas_seleccionadas:
            show_toast("Selecciona al menos una carta para quitar de esta colección.", "warning", 2200)
            return

        if not self._confirmar_dialogo_continuar(
            t("Quitar de colección"),
            f"{t('¿Desea quitar de la colección?')}\n\n"
            f"Se quitarán {len(self.cartas_seleccionadas)} carta(s) de '{self.carpeta_activa}' (seguirán en 'Todas')."
        ):
            return

        actualizadas = 0
        try:
            for key in list(self.cartas_seleccionadas):
                if ":" in key:
                    id_api, lang = key.split(":", 1)
                else:
                    id_api, lang = key, None
                q = self.session.query(UsuarioCarta).filter(
                    UsuarioCarta.usuario_nombre == self.nombre_usuario,
                    UsuarioCarta.carta_id == id_api,
                    UsuarioCarta.categoria == self.carpeta_activa,
                )
                if lang:
                    q = q.filter(func.coalesce(UsuarioCarta.idioma, "es") == lang)
                rel = q.first()
                if rel:
                    rel.categoria = None
                    actualizadas += 1
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            print(f"Error quitando cartas de colección: {e}")

        col_name = self.carpeta_activa
        self.limpiar_seleccion()
        self.actualizar_valor_total()
        self.reset_page_and_actualizar()
        show_toast(f"{actualizadas} carta(s) quitada(s) de '{col_name}'", "info")

    def limpiar_filtros(self):
        self.buscador.blockSignals(True)
        self.buscador.clear()
        self.buscador.blockSignals(False)

        for combo in self.filtros.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

        if hasattr(self, "energy_bar"):
            self.energy_bar.set_active_type(None)

        if hasattr(self, 'combo_idioma'):
            self.combo_idioma.blockSignals(True)
            self.combo_idioma.setCurrentIndex(0)
            self.combo_idioma.blockSignals(False)

        self.carpeta_activa = None
        self.cargar_categorias_combo()

        self.reset_page_and_actualizar()

    def on_text_changed(self):
        self.timer_busqueda.start(300)

    def reset_page_and_actualizar(self):
        self.current_page = 0
        self.actualizar_total_cartas()
        self.actualizar_valor_total()
        self.actualizar_con_transicion()

    def _get_filter_value(self, combo):
        if combo.currentIndex() <= 0:
            return None
        return combo.currentText().strip()

    # ✅ SQLAlchemy conteo
    def actualizar_total_cartas(self):
        q = self.session.query(func.count(Cartas.id_api)).join(UsuarioCarta).filter(
            UsuarioCarta.usuario_nombre == self.nombre_usuario
        )

        selected_lang = self.combo_idioma.currentData()
        if selected_lang:
            q = q.filter(Cartas.idioma == selected_lang)

        if self.carpeta_activa:
            q = q.filter(UsuarioCarta.categoria == self.carpeta_activa)

        texto = self.buscador.text().lower().strip()
        if texto:
            q = q.filter(func.lower(Cartas.nombre).like(f"%{texto}%"))

        for columna, combo in self.filtros.items():
            if val := self._get_filter_value(combo):
                q = q.filter(getattr(Cartas, columna) == val)

        self.total_cartas = q.scalar()

    def actualizar_con_transicion(self):
        self.actualizar_galeria()
        self.container.update()
        self.scroll.viewport().update()

    # ✅ SQLAlchemy mostrar cartas
    def actualizar_galeria(self):
        # Limpiar sincrónicamente la estructura de la cuadrícula
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        texto = self.buscador.text().lower().strip()

        # Obtener dimensiones de carta desde ajustes
        from MyQtApp.config import load_settings
        settings = load_settings()
        tam = settings.get("tamano_cartas", "Normal")
        if tam == "Pequeño":
            size = (90, 127)
            cols_per_row = 7
        elif tam == "Grande":
            size = (150, 212)
            cols_per_row = 4
        else:  # Normal
            size = (120, 170)
            cols_per_row = 5
        self._current_card_size = size
        if hasattr(self, "energy_bar"):
            self.energy_bar.set_active_zoom(tam)

        q = self.session.query(Cartas, UsuarioCarta.variante).join(
            UsuarioCarta,
            and_(
                Cartas.id_api == UsuarioCarta.carta_id,
                func.coalesce(Cartas.idioma, 'es') == func.coalesce(UsuarioCarta.idioma, 'es')
            )
        ).filter(
            UsuarioCarta.usuario_nombre == self.nombre_usuario
        )

        selected_lang = self.combo_idioma.currentData()
        if selected_lang:
            q = q.filter(Cartas.idioma == selected_lang)

        if self.carpeta_activa:
            q = q.filter(UsuarioCarta.categoria == self.carpeta_activa)

        if texto:
            q = q.filter(func.lower(Cartas.nombre).like(f"%{texto}%"))

        for columna, combo in self.filtros.items():
            if val := self._get_filter_value(combo):
                q = q.filter(getattr(Cartas, columna) == val)

        q = q.limit(self.CARTAS_POR_PAGINA).offset(self.current_page * self.CARTAS_POR_PAGINA)
        cartas_tuples = q.all()

        row, col = 0, 0
        self.labels_por_id.clear()
        self.card_widgets_por_key.clear()

        for carta, variante_db in cartas_tuples:
            nombre = carta.nombre
            id_api = carta.id_api
            card_lang = carta.idioma or language_manager.current_language
            card_key = f"{id_api}:{card_lang}"
            nombre_archivo = nombre.lower().replace(" ", "_")
            needs_download = False

            # 1. Intentar cargar versión .webp exacta por idioma de la carta
            pixmap = get_webp_pixmap(id_api, nombre, card_lang, size=size, allow_lang_fallback=False)
            if not pixmap:
                needs_download = True
                pixmap = get_webp_pixmap(id_api, nombre, card_lang, size=size, allow_lang_fallback=True)
            if not pixmap:
                pixmap = get_pixmap_from_zip(nombre_archivo, size=size, id_api=id_api)
            if not pixmap:
                ruta_alt = os.path.join(self.path_imagenes, f"{nombre_archivo}_{id_api}.webp")
                if os.path.exists(ruta_alt):
                    pixmap = QPixmap(ruta_alt).scaled(size[0], size[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            if not pixmap or pixmap.isNull():
                pixmap = get_card_placeholder_pixmap(size, nombre)
                needs_download = True

            card_widget = CardItemWidget(carta, pixmap, size, variante=variante_db or "Normal")
            card_widget.image_label.card_key = card_key
            card_widget.image_label.clicked.connect(self.seleccionar_carta)
            card_widget.variant_badge.variant_changed.connect(self.cambiar_variante_carta)

            if card_key in self.cartas_seleccionadas:
                card_widget.image_label.setStyleSheet("border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);")
            else:
                card_widget.image_label.setStyleSheet("border: none; background-color: transparent;")

            self.labels_por_id.setdefault(card_key, []).append(card_widget.image_label)
            self.card_widgets_por_key.setdefault(card_key, []).append(card_widget)
            self.grid.addWidget(card_widget, row, col)

            if needs_download:
                self.image_loader.request_image(
                    card_key,
                    id_api,
                    nombre,
                    idioma=card_lang,
                    set_id=getattr(carta, "set_id", None),
                    number=getattr(carta, "number", None),
                )

            col += 1
            if col == cols_per_row:
                col = 0
                row += 1

        total_pages = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        self.lbl_pagina.setText(f"{t('Página')} {self.current_page + 1} {t('de')} {total_pages}")
        self.btn_anterior.setEnabled(self.current_page > 0)
        self.btn_siguiente.setEnabled(self.current_page < total_pages - 1)

    def _on_energy_pill_selected(self, type_val):
        """Sincroniza el QComboBox de Tipo cuando se hace clic en una ficha visual de energía."""
        combo = self.filtros.get("type")
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
        self.reset_page_and_actualizar()

    def _sync_energy_bar_from_combo(self):
        """Sincroniza la barra visual de energías cuando cambia el QComboBox de Tipo."""
        combo = self.filtros.get("type")
        if combo and hasattr(self, "energy_bar"):
            val = combo.currentText() if combo.currentIndex() > 0 else None
            self.energy_bar.set_active_type(val)

    def _on_zoom_changed(self, size_key: str):
        """Aplica inmediatamente la escala seleccionada (Pequeño / Normal / Grande)."""
        from MyQtApp.config import load_settings, save_settings
        settings = load_settings()
        settings["tamano_cartas"] = size_key
        save_settings(settings)
        self.actualizar_galeria()

    def _on_async_image_ready(self, card_key: str, local_path: str):
        widgets = self.card_widgets_por_key.get(card_key)
        if not widgets or not os.path.exists(local_path):
            return
        pix = QPixmap(local_path)
        if pix.isNull():
            return
        w, h = self._current_card_size
        scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        for cw in list(widgets):
            try:
                cw.set_card_pixmap(scaled)
            except RuntimeError:
                pass

    def cambiar_variante_carta(self, id_api, nueva_variante):
        try:
            rel = self.session.query(UsuarioCarta).filter(
                UsuarioCarta.usuario_nombre == self.nombre_usuario,
                UsuarioCarta.carta_id == id_api
            ).first()
            if rel:
                rel.variante = nueva_variante
                self.session.commit()
                show_toast(f"Variante actualizada: {nueva_variante}", "info")

        except Exception as e:
            print(f"Error cambiando variante en BD: {e}")

    def retranslate_ui(self):
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        self.btn_sync_precios.setText(t("Precios Real-Time"))
        if hasattr(self, 'btn_seleccionar_todo'):
            self.btn_seleccionar_todo.setText(t("Seleccionar Todo"))
        self.btn_anterior.setText(t("Anterior"))
        self.btn_siguiente.setText(t("Siguiente"))
        total_pages = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        self.lbl_pagina.setText(f"{t('Página')} {self.current_page + 1} {t('de')} {total_pages}")
        self.actualizar_valor_total()

        campos_labels = [("Rareza", "rarity"), ("Tipo", "type"), ("Edición", "edition"),
                         ("Etapa", "stage"), ("Entrenador", "trainer"), ("Especial", "especial_type")]
        for etiqueta, columna in campos_labels:
            if columna in self.filtros:
                cb = self.filtros[columna]
                if cb.count() > 0:
                    cb.setItemText(0, f"{t(etiqueta)}: {t('Todos')}")

    def pagina_anterior(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.actualizar_con_transicion()
            from MyQtApp.config import load_settings
            settings = load_settings()
            vol = (settings.get("volumen_sonido", 80) / 100.0) * 0.5
            self.sonido_pagina.setVolume(vol)
            self.sonido_pagina.play()

    def pagina_siguiente(self):
        total = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        if self.current_page < total - 1:
            self.current_page += 1
            self.actualizar_con_transicion()
            from MyQtApp.config import load_settings
            settings = load_settings()
            vol = (settings.get("volumen_sonido", 80) / 100.0) * 0.5
            self.sonido_pagina.setVolume(vol)
            self.sonido_pagina.play()

    def seleccionar_carta(self, label_obj, id_carta):
        card_key = getattr(label_obj, 'card_key', None) or id_carta

        if card_key in self.cartas_seleccionadas:
            self.cartas_seleccionadas.remove(card_key)
            style = "border: none; background-color: transparent;"
        else:
            self.cartas_seleccionadas.add(card_key)
            style = "border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);"

        labels = self.labels_por_id.get(card_key, [])
        if isinstance(labels, list):
            if label_obj and label_obj not in labels:
                labels.append(label_obj)
            for lbl in labels:
                lbl.setStyleSheet(style)
        elif label_obj:
            label_obj.setStyleSheet(style)

    def toggle_seleccionar_pagina(self):
        """Selecciona o deselecciona todas las cartas visibles en la página actual (Issue #49)."""
        if not self.labels_por_id:
            return
        page_keys = set(self.labels_por_id.keys())
        all_selected = page_keys.issubset(self.cartas_seleccionadas)

        if all_selected:
            # Deseleccionar todas las cartas de esta página
            for key in page_keys:
                self.cartas_seleccionadas.discard(key)
                labels = self.labels_por_id.get(key, [])
                if isinstance(labels, list):
                    for lbl in labels:
                        lbl.setStyleSheet("border: none; background-color: transparent;")
                elif labels:
                    labels.setStyleSheet("border: none; background-color: transparent;")
        else:
            # Seleccionar todas las cartas de esta página
            for key in page_keys:
                self.cartas_seleccionadas.add(key)
                labels = self.labels_por_id.get(key, [])
                if isinstance(labels, list):
                    for lbl in labels:
                        lbl.setStyleSheet("border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);")
                elif labels:
                    labels.setStyleSheet("border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);")

    def get_cartas_seleccionadas(self):
        if not self.cartas_seleccionadas:
            return []

        resultado = []
        for key in self.cartas_seleccionadas:
            if ":" in key:
                id_api, lang = key.split(":", 1)
            else:
                id_api, lang = key, language_manager.current_language

            c = self.session.query(Cartas.id_api, Cartas.nombre, Cartas.idioma)\
                .filter(Cartas.id_api == id_api, Cartas.idioma == lang).first()
            if not c:
                c = self.session.query(Cartas.id_api, Cartas.nombre, Cartas.idioma)\
                    .filter(Cartas.id_api == id_api).first()

            if c:
                resultado.append({"id_api": c[0], "nombre": c[1], "idioma": c[2]})

        return resultado

    def limpiar_seleccion(self):
        self.cartas_seleccionadas.clear()
        for key, labels in self.labels_por_id.items():
            if isinstance(labels, list):
                for lbl in labels:
                    lbl.setStyleSheet("border: none; background-color: transparent;")
            elif labels:
                labels.setStyleSheet("border: none; background-color: transparent;")

    def iniciar_sincronizacion_precios(self):
        from MyQtApp.app.price_updater import PriceUpdaterThread

        cartas_usuario = self.session.query(UsuarioCarta.carta_id, UsuarioCarta.idioma).filter(
            UsuarioCarta.usuario_nombre == self.nombre_usuario
        ).all()

        id_list = [(c[0], c[1] or "en") for c in cartas_usuario if c[0]]
        if not id_list:
            return

        self.btn_sync_precios.setEnabled(False)
        self.btn_sync_precios.setText("Conectando...")

        self.price_thread = PriceUpdaterThread(id_list, parent=self)
        self.price_thread.progress.connect(self.on_precio_progreso)
        self.price_thread.finished.connect(self.on_precio_finalizado)
        self.price_thread.start()

    def on_precio_progreso(self, actual, total):
        self.btn_sync_precios.setText(f"Cargando ({actual}/{total})...")

    def on_precio_finalizado(self, actualizadas):
        self.session.expire_all()
        self.btn_sync_precios.setEnabled(True)
        self.btn_sync_precios.setText(t("Precios Real-Time"))
        self.actualizar_valor_total()
        self.actualizar_galeria()

    def actualizar_valor_total(self):
        """Calcula el valor acumulado de la colección actualmente seleccionada ('Todas' o una sub-colección) (Issue #37)."""
        q = (
            self.session.query(func.sum(Cartas.price))
            .join(
                UsuarioCarta,
                and_(
                    Cartas.id_api == UsuarioCarta.carta_id,
                    func.coalesce(Cartas.idioma, 'es') == func.coalesce(UsuarioCarta.idioma, 'es'),
                ),
            )
            .filter(
                UsuarioCarta.usuario_nombre == self.nombre_usuario,
                Cartas.price > 0,
            )
        )
        if self.carpeta_activa:
            q = q.filter(UsuarioCarta.categoria == self.carpeta_activa)

        res = q.scalar()
        total_val = float(res) if res else 0.0
        if self.carpeta_activa:
            self.lbl_valor_total.setText(f"{t('Valor')} ({self.carpeta_activa}): ${total_val:,.2f} USD")
        else:
            self.lbl_valor_total.setText(f"{t('Valor Colección')} ({t('Todas')}): ${total_val:,.2f} USD")
