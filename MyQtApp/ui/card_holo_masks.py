"""Generación automática, caché en disco y composición de máscaras físicas (White Underprint) por carta."""

from __future__ import annotations

from collections import OrderedDict
import os
import re
import threading
import unicodedata

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from MyQtApp.config import HOLO_MASKS_DIR

MASK_SCHEMA_VERSION = "v1"
CANONICAL_W = 360
CANONICAL_H = 504

_MAX_MASK_CACHE = 128
_MAX_SCALED_MASK_CACHE = 256

_CACHE_LOCK = threading.RLock()
_MASK_QIMAGE_CACHE: "OrderedDict[str, tuple[QImage, bool]]" = OrderedDict()
_SCALED_MASK_CACHE: "OrderedDict[tuple[int, int, int], QImage]" = OrderedDict()

_REMBG_LOCK = threading.Lock()
_REMBG_SESSION = None
_REMBG_UNAVAILABLE = False

_WINDOW_HOLO_PROFILES = {"rare_holo", "cosmo_holo", "cracked_ice", "confetti_holo"}
_REVERSE_FRAME_PROFILES = {"reverse_holo", "pokeball_holo", "masterball_holo"}
_SPLASH_HYBRID_PROFILES = {"amazing_rare", "prism_star"}
_DUAL_ARCHETYPE_PROFILES = {"shiny_radiant", "classic_gold_break", "double_rare_ex_v"}
_SATIN_INTERIOR_PROFILES = {"illustration_rare", "special_illustration_rare", "double_rare_ex_v"}
_RULE_BOX_ESPECIAL = {"ex", "v", "vmax", "vstar", "gx"}
_RULE_BOX_RARITIES = {
    "double rare",
    "rare holo v",
    "rare holo vmax",
    "rare holo vstar",
    "rare holo gx",
    "rare holo ex",
    "hyper rare",
}
_EVOLVED_STAGES = {"stage 1", "stage 2", "restored"}


def _norm(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value).strip())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def _safe_token(value: str | None, fallback: str = "card") -> str:
    raw = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value or "").strip())
    raw = raw.strip("._")
    return raw[:64] if raw else fallback


def _touch_lru(cache: OrderedDict, key, value, max_size: int):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > max_size:
        cache.popitem(last=False)


def _get_rembg_session():
    """Carga perezosamente el modelo ONNX local sin disparar descargas de red."""
    global _REMBG_SESSION, _REMBG_UNAVAILABLE
    if _REMBG_UNAVAILABLE:
        return None
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION

    with _REMBG_LOCK:
        if _REMBG_UNAVAILABLE:
            return None
        if _REMBG_SESSION is not None:
            return _REMBG_SESSION

        u2_home = os.environ.get("U2NET_HOME") or os.path.join(os.path.expanduser("~"), ".u2net")
        u2_path = os.path.join(u2_home, "u2net.onnx")
        isnet_path = os.path.join(u2_home, "isnet-general-use.onnx")

        model_name = None
        if os.path.exists(u2_path):
            model_name = "u2net"
        elif os.path.exists(isnet_path):
            model_name = "isnet-general-use"

        if not model_name:
            _REMBG_UNAVAILABLE = True
            return None

        try:
            from rembg import new_session

            _REMBG_SESSION = new_session(model_name, providers=["CPUExecutionProvider"])
            return _REMBG_SESSION
        except Exception:
            _REMBG_UNAVAILABLE = True
            return None


def _run_rembg_mask(bgr_crop: np.ndarray) -> np.ndarray | None:
    """Ejecuta rembg sobre un recorte BGR con relleno espejo BORDER_REFLECT_101."""
    sess = _get_rembg_session()
    if sess is None or bgr_crop is None or bgr_crop.size == 0:
        return None
    try:
        from rembg import remove

        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        mask = np.array(remove(Image.fromarray(rgb), session=sess, only_mask=True))
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        return mask.astype(np.uint8)
    except Exception:
        return None


