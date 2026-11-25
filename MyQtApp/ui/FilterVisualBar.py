import math
from PyQt6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QPushButton, QLabel, QScrollArea
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QPolygonF

from MyQtApp.config import load_settings
from MyQtApp.i18n import t


# Tipos de energía Pokémon sincronizados con Cartas.type en PokeDatabase.db (sin emojis)
ENERGY_TYPES = [
    (None, "Todos", "#64748b", "#ffffff"),
    ("Grass", "Planta", "#16a34a", "#ffffff"),
    ("Fire", "Fuego", "#dc2626", "#ffffff"),
    ("Water", "Agua", "#0284c7", "#ffffff"),
    ("Lightning", "Rayo", "#ca8a04", "#ffffff"),
    ("Psychic", "Psíquico", "#9333ea", "#ffffff"),
    ("Fighting", "Lucha", "#c2410c", "#ffffff"),
    ("Darkness", "Oscuro", "#334155", "#ffffff"),
    ("Metal", "Metálico", "#64748b", "#ffffff"),
    ("Dragon", "Dragón", "#b45309", "#ffffff"),
    ("Fairy", "Hada", "#db2777", "#ffffff"),
    ("Colorless", "Incoloro", "#94a3b8", "#1e293b"),
]

# Generaciones / Regiones Pokémon sincronizadas con Cartas.generacion
GENERATION_FILTERS = [
    (None, "Todas", "#64748b", "#ffffff"),
    ("Kanto", "Kanto", "#dc2626", "#ffffff"),
    ("Johto", "Johto", "#d97706", "#ffffff"),
    ("Hoenn", "Hoenn", "#0284c7", "#ffffff"),
    ("Sinnoh", "Sinnoh", "#7c3aed", "#ffffff"),
    ("Teselia", "Teselia", "#0f766e", "#ffffff"),
    ("Kalos", "Kalos", "#2563eb", "#ffffff"),
    ("Alola", "Alola", "#ea580c", "#ffffff"),
    ("Galar", "Galar", "#db2777", "#ffffff"),
    ("Paldea", "Paldea", "#9333ea", "#ffffff"),
]

ZOOM_LEVELS = [
    ("Pequeño", "Compacto"),
    ("Normal", "Normal"),
    ("Grande", "Grande"),
]


