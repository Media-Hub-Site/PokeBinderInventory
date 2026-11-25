"""Constantes, modos de cuadrícula y re-exportación de temas para Binder."""

from MyQtApp.ui.BinderCoverWidget import (
    BINDER_DESIGNS,
    BINDER_COVERS_DIR,
    resolve_design_key,
    get_design_default_interior_color,
)

BINDER_THEMES = BINDER_DESIGNS

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
