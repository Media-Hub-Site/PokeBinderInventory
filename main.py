import sys
import os
from PyQt6.QtWidgets import QApplication, QWidget, QStackedWidget, QVBoxLayout, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, pyqtProperty, QTimer
from MyQtApp.ui.Login import LoginWindow
from MyQtApp.ui.Index import MainWindow
from MyQtApp.models import Base
from MyQtApp.session import engine
from MyQtApp.config import apply_global_style

class AppWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PokeBinder")
        
        # Obtener geometría centrada para la ventana de Login (520x520)
        self.setGeometry(self.get_centered_geometry(520, 520))
        self.setMinimumSize(520, 520)
        self.setMaximumSize(520, 520)
        
        self.setObjectName("MainBackground")

        # Layout principal
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Stack de páginas
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # Añadir LoginWidget
        self.login_widget = LoginWindow()
        self.stack.addWidget(self.login_widget)

        # Conectar señal de login exitoso
        self.login_widget.login_successful.connect(self.on_login_successful)

        # Overlay de transición (Flash blanco)
        self.flash_overlay = QWidget(self)
        self.flash_overlay.setStyleSheet("background-color: white; border-radius: 20px;")
        self.flash_overlay.hide()

        # Efecto de opacidad para el flash
        self.flash_opacity = QGraphicsOpacityEffect(self.flash_overlay)
        self.flash_overlay.setGraphicsEffect(self.flash_opacity)

        # Ajustar geometría del flash inicialmente
        self.flash_overlay.setGeometry(self.rect())

    @pyqtProperty(float)
    def windowProgress(self):
        return getattr(self, "_window_progress", 0.0)

    @windowProgress.setter
    def windowProgress(self, val):
        self._window_progress = val
        w = int(self._start_w + (self._end_w - self._start_w) * val)
        h = int(self._start_h + (self._end_h - self._start_h) * val)
        
        # Centrar el marco completo de la ventana en el área disponible de la pantalla actual
        screen_obj = self.screen() or QApplication.primaryScreen()
        screen = screen_obj.availableGeometry()
        fg = self.frameGeometry()
        extra_w = max(0, fg.width() - self.width())
        extra_h = max(0, fg.height() - self.height())
        self.resize(w, h)
        x = screen.x() + max(0, (screen.width() - (w + extra_w)) // 2)
        y = screen.y() + max(0, (screen.height() - (h + extra_h)) // 2)
        self.move(x, y)

    def center_on_screen(self):
        """Centra exactamente la ventana (incluyendo bordes y barra de título) en la pantalla actual."""
        screen_obj = self.screen() or QApplication.primaryScreen()
        if not screen_obj:
            return
        avail = screen_obj.availableGeometry()
        if self.layout():
            self.layout().activate()
        fg = self.frameGeometry()
        extra_w = max(0, fg.width() - self.width())
        extra_h = max(0, fg.height() - self.height())
        max_w = max(self.minimumWidth(), avail.width() - extra_w)
        max_h = max(self.minimumHeight(), avail.height() - extra_h)
        target_w = min(self.width(), max_w)
        target_h = min(self.height(), max_h)
        if target_w != self.width() or target_h != self.height():
            self.resize(target_w, target_h)
            fg = self.frameGeometry()
        x = avail.x() + max(0, (avail.width() - fg.width()) // 2)
        y = avail.y() + max(0, (avail.height() - fg.height()) // 2)
        self.move(x, y)

    def get_centered_geometry(self, width, height):
        screen_obj = self.screen()
        if screen_obj is None:
            screen_obj = QApplication.primaryScreen()
        screen = screen_obj.availableGeometry()
        x = screen.x() + max(0, (screen.width() - width) // 2)
        y = screen.y() + max(0, (screen.height() - height) // 2)
        return QRect(x, y, width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.flash_overlay.setGeometry(self.rect())

    def on_login_successful(self, username):
        # Desbloquear límites de tamaño temporalmente para la animación
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setWindowTitle(f"PokeBinder - {username.capitalize()}")

        # Crear la ventana principal (se agregará al stack al finalizar el fade-in para evitar saltos bruscos)
        self.main_window = MainWindow(username)
        self.main_window.logout_requested.connect(self.on_logout_requested)

        # Calcular el área disponible completa de la pantalla para animar la expansión al 100%
        screen_obj = self.screen() or QApplication.primaryScreen()
        avail = screen_obj.availableGeometry()
        fg = self.frameGeometry()
        extra_w = max(16, fg.width() - self.width())
        extra_h = max(39, fg.height() - self.height())
        target_w = max(1020, avail.width() - extra_w)
        target_h = max(620, avail.height() - extra_h)

        # Ejecutar la transición de flash blanco con expansión al 100% y maximizado final
        self.ejecutar_transicion_flash(
            nuevo_indice=1,
            target_w=target_w,
            target_h=target_h,
            maximize_on_finish=True,
        )

    def on_logout_requested(self):
        # Desbloquear límites de tamaño temporalmente para la animación
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setWindowTitle("PokeBinder")

        if self.isFullScreen() or self.isMaximized():
            avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            self.showNormal()
            self.setGeometry(avail)

        # Ejecutar transición de regreso al Login (índice 0) con redimensionamiento animado a 520x520
        self.ejecutar_transicion_flash(nuevo_indice=0, destruir_main=True, target_w=520, target_h=520)

    def ejecutar_transicion_flash(self, nuevo_indice, destruir_main=False, target_w=None, target_h=None, maximize_on_finish=False):
        self.flash_overlay.show()
        self.flash_overlay.raise_()

        # Animación de Entrada (Fade in suave)
        self.anim_in = QPropertyAnimation(self.flash_opacity, b"opacity")
        self.anim_in.setDuration(200)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Animación de Salida (Fade out suave)
        self.anim_out = QPropertyAnimation(self.flash_opacity, b"opacity")
        self.anim_out.setDuration(200)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Grupo paralelo para la entrada y cambio de tamaño
        grupo_in = QParallelAnimationGroup(self)
        grupo_in.addAnimation(self.anim_in)

        if target_w and target_h:
            self._start_w = self.width()
            self._start_h = self.height()
            self._end_w = target_w
            self._end_h = target_h
            
            self.anim_geom = QPropertyAnimation(self, b"windowProgress")
            self.anim_geom.setDuration(240)
            self.anim_geom.setStartValue(0.0)
            self.anim_geom.setEndValue(1.0)
            self.anim_geom.setEasingCurve(QEasingCurve.Type.OutCubic)
            grupo_in.addAnimation(self.anim_geom)

        # Conservar referencia para evitar recolección de basura
        self._trans_group = grupo_in

        def al_completar_in():
            if not destruir_main and getattr(self, "main_window", None) is not None:
                if self.stack.indexOf(self.main_window) == -1:
                    self.stack.addWidget(self.main_window)
            self.stack.setCurrentIndex(nuevo_indice)
            if destruir_main:
                if self.stack.count() > 1:
                    widget_main = self.stack.widget(1)
                    self.stack.removeWidget(widget_main)
                    widget_main.deleteLater()
                self.main_window = None
                # Fijar tamaño del login
                self.setMinimumSize(520, 520)
                self.setMaximumSize(520, 520)
                if hasattr(self.login_widget, 'load_profiles'):
                    self.login_widget.load_profiles()
                self.center_on_screen()
                QTimer.singleShot(0, self.center_on_screen)
                QTimer.singleShot(60, self.center_on_screen)
            else:
                # Establecer límites del main window y maximizar o re-centrar tras ajustar layout
                self.setMinimumSize(1020, 620)
                self.setMaximumSize(16777215, 16777215)
                if maximize_on_finish:
                    self.showMaximized()
                else:
                    self.center_on_screen()
                    QTimer.singleShot(0, self.center_on_screen)
                    QTimer.singleShot(60, self.center_on_screen)

            self.anim_out.start()

        def al_completar_out():
            self.flash_overlay.hide()
            if not (self.isMaximized() or self.isFullScreen()):
                self.center_on_screen()
            self._trans_group = None

        grupo_in.finished.connect(al_completar_in)
        self.anim_out.finished.connect(al_completar_out)
        
        grupo_in.start()

    def keyPressEvent(self, event):
        if self.stack.currentIndex() == 1:
            if event.key() == Qt.Key.Key_F11:
                if self.isFullScreen():
                    self.showMaximized()
                else:
                    self.showFullScreen()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
                self.showMaximized()
                event.accept()
                return
        super().keyPressEvent(event)


from MyQtApp.ui.toast import init_global_toast, install_global_exception_hook

def ensure_db_schema_up_to_date():
    import sqlite3
    from MyQtApp.config import DB_PATH
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(usuario_carta)")
            cols = [row[1] for row in cur.fetchall()]
            if "variante" not in cols:
                cur.execute("ALTER TABLE usuario_carta ADD COLUMN variante VARCHAR DEFAULT 'Normal'")
            if "idioma" not in cols:
                cur.execute("ALTER TABLE usuario_carta ADD COLUMN idioma VARCHAR DEFAULT 'es'")
            if "categoria" not in cols:
                cur.execute("ALTER TABLE usuario_carta ADD COLUMN categoria VARCHAR")
            if "cantidad" not in cols:
                cur.execute("ALTER TABLE usuario_carta ADD COLUMN cantidad INTEGER NOT NULL DEFAULT 1")
            
            cur.execute("PRAGMA table_info(Cartas)")
            cols_cartas = [row[1] for row in cur.fetchall()]
            if "variantes_disponibles" not in cols_cartas:
                cur.execute("ALTER TABLE Cartas ADD COLUMN variantes_disponibles VARCHAR DEFAULT 'normal,reverse,holo'")
            if "generacion" not in cols_cartas:
                cur.execute("ALTER TABLE Cartas ADD COLUMN generacion VARCHAR")
            if "pokedex_id" not in cols_cartas:
                cur.execute("ALTER TABLE Cartas ADD COLUMN pokedex_id INTEGER")
            if "tag" not in cols_cartas:
                cur.execute("ALTER TABLE Cartas ADD COLUMN tag VARCHAR DEFAULT 'Desconocido'")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_generacion ON Cartas(generacion)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_pokedex_id ON Cartas(pokedex_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_tag ON Cartas(tag)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS carta_precios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    carta_id VARCHAR NOT NULL,
                    fuente VARCHAR NOT NULL,
                    moneda VARCHAR NOT NULL DEFAULT 'USD',
                    precio_usd FLOAT NOT NULL DEFAULT 0.0,
                    precio_original FLOAT NOT NULL DEFAULT 0.0,
                    precio_low FLOAT,
                    precio_mid FLOAT,
                    precio_high FLOAT,
                    variante VARCHAR DEFAULT 'market',
                    actualizado_en VARCHAR,
                    UNIQUE (carta_id, fuente)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS ix_carta_precios_carta_id ON carta_precios (carta_id)")
            
            conn.commit()
            conn.close()

            from MyQtApp.app.card_data_migration import normalize_cards_database
            normalize_cards_database(DB_PATH)

            from MyQtApp.app.pokemon_generations import populate_generations_in_db
            populate_generations_in_db(DB_PATH, force=False)
        except Exception as e:
            print(f"Error asegurando esquema DB: {e}")

def main():
    smoke_test = "--smoke-test" in sys.argv[1:]
    if smoke_test:
        from MyQtApp.ui.card_holo_masks import _CV2_AVAILABLE
        if not _CV2_AVAILABLE:
            sys.exit(2)
    else:
        install_global_exception_hook()

    # Soporte para inyección de idioma desde Launcher (--lang=es/en) o variable de entorno
    lang_arg = os.environ.get("MEDIAHUB_APP_LANG", "")
    for arg in sys.argv[1:]:
        if arg.startswith("--lang="):
            lang_arg = arg.split("=", 1)[1].strip()
    
    if lang_arg:
        from MyQtApp.i18n import language_manager
        lang_map = {
            "es": "Español", "en": "English", "ja": "日本語", "fr": "Français", "pt": "Português"
        }
        chosen = lang_map.get(lang_arg.lower(), "Español")
        language_manager.set_language(chosen)

    app = QApplication(sys.argv)
    app.setApplicationName("PokeBinder")
    app.setApplicationDisplayName("PokeBinder")

    # Inicializar Base de datos (con autorrecuperación si SQLite sufrió daño previo)
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as db_err:
        print(f"⚠️ Error al inicializar BD ({db_err}); intentando autorrecuperación desde respaldo...")
        try:
            engine.dispose()
        except Exception:
            pass
        from MyQtApp.app.backup import ensure_database_integrity_or_recover
        ensure_database_integrity_or_recover()
        Base.metadata.create_all(bind=engine)
    ensure_db_schema_up_to_date()

    # Generar respaldo de seguridad preventivo al iniciar
    if not smoke_test:
        try:
            from MyQtApp.app.backup import create_database_backup
            create_database_backup(tag="auto")
        except Exception as e:
            print(f"Error generando respaldo automático de inicio: {e}")

    # Cargar Estilos Globales
    apply_global_style(app)

    window = AppWindow()
    if smoke_test:
        from PyQt6.QtGui import QPixmap, QColor
        from MyQtApp.ui.card_holo_masks import get_initial_foil_mask
        test_pix = QPixmap(180, 252)
        test_pix.fill(QColor("#1e293b"))
        mask_qimg, _, _ = get_initial_foil_mask(
            test_pix, None, "es", "full_art_etched", rarity="Special Illustration Rare"
        )
        window.close()
        app.quit()
        sys.exit(0 if (mask_qimg is not None and not mask_qimg.isNull()) else 3)
    init_global_toast(window)
    window.show()
    QTimer.singleShot(0, window.center_on_screen)
    sys.exit(app.exec())




if __name__ == "__main__":
    main()
