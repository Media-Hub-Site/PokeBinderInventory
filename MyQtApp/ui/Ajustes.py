from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QSizePolicy, QFrame, QApplication, QMessageBox,
    QDialog, QListWidget, QListWidgetItem, QGridLayout, QLineEdit, QFileDialog, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPainterPath, QColor, QIcon
import os
import hashlib
from MyQtApp.config import (
    STYLE_FILE, STYLE_DARK_FILE, load_settings, save_settings,
    DEFAULT_SETTINGS, get_available_music_tracks, MUSIC_TRACK_NAMES, PROJECT_ROOT,
    BUNDLE_DIR, EXE_DIR, ICONS_DIR, PERFIL_DIR
)
from MyQtApp.i18n import t, language_manager
from MyQtApp.app.backup import create_database_backup, list_backups, restore_database_backup
from MyQtApp.session import SessionLocal
from MyQtApp.models import Usuarios


PRESET_AVATARS = [
    ("Blastoise", "assets/perfil/blastoise.webp"),
    ("Bulbasaur", "assets/perfil/bulbasaur.webp"),
    ("Charizard", "assets/perfil/charizard.webp"),
    ("Charmander", "assets/perfil/charmander.webp"),
    ("Charmeleon", "assets/perfil/charmeleon.webp"),
    ("Eevee", "assets/perfil/eevee.webp"),
    ("Espeon", "assets/perfil/espeon.webp"),
    ("Flareon", "assets/perfil/flareon.webp"),
    ("Ivysaur", "assets/perfil/ivysaur.webp"),
    ("Jolteon", "assets/perfil/jolteon.webp"),
    ("Leafeon", "assets/perfil/leafeon.webp"),
    ("Pichu", "assets/perfil/pichu.webp"),
    ("Pikachu", "assets/perfil/pikachu.webp"),
    ("Raichu", "assets/perfil/raichu.webp"),
    ("Snorlax", "assets/perfil/snorlax.webp"),
    ("Squirtle", "assets/perfil/squirtle.webp"),
    ("Sylveon", "assets/perfil/sylveon.webp"),
    ("Umbreon", "assets/perfil/umbreon.webp"),
    ("Vaporeon", "assets/perfil/vaporeon.webp"),
    ("Wartotle", "assets/perfil/wartotle.webp"),
]


def resolve_avatar_path(image_path: str | None) -> str | None:
    """Resuelve la ruta absoluta del avatar considerando modo dev y ejecutable empaquetado."""
    if not image_path:
        return None
    if os.path.isabs(image_path) and os.path.exists(image_path):
        return image_path

    # Posibles raíces donde buscar rutas relativas
    candidates = [
        os.path.join(BUNDLE_DIR, image_path),
        os.path.join(EXE_DIR, image_path),
        os.path.join(PROJECT_ROOT, image_path),
    ]

    # Si es nombre de archivo directo dentro de assets/perfil
    fname = os.path.basename(image_path)
    candidates.extend([
        os.path.join(PERFIL_DIR, fname),
        os.path.join(EXE_DIR, "assets", "perfil", fname),
        os.path.join(BUNDLE_DIR, "assets", "perfil", fname),
    ])

    for c in candidates:
        if os.path.exists(c):
            return c

    return None


def _get_circular_avatar(image_path: str | None, size: int = 56) -> QPixmap:
    pixmap = None
    resolved = resolve_avatar_path(image_path)
    if resolved:
        pixmap = QPixmap(resolved)

    if not pixmap or pixmap.isNull():
        # Intentar logo de fallback en bundle o exe
        fallback_candidates = [
            os.path.join(ICONS_DIR, "TCG_Logo.png"),
            os.path.join(BUNDLE_DIR, "assets", "icons", "TCG_Logo.png"),
            os.path.join(EXE_DIR, "assets", "icons", "TCG_Logo.png"),
        ]
        for fb in fallback_candidates:
            if os.path.exists(fb):
                pixmap = QPixmap(fb)
                break

    if not pixmap or pixmap.isNull():
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#f7a8b8"))

    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)

    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    ox = (scaled.width() - size) // 2
    oy = (scaled.height() - size) // 2
    painter.drawPixmap(0, 0, scaled, ox, oy, size, size)
    painter.end()
    return result


