"""Perfiles y renderizado 3D QPainter de efectos holográficos selectivos por rareza y variante."""

from __future__ import annotations

import math
import unicodedata
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

# Catálogo oficial de perfiles visuales (21 perfiles distintos)
HOLO_PROFILES: dict[str, dict[str, str]] = {
    "matte_none": {
        "profile": "matte_none",
        "label": "Mate (Sin holo)",
        "accent": "#94a3b8",
    },
    "reverse_holo": {
        "profile": "reverse_holo",
        "label": "Reverse Holo",
        "accent": "#4ade80",
    },
    "rare_holo": {
        "profile": "rare_holo",
        "label": "Holo Clásico",
        "accent": "#c084fc",
    },
    "double_rare_ex_v": {
        "profile": "double_rare_ex_v",
        "label": "Doble Haz EX/V/GX",
        "accent": "#38bdf8",
    },
    "vmax_kinetic": {
        "profile": "vmax_kinetic",
        "label": "VMAX Relieve",
        "accent": "#e879f9",
    },
    "vstar_aura": {
        "profile": "vstar_aura",
        "label": "Aura VSTAR",
        "accent": "#fde047",
    },
    "full_art_etched": {
        "profile": "full_art_etched",
        "label": "Full Art Relieve",
        "accent": "#fbbf24",
    },
    "illustration_rare": {
        "profile": "illustration_rare",
        "label": "Aurora Ilustración",
        "accent": "#f9a8d4",
    },
    "special_illustration_rare": {
        "profile": "special_illustration_rare",
        "label": "SIR Prisma Relieve",
        "accent": "#f59e0b",
    },
    "rainbow_hyper": {
        "profile": "rainbow_hyper",
        "label": "Arcoíris Hyper",
        "accent": "#ec4899",
    },
    "gold_secret": {
        "profile": "gold_secret",
        "label": "Oro 24K Secreta",
        "accent": "#fde047",
    },
    "shiny_radiant": {
        "profile": "shiny_radiant",
        "label": "Shiny Cristal",
        "accent": "#67e8f9",
    },
    "ace_spec": {
        "profile": "ace_spec",
        "label": "ACE SPEC Neón",
        "accent": "#f43f5e",
    },
    "prism_star": {
        "profile": "prism_star",
        "label": "Estrella Prisma",
        "accent": "#22d3ee",
    },
    "amazing_rare": {
        "profile": "amazing_rare",
        "label": "Amazing Prisma",
        "accent": "#c084fc",
    },
    "classic_gold_break": {
        "profile": "classic_gold_break",
        "label": "Oro Clásico / BREAK",
        "accent": "#f59e0b",
    },
    "cosmo_holo": {
        "profile": "cosmo_holo",
        "label": "Cosmo Holo",
        "accent": "#818cf8",
    },
    "pokeball_holo": {
        "profile": "pokeball_holo",
        "label": "Patrón Poké Ball",
        "accent": "#f87171",
    },
    "masterball_holo": {
        "profile": "masterball_holo",
        "label": "Patrón Master Ball",
        "accent": "#e879f9",
    },
    "cracked_ice": {
        "profile": "cracked_ice",
        "label": "Hielo Fracturado",
        "accent": "#67e8f9",
    },
    "confetti_holo": {
        "profile": "confetti_holo",
        "label": "Confeti Holo",
        "accent": "#f472b6",
    },
}

_EXPLICIT_VARIANT_MAP: dict[str, str] = {
    "masterball": "masterball_holo",
    "master ball": "masterball_holo",
    "masterball holo": "masterball_holo",
    "master ball holo": "masterball_holo",
    "pokeball": "pokeball_holo",
    "poke ball": "pokeball_holo",
    "pokeball holo": "pokeball_holo",
    "poke ball holo": "pokeball_holo",
    "cracked ice holo": "cracked_ice",
    "cracked ice": "cracked_ice",
    "confetti holo": "confetti_holo",
    "confetti": "confetti_holo",
    "cosmo holo": "cosmo_holo",
    "cosmos holo": "cosmo_holo",
    "cosmo": "cosmo_holo",
    "full art": "full_art_etched",
    "holografica reverse": "reverse_holo",
    "reverse holo": "reverse_holo",
    "reverse": "reverse_holo",
}

_RARITY_PROFILE_MAP: dict[str, str] = {
    "rare rainbow": "rainbow_hyper",
    "hyper rare": "gold_secret",
    "rare secret": "gold_secret",
    "mega hyper rare": "gold_secret",
    "special illustration rare": "special_illustration_rare",
    "illustration rare": "illustration_rare",
    "rare ultra": "full_art_etched",
    "ultra rare": "full_art_etched",
    "rare shiny": "shiny_radiant",
    "shiny rare": "shiny_radiant",
    "rare shiny gx": "shiny_radiant",
    "shiny ultra rare": "shiny_radiant",
    "radiant rare": "shiny_radiant",
    "rare shining": "shiny_radiant",
    "ace spec rare": "ace_spec",
    "rare ace": "ace_spec",
    "rare prism star": "prism_star",
    "amazing rare": "amazing_rare",
    "rare break": "classic_gold_break",
    "rare prime": "classic_gold_break",
    "legend": "classic_gold_break",
    "black white rare": "classic_gold_break",
    "rare holo star": "cosmo_holo",
    "rare holo vmax": "vmax_kinetic",
    "mega_attack_rare": "vmax_kinetic",
    "mega attack rare": "vmax_kinetic",
    "rare holo vstar": "vstar_aura",
    "double rare": "double_rare_ex_v",
    "rare holo ex": "double_rare_ex_v",
    "rare holo v": "double_rare_ex_v",
    "rare holo gx": "double_rare_ex_v",
    "rare holo lv.x": "double_rare_ex_v",
    "rare holo lv x": "double_rare_ex_v",
}

_BASE_HOLO_RARITIES: set[str] = {
    "rare holo",
    "promo",
    "classic collection",
    "trainer gallery rare holo",
}

_ESPECIAL_PROFILE_MAP: dict[str, str] = {
    "vmax": "vmax_kinetic",
    "v-max": "vmax_kinetic",
    "mega": "vmax_kinetic",
    "v-union": "vmax_kinetic",
    "v union": "vmax_kinetic",
    "vstar": "vstar_aura",
    "v-star": "vstar_aura",
    "ex": "double_rare_ex_v",
    "v": "double_rare_ex_v",
    "gx": "double_rare_ex_v",
    "level-up": "double_rare_ex_v",
    "lv.x": "double_rare_ex_v",
    "ace spec": "ace_spec",
    "prism star": "prism_star",
    "radiant": "shiny_radiant",
    "break": "classic_gold_break",
    "prime": "classic_gold_break",
    "legend": "classic_gold_break",
    "star": "cosmo_holo",
    "tera": "double_rare_ex_v",
}


