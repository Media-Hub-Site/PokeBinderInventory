import random
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QMessageBox, QStackedWidget, QSpacerItem, QSizePolicy, QGraphicsOpacityEffect,
    QDialog, QComboBox
)
from PyQt6.QtCore import Qt, QUrl, QPropertyAnimation, QVariantAnimation, QEasingCurve, QPoint, QByteArray, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter
from PyQt6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput
import os

from MyQtApp.config import SOUNDS_DIR, IMAGES_DIR, ICONS_DIR, load_settings, get_music_track_path
from MyQtApp.app.db_services import agregar_cartas_usuario, eliminar_cartas_usuario

from .Galeria import GaleriaCartas
from .Inventario import GaleriaCartasInventario
from .Ajustes import AjustesWidget
from .Binder import BinderView
from .PrintView import PrintView
from .Mazos import MazosView
from MyQtApp.i18n import t, language_manager


class _SectionCrossfadeOverlay(QWidget):
    """
    Overlay liviano de cross-fade entre secciones usando QPainter (sin QGraphicsOpacityEffect
    sobre el subárbol de widgets), evitando conflictos con overlays 3D, QTableWidget y QScrollArea.
    """
    finished = pyqtSignal()

    def __init__(self, parent: QWidget, old_pixmap: QPixmap, duration_ms: int = 170):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._old_pixmap = old_pixmap
        self._opacity = 1.0
        self._done = False

        self.show()
        self.raise_()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(max(60, int(duration_ms)))
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_tick)
        self._anim.finished.connect(self._on_done)
        self._anim.start()

    def _on_tick(self, val):
        if self._done:
            return
        self._opacity = max(0.0, min(1.0, float(val)))
        self.update()

    def _on_done(self):
        if self._done:
            return
        self._done = True
        self.finished.emit()
        self.hide()
        self.deleteLater()

    def cancel(self):
        if self._done:
            return
        self._done = True
        try:
            if self._anim is not None:
                self._anim.blockSignals(True)
                self._anim.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        if self._old_pixmap.isNull() or self._opacity <= 0.01:
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._old_pixmap)


class BotonConSonido(QPushButton):
    def __init__(self, texto, parent=None):
        super().__init__(texto, parent)

        self.hover_sound = QSoundEffect()
        self.hover_sound.setSource(QUrl.fromLocalFile(os.path.join(SOUNDS_DIR, "hover.wav")))

        self.click_sound = QSoundEffect()
        self.click_sound.setSource(QUrl.fromLocalFile(os.path.join(SOUNDS_DIR, "click.wav")))

        self.setMouseTracking(True)

    def enterEvent(self, event):
        settings = load_settings()
        vol = (settings.get("volumen_sonido", 80) / 100.0) * 0.3
        self.hover_sound.setVolume(vol)
        self.hover_sound.play()
        super().enterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            settings = load_settings()
            vol = (settings.get("volumen_sonido", 80) / 100.0) * 0.8
            self.click_sound.setVolume(vol)
            self.click_sound.play()
        super().mousePressEvent(event)


class VariantLegendSidebarWidget(QWidget):
    """Panel vertical compacto en la columna lateral izquierda que muestra los colores de las Variantes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)

        header = QLabel(t("Variantes"), self)
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #38bdf8; border: none; background: transparent;")
        layout.addWidget(header)

        from PyQt6.QtGui import QPalette, QColor
        black_pal = QPalette()
        black_pal.setColor(QPalette.ColorRole.WindowText, QColor("#000000"))
        black_pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))

        from MyQtApp.config import VARIANT_COLOR_MAP
        for key, info in VARIANT_COLOR_MAP.items():
            item_row = QHBoxLayout()
            item_row.setContentsMargins(0, 0, 0, 0)
            item_row.setSpacing(6)

            color_badge = QLabel(self)
            color_badge.setFixedSize(10, 12)
            color_badge.setStyleSheet(f"background-color: {info['color']}; border: 1px solid {info['border']}; border-radius: 3px;")

            desc = QLabel(f"{info['name']}", self)
            desc.setPalette(black_pal)
            desc.setStyleSheet("font-size: 10px; color: #000000; font-weight: 600; border: none; background: transparent;")

            item_row.addWidget(color_badge)
            item_row.addWidget(desc)
            item_row.addStretch()
            layout.addLayout(item_row)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.78);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 10px;
            }
        """)


