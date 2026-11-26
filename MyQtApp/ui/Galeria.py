from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QScrollArea, QGridLayout,
    QHBoxLayout, QLineEdit, QComboBox, QPushButton, QGraphicsOpacityEffect,
    QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSpinBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QUrl, QEasingCurve
from PyQt6.QtMultimedia import QSoundEffect
import os

from MyQtApp.app.getImgs import (
    get_pixmap_from_zip, get_webp_pixmap, get_card_placeholder_pixmap,
    has_exact_lang_image, CardImageLoaderManager
)
from MyQtApp.app.filtro import sort_filter_values, format_filter_option_label
from MyQtApp.app.price_updater import format_price, get_active_currency
from MyQtApp.ui.CardWidget import ClickableLabel, CardItemWidget, VariantLegendBar, CardZoomOverlay
from MyQtApp.ui.FilterVisualBar import EnergyTypeFilterBar
from ..session import SessionLocal
from ..models import Cartas  # tu modelo SQLAlchemy

from MyQtApp.config import SOUNDS_DIR
from MyQtApp.i18n import t, language_manager


class GaleriaCartas(QWidget):
    CARTAS_POR_PAGINA = 30

    def __init__(self, path_imagenes):
        super().__init__()
        self.path_imagenes = path_imagenes
        self.session = SessionLocal()

        self.labels_por_id = {}
        self.card_widgets_por_key = {}
        self._current_card_size = (120, 170)
        self.cartas_seleccionadas = set()
        self.cantidades_seleccionadas = {}
        self.current_page = 0
        self.total_cartas = 0
        self._active_generation = None
        self._view_mode = "grid"  # "grid" | "list"
        self._current_cards_map = {}

        self.image_loader = CardImageLoaderManager(max_threads=6, parent=self)
        self.image_loader.image_ready.connect(self._on_async_image_ready)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 8)
        self.main_layout.setSpacing(8)

        # Header estructurado en 2 filas
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(6)

        # Fila 1: Buscador (expansible) + Botón Sync Precios
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.buscador = QLineEdit()
        self.buscador.setProperty("class", "SearchInput")
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        self.buscador.setMinimumWidth(180)
        self.timer_busqueda = QTimer()
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.timeout.connect(self.reset_page_and_actualizar)
        self.buscador.textChanged.connect(self.on_text_changed)
        row1.addWidget(self.buscador, stretch=1)

        self.btn_sync_precios = QPushButton(t("Actualizar Precios"))
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

        # Fila 2: Combos de Filtros distribuidos limpiamente
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.filtros = {}
        campos = {
            "Tipo": Cartas.type,
            "Etapa": Cartas.stage,
            "Rule Box": Cartas.especial_type,
            "Entrenador": Cartas.trainer,
            "Rareza": Cartas.rarity,
            "Edición": Cartas.edition
        }

        for etiqueta, columna in campos.items():
            combo = QComboBox()
            combo.addItem(f"{t(etiqueta)}: {t('Todos')}", None)
            combo.setProperty("class", "FilterCombo")
            combo.currentIndexChanged.connect(self.reset_page_and_actualizar)
            self.filtros[columna] = combo
            row2.addWidget(combo, stretch=1)

        # Filtro de Idioma
        self.combo_idioma = QComboBox()
        self.combo_idioma.setProperty("class", "FilterCombo")
        self.combo_idioma.addItem(f"{t('Idioma')}: {t('Todos')}", None)
        self.combo_idioma.addItem("Español 🇪🇸", "es")
        self.combo_idioma.addItem("English 🇬🇧", "en")
        self.combo_idioma.addItem("日本語 🇯🇵", "ja")
        self.combo_idioma.addItem("Français 🇫🇷", "fr")
        self.combo_idioma.addItem("Português 🇵🇹", "pt")
        self.combo_idioma.addItem("繁體中文 🇨🇳", "zh")
        self.combo_idioma.currentIndexChanged.connect(self.reset_page_and_actualizar)
        row2.addWidget(self.combo_idioma, stretch=1)

        header_vbox.addLayout(row2)

        # Barra complementaria de filtros visuales por Energía / Generación Pokémon + Zoom rápido (Etapa 2 / Issue #54)
        self.energy_bar = EnergyTypeFilterBar(self)
        self.energy_bar.type_selected.connect(self._on_energy_pill_selected)
        self.energy_bar.generation_selected.connect(self._on_generation_pill_selected)
        self.energy_bar.zoom_changed.connect(self._on_zoom_changed)
        self.filtros[Cartas.type].currentIndexChanged.connect(self._sync_energy_bar_from_combo)
        header_vbox.addWidget(self.energy_bar)

        self.main_layout.addLayout(header_vbox)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self.container = QWidget()
        self.container.setObjectName("GaleriaContainer")
        self.grid = QGridLayout(self.container)
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll, stretch=1)

        # Vista de Lista tipo Excel con columnas ajustables (Issue #58)
        self.list_table = QTableWidget()
        self.list_table.setColumnCount(10)
        self.list_table.setHorizontalHeaderLabels([
            t("#Dex"), t("Nombre"), t("Tipo"), t("Generación"),
            t("Rareza"), t("Edición"), t("Etapa"), t("Idioma"),
            f"{t('Precio')} ({get_active_currency()})", t("Copias")
        ])
        self.list_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.list_table.setAlternatingRowColors(True)
        self.list_table.setShowGrid(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.list_table.horizontalHeader().setStretchLastSection(True)
        self.list_table.setColumnWidth(0, 58)
        self.list_table.setColumnWidth(1, 200)
        self.list_table.setColumnWidth(2, 85)
        self.list_table.setColumnWidth(3, 95)
        self.list_table.setColumnWidth(4, 120)
        self.list_table.setColumnWidth(5, 145)
        self.list_table.setColumnWidth(6, 85)
        self.list_table.setColumnWidth(7, 60)
        self.list_table.setColumnWidth(8, 90)
        self.list_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #fff6f8;
                color: #3f2730;
                gridline-color: #f3c8d1;
                border: 1.5px solid #f2b8c3;
                border-radius: 10px;
                font-size: 12px;
                selection-background-color: #fde0e7;
                selection-color: #5a2a3a;
            }
            QHeaderView::section {
                background-color: #ffeef2;
                color: #5a2a3a;
                font-weight: 700;
                font-size: 12px;
                padding: 6px 8px;
                border: none;
                border-right: 1px solid #f2b8c3;
                border-bottom: 1.5px solid #f2b8c3;
            }
        """)
        self.list_table.itemSelectionChanged.connect(self._on_list_selection_changed)
        self.list_table.cellDoubleClicked.connect(self._on_list_double_clicked)
        self.list_table.setVisible(False)
        self.main_layout.addWidget(self.list_table, stretch=1)

        # Paginación
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

        # Sonido
        self.sonido_pagina = QSoundEffect()
        self.sonido_pagina.setSource(QUrl.fromLocalFile(os.path.join(SOUNDS_DIR, "paginas.wav")))
        self.sonido_pagina.setVolume(0.5)

        self.cargar_filtros()
        self.actualizar_total_cartas()
        self.actualizar_galeria()
        language_manager.language_changed.connect(self.retranslate_ui)

    def cargar_filtros(self):
        curr_lang = language_manager.current_language
        for columna, combo in self.filtros.items():
            field_name = getattr(columna, "key", str(columna))
            prev_val = self._get_filter_value(combo)
            combo.blockSignals(True)
            while combo.count() > 1:
                combo.removeItem(1)
            valores = self.session.query(columna).filter(columna != None).distinct().all()
            for raw_val in sort_filter_values(field_name, valores):
                display_txt = format_filter_option_label(field_name, raw_val, curr_lang)
                combo.addItem(display_txt, raw_val)
            if prev_val:
                idx = combo.findData(prev_val)
                if idx < 0:
                    idx = combo.findText(prev_val, Qt.MatchFlag.MatchFixedString)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def on_text_changed(self):
        self.timer_busqueda.start(300)

    def reset_page_and_actualizar(self):
        self.current_page = 0
        self.actualizar_total_cartas()
        self.actualizar_con_transicion()

    def _get_filter_value(self, combo):
        if combo.currentIndex() <= 0:
            return None
        data = combo.currentData()
        if data is not None:
            return str(data).strip() or None
        return combo.currentText().strip() or None

    def _build_language_query(self):
        selected_lang = self.combo_idioma.currentData()
        if selected_lang:
            return self.session.query(Cartas).filter(Cartas.idioma == selected_lang)
        
        curr_lang = language_manager.current_language
        q = self.session.query(Cartas).filter(Cartas.idioma == curr_lang)
        if q.count() == 0:
            q = self.session.query(Cartas)
        return q

    def actualizar_total_cartas(self):
        query = self._build_language_query()

        if text := self.buscador.text().strip().lower():
            query = query.filter(Cartas.nombre.ilike(f"%{text}%"))

        for col, combo in self.filtros.items():
            if val := self._get_filter_value(combo):
                query = query.filter(col == val)

        if getattr(self, "_active_generation", None):
            query = query.filter(Cartas.generacion.ilike(f"%{self._active_generation}%"))

        self.total_cartas = query.count()

    def actualizar_con_transicion(self):
        self.actualizar_galeria()
        self.container.update()
        self.scroll.viewport().update()

    def actualizar_galeria(self):
        # Limpiar sincrónicamente la estructura de la cuadrícula
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self.labels_por_id.clear()
        self.card_widgets_por_key.clear()

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

        query = self._build_language_query()

        if text := self.buscador.text().strip().lower():
            query = query.filter(Cartas.nombre.ilike(f"%{text}%"))

        for col, combo in self.filtros.items():
            if val := self._get_filter_value(combo):
                query = query.filter(col == val)

        if getattr(self, "_active_generation", None):
            query = query.filter(Cartas.generacion.ilike(f"%{self._active_generation}%"))

        # Issue #55: Ordenar por número de Pokédex cuando hay filtro de Generación o Energía/Tipo
        has_gen_filter = bool(getattr(self, "_active_generation", None))
        has_type_filter = bool(self._get_filter_value(self.filtros[Cartas.type]))
        if has_gen_filter or has_type_filter:
            query = query.order_by(
                Cartas.pokedex_id.is_(None),
                Cartas.pokedex_id.asc(),
                Cartas.nombre.asc(),
            )

        cartas = query.limit(self.CARTAS_POR_PAGINA)\
                      .offset(self.current_page * self.CARTAS_POR_PAGINA)\
                      .all()

        self._current_cards_map.clear()
        for c in cartas:
            c_lang = c.idioma or language_manager.current_language
            self._current_cards_map[f"{c.id_api}:{c_lang}"] = c

        if self._view_mode == "list":
            self._populate_list_table(cartas)
            total_paginas = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
            self.lbl_pagina.setText(f"{t('Página')} {self.current_page+1} {t('de')} {total_paginas}")
            self.btn_anterior.setEnabled(self.current_page > 0)
            self.btn_siguiente.setEnabled(self.current_page < total_paginas - 1)
            return

        row, col = 0, 0
        for carta in cartas:
            card_lang = carta.idioma or language_manager.current_language
            card_key = f"{carta.id_api}:{card_lang}"
            nombre_archivo = carta.nombre.lower().replace(' ', '_')
            needs_download = False

            # 1. Intentar cargar versión .webp exacta en el idioma de la carta
            pix = get_webp_pixmap(carta.id_api, carta.nombre, card_lang, size=size, allow_lang_fallback=False)

            # 2. Si no existe en ese idioma exacto, buscar fallback local y encolar descarga .webp en su idioma
            if not pix:
                needs_download = True
                pix = get_webp_pixmap(carta.id_api, carta.nombre, card_lang, size=size, allow_lang_fallback=True)
            if not pix:
                pix = get_pixmap_from_zip(nombre_archivo, size=size, id_api=carta.id_api)
            if not pix:
                ruta_alt = os.path.join(self.path_imagenes, f"{nombre_archivo}_{carta.id_api}.webp")
                if os.path.exists(ruta_alt):
                    pix = QPixmap(ruta_alt).scaled(size[0], size[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            # 3. Nunca ocultar la carta: mostrar placeholder limpio mientras se descarga el .webp
            if not pix or pix.isNull():
                pix = get_card_placeholder_pixmap(size, carta.nombre)
                needs_download = True

            card_widget = CardItemWidget(carta, pix, size)
            card_widget.image_label.card_key = card_key
            card_widget.image_label.clicked.connect(self.seleccionar_carta)
            card_widget.copy_qty_changed.connect(self._on_card_copy_qty_changed)

            if card_key in self.cartas_seleccionadas:
                card_widget.image_label.setStyleSheet("border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);")
                qty = self.cantidades_seleccionadas.setdefault(card_key, 1)
                card_widget.set_selection_stepper(True, qty)
            else:
                card_widget.image_label.setStyleSheet("border: none; background-color: transparent;")
                card_widget.set_selection_stepper(False, 1)

            self.labels_por_id.setdefault(card_key, []).append(card_widget.image_label)
            self.card_widgets_por_key.setdefault(card_key, []).append(card_widget)
            self.grid.addWidget(card_widget, row, col)

            if needs_download:
                self.image_loader.request_image(
                    card_key,
                    carta.id_api,
                    carta.nombre,
                    idioma=card_lang,
                    set_id=getattr(carta, "set_id", None),
                    number=getattr(carta, "number", None),
                )

            col += 1
            if col == cols_per_row:
                row, col = row + 1, 0

        total_paginas = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        self.lbl_pagina.setText(f"{t('Página')} {self.current_page+1} {t('de')} {total_paginas}")
        self.btn_anterior.setEnabled(self.current_page > 0)
        self.btn_siguiente.setEnabled(self.current_page < total_paginas - 1)

    def _on_energy_pill_selected(self, type_val):
        """Sincroniza el QComboBox de Tipo cuando se hace clic en una ficha visual de energía."""
        combo = self.filtros.get(Cartas.type)
        if not combo:
            return
        combo.blockSignals(True)
        if not type_val:
            combo.setCurrentIndex(0)
        else:
            idx = combo.findData(type_val)
            if idx < 0:
                idx = combo.findText(type_val, Qt.MatchFlag.MatchFixedString)
            if idx < 0 and type_val == "Lightning":
                idx = combo.findData("Electric")
                if idx < 0:
                    idx = combo.findText("Electric", Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        self.reset_page_and_actualizar()

    def _on_generation_pill_selected(self, gen_val):
        """Aplica el filtro rápido por Generación Pokémon (Issue #54)."""
        self._active_generation = gen_val or None
        self.reset_page_and_actualizar()

    def set_view_mode(self, mode: str):
        """Alterna entre vista de cuadrícula con imágenes ('grid') y vista de tabla ('list') (Issue #58)."""
        if mode not in ("grid", "list") or self._view_mode == mode:
            return
        self._view_mode = mode
        is_list = mode == "list"
        self.scroll.setVisible(not is_list)
        self.list_table.setVisible(is_list)
        self.actualizar_galeria()

    def _populate_list_table(self, cartas):
        self.list_table.blockSignals(True)
        self.list_table.setHorizontalHeaderItem(
            8, QTableWidgetItem(f"{t('Precio')} ({get_active_currency()})")
        )
        self.list_table.setRowCount(len(cartas))
        for r_idx, carta in enumerate(cartas):
            card_lang = carta.idioma or language_manager.current_language
            card_key = f"{carta.id_api}:{card_lang}"
            dex_txt = f"#{carta.pokedex_id:04d}" if getattr(carta, "pokedex_id", None) else "-"
            price_val = format_price(float(carta.price), "USD", include_code=False) if carta.price else "-"
            vals = [
                dex_txt,
                carta.nombre or "",
                carta.type or "-",
                getattr(carta, "generacion", None) or "-",
                carta.rarity or "-",
                carta.edition or carta.set_name or "-",
                carta.stage or "-",
                (card_lang or "").upper(),
                price_val,
            ]
            for c_idx, txt in enumerate(vals):
                item = QTableWidgetItem(txt)
                if c_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, card_key)
                if c_idx in (0, 7, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.list_table.setItem(r_idx, c_idx, item)

            is_sel = card_key in self.cartas_seleccionadas
            spin = QSpinBox(self.list_table)
            spin.setRange(1, 99)
            spin.setValue(self.cantidades_seleccionadas.get(card_key, 1) if is_sel else 1)
            spin.setEnabled(is_sel)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spin.valueChanged.connect(lambda val, ck=card_key: self._on_card_copy_qty_changed(ck, val))
            self.list_table.setCellWidget(r_idx, 9, spin)

            if is_sel:
                self.list_table.selectRow(r_idx)
        self.list_table.blockSignals(False)

    def _on_list_selection_changed(self):
        page_keys = {
            self.list_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            for r in range(self.list_table.rowCount())
            if self.list_table.item(r, 0)
        }
        selected_rows = {idx.row() for idx in self.list_table.selectedIndexes()}
        selected_page_keys = {
            self.list_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            for r in selected_rows
            if self.list_table.item(r, 0)
        }
        self.cartas_seleccionadas -= page_keys
        self.cartas_seleccionadas |= selected_page_keys
        for k in page_keys - selected_page_keys:
            self.cantidades_seleccionadas.pop(k, None)
        for k in selected_page_keys:
            self.cantidades_seleccionadas.setdefault(k, 1)
        for r in range(self.list_table.rowCount()):
            it = self.list_table.item(r, 0)
            spin = self.list_table.cellWidget(r, 9)
            if it and spin is not None:
                ck = it.data(Qt.ItemDataRole.UserRole)
                active = ck in self.cartas_seleccionadas
                spin.blockSignals(True)
                spin.setEnabled(active)
                if not active:
                    spin.setValue(1)
                else:
                    spin.setValue(self.cantidades_seleccionadas.get(ck, 1))
                spin.blockSignals(False)

    def _on_list_double_clicked(self, row: int, _col: int):
        item = self.list_table.item(row, 0)
        if not item:
            return
        card_key = item.data(Qt.ItemDataRole.UserRole)
        carta = self._current_cards_map.get(card_key)
        if not carta:
            return
        c_lang = carta.idioma or language_manager.current_language
        pix = get_webp_pixmap(carta.id_api, carta.nombre, c_lang, size=(360, 500), allow_lang_fallback=True)
        if not pix or pix.isNull():
            pix = get_card_placeholder_pixmap((360, 500), carta.nombre)
        overlay = CardZoomOverlay(carta, pix, self.window())
        overlay.show()

    def _sync_energy_bar_from_combo(self):
        """Sincroniza la barra visual de energías cuando cambia el QComboBox de Tipo."""
        combo = self.filtros.get(Cartas.type)
        if combo and hasattr(self, "energy_bar"):
            self.energy_bar.set_active_type(self._get_filter_value(combo))

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

    def retranslate_ui(self):
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        self.btn_sync_precios.setText(t("Actualizar Precios"))
        if hasattr(self, 'btn_seleccionar_todo'):
            self.btn_seleccionar_todo.setText(t("Seleccionar Todo"))
        self.btn_anterior.setText(t("Anterior"))
        self.btn_siguiente.setText(t("Siguiente"))
        total_paginas = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        self.lbl_pagina.setText(f"{t('Página')} {self.current_page+1} {t('de')} {total_paginas}")
        
        curr_lang = language_manager.current_language
        campos_labels = [
            ("Tipo", Cartas.type),
            ("Etapa", Cartas.stage),
            ("Rule Box", Cartas.especial_type),
            ("Entrenador", Cartas.trainer),
            ("Rareza", Cartas.rarity),
            ("Edición", Cartas.edition),
        ]
        for etiqueta, columna in campos_labels:
            if columna in self.filtros:
                cb = self.filtros[columna]
                field_name = getattr(columna, "key", str(columna))
                selected_data = self._get_filter_value(cb)
                cb.blockSignals(True)
                if cb.count() > 0:
                    cb.setItemText(0, f"{t(etiqueta)}: {t('Todos')}")
                for i in range(1, cb.count()):
                    raw_val = cb.itemData(i)
                    if raw_val is not None:
                        cb.setItemText(i, format_filter_option_label(field_name, raw_val, curr_lang))
                if selected_data is not None:
                    idx = cb.findData(selected_data)
                    if idx < 0:
                        idx = cb.findText(selected_data, Qt.MatchFlag.MatchFixedString)
                    cb.setCurrentIndex(idx if idx >= 0 else 0)
                cb.blockSignals(False)

        if hasattr(self, "combo_idioma") and self.combo_idioma.count() > 0:
            self.combo_idioma.setItemText(0, f"{t('Idioma')}: {t('Todos')}")
        if hasattr(self, "list_table"):
            self.list_table.setHorizontalHeaderItem(
                8, QTableWidgetItem(f"{t('Precio')} ({get_active_currency()})")
            )

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
        total_paginas = max(1, (self.total_cartas + self.CARTAS_POR_PAGINA - 1) // self.CARTAS_POR_PAGINA)
        if self.current_page < total_paginas - 1:
            self.current_page += 1
            self.actualizar_con_transicion()
            from MyQtApp.config import load_settings
            settings = load_settings()
            vol = (settings.get("volumen_sonido", 80) / 100.0) * 0.5
            self.sonido_pagina.setVolume(vol)
            self.sonido_pagina.play()

    def _on_card_copy_qty_changed(self, card_key: str, qty: int):
        qty_clean = max(1, min(99, int(qty or 1)))
        self.cantidades_seleccionadas[card_key] = qty_clean
        for cw in self.card_widgets_por_key.get(card_key, []):
            try:
                cw.set_selection_stepper(card_key in self.cartas_seleccionadas, qty_clean)
            except RuntimeError:
                pass

    def _sync_steppers_for_key(self, card_key: str):
        is_sel = card_key in self.cartas_seleccionadas
        qty = self.cantidades_seleccionadas.get(card_key, 1) if is_sel else 1
        for cw in self.card_widgets_por_key.get(card_key, []):
            try:
                cw.set_selection_stepper(is_sel, qty)
            except RuntimeError:
                pass

    def seleccionar_carta(self, label_obj, id_carta):
        card_key = getattr(label_obj, 'card_key', None) or id_carta

        if card_key in self.cartas_seleccionadas:
            self.cartas_seleccionadas.remove(card_key)
            self.cantidades_seleccionadas.pop(card_key, None)
            style = "border: none; background-color: transparent;"
        else:
            self.cartas_seleccionadas.add(card_key)
            self.cantidades_seleccionadas.setdefault(card_key, 1)
            style = "border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);"

        labels = self.labels_por_id.get(card_key, [])
        if isinstance(labels, list):
            if label_obj and label_obj not in labels:
                labels.append(label_obj)
            for lbl in labels:
                lbl.setStyleSheet(style)
        elif label_obj:
            label_obj.setStyleSheet(style)
        self._sync_steppers_for_key(card_key)

    def toggle_seleccionar_pagina(self):
        """Selecciona o deselecciona todas las cartas actualmente desplegadas en la página."""
        if self._view_mode == "list":
            page_keys = {
                self.list_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                for r in range(self.list_table.rowCount())
                if self.list_table.item(r, 0)
            }
            if not page_keys:
                return
            all_selected = page_keys.issubset(self.cartas_seleccionadas)
            self.list_table.blockSignals(True)
            if all_selected:
                self.cartas_seleccionadas -= page_keys
                for key in page_keys:
                    self.cantidades_seleccionadas.pop(key, None)
                self.list_table.clearSelection()
            else:
                self.cartas_seleccionadas |= page_keys
                for key in page_keys:
                    self.cantidades_seleccionadas.setdefault(key, 1)
                self.list_table.selectAll()
            for r in range(self.list_table.rowCount()):
                it = self.list_table.item(r, 0)
                spin = self.list_table.cellWidget(r, 9)
                if it and spin is not None:
                    ck = it.data(Qt.ItemDataRole.UserRole)
                    active = ck in self.cartas_seleccionadas
                    spin.blockSignals(True)
                    spin.setEnabled(active)
                    spin.setValue(self.cantidades_seleccionadas.get(ck, 1) if active else 1)
                    spin.blockSignals(False)
            self.list_table.blockSignals(False)
            return

        if not self.labels_por_id:
            return

        # Comprobar si todas las cartas de la página ya están seleccionadas
        page_keys = set(self.labels_por_id.keys())
        all_selected = page_keys.issubset(self.cartas_seleccionadas)

        if all_selected:
            # Deseleccionar todas las cartas de esta página
            for key in page_keys:
                self.cartas_seleccionadas.discard(key)
                self.cantidades_seleccionadas.pop(key, None)
                for lbl in self.labels_por_id.get(key, []):
                    lbl.setStyleSheet("border: none; background-color: transparent;")
                self._sync_steppers_for_key(key)
        else:
            # Seleccionar todas las cartas de esta página
            for key in page_keys:
                self.cartas_seleccionadas.add(key)
                self.cantidades_seleccionadas.setdefault(key, 1)
                for lbl in self.labels_por_id.get(key, []):
                    lbl.setStyleSheet("border: 2.5px solid #00cccc; border-radius: 6px; background-color: rgba(0, 255, 200, 0.25);")
                self._sync_steppers_for_key(key)

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
                qty = max(1, int(self.cantidades_seleccionadas.get(key, 1) or 1))
                resultado.append({"id_api": c[0], "nombre": c[1], "idioma": c[2], "cantidad": qty})

        return resultado

    def limpiar_seleccion(self):
        self.cartas_seleccionadas.clear()
        self.cantidades_seleccionadas.clear()
        if hasattr(self, "list_table"):
            self.list_table.blockSignals(True)
            self.list_table.clearSelection()
            for r in range(self.list_table.rowCount()):
                spin = self.list_table.cellWidget(r, 9)
                if spin is not None:
                    spin.blockSignals(True)
                    spin.setEnabled(False)
                    spin.setValue(1)
                    spin.blockSignals(False)
            self.list_table.blockSignals(False)
        for key, labels in self.labels_por_id.items():
            if isinstance(labels, list):
                for lbl in labels:
                    lbl.setStyleSheet("border: none; background-color: transparent;")
            elif labels:
                labels.setStyleSheet("border: none; background-color: transparent;")
            self._sync_steppers_for_key(key)

    def iniciar_sincronizacion_precios(self):
        from MyQtApp.app.price_updater import PriceUpdaterThread

        # Obtener IDs de las cartas actualmente desplegadas en la galería
        id_list = list(self.labels_por_id.keys())
        if not id_list:
            return

        self.btn_sync_precios.setEnabled(False)
        self.btn_sync_precios.setText("🔄 Conectando...")

        self.price_thread = PriceUpdaterThread(id_list, parent=self)
        self.price_thread.progress.connect(self.on_precio_progreso)
        self.price_thread.finished.connect(self.on_precio_finalizado)
        self.price_thread.start()

    def on_precio_progreso(self, actual, total):
        self.btn_sync_precios.setText(f"Cargando ({actual}/{total})...")

    def on_precio_finalizado(self, actualizadas):
        self.session.expire_all()
        self.btn_sync_precios.setEnabled(True)
        self.btn_sync_precios.setText(t("Actualizar Precios"))
        self.actualizar_galeria()
