"""Panel lateral de colección e inventario para arrastrar cartas al Binder."""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QLineEdit, QMenu,
)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QPalette
from sqlalchemy import and_, func

from MyQtApp.config import IMAGES_DIR
from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas, UsuarioCarta
from MyQtApp.app.getImgs import get_pixmap_from_zip, get_webp_pixmap, get_card_placeholder_pixmap
from MyQtApp.app.db_services import obtener_categorias_usuario
from MyQtApp.i18n import t
from MyQtApp.ui.CardWidget import VariantBadgeButton, LanguageBadgeLabel, InfoIconLabel
from MyQtApp.ui.binder.widgets import DraggableCardLabel
from MyQtApp.ui.pixmap_cache import get_cached_pixmap
from MyQtApp.ui.toast import show_toast


class InventorySidebar(QWidget):
    card_removed_from_binder = pyqtSignal(str)  # emits source_slot (e.g. "0_3")

    def __init__(self, usuario, binder_view=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.binder_view = binder_view
        self.coleccion_activa = None  # None = Todas las colecciones
        self.orden_activo = None      # None | "rarity" | "type" | "idioma" | "pokedex" | "cantidad"
        self._card_items_by_key: dict[tuple[str, str], list[dict]] = {}
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

        # 1. Buscador
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(t("Buscar carta por nombre..."))
        self.buscador.setProperty("class", "SearchInput")
        self.timer_busqueda = QTimer()
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(300)
        self.timer_busqueda.timeout.connect(self.load_cards)
        self.buscador.textChanged.connect(lambda: self.timer_busqueda.start())
        layout.addWidget(self.buscador)

        # 2. Botones "Colección" y "Ordenar" (Issue #42)
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

    def _mostrar_menu_coleccion(self):
        """Despliega menú para filtrar por una colección creada en específico (Issue #42)."""
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
        """Despliega menú para ordenar las cartas por Rareza, Energía, Idioma, Pokedex y Cantidad."""
        menu = self._create_styled_popup_menu()

        opciones = [
            (t("Rareza"), "rarity"),
            (t("Energía"), "type"),
            (t("Idioma"), "idioma"),
            ("Pokedex", "pokedex"),
            ("Cantidad", "cantidad"),
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

    @staticmethod
    def _apply_copies_badge_style(copies_badge: QLabel, rem_val: int, owned_val: int, card_w: int):
        copies_badge.setText(f"{rem_val}/{owned_val}")
        badge_bg = "rgba(5, 150, 105, 0.92)" if rem_val > 0 else "rgba(220, 38, 38, 0.94)"
        badge_border = "#a7f3d0" if rem_val > 0 else "#fecaca"
        copies_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {badge_bg};
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                border: 1.2px solid {badge_border};
                border-radius: 8px;
                padding: 1px 6px;
            }}
        """)
        copies_badge.adjustSize()
        cx = max(24, (card_w - copies_badge.width()) // 2)
        copies_badge.move(cx, 3)

    def _create_single_card_widget(self, carta, variante_db="Normal", owned_qty: int = 1, remaining_qty: int = 1):
        """Crea el widget de carta individual con su idioma, variante y contador de copias disponibles (Issues #24 y #43)."""
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
                pixmap = get_cached_pixmap(ruta_alt, card_size[0], card_size[1], keep_aspect=True, smooth=True)
        if not pixmap or pixmap.isNull():
            pixmap = get_card_placeholder_pixmap(card_size, nombre)

        owned_val = max(1, int(owned_qty or 1))
        rem_val = max(0, int(remaining_qty if remaining_qty is not None else owned_val))

        card_lbl = DraggableCardLabel(id_api, nombre_archivo, pixmap)
        card_lbl.setFixedSize(card_size[0], card_size[1])
        card_lbl.idioma = card_lang
        card_lbl.variante = variante
        card_lbl.owned_copies = owned_val
        card_lbl.remaining_copies = rem_val

        dim_overlay = QLabel(card_lbl)
        dim_overlay.setGeometry(0, 0, card_size[0], card_size[1])
        dim_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        dim_overlay.setStyleSheet("background-color: rgba(15, 23, 42, 0.48); border-radius: 5px;")
        dim_overlay.setVisible(rem_val <= 0)
        if rem_val <= 0:
            dim_overlay.raise_()

        # Botón vertical de variante (arriba a la izquierda)
        variant_badge = VariantBadgeButton(id_api, variante, card_lbl)
        variant_badge.move(3, 3)
        variant_badge.raise_()

        def _on_var_changed(_cid, nueva_var):
            card_lbl.variante = nueva_var
            self._actualizar_variante_bd(id_api, card_lang, nueva_var)

        variant_badge.variant_changed.connect(_on_var_changed)

        # Insignia superior central de copias disponibles / totales (Issue #24)
        copies_badge = QLabel(card_lbl)
        copies_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        copies_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_copies_badge_style(copies_badge, rem_val, owned_val, card_size[0])
        copies_badge.raise_()

        # Botón de información (arriba a la derecha)
        info_btn = InfoIconLabel(carta, card_lbl)
        info_btn.move(card_size[0] - 26, 3)
        info_btn.raise_()

        # Insignia distintiva de idioma (abajo a la izquierda)
        lang_badge = LanguageBadgeLabel(card_lang, card_lbl)
        badge_h = lang_badge.height()
        lang_badge.move(3, card_size[1] - badge_h - 3)
        lang_badge.raise_()

        # Indicador geométrico de rareza (abajo a la derecha)
        from MyQtApp.ui.FilterVisualBar import RaritySymbolBadge
        rarity_badge = RaritySymbolBadge(getattr(carta, "rarity", None), card_lbl)
        rarity_badge.move(card_size[0] - rarity_badge.width() - 3, card_size[1] - rarity_badge.height() - 3)
        rarity_badge.raise_()

        type_str = carta.type or "N/A"
        rarity_str = carta.rarity or "N/A"
        price_val = f"${carta.price:.2f}" if (carta.price and carta.price > 0) else "N/A"
        card_lbl.setToolTip(
            f"<b>{nombre}</b><br/>ID: {id_api}<br/>Idioma: {card_lang.upper()}<br/>"
            f"Copias disponibles: {rem_val} / {owned_val}<br/>"
            f"Tipo: {type_str}<br/>Rareza: {rarity_str}<br/>Precio: {price_val} USD"
        )

        self._card_items_by_key.setdefault((str(id_api), str(card_lang)), []).append({
            "widget": card_lbl,
            "copies_badge": copies_badge,
            "dim_overlay": dim_overlay,
            "variant_badge": variant_badge,
            "info_btn": info_btn,
            "lang_badge": lang_badge,
            "rarity_badge": rarity_badge,
            "owned_val": owned_val,
            "nombre": nombre,
            "type_str": type_str,
            "rarity_str": rarity_str,
            "price_val": price_val,
            "card_w": card_size[0],
        })
        return card_lbl

    def update_usage_badges(self):
        """
        Actualiza in-place las insignias de copias restantes y estado draggable de todas las
        cartas ya renderizadas sin destruir widgets ni consultar la BD.
        """
        if not self._card_items_by_key:
            self.load_cards()
            return

        exact_used, no_lang_used = ({}, {})
        if self.binder_view and hasattr(self.binder_view, "get_used_card_counts_across_all_binders"):
            exact_used, no_lang_used = self.binder_view.get_used_card_counts_across_all_binders()

        for (id_api, c_lang), entries in self._card_items_by_key.items():
            used_val = exact_used.get((id_api, c_lang), 0) + no_lang_used.get(id_api, 0)
            for meta in entries:
                card_lbl = meta["widget"]
                owned_val = meta["owned_val"]
                rem_val = max(0, owned_val - used_val)
                should_be_visible = rem_val > 0
                if card_lbl.remaining_copies == rem_val and (not card_lbl.isHidden()) == should_be_visible:
                    continue

                card_lbl.remaining_copies = rem_val
                card_lbl.setVisible(should_be_visible)
                dim_overlay = meta["dim_overlay"]
                dim_overlay.setVisible(rem_val <= 0)
                if rem_val <= 0:
                    dim_overlay.raise_()
                    meta["variant_badge"].raise_()
                    meta["info_btn"].raise_()
                    meta["lang_badge"].raise_()
                    meta["rarity_badge"].raise_()

                copies_badge = meta["copies_badge"]
                self._apply_copies_badge_style(copies_badge, rem_val, owned_val, meta["card_w"])
                copies_badge.raise_()

                card_lbl.setToolTip(
                    f"<b>{meta['nombre']}</b><br/>ID: {id_api}<br/>Idioma: {c_lang.upper()}<br/>"
                    f"Copias disponibles: {rem_val} / {owned_val}<br/>"
                    f"Tipo: {meta['type_str']}<br/>Rareza: {meta['rarity_str']}<br/>Precio: {meta['price_val']} USD"
                )

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
            if self.coleccion_activa:
                cats = obtener_categorias_usuario(self.usuario)
                if self.coleccion_activa not in cats:
                    self.coleccion_activa = None

            query = (
                session.query(Cartas, UsuarioCarta.variante, UsuarioCarta.cantidad)
                .join(
                    UsuarioCarta,
                    and_(
                        Cartas.id_api == UsuarioCarta.carta_id,
                        func.coalesce(Cartas.idioma, "es") == func.coalesce(UsuarioCarta.idioma, "es"),
                    ),
                )
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

            # 3. Ordenar por Rareza, Energía, Idioma, Pokedex o Cantidad si está activo
            if self.orden_activo == "rarity":
                rows.sort(key=lambda r: ((r[0].rarity or "zzz").lower(), (r[0].nombre or "").lower()))
            elif self.orden_activo == "type":
                rows.sort(key=lambda r: ((r[0].type or "zzz").lower(), (r[0].nombre or "").lower()))
            elif self.orden_activo == "idioma":
                rows.sort(key=lambda r: ((r[0].idioma or "es").lower(), (r[0].nombre or "").lower()))
            elif self.orden_activo == "pokedex":
                rows.sort(
                    key=lambda r: (
                        getattr(r[0], "pokedex_id", None) is None,
                        getattr(r[0], "pokedex_id", None) if getattr(r[0], "pokedex_id", None) is not None else 999999,
                        (r[0].nombre or "").lower(),
                    )
                )
            elif self.orden_activo == "cantidad":
                rows.sort(key=lambda r: (-(max(1, int(r[2] or 1))), (r[0].nombre or "").lower()))

            exact_used, no_lang_used = ({}, {})
            if self.binder_view and hasattr(self.binder_view, "get_used_card_counts_across_all_binders"):
                exact_used, no_lang_used = self.binder_view.get_used_card_counts_across_all_binders()

            # Limpiar área de cartas e índice in-place
            self._card_items_by_key.clear()
            for i in reversed(range(self.cards_layout.count())):
                item = self.cards_layout.itemAt(i)
                if item and item.widget():
                    item.widget().deleteLater()

            for carta, variante_db, cantidad_db in rows:
                c_lang = getattr(carta, "idioma", None) or "es"
                owned_val = max(1, int(cantidad_db or 1))
                used_val = exact_used.get((carta.id_api, c_lang), 0) + no_lang_used.get(carta.id_api, 0)
                rem_val = max(0, owned_val - used_val)
                item_widget = self._create_single_card_widget(
                    carta, variante_db, owned_qty=owned_val, remaining_qty=rem_val
                )
                if item_widget:
                    self.cards_layout.addWidget(item_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
                    item_widget.setVisible(rem_val > 0)
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