def qimage_to_bgr(
    qimg: QImage | None,
    size: tuple[int, int] = (CANONICAL_W, CANONICAL_H),
) -> np.ndarray | None:
    """Convierte un QImage de forma segura (respetando bytesPerLine) a BGR uint8."""
    if qimg is None or qimg.isNull():
        return None
    img = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    if img.isNull() or img.width() <= 0 or img.height() <= 0:
        return None

    bpl = img.bytesPerLine()
    ptr = img.constBits()
    ptr.setsize(img.height() * bpl)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((img.height(), bpl // 4, 4))[:, : img.width(), :]
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    if size and (bgr.shape[1] != int(size[0]) or bgr.shape[0] != int(size[1])):
        bgr = cv2.resize(bgr, (int(size[0]), int(size[1])), interpolation=cv2.INTER_AREA)
    return bgr


def mask_u8_to_alpha_qimage(mask_u8: np.ndarray) -> QImage:
    """Convierte una máscara uint8 (0=mate, 255=foil) directamente a QImage ARGB32 premultiplicada."""
    h, w = mask_u8.shape[:2]
    clipped = np.clip(mask_u8, 0, 255).astype(np.uint8)
    premult = np.repeat(clipped[:, :, None], 4, axis=2)
    return QImage(premult.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()


def _grayscale_qimage_to_alpha_qimage(gray_qimg: QImage) -> QImage | None:
    """Convierte un QImage cargado desde disco en máscara alfa RGBA."""
    if gray_qimg is None or gray_qimg.isNull():
        return None
    g = gray_qimg.convertToFormat(QImage.Format.Format_Grayscale8)
    if g.isNull() or g.width() <= 0 or g.height() <= 0:
        return None
    bpl = g.bytesPerLine()
    ptr = g.constBits()
    ptr.setsize(g.height() * bpl)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((g.height(), bpl))[:, : g.width()].copy()
    return mask_u8_to_alpha_qimage(arr)


def get_scaled_mask_qimage(mask_qimg: QImage, width: int, height: int) -> QImage:
    """Obtiene una máscara pre-escalada en Format_ARGB32_Premultiplied desde caché LRU."""
    w = max(1, int(width))
    h = max(1, int(height))
    key = (int(mask_qimg.cacheKey()), w, h)
    with _CACHE_LOCK:
        cached = _SCALED_MASK_CACHE.get(key)
        if cached is not None and not cached.isNull():
            _SCALED_MASK_CACHE.move_to_end(key)
            return cached

    if mask_qimg.width() == w and mask_qimg.height() == h:
        scaled = mask_qimg
    else:
        scaled = mask_qimg.scaled(
            w,
            h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    if scaled.format() != QImage.Format.Format_ARGB32_Premultiplied:
        scaled = scaled.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    with _CACHE_LOCK:
        _touch_lru(_SCALED_MASK_CACHE, key, scaled, _MAX_SCALED_MASK_CACHE)
    return scaled


def detect_art_window(bgr: np.ndarray) -> tuple[tuple[int, int, int, int], float, int, bool]:
    """Detecta automáticamente la ventana de ilustración y distingue cartas con marco vs Full Art."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    dy = np.abs(np.diff(gray, axis=0))
    row_score = dy[:, int(w * 0.20) : int(w * 0.80)].mean(axis=1)
    y_top_s = int(h * 0.082)
    y_top_band = row_score[y_top_s : int(h * 0.135)]
    y1 = y_top_s + int(np.argmax(y_top_band))

    y_bot_s = int(h * 0.450)
    y_bot_band = row_score[y_bot_s : int(h * 0.525)]
    y2 = y_bot_s + int(np.argmax(y_bot_band))

    dx = np.abs(np.diff(gray, axis=1))
    col_score = dx[y1 + 8 : max(y1 + 16, y2 - 8), :].mean(axis=0)
    x_left_s = int(w * 0.060)
    x_left_band = col_score[x_left_s : int(w * 0.135)]
    x1 = x_left_s + int(np.argmax(x_left_band))

    x_right_s = int(w * 0.865)
    x_right_band = col_score[x_right_s : int(w * 0.940)]
    x2 = x_right_s + int(np.argmax(x_right_band))

    p_top = float(y_top_band.max() - np.median(y_top_band))
    p_bot = float(y_bot_band.max() - np.median(y_bot_band))
    p_left = float(x_left_band.max() - np.median(x_left_band))
    p_right = float(x_right_band.max() - np.median(x_right_band))
    prom = (p_top + p_bot + p_left + p_right) / 4.0
    sides_ok = sum(1 for p in (p_top, p_bot, p_left, p_right) if p > 14.0)
    is_windowed = sides_ok >= 3 and prom >= 23.0

    if is_windowed and (x2 - x1) >= int(w * 0.70) and (y2 - y1) >= int(h * 0.30):
        art_rect = (int(x1), int(y1), int(x2), int(y2))
    else:
        art_rect = (int(w * 0.082), int(h * 0.098), int(w * 0.918), int(h * 0.482))

    return art_rect, prom, sides_ok, is_windowed


def detect_silver_holo_border(bgr: np.ndarray, set_id: str | None = None) -> bool:
    """Identifica bordes plateados/holo neutros (SV, ex clásicos, LV.X, Radiant) frente a bordes amarillos."""
    h, w = bgr.shape[:2]
    y_a, y_b = int(h * 0.15), int(h * 0.85)
    left_strip = bgr[y_a:y_b, 4:13]
    right_strip = bgr[y_a:y_b, max(14, w - 13) : max(15, w - 4)]
    strips = np.concatenate([left_strip, right_strip], axis=1)
    hsv = cv2.cvtColor(strips, cv2.COLOR_BGR2HSV)
    med_sat = float(np.median(hsv[:, :, 1]))
    med_val = float(np.median(hsv[:, :, 2]))
    return med_sat < 42.0 and 90.0 <= med_val <= 242.0


def resolve_effective_archetype(
    profile_key: str,
    is_windowed: bool,
    rarity: str | None = None,
    especial_type: str | None = None,
    prom: float = 0.0,
) -> str:
    """Determina la geometría física efectiva de lámina holo según perfil y diseño visual real."""
    if profile_key == "matte_none":
        return "none"
    if profile_key in _REVERSE_FRAME_PROFILES:
        return "reverse_frame" if is_windowed else "full_art_etched"
    if profile_key in _WINDOW_HOLO_PROFILES:
        return "art_window_bg" if is_windowed else "full_art_etched"
    if profile_key in _SPLASH_HYBRID_PROFILES:
        return "splash_hybrid" if is_windowed else "full_art_etched"
    if profile_key in _DUAL_ARCHETYPE_PROFILES:
        return "splash_hybrid" if is_windowed else "full_art_etched"

    rarity_norm = _norm(rarity)
    if is_windowed and rarity_norm == "rare secret" and prom > 38.0:
        return "splash_hybrid"
    return "full_art_etched"


def _filter_glyph_components(binary_img: np.ndarray, max_comp_w: int, max_comp_h: int) -> np.ndarray:
    """Mantiene trazos tipográficos y símbolos mediante tabla vectorizada O(N)."""
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
    if num <= 1:
        return np.zeros_like(binary_img)
    areas = stats[1:, cv2.CC_STAT_AREA]
    widths = stats[1:, cv2.CC_STAT_WIDTH]
    heights = stats[1:, cv2.CC_STAT_HEIGHT]
    valid = (areas >= 4) & (widths <= max_comp_w) & (heights <= max_comp_h)
    keep = np.zeros(num, dtype=np.uint8)
    keep[1:][valid] = 255
    return keep[labels]


def _detect_evolution_box_rect(
    is_windowed: bool,
    art_rect: tuple[int, int, int, int],
    w: int,
    h: int,
    stage: str | None,
    especial_type: str | None,
) -> tuple[int, int, int, int] | None:
    stage_norm = _norm(stage)
    esp_norm = _norm(especial_type)
    if stage_norm not in _EVOLVED_STAGES and esp_norm not in {"vmax", "vstar"}:
        return None
    if is_windowed and art_rect[0] > int(w * 0.095):
        return (int(w * 0.028), int(h * 0.032), int(w * 0.205), int(h * 0.168))
    return (int(w * 0.028), int(h * 0.032), int(w * 0.195), int(h * 0.175))


def _paint_evo_mask(
    target: np.ndarray,
    evo_rect: tuple[int, int, int, int] | None,
    is_windowed: bool,
    art_rect: tuple[int, int, int, int],
    w: int,
    val: float,
):
    """Enmascara el recuadro de pre-evolución (elipse en cartas vintage octogonales, rectángulo redondeado en modernas)."""
    if evo_rect is None:
        return
    ex1, ey1, ex2, ey2 = evo_rect
    if is_windowed and art_rect[0] > int(w * 0.095):
        cx = (ex1 + ex2) // 2
        cy = (ey1 + ey2) // 2
        rx = max(4, (ex2 - ex1) // 2)
        ry = max(4, (ey2 - ey1) // 2)
        if target.dtype == np.uint8:
            cv2.ellipse(target, (cx, cy), (rx, ry), 0, 0, 360, int(val), -1)
        else:
            yy, xx = np.ogrid[ey1:ey2, ex1:ex2]
            mask = (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2) <= 1.0
            region = target[ey1:ey2, ex1:ex2]
            region[mask] = val
    else:
        target[ey1:ey2, ex1:ex2] = val


def detect_opaque_ui_mask(
    bgr: np.ndarray,
    is_windowed: bool,
    art_rect: tuple[int, int, int, int],
    rarity: str | None = None,
    especial_type: str | None = None,
    stage: str | None = None,
) -> np.ndarray:
    """Detecta tinta opaca mate: tipografía, orbes de energía, Ability, evolución y Rule Box."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    min_rgb = np.min(bgr, axis=2)

    # Restringir tipografía a bandas de UI antes del análisis de componentes conexas
    zones = np.zeros((h, w), dtype=np.uint8)
    zones[int(h * 0.020) : int(h * 0.125), int(w * 0.02) : int(w * 0.98)] = 255
    zones[int(h * 0.100) : int(h * 0.175), int(w * 0.60) : int(w * 0.97)] = 255
    zones[int(h * 0.465) : int(h * 0.992), int(w * 0.02) : int(w * 0.98)] = 255

    k11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    bhat_g = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k11)
    bhat_m = cv2.morphologyEx(min_rgb, cv2.MORPH_BLACKHAT, k11)
    that_g = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k11)

    thin_dark_raw = (
        (zones > 0) & (((bhat_g > 46) & (gray < 105)) | ((bhat_m > 54) & (min_rgb < 68)))
    ).astype(np.uint8) * 255

    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dark_bg = (gray < 85).astype(np.uint8) * 255
    thin_white_raw = (
        (zones > 0) & (that_g > 52) & (gray > 185) & (cv2.dilate(dark_bg, k5) > 0)
    ).astype(np.uint8) * 255

    max_cw = int(w * 0.32)
    max_ch = int(h * 0.085)
    glyph_cores = cv2.bitwise_or(
        _filter_glyph_components(thin_dark_raw, max_cw, max_ch),
        _filter_glyph_components(thin_white_raw, max_cw, max_ch),
    )
    ui_mask = cv2.dilate(glyph_cores, k3 if is_windowed else k5)

    # Orbes de energía circulares (superior derecho, costo de ataques, debilidad/retirada)
    circles = cv2.HoughCircles(
        cv2.GaussianBlur(gray, (5, 5), 1.2),
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(w * 0.052),
        param1=85,
        param2=23,
        minRadius=int(w * 0.018),
        maxRadius=int(w * 0.048),
    )
    if circles is not None:
        for cx_f, cy_f, r_f in np.round(circles[0]).astype(int):
            in_top_orb = cx_f > int(w * 0.82) and cy_f < int(h * 0.115)
            in_atk_orb = cx_f < int(w * 0.36) and int(h * 0.46) < cy_f < int(h * 0.855)
            in_bot_orb = int(h * 0.84) < cy_f < int(h * 0.915)
            if in_top_orb or in_atk_orb or in_bot_orb:
                cv2.circle(ui_mask, (int(cx_f), int(cy_f)), int(r_f + 2), 255, -1)

    # Insignia carmesí "Ability" (exige rojo intenso + bajo verde en píxeles rojos + texto blanco Top-Hat)
    ab_y1, ab_y2 = int(h * 0.46), int(h * 0.68)
    ab_x1, ab_x2 = int(w * 0.04), int(w * 0.38)
    ab_roi = bgr[ab_y1:ab_y2, ab_x1:ab_x2]
    ab_gray = gray[ab_y1:ab_y2, ab_x1:ab_x2]
    ab_that = that_g[ab_y1:ab_y2, ab_x1:ab_x2]
    red_diff = ab_roi[:, :, 2].astype(np.int32) - np.maximum(ab_roi[:, :, 1], ab_roi[:, :, 0]).astype(np.int32)
    red_bin = ((red_diff > 75) & (ab_roi[:, :, 2] > 140)).astype(np.uint8) * 255
    red_closed = cv2.morphologyEx(red_bin, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 5)))
    contours, _ = cv2.findContours(red_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 180:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            aspect = rw / max(1.0, float(rh))
            rm = red_bin[ry : ry + rh, rx : rx + rw] > 0
            g_in_red = float(np.median(ab_roi[ry : ry + rh, rx : rx + rw, 1][rm])) if rm.any() else 255.0
            tw = int(((ab_that[ry : ry + rh, rx : rx + rw] > 50) & (ab_gray[ry : ry + rh, rx : rx + rw] > 185)).sum())
            if rx >= 4 and 2.0 <= aspect <= 8.5 and g_in_red < 65.0 and tw >= 30:
                cv2.drawContours(ui_mask, [cnt], -1, 255, thickness=-1, offset=(ab_x1, ab_y1))
                cv2.drawContours(ui_mask, [cnt], -1, 255, thickness=2, offset=(ab_x1, ab_y1))

    # Etiqueta superior izquierda de Etapa (BASIC / STAGE 1 / VMAX / VSTAR)
    cv2.rectangle(ui_mask, (int(w * 0.022), int(h * 0.028)), (int(w * 0.175), int(h * 0.068)), 255, -1)

    # Recuadro de retrato de pre-evolución si corresponde
    evo_rect = _detect_evolution_box_rect(is_windowed, art_rect, w, h, stage, especial_type)
    _paint_evo_mask(ui_mask, evo_rect, is_windowed, art_rect, w, 255)

    # Placa Rule Box únicamente en cartas Rule Box Full-Bleed
    rarity_norm = _norm(rarity)
    esp_norm = _norm(especial_type)
    if not is_windowed and (esp_norm in _RULE_BOX_ESPECIAL or rarity_norm in _RULE_BOX_RARITIES):
        cv2.rectangle(
            ui_mask,
            (int(w * 0.338), int(h * 0.894)),
            (int(w * 0.966), int(h * 0.968)),
            255,
            -1,
        )

    return cv2.GaussianBlur(ui_mask, (3, 3), 0.7)


def _compute_window_color_prior(crop: np.ndarray) -> np.ndarray:
    """Calcula un mapa de saliencia del sujeto respecto a la paleta de bordes en CIE Lab."""
    ch, cw = crop.shape[:2]
    if cw < 16 or ch < 16:
        return np.full((ch, cw), 128.0, dtype=np.float32)

    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    lr_edges = np.concatenate(
        [
            lab[int(ch * 0.12) : int(ch * 0.88), 2:8].reshape(-1, 3),
            lab[int(ch * 0.12) : int(ch * 0.88), cw - 8 : cw - 2].reshape(-1, 3),
        ],
        axis=0,
    )
    q20, q50, q80 = np.percentile(lr_edges, [20, 50, 80], axis=0)
    d1 = np.linalg.norm(lab - q20, axis=2)
    d2 = np.linalg.norm(lab - q50, axis=2)
    d3 = np.linalg.norm(lab - q80, axis=2)
    min_bg_dist = np.minimum(np.minimum(d1, d2), d3)
    color_fg = np.clip((min_bg_dist - 17.0) / 27.0, 0.0, 1.0) * 255.0

    yy, xx = np.mgrid[0:ch, 0:cw]
    cx_n = (xx - cw * 0.5) / max(1.0, cw * 0.5)
    cy_n = (yy - ch * 0.52) / max(1.0, ch * 0.52)
    spatial = np.clip(1.18 - 0.38 * (cx_n**2 + cy_n**2), 0.35, 1.0)
    return np.clip(color_fg * spatial, 0.0, 255.0).astype(np.float32)


def _refine_with_grabcut(bgr_img: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Refina la silueta semilla usando GrabCut conservando bordes de arte limpios."""
    ch, cw = bgr_img.shape[:2]
    gc_mask = np.full((ch, cw), cv2.GC_PR_BGD, dtype=np.uint8)
    gc_mask[seed > 110] = cv2.GC_PR_FGD
    gc_mask[seed > 195] = cv2.GC_FGD
    gc_mask[seed < 32] = cv2.GC_BGD
    if cw > 4:
        gc_mask[:, 0:2] = cv2.GC_BGD
        gc_mask[:, cw - 2 : cw] = cv2.GC_BGD

    if (gc_mask == cv2.GC_FGD).sum() > 25 and (gc_mask == cv2.GC_BGD).sum() > 25:
        bgd_m = np.zeros((1, 65), np.float64)
        fgd_m = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr_img, gc_mask, None, bgd_m, fgd_m, 2, cv2.GC_INIT_WITH_MASK)
            refined = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255.0, 0.0).astype(np.float32)
            return cv2.GaussianBlur(refined, (5, 5), 1.1)
        except Exception:
            pass
    return cv2.GaussianBlur(seed.astype(np.float32), (5, 5), 1.1)


def segment_window_subject(crop: np.ndarray, use_ai: bool = False) -> np.ndarray:
    """Segmenta el Pokémon respecto al fondo cósmico dentro de la ventana de arte."""
    color_prior = _compute_window_color_prior(crop)
    if not use_ai:
        sm = cv2.GaussianBlur(color_prior, (7, 7), 1.6)
        ramp = np.clip((sm - 82.0) / 72.0, 0.0, 1.0) * 255.0
        return ramp.astype(np.float32)

    ch, cw = crop.shape[:2]
    pad = 24
    padded = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REFLECT_101)
    u2_raw = _run_rembg_mask(padded)
    if u2_raw is None:
        return _refine_with_grabcut(crop, color_prior)

    u2_prob = u2_raw[pad : pad + ch, pad : pad + cw]
    fg_ratio = float((u2_prob > 128).mean())
    if fg_ratio < 0.04:
        seed = color_prior
    elif fg_ratio > 0.78:
        p45 = float(np.percentile(u2_prob, 45))
        seed = np.clip((u2_prob.astype(np.float32) - p45) / max(1.0, 255.0 - p45), 0.0, 1.0) * 255.0
    else:
        seed = np.maximum(u2_prob.astype(np.float32), color_prior * 0.85)

    return _refine_with_grabcut(crop, seed)


def _compute_fullart_color_prior(inner: np.ndarray) -> np.ndarray:
    """Estima saliencia rápida en cartas Full Art midiendo contraste frente a cielo/bordes."""
    ih, iw = inner.shape[:2]
    small = cv2.resize(inner, (max(16, iw // 2), max(16, ih // 2)), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    border_samples = np.concatenate(
        [
            lab[0:4, int(sw * 0.08) : int(sw * 0.92)].reshape(-1, 3),
            lab[int(sh * 0.06) : int(sh * 0.75), 0:3].reshape(-1, 3),
            lab[int(sh * 0.06) : int(sh * 0.75), max(4, sw - 3) : sw].reshape(-1, 3),
        ],
        axis=0,
    )
    q20, q50, q80 = np.percentile(border_samples, [20, 50, 80], axis=0)
    d1 = np.linalg.norm(lab - q20, axis=2)
    d2 = np.linalg.norm(lab - q50, axis=2)
    d3 = np.linalg.norm(lab - q80, axis=2)
    min_bg_dist = np.minimum(np.minimum(d1, d2), d3)
    color_fg = np.clip((min_bg_dist - 19.0) / 30.0, 0.0, 1.0) * 255.0

    yy, xx = np.mgrid[0:sh, 0:sw]
    cx_n = (xx - sw * 0.5) / max(1.0, sw * 0.5)
    cy_n = (yy - sh * 0.44) / max(1.0, sh * 0.52)
    spatial = np.clip(1.12 - 0.35 * (cx_n**2 + cy_n**2), 0.35, 1.0)
    prior_small = np.clip(color_fg * spatial, 0.0, 255.0).astype(np.float32)
    prior = cv2.resize(prior_small, (iw, ih), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(prior, (7, 7), 1.6)


def segment_fullart_subject(
    bgr: np.ndarray,
    ui_mask: np.ndarray,
    use_ai: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Segmenta el personaje en cartas Full Art (limpiando primero la tipografía) y su contorno en relieve."""
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = int(w * 0.05), int(h * 0.08), int(w * 0.95), int(h * 0.88)
    inner = bgr[y1:y2, x1:x2]
    ih, iw = inner.shape[:2]

    subj_full = np.zeros((h, w), dtype=np.float32)

    if not use_ai:
        prior = _compute_fullart_color_prior(inner)
        subj_full[y1:y2, x1:x2] = np.clip((prior - 78.0) / 76.0, 0.0, 1.0) * 255.0
    else:
        inner_ink = (ui_mask[y1:y2, x1:x2] > 80).astype(np.uint8) * 255
        cleaned = cv2.inpaint(inner, inner_ink, 3, cv2.INPAINT_TELEA) if inner_ink.any() else inner
        u2 = _run_rembg_mask(cleaned)
        if u2 is None:
            prior = _compute_fullart_color_prior(cleaned)
            subj_inner = _refine_with_grabcut(cleaned, prior)
        else:
            if u2.shape[0] != ih or u2.shape[1] != iw:
                u2 = cv2.resize(u2, (iw, ih), interpolation=cv2.INTER_LINEAR)
            fg_ratio = float((u2 > 128).mean())
            if fg_ratio > 0.80:
                p45 = float(np.percentile(u2, 45))
                subj_inner = np.clip((u2.astype(np.float32) - p45) / max(1.0, 255.0 - p45), 0.0, 1.0) * 255.0
            elif fg_ratio < 0.05:
                subj_inner = _compute_fullart_color_prior(cleaned)
            else:
                subj_inner = u2.astype(np.float32)
        subj_full[y1:y2, x1:x2] = cv2.GaussianBlur(subj_inner.astype(np.float32), (7, 7), 1.3)

    # Contornos metálicos grabados (solo en Nivel-2 o en bordes del personaje)
    subj_bin = (subj_full > 110).astype(np.uint8) * 255
    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    outer_rim = cv2.dilate(subj_bin, k5) - cv2.erode(subj_bin, k5)

    if use_ai:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        hsv_v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
        canny = cv2.Canny(gray, 90, 200)
        internal_rim = np.where(
            (canny > 0) & (subj_full > 110) & (hsv_v > 175) & (ui_mask <= 80),
            np.uint8(255),
            np.uint8(0),
        )
        rim_raw = np.maximum(outer_rim.astype(np.float32), internal_rim.astype(np.float32))
    else:
        rim_raw = outer_rim.astype(np.float32)

    rim_full = cv2.GaussianBlur(rim_raw, (3, 3), 0.8)
    return subj_full, rim_full


def compose_foil_mask(
    bgr: np.ndarray,
    profile_key: str,
    rarity: str | None = None,
    especial_type: str | None = None,
    stage: str | None = None,
    set_id: str | None = None,
    use_ai: bool = False,
) -> np.ndarray:
    """Compone la máscara especular uint8 (0=mate opaco, 255=foil completo) de una carta."""
    h, w = bgr.shape[:2]
    art_rect, prom, _sides, is_windowed = detect_art_window(bgr)
    archetype = resolve_effective_archetype(profile_key, is_windowed, rarity, especial_type, prom=prom)
    if archetype == "none":
        return np.zeros((h, w), dtype=np.uint8)

    has_silver_border = detect_silver_holo_border(bgr, set_id=set_id)
    evo_rect = _detect_evolution_box_rect(is_windowed, art_rect, w, h, stage, especial_type)
    ui_mask = detect_opaque_ui_mask(
        bgr,
        is_windowed=is_windowed,
        art_rect=art_rect,
        rarity=rarity,
        especial_type=especial_type,
        stage=stage,
    )
    ui_block = 1.0 - np.clip(ui_mask.astype(np.float32) / 255.0, 0.0, 1.0)
    x1, y1, x2, y2 = art_rect

    if archetype == "art_window_bg":
        foil = np.zeros((h, w), dtype=np.float32)
        if has_silver_border:
            bx = max(8, int(w * 0.036))
            by = max(10, int(h * 0.028))
            border_mask = np.ones((h, w), dtype=bool)
            border_mask[by : h - by, bx : w - bx] = False
            foil[border_mask] = 185.0

        crop = bgr[y1:y2, x1:x2]
        subj_win = segment_window_subject(crop, use_ai=use_ai)
        subj_norm = np.clip(subj_win / 255.0, 0.0, 1.0)
        bg_weight = 1.0 - subj_norm
        foil[y1:y2, x1:x2] = 255.0 * bg_weight + 14.0 * subj_norm

        subj_bin = (subj_win > 115).astype(np.uint8) * 255
        k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        rim_w = cv2.GaussianBlur((cv2.dilate(subj_bin, k5) - subj_bin).astype(np.float32), (3, 3), 0.7)
        foil[y1:y2, x1:x2] = np.maximum(foil[y1:y2, x1:x2], (rim_w / 255.0) * 75.0)

        _paint_evo_mask(foil, evo_rect, is_windowed, art_rect, w, 0.0)
        return np.clip(foil, 0.0, 255.0).astype(np.uint8)

    if archetype == "reverse_frame":
        foil = np.zeros((h, w), dtype=np.float32)
        bx = max(8, int(w * 0.042))
        by = max(10, int(h * 0.032))
        if has_silver_border:
            foil[:, :] = 205.0
        foil[by : h - by, bx : w - bx] = 245.0
        foil[max(0, y1 - 1) : min(h, y2 + 1), max(0, x1 - 1) : min(w, x2 + 1)] = 0.0
        _paint_evo_mask(foil, evo_rect, is_windowed, art_rect, w, 0.0)
        foil *= ui_block
        return np.clip(foil, 0.0, 255.0).astype(np.uint8)

    if archetype == "splash_hybrid":
        foil = np.zeros((h, w), dtype=np.float32)
        if has_silver_border or profile_key in {"shiny_radiant", "prism_star", "classic_gold_break"}:
            bx = max(8, int(w * 0.036))
            by = max(10, int(h * 0.028))
            border_mask = np.ones((h, w), dtype=bool)
            border_mask[by : h - by, bx : w - bx] = False
            foil[border_mask] = 215.0

        if profile_key == "amazing_rare":
            cx_a = (x1 + x2) * 0.5
            cy_a = (y1 + y2) * 0.5
            rw = max(1.0, (x2 - x1) * 0.64)
            rh = max(1.0, (y2 - y1) * 0.64)
            yy, xx = np.mgrid[0:h, 0:w]
            dist = np.sqrt(((xx - cx_a) / rw) ** 2 + ((yy - cy_a) / rh) ** 2)
            splash = np.clip(1.0 - (dist - 0.72) / 0.42, 0.0, 1.0) * 135.0
            foil = np.maximum(foil, splash)

        crop = bgr[y1:y2, x1:x2]
        subj_win = segment_window_subject(crop, use_ai=use_ai)
        subj_norm = np.clip(subj_win / 255.0, 0.0, 1.0)
        foil[y1:y2, x1:x2] = 255.0 * (1.0 - 0.90 * subj_norm)

        _paint_evo_mask(foil, evo_rect, is_windowed, art_rect, w, 0.0)
        foil *= ui_block
        return np.clip(foil, 0.0, 255.0).astype(np.uint8)

    # Full-Bleed / Full Art / Etched ("full_art_etched")
    subj_full, rim_full = segment_fullart_subject(bgr, ui_mask, use_ai=use_ai)
    subj_norm = np.clip(subj_full / 255.0, 0.0, 1.0)
    rim_norm = np.clip(rim_full / 255.0, 0.0, 1.0)
    interior_val = 22.0 if profile_key in _SATIN_INTERIOR_PROFILES else 55.0
    foil = 255.0 * (1.0 - subj_norm) + interior_val * subj_norm
    foil = np.maximum(foil, rim_norm * 215.0)
    foil *= ui_block
    return np.clip(foil, 0.0, 255.0).astype(np.uint8)


def _build_cache_key(
    pixmap: QPixmap | QImage | None,
    id_api: str | None,
    idioma: str | None,
    profile_key: str,
    is_hd: bool,
) -> tuple[str, str | None]:
    qual = "hd" if is_hd else "sd"
    if id_api:
        safe_id = _safe_token(str(id_api).lower(), "card")
        safe_lang = _safe_token(str(idioma or "es").lower(), "es")
        fname = f"{MASK_SCHEMA_VERSION}_{safe_id}_{safe_lang}_{profile_key}_{qual}.webp"
        disk_path = os.path.join(HOLO_MASKS_DIR, fname)
        return fname, disk_path

    ck = int(pixmap.cacheKey()) if pixmap is not None else 0
    return f"mem_{MASK_SCHEMA_VERSION}_{ck}_{profile_key}_{qual}", None


def get_initial_foil_mask(
    pixmap: QPixmap | None,
    id_api: str | None,
    idioma: str | None,
    profile_key: str,
    rarity: str | None = None,
    especial_type: str | None = None,
    stage: str | None = None,
    set_id: str | None = None,
    is_hd: bool = False,
) -> tuple[QImage | None, bool, str]:
    """Obtiene máscara desde memoria/disco o genera al instante la máscara heurística Nivel-1 (<8 ms)."""
    if not profile_key or profile_key == "matte_none" or pixmap is None or pixmap.isNull():
        return None, True, ""

    cache_key, disk_path = _build_cache_key(pixmap, id_api, idioma, profile_key, is_hd)

    with _CACHE_LOCK:
        cached = _MASK_QIMAGE_CACHE.get(cache_key)
        if cached is not None and not cached[0].isNull():
            _MASK_QIMAGE_CACHE.move_to_end(cache_key)
            return cached[0], cached[1], cache_key

    if disk_path and os.path.exists(disk_path):
        loaded_qimg = QImage(disk_path)
        if not loaded_qimg.isNull():
            if loaded_qimg.hasAlphaChannel():
                alpha_qimg = loaded_qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            else:
                alpha_qimg = _grayscale_qimage_to_alpha_qimage(loaded_qimg)
            if alpha_qimg is not None and not alpha_qimg.isNull():
                with _CACHE_LOCK:
                    _touch_lru(_MASK_QIMAGE_CACHE, cache_key, (alpha_qimg, True), _MAX_MASK_CACHE)
                return alpha_qimg, True, cache_key

    qimg = pixmap.toImage()
    bgr = qimage_to_bgr(qimg, (CANONICAL_W, CANONICAL_H))
    if bgr is None:
        return None, True, ""

    fast_u8 = compose_foil_mask(
        bgr,
        profile_key=profile_key,
        rarity=rarity,
        especial_type=especial_type,
        stage=stage,
        set_id=set_id,
        use_ai=False,
    )
    fast_qimg = mask_u8_to_alpha_qimage(fast_u8)
    with _CACHE_LOCK:
        _touch_lru(_MASK_QIMAGE_CACHE, cache_key, (fast_qimg, False), _MAX_MASK_CACHE)
    return fast_qimg, False, cache_key


def _save_mask_atomically(mask_u8: np.ndarray, disk_path: str):
    """Guarda la máscara RGBA .webp sin pérdidas de forma atómica para recarga directa en Qt (<3 ms)."""
    try:
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        h, w = mask_u8.shape[:2]
        rgba = np.full((h, w, 4), 255, dtype=np.uint8)
        rgba[:, :, 3] = np.clip(mask_u8, 0, 255).astype(np.uint8)
        tmp_path = f"{disk_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        Image.fromarray(rgba, mode="RGBA").save(tmp_path, format="WEBP", lossless=True, method=0)
        os.replace(tmp_path, disk_path)
    except Exception:
        pass


class HoloMaskWorker(QThread):
    """Genera en segundo plano la máscara definitiva asistida por IA (rembg/GrabCut) usando QImage seguro."""

    mask_ready = pyqtSignal(str, QImage)

    def __init__(
        self,
        card_qimage: QImage,
        cache_key: str,
        id_api: str | None,
        idioma: str | None,
        profile_key: str,
        rarity: str | None = None,
        especial_type: str | None = None,
        stage: str | None = None,
        set_id: str | None = None,
        is_hd: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._card_qimage = card_qimage.copy() if card_qimage and not card_qimage.isNull() else QImage()
        self.cache_key = cache_key
        self.id_api = id_api
        self.idioma = idioma
        self.profile_key = profile_key
        self.rarity = rarity
        self.especial_type = especial_type
        self.stage = stage
        self.set_id = set_id
        self.is_hd = bool(is_hd)

    def run(self):
        if self._card_qimage.isNull() or not self.profile_key or self.profile_key == "matte_none":
            return
        bgr = qimage_to_bgr(self._card_qimage, (CANONICAL_W, CANONICAL_H))
        if bgr is None:
            return

        refined_u8 = compose_foil_mask(
            bgr,
            profile_key=self.profile_key,
            rarity=self.rarity,
            especial_type=self.especial_type,
            stage=self.stage,
            set_id=self.set_id,
            use_ai=True,
        )
        _, disk_path = _build_cache_key(None, self.id_api, self.idioma, self.profile_key, self.is_hd)
        if disk_path:
            _save_mask_atomically(refined_u8, disk_path)

        refined_qimg = mask_u8_to_alpha_qimage(refined_u8)
        with _CACHE_LOCK:
            _touch_lru(_MASK_QIMAGE_CACHE, self.cache_key, (refined_qimg, True), _MAX_MASK_CACHE)

        try:
            self.mask_ready.emit(self.cache_key, refined_qimg)
        except RuntimeError:
            pass


_PROFILE_ZONE_DESCRIPTIONS: dict[str, str] = {
    "matte_none": "Acabado de cartón mate estándar sin lámina holográfica.",
    "reverse_holo": "Foil selectivo en el marco de la carta; la ilustración y los textos se mantienen mate.",
    "rare_holo": "Brillo prismático detrás del Pokémon dentro de la ventana de arte; Pokémon y textos mate.",
    "double_rare_ex_v": "Haz doble diagonal sobre el fondo con textura satinada y textos/Rule Box protegidos.",
    "vmax_kinetic": "Foil kinético texturizado con realce en bordes del Pokémon y tipografía mate nítida.",
    "vstar_aura": "Aura estelar radial en fondo con protección de textos, energías y caja VSTAR.",
    "full_art_etched": "Textura grabada en toda la carta excepto textos, iconos de energía y cajas de reglas.",
    "illustration_rare": "Aurora perlada sobre fondo e ilustración; Pokémon y textos legibles sin deslumbramiento.",
    "special_illustration_rare": "Relieve prismático SIR con énfasis en fondo/ribetes y textos opacos.",
    "rainbow_hyper": "Foil arcoíris hiper-raro grabando fondo y contornos con tinta negra/blanca mate.",
    "gold_secret": "Lámina oro 24K en fondo y bordes manteniendo tipografía, iconos y Rule Box mate.",
    "shiny_radiant": "Foil cristalino selectivo destacando el fondo brillante detrás del Pokémon Shiny.",
    "ace_spec": "Barrido neón fucsia/magenta en fondo respetando recuadros y reglas ACE SPEC.",
    "prism_star": "Facetas prismáticas en ventana y borde protegiendo el sujeto y texto.",
    "amazing_rare": "Salpicadura multicolor iridiscente alrededor de la ventana con texto protegido.",
    "classic_gold_break": "Foil metálico cálido en zonas activas conservando tipografía opaca.",
    "cosmo_holo": "Orbes y anillos Cosmo Holo detrás del Pokémon en la ventana de arte.",
    "pokeball_holo": "Patrón vectorial Poké Ball en marco exterior con ilustración y textos mate.",
    "masterball_holo": "Patrón vectorial Master Ball en marco exterior con ilustración y textos mate.",
    "cracked_ice": "Facetas de hielo fracturado detrás del Pokémon en la ventana de ilustración.",
    "confetti_holo": "Destellos confeti detrás del Pokémon conservando el sujeto y marco mate.",
}


def get_profile_zone_tooltip(profile_key: str) -> str:
    """Devuelve una descripción breve en español de las zonas físicas de foil activo."""
    return _PROFILE_ZONE_DESCRIPTIONS.get(
        profile_key,
        "Efecto holográfico selectivo adaptado a las capas reales de impresión.",
    )
