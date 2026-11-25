"""Caché LRU en memoria para QPixmap (originales y re-escalados)."""

import os
from collections import OrderedDict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

MAX_PIXMAP_CACHE = 600
MAX_RAW_CACHE = 250

_raw_cache: "OrderedDict[str, QPixmap]" = OrderedDict()
_scaled_cache: "OrderedDict[tuple, QPixmap]" = OrderedDict()


def _touch(cache: OrderedDict, key, value, max_size: int):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > max_size:
        cache.popitem(last=False)


def get_cached_pixmap(
    path: str,
    width: int | None = None,
    height: int | None = None,
    keep_aspect: bool = True,
    smooth: bool = True,
) -> QPixmap | None:
    """Carga un QPixmap desde disco usando caché LRU y lo escala opcionalmente."""
    if not path:
        return None
    norm_path = os.path.normpath(path)

    if width is not None and height is not None:
        scaled_key = ("path", norm_path, int(width), int(height), bool(keep_aspect), bool(smooth))
        cached = _scaled_cache.get(scaled_key)
        if cached is not None and not cached.isNull():
            _scaled_cache.move_to_end(scaled_key)
            return cached

    raw = _raw_cache.get(norm_path)
    if raw is None or raw.isNull():
        if not os.path.exists(norm_path):
            return None
        raw = QPixmap(norm_path)
        if raw.isNull():
            return None
        _touch(_raw_cache, norm_path, raw, MAX_RAW_CACHE)
    else:
        _raw_cache.move_to_end(norm_path)

    if width is None or height is None:
        return raw

    aspect = Qt.AspectRatioMode.KeepAspectRatio if keep_aspect else Qt.AspectRatioMode.IgnoreAspectRatio
    trans = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
    scaled = raw.scaled(int(width), int(height), aspect, trans)
    if scaled.isNull():
        return raw
    _touch(_scaled_cache, scaled_key, scaled, MAX_PIXMAP_CACHE)
    return scaled


def scale_cached_pixmap(
    pix: QPixmap,
    width: int,
    height: int,
    keep_aspect: bool = True,
    smooth: bool = True,
) -> QPixmap:
    """Escala un QPixmap existente reutilizando el caché LRU por cacheKey."""
    if pix is None or pix.isNull() or width <= 0 or height <= 0:
        return pix
    if pix.width() == int(width) and pix.height() == int(height):
        return pix

    key = ("key", int(pix.cacheKey()), int(width), int(height), bool(keep_aspect), bool(smooth))
    cached = _scaled_cache.get(key)
    if cached is not None and not cached.isNull():
        _scaled_cache.move_to_end(key)
        return cached

    aspect = Qt.AspectRatioMode.KeepAspectRatio if keep_aspect else Qt.AspectRatioMode.IgnoreAspectRatio
    trans = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
    scaled = pix.scaled(int(width), int(height), aspect, trans)
    if not scaled.isNull():
        _touch(_scaled_cache, key, scaled, MAX_PIXMAP_CACHE)
        return scaled
    return pix


def clear_pixmap_cache():
    """Limpia ambos cachés de QPixmap en memoria."""
    _raw_cache.clear()
    _scaled_cache.clear()