def _norm(value: str | None) -> str:
    """Normaliza cadenas eliminando acentos y espacios sobrantes."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value).strip())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def _profile_dict(profile_key: str) -> dict[str, str]:
    """Devuelve una copia del diccionario descriptor para el perfil solicitado."""
    return dict(HOLO_PROFILES.get(profile_key, HOLO_PROFILES["matte_none"]))


def resolve_holo_profile(
    rarity: str | None,
    especial_type: str | None = None,
    variante: str | None = None,
    tag: str | None = None,
) -> dict[str, str]:
    """Resuelve el perfil holográfico 3D más fiel según variante, rareza, rule-box y tag."""
    var_norm = _norm(variante)
    if var_norm in _EXPLICIT_VARIANT_MAP:
        return _profile_dict(_EXPLICIT_VARIANT_MAP[var_norm])

    rarity_norm = _norm(rarity)
    if rarity_norm in _RARITY_PROFILE_MAP:
        return _profile_dict(_RARITY_PROFILE_MAP[rarity_norm])

    esp_norm = _norm(especial_type)
    if esp_norm in _ESPECIAL_PROFILE_MAP:
        return _profile_dict(_ESPECIAL_PROFILE_MAP[esp_norm])

    tag_tokens = {_norm(part) for part in str(tag or "").split(",") if part.strip()}
    if rarity_norm == "promo":
        if "prime" in tag_tokens:
            return _profile_dict("classic_gold_break")
        if "star" in tag_tokens:
            return _profile_dict("cosmo_holo")

    if rarity_norm in _BASE_HOLO_RARITIES:
        return _profile_dict("rare_holo")

    if var_norm in {"holo", "holografica"}:
        return _profile_dict("rare_holo")

    return _profile_dict("matte_none")


# ---------------------------------------------------------------------------
# Tablas geométricas precalculadas (deterministas, cero asignaciones por frame)
# ---------------------------------------------------------------------------

def _hash01(idx: int, salt: int = 1) -> float:
    x = math.sin(idx * 12.9898 + salt * 78.233) * 43758.5453
    return x - math.floor(x)


def _build_stardust(count: int) -> tuple[tuple[float, float, float, float], ...]:
    pts = []
    for i in range(count):
        u = 0.06 + 0.88 * _hash01(i, 11)
        v = 0.06 + 0.88 * _hash01(i, 23)
        r = 0.9 + 1.5 * _hash01(i, 37)
        phase = _hash01(i, 51) * math.tau
        pts.append((u, v, r, phase))
    return tuple(pts)


def _build_cosmo_orbs() -> tuple[tuple[float, float, float, int, float, bool], ...]:
    orbs = []
    for i in range(28):
        u = 0.07 + 0.86 * _hash01(i, 101)
        v = 0.07 + 0.86 * _hash01(i, 203)
        rad = 0.032 + 0.068 * _hash01(i, 307)
        hue = i % 5
        phase = _hash01(i, 409) * 0.75
        is_ring = (i % 3 == 0)
        orbs.append((u, v, rad, hue, phase, is_ring))
    return tuple(orbs)


def _build_confetti() -> tuple[tuple[float, float, float, int, float], ...]:
    dots = []
    for i in range(52):
        u = 0.05 + 0.90 * _hash01(i, 503)
        v = 0.05 + 0.90 * _hash01(i, 607)
        rad = 2.1 + 2.8 * _hash01(i, 709)
        color_idx = i % 6
        phase = _hash01(i, 811) * math.tau
        dots.append((u, v, rad, color_idx, phase))
    return tuple(dots)


def _build_mesh_facets(cols: int, rows: int, jitter: float, seed: int) -> tuple:
    """Construye una malla triangular sin huecos ni solapes para Prism Star / Cracked Ice."""
    grid: list[list[tuple[float, float]]] = []
    for r in range(rows + 1):
        row_pts = []
        base_v = -0.04 + 1.08 * (r / rows)
        for c in range(cols + 1):
            base_u = -0.04 + 1.08 * (c / cols)
            if 0 < c < cols and 0 < r < rows:
                idx = r * (cols + 1) + c
                du = (_hash01(idx, seed) - 0.5) * (jitter / cols)
                dv = (_hash01(idx, seed + 19) - 0.5) * (jitter / rows)
            else:
                du = 0.0
                dv = 0.0
            row_pts.append((base_u + du, base_v + dv))
        grid.append(row_pts)

    facets = []
    tri_idx = 0
    for r in range(rows):
        for c in range(cols):
            p00 = grid[r][c]
            p10 = grid[r][c + 1]
            p01 = grid[r + 1][c]
            p11 = grid[r + 1][c + 1]
            if (r + c + seed) % 2 == 0:
                tris = ((p00, p10, p11), (p00, p11, p01))
            else:
                tris = ((p00, p10, p01), (p10, p11, p01))
            for pts in tris:
                ang = _hash01(tri_idx, seed + 43) * math.tau
                facets.append((pts, math.cos(ang), math.sin(ang), tri_idx))
                tri_idx += 1
    return tuple(facets)


_STARDUST_POINTS = _build_stardust(38)
_COSMO_ORBS = _build_cosmo_orbs()
_CONFETTI_DOTS = _build_confetti()
_PRISM_FACETS = _build_mesh_facets(cols=4, rows=6, jitter=0.58, seed=13)
_ICE_SHARDS = _build_mesh_facets(cols=5, rows=7, jitter=0.76, seed=31)

_DIAMOND_ANCHORS: tuple[tuple[float, float, float], ...] = (
    (0.18, 0.22, 1.0), (0.38, 0.16, 0.8), (0.70, 0.20, 1.1), (0.83, 0.30, 0.9),
    (0.24, 0.39, 0.95), (0.52, 0.34, 1.15), (0.76, 0.45, 0.85), (0.16, 0.56, 1.0),
    (0.44, 0.53, 1.05), (0.66, 0.59, 0.9), (0.84, 0.64, 1.1), (0.28, 0.73, 0.85),
    (0.56, 0.76, 1.0), (0.78, 0.81, 0.95), (0.20, 0.87, 0.8), (0.48, 0.89, 1.05),
)

_AMAZING_SPLASHES: tuple[tuple[float, float, float, str], ...] = (
    (0.24, 0.28, 0.34, "#06b6d4"),
    (0.76, 0.25, 0.32, "#f43f5e"),
    (0.52, 0.46, 0.38, "#f59e0b"),
    (0.22, 0.64, 0.34, "#a855f7"),
    (0.78, 0.68, 0.35, "#22c55e"),
    (0.48, 0.82, 0.32, "#38bdf8"),
)


# ---------------------------------------------------------------------------
# Helpers de dibujo compartido
# ---------------------------------------------------------------------------

def _draw_cross_sparkle(
    painter: QPainter,
    x: float,
    y: float,
    radius: float,
    color: QColor,
    diamond: bool = False,
):
    """Dibuja un destello en cruz o rombo nítido con núcleo brillante."""
    painter.setPen(QPen(color, 1.2))
    painter.drawLine(QPointF(x - radius, y), QPointF(x + radius, y))
    painter.drawLine(QPointF(x, y - radius), QPointF(x, y + radius))
    if diamond:
        r2 = radius * 0.48
        poly = QPolygonF([
            QPointF(x, y - r2 * 1.4),
            QPointF(x + r2, y),
            QPointF(x, y + r2 * 1.4),
            QPointF(x - r2, y),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(poly)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        core = max(1.0, radius * 0.28)
        painter.drawEllipse(QPointF(x, y), core, core)


def _draw_diagonal_etch(
    painter: QPainter,
    rect: QRectF,
    step: float,
    color: QColor,
    nx: float,
    ny: float,
    cross: bool = False,
):
    """Traza micro-textura grabada diagonal sobre toda la superficie de la carta."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    offset = ((nx - ny) * 0.5) * step
    painter.setPen(QPen(color, 0.9))
    span = cw + ch
    x = -ch + offset
    while x < span:
        painter.drawLine(QPointF(cx + x, cy), QPointF(cx + x - ch * 0.85, cy + ch))
        x += step
    if cross:
        offset2 = ((nx + ny) * 0.5) * step
        x2 = -ch + offset2
        while x2 < span:
            painter.drawLine(QPointF(cx + x2, cy + ch), QPointF(cx + x2 - ch * 0.85, cy))
            x2 += step * 1.35


