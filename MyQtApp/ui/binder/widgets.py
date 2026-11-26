"""Widgets visuales interactivos de las páginas y bolsillos del Binder."""

from PyQt6.QtWidgets import QWidget, QLabel, QGridLayout, QPushButton, QApplication, QFrame
from PyQt6.QtCore import Qt, QMimeData, QPoint, QPointF, QRect, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QDrag, QPainter, QLinearGradient, QColor, QPen

from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas
from MyQtApp.app.getImgs import get_pixmap_from_zip, get_webp_pixmap
from MyQtApp.i18n import t, language_manager
from MyQtApp.ui.CardWidget import CardZoomOverlay, VariantBadgeButton, LanguageBadgeLabel, InfoIconLabel
from MyQtApp.ui.AdvancedCoverStudio import render_inside_cover_surface
from MyQtApp.ui.BinderBookAnimations import CardSlideInOverlay
from MyQtApp.ui.pixmap_cache import scale_cached_pixmap
from MyQtApp.ui.toast import show_toast
from MyQtApp.ui.binder.constants import PAGE_DRAG_MIME


class DraggableCardLabel(QLabel):
    def __init__(self, id_api, nombre_archivo, pixmap, parent=None):
        super().__init__(parent)
        self.id_api = id_api
        self.nombre_archivo = nombre_archivo
        self.drag_start_position = QPoint()
        self.setPixmap(pixmap)
        self.setScaledContents(True)
        self.setFixedSize(100, 140)
        self.setStyleSheet("border: 1px solid #ddd; border-radius: 5px;")

        self.long_press_timer = QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._on_long_press)

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._warned_empty_drag = False
                self.drag_start_position = event.pos()
                self.long_press_timer.start(260)
            super().mousePressEvent(event)
        except Exception as e:
            print(f"Error en DraggableCardLabel mousePressEvent: {e}")

    def mouseMoveEvent(self, event):
        try:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return
            if (
                getattr(self, "drag_start_position", None)
                and (event.pos() - self.drag_start_position).manhattanLength() >= QApplication.startDragDistance()
            ):
                self.long_press_timer.stop()
                if getattr(self, "remaining_copies", 1) <= 0:
                    if not getattr(self, "_warned_empty_drag", False):
                        self._warned_empty_drag = True
                        show_toast(
                            t("No te quedan copias disponibles de esta carta (ya están repartidas en tus binders)."),
                            "warning",
                            2600,
                        )
                    return

                drag = QDrag(self)
                mime_data = QMimeData()

                # Pass card ID and source info
                mime_data.setText(self.id_api)
                mime_data.setProperty("source", "inventory")
                mime_data.setProperty("nombre_archivo", self.nombre_archivo)
                mime_data.setProperty("idioma", getattr(self, "idioma", "en") or "en")
                mime_data.setProperty("variante", getattr(self, "variante", "Normal") or "Normal")
                drag.setMimeData(mime_data)

                if self.pixmap() and not self.pixmap().isNull():
                    drag.setPixmap(scale_cached_pixmap(self.pixmap(), 80, 112, keep_aspect=True, smooth=True))
                drag.setHotSpot(event.pos())

                drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        except Exception as e:
            print(f"Error en DraggableCardLabel mouseMoveEvent: {e}")

    def mouseReleaseEvent(self, event):
        try:
            if self.long_press_timer.isActive():
                self.long_press_timer.stop()
            super().mouseReleaseEvent(event)
        except Exception as e:
            print(f"Error en DraggableCardLabel mouseReleaseEvent: {e}")

    def _on_long_press(self):
        parent_win = self.window()
        pix = self.pixmap()
        idioma = getattr(self, "idioma", None)
        if not idioma and self.id_api:
            try:
                session = SessionLocal()
                c_db = session.query(Cartas).filter(Cartas.id_api == self.id_api).first()
                session.close()
                if c_db and c_db.idioma:
                    idioma = c_db.idioma
            except Exception:
                pass

        card_lang = idioma or language_manager.current_language
        if self.nombre_archivo:
            hi_pix = get_webp_pixmap(self.id_api, self.nombre_archivo, card_lang, size=(450, 630))
            if not hi_pix:
                hi_pix = get_pixmap_from_zip(self.nombre_archivo, size=(450, 630), id_api=self.id_api)
            if hi_pix:
                pix = hi_pix
        if parent_win and pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(
                pix,
                origin_global,
                id_api=self.id_api,
                nombre_archivo=self.nombre_archivo,
                idioma=idioma,
                variante=getattr(self, "variante", None),
            )


