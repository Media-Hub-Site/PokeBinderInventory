"""Constantes, modos de cuadrícula y re-exportación de temas para Binder."""

from MyQtApp.ui.BinderCoverWidget import (
    BINDER_DESIGNS,
    BINDER_COVERS_DIR,
    resolve_design_key,
    get_design_default_interior_color,
)

BINDER_THEMES = BINDER_DESIGNS

PAGE_DRAG_MIME = "application/x-pokebinder-page"

BINDER_TYPES = ("normal", "toploader")
BINDER_MODE_ORDER = ["2x2", "3x3", "4x3", "3x4", "4x4"]

SLEEVE_COLOR_PRESETS = [
    ("Negro Mate", "#18181b"),
    ("Blanco Perla", "#f8fafc"),
    ("Rojo Carmesí", "#dc2626"),
    ("Azul Zafiro", "#2563eb"),
    ("Verde Esmeralda", "#16a34a"),
    ("Amarillo Pikachu", "#eab308"),
    ("Morado Gengar", "#7c3aed"),
    ("Rosa Sylveon", "#ec4899"),
    ("Naranja Charizard", "#ea580c"),
    ("Celeste Glaceon", "#06b6d4"),
    ("Dorado Metálico", "#d97706"),
    ("Plata", "#94a3b8"),
]

BINDER_MODES = {
    "2x2": {
        "rows": 2,
        "cols": 2,
        "slot_w": 130,
        "slot_h": 180,
        "card_w": 120,
        "card_h": 170,
    },
    "3x3": {
        "rows": 3,
        "cols": 3,
        "slot_w": 110,
        "slot_h": 155,
        "card_w": 100,
        "card_h": 145,
    },
    "4x3": {
        "rows": 4,
        "cols": 3,
        "slot_w": 85,
        "slot_h": 120,
        "card_w": 75,
        "card_h": 105,
    },
    "3x4": {
        "rows": 3,
        "cols": 4,
        "slot_w": 85,
        "slot_h": 120,
        "card_w": 75,
        "card_h": 105,
    },
    "4x4": {
        "rows": 4,
        "cols": 4,
        "slot_w": 85,
        "slot_h": 120,
        "card_w": 75,
        "card_h": 105,
    },
}