def _draw_specular_beam(
    painter: QPainter,
    rect: QRectF,
    pos_ratio: float,
    width_ratio: float,
    color_mid: QColor,
    angle_skew: float = 0.35,
):
    """Dibuja un haz metálico diagonal continuo sobre `rect`."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    bx = cx + pos_ratio * cw
    half_w = cw * width_ratio
    grad = QLinearGradient(bx - half_w, cy, bx + half_w, cy + ch * angle_skew)
    transparent = QColor(color_mid.red(), color_mid.green(), color_mid.blue(), 0)
    grad.setColorAt(0.0, transparent)
    grad.setColorAt(0.5, color_mid)
    grad.setColorAt(1.0, transparent)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(rect)


# ---------------------------------------------------------------------------
# Pintores por perfil (21 perfiles genuinamente distintos)
# ---------------------------------------------------------------------------

def _paint_matte_none(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Cartas comunes/no-holo: reflejo difuso mate muy sutil (alpha <= 48), sin arcoíris ni estrellas."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    gx = cx + (0.5 + 0.34 * nx) * cw
    gy = cy + (0.5 + 0.34 * ny) * ch
    peak_alpha = min(46, int(10 + 34 * tilt))
    mid_alpha = min(20, int(4 + 14 * tilt))

    grad = QRadialGradient(gx, gy, max(cw, ch) * 0.88)
    grad.setColorAt(0.0, QColor(255, 252, 246, peak_alpha))
    grad.setColorAt(0.5, QColor(255, 252, 246, mid_alpha))
    grad.setColorAt(1.0, QColor(255, 252, 246, 0))

    painter.setClipPath(clip_path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(rect)


def _paint_reverse_holo(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Brillo metálico cepillado en marco/cuerpo respetando recorte de ventana de arte."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    art_rect = QRectF(cx + 0.08 * cw, cy + 0.12 * ch, 0.84 * cw, 0.39 * ch)
    art_hole = QPainterPath()
    art_hole.addRoundedRect(art_rect, 4.0, 4.0)
    frame_path = clip_path.subtracted(art_hole)

    painter.setClipPath(frame_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    eff = 0.25 + 0.75 * tilt
    shift = nx * cw * 0.7 + ny * ch * 0.35
    foil = QLinearGradient(cx - cw * 0.2 + shift, cy, cx + cw * 1.1 + shift, cy + ch * 0.85)
    foil.setSpread(QLinearGradient.Spread.ReflectSpread)
    a1 = int(95 * eff)
    a2 = int(60 * eff)
    foil.setColorAt(0.0, QColor(226, 232, 240, a2))
    foil.setColorAt(0.3, QColor(248, 250, 252, a1))
    foil.setColorAt(0.55, QColor(148, 163, 184, int(45 * eff)))
    foil.setColorAt(0.8, QColor(186, 230, 253, a2))
    foil.setColorAt(1.0, QColor(226, 232, 240, a2))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(foil)
    painter.drawRect(rect)

    # Líneas diagonales finas de acabado metálico cepillado
    _draw_diagonal_etch(
        painter,
        rect,
        step=max(8.0, cw / 36.0),
        color=QColor(248, 250, 252, int(46 * eff)),
        nx=nx,
        ny=ny,
    )
    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.42 * (nx - ny * 0.5),
        width_ratio=0.20,
        color_mid=QColor(255, 255, 255, int(115 * eff)),
    )

    # Filete sutil marcando el contorno de la ventana de arte
    painter.setClipping(True)
    painter.setClipPath(clip_path)
    painter.setPen(QPen(QColor(226, 232, 240, int(85 * eff)), 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(art_rect, 4.0, 4.0)


def _paint_rare_holo(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Foil plateado-prismático enfocado en la ventana de arte con haces verticales suaves."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.22 + 0.78 * tilt

    art_rect = QRectF(cx + 0.08 * cw, cy + 0.12 * ch, 0.84 * cw, 0.39 * ch)
    art_path = QPainterPath()
    art_path.addRoundedRect(art_rect, 4.0, 4.0)
    art_clip = clip_path.intersected(art_path)

    painter.setClipPath(art_clip)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    shift_x = nx * art_rect.width() * 0.85
    prism = QLinearGradient(
        art_rect.left() - art_rect.width() * 0.2 + shift_x,
        art_rect.top(),
        art_rect.right() + art_rect.width() * 0.2 + shift_x,
        art_rect.top() + art_rect.height() * 0.18,
    )
    prism.setSpread(QLinearGradient.Spread.ReflectSpread)
    a = int(85 * eff)
    prism.setColorAt(0.00, QColor(226, 232, 240, a))
    prism.setColorAt(0.25, QColor(125, 211, 252, a))
    prism.setColorAt(0.50, QColor(216, 180, 254, a))
    prism.setColorAt(0.75, QColor(253, 230, 138, int(a * 0.85)))
    prism.setColorAt(1.00, QColor(248, 250, 252, a))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(prism)
    painter.drawRect(art_rect)

    # Haces verticales suaves dentro de la ventana de arte (sin estrellas por toda la carta)
    beam_center = 0.5 + 0.45 * nx
    for i in range(9):
        u = (i + 0.5) / 9.0
        dist = abs(u - beam_center)
        strength = max(0.0, 1.0 - dist / 0.36) * eff
        if strength > 0.08:
            bx = art_rect.left() + u * art_rect.width()
            bw = art_rect.width() * 0.055
            vgrad = QLinearGradient(bx - bw, art_rect.top(), bx + bw, art_rect.top())
            ba = int(125 * strength)
            vgrad.setColorAt(0.0, QColor(255, 255, 255, 0))
            vgrad.setColorAt(0.5, QColor(255, 255, 255, ba))
            vgrad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(vgrad)
            painter.drawRect(QRectF(bx - bw, art_rect.top(), bw * 2.0, art_rect.height()))


def _paint_double_rare_ex_v(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Doble haz diagonal cian/plata + destello cruzado nítido de alto contraste."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.25 + 0.75 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    # Base fría metálica cian/plata
    wash = QLinearGradient(cx, cy, cx + cw, cy + ch)
    wash.setColorAt(0.0, QColor(56, 189, 248, int(36 * eff)))
    wash.setColorAt(0.5, QColor(224, 242, 254, int(52 * eff)))
    wash.setColorAt(1.0, QColor(129, 140, 248, int(36 * eff)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(wash)
    painter.drawRect(rect)

    # Haz 1: diagonal principal cian-blanco
    pos1 = 0.5 + 0.45 * (nx - ny * 0.6)
    _draw_specular_beam(painter, rect, pos1, 0.16, QColor(224, 242, 254, int(175 * eff)), angle_skew=0.45)

    # Haz 2: contra-diagonal plateado-celeste
    pos2 = 0.5 - 0.45 * (nx + ny * 0.6)
    _draw_specular_beam(painter, rect, pos2, 0.12, QColor(56, 189, 248, int(145 * eff)), angle_skew=-0.42)

    # Destello cruzado nítido de alto contraste en el foco especular
    fx = cx + (0.5 + 0.32 * nx) * cw
    fy = cy + (0.44 + 0.30 * ny) * ch
    flare_r = min(cw, ch) * (0.16 + 0.14 * eff)
    halo = QRadialGradient(fx, fy, flare_r)
    halo.setColorAt(0.0, QColor(255, 255, 255, int(210 * eff)))
    halo.setColorAt(0.35, QColor(56, 189, 248, int(110 * eff)))
    halo.setColorAt(1.0, QColor(56, 189, 248, 0))
    painter.setBrush(halo)
    painter.drawEllipse(QPointF(fx, fy), flare_r, flare_r)

    painter.setPen(QPen(QColor(255, 255, 255, int(235 * eff)), 2.0))
    painter.drawLine(QPointF(fx - flare_r * 1.15, fy), QPointF(fx + flare_r * 1.15, fy))
    painter.drawLine(QPointF(fx, fy - flare_r * 1.15), QPointF(fx, fy + flare_r * 1.15))
    painter.setPen(QPen(QColor(186, 230, 253, int(155 * eff)), 1.1))
    diag = flare_r * 0.62
    painter.drawLine(QPointF(fx - diag, fy - diag), QPointF(fx + diag, fy + diag))
    painter.drawLine(QPointF(fx - diag, fy + diag), QPointF(fx + diag, fy - diag))

    for u, v, scale in _DIAMOND_ANCHORS[::3]:
        dist = abs((u + v * 0.35) - (pos1 + 0.16))
        strength = max(0.0, 1.0 - dist / 0.25) * eff
        if strength > 0.22:
            _draw_cross_sparkle(
                painter,
                cx + u * cw,
                cy + v * ch,
                (5.0 + 4.5 * strength) * scale,
                QColor(224, 242, 254, int(215 * strength)),
            )


def _paint_vmax_kinetic(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Textura grabada ondulada + onda energética magenta/cian + destellos en rombo/cruz."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.25 + 0.75 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    # Onda energética magenta/cian reactiva al ángulo
    shift_x = nx * cw * 0.75
    shift_y = ny * ch * 0.65
    wave = QLinearGradient(cx + shift_x, cy - ch * 0.2 + shift_y, cx + cw + shift_x, cy + ch + shift_y)
    wave.setSpread(QLinearGradient.Spread.ReflectSpread)
    wave.setColorAt(0.00, QColor(232, 121, 249, int(85 * eff)))
    wave.setColorAt(0.32, QColor(34, 211, 238, int(92 * eff)))
    wave.setColorAt(0.65, QColor(236, 72, 153, int(88 * eff)))
    wave.setColorAt(1.00, QColor(56, 189, 248, int(80 * eff)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(wave)
    painter.drawRect(rect)

    # Textura grabada ondulada (20 curvas suaves)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    rows = 20
    phase = (nx * 2.4 + ny * 1.6)
    amp = ch * 0.024
    for r in range(rows):
        base_y = cy + (r + 0.5) * (ch / rows)
        col = QColor(240, 171, 252, int(68 * eff)) if r % 2 == 0 else QColor(103, 232, 249, int(62 * eff))
        painter.setPen(QPen(col, 1.15))
        path = QPainterPath()
        steps = 10
        for s in range(steps + 1):
            t_u = s / steps
            px = cx + t_u * cw
            py = base_y + math.sin(t_u * math.tau * 2.0 + phase + r * 0.55) * amp
            if s == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        painter.drawPath(path)

    # Destellos en rombo/cruz reactivos al ángulo
    beam_u = 0.5 + 0.42 * nx
    for u, v, scale in _DIAMOND_ANCHORS:
        dist = math.hypot((u - beam_u), (v - (0.5 + 0.42 * ny)) * 0.85)
        strength = max(0.0, 1.0 - dist / 0.44) * eff
        if strength > 0.18:
            col = QColor(253, 244, 255, int(230 * strength))
            _draw_cross_sparkle(painter, cx + u * cw, cy + v * ch, (4.5 + 4.0 * strength) * scale, col, diamond=True)


def _paint_vstar_aura(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Aura dorada-celeste radial + rayos de luz estelar desde el centro + micro-destellos."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.25 + 0.75 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    center_x = cx + (0.5 + 0.22 * nx) * cw
    center_y = cy + (0.46 + 0.22 * ny) * ch
    rad = max(cw, ch) * 0.82

    aura = QRadialGradient(center_x, center_y, rad)
    aura.setColorAt(0.00, QColor(255, 251, 235, int(165 * eff)))
    aura.setColorAt(0.26, QColor(253, 224, 71, int(125 * eff)))
    aura.setColorAt(0.58, QColor(56, 189, 248, int(85 * eff)))
    aura.setColorAt(1.00, QColor(14, 165, 233, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(aura)
    painter.drawRect(rect)

    # Rayos estelares desde el centro
    ray_count = 16
    rot_offset = nx * 0.28 + ny * 0.16
    ray_len = max(cw, ch) * 0.95
    for i in range(ray_count):
        ang = (i / ray_count) * math.tau + rot_offset
        spread = 0.055 if i % 2 == 0 else 0.032
        p1 = QPointF(center_x + math.cos(ang - spread) * ray_len, center_y + math.sin(ang - spread) * ray_len)
        p2 = QPointF(center_x + math.cos(ang + spread) * ray_len, center_y + math.sin(ang + spread) * ray_len)
        col = QColor(254, 240, 138, int(75 * eff)) if i % 2 == 0 else QColor(186, 230, 253, int(65 * eff))
        painter.setBrush(col)
        painter.drawPolygon(QPolygonF([QPointF(center_x, center_y), p1, p2]))

    # Micro-destellos dorados/blancos
    for u, v, r_pt, phase in _STARDUST_POINTS[:26]:
        twinkle = 0.5 + 0.5 * math.sin(phase + nx * 4.2 - ny * 3.1)
        strength = twinkle * eff
        if strength > 0.25:
            col = QColor(254, 249, 195, int(225 * strength)) if int(phase * 10) % 2 == 0 else QColor(255, 255, 255, int(215 * strength))
            _draw_cross_sparkle(painter, cx + u * cw, cy + v * ch, 2.2 + r_pt * 1.4, col)


def _paint_full_art_etched(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Textura micro-grabada diagonal completa en toda la carta + barrido plateado-iridiscente."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    # Barrido metálico plateado-iridiscente de alto relieve
    shift = nx * cw * 0.75 + ny * ch * 0.45
    metal = QLinearGradient(cx - cw * 0.2 + shift, cy, cx + cw * 1.1 + shift, cy + ch * 0.9)
    metal.setSpread(QLinearGradient.Spread.ReflectSpread)
    a = int(88 * eff)
    metal.setColorAt(0.00, QColor(248, 250, 252, a))
    metal.setColorAt(0.25, QColor(186, 230, 253, a))
    metal.setColorAt(0.50, QColor(233, 213, 255, a))
    metal.setColorAt(0.75, QColor(254, 243, 199, a))
    metal.setColorAt(1.00, QColor(203, 213, 225, a))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(metal)
    painter.drawRect(rect)

    # Textura micro-grabada diagonal de doble pase (relieve táctil)
    step = max(6.5, cw / 44.0)
    _draw_diagonal_etch(
        painter,
        rect,
        step=step,
        color=QColor(255, 255, 255, int(62 * eff)),
        nx=nx,
        ny=ny,
        cross=True,
    )
    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.46 * (nx - ny * 0.5),
        width_ratio=0.18,
        color_mid=QColor(255, 255, 255, int(145 * eff)),
    )


def _paint_illustration_rare(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Aurora perlada pastel suave que fluye con el ángulo + polvo estelar fino delicado."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.25 + 0.75 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    sx = nx * cw * 0.75
    sy = ny * ch * 0.75
    aurora = QLinearGradient(cx + sx, cy + sy, cx + cw + sx, cy + ch + sy)
    aurora.setSpread(QLinearGradient.Spread.ReflectSpread)
    a = int(76 * eff)
    aurora.setColorAt(0.00, QColor(251, 207, 232, a))   # rosa pastel
    aurora.setColorAt(0.25, QColor(186, 230, 253, a))   # celeste perlado
    aurora.setColorAt(0.50, QColor(167, 243, 208, a))   # menta suave
    aurora.setColorAt(0.75, QColor(221, 214, 254, a))   # lavanda suave
    aurora.setColorAt(1.00, QColor(254, 243, 199, a))   # crema nacarada
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(aurora)
    painter.drawRect(rect)

    # Velo perlado flotante
    gx = cx + (0.5 + 0.35 * nx) * cw
    gy = cy + (0.5 + 0.35 * ny) * ch
    pearl = QRadialGradient(gx, gy, max(cw, ch) * 0.65)
    pearl.setColorAt(0.0, QColor(255, 255, 255, int(92 * eff)))
    pearl.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(pearl)
    painter.drawRect(rect)

    # Polvo estelar fino delicado
    for u, v, r_pt, phase in _STARDUST_POINTS:
        twinkle = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(phase + nx * 3.5 + ny * 3.5))
        a_dot = int(175 * twinkle * eff)
        if a_dot > 25:
            painter.setBrush(QColor(255, 255, 255, a_dot))
            painter.drawEllipse(QPointF(cx + u * cw, cy + v * ch), r_pt * 0.72, r_pt * 0.72)


def _paint_special_illustration_rare(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Aurora perlada profunda con relieve texturizado + ribete prismático dorado-violeta + destellos."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    sx = nx * cw * 0.85
    sy = ny * ch * 0.85
    aurora = QLinearGradient(cx + sx, cy + sy, cx + cw + sx, cy + ch + sy)
    aurora.setSpread(QLinearGradient.Spread.ReflectSpread)
    a = int(95 * eff)
    aurora.setColorAt(0.00, QColor(192, 132, 252, a))
    aurora.setColorAt(0.28, QColor(244, 114, 182, a))
    aurora.setColorAt(0.55, QColor(56, 189, 248, a))
    aurora.setColorAt(0.82, QColor(251, 191, 36, a))
    aurora.setColorAt(1.00, QColor(168, 85, 247, a))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(aurora)
    painter.drawRect(rect)

    # Relieve texturizado micro-grabado
    _draw_diagonal_etch(
        painter,
        rect,
        step=max(7.0, cw / 40.0),
        color=QColor(254, 243, 199, int(52 * eff)),
        nx=nx,
        ny=ny,
    )

    # Ribete prismático dorado-violeta en el perímetro de la carta
    rim_grad = QLinearGradient(cx + sx * 0.4, cy, cx + cw + sx * 0.4, cy + ch)
    rim_grad.setSpread(QLinearGradient.Spread.ReflectSpread)
    ra = int(205 * eff)
    rim_grad.setColorAt(0.0, QColor(253, 224, 71, ra))
    rim_grad.setColorAt(0.5, QColor(168, 85, 247, ra))
    rim_grad.setColorAt(1.0, QColor(244, 114, 182, ra))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QBrush(rim_grad), 4.5))
    painter.drawRoundedRect(rect.adjusted(2.5, 2.5, -2.5, -2.5), 12.0, 12.0)

    # Destellos finos
    for u, v, scale in _DIAMOND_ANCHORS[::2]:
        twinkle = 0.5 + 0.5 * math.sin((u * 8.0 + v * 6.0) + nx * 4.0 - ny * 3.0)
        strength = twinkle * eff
        if strength > 0.28:
            _draw_cross_sparkle(
                painter,
                cx + u * cw,
                cy + v * ch,
                (3.4 + 3.2 * strength) * scale,
                QColor(254, 249, 195, int(220 * strength)),
            )


def _paint_rainbow_hyper(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Foil arcoíris saturado de espectro completo en bandas reflectantes con trama diagonal texturizada."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    sx = nx * cw * 1.15
    sy = ny * ch * 1.15
    rainbow = QLinearGradient(cx - cw * 0.25 + sx, cy - ch * 0.25 + sy, cx + cw * 1.1 + sx, cy + ch * 1.1 + sy)
    rainbow.setSpread(QLinearGradient.Spread.ReflectSpread)
    a = int(125 * eff)
    rainbow.setColorAt(0.00, QColor(255, 0, 128, a))
    rainbow.setColorAt(0.17, QColor(255, 115, 0, a))
    rainbow.setColorAt(0.34, QColor(250, 224, 21, a))
    rainbow.setColorAt(0.51, QColor(34, 211, 102, a))
    rainbow.setColorAt(0.68, QColor(6, 182, 212, a))
    rainbow.setColorAt(0.85, QColor(139, 92, 246, a))
    rainbow.setColorAt(1.00, QColor(236, 72, 153, a))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(rainbow)
    painter.drawRect(rect)

    # Trama diagonal texturizada
    _draw_diagonal_etch(
        painter,
        rect,
        step=max(6.5, cw / 44.0),
        color=QColor(255, 255, 255, int(68 * eff)),
        nx=nx,
        ny=ny,
        cross=True,
    )
    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.45 * (nx - ny * 0.5),
        width_ratio=0.19,
        color_mid=QColor(255, 255, 255, int(135 * eff)),
    )


def _paint_gold_secret(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Lámina metálica oro 24K (#fde047, #f59e0b, #fffbeb) con textura grabada y destellos cálidos."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    shift = nx * cw * 0.8 + ny * ch * 0.4
    gold = QLinearGradient(cx - cw * 0.15 + shift, cy, cx + cw * 1.05 + shift, cy + ch * 0.9)
    gold.setSpread(QLinearGradient.Spread.ReflectSpread)
    c_light = QColor("#fffbeb")
    c_mid = QColor("#fde047")
    c_deep = QColor("#f59e0b")
    c_light.setAlpha(int(120 * eff))
    c_mid.setAlpha(int(115 * eff))
    c_deep.setAlpha(int(95 * eff))
    gold.setColorAt(0.00, c_deep)
    gold.setColorAt(0.30, c_mid)
    gold.setColorAt(0.55, c_light)
    gold.setColorAt(0.80, c_mid)
    gold.setColorAt(1.00, c_deep)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gold)
    painter.drawRect(rect)

    # Textura grabada dorada
    _draw_diagonal_etch(
        painter,
        rect,
        step=max(7.0, cw / 40.0),
        color=QColor(253, 224, 71, int(68 * eff)),
        nx=nx,
        ny=ny,
    )
    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.44 * (nx - ny * 0.45),
        width_ratio=0.20,
        color_mid=QColor(255, 251, 235, int(155 * eff)),
    )

    # Destellos dorados cálidos
    beam_pos = 0.5 + 0.44 * (nx - ny * 0.45)
    for u, v, scale in _DIAMOND_ANCHORS:
        dist = abs((u + v * 0.3) - (beam_pos + 0.15))
        strength = max(0.0, 1.0 - dist / 0.28) * eff
        if strength > 0.2:
            col = QColor(255, 251, 235, int(235 * strength))
            _draw_cross_sparkle(painter, cx + u * cw, cy + v * ch, (4.2 + 3.8 * strength) * scale, col)


def _paint_shiny_radiant(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Rejilla geométrica de diamantes/rombos + destellos cristalinos celeste-blanco."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    cols, rows = 6, 8
    cell_w = cw / cols
    cell_h = ch / rows
    beam_u = 0.5 + 0.45 * nx
    beam_v = 0.5 + 0.45 * ny

    for r in range(rows):
        for c in range(cols):
            uc = (c + 0.5) / cols
            vc = (r + 0.5) / rows
            dist = math.hypot((uc - beam_u), (vc - beam_v) * 1.1)
            strength = max(0.0, 1.0 - dist / 0.58) * eff
            mx = cx + uc * cw
            my = cy + vc * ch
            poly = QPolygonF([
                QPointF(mx, my - cell_h * 0.48),
                QPointF(mx + cell_w * 0.48, my),
                QPointF(mx, my + cell_h * 0.48),
                QPointF(mx - cell_w * 0.48, my),
            ])
            fill_a = int((22 + 95 * strength) * eff)
            fill_col = QColor(186, 230, 253, fill_a) if (r + c) % 2 == 0 else QColor(224, 242, 254, int(fill_a * 0.8))
            painter.setBrush(fill_col)
            painter.setPen(QPen(QColor(224, 242, 254, int((40 + 120 * strength) * eff)), 0.9))
            painter.drawPolygon(poly)

            if strength > 0.42 and (r + c) % 2 == 0:
                _draw_cross_sparkle(
                    painter,
                    mx,
                    my - cell_h * 0.48,
                    3.5 + 4.0 * strength,
                    QColor(255, 255, 255, int(235 * strength)),
                )


def _paint_ace_spec(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Barrido intenso fucsia/rosa neón (#ec4899, #f43f5e) con franjas diagonales de energía."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    c_pink = QColor("#ec4899")
    c_rose = QColor("#f43f5e")
    shift = nx * cw * 0.8 + ny * ch * 0.4
    neon = QLinearGradient(cx + shift, cy, cx + cw + shift, cy + ch * 0.75)
    neon.setSpread(QLinearGradient.Spread.ReflectSpread)
    neon.setColorAt(0.0, QColor(c_pink.red(), c_pink.green(), c_pink.blue(), int(90 * eff)))
    neon.setColorAt(0.5, QColor(c_rose.red(), c_rose.green(), c_rose.blue(), int(125 * eff)))
    neon.setColorAt(1.0, QColor(253, 164, 175, int(110 * eff)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(neon)
    painter.drawRect(rect)

    # Franjas diagonales paralelas de energía neón
    stripe_count = 10
    beam_u = 0.5 + 0.45 * (nx - ny * 0.4)
    for i in range(stripe_count):
        u = -0.15 + (i / (stripe_count - 1)) * 1.3
        dist = abs(u - beam_u)
        strength = max(0.15, 1.0 - dist / 0.42) * eff
        sx = cx + u * cw
        sw = cw * 0.055
        poly = QPolygonF([
            QPointF(sx, cy),
            QPointF(sx + sw, cy),
            QPointF(sx + sw - cw * 0.38, cy + ch),
            QPointF(sx - cw * 0.38, cy + ch),
        ])
        col = QColor(244, 63, 94, int(115 * strength)) if i % 2 == 0 else QColor(236, 72, 153, int(95 * strength))
        painter.setBrush(col)
        painter.drawPolygon(poly)

    _draw_specular_beam(painter, rect, beam_u, 0.16, QColor(253, 242, 248, int(150 * eff)), angle_skew=0.55)


def _paint_prism_star(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Facetas geométricas triangulares prismáticas que refractan colores distintos al girar."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt
    palette = (
        QColor(56, 189, 248),
        QColor(236, 72, 153),
        QColor(250, 204, 21),
        QColor(74, 222, 128),
        QColor(168, 85, 247),
        QColor(244, 63, 94),
    )

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    dir_x = nx if abs(nx) + abs(ny) > 0.05 else 0.45
    dir_y = ny if abs(nx) + abs(ny) > 0.05 else -0.35

    for pts, fnx, fny, idx in _PRISM_FACETS:
        dot = fnx * dir_x + fny * dir_y
        refract = max(0.08, 0.45 + 0.65 * dot) * eff
        base_col = palette[(idx + int((nx + 1.0) * 2.5)) % len(palette)]
        col = QColor(base_col.red(), base_col.green(), base_col.blue(), min(165, int(130 * refract)))
        poly = QPolygonF([QPointF(cx + u * cw, cy + v * ch) for u, v in pts])
        painter.setBrush(col)
        painter.setPen(QPen(QColor(255, 255, 255, min(140, int(95 * refract))), 0.85))
        painter.drawPolygon(poly)


def _paint_amazing_rare(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Manchas/explosiones de aura multicolor tipo pintura iridiscente."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.28 + 0.72 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    painter.setPen(Qt.PenStyle.NoPen)

    for idx, (u, v, rad_r, hex_col) in enumerate(_AMAZING_SPLASHES):
        px = cx + (u + nx * 0.08 * (1 if idx % 2 == 0 else -1)) * cw
        py = cy + (v + ny * 0.08 * (-1 if idx % 2 == 0 else 1)) * ch
        rad = max(cw, ch) * rad_r
        c = QColor(hex_col)
        grad = QRadialGradient(px, py, rad)
        grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), int(145 * eff)))
        grad.setColorAt(0.55, QColor(c.red(), c.green(), c.blue(), int(72 * eff)))
        grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(px, py), rad, rad)

    # Salpicaduras finas iridiscentes alrededor de las explosiones
    for u, v, r_pt, phase in _STARDUST_POINTS[:28]:
        c = QColor(_AMAZING_SPLASHES[int(phase * 10) % len(_AMAZING_SPLASHES)][3])
        tw = 0.45 + 0.55 * math.sin(phase + nx * 3.5 + ny * 2.5)
        painter.setBrush(QColor(c.red(), c.green(), c.blue(), int(195 * tw * eff)))
        painter.drawEllipse(QPointF(cx + u * cw, cy + v * ch), r_pt * 1.15, r_pt * 1.15)


def _paint_classic_gold_break(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Barras metálicas horizontales doradas/bronce con reflejo cálido."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    painter.setPen(Qt.PenStyle.NoPen)

    bar_count = 16
    bar_h = ch / bar_count
    beam_v = 0.5 + 0.45 * ny
    for i in range(bar_count):
        vc = (i + 0.5) / bar_count
        dist = abs(vc - beam_v)
        strength = max(0.18, 1.0 - dist / 0.45) * eff
        by = cy + i * bar_h
        grad = QLinearGradient(cx, by, cx + cw, by)
        shift_stop = max(0.15, min(0.85, 0.5 + 0.35 * nx))
        c_bronze = QColor(180, 83, 9, int(85 * strength))
        c_gold = QColor(245, 158, 11, int(110 * strength))
        c_shine = QColor(254, 243, 199, int(145 * strength))
        grad.setColorAt(0.0, c_bronze)
        grad.setColorAt(shift_stop, c_shine if i % 2 == 0 else c_gold)
        grad.setColorAt(1.0, c_bronze)
        painter.setBrush(grad)
        painter.drawRect(QRectF(cx, by, cw, bar_h * 0.82))


def _paint_cosmo_holo(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Orbes y anillos bokeh iridiscentes circulares clásicos estilo Cosmo Holo."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt
    palette = (
        QColor(129, 140, 248),
        QColor(56, 189, 248),
        QColor(244, 114, 182),
        QColor(250, 204, 21),
        QColor(74, 222, 128),
    )

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    beam_u = 0.5 + 0.44 * nx
    beam_v = 0.5 + 0.44 * ny
    for u, v, rad_r, hue_idx, phase, is_ring in _COSMO_ORBS:
        dist = math.hypot((u - beam_u), (v - beam_v) * 0.9)
        strength = max(0.08, 1.0 - dist / 0.58) * eff
        if strength <= 0.10:
            continue
        ox = cx + u * cw
        oy = cy + v * ch
        rad = min(cw, ch) * rad_r
        col = palette[(hue_idx + int((nx + 1.0) * 1.5)) % len(palette)]
        if is_ring:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(175 * strength)), 1.6))
            painter.drawEllipse(QPointF(ox, oy), rad, rad)
        else:
            grad = QRadialGradient(ox, oy, rad)
            grad.setColorAt(0.0, QColor(255, 255, 255, int(155 * strength)))
            grad.setColorAt(0.55, QColor(col.red(), col.green(), col.blue(), int(115 * strength)))
            grad.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(ox, oy), rad, rad)

    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.42 * (nx - ny * 0.4),
        width_ratio=0.22,
        color_mid=QColor(224, 231, 255, int(75 * eff)),
    )


def _draw_ball_grid(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
    is_masterball: bool = False,
):
    """Dibuja patrón vectorial repetitivo de Pokéballs o Masterballs bajo el haz especular."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    beam_u = 0.5 + 0.45 * nx
    beam_v = 0.5 + 0.45 * ny

    # Velo especular sutil acompañando la revelación del patrón
    spot = QRadialGradient(cx + beam_u * cw, cy + beam_v * ch, max(cw, ch) * 0.55)
    base_tint = QColor(217, 70, 239) if is_masterball else QColor(248, 113, 113)
    spot.setColorAt(0.0, QColor(255, 255, 255, int(72 * eff)))
    spot.setColorAt(0.55, QColor(base_tint.red(), base_tint.green(), base_tint.blue(), int(52 * eff)))
    spot.setColorAt(1.0, QColor(base_tint.red(), base_tint.green(), base_tint.blue(), 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(spot)
    painter.drawRect(rect)

    cols, rows = 5, 7
    r_ball = min(cw / (cols * 2.55), ch / (rows * 2.55))
    btn_r = r_ball * 0.25

    for row in range(rows):
        v = (row + 0.5) / rows
        stagger = 0.5 / cols if row % 2 == 1 else 0.0
        for col in range(cols + 1):
            u = (col + 0.3) / cols + stagger
            if u < -0.05 or u > 1.05:
                continue
            dist = math.hypot((u - beam_u) * 0.92, (v - beam_v) * 1.15)
            vis = max(0.10, 1.0 - dist / 0.55) * eff
            if vis <= 0.12:
                continue

            bx = cx + u * cw
            by = cy + v * ch
            alpha = min(225, int(195 * vis))
            line_col = QColor(245, 208, 254, alpha) if is_masterball else QColor(254, 226, 226, alpha)
            accent_col = QColor(232, 121, 249, int(alpha * 0.85)) if is_masterball else QColor(248, 113, 113, int(alpha * 0.8))

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(line_col, 1.4))
            painter.drawEllipse(QPointF(bx, by), r_ball, r_ball)

            # Línea ecuatorial dividida por el botón central
            painter.drawLine(QPointF(bx - r_ball, by), QPointF(bx - btn_r, by))
            painter.drawLine(QPointF(bx + btn_r, by), QPointF(bx + r_ball, by))

            # Botón central
            painter.drawEllipse(QPointF(bx, by), btn_r, btn_r)
            painter.setBrush(accent_col)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(bx, by), btn_r * 0.48, btn_r * 0.48)

            if is_masterball:
                # Cápsulas laterales superiores y letra 'M' distintiva de Master Ball
                painter.setBrush(accent_col)
                painter.drawEllipse(QPointF(bx - r_ball * 0.46, by - r_ball * 0.44), r_ball * 0.16, r_ball * 0.12)
                painter.drawEllipse(QPointF(bx + r_ball * 0.46, by - r_ball * 0.44), r_ball * 0.16, r_ball * 0.12)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(line_col, 1.35))
                m_poly = QPolygonF([
                    QPointF(bx - r_ball * 0.30, by - r_ball * 0.30),
                    QPointF(bx - r_ball * 0.30, by - r_ball * 0.66),
                    QPointF(bx, by - r_ball * 0.40),
                    QPointF(bx + r_ball * 0.30, by - r_ball * 0.66),
                    QPointF(bx + r_ball * 0.30, by - r_ball * 0.30),
                ])
                painter.drawPolyline(m_poly)