class BinderSlot(QLabel):
    def __init__(self, page_index, slot_index, parent=None, binder_view=None, slot_w=120, slot_h=170, card_w=110, card_h=160):
        super().__init__(parent)
        self.page_index = page_index
        self.slot_index = slot_index
        self.binder_view = binder_view
        self.id_api = None
        self.nombre_archivo = None
        self.idioma = None
        self.variante = "Normal"
        self.selected = False
        self.slot_w = slot_w
        self.slot_h = slot_h
        self.card_w = card_w
        self.card_h = card_h
        self.drag_start_position = QPoint()
        self.variant_badge = None
        self.lang_badge = None
        self.info_btn = None
        self.carta_obj = None

        self.setFixedSize(slot_w, slot_h)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.update_style()

        self.long_press_timer = QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._on_long_press)

    def set_selected(self, val: bool):
        if not self.id_api:
            self.selected = False
        else:
            self.selected = val
        self.update_style()
        if self.binder_view and hasattr(self.binder_view, "update_selection_state"):
            self.binder_view.update_selection_state()

    def _on_long_press(self):
        if not self.id_api:
            return
        parent_win = self.window()
        pix = self.pixmap()
        idioma = getattr(self, "idioma", None)
        if not idioma and self.id_api:
            try:
                session = SessionLocal()
                c_db = session.query(Cartas).filter(Cartas.id_api == self.id_api).first()
                session.close()
                if c_db and c_db.idioma:
                    idioma = c_db.idioma
            except Exception:
                pass

        card_lang = idioma or language_manager.current_language
        if self.nombre_archivo:
            hi_pix = get_webp_pixmap(self.id_api, self.nombre_archivo, card_lang, size=(450, 630))
            if not hi_pix:
                hi_pix = get_pixmap_from_zip(self.nombre_archivo, size=(450, 630), id_api=self.id_api)
            if hi_pix:
                pix = hi_pix
        if parent_win and pix and not pix.isNull():
            origin_global = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            overlay = CardZoomOverlay(parent_win)
            overlay.show_zoom(
                pix,
                origin_global,
                id_api=self.id_api,
                nombre_archivo=self.nombre_archivo,
                idioma=idioma,
                variante=getattr(self, "variante", None),
            )

    def update_style(self):
        # Adaptar contraste del bolsillo al color interior de la hoja (Issue #28)
        is_light_page = False
        try:
            p = self.parent()
            if p is not None and hasattr(p, "interior_color") and p.interior_color:
                ic = QColor(p.interior_color)
                if ic.isValid():
                    luma = 0.299 * ic.red() + 0.587 * ic.green() + 0.114 * ic.blue()
                    is_light_page = luma > 155
        except Exception:
            is_light_page = False

        if self.id_api:
            if self.selected:
                self.setStyleSheet("""
                    QLabel {
                        background-color: rgba(225, 29, 72, 0.28);
                        border: 3px solid #f43f5e;
                        border-radius: 7px;
                    }
                """)
            else:
                border_col = "rgba(15, 23, 42, 0.25)" if is_light_page else "rgba(255, 255, 255, 0.22)"
                bg_col = "rgba(15, 23, 42, 0.04)" if is_light_page else "rgba(255, 255, 255, 0.04)"
                self.setStyleSheet(f"""
                    QLabel {{
                        background-color: {bg_col};
                        border: 1.5px solid {border_col};
                        border-radius: 7px;
                    }}
                """)
        else:
            self.selected = False
            empty_bg = "rgba(15, 23, 42, 0.05)" if is_light_page else "rgba(255, 255, 255, 0.05)"
            empty_border = "rgba(15, 23, 42, 0.28)" if is_light_page else "rgba(255, 255, 255, 0.22)"
            hover_bg = "rgba(244, 143, 177, 0.16)" if is_light_page else "rgba(255, 255, 255, 0.11)"
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {empty_bg};
                    border: 1.5px dashed {empty_border};
                    border-radius: 7px;
                }}
                QLabel:hover {{
                    background-color: {hover_bg};
                    border: 1.5px dashed rgba(244, 143, 177, 0.85);
                }}
            """)
            self.clear()

    def set_card(self, id_api, nombre_archivo, pixmap, idioma=None, variante="Normal", carta=None, animate_insert=False):
        self.id_api = id_api
        self.nombre_archivo = nombre_archivo
        self.idioma = idioma
        self.variante = variante or "Normal"
        self.carta_obj = carta
        self.selected = False
        scaled_pix = None
        if pixmap:
            scaled_pix = scale_cached_pixmap(pixmap, self.card_w, self.card_h, keep_aspect=True, smooth=True)
            self.setPixmap(scaled_pix)

        # Botón vertical de variante (arriba a la izquierda)
        if not self.variant_badge:
            self.variant_badge = VariantBadgeButton(self.id_api, self.variante, self)
            self.variant_badge.variant_changed.connect(self._on_slot_variant_changed)
        else:
            self.variant_badge.id_api = self.id_api
            self.variant_badge.set_variante(self.variante)
        self.variant_badge.move(3, 3)

        # Burbuja de información de la carta (arriba a la derecha, Issue #17)
        if self.info_btn:
            self.info_btn.deleteLater()
            self.info_btn = None
        if carta is not None:
            self.info_btn = InfoIconLabel(carta, self)
            self.info_btn.move(self.slot_w - 26, 3)

        # Insignia de idioma (abajo a la izquierda)
        if self.idioma:
            if not self.lang_badge:
                self.lang_badge = LanguageBadgeLabel(self.idioma, self)
            else:
                self.lang_badge.setText(self.idioma)
            bh = self.lang_badge.height()
            self.lang_badge.move(3, self.slot_h - bh - 3)
        elif self.lang_badge:
            self.lang_badge.hide()

        self.apply_details_visibility()
        self.update_style()

        # Animación táctil de inserción en mica (Card Slide-In) al soltar carta
        if animate_insert and scaled_pix and not scaled_pix.isNull():
            from MyQtApp.config import load_settings
            if load_settings().get("animaciones", True):
                if getattr(self, "_slide_overlay", None):
                    try:
                        self._slide_overlay.deleteLater()
                    except Exception:
                        pass
                overlay = CardSlideInOverlay(self, scaled_pix)
                self._slide_overlay = overlay

                def _on_slide_done():
                    self._slide_overlay = None
                    self.apply_details_visibility()

                overlay.animation_finished.connect(_on_slide_done)

    def apply_details_visibility(self):
        """Muestra u oculta variante, burbuja de info e idioma según el toggle 'Ver detalles' (Issue #17)."""
        show_details = bool(self.id_api and getattr(self.binder_view, "show_card_details", False))
        if self.variant_badge:
            if show_details:
                self.variant_badge.show()
                self.variant_badge.raise_()
            else:
                self.variant_badge.hide()
        if self.info_btn:
            if show_details:
                self.info_btn.show()
                self.info_btn.raise_()
            else:
                self.info_btn.hide()
        if self.lang_badge:
            if show_details and self.idioma:
                self.lang_badge.show()
                self.lang_badge.raise_()
            else:
                self.lang_badge.hide()

    def _on_slot_variant_changed(self, id_api, nueva_variante):
        self.variante = nueva_variante
        if self.binder_view and hasattr(self.binder_view, "update_slot_variant"):
            self.binder_view.update_slot_variant(self.page_index, self.slot_index, nueva_variante)

    def clear_card(self, animate_remove: bool = False):
        old_pix = None
        if animate_remove:
            try:
                from MyQtApp.config import load_settings
                if load_settings().get("animaciones", True) and self.pixmap() and not self.pixmap().isNull():
                    old_pix = self.pixmap().copy()
            except Exception:
                old_pix = None

        self.id_api = None
        self.nombre_archivo = None
        self.idioma = None
        self.variante = "Normal"
        self.carta_obj = None
        self.selected = False
        if self.variant_badge:
            self.variant_badge.hide()
        if self.info_btn:
            self.info_btn.hide()
        if self.lang_badge:
            self.lang_badge.hide()
        self.clear()
        self.update_style()

        if old_pix is not None and not old_pix.isNull():
            try:
                self._slide_out_overlay = CardSlideInOverlay(self, old_pix, reverse=True)
            except Exception as e:
                print(f"Error en animación de salida de carta: {e}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PAGE_DRAG_MIME):
            p = self.parent()
            if p and hasattr(p, "set_page_drop_hover"):
                p.set_page_drop_hover(True)
            event.acceptProposedAction()
            return
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        p = self.parent()
        if p and hasattr(p, "set_page_drop_hover"):
            p.set_page_drop_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(PAGE_DRAG_MIME):
            p = self.parent()
            if p and hasattr(p, "set_page_drop_hover"):
                p.set_page_drop_hover(False)
            try:
                src_page = int(bytes(event.mimeData().data(PAGE_DRAG_MIME)).decode("utf-8"))
            except Exception:
                event.ignore()
                return
            if self.binder_view and hasattr(self.binder_view, "swap_pages"):
                self.binder_view.swap_pages(src_page, self.page_index)
            event.acceptProposedAction()
            return
        try:
            card_id = event.mimeData().text()
            source_slot = event.mimeData().property("source_slot")
            nombre_archivo = event.mimeData().property("nombre_archivo")
            idioma = event.mimeData().property("idioma")
            variante = event.mimeData().property("variante") or "Normal"

            if card_id:
                if self.binder_view:
                    self.binder_view.handle_drop(
                        self.page_index,
                        self.slot_index,
                        card_id,
                        source_slot=source_slot,
                        nombre_archivo=nombre_archivo,
                        idioma=idioma,
                        variante=variante,
                    )
                event.accept()
        except Exception as e:
            print(f"Error en BinderSlot dropEvent: {e}")

    # Allow dragging FROM the slot too
    def mousePressEvent(self, event):
        if getattr(self.binder_view, "move_pages_mode", False) and event.button() == Qt.MouseButton.LeftButton:
            p = self.parent()
            if p and hasattr(p, "_begin_page_press"):
                p._begin_page_press(self.mapTo(p, event.position().toPoint()))
                event.accept()
                return
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.id_api:
                self.drag_start_position = event.pos()
                self.long_press_timer.start(260)
        except Exception as e:
            print(f"Error en BinderSlot mousePressEvent: {e}")

    def mouseMoveEvent(self, event):
        if getattr(self.binder_view, "move_pages_mode", False):
            if event.buttons() & Qt.MouseButton.LeftButton:
                p = self.parent()
                if p and hasattr(p, "_handle_page_move"):
                    p._handle_page_move(self.mapTo(p, event.position().toPoint()))
                    event.accept()
                    return
            return
        try:
            if not self.id_api:
                return
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return
            if (
                getattr(self, "drag_start_position", None)
                and (event.pos() - self.drag_start_position).manhattanLength() >= QApplication.startDragDistance()
            ):
                self.long_press_timer.stop()

                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setText(self.id_api)
                mime_data.setProperty("source", "binder")
                mime_data.setProperty("source_slot", f"{self.page_index}_{self.slot_index}")
                mime_data.setProperty("nombre_archivo", self.nombre_archivo)
                mime_data.setProperty("idioma", getattr(self, "idioma", "en") or "en")
                mime_data.setProperty("variante", getattr(self, "variante", "Normal") or "Normal")
                drag.setMimeData(mime_data)

                if self.pixmap() and not self.pixmap().isNull():
                    drag.setPixmap(scale_cached_pixmap(self.pixmap(), 80, 112, keep_aspect=True, smooth=True))
                    drag.setHotSpot(event.pos())

                drag.exec(Qt.DropAction.CopyAction)
        except Exception as e:
            print(f"Error en BinderSlot mouseMoveEvent: {e}")

    def mouseReleaseEvent(self, event):
        if getattr(self.binder_view, "move_pages_mode", False) and event.button() == Qt.MouseButton.LeftButton:
            p = self.parent()
            if p and hasattr(p, "_finish_page_release"):
                p._finish_page_release(self.mapTo(p, event.position().toPoint()))
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            if self.long_press_timer.isActive():
                self.long_press_timer.stop()
                if self.id_api:
                    self.set_selected(not self.selected)
        super().mouseReleaseEvent(event)


class BinderPage(QWidget):
    def __init__(self, page_index, binder_view, rows, cols, slot_w, slot_h, card_w, card_h, is_left=True, interior_color=None, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.binder_view = binder_view
        self.rows = rows
        self.cols = cols
        self.is_left = is_left
        self.interior_color = interior_color or "#18181e"
        self._move_mode = False
        self._move_selected = False
        self._page_drop_hover = False
        self._page_drag_start = None

        self.setAcceptDrops(True)

        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self.slots = []
        for r in range(rows):
            for c in range(cols):
                slot_idx = r * cols + c
                slot = BinderSlot(
                    page_index,
                    slot_idx,
                    parent=self,
                    binder_view=binder_view,
                    slot_w=slot_w,
                    slot_h=slot_h,
                    card_w=card_w,
                    card_h=card_h,
                )
                layout.addWidget(slot, r, c)
                self.slots.append(slot)

        self.page_move_handle = QLabel(f"⇄ {t('Hoja')} {self.page_index + 1} · {t('Arrastrar')}", self)
        self.page_move_handle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.page_move_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_move_handle.adjustSize()
        self.page_move_handle.hide()
        self._refresh_move_handle_style()

    def _refresh_move_handle_style(self):
        if self._move_selected:
            txt = f"⇄ {t('Hoja')} {self.page_index + 1} ({t('Seleccionada')})"
            bg = "rgba(245, 158, 11, 235)"
            bd = "#fef08a"
        else:
            txt = f"⇄ {t('Hoja')} {self.page_index + 1} · {t('Arrastrar')}"
            bg = "rgba(2, 132, 199, 225)"
            bd = "#bae6fd"
        self.page_move_handle.setText(txt)
        self.page_move_handle.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: #ffffff;
                border: 1.5px solid {bd};
                border-radius: 10px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 800;
            }}
        """)
        self.page_move_handle.adjustSize()
        self._position_move_handle()

    def _position_move_handle(self):
        if hasattr(self, "page_move_handle") and self.page_move_handle:
            hw = self.page_move_handle.width()
            hx = max(6, (self.width() - hw) // 2)
            self.page_move_handle.move(hx, 8)
            self.page_move_handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_move_handle()

    def set_move_mode(self, enabled: bool, selected: bool = False):
        self._move_mode = bool(enabled)
        self._move_selected = bool(enabled and selected)
        if not self._move_mode:
            self._page_drop_hover = False
            self._page_drag_start = None
            self.page_move_handle.hide()
            self.unsetCursor()
        else:
            self._refresh_move_handle_style()
            self.page_move_handle.show()
            self.page_move_handle.raise_()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def set_page_drop_hover(self, hovering: bool):
        val = bool(hovering)
        if self._page_drop_hover != val:
            self._page_drop_hover = val
            self.update()

    def _begin_page_press(self, pos: QPoint):
        if self._move_mode:
            self._page_drag_start = pos

    def _handle_page_move(self, pos: QPoint):
        if not self._move_mode or self._page_drag_start is None:
            return
        if (pos - self._page_drag_start).manhattanLength() >= QApplication.startDragDistance():
            self._page_drag_start = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(PAGE_DRAG_MIME, str(self.page_index).encode("utf-8"))
            drag.setMimeData(mime)
            pix = self.grab()
            if not pix.isNull():
                thumb = scale_cached_pixmap(pix, 118, 160, keep_aspect=True, smooth=True)
                drag.setPixmap(thumb)
                drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
            drag.exec(Qt.DropAction.MoveAction)

    def _finish_page_release(self, _pos: QPoint):
        if self._move_mode and self._page_drag_start is not None:
            self._page_drag_start = None
            if self.binder_view and hasattr(self.binder_view, "on_page_move_clicked"):
                self.binder_view.on_page_move_clicked(self.page_index)

    def mousePressEvent(self, event):
        if self._move_mode and event.button() == Qt.MouseButton.LeftButton:
            self._begin_page_press(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._move_mode and (event.buttons() & Qt.MouseButton.LeftButton):
            self._handle_page_move(event.position().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._move_mode and event.button() == Qt.MouseButton.LeftButton:
            self._finish_page_release(event.position().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PAGE_DRAG_MIME):
            self.set_page_drop_hover(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.set_page_drop_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.set_page_drop_hover(False)
        if event.mimeData().hasFormat(PAGE_DRAG_MIME):
            try:
                src_page = int(bytes(event.mimeData().data(PAGE_DRAG_MIME)).decode("utf-8"))
            except Exception:
                event.ignore()
                return
            if self.binder_view and hasattr(self.binder_view, "swap_pages"):
                self.binder_view.swap_pages(src_page, self.page_index)
            event.acceptProposedAction()
            return
        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Base de hoja personalizable estilo Ultra PRO (negro mate por defecto o color elegido)
        base_col = QColor(self.interior_color)
        if not base_col.isValid():
            base_col = QColor(24, 24, 30)
        c_top = base_col.lighter(120)
        c_top.setAlpha(242)
        c_mid = QColor(base_col)
        c_mid.setAlpha(246)
        c_bot = base_col.darker(122)
        c_bot.setAlpha(250)

        luma = 0.299 * base_col.red() + 0.587 * base_col.green() + 0.114 * base_col.blue()
        seam_col = QColor(20, 20, 30, 50) if luma > 155 else QColor(255, 255, 255, 26)
        border_col = QColor(20, 20, 30, 70) if luma > 155 else QColor(255, 255, 255, 40)

        sheet_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        sheet_grad.setColorAt(0.0, c_top)
        sheet_grad.setColorAt(0.5, c_mid)
        sheet_grad.setColorAt(1.0, c_bot)
        painter.setBrush(sheet_grad)
        painter.setPen(QPen(border_col, 1.2))
        painter.drawRoundedRect(rect, 7, 7)

        seam_pen = QPen(seam_col, 1.0, Qt.PenStyle.DotLine)
        painter.setPen(seam_pen)
        if self.cols > 1:
            for c in range(1, self.cols):
                x = rect.left() + (rect.width() * c / self.cols)
                painter.drawLine(QPointF(x, rect.top() + 6), QPointF(x, rect.bottom() - 6))
        if self.rows > 1:
            for r in range(1, self.rows):
                y = rect.top() + (rect.height() * r / self.rows)
                painter.drawLine(QPointF(rect.left() + 6, y), QPointF(rect.right() - 6, y))

        sheen = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 22))
        sheen.setColorAt(0.30, QColor(255, 255, 255, 5))
        sheen.setColorAt(0.55, QColor(255, 255, 255, 14))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sheen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        hx = rect.left() + 12 if self.is_left else rect.right() - 12
        hy = rect.bottom() - 12
        holo = QLinearGradient(hx - 5, hy - 5, hx + 5, hy + 5)
        holo.setColorAt(0.0, QColor(180, 230, 255, 110))
        holo.setColorAt(0.5, QColor(255, 200, 240, 125))
        holo.setColorAt(1.0, QColor(210, 255, 210, 110))
        painter.setBrush(holo)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 0.8))
        painter.drawEllipse(QPointF(hx, hy), 4.5, 4.5)

        if self._page_drop_hover:
            painter.setBrush(QColor(56, 189, 248, 52))
            painter.setPen(QPen(QColor("#38bdf8"), 3.0))
            painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 7, 7)
        elif self._move_selected:
            painter.setBrush(QColor(245, 158, 11, 28))
            painter.setPen(QPen(QColor("#f59e0b"), 3.0))
            painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 7, 7)
        elif self._move_mode:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(56, 189, 248, 150), 1.6, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 7, 7)

    def get_slot(self, slot_index):
        if 0 <= slot_index < len(self.slots):
            return self.slots[slot_index]
        return None


class BinderInsideCoverWidget(QFrame):
    """
    Cara interior de la tapa delantera del Binder en el primer pliego (Issue #57 y #59).
    Replica el mismo tamaño que BinderPage y permite editar su decoración, color, bolsillo y emblema.
    """

    edit_inside_requested = pyqtSignal()

    def __init__(
        self,
        rows,
        cols,
        slot_w,
        slot_h,
        folder_name="Mi Binder",
        interior_color=None,
        advanced_design=None,
        locked: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.folder_name = folder_name or "Mi Binder"
        self.interior_color = interior_color or "#18181e"
        self.advanced_design = advanced_design
        self.locked = bool(locked)
        w = cols * slot_w + (cols - 1) * 10 + 20
        h = rows * slot_h + (rows - 1) * 10 + 20
        self.setFixedSize(w, h)

        self.btn_edit_inside = QPushButton(t("Editar portada"), self)
        self.btn_edit_inside.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_inside.setToolTip(t("Personalizar el interior de la portada del binder (stickers, color, texto)"))
        self.btn_edit_inside.setStyleSheet("""
            QPushButton {
                background-color: rgba(15, 23, 42, 0.72);
                color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #f56b7b;
                border-color: #ffffff;
                color: #ffffff;
            }
        """)
        self.btn_edit_inside.adjustSize()
        self.btn_edit_inside.move(max(12, w - self.btn_edit_inside.width() - 12), 12)
        self.btn_edit_inside.clicked.connect(self.edit_inside_requested.emit)
        self.btn_edit_inside.setVisible(not self.locked)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.locked:
            self.edit_inside_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            render_inside_cover_surface(
                painter,
                rect,
                self.interior_color,
                self.folder_name,
                advanced_design=self.advanced_design,
                include_advanced=True,
            )
        finally:
            painter.end()
