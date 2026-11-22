import random
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QMessageBox, QStackedWidget, QSpacerItem, QSizePolicy, QGraphicsOpacityEffect,
    QDialog, QComboBox
)
from PyQt6.QtCore import Qt, QUrl, QPropertyAnimation, QEasingCurve, QPoint, QByteArray, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
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

        from MyQtApp.config import VARIANT_COLOR_MAP
        for key, info in VARIANT_COLOR_MAP.items():
            item_row = QHBoxLayout()
            item_row.setContentsMargins(0, 0, 0, 0)
            item_row.setSpacing(6)

            color_badge = QLabel(self)
            color_badge.setFixedSize(10, 12)
            color_badge.setStyleSheet(f"background-color: {info['color']}; border: 1px solid {info['border']}; border-radius: 3px;")

            desc = QLabel(f"{info['name']}", self)
            desc.setStyleSheet("font-size: 10px; color: #f8fafc; font-weight: 500; border: none; background: transparent;")

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
        self.setGeometry(550, 250, 1000, 650)

        main_layout = QHBoxLayout(self)

        # Barra lateral
        nav_layout = QVBoxLayout()

        iconoBuscar = QIcon(os.path.join(ICONS_DIR, "buscar.png"))
        iconoCarpeta = QIcon(os.path.join(ICONS_DIR, "carpeta.png"))
        iconoColeccion = QIcon(os.path.join(ICONS_DIR, "coleccion.png"))

        self.btn_buscar = BotonConSonido(iconoBuscar, t("Buscar"))
        self.btn_ver_carpeta = BotonConSonido(iconoCarpeta, t("Binder"))
        self.btn_mi_coleccion = BotonConSonido(iconoColeccion, t("Colección"))
        self.btn_mazos = BotonConSonido(t("Mazos"))
        self.btn_print = BotonConSonido(t("Print"))

        botones_principales = [
            self.btn_buscar,
            self.btn_ver_carpeta,
            self.btn_mi_coleccion,
            self.btn_mazos,
            self.btn_print,
            BotonConSonido(t("Ajustes")),
        ]

        for btn in botones_principales:
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "NavButton")
            nav_layout.addWidget(btn)

        self.btn_ajustes = botones_principales[-1]

        nav_layout.addSpacing(16)

        self.btn_agregar = BotonConSonido(t("Agregar a Colección"))
        self.btn_agregar_carpeta = BotonConSonido(t("Agregar a Carpeta"))
        self.btn_eliminar = BotonConSonido(t("Eliminar"))
        self.btn_vaciar = BotonConSonido(t("Vaciar"))

        botones_secundarios_layout = QVBoxLayout()
        botones_secundarios_layout.setSpacing(8)
        for btn in [self.btn_agregar, self.btn_agregar_carpeta, self.btn_eliminar, self.btn_vaciar]:
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "ActionSecondary")
            botones_secundarios_layout.addWidget(btn)

        nav_layout.addLayout(botones_secundarios_layout)

        # Cuadro explicativo de la leyenda de variantes
        nav_layout.addSpacing(12)
        self.variant_legend_sidebar = VariantLegendSidebarWidget(self)
        nav_layout.addWidget(self.variant_legend_sidebar)

        nav_layout.addStretch()

        self.btn_salir = BotonConSonido(t("Salir del programa"))
        self.btn_salir.setFixedHeight(44)
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salir.setProperty("class", "ExitButton")
        nav_layout.addWidget(self.btn_salir)
        nav_layout.addSpacing(14)


        # Panel lateral
        side_widget = QWidget()
        side_layout_wrapper = QVBoxLayout(side_widget)
        side_layout_wrapper.setContentsMargins(12, 12, 12, 12)
        side_widget.setObjectName('side')
        side_layout_wrapper.addLayout(nav_layout)
        side_layout_wrapper.addStretch()

        main_layout.addWidget(side_widget, 1)

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

        # Pie inferior
        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        bottom_layout.setSpacing(8)
        bottom_layout.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        view_buttons = QWidget()
        vb_layout = QHBoxLayout(view_buttons)
        vb_layout.setContentsMargins(0, 0, 0, 0)
        vb_layout.setSpacing(8)

        self.btn_view_grid = QPushButton("▦")
        self.btn_view_grid.setFixedSize(48, 48)
        self.btn_view_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_grid.setToolTip("Vista en imágenes")
        self.btn_view_grid.setProperty("class", "ViewGrid")

        self.btn_view_list = QPushButton("≡")
        self.btn_view_list.setFixedSize(48, 48)
        self.btn_view_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_list.setToolTip("Vista en lista")
        self.btn_view_list.setProperty("class", "ViewList")

        vb_layout.addWidget(self.btn_view_grid)
        vb_layout.addWidget(self.btn_view_list)

        bottom_layout.addWidget(view_buttons, 0, Qt.AlignmentFlag.AlignRight)
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
        self.btn_agregar_carpeta.clicked.connect(self.agregar_cartas_a_carpeta)
        self.btn_eliminar.clicked.connect(self.eliminar_cartas)
        self.btn_vaciar.clicked.connect(self.vaciar_binder)

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
        self.btn_mi_coleccion.setText(t("Colección"))
        self.btn_mazos.setText(t("Mazos"))
        self.btn_print.setText(t("Print"))
        self.btn_ajustes.setText(t("Ajustes"))
        self.btn_agregar.setText(t("Agregar a Colección"))
        self.btn_agregar_carpeta.setText(t("Agregar a Carpeta"))
        self.btn_vaciar.setText(t("Vaciar"))
        self.btn_salir.setText(t("Salir del programa"))

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

    def animar_transicion(self, nuevo_indice):
        indice_actual = self.paginas.currentIndex()
        if nuevo_indice == indice_actual:
            return

        widget_actual = self.paginas.currentWidget()
        widget_nuevo = self.paginas.widget(nuevo_indice)

        if not self.animaciones_activas:
            # Sin animación: cambiar de página al instante
            self.paginas.setCurrentIndex(nuevo_indice)
            self.actualizar_botones_secundarios(nuevo_indice)
            return

        # Transición moderna de fundido suave (Cross-fade)
        self.paginas.setCurrentIndex(nuevo_indice)
        self.actualizar_botones_secundarios(nuevo_indice)

        eff = QGraphicsOpacityEffect(widget_nuevo)
        widget_nuevo.setGraphicsEffect(eff)

        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.15)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def cleanup():
            widget_nuevo.setGraphicsEffect(None)
            self._current_animations = []

        anim.finished.connect(cleanup)
        self._current_animations = [anim, eff]
        anim.start()

    def on_username_changed(self, new_username):
        self.usuario = new_username
        self.setWindowTitle(f"{t('Menú Principal')} - {t('Usuario:')} {new_username.capitalize()}")

    def cambiar_cuenta(self):
        if hasattr(self, 'player') and self.player:
            self.player.stop()
        self.logout_requested.emit()

    def closeEvent(self, event):
        if hasattr(self, 'player') and self.player:
            self.player.stop()
        top_level = self.window()
        if top_level and top_level != self:
            top_level.close()
        super().closeEvent(event)

    def actualizar_botones_secundarios(self, indice):
        try:
            self.btn_agregar.setVisible(indice == 0)
            self.btn_agregar_carpeta.setVisible(indice == 0)
            self.btn_eliminar.setVisible(indice == 2)
            self.btn_vaciar.setVisible(indice == 1)
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
            msg_cat = f" en la carpeta '{carpeta_elegida}'" if carpeta_elegida else ""
            self.mostrar_mensaje(f"Se han agregado {exitos} carta(s) a tu colección{msg_cat}.")
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
        """Agrega directamente a la colección general sin asignar carpeta."""
        galeria_busqueda = self.paginas.widget(0)
        cartas_seleccionadas = galeria_busqueda.get_cartas_seleccionadas()

        if not cartas_seleccionadas:
            self.mostrar_mensaje(t("Selecciona al menos una carta para agregar."))
            return

        self._ejecutar_agregar_cartas(galeria_busqueda, cartas_seleccionadas, carpeta_elegida=None)

    def agregar_cartas_a_carpeta(self):
        """Pregunta al usuario a qué carpeta de su colección desea agregar las cartas seleccionadas."""
        galeria_busqueda = self.paginas.widget(0)
        cartas_seleccionadas = galeria_busqueda.get_cartas_seleccionadas()

        if not cartas_seleccionadas:
            self.mostrar_mensaje(t("Selecciona al menos una carta para agregar."))
            return

        from PyQt6.QtWidgets import QLineEdit
        from MyQtApp.app.db_services import obtener_categorias_usuario, crear_categoria_usuario

        carpetas_existentes = obtener_categorias_usuario(self.usuario)

        dlg = QDialog(self)
        dlg.setWindowTitle(t("Agregar a Carpeta"))
        dlg.setFixedSize(390, 250 if carpetas_existentes else 200)
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

        lbl = QLabel(t("¿A qué carpeta deseas agregar estas cartas?"))
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #5a2a3a;")
        dlg_layout.addWidget(lbl)

        combo_cat = None
        if carpetas_existentes:
            combo_cat = QComboBox()
            for cat in carpetas_existentes:
                combo_cat.addItem(cat, cat)
            dlg_layout.addWidget(combo_cat)

            lbl_or = QLabel(t("O crea una carpeta nueva:"))
            lbl_or.setStyleSheet("font-size: 12px; font-weight: 600; color: #8c5464;")
            dlg_layout.addWidget(lbl_or)
        else:
            lbl_empty = QLabel(t("Aún no tienes carpetas. Escribe un nombre para crear la primera:"))
            lbl_empty.setWordWrap(True)
            lbl_empty.setStyleSheet("font-size: 12px; font-weight: 500; color: #8c5464;")
            dlg_layout.addWidget(lbl_empty)

        txt_nueva_carpeta = QLineEdit()
        txt_nueva_carpeta.setPlaceholderText(t("Ej: Favoritas, Intercambios, Charizards..."))
        dlg_layout.addWidget(txt_nueva_carpeta)

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

        btn_add = QPushButton(t("Agregar a Carpeta"))
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
            nueva = txt_nueva_carpeta.text().strip()
            if nueva:
                crear_categoria_usuario(self.usuario, nueva)
                chosen[0] = nueva
                dlg.accept()
            elif combo_cat and combo_cat.currentData():
                chosen[0] = combo_cat.currentData()
                dlg.accept()
            else:
                QMessageBox.warning(dlg, t("Aviso"), t("Ingresa un nombre para la carpeta."))

        btn_add.clicked.connect(on_confirm)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_add)
        dlg_layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted and chosen[0]:
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