def _paint_pokeball_holo(painter, clip_path, rect, nx, ny, tilt):
    _draw_ball_grid(painter, clip_path, rect, nx, ny, tilt, is_masterball=False)


def _paint_masterball_holo(painter, clip_path, rect, nx, ny, tilt):
    _draw_ball_grid(painter, clip_path, rect, nx, ny, tilt, is_masterball=True)


def _paint_cracked_ice(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Polígonos angulares tipo hielo fracturado iluminados selectivamente según el ángulo."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    dir_x = nx if abs(nx) + abs(ny) > 0.05 else 0.35
    dir_y = ny if abs(nx) + abs(ny) > 0.05 else 0.45

    for pts, fnx, fny, idx in _ICE_SHARDS:
        align = max(0.0, fnx * dir_x + fny * dir_y)
        glint = (0.12 + 0.88 * (align ** 1.3)) * eff
        if idx % 3 == 0:
            col = QColor(224, 242, 254, min(185, int(165 * glint)))
        elif idx % 3 == 1:
            col = QColor(103, 232, 249, min(170, int(145 * glint)))
        else:
            col = QColor(196, 181, 253, min(145, int(115 * glint)))

        poly = QPolygonF([QPointF(cx + u * cw, cy + v * ch) for u, v in pts])
        painter.setBrush(col)
        painter.setPen(QPen(QColor(255, 255, 255, min(175, int(130 * glint))), 1.0))
        painter.drawPolygon(poly)


def _paint_confetti_holo(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    nx: float,
    ny: float,
    tilt: float,
):
    """Puntos circulares multicolores estilo confeti que centellean al inclinar."""
    cx, cy, cw, ch = rect.x(), rect.y(), rect.width(), rect.height()
    eff = 0.26 + 0.74 * tilt
    palette = (
        QColor(244, 114, 182),
        QColor(56, 189, 248),
        QColor(250, 204, 21),
        QColor(74, 222, 128),
        QColor(192, 132, 252),
        QColor(251, 113, 133),
    )

    painter.setClipPath(clip_path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

    _draw_specular_beam(
        painter,
        rect,
        pos_ratio=0.5 + 0.44 * (nx - ny * 0.35),
        width_ratio=0.22,
        color_mid=QColor(255, 255, 255, int(68 * eff)),
    )

    painter.setPen(Qt.PenStyle.NoPen)
    for u, v, rad, color_idx, phase in _CONFETTI_DOTS:
        sparkle = 0.5 + 0.5 * math.sin(phase + nx * 5.2 - ny * 4.4)
        strength = (0.15 + 0.85 * (sparkle ** 1.6)) * eff
        if strength > 0.16:
            c = palette[color_idx]
            px = cx + u * cw
            py = cy + v * ch
            painter.setBrush(QColor(c.red(), c.green(), c.blue(), int(205 * strength)))
            painter.drawEllipse(QPointF(px, py), rad, rad)
            if strength > 0.58:
                painter.setBrush(QColor(255, 255, 255, int(190 * strength)))
                painter.drawEllipse(QPointF(px, py), rad * 0.42, rad * 0.42)


_PROFILE_PAINTERS = {
    "matte_none": _paint_matte_none,
    "reverse_holo": _paint_reverse_holo,
    "rare_holo": _paint_rare_holo,
    "double_rare_ex_v": _paint_double_rare_ex_v,
    "vmax_kinetic": _paint_vmax_kinetic,
    "vstar_aura": _paint_vstar_aura,
    "full_art_etched": _paint_full_art_etched,
    "illustration_rare": _paint_illustration_rare,
    "special_illustration_rare": _paint_special_illustration_rare,
    "rainbow_hyper": _paint_rainbow_hyper,
    "gold_secret": _paint_gold_secret,
    "shiny_radiant": _paint_shiny_radiant,
    "ace_spec": _paint_ace_spec,
    "prism_star": _paint_prism_star,
    "amazing_rare": _paint_amazing_rare,
    "classic_gold_break": _paint_classic_gold_break,
    "cosmo_holo": _paint_cosmo_holo,
    "pokeball_holo": _paint_pokeball_holo,
    "masterball_holo": _paint_masterball_holo,
    "cracked_ice": _paint_cracked_ice,
    "confetti_holo": _paint_confetti_holo,
}


def paint_card_holo_effect(
    painter: QPainter,
    clip_path: QPainterPath,
    rect: QRectF,
    rot_x: float,
    rot_y: float,
    profile_info: dict | str | None,
):
    """Pinta el efecto holográfico selectivo sobre la carta usando QPainter puro a 60 FPS."""
    if rect.width() <= 1.0 or rect.height() <= 1.0:
        return

    if isinstance(profile_info, dict):
        profile_key = profile_info.get("profile", "matte_none")
    elif isinstance(profile_info, str) and profile_info:
        profile_key = profile_info
    else:
        profile_key = "matte_none"

    rx = max(-34.0, min(34.0, float(rot_x)))
    ry = max(-34.0, min(34.0, float(rot_y)))
    nx = ry / 34.0
    ny = -rx / 34.0
    tilt = min(1.0, (abs(rx) + abs(ry)) / 48.0)

    paint_fn = _PROFILE_PAINTERS.get(profile_key, _paint_matte_none)

    painter.save()
    try:
        paint_fn(painter, clip_path, rect, nx, ny, tilt)
    finally:
        painter.restore()