class MainWindow(QWidget):
    logout_requested = pyqtSignal()

    def __init__(self, usuario):
        super().__init__()
        self.settings = load_settings()
        self.animaciones_activas = self.settings.get("animaciones", True)
        self.usuario = usuario
        self.setObjectName("MainBackground")
        self.setWindowTitle(f"{t('Menú Principal')} - {t('Usuario:')} {usuario.capitalize()}")
        self.setGeometry(550, 250, 1240, 920)

        main_layout = QHBoxLayout(self)

        # Barra lateral
        nav_layout = QVBoxLayout()

        iconoBuscar = QIcon(os.path.join(ICONS_DIR, "buscar.png"))
        iconoCarpeta = QIcon(os.path.join(ICONS_DIR, "carpeta.png"))
        iconoColeccion = QIcon(os.path.join(ICONS_DIR, "coleccion.png"))

        self.btn_buscar = BotonConSonido(iconoBuscar, t("Buscar"))
        self.btn_ver_carpeta = BotonConSonido(iconoCarpeta, t("Binder"))
        self.btn_mi_coleccion = BotonConSonido(iconoColeccion, t("Colecciones"))
        self.btn_mazos = BotonConSonido(t("Mazos"))
        self.btn_print = BotonConSonido(t("Print"))
        self.btn_ajustes = BotonConSonido(t("Ajustes"))

        self._nav_buttons = [
            self.btn_buscar,
            self.btn_ver_carpeta,
            self.btn_mi_coleccion,
            self.btn_mazos,
            self.btn_print,
            self.btn_ajustes,
        ]

        for btn in self._nav_buttons:
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "NavButton")
            btn.setProperty("active", False)
            nav_layout.addWidget(btn)

        # Cuadro explicativo de los colores de Variantes (visible en Binder y Colecciones)
        nav_layout.addSpacing(12)
        self.variant_legend_sidebar = VariantLegendSidebarWidget(self)
        sp_legend = self.variant_legend_sidebar.sizePolicy()
        sp_legend.setRetainSizeWhenHidden(True)
        self.variant_legend_sidebar.setSizePolicy(sp_legend)
        nav_layout.addWidget(self.variant_legend_sidebar)

        nav_layout.addStretch()

        self.btn_salir = BotonConSonido(t("Salir"))
        self.btn_salir.setFixedHeight(44)
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salir.setProperty("class", "ExitButton")
        nav_layout.addWidget(self.btn_salir)
        nav_layout.addSpacing(14)


        # Panel lateral (ancho consistente igual al de Colecciones para evitar cambios de margen - Issue #39)
        side_widget = QWidget()
        side_layout_wrapper = QVBoxLayout(side_widget)
        side_layout_wrapper.setContentsMargins(12, 12, 12, 12)
        side_widget.setObjectName('side')
        side_widget.setFixedWidth(176)
        side_layout_wrapper.addLayout(nav_layout)
        side_layout_wrapper.addStretch()

        main_layout.addWidget(side_widget, 0)

        # Páginas con transición
        self.paginas = QStackedWidget()
        self.paginas.addWidget(GaleriaCartas(IMAGES_DIR))                     # índice 0
        self.paginas.addWidget(BinderView(self.usuario))                         # índice 1
        self.paginas.addWidget(GaleriaCartasInventario(IMAGES_DIR, self.usuario))# índice 2
        self.paginas.addWidget(MazosView(self.usuario))                          # índice 3
        self.paginas.addWidget(PrintView(self.usuario))                          # índice 4
        self.paginas.addWidget(AjustesWidget(self.usuario))                     # índice 5

        # Área principal
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 14, 14, 10)
        content_layout.setSpacing(6)
        content_widget.setObjectName('content')

        content_layout.addWidget(self.paginas)

        # Pie inferior (Issue #31: botones de vista a la izquierda, acción contextual a la derecha)
        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        bottom_layout.setSpacing(10)

        view_buttons = QWidget()
        vb_layout = QHBoxLayout(view_buttons)
        vb_layout.setContentsMargins(0, 0, 0, 0)
        vb_layout.setSpacing(8)

        self.btn_view_grid = QPushButton("▦")
        self.btn_view_grid.setFixedSize(48, 48)
        self.btn_view_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_grid.setToolTip(t("Vista en imágenes"))
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setChecked(True)
        self.btn_view_grid.setProperty("class", "ViewGrid")

        self.btn_view_list = QPushButton("≡")
        self.btn_view_list.setFixedSize(48, 48)
        self.btn_view_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_list.setToolTip(t("Vista en lista"))
        self.btn_view_list.setCheckable(True)
        self.btn_view_list.setProperty("class", "ViewList")

        vb_layout.addWidget(self.btn_view_grid)
        vb_layout.addWidget(self.btn_view_list)
        self.view_buttons_container = view_buttons

        bottom_layout.addWidget(view_buttons, 0, Qt.AlignmentFlag.AlignLeft)
        bottom_layout.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # Botones contextuales en la barra inferior (Agregar / Eliminar / Vaciar)
        self.btn_agregar = BotonConSonido(t("Agregar"))
        self.btn_eliminar = BotonConSonido(t("Eliminar"))
        self.btn_vaciar = BotonConSonido(t("Vaciar"))

        for btn in (self.btn_agregar, self.btn_eliminar, self.btn_vaciar):
            btn.setFixedHeight(40)
            btn.setMinimumWidth(160)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "ActionSecondary")
            bottom_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)

        content_layout.addWidget(bottom_bar)

        main_layout.addWidget(content_widget, 4)

        # Conexiones
        self.btn_buscar.clicked.connect(lambda: self.animar_transicion(0))
        self.btn_ver_carpeta.clicked.connect(lambda: self.animar_transicion(1))
        self.btn_mi_coleccion.clicked.connect(lambda: self.animar_transicion(2))
        self.btn_mazos.clicked.connect(lambda: self.animar_transicion(3))
        self.btn_print.clicked.connect(lambda: self.animar_transicion(4))
        self.btn_ajustes.clicked.connect(lambda: self.animar_transicion(5))
        self.btn_salir.clicked.connect(self.confirmar_salir)
        self.btn_agregar.clicked.connect(self.agregar_cartas)
        self.btn_eliminar.clicked.connect(self.eliminar_cartas)
        self.btn_vaciar.clicked.connect(self.vaciar_binder)
        self.btn_view_grid.clicked.connect(lambda: self._cambiar_vista_cartas("grid"))
        self.btn_view_list.clicked.connect(lambda: self._cambiar_vista_cartas("list"))

        ajustes = self.paginas.widget(5)
        ajustes.music_volume_changed.connect(self.actualizar_volumen_musica)
        ajustes.music_track_changed.connect(self.cambiar_musica)
        ajustes.animations_toggled.connect(self.toggle_animaciones)
        ajustes.card_size_changed.connect(self.actualizar_tamano_cartas)
        if hasattr(ajustes, 'logout_requested'):
            ajustes.logout_requested.connect(self.cambiar_cuenta)
        if hasattr(ajustes, 'username_changed'):
            ajustes.username_changed.connect(self.on_username_changed)

        binder_view = self.paginas.widget(1)
        if hasattr(binder_view, 'open_binder_in_print_requested'):
            binder_view.open_binder_in_print_requested.connect(self.abrir_binder_en_print)
        if hasattr(binder_view, 'inside_binder_changed'):
            binder_view.inside_binder_changed.connect(self.on_binder_inside_changed)

        mazos_view = self.paginas.widget(3)
        if hasattr(mazos_view, 'open_deck_in_print_requested'):
            mazos_view.open_deck_in_print_requested.connect(self.abrir_mazo_en_print)

        self.actualizar_botones_secundarios(0)

        # Configurar audio
        pista = self.settings.get("pista_musica", 1)
        ruta_musica = get_music_track_path(pista)

        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(ruta_musica))
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        vol = self.settings.get("volumen_musica", 20) / 100.0
        self.audio_output.setVolume(vol)
        self.player.play()

        language_manager.language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setWindowTitle(f"{t('Menú Principal')} - {t('Usuario:')} {self.usuario.capitalize()}")
        self.btn_buscar.setText(t("Buscar"))
        self.btn_ver_carpeta.setText(t("Binder"))
        self.btn_mi_coleccion.setText(t("Colecciones"))
        self.btn_mazos.setText(t("Mazos"))
        self.btn_print.setText(t("Print"))
        self.btn_ajustes.setText(t("Ajustes"))
        self.btn_agregar.setText(t("Agregar"))
        self.btn_eliminar.setText(t("Eliminar"))
        self.btn_vaciar.setText(t("Vaciar"))
        self.btn_salir.setText(t("Salir"))

    def actualizar_volumen_musica(self, valor):
        self.audio_output.setVolume(valor / 100.0)

    def cambiar_musica(self, pista):
        ruta_musica = get_music_track_path(pista)
        was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.setSource(QUrl.fromLocalFile(ruta_musica))
        if was_playing:
            self.player.play()

    def toggle_animaciones(self, estado):
        self.animaciones_activas = estado

    def abrir_binder_en_print(self, binder_id: str, action: str = "print"):
        """Redirige al usuario a la sección Print y carga automáticamente el binder en la cola."""
        self.animar_transicion(4)
        print_view = self.paginas.widget(4)
        if hasattr(print_view, "cargar_binder_automatico"):
            print_view.cargar_binder_automatico(binder_id)

    def abrir_mazo_en_print(self, mazo_id: int, action: str = "print"):
        """Redirige al usuario a la sección Print y carga automáticamente el mazo en la cola."""
        self.animar_transicion(4)
        print_view = self.paginas.widget(4)
        if hasattr(print_view, "cargar_mazo_automatico"):
            print_view.cargar_mazo_automatico(mazo_id)

    def actualizar_tamano_cartas(self, size):
        try:
            galeria = self.paginas.widget(0)
            if hasattr(galeria, 'actualizar_galeria'):
                galeria.actualizar_galeria()
        except Exception as e:
            print(f"Error actualizando galeria: {e}")
        try:
            inventario = self.paginas.widget(2)
            if hasattr(inventario, 'actualizar_galeria'):
                inventario.actualizar_galeria()
        except Exception as e:
            print(f"Error actualizando inventario: {e}")
        try:
            mazos = self.paginas.widget(3)
            if hasattr(mazos, '_update_zoom_buttons_style'):
                mazos._update_zoom_buttons_style()
            if hasattr(mazos, 'cargar_coleccion_navegador'):
                mazos.cargar_coleccion_navegador()
        except Exception as e:
            print(f"Error actualizando mazos: {e}")

    def _cancel_section_transition(self):
        ov = getattr(self, "_section_fade_overlay", None)
        self._section_fade_overlay = None
        if ov is not None:
            try:
                ov.cancel()
            except Exception:
                pass
        self._current_animations = []

    def animar_transicion(self, nuevo_indice):
        indice_actual = self.paginas.currentIndex()
        if nuevo_indice == indice_actual:
            return

        widget_actual = self.paginas.currentWidget()

        # Cancelar cualquier transición previa y detener animaciones internas activas (Binder / Mazos)
        self._cancel_section_transition()
        if widget_actual is not None and hasattr(widget_actual, "stop_active_animations"):
            try:
                widget_actual.stop_active_animations()
            except Exception:
                pass

        if not self.animaciones_activas or not self.isVisible() or self.paginas.width() < 20 or self.paginas.height() < 20:
            self.paginas.setCurrentIndex(nuevo_indice)
            self.actualizar_botones_secundarios(nuevo_indice)
            return

        # Capturar snapshot estático de la sección saliente para cross-fade sin QGraphicsEffect
        old_pix = None
        try:
            old_pix = self.paginas.grab()
        except Exception:
            old_pix = None

        self.paginas.setCurrentIndex(nuevo_indice)
        self.actualizar_botones_secundarios(nuevo_indice)

        if old_pix is not None and not old_pix.isNull():
            ov = _SectionCrossfadeOverlay(self.paginas, old_pix, duration_ms=170)
            self._section_fade_overlay = ov
            ov.finished.connect(
                lambda target_ov=ov: setattr(self, "_section_fade_overlay", None)
                if getattr(self, "_section_fade_overlay", None) is target_ov else None
            )

    def on_username_changed(self, new_username):
        self.usuario = new_username
        self.setWindowTitle(f"{t('Menú Principal')} - {t('Usuario:')} {new_username.capitalize()}")

    def cambiar_cuenta(self):
        self._cancel_section_transition()
        for i in range(self.paginas.count()):
            w = self.paginas.widget(i)
            if w is not None and hasattr(w, "stop_active_animations"):
                try:
                    w.stop_active_animations()
                except Exception:
                    pass
        if hasattr(self, 'player') and self.player:
            self.player.stop()
        self.logout_requested.emit()

    def closeEvent(self, event):
        self._cancel_section_transition()
        for i in range(self.paginas.count()):
            w = self.paginas.widget(i)
            if w is not None and hasattr(w, "stop_active_animations"):
                try:
                    w.stop_active_animations()
                except Exception:
                    pass
        if hasattr(self, 'player') and self.player:
            self.player.stop()
        top_level = self.window()
        if top_level and top_level != self:
            top_level.close()
        super().closeEvent(event)

    def _update_nav_active_state(self, active_index: int):
        """Actualiza el estado visual activo (Color 3) del botón de la sección actual en el sidebar (Issue #30)."""
        for idx, btn in enumerate(getattr(self, "_nav_buttons", [])):
            is_active = (idx == active_index)
            if btn.property("active") != is_active:
                btn.setProperty("active", is_active)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def on_binder_inside_changed(self, is_inside: bool):
        """Actualiza la visibilidad de Vaciar según si estamos dentro o fuera de una carpeta."""
        if self.paginas.currentIndex() == 1:
            self.btn_vaciar.setVisible(is_inside)

    def _cambiar_vista_cartas(self, mode: str):
        """Alterna entre vista en imágenes ('grid') y vista en lista ('list') en Buscar y Colecciones (Issue #58)."""
        idx = self.paginas.currentIndex()
        target = self.paginas.widget(idx) if idx in (0, 2) else None
        if target is not None and hasattr(target, "set_view_mode"):
            target.set_view_mode(mode)
        self._sync_view_mode_buttons(idx)

    def _sync_view_mode_buttons(self, indice: int):
        show_view_btns = indice in (0, 2)
        if hasattr(self, "view_buttons_container"):
            self.view_buttons_container.setVisible(show_view_btns)
        if not show_view_btns:
            return
        w = self.paginas.widget(indice)
        mode = getattr(w, "_view_mode", "grid")
        self.btn_view_grid.setChecked(mode == "grid")
        self.btn_view_list.setChecked(mode == "list")

    def actualizar_botones_secundarios(self, indice):
        try:
            self._update_nav_active_state(indice)
            self._sync_view_mode_buttons(indice)
            self.btn_agregar.setVisible(indice == 0)
            self.btn_eliminar.setVisible(indice == 2)
            
            # El botón vaciar solo debe aparecer dentro de una carpeta del binder
            is_inside_binder = False
            if indice == 1:
                binder_w = self.paginas.widget(1)
                if hasattr(binder_w, 'is_inside_binder'):
                    is_inside_binder = binder_w.is_inside_binder()
            self.btn_vaciar.setVisible(is_inside_binder)

            if hasattr(self, 'variant_legend_sidebar') and self.variant_legend_sidebar:
                self.variant_legend_sidebar.setVisible(indice in (1, 2))
        except Exception as e:
            print(f"Error en actualizar_botones_secundarios: {e}")

        if indice == 1:
            try:
                binder = self.paginas.widget(1)
                if hasattr(binder, 'refresh_inventory'):
                    binder.refresh_inventory()
            except Exception as e:
                print(f"Error actualizando binder: {e}")

        if indice == 2:
            try:
                inventario = self.paginas.widget(2)
                if hasattr(inventario, 'reset_page_and_actualizar'):
                    inventario.reset_page_and_actualizar()
                else:
                    if hasattr(inventario, 'actualizar_total_cartas'):
                        inventario.actualizar_total_cartas()
                    if hasattr(inventario, 'actualizar_galeria'):
                        inventario.actualizar_galeria()
            except Exception as e:
                print(f"Error actualizando inventario: {e}")

    def confirmar_salir(self):
        self.mostrar_mensaje("¿Seguro que quieres salir del programa?",
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                             cerrar=True)

    def _ejecutar_agregar_cartas(self, galeria_busqueda, cartas_seleccionadas, carpeta_elegida=None):
        exitos = agregar_cartas_usuario(self.usuario, cartas_seleccionadas, categoria=carpeta_elegida)

        if exitos:
            if hasattr(galeria_busqueda, 'limpiar_seleccion'):
                galeria_busqueda.limpiar_seleccion()
            msg_cat = f" en la colección '{carpeta_elegida}'" if carpeta_elegida else ""
            self.mostrar_mensaje(f"Se han agregado {exitos} carta(s) a tus colecciones{msg_cat}.")
            try:
                inventario = self.paginas.widget(2)
                if hasattr(inventario, 'cargar_categorias_combo'):
                    inventario.cargar_categorias_combo()
                if hasattr(inventario, 'reset_page_and_actualizar'):
                    inventario.reset_page_and_actualizar()
                else:
                    if hasattr(inventario, 'actualizar_total_cartas'):
                        inventario.actualizar_total_cartas()
                    if hasattr(inventario, 'actualizar_galeria'):
                        inventario.actualizar_galeria()
            except Exception as e:
                print(f"Error al refrescar inventario tras agregar: {e}")
        else:
            if carpeta_elegida:
                # Si la carta ya estaba en la colección pero se agregó a una carpeta, refrescar igual
                try:
                    inventario = self.paginas.widget(2)
                    if hasattr(inventario, 'cargar_categorias_combo'):
                        inventario.cargar_categorias_combo()
                    if hasattr(inventario, 'reset_page_and_actualizar'):
                        inventario.reset_page_and_actualizar()
                except Exception:
                    pass
                self.mostrar_mensaje(f"Las cartas seleccionadas ya estaban en tu colección y fueron asignadas a '{carpeta_elegida}'.")
            else:
                self.mostrar_mensaje("Las cartas seleccionadas ya están en tu colección o hubo un error.")

    def agregar_cartas(self):
        """Pregunta al usuario a qué colección desea agregar las cartas seleccionadas (Issues #31 y #32)."""
        galeria_busqueda = self.paginas.widget(0)
        cartas_seleccionadas = galeria_busqueda.get_cartas_seleccionadas()

        if not cartas_seleccionadas:
            self.mostrar_mensaje(t("Selecciona al menos una carta para agregar."))
            return

        from PyQt6.QtWidgets import QLineEdit
        from MyQtApp.app.db_services import obtener_categorias_usuario, crear_categoria_usuario

        colecciones_existentes = obtener_categorias_usuario(self.usuario)

        dlg = QDialog(self)
        dlg.setWindowTitle(t("Agregar a Colección"))
        dlg.setFixedSize(410, 260)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QLabel {
                font-size: 13px;
                font-weight: 600;
                color: #5a2a3a;
            }
            QComboBox, QLineEdit {
                border: 2px solid #f7a8b8;
                border-radius: 10px;
                padding: 6px 10px;
                background-color: #ffffff;
                color: #5a2a3a;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #f56b7b;
            }
        """)

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(22, 20, 22, 20)
        dlg_layout.setSpacing(12)

        lbl = QLabel(t("¿A qué colección deseas agregar estas cartas?"))
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #5a2a3a;")
        dlg_layout.addWidget(lbl)

        combo_cat = QComboBox()
        combo_cat.addItem(t("Todas (colección general)"), None)
        for cat in colecciones_existentes:
            combo_cat.addItem(cat, cat)
        dlg_layout.addWidget(combo_cat)

        lbl_or = QLabel(t("O crea una colección nueva (opcional):"))
        lbl_or.setStyleSheet("font-size: 12px; font-weight: 600; color: #8c5464;")
        dlg_layout.addWidget(lbl_or)

        txt_nueva_col = QLineEdit()
        txt_nueva_col.setPlaceholderText(t("Ej: Favoritas, Kalos, Intercambios..."))
        dlg_layout.addWidget(txt_nueva_col)

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

        btn_add = QPushButton(t("Agregar"))
        btn_add.setFixedHeight(36)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #f7a8b8;
                color: #ffffff;
                border: 2px solid #f29ca4;
                border-radius: 10px;
                padding: 4px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #f5475c;
            }
        """)

        chosen = [None]

        def on_confirm():
            nueva = txt_nueva_col.text().strip()
            if nueva:
                crear_categoria_usuario(self.usuario, nueva)
                chosen[0] = nueva
            else:
                chosen[0] = combo_cat.currentData()
            dlg.accept()

        btn_add.clicked.connect(on_confirm)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_add)
        dlg_layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._ejecutar_agregar_cartas(galeria_busqueda, cartas_seleccionadas, carpeta_elegida=chosen[0])

    def mostrar_mensaje(self, texto, botones=QMessageBox.StandardButton.Ok, cerrar=False):
        mensaje = QMessageBox(self)
        mensaje.setWindowTitle("Confirmación" if cerrar else "Información")
        mensaje.setText(texto)
        mensaje.setStandardButtons(botones)
        mensaje.setDefaultButton(QMessageBox.StandardButton.Ok)

        resultado = mensaje.exec()
        if cerrar and resultado == QMessageBox.StandardButton.Yes:
            self.close()

    def eliminar_cartas(self):
        try:
            inventario = self.paginas.widget(2)
        except Exception as e:
            print(f"Error accediendo a widget de inventario: {e}")
            inventario = None

        if inventario is None:
            self.mostrar_mensaje("No se pudo acceder al inventario.")
            return

        try:
            cartas = inventario.get_cartas_seleccionadas()
        except Exception as e:
            print(f"Error obteniendo cartas de inventario: {e}")
            cartas = []

        if not cartas:
            self.mostrar_mensaje("Selecciona al menos una carta de tu inventario para eliminar.")
            return

        nombres = [c.get('nombre', c.get('id_api')) if isinstance(c, dict) else str(c) for c in cartas]
        texto = f"¿Seguro que quieres eliminar {len(nombres)} carta(s) de tu inventario?\n\n"
        texto += ", ".join(nombres[:6])
        if len(nombres) > 6:
            texto += ", ..."

        resp = QMessageBox.question(self, "Confirmar eliminación", texto,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return

        eliminados = eliminar_cartas_usuario(self.usuario, cartas)

        if eliminados:
            if hasattr(inventario, 'limpiar_seleccion'):
                inventario.limpiar_seleccion()
            self.mostrar_mensaje(f"Se han eliminado {eliminados} carta(s) de tu inventario.")
        else:
            self.mostrar_mensaje("No se eliminaron cartas (posiblemente ya no existían en la tabla o hubo error).")

        try:
            if hasattr(inventario, 'reset_page_and_actualizar'):
                inventario.reset_page_and_actualizar()
            else:
                if hasattr(inventario, 'actualizar_total_cartas'):
                    inventario.actualizar_total_cartas()
                if hasattr(inventario, 'actualizar_galeria'):
                    inventario.actualizar_galeria()
        except Exception as e:
            print(f"Error refrescando inventario tras eliminar: {e}")

    def vaciar_binder(self):
        resp = QMessageBox.question(self, "Vaciar Carpeta", "¿Estás seguro de que quieres quitar todas las cartas de la carpeta?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            try:
                binder = self.paginas.widget(1)
                binder.clear_binder()
                self.mostrar_mensaje("Carpeta vaciada correctamente.")
            except Exception as e:
                print(f"Error vaciando binder: {e}")
                self.mostrar_mensaje("Error al vaciar la carpeta.")