class AvatarPickerDialog(QDialog):
    """Diálogo para seleccionar un avatar Pokémon preset o subir una imagen personalizada."""

    def __init__(self, current_avatar: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Seleccionar Avatar de Perfil"))
        self.setFixedSize(560, 520)
        self.selected_path = current_avatar

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QLabel(t("Elige un Avatar Pokémon o sube una imagen:"))
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #a3364a;")
        layout.addWidget(header)

        # ScrollArea para la lista completa de avatares Pokémon
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid rgba(242, 156, 164, 0.4);
                border-radius: 10px;
                background-color: transparent;
            }
        """)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(10)
        grid.setContentsMargins(8, 8, 8, 8)

        self.buttons = []
        for idx, (name, path) in enumerate(PRESET_AVATARS):
            r = idx // 4
            c = idx % 4

            btn = QPushButton()
            btn.setFixedSize(92, 92)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name)

            pix = _get_circular_avatar(path, size=70)
            btn.setIcon(QIcon(pix))
            btn.setIconSize(pix.size())

            is_selected = (self.selected_path == path)
            border_color = "#e25b70" if is_selected else "rgba(242, 156, 164, 0.4)"
            bg_color = "rgba(242, 156, 164, 0.25)" if is_selected else "rgba(255, 255, 255, 0.8)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    border-color: #e25b70;
                    background-color: rgba(242, 156, 164, 0.35);
                }}
            """)
            btn.clicked.connect(lambda checked, p=path: self._select_preset(p))
            grid.addWidget(btn, r, c)
            self.buttons.append((btn, path))

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # Botón para cargar archivo personalizado
        custom_layout = QHBoxLayout()
        self.btn_upload = QPushButton(f"📁  {t('Subir Imagen Personalizada...')}")
        self.btn_upload.setProperty("class", "pill")
        self.btn_upload.setFixedHeight(34)
        self.btn_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_upload.clicked.connect(self._choose_custom_file)
        custom_layout.addWidget(self.btn_upload)
        custom_layout.addStretch()
        layout.addLayout(custom_layout)

        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(t("Cancelar"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton(f"✔  {t('Aceptar')}")
        self.btn_apply.setProperty("class", "pill")
        self.btn_apply.setFixedHeight(34)
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_layout)

    def _select_preset(self, path: str):
        self.selected_path = path
        for btn, bpath in self.buttons:
            is_selected = (bpath == path)
            border_color = "#e25b70" if is_selected else "rgba(242, 156, 164, 0.4)"
            bg_color = "rgba(242, 156, 164, 0.25)" if is_selected else "rgba(255, 255, 255, 0.8)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    border-color: #e25b70;
                    background-color: rgba(242, 156, 164, 0.35);
                }}
            """)

    def _choose_custom_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            t("Seleccionar Imagen de Avatar"),
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if file_path:
            self.selected_path = file_path
            self.accept()


class EditUsernameDialog(QDialog):
    """Diálogo para cambiar el nombre de usuario (solicita contraseña si la cuenta la tiene)."""

    def __init__(self, username: str, has_password: bool, parent=None):
        super().__init__(parent)
        self.old_username = username
        self.has_password = has_password
        self.new_username = None

        self.setWindowTitle(t("Cambiar Nombre de Usuario"))
        self.setFixedSize(380, 240 if has_password else 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"✏️  {t('Cambiar nombre para')} {username}")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #a3364a;")
        layout.addWidget(title)

        if has_password:
            layout.addWidget(QLabel(t("Contraseña actual:")))
            self.txt_pwd = QLineEdit()
            self.txt_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.txt_pwd.setPlaceholderText(t("Ingresa tu contraseña actual"))
            self.txt_pwd.setFixedHeight(32)
            layout.addWidget(self.txt_pwd)

        layout.addWidget(QLabel(t("Nuevo nombre de usuario:")))
        self.txt_new_name = QLineEdit()
        self.txt_new_name.setText(username)
        self.txt_new_name.setFixedHeight(32)
        layout.addWidget(self.txt_new_name)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(t("Cancelar"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton(f"💾  {t('Guardar')}")
        self.btn_save.setProperty("class", "pill")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.on_save)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def on_save(self):
        new_name = self.txt_new_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Error", t("El nombre de usuario no puede estar vacío."))
            return

        if new_name == self.old_username:
            self.reject()
            return

        db = SessionLocal()
        try:
            user = db.query(Usuarios).filter(Usuarios.nombre == self.old_username).first()
            if not user:
                QMessageBox.critical(self, "Error", t("Usuario no encontrado."))
                return

            if self.has_password:
                pwd = self.txt_pwd.text().strip()
                pwd_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
                if user.password_hash and pwd_hash != user.password_hash:
                    QMessageBox.warning(self, "Error", t("La contraseña actual es incorrecta."))
                    return

            # Verificar si ya existe otro usuario con ese nuevo nombre
            exist = db.query(Usuarios).filter(Usuarios.nombre.ilike(new_name)).first()
            if exist and exist.id != user.id:
                QMessageBox.warning(self, "Error", t("Ya existe una cuenta con ese nombre de usuario."))
                return

            # Actualizar nombre en cascada para Mazo y usuario_carta
            from ..models import UsuarioCarta, Mazo
            db.query(UsuarioCarta).filter(UsuarioCarta.usuario_nombre == self.old_username).update({"usuario_nombre": new_name})
            db.query(Mazo).filter(Mazo.usuario_nombre == self.old_username).update({"usuario_nombre": new_name})

            user.nombre = new_name
            db.commit()
            self.new_username = new_name
            QMessageBox.information(self, t("Éxito"), t("Nombre de usuario actualizado con éxito."))
            self.accept()
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Error", f"Error al cambiar nombre: {e}")
        finally:
            db.close()


class PasswordConfigDialog(QDialog):
    """Diálogo para configurar, cambiar o eliminar la contraseña del perfil."""

    def __init__(self, username: str, has_password: bool, parent=None):
        super().__init__(parent)
        self.username = username
        self.has_password = has_password
        self.remove_requested = False
        self.new_password = None

        self.setWindowTitle(t("Seguridad de la Cuenta"))
        self.setFixedSize(380, 270 if has_password else 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"🔐  {t('Contraseña para')} {username}")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #a3364a;")
        layout.addWidget(title)

        if has_password:
            layout.addWidget(QLabel(t("Contraseña actual:")))
            self.txt_old_pwd = QLineEdit()
            self.txt_old_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.txt_old_pwd.setPlaceholderText(t("Ingresa contraseña actual"))
            self.txt_old_pwd.setFixedHeight(32)
            layout.addWidget(self.txt_old_pwd)

        layout.addWidget(QLabel(t("Nueva contraseña (deja vacío para eliminar):") if has_password else t("Nueva contraseña:")))
        self.txt_new_pwd = QLineEdit()
        self.txt_new_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_new_pwd.setPlaceholderText(t("Nueva contraseña"))
        self.txt_new_pwd.setFixedHeight(32)
        layout.addWidget(self.txt_new_pwd)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(t("Cancelar"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton(f"💾  {t('Guardar')}")
        self.btn_save.setProperty("class", "pill")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.on_save)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def on_save(self):
        new_pwd = self.txt_new_pwd.text().strip()
        db = SessionLocal()
        try:
            user = db.query(Usuarios).filter(Usuarios.nombre == self.username).first()
            if not user:
                QMessageBox.critical(self, "Error", t("Usuario no encontrado."))
                return

            if self.has_password:
                old_pwd = self.txt_old_pwd.text().strip()
                old_hash = hashlib.sha256(old_pwd.encode('utf-8')).hexdigest()
                if user.password_hash and old_hash != user.password_hash:
                    QMessageBox.warning(self, "Error", t("La contraseña actual es incorrecta."))
                    return

            if not new_pwd:
                user.password_hash = None
                db.commit()
                self.remove_requested = True
                QMessageBox.information(self, t("Éxito"), t("La contraseña ha sido eliminada. La cuenta ahora inicia sesión directamente."))
            else:
                user.password_hash = hashlib.sha256(new_pwd.encode('utf-8')).hexdigest()
                db.commit()
                self.new_password = new_pwd
                QMessageBox.information(self, t("Éxito"), t("Contraseña actualizada con éxito."))

            self.accept()
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Error", f"Error al guardar contraseña: {e}")
        finally:
            db.close()


class DeleteAccountDialog(QDialog):
    """Diálogo con flujo de dos pasos y verificación de contraseña para eliminar la cuenta."""

    def __init__(self, username: str, has_password: bool, parent=None):
        super().__init__(parent)
        self.username = username
        self.has_password = has_password
        self.account_deleted = False

        self.setWindowTitle(t("Eliminar Cuenta"))
        self.setFixedSize(400, 260 if has_password else 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"🗑️  {t('Eliminar Cuenta:')} <b>{username}</b>")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #d93848;")
        layout.addWidget(title)

        info = QLabel(t("Esta opción eliminará permanentemente tu usuario y tu colección."))
        info.setWordWrap(True)
        info.setStyleSheet("color: #666666; font-size: 11px;")
        layout.addWidget(info)

        if has_password:
            layout.addWidget(QLabel(t("Ingresa tu contraseña para confirmar:")))
            self.txt_pwd = QLineEdit()
            self.txt_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.txt_pwd.setPlaceholderText(t("Tu contraseña actual"))
            self.txt_pwd.setFixedHeight(32)
            layout.addWidget(self.txt_pwd)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(t("Cancelar"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_delete = QPushButton(f"🗑️  {t('Eliminar cuenta')}")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #d93848;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #b82836;
            }
        """)
        self.btn_delete.setFixedHeight(34)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self.on_start_deletion)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

    def on_start_deletion(self):
        db = SessionLocal()
        try:
            user = db.query(Usuarios).filter(Usuarios.nombre == self.username).first()
            if not user:
                QMessageBox.critical(self, "Error", t("Usuario no encontrado."))
                return

            # Si tiene contraseña, validar primero
            if self.has_password:
                pwd = self.txt_pwd.text().strip()
                if not pwd:
                    QMessageBox.warning(self, "Error", t("Debes ingresar tu contraseña."))
                    return
                pwd_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
                if user.password_hash and pwd_hash != user.password_hash:
                    QMessageBox.warning(self, "Error", t("Contraseña incorrecta."))
                    return

            # Paso 1: Primer diálogo de confirmación
            reply1 = QMessageBox.question(
                self,
                t("Eliminar Cuenta"),
                t("¿Estás seguro de eliminar tu cuenta?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply1 != QMessageBox.StandardButton.Yes:
                return

            # Paso 2: Segundo diálogo de confirmación
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(t("Confirmación Final"))
            msg_box.setText(t("Esta acción es irreversible."))
            msg_box.setIcon(QMessageBox.Icon.Warning)
            btn_continue = msg_box.addButton(t("Continuar"), QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg_box.addButton(t("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_cancel)
            msg_box.exec()

            if msg_box.clickedButton() != btn_continue:
                return

            # Proceder con la eliminación del usuario y dependencias
            from ..models import UsuarioCarta, Mazo, MazoCarta
            # Eliminar cartas en mazos del usuario
            mazos = db.query(Mazo).filter(Mazo.usuario_nombre == self.username).all()
            for m in mazos:
                db.query(MazoCarta).filter(MazoCarta.mazo_id == m.id).delete()
            db.query(Mazo).filter(Mazo.usuario_nombre == self.username).delete()
            db.query(UsuarioCarta).filter(UsuarioCarta.usuario_nombre == self.username).delete()
            db.delete(user)
            db.commit()

            self.account_deleted = True
            QMessageBox.information(self, t("Cuenta Eliminada"), t("Tu cuenta ha sido eliminada exitosamente."))
            self.accept()

        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Error", f"Error al eliminar la cuenta: {e}")
        finally:
            db.close()


def _make_divider():
    hr = QFrame()
    hr.setFrameShape(QFrame.Shape.HLine)
    hr.setFrameShadow(QFrame.Shadow.Sunken)
    hr.setStyleSheet("background-color: rgba(242, 156, 164, 0.3); border: none; max-height: 1px;")
    return hr


def _make_section_card(title: str, icon: str = "") -> tuple:
    """Crea una tarjeta de sección con título y devuelve (card_widget, inner_layout, title_lbl)."""
    card = QWidget()
    card.setObjectName("settings_card")
    card.setStyleSheet("""
        QWidget#settings_card {
            background-color: rgba(255, 247, 248, 0.85);
            border: 1.5px solid rgba(242, 156, 164, 0.4);
            border-radius: 12px;
        }
    """)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(18, 12, 18, 14)
    card_layout.setSpacing(12)

    title_lbl = None
    if title:
        title_lbl = QLabel(f"  {icon}  {title}" if icon else title)
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #a3364a; border: none; background: transparent; padding-bottom: 2px;")
        card_layout.addWidget(title_lbl)
        card_layout.addWidget(_make_divider())

    return card, card_layout, title_lbl


def _make_setting_row(label_text: str, control: QWidget, label_width: int = 140) -> tuple:
    """Crea una fila etiqueta + control bien alineada y devuelve (row_layout, lbl)."""
    row = QHBoxLayout()
    row.setSpacing(12)
    lbl = QLabel(label_text)
    lbl.setFont(QFont("Segoe UI", 10))
    lbl.setStyleSheet("color: #5a2a3a; border: none; background: transparent;")
    lbl.setFixedWidth(label_width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    row.addWidget(lbl)
    row.addWidget(control)
    return row, lbl


def _make_slider_row(label_text: str, icon: str, initial_value: int, callback) -> tuple:
    """Crea fila con ícono + slider + valor y devuelve (row_layout, slider, lbl)."""
    row = QHBoxLayout()
    row.setSpacing(10)

    lbl = QLabel(label_text)
    lbl.setFont(QFont("Segoe UI", 10))
    lbl.setStyleSheet("color: #5a2a3a; border: none; background: transparent;")
    lbl.setFixedWidth(140)
    lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(lbl)

    icon_lbl = QLabel(icon)
    icon_lbl.setFixedWidth(24)
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(icon_lbl)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(initial_value)
    slider.setFixedHeight(26)
    row.addWidget(slider, stretch=1)

    val_lbl = QLabel(f"{initial_value}%")
    val_lbl.setFont(QFont("Segoe UI", 9))
    val_lbl.setFixedWidth(36)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val_lbl.setStyleSheet("color: #888; border: none; background: transparent;")
    row.addWidget(val_lbl)

    def _on_change(v):
        val_lbl.setText(f"{v}%")
        callback(v)

    slider.valueChanged.connect(_on_change)
    return row, slider, lbl


class RestoreBackupDialog(QDialog):
    """Diálogo modal para listar y seleccionar copias de seguridad a restaurar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Restaurar Copia de Seguridad"))
        self.setMinimumSize(480, 320)
        self.selected_backup = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl_title = QLabel(t("Selecciona un respaldo para restaurar:"))
        lbl_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #5a2a3a;")
        layout.addWidget(lbl_title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1.5px solid rgba(242, 156, 164, 0.5);
                border-radius: 8px;
                padding: 6px;
                background-color: #ffffff;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f2f2f2;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #f29ca4;
                color: white;
            }
        """)

        backups = list_backups()
        if not backups:
            item = QListWidgetItem(t("No se encontraron respaldos de seguridad."))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list_widget.addItem(item)
        else:
            for filename, full_path, dt_str in backups:
                item = QListWidgetItem(f"📅  {dt_str}   —   ({filename})")
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(t("Cancelar"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_restore = QPushButton(f"↩️ {t('Restaurar')}")
        self.btn_restore.setFixedHeight(34)
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore.clicked.connect(self.on_restore)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_restore)
        layout.addLayout(btn_layout)

    def on_restore(self):
        curr = self.list_widget.currentItem()
        if not curr:
            return
        path = curr.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", t("No se ha seleccionado una copia válida."))
            return

        reply = QMessageBox.question(
            self,
            t("Confirmar Restauración"),
            t("¿Estás seguro de restaurar este respaldo? Todos los perfiles e inventarios actuales se reemplazarán por esta copia de seguridad."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.selected_backup = path
            self.accept()


class PokeBinderInfoDialog(QDialog):
    """Ventana informativa con estética de PokeBinder sobre APIs, mercados, música y almacenamiento local."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Información de PokeBinder"))
        self.resize(620, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #fff5f7;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QFrame#InfoSectionCard {
                background-color: #ffffff;
                border: 1.5px solid #f2c4ce;
                border-radius: 14px;
            }
            QLabel#InfoTitle {
                font-size: 19px;
                font-weight: 800;
                color: #a3364a;
            }
            QLabel#InfoSubtitle {
                font-size: 12px;
                color: #7a4b58;
            }
            QLabel#CardHeading {
                font-size: 13px;
                font-weight: 700;
                color: #a3364a;
                border: none;
                background: transparent;
            }
            QLabel#CardBody {
                font-size: 12px;
                color: #3f2730;
                line-height: 1.45;
                border: none;
                background: transparent;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        lbl_title = QLabel("Información de PokeBinder")
        lbl_title.setObjectName("InfoTitle")
        outer.addWidget(lbl_title)

        lbl_sub = QLabel("Detalles técnicos, fuentes de mercado, audio y privacidad de tu colección.")
        lbl_sub.setObjectName("InfoSubtitle")
        outer.addWidget(lbl_sub)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(0, 2, 6, 4)
        vbox.setSpacing(10)

        def _add_card(heading: str, body_html: str):
            card = QFrame()
            card.setObjectName("InfoSectionCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(6)
            h = QLabel(heading)
            h.setObjectName("CardHeading")
            cl.addWidget(h)
            b = QLabel(body_html)
            b.setObjectName("CardBody")
            b.setWordWrap(True)
            b.setTextFormat(Qt.TextFormat.RichText)
            cl.addWidget(b)
            vbox.addWidget(card)

        _add_card(
            "¿Qué es una API? (en términos sencillos)",
            "Una <b>API</b> (Interfaz de Programación de Aplicaciones) funciona como un <b>puente digital</b> "
            "o mensajero automático entre PokeBinder y servidores especializados de cartas Pokémon.<br><br>"
            "Cuando consultas una carta o actualizas su precio, la app envía una solicitud rápida por internet "
            "y recibe al instante la imagen oficial y los valores actualizados del mercado, sin que tengas "
            "que buscarlos manualmente página por página."
        )

        _add_card(
            "Fuentes de Cartas e Imágenes",
            "• <b>TCGdex API</b> (api.tcgdex.net): catálogo multilingüe (Español, Inglés, Japonés, Francés, "
            "Portugués y Chino Tradicional) e imágenes optimizadas en formato .webp.<br>"
            "• <b>Pokémon TCG CDN</b> (images.pokemontcg.io): fuente de respaldo automática para asegurar "
            "que las más de 95.000 cartas del catálogo muestren su arte correctamente."
        )

        _add_card(
            "Fuentes de Precios de Mercado",
            "• <b>TCGPlayer</b>: precios de mercado de referencia en dólares estadounidenses (USD).<br>"
            "• <b>Cardmarket</b>: precios del mercado europeo en euros (EUR), con conversión automática en vivo a USD.<br>"
            "• <b>Pokémon TCG API y TCGCSV</b>: fuentes complementarias utilizadas para contrastar valores "
            "de mercado por carta y calcular el valor acumulado de tu colección y binders."
        )

        track_items = [
            f"• <b>Pista {n}</b>: {MUSIC_TRACK_NAMES.get(n, f'Pista {n}')}"
            for n in range(1, 8)
        ]
        track_list_html = "<br>".join(track_items)
        _add_card(
            "Música y Efectos de Sonido",
            "<b>Pistas de música de fondo disponibles:</b><br>"
            f"{track_list_html}<br><br>"
            "<i>(Seleccionables y regulables desde la sección Audio en Ajustes).</i><br><br>"
            "• <b>Efectos interactivos</b>: sonido de cambio de página y apertura de binder/portamazos "
            "(<i>paginas.wav</i>), inserción de cartas y clics (<i>click.wav</i>) y retroalimentación de botones (<i>hover.wav</i>)."
        )

        _add_card(
            "Almacenamiento Local y Copias de Seguridad",
            "<b>Cada cuenta es local por dispositivo.</b><br><br>"
            "Tu sesión, colección de cartas, carpetas, binders 3D, mazos, portamazos personalizados y ajustes "
            "se guardan exclusivamente en tu propio computador (dentro de <i>%LOCALAPPDATA%\\PokeBinder</i>) "
            "y no se suben automáticamente a ningún servidor externo.<br><br>"
            "Si deseas llevar tu progreso a otro computador o guardarlo en Google Drive o un disco duro, "
            "utiliza el botón <b>Exportar datos</b> en la parte inferior de Ajustes. Luego podrás recuperarlo "
            "en cualquier sesión nueva mediante <b>Importar copia de seguridad</b>."
        )

        vbox.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton(t("Cerrar"))
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #f56b7b;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                border: 1.5px solid #d44854;
                border-radius: 10px;
                padding: 4px 24px;
            }
            QPushButton:hover { background-color: #e05263; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        outer.addLayout(btn_row)


class AjustesWidget(QWidget):
    """Pantalla de ajustes (UI, lógica de temas, y señales de cambio de estado)."""

    music_volume_changed = pyqtSignal(int)
    sound_volume_changed = pyqtSignal(int)
    music_track_changed = pyqtSignal(int)
    animations_toggled = pyqtSignal(bool)
    theme_toggled = pyqtSignal(bool)
    card_size_changed = pyqtSignal(str)
    logout_requested = pyqtSignal()
    username_changed = pyqtSignal(str)

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ajustes_root")
        self.usuario = usuario
        self.settings = load_settings()
        self.user_avatar_path = None
        self.user_has_password = False

        self._load_user_profile_data()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ───── Título + Botón "Información de PokeBinder" ──────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel(f"⚙️  {t('Ajustes')}")
        self.title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #a3364a;")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()

        self.btn_info_app = QPushButton(t("Información de PokeBinder"))
        self.btn_info_app.setFixedHeight(34)
        self.btn_info_app.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_app.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #a3364a;
                font-size: 12px;
                font-weight: 700;
                border: 1.5px solid #f29ca4;
                border-radius: 10px;
                padding: 4px 16px;
            }
            QPushButton:hover {
                background-color: #f7a8b8;
                color: #ffffff;
                border-color: #f56b7b;
            }
        """)
        self.btn_info_app.clicked.connect(self.abrir_info_pokebinder)
        title_row.addWidget(self.btn_info_app)
        root.addLayout(title_row)

        # ───── Sección 0: Perfil de Usuario ────────────────────────────────────
        if self.usuario:
            prof_card, prof_layout, self.lbl_sec_perfil = _make_section_card(t("Perfil de Usuario"), "👤")

            prof_row = QHBoxLayout()
            prof_row.setSpacing(16)

            # Avatar preview widget
            self.avatar_preview_lbl = QLabel()
            self.avatar_preview_lbl.setFixedSize(56, 56)
            self._update_avatar_preview()
            prof_row.addWidget(self.avatar_preview_lbl)

            # User details & actions
            info_layout = QVBoxLayout()
            info_layout.setSpacing(4)

            self.user_name_lbl = QLabel(f"<b>{self.usuario}</b>")
            self.user_name_lbl.setFont(QFont("Segoe UI", 11))
            self.user_name_lbl.setStyleSheet("color: #5a2a3a; border: none; background: transparent;")
            info_layout.addWidget(self.user_name_lbl)

            btn_sub_layout = QHBoxLayout()
            btn_sub_layout.setSpacing(10)

            self.btn_change_avatar = QPushButton(f"✨  {t('Cambiar Avatar')}")
            self.btn_change_avatar.setProperty("class", "pill")
            self.btn_change_avatar.setFixedHeight(30)
            self.btn_change_avatar.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_change_avatar.clicked.connect(self._open_avatar_picker)
            btn_sub_layout.addWidget(self.btn_change_avatar)

            self.btn_change_name = QPushButton(f"✏️  {t('Cambiar Nombre')}")
            self.btn_change_name.setProperty("class", "pill")
            self.btn_change_name.setFixedHeight(30)
            self.btn_change_name.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_change_name.clicked.connect(self._open_username_config)
            btn_sub_layout.addWidget(self.btn_change_name)

            self.btn_change_pwd = QPushButton()
            self._refresh_pwd_btn_text()
            self.btn_change_pwd.setProperty("class", "pill")
            self.btn_change_pwd.setFixedHeight(30)
            self.btn_change_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_change_pwd.clicked.connect(self._open_password_config)
            btn_sub_layout.addWidget(self.btn_change_pwd)

            self.btn_delete_acc = QPushButton(f"🗑️  {t('Eliminar Cuenta')}")
            self.btn_delete_acc.setProperty("class", "pill")
            self.btn_delete_acc.setStyleSheet("""
                QPushButton {
                    background-color: #fee2e2;
                    color: #dc2626;
                    border: 1.5px solid #fca5a5;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #fecaca;
                    border-color: #ef4444;
                }
            """)
            self.btn_delete_acc.setFixedHeight(30)
            self.btn_delete_acc.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_delete_acc.clicked.connect(self._open_delete_account)
            btn_sub_layout.addWidget(self.btn_delete_acc)

            btn_sub_layout.addStretch()
            info_layout.addLayout(btn_sub_layout)

            prof_row.addLayout(info_layout)
            prof_card.layout().addLayout(prof_row)
            root.addWidget(prof_card)
        else:
            self.lbl_sec_perfil = None

        # ───── Sección 1: Audio ────────────────────────────────────────────────
        audio_card, audio_layout, self.lbl_sec_audio = _make_section_card(t("Audio"), "🎵")

        row_musica, self.slider_musica, self.lbl_musica = _make_slider_row(
            t("Música de fondo"), "🎶", self.settings["volumen_musica"], self.on_music_volume
        )
        row_sonido, self.slider_sonido, self.lbl_sonido = _make_slider_row(
            t("Efectos de sonido"), "🔊", self.settings["volumen_sonido"], self.on_sound_volume
        )
        audio_layout.addLayout(row_musica)
        audio_layout.addLayout(row_sonido)

        # Fila: Pista musical (botones circulares)
        track_row = QHBoxLayout()
        track_row.setSpacing(10)
        self.lbl_track = QLabel(t("Pista de música"))
        self.lbl_track.setFont(QFont("Segoe UI", 10))
        self.lbl_track.setStyleSheet("color: #5a2a3a; border: none; background: transparent;")
        self.lbl_track.setFixedWidth(140)
        self.lbl_track.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        track_row.addWidget(self.lbl_track)

        CIRCLE_BASE = """
            QPushButton {
                background-color: #fff0f3;
                color: #b05060;
                border: 2.5px solid #f29ca4;
                border-radius: 18px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fad8de;
                border-color: #e25b70;
            }
        """
        CIRCLE_ACTIVE = """
            QPushButton {
                background-color: #e25b70;
                color: white;
                border: 2.5px solid #c94358;
                border-radius: 18px;
                font-size: 12pt;
                font-weight: bold;
            }
        """
        self._track_btns = []
        current_track = self.settings.get("pista_musica", 1)
        available_tracks = get_available_music_tracks()
        for i in available_tracks:
            btn = QPushButton(str(i))
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            track_name = MUSIC_TRACK_NAMES.get(i)
            if track_name:
                btn.setToolTip(f"Pista {i}: {track_name}")
            else:
                btn.setToolTip(f"Pista {i}")
            btn.setStyleSheet(CIRCLE_ACTIVE if i == current_track else CIRCLE_BASE)
            btn.setProperty("track_num", i)
            btn.clicked.connect(lambda checked=False, n=i: self.select_music_track(n))
            track_row.addWidget(btn)
            self._track_btns.append(btn)

        self._circle_base_style = CIRCLE_BASE
        self._circle_active_style = CIRCLE_ACTIVE
        track_row.addStretch()
        audio_layout.addLayout(track_row)

        root.addWidget(audio_card)

        # ───── Sección 2: Apariencia ───────────────────────────────────────────
        ap_card, ap_layout, self.lbl_sec_apariencia = _make_section_card(t("Apariencia"), "🎨")

        # Fila: Tema
        self.btn_tema = QPushButton(t("Tema Oscuro") if self.settings["tema_oscuro"] else t("Tema Claro"))
        self.btn_tema.setProperty("class", "pill")
        self.btn_tema.setFixedHeight(34)
        self.btn_tema.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tema.clicked.connect(self.toggle_theme)
        row_tema, self.lbl_tema = _make_setting_row(t("Tema de color"), self.btn_tema)
        ap_layout.addLayout(row_tema)

        # Fila: Tamaño de cartas
        tam_cart_val = self.settings.get("tamano_cartas", "Normal")
        self.btn_tamcart = QPushButton(t(tam_cart_val))
        self.btn_tamcart.setProperty("class", "pill")
        self.btn_tamcart.setFixedHeight(34)
        self.btn_tamcart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tamcart.clicked.connect(self.toggle_card_size)
        row_tamcart, self.lbl_tamcart = _make_setting_row(t("Tamaño de cartas"), self.btn_tamcart)
        ap_layout.addLayout(row_tamcart)

        # Fila: Tamaño de fuente con slider
        row_font, self.font_slider, self.lbl_fuente = _make_slider_row(
            t("Tamaño de fuente"), "🔡", self.settings["tamano_fuente"], self.on_font_size_changed
        )
        self.font_slider.setRange(8, 30)
        self.font_slider.setValue(self.settings["tamano_fuente"])
        ap_layout.addLayout(row_font)

        root.addWidget(ap_card)

        # ───── Sección 3: Sistema ──────────────────────────────────────────────
        sys_card, sys_layout, self.lbl_sec_sistema = _make_section_card(t("Sistema"), "🖥️")

        # Fila: Animaciones
        encendido = self.settings["animaciones"]
        self.btn_anim_si = QPushButton(t("SI") if encendido else t("NO"))
        self.btn_anim_si.setProperty("class", "pill selected" if encendido else "pill")
        self.btn_anim_si.setFixedHeight(34)
        self.btn_anim_si.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_anim_si.clicked.connect(self.toggle_animations)
        row_anim, self.lbl_anim = _make_setting_row(t("Animaciones UI"), self.btn_anim_si)
        sys_layout.addLayout(row_anim)

        # Fila: Ritmo de Animaciones (Etapa 1)
        self.combo_anim_speed = QComboBox()
        self.combo_anim_speed.addItem(f"{t('Rápido')} (1.5x)", "Rápido")
        self.combo_anim_speed.addItem(f"{t('Equilibrado')} (1.0x)", "Equilibrado")
        self.combo_anim_speed.addItem(f"{t('Cinematográfico')} (0.7x)", "Cinematográfico")
        cur_speed = self.settings.get("velocidad_animaciones", "Equilibrado")
        idx_speed = self.combo_anim_speed.findData(cur_speed)
        if idx_speed >= 0:
            self.combo_anim_speed.setCurrentIndex(idx_speed)
        self.combo_anim_speed.setFixedHeight(34)
        self.combo_anim_speed.setEnabled(encendido)
        self.combo_anim_speed.setStyleSheet("""
            QComboBox {
                border: 1.5px solid #f29ca4;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 10pt;
            }
            QComboBox::drop-down { border: none; }
        """)
        self.combo_anim_speed.currentIndexChanged.connect(self.on_anim_speed_changed)
        row_anim_speed, self.lbl_anim_speed = _make_setting_row(t("Ritmo de Animaciones"), self.combo_anim_speed)
        sys_layout.addLayout(row_anim_speed)

        # Fila: Idioma
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["Español", "English", "日本語", "Français", "Português"])
        current_lang = self.settings.get("idioma", "Español")
        self.combo_lang.setCurrentText(current_lang)
        self.combo_lang.setFixedHeight(34)
        self.combo_lang.setStyleSheet("""
            QComboBox {
                border: 1.5px solid #f29ca4;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 10pt;
            }
            QComboBox::drop-down { border: none; }
        """)
        self.combo_lang.currentIndexChanged.connect(self.on_language_changed)
        row_lang, self.lbl_idioma = _make_setting_row(t("Idioma"), self.combo_lang)
        sys_layout.addLayout(row_lang)

        root.addWidget(sys_card)

        # ───── Sección 4: Base de Datos y Respaldos ───────────────────────────
        db_card, db_layout, self.lbl_sec_db = _make_section_card(t("Base de Datos y Respaldos"), "🗄️")

        btn_backup_layout = QHBoxLayout()
        btn_backup_layout.setSpacing(12)

        self.btn_create_backup = QPushButton(f"💾 {t('Crear Respaldo')}")
        self.btn_create_backup.setProperty("class", "pill")
        self.btn_create_backup.setFixedHeight(34)
        self.btn_create_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_backup.clicked.connect(self.crear_respaldo_manual)

        self.btn_restore_backup = QPushButton(f"📂 {t('Restaurar Respaldo')}")
        self.btn_restore_backup.setProperty("class", "pill")
        self.btn_restore_backup.setFixedHeight(34)
        self.btn_restore_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_backup.clicked.connect(self.restaurar_respaldo_manual)

        btn_backup_layout.addWidget(self.btn_create_backup)
        btn_backup_layout.addWidget(self.btn_restore_backup)
        btn_backup_layout.addStretch()

        db_layout.addLayout(btn_backup_layout)
        root.addWidget(db_card)

        root.addStretch()

        # ───── Footer: Acciones ────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_logout = QPushButton(f"🚪 {t('Cerrar sesión')}")
        self.btn_logout.setProperty("class", "pill logout_btn")
        self.btn_logout.setFixedHeight(36)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.clicked.connect(self.logout_requested.emit)

        footer.addWidget(self.btn_logout)
        footer.addStretch()

        self.btn_export_portable = QPushButton(t("Exportar datos"))
        self.btn_import_portable = QPushButton(t("Importar copia de seguridad"))
        self.btn_rest = QPushButton(f"↩️ {t('Restaurar valores')}")
        self.btn_save = QPushButton(f"💾 {t('Guardar')}")
        for b in (self.btn_export_portable, self.btn_import_portable, self.btn_rest, self.btn_save):
            b.setProperty("class", "pill")
            b.setFixedHeight(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            footer.addWidget(b)

        self.btn_export_portable.clicked.connect(self.exportar_datos_portables)
        self.btn_import_portable.clicked.connect(self.importar_copia_portable)
        self.btn_rest.clicked.connect(self.restaurar_valores)
        self.btn_save.clicked.connect(self.guardar_valores)

        root.addLayout(footer)
        self.setMinimumWidth(580)

        # Conectar a los cambios de idioma para retraducir dinámicamente esta pantalla
        language_manager.language_changed.connect(self.retranslate_ui)

    def _load_user_profile_data(self):
        if not self.usuario:
            return
        db = SessionLocal()
        try:
            user = db.query(Usuarios).filter(Usuarios.nombre == self.usuario).first()
            if user:
                self.user_avatar_path = user.avatar
                self.user_has_password = bool(user.password_hash)
        except Exception:
            pass
        finally:
            db.close()

    def _update_avatar_preview(self):
        if hasattr(self, 'avatar_preview_lbl') and self.avatar_preview_lbl:
            pix = _get_circular_avatar(self.user_avatar_path, size=56)
            self.avatar_preview_lbl.setPixmap(pix)

    def _refresh_pwd_btn_text(self):
        if hasattr(self, 'btn_change_pwd') and self.btn_change_pwd:
            if self.user_has_password:
                self.btn_change_pwd.setText(f"🔑  {t('Cambiar/Quitar Contraseña')}")
            else:
                self.btn_change_pwd.setText(f"🔒  {t('Añadir Contraseña')}")

    def _open_avatar_picker(self):
        dlg = AvatarPickerDialog(current_avatar=self.user_avatar_path, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_avatar = dlg.selected_path
            db = SessionLocal()
            try:
                user = db.query(Usuarios).filter(Usuarios.nombre == self.usuario).first()
                if user:
                    user.avatar = new_avatar
                    db.commit()
                    self.user_avatar_path = new_avatar
                    self._update_avatar_preview()
                    QMessageBox.information(self, t("Avatar Actualizado"), t("Tu nuevo avatar ha sido guardado exitosamente."))
            except Exception as e:
                db.rollback()
                QMessageBox.critical(self, "Error", f"Error al guardar el avatar: {e}")
            finally:
                db.close()

    def _open_password_config(self):
        dlg = PasswordConfigDialog(username=self.usuario, has_password=self.user_has_password, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_user_profile_data()
            self._refresh_pwd_btn_text()

    def _open_username_config(self):
        dlg = EditUsernameDialog(username=self.usuario, has_password=self.user_has_password, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.new_username:
            old_name = self.usuario
            self.usuario = dlg.new_username
            self.user_name_lbl.setText(f"<b>{self.usuario}</b>")
            self._load_user_profile_data()
            self.username_changed.emit(self.usuario)

    def _open_delete_account(self):
        dlg = DeleteAccountDialog(username=self.usuario, has_password=self.user_has_password, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.account_deleted:
            self.logout_requested.emit()

    def retranslate_ui(self):
        self.title_lbl.setText(f"⚙️  {t('Ajustes')}")
        if hasattr(self, 'lbl_sec_perfil') and self.lbl_sec_perfil:
            self.lbl_sec_perfil.setText(f"  👤  {t('Perfil de Usuario')}")
        if hasattr(self, 'btn_change_avatar') and self.btn_change_avatar:
            self.btn_change_avatar.setText(f"✨  {t('Cambiar Avatar')}")
        if hasattr(self, 'btn_change_name') and self.btn_change_name:
            self.btn_change_name.setText(f"✏️  {t('Cambiar Nombre')}")
        if hasattr(self, 'btn_delete_acc') and self.btn_delete_acc:
            self.btn_delete_acc.setText(f"🗑️  {t('Eliminar Cuenta')}")
        self._refresh_pwd_btn_text()
        if self.lbl_sec_audio:
            self.lbl_sec_audio.setText(f"  🎵  {t('Audio')}")
        self.lbl_musica.setText(t("Música de fondo"))
        self.lbl_sonido.setText(t("Efectos de sonido"))
        self.lbl_track.setText(t("Pista de música"))

        if self.lbl_sec_apariencia:
            self.lbl_sec_apariencia.setText(f"  🎨  {t('Apariencia')}")
        self.lbl_tema.setText(t("Tema de color"))
        self.lbl_tamcart.setText(t("Tamaño de cartas"))
        self.lbl_fuente.setText(t("Tamaño de fuente"))

        if self.lbl_sec_sistema:
            self.lbl_sec_sistema.setText(f"  🖥️  {t('Sistema')}")
        self.lbl_anim.setText(t("Animaciones UI"))
        if hasattr(self, "lbl_anim_speed") and self.lbl_anim_speed:
            self.lbl_anim_speed.setText(t("Ritmo de Animaciones"))
        self.lbl_idioma.setText(t("Idioma"))

        if hasattr(self, 'lbl_sec_db') and self.lbl_sec_db:
            self.lbl_sec_db.setText(f"  🗄️  {t('Base de Datos y Respaldos')}")
        if hasattr(self, 'btn_create_backup') and self.btn_create_backup:
            self.btn_create_backup.setText(f"💾 {t('Crear Respaldo')}")
        if hasattr(self, 'btn_restore_backup') and self.btn_restore_backup:
            self.btn_restore_backup.setText(f"📂 {t('Restaurar Respaldo')}")

        es_oscuro = self.settings.get("tema_oscuro", False)
        self.btn_tema.setText(t("Tema Oscuro") if es_oscuro else t("Tema Claro"))

        tam_cart_val = self.settings.get("tamano_cartas", "Normal")
        self.btn_tamcart.setText(t(tam_cart_val))

        encendido = self.settings.get("animaciones", True)
        self.btn_anim_si.setText(t("SI") if encendido else t("NO"))

        self.btn_logout.setText(t("Cerrar sesión"))
        self.btn_rest.setText(f"↩️ {t('Restaurar valores')}")
        self.btn_save.setText(f"💾 {t('Guardar')}")

    def crear_respaldo_manual(self):
        path = create_database_backup(tag="manual")
        if path:
            QMessageBox.information(
                self,
                t("Respaldo Creado"),
                f"{t('Copia de seguridad guardada con éxito en:')}\n{path}"
            )
        else:
            QMessageBox.critical(
                self,
                "Error",
                t("No se pudo crear la copia de seguridad de la base de datos.")
            )

    def restaurar_respaldo_manual(self):
        dlg = RestoreBackupDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_backup:
            if restore_database_backup(dlg.selected_backup):
                QMessageBox.information(
                    self,
                    t("Restauración Completada"),
                    t("La base de datos de perfiles ha sido restaurada con éxito. Por favor, reinicia la aplicación para refrescar todos los datos.")
                )
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    t("Ocurrió un error al restaurar la base de datos.")
                )

    # ── Callbacks Instantáneos ─────────────────────────────────────────────────
    def on_music_volume(self, val):
        self.settings["volumen_musica"] = val
        save_settings(self.settings)
        self.music_volume_changed.emit(val)

    def on_sound_volume(self, val):
        self.settings["volumen_sonido"] = val
        save_settings(self.settings)
        self.sound_volume_changed.emit(val)

    def on_music_track(self, val):
        self.settings["pista_musica"] = val
        save_settings(self.settings)
        self.music_track_changed.emit(val)

    def select_music_track(self, track_num: int):
        """Selecciona la pista musical y actualiza visualmente los botones circulares."""
        self.settings["pista_musica"] = track_num
        save_settings(self.settings)
        for btn in self._track_btns:
            n = btn.property("track_num")
            btn.setStyleSheet(self._circle_active_style if n == track_num else self._circle_base_style)
        self.music_track_changed.emit(track_num)

    def on_font_size_changed(self, val):
        self.settings["tamano_fuente"] = val
        save_settings(self.settings)
        app = QApplication.instance()
        if app:
            from MyQtApp.config import apply_global_style
            apply_global_style(app)

    def on_language_changed(self, index):
        selected_lang = self.combo_lang.currentText()
        language_manager.set_language(selected_lang)

    def toggle_card_size(self):
        sizes = ["Pequeño", "Normal", "Grande"]
        current = self.settings.get("tamano_cartas", "Normal")
        try:
            next_idx = (sizes.index(current) + 1) % len(sizes)
        except ValueError:
            next_idx = 1
        next_size = sizes[next_idx]
        self.settings["tamano_cartas"] = next_size
        self.btn_tamcart.setText(t(next_size))
        save_settings(self.settings)
        self.card_size_changed.emit(next_size)

    def toggle_animations(self):
        self.settings["animaciones"] = not self.settings["animaciones"]
        encendido = self.settings["animaciones"]
        self.btn_anim_si.setText(t("SI") if encendido else t("NO"))
        self.btn_anim_si.setProperty("class", "pill selected" if encendido else "pill")
        self.btn_anim_si.style().unpolish(self.btn_anim_si)
        self.btn_anim_si.style().polish(self.btn_anim_si)
        if hasattr(self, "combo_anim_speed"):
            self.combo_anim_speed.setEnabled(encendido)
        save_settings(self.settings)
        self.animations_toggled.emit(encendido)

    def on_anim_speed_changed(self, _index):
        val = self.combo_anim_speed.currentData()
        if val:
            self.settings["velocidad_animaciones"] = val
            save_settings(self.settings)

    def toggle_theme(self):
        app = QApplication.instance()
        if not app:
            return
        self.settings["tema_oscuro"] = not self.settings["tema_oscuro"]
        es_oscuro = self.settings["tema_oscuro"]
        self.btn_tema.setText(t("Tema Oscuro") if es_oscuro else t("Tema Claro"))
        save_settings(self.settings)
        from MyQtApp.config import apply_global_style
        apply_global_style(app)
        self.theme_toggled.emit(es_oscuro)

    # ── Persistencia ──────────────────────────────────────────────────────────
    def restaurar_valores(self):
        self.settings = DEFAULT_SETTINGS.copy()
        save_settings(self.settings)

        for w in (self.slider_musica, self.slider_sonido, self.font_slider, self.combo_lang):
            w.blockSignals(True)

        self.slider_musica.setValue(self.settings["volumen_musica"])
        self.slider_sonido.setValue(self.settings["volumen_sonido"])
        self.font_slider.setValue(self.settings["tamano_fuente"])
        self.combo_lang.setCurrentText(self.settings["idioma"])
        language_manager.set_language(self.settings["idioma"])
        self.btn_tamcart.setText(t(self.settings["tamano_cartas"]))

        # Actualizar botones circulares de pista
        default_track = self.settings["pista_musica"]
        for btn in self._track_btns:
            n = btn.property("track_num")
            btn.setStyleSheet(self._circle_active_style if n == default_track else self._circle_base_style)

        for w in (self.slider_musica, self.slider_sonido, self.font_slider, self.combo_lang):
            w.blockSignals(False)

        self.btn_tema.setText(t("Tema Claro"))
        self.btn_anim_si.setText(t("SI"))
        self.btn_anim_si.setProperty("class", "pill selected")
        self.btn_anim_si.style().unpolish(self.btn_anim_si)
        self.btn_anim_si.style().polish(self.btn_anim_si)
        if hasattr(self, "combo_anim_speed"):
            self.combo_anim_speed.blockSignals(True)
            idx_sp = self.combo_anim_speed.findData(self.settings.get("velocidad_animaciones", "Equilibrado"))
            if idx_sp >= 0:
                self.combo_anim_speed.setCurrentIndex(idx_sp)
            self.combo_anim_speed.setEnabled(True)
            self.combo_anim_speed.blockSignals(False)

        app = QApplication.instance()
        if app:
            from MyQtApp.config import apply_global_style
            apply_global_style(app)

        self.music_volume_changed.emit(self.settings["volumen_musica"])
        self.sound_volume_changed.emit(self.settings["volumen_sonido"])
        self.music_track_changed.emit(self.settings["pista_musica"])
        self.animations_toggled.emit(self.settings["animaciones"])
        self.theme_toggled.emit(self.settings["tema_oscuro"])
        self.card_size_changed.emit(self.settings["tamano_cartas"])
        self.retranslate_ui()

    def guardar_valores(self):
        save_settings(self.settings)
        QMessageBox.information(self, t("Ajustes Guardados"), t("Mensaje Guardado"))

    def abrir_info_pokebinder(self):
        """Abre la ventana informativa de PokeBinder (APIs, mercados, música y almacenamiento local)."""
        dlg = PokeBinderInfoDialog(self)
        dlg.exec()

    def exportar_datos_portables(self):
        """Exporta colección, carpetas, binders, mazos, portamazos 3D y ajustes a un archivo .zip portable."""
        if not self.usuario:
            QMessageBox.warning(self, t("Exportar datos"), "No hay una sesión de usuario activa.")
            return

        from datetime import datetime
        from MyQtApp.app.portable_backup import export_user_backup_zip

        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        default_name = os.path.join(
            os.path.expanduser("~/Desktop"),
            f"PokeBinder_Respaldo_{self.usuario}_{stamp}.zip",
        )
        zip_path, _ = QFileDialog.getSaveFileName(
            self,
            t("Exportar datos de PokeBinder"),
            default_name,
            "Copia de seguridad PokeBinder (*.zip)",
        )
        if not zip_path:
            return
        if not zip_path.lower().endswith(".zip"):
            zip_path += ".zip"

        try:
            counts = export_user_backup_zip(self.usuario, zip_path)
            QMessageBox.information(
                self,
                t("Exportación completada"),
                (
                    f"Tus datos fueron exportados correctamente en:\n{zip_path}\n\n"
                    f"• Cartas en colección: {counts['collection_cards']}\n"
                    f"• Carpetas de colección: {counts['collection_folders']}\n"
                    f"• Binders: {counts['binders']}\n"
                    f"• Mazos / Portamazos: {counts['decks']}\n\n"
                    "Puedes guardar este archivo en Google Drive, un pendrive o disco duro."
                ),
            )
        except Exception as e:
            QMessageBox.critical(self, t("Error al exportar"), f"No se pudo crear el archivo de respaldo:\n{e}")

    def importar_copia_portable(self):
        """Importa una copia de seguridad portable (.zip) en la sesión actual del usuario."""
        if not self.usuario:
            QMessageBox.warning(self, t("Importar copia de seguridad"), "No hay una sesión de usuario activa.")
            return

        from MyQtApp.app.portable_backup import import_user_backup_zip

        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            t("Importar copia de seguridad de PokeBinder"),
            os.path.expanduser("~/Desktop"),
            "Copia de seguridad PokeBinder (*.zip)",
        )
        if not zip_path:
            return

        reply = QMessageBox.question(
            self,
            t("Confirmar importación"),
            (
                f"¿Deseas importar la copia de seguridad en la sesión actual ('{self.usuario}')?\n\n"
                "Se restaurarán tus cartas de colección, carpetas, binders, mazos y diseños de portamazos "
                "sin borrar el catálogo global."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            counts = import_user_backup_zip(self.usuario, zip_path)
            # Refrescar vistas principales si existen en la ventana padre
            win = self.window()
            if win:
                for attr, method in (
                    ("inventario_widget", "actualizar_galeria"),
                    ("inventario_widget", "cargar_categorias_combo"),
                    ("binder_widget", "load_binder_data"),
                    ("binder_widget", "render_folders_grid"),
                    ("mazos_widget", "cargar_mazos"),
                ):
                    sub = getattr(win, attr, None)
                    if sub and hasattr(sub, method):
                        try:
                            getattr(sub, method)()
                        except Exception:
                            pass

            QMessageBox.information(
                self,
                t("Copia de seguridad importada"),
                (
                    f"Datos restaurados correctamente en tu cuenta '{self.usuario}':\n\n"
                    f"• Cartas agregadas a colección: {counts['collection_cards']}\n"
                    f"• Carpetas restauradas: {counts['collection_folders']}\n"
                    f"• Binders restaurados: {counts['binders']}\n"
                    f"• Mazos / Portamazos restaurados: {counts['decks']}"
                ),
            )
        except Exception as e:
            QMessageBox.critical(self, t("Error al importar"), f"No se pudo importar la copia de seguridad:\n{e}")
