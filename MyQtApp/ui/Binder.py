"""Fachada de compatibilidad hacia atrás; la implementación vive en MyQtApp.ui.binder."""

from MyQtApp.ui.binder import (
    BINDER_MODES,
    BINDER_THEMES,
    BINDER_DESIGNS,
    BINDER_COVERS_DIR,
    resolve_design_key,
    get_design_default_interior_color,
    DraggableCardLabel,
    BinderSlot,
    BinderPage,
    BinderInsideCoverWidget,
    InventorySidebar,
    BinderView,
)

__all__ = [
    "BINDER_MODES",
    "BINDER_THEMES",
    "BINDER_DESIGNS",
    "BINDER_COVERS_DIR",
    "resolve_design_key",
    "get_design_default_interior_color",
    "DraggableCardLabel",
    "BinderSlot",
    "BinderPage",
    "BinderInsideCoverWidget",
    "InventorySidebar",
    "BinderView",
]