class EnergyTypeFilterBar(QFrame):
    """
    Barra visual compacta y complementaria de filtros rápidos por Tipo de Energía o Generación Pokémon
    + botón compacto para alternar entre modos de filtro rápido
    + control de escala/zoom de cuadrícula (Compacto / Normal / Grande).
    Se sincroniza bidireccionalmente con el QComboBox de Tipo existente sin reemplazarlo.
    """
    type_selected = pyqtSignal(object)        # str | None
    generation_selected = pyqtSignal(object)  # str | None
    zoom_changed = pyqtSignal(str)            # "Pequeño" | "Normal" | "Grande"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EnergyTypeFilterBar")
        self.setFixedHeight(34)
        self._mode = "energy"  # "energy" | "generation"
        self._active_type = None
        self._active_generation = None
        self._active_zoom = load_settings().get("tamano_cartas", "Normal")
        self._type_buttons = {}
        self._gen_buttons = {}
        self._zoom_buttons = {}

        self.setStyleSheet("""
            QFrame#EnergyTypeFilterBar {
                background-color: #fff6f8;
                border: 1px solid #f3c8d1;
                border-radius: 9px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(5)

        # Botón pequeño para alternar entre filtros rápidos (Energía <-> Generación)
        self.btn_switch_mode = QPushButton("⇄")
        self.btn_switch_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_switch_mode.setFixedSize(22, 22)
        self.btn_switch_mode.setToolTip(t("Cambiar filtro rápido (Energía / Generación)"))
        self.btn_switch_mode.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #5a2a3a;
                font-size: 12px;
                font-weight: 800;
                border: 1.5px solid #f2b8c3;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #ffdfe6;
                border-color: #f56b7b;
                color: #c8324c;
            }
        """)
        self.btn_switch_mode.clicked.connect(self.toggle_filter_mode)
        layout.addWidget(self.btn_switch_mode)

        self.lbl_tipo = QLabel(t("Energía"))
        self.lbl_tipo.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;"
        )
        layout.addWidget(self.lbl_tipo)

        # Scroll horizontal de fichas (energía o generación según modo)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(26)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 0px;
                background: transparent;
            }
        """)

        pills_container = QWidget()
        pills_container.setStyleSheet("background: transparent;")
        pills_layout = QHBoxLayout(pills_container)
        pills_layout.setContentsMargins(0, 0, 0, 0)
        pills_layout.setSpacing(3)

        for db_val, label_txt, hex_color, fg_color in ENERGY_TYPES:
            btn = QPushButton(t(label_txt))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setProperty("filter_val", db_val)
            btn.setProperty("filter_color", hex_color)
            btn.setProperty("filter_fg", fg_color)
            btn.clicked.connect(lambda ch, v=db_val: self._on_pill_clicked(v))
            pills_layout.addWidget(btn)
            self._type_buttons[db_val] = btn

        for gen_val, label_txt, hex_color, fg_color in GENERATION_FILTERS:
            btn = QPushButton(t(label_txt))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setProperty("filter_val", gen_val)
            btn.setProperty("filter_color", hex_color)
            btn.setProperty("filter_fg", fg_color)
            btn.clicked.connect(lambda ch, v=gen_val: self._on_generation_pill_clicked(v))
            btn.setVisible(False)
            pills_layout.addWidget(btn)
            self._gen_buttons[gen_val] = btn

        pills_layout.addStretch()
        self.scroll.setWidget(pills_container)
        layout.addWidget(self.scroll, stretch=1)

        # Separador visual discreto
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(18)
        sep.setStyleSheet("background-color: #f2b8c3; border: none;")
        layout.addWidget(sep)

        # Control de Zoom / Escala de cartas
        self.lbl_zoom = QLabel(t("Vista"))
        self.lbl_zoom.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #5a2a3a; border: none; background: transparent;"
        )
        layout.addWidget(self.lbl_zoom)

        for key, display in ZOOM_LEVELS:
            zbtn = QPushButton(t(display))
            zbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            zbtn.setFixedHeight(22)
            zbtn.clicked.connect(lambda ch, k=key: self._on_zoom_clicked(k))
            layout.addWidget(zbtn)
            self._zoom_buttons[key] = zbtn

        self._refresh_mode_ui()
        self._refresh_type_styles()
        self._refresh_gen_styles()
        self._refresh_zoom_styles()

    def toggle_filter_mode(self):
        self._mode = "generation" if self._mode == "energy" else "energy"
        self._refresh_mode_ui()

    def set_filter_mode(self, mode: str):
        if mode in ("energy", "generation") and self._mode != mode:
            self._mode = mode
            self._refresh_mode_ui()

    def _refresh_mode_ui(self):
        is_gen = self._mode == "generation"
        if is_gen:
            badge = f" ({self._active_type})" if self._active_type else ""
            self.lbl_tipo.setText(t("Generación") + badge)
            self.btn_switch_mode.setToolTip(t("Cambiar a filtro rápido de Energía"))
        else:
            badge = f" ({self._active_generation})" if self._active_generation else ""
            self.lbl_tipo.setText(t("Energía") + badge)
            self.btn_switch_mode.setToolTip(t("Cambiar a filtro rápido de Generación"))

        for btn in self._type_buttons.values():
            btn.setVisible(not is_gen)
        for btn in self._gen_buttons.values():
            btn.setVisible(is_gen)

    def _on_pill_clicked(self, db_val):
        if self._active_type == db_val and db_val is not None:
            # Segundo clic en el mismo tipo limpia el filtro
            self._active_type = None
        else:
            self._active_type = db_val
        self._refresh_type_styles()
        self._refresh_mode_ui()
        self.type_selected.emit(self._active_type)

    def _on_generation_pill_clicked(self, gen_val):
        if self._active_generation == gen_val and gen_val is not None:
            self._active_generation = None
        else:
            self._active_generation = gen_val
        self._refresh_gen_styles()
        self._refresh_mode_ui()
        self.generation_selected.emit(self._active_generation)

    def set_active_type(self, db_val):
        """Actualiza el estado visual sin emitir señal (para sincronizar desde el QComboBox)."""
        if db_val == "Electric":
            db_val = "Lightning"
        if db_val not in self._type_buttons:
            db_val = None
        if self._active_type != db_val:
            self._active_type = db_val
            self._refresh_type_styles()
            self._refresh_mode_ui()

    def set_active_generation(self, gen_val):
        if gen_val not in self._gen_buttons:
            gen_val = None
        if self._active_generation != gen_val:
            self._active_generation = gen_val
            self._refresh_gen_styles()
            self._refresh_mode_ui()

    def reset_filters(self):
        self._active_type = None
        self._active_generation = None
        self._refresh_type_styles()
        self._refresh_gen_styles()
        self._refresh_mode_ui()

    def _on_zoom_clicked(self, size_key: str):
        if self._active_zoom == size_key:
            return
        self._active_zoom = size_key
        self._refresh_zoom_styles()
        self.zoom_changed.emit(size_key)

    def set_active_zoom(self, size_key: str):
        if size_key in self._zoom_buttons and self._active_zoom != size_key:
            self._active_zoom = size_key
            self._refresh_zoom_styles()

    def _apply_pill_styles(self, buttons_map: dict, active_val):
        for val, btn in buttons_map.items():
            hex_c = btn.property("filter_color")
            fg_c = btn.property("filter_fg")
            is_active = (val == active_val)
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {hex_c};
                        color: {fg_c};
                        font-size: 11px;
                        font-weight: 700;
                        border: 1.5px solid {hex_c};
                        border-radius: 9px;
                        padding: 0px 7px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #ffffff;
                        color: #3f2730;
                        font-size: 11px;
                        font-weight: 600;
                        border: 1.5px solid {hex_c};
                        border-radius: 9px;
                        padding: 0px 7px;
                    }}
                    QPushButton:hover {{
                        background-color: {hex_c};
                        color: {fg_c};
                    }}
                """)

    def _refresh_type_styles(self):
        self._apply_pill_styles(self._type_buttons, self._active_type)

    def _refresh_gen_styles(self):
        self._apply_pill_styles(self._gen_buttons, self._active_generation)

    def _refresh_zoom_styles(self):
        for key, btn in self._zoom_buttons.items():
            is_active = (key == self._active_zoom)
            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f56b7b;
                        color: #ffffff;
                        font-size: 10px;
                        font-weight: 700;
                        border: 1.5px solid #e05263;
                        border-radius: 8px;
                        padding: 0px 8px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #5a2a3a;
                        font-size: 10px;
                        font-weight: 600;
                        border: 1px solid #f2b8c3;
                        border-radius: 8px;
                        padding: 0px 8px;
                    }
                    QPushButton:hover {
                        background-color: #ffdfe6;
                        border-color: #f56b7b;
                    }
                """)


def classify_rarity_tier(rarity_text: str | None) -> tuple[str, str, str]:
    """
    Clasifica cualquier texto de rareza en una forma geométrica universal apta para daltonismo.
    Retorna (shape_key, color_hex, human_tier_label).
      - 'circle'       -> Común (Círculo)
      - 'diamond'      -> Infrecuente (Rombo)
      - 'star'         -> Rara / Holo / Promo (Estrella)
      - 'double_star'  -> Ultra / Double / Illustration / EX / GX / V (Doble Estrella)
      - 'sparkle'      -> Secreta / Hyper / Rainbow (Destello 4 puntas)
    """
    if not rarity_text:
        return "circle", "#cbd5e1", "Común"
    r = str(rarity_text).strip().lower()
    if any(k in r for k in ("secret", "hyper", "rainbow", "gold", "mega_attack", "mega hyper", "black white")):
        return "sparkle", "#fb7185", "Secreta / Hyper"
    if any(k in r for k in (
        "double", "ultra", "illustration", "ex", "gx", "vmax", "vstar", "holo v",
        "ace", "amazing", "radiant", "shining", "prime", "prism", "legend", "break"
    )):
        return "double_star", "#c084fc", "Ultra / Especial"
    if "uncommon" in r:
        return "diamond", "#2dd4bf", "Infrecuente"
    if "common" in r:
        return "circle", "#e2e8f0", "Común"
    if any(k in r for k in ("rare", "holo", "promo", "classic")):
        return "star", "#fbbf24", "Rara"
    return "circle", "#cbd5e1", "Común"


def _make_star_polygon(cx: float, cy: float, r_outer: float, r_inner: float, points: int = 5) -> QPolygonF:
    poly = QPolygonF()
    for i in range(points * 2):
        angle = -math.pi / 2.0 + i * math.pi / points
        rad = r_outer if i % 2 == 0 else r_inner
        poly.append(QPointF(cx + math.cos(angle) * rad, cy + math.sin(angle) * rad))
    return poly


class RaritySymbolBadge(QWidget):
    """
    Indicador geométrico discreto de rareza en la esquina inferior derecha de cada carta.
    Permite distinguir niveles de rareza por forma (círculo, rombo, estrella, doble estrella, destello)
    sin depender únicamente del color (accesible para daltonismo).
    """

    def __init__(self, rarity_text: str | None, parent=None):
        super().__init__(parent)
        self.rarity_text = rarity_text or ""
        self.shape_key, self.color_hex, self.tier_label = classify_rarity_tier(rarity_text)
        w = 26 if self.shape_key == "double_star" else 20
        self.setFixedSize(w, 20)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        desc = f"{self.rarity_text} ({self.tier_label})" if self.rarity_text else self.tier_label
        self.setToolTip(f"{t('Rareza')}: {desc}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(QColor(15, 23, 42, 205))
        painter.setPen(QPen(QColor(255, 255, 255, 130), 1.0))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        cx = self.width() * 0.5
        cy = self.height() * 0.5
        fill = QColor(self.color_hex)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(15, 23, 42, 180), 0.7))

        if self.shape_key == "circle":
            painter.drawEllipse(QPointF(cx, cy), 4.2, 4.2)
        elif self.shape_key == "diamond":
            poly = QPolygonF([
                QPointF(cx, cy - 5.4),
                QPointF(cx + 5.0, cy),
                QPointF(cx, cy + 5.4),
                QPointF(cx - 5.0, cy),
            ])
            painter.drawPolygon(poly)
        elif self.shape_key == "star":
            painter.drawPolygon(_make_star_polygon(cx, cy + 0.4, 5.8, 2.5, points=5))
        elif self.shape_key == "double_star":
            painter.drawPolygon(_make_star_polygon(cx - 5.2, cy + 0.4, 4.7, 2.0, points=5))
            painter.drawPolygon(_make_star_polygon(cx + 5.2, cy + 0.4, 4.7, 2.0, points=5))
        elif self.shape_key == "sparkle":
            painter.drawPolygon(_make_star_polygon(cx, cy, 6.4, 2.1, points=4))
