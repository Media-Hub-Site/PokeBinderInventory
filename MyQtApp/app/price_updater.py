import json
import os
import re
import time
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests
from PyQt6.QtCore import QThread, pyqtSignal

from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas, CartaPrecio
from MyQtApp.config import TCGDEX_LANG_MAP, SUPPORTED_CURRENCIES, normalize_lang_code, load_settings
from MyQtApp.app.getImgs import tcgdex_to_pokemontcg_id

_HTTP_HEADERS = {
    "User-Agent": "PokeBinder/2.3 (https://github.com/Media-Hub-Site/PokeBinderInventory)"
}

_TCGMATCH_PUBLIC_HEADERS = {
    "User-Agent": "PokeBinder/2.3 (https://github.com/Media-Hub-Site/PokeBinderInventory)",
    "Origin": "https://tcgmatch.cl",
    "Referer": "https://tcgmatch.cl/",
}

# Cachés en memoria protegidos por locks
_rate_lock = threading.Lock()
_cached_eur_usd = None

_clp_rate_lock = threading.Lock()
_clp_to_usd_rate = None

_usd_rates_lock = threading.Lock()
_cached_usd_rates: dict[str, float] | None = None

_tcgcsv_lock = threading.Lock()
_tcgcsv_groups_by_cat: dict[int, list] = {}
_tcgcsv_group_cache: dict[tuple[int, int], tuple] = {}

_tcgmatch_lock = threading.Lock()
_tcgmatch_set_slugs: list[str] | None = None
_tcgmatch_set_cache: dict[str, list[dict]] = {}

# Orden estándar de presentación de fuentes de precio
PRICE_SOURCE_ORDER = ["TCGPlayer", "TCGMatch", "Cardmarket", "PokemonTCG", "TCGCSV"]


def get_eur_to_usd_rate() -> float:
    """Obtiene la tasa de cambio EUR -> USD en vivo (cacheada por sesión, fallback 1.09)."""
    global _cached_eur_usd
    with _rate_lock:
        if _cached_eur_usd is not None:
            return _cached_eur_usd
    rate = 1.09
    try:
        resp = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD", timeout=4)
        if resp.status_code == 200:
            val = resp.json().get("rates", {}).get("USD")
            if val and float(val) > 0:
                rate = float(val)
    except Exception:
        pass
    with _rate_lock:
        _cached_eur_usd = rate
    return rate


def get_clp_to_usd_rate() -> float:
    """Obtiene la tasa CLP -> USD en vivo (con respaldo seguro ~1/950 USD)."""
    global _clp_to_usd_rate
    with _clp_rate_lock:
        if _clp_to_usd_rate is not None:
            return _clp_to_usd_rate
    rates = get_all_usd_rates()
    clp_per_usd = float(rates.get("CLP") or 950.0)
    rate = (1.0 / clp_per_usd) if clp_per_usd > 0 else (1.0 / 950.0)
    with _clp_rate_lock:
        _clp_to_usd_rate = rate
    return rate


def get_all_usd_rates() -> dict[str, float]:
    """Obtiene y cachea por sesión las tasas de cambio desde USD hacia todas las monedas soportadas."""
    global _cached_usd_rates
    with _usd_rates_lock:
        if _cached_usd_rates is not None:
            return _cached_usd_rates

    rates = {
        code: float(info.get("rate_from_usd", 1.0))
        for code, info in SUPPORTED_CURRENCIES.items()
    }
    rates["USD"] = 1.0
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", headers=_HTTP_HEADERS, timeout=3)
        if r.status_code == 200:
            api_rates = r.json().get("rates", {})
            if isinstance(api_rates, dict):
                for code, val in api_rates.items():
                    try:
                        fval = float(val)
                        if fval > 0:
                            rates[str(code).upper()] = fval
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass

    with _usd_rates_lock:
        _cached_usd_rates = rates
    return rates


def get_active_currency() -> str:
    """Retorna el código de moneda activa configurado por el usuario en Ajustes (por defecto 'USD')."""
    try:
        code = str(load_settings().get("moneda", "USD") or "USD").strip().upper()
    except Exception:
        code = "USD"
    return code if code in SUPPORTED_CURRENCIES else "USD"


def convert_currency(amount: float, from_currency: str = "USD", to_currency: str | None = None) -> float:
    """Convierte un monto desde from_currency a USD y luego a to_currency (por defecto get_active_currency())."""
    if amount is None:
        return 0.0
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return 0.0
    if val == 0.0:
        return 0.0

    src = str(from_currency or "USD").strip().upper()
    dst = str(to_currency or get_active_currency() or "USD").strip().upper()
    if dst not in SUPPORTED_CURRENCIES:
        dst = "USD"
    if src == dst:
        return val

    rates = get_all_usd_rates()
    src_rate = float(rates.get(src) or SUPPORTED_CURRENCIES.get(src, {}).get("rate_from_usd", 1.0) or 1.0)
    dst_rate = float(rates.get(dst) or SUPPORTED_CURRENCIES.get(dst, {}).get("rate_from_usd", 1.0) or 1.0)

    usd_val = (val / src_rate) if (src != "USD" and src_rate > 0) else val
    return (usd_val * dst_rate) if dst != "USD" else usd_val


def format_price(
    amount: float,
    from_currency: str = "USD",
    target_currency: str | None = None,
    include_code: bool = True,
) -> str:
    """Formatea un precio convirtiéndolo a target_currency (por defecto la moneda activa del usuario)."""
    target = str(target_currency or get_active_currency() or "USD").strip().upper()
    if target not in SUPPORTED_CURRENCIES:
        target = "USD"
    c_info = SUPPORTED_CURRENCIES[target]
    sym = c_info.get("symbol", "$")
    decimals = int(c_info.get("decimals", 2))

    val = convert_currency(amount, from_currency=from_currency, to_currency=target)
    if decimals == 0:
        num_str = f"{sym}{int(round(val)):,}"
    else:
        num_str = f"{sym}{val:,.2f}"
    return f"{num_str} {target}" if include_code else num_str


def _strip_accents(s: str) -> str:
    txt = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in txt if not unicodedata.combining(ch))


def _normalize_text(s: str) -> str:
    clean = _strip_accents(s).lower()
    # Normalizar símbolos especiales comunes de cartas Pokémon
    clean = clean.replace("δ", " delta ").replace("★", " star ").replace("—", " ").replace("–", " ")
    return re.sub(r"[^a-z0-9]+", " ", clean).strip()


def _clean_search_query(s: str) -> str:
    """Limpia símbolos griegos/guiones largos sin perder palabras clave para APIs de búsqueda."""
    txt = _strip_accents(s)
    txt = re.sub(r"[δ★☆◊♦•—–]+", " ", txt)
    txt = re.sub(r"[^\w\s\-'.:/]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _clean_number_token(num: str | None) -> str:
    if not num or str(num).strip().upper() == "N/A":
        return ""
    part = str(num).split("/")[0].strip().lower()
    return part.lstrip("0") if part.isdigit() else part


def _tcgdex_id_variants(id_api: str) -> list[str]:
    """Genera variantes de id_api (con y sin ceros a la izquierda en el número, ej. sv08-1 <-> sv08-001)."""
    if not id_api or "-" not in id_api:
        return [id_api] if id_api else []
    variants = [id_api]
    set_part, num_part = id_api.split("-", 1)
    if num_part.isdigit():
        unpadded = str(int(num_part))
        padded3 = num_part.zfill(3)
        for cand in (f"{set_part}-{padded3}", f"{set_part}-{unpadded}"):
            if cand not in variants:
                variants.append(cand)
    return variants


def _resolve_canonical_en_meta(
    id_api: str,
    card_name: str | None = None,
    set_name: str | None = None,
    number: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Busca metadatos canónicos en inglés en la BD local para mejorar precisión multi-API."""
    need_name = not card_name
    need_set = not set_name or set_name in ("TCGDex", "N/A")
    need_num = not number or number == "N/A"

    if not id_api:
        return card_name, set_name, number

    session = SessionLocal()
    try:
        row = session.query(Cartas.nombre, Cartas.set_name, Cartas.number).filter(
            Cartas.id_api == id_api,
            Cartas.idioma == "en",
        ).first()
        if not row:
            row = session.query(Cartas.nombre, Cartas.set_name, Cartas.number).filter(
                Cartas.id_api == id_api,
            ).first()
        if row:
            db_name, db_set, db_num = row
            # Preferimos el nombre/set en inglés si la BD tiene fila en 'en'
            if db_name:
                card_name = db_name
            if db_set and db_set not in ("TCGDex", "N/A"):
                set_name = db_set
            elif need_set and db_set:
                set_name = db_set
            if need_num and db_num:
                number = db_num
    except Exception:
        pass
    finally:
        session.close()

    return card_name, set_name, number


def _extract_tcgdex_prices(card_json: dict) -> dict:
    """Extrae precios de TCGPlayer (USD) y Cardmarket (EUR -> USD) de una respuesta TCGdex v2."""
    result = {}
    if not isinstance(card_json, dict):
        return result
    pricing = card_json.get("pricing")
    if not isinstance(pricing, dict):
        return result

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. TCGPlayer (USD)
    tcgp = pricing.get("tcgplayer")
    if isinstance(tcgp, dict):
        best_price = 0.0
        best_variant = "market"
        best_low = None
        best_mid = None
        best_high = None
        priority = [
            "normal", "holofoil", "reverse-holofoil",
            "unlimited-holofoil", "1st-edition-holofoil", "unlimited", "1st-edition",
        ]
        keys = [k for k in priority if k in tcgp] + [
            k for k in tcgp.keys() if k not in priority and k not in ("unit", "updated")
        ]
        for variant_key in keys:
            vdata = tcgp.get(variant_key)
            if not isinstance(vdata, dict):
                continue
            cand = vdata.get("marketPrice") or vdata.get("midPrice") or vdata.get("lowPrice")
            if cand is not None and float(cand) > 0:
                best_price = float(cand)
                best_variant = variant_key
                best_low = float(vdata["lowPrice"]) if vdata.get("lowPrice") else None
                best_mid = float(vdata["midPrice"]) if vdata.get("midPrice") else None
                best_high = float(vdata["highPrice"]) if vdata.get("highPrice") else None
                break

        if best_price > 0:
            result["TCGPlayer"] = {
                "moneda": "USD",
                "precio_usd": round(best_price, 2),
                "precio_original": round(best_price, 2),
                "low": round(best_low, 2) if best_low else None,
                "mid": round(best_mid, 2) if best_mid else None,
                "high": round(best_high, 2) if best_high else None,
                "variante": best_variant,
                "actualizado_en": tcgp.get("updated") or now_iso,
            }

    # 2. Cardmarket (EUR -> USD)
    cm = pricing.get("cardmarket")
    if isinstance(cm, dict):
        eur_val = None
        variante_cm = "cardmarket"
        low_chk = float(cm.get("low") or cm.get("low-holo") or 0.0)
        avg30_chk = float(cm.get("avg30") or cm.get("avg") or cm.get("avg30-holo") or 0.0)
        cm_candidates = [
            ("trend", "cardmarket"),
            ("avg30", "cardmarket"),
            ("avg7", "cardmarket"),
            ("avg", "cardmarket"),
            ("low", "cardmarket"),
            ("trend-holo", "holofoil"),
            ("avg30-holo", "holofoil"),
            ("avg-holo", "holofoil"),
            ("low-holo", "holofoil"),
        ]
        for field_k, var_lbl in cm_candidates:
            raw_v = cm.get(field_k)
            if raw_v is not None:
                try:
                    fv = float(raw_v)
                    if field_k == "trend" and fv < 0.25 and (avg30_chk > 1.0 or low_chk > 0.5):
                        continue
                    if fv > 0:
                        eur_val = fv
                        variante_cm = var_lbl
                        break
                except (TypeError, ValueError):
                    continue

        if eur_val and eur_val > 0:
            rate = get_eur_to_usd_rate()
            low_raw = cm.get("low") or cm.get("low-holo")
            mid_raw = cm.get("avg30") or cm.get("avg") or cm.get("avg30-holo") or cm.get("avg-holo")
            high_raw = cm.get("avg1") or cm.get("avg1-holo")
            result["Cardmarket"] = {
                "moneda": "EUR",
                "precio_usd": round(eur_val * rate, 2),
                "precio_original": round(eur_val, 2),
                "low": round(float(low_raw), 2) if low_raw and float(low_raw) > 0 else None,
                "mid": round(float(mid_raw), 2) if mid_raw and float(mid_raw) > 0 else None,
                "high": round(float(high_raw), 2) if high_raw and float(high_raw) > 0 else None,
                "variante": variante_cm,
                "actualizado_en": cm.get("updated") or now_iso,
            }

    return result


def _score_tcgmatch_candidate(
    item: dict,
    norm_name: str,
    num_clean: str,
    norm_set: str,
) -> tuple[int, float]:
    """Evalúa cuán exacta es la coincidencia de un producto TCGMatch respecto a la carta buscada."""
    item_name_raw = str(item.get("name") or "")
    item_name = _normalize_text(item_name_raw)
    item_set = _normalize_text(item.get("setName") or item.get("set_name") or "")
    code_raw = str(item.get("cardCode") or item.get("code") or "")
    item_num = _clean_number_token(code_raw)

    # Descartar productos sellados o cajas si el catálogo los devolvió por error
    item_type = str(item.get("type") or "card").lower()
    if item_type and item_type != "card":
        return (-1, 0.0)

    # Exigir coincidencia razonable de nombre
    name_tokens = [w for w in norm_name.split() if len(w) >= 2]
    if not item_name:
        return (-1, 0.0)
    if norm_name in item_name:
        score = 40
    elif name_tokens and all(w in item_name for w in name_tokens):
        score = 28
    else:
        return (-1, 0.0)

    # Coincidencia por número dentro del set
    if num_clean and item_num:
        if item_num == num_clean:
            score += 45
        else:
            score -= 20

    # Coincidencia por nombre de set (evitar World Championship / Prize Pack si no se pidió)
    if norm_set and norm_set not in ("tcgdex", "n a"):
        # Quitar prefijos "hs " o "ex " o códigos tipo "sv08 " para comparar tokens reales
        set_tokens = [
            w for w in norm_set.split()
            if len(w) >= 3 and w not in ("pokemon", "pok", "mon", "ex", "hs", "sv", "swsh", "sm", "xy", "bw", "dp")
        ] or norm_set.split()
        if item_set == norm_set:
            score += 50
        elif norm_set in item_set or (len(item_set) >= 4 and item_set in norm_set):
            score += 38
        elif set_tokens:
            overlap = sum(1 for w in set_tokens if w in item_set)
            if overlap == len(set_tokens):
                score += 32
            elif overlap > 0:
                score += overlap * 12

        is_special_reprint = (
            "world championship" in item_set
            or "prize pack" in item_set
            or "trick or trade" in item_set
        )
        if is_special_reprint and not any(k in norm_set for k in ("world", "prize", "trick")):
            score -= 35

    raw_mkt = item.get("marketPrice") or item.get("market_price") or 0
    raw_low = item.get("lowestPrice") or item.get("min_price") or item.get("price") or 0
    price_val = float(raw_mkt or raw_low or 0.0)
    if price_val <= 0:
        return (-1, 0.0)
    return (score, price_val)


def _get_tcgmatch_set_slugs() -> list[str]:
    global _tcgmatch_set_slugs
    with _tcgmatch_lock:
        if _tcgmatch_set_slugs is not None:
            return _tcgmatch_set_slugs
    slugs = []
    try:
        r = requests.get("https://tcgmatch.cl/sitemap-sets.xml", headers=_TCGMATCH_PUBLIC_HEADERS, timeout=8)
        if r.status_code == 200:
            matches = re.findall(r"https://tcgmatch\.cl/cartas/pokemon/([^<\s]+)", r.text)
            slugs = sorted(set(matches))
    except Exception:
        pass
    with _tcgmatch_lock:
        _tcgmatch_set_slugs = slugs
    return slugs


def _search_tcgmatch_set_page_fallback(
    card_name: str,
    number: str | None,
    set_name: str | None,
    set_id: str | None = None,
) -> dict | None:
    """Respaldo público leyendo __NEXT_DATA__ de https://tcgmatch.cl/cartas/pokemon/<slug>."""
    if not set_name or set_name in ("N/A", "TCGDex"):
        return None
    slugs = _get_tcgmatch_set_slugs()
    if not slugs:
        return None

    norm_set = _normalize_text(set_name)
    norm_set_id = _normalize_text(set_id or "")
    set_tokens = [w for w in norm_set.split() if len(w) >= 3]
    best_slug = None
    best_score = 0
    for slug in slugs:
        s_norm = slug.replace("-", " ")
        sc = 0
        if norm_set_id and norm_set_id in s_norm:
            sc += 35
        if norm_set and (norm_set in s_norm or s_norm in norm_set):
            sc += 40
        elif set_tokens:
            ov = sum(1 for t_tok in set_tokens if t_tok in s_norm)
            if ov == len(set_tokens):
                sc += 30
            elif ov > 0:
                sc += ov * 10
        if sc > best_score:
            best_score = sc
            best_slug = slug

    if not best_slug or best_score < 20:
        return None

    with _tcgmatch_lock:
        items = _tcgmatch_set_cache.get(best_slug)

    if items is None:
        items = []
        try:
            r = requests.get(
                f"https://tcgmatch.cl/cartas/pokemon/{best_slug}",
                headers=_TCGMATCH_PUBLIC_HEADERS,
                timeout=9,
            )
            if r.status_code == 200:
                idx = r.text.find("__NEXT_DATA__")
                if idx != -1:
                    start = r.text.find(">", idx) + 1
                    end = r.text.find("</script>", start)
                    data = json.loads(r.text[start:end])
                    items = data.get("props", {}).get("pageProps", {}).get("singles", {}).get("items", []) or []
        except Exception:
            items = []
        with _tcgmatch_lock:
            _tcgmatch_set_cache[best_slug] = items

    if not items:
        return None

    norm_name = _normalize_text(_clean_search_query(card_name))
    num_clean = _clean_number_token(number)
    best_item = None
    best_sc = -1
    for it in items:
        if not isinstance(it, dict):
            continue
        sc, _pv = _score_tcgmatch_candidate(it, norm_name, num_clean, norm_set)
        if sc > best_sc:
            best_sc = sc
            best_item = it

    if not best_item or best_sc < 35:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    mkt = best_item.get("marketPrice") or best_item.get("lowestPrice")
    low_v = best_item.get("lowestPrice")
    val = float(mkt or low_v or 0.0)
    if val <= 0:
        return None
    return {
        "moneda": "CLP",
        "precio_usd": round(val * get_clp_to_usd_rate(), 2),
        "precio_original": round(val, 0),
        "low": round(float(low_v), 0) if low_v and float(low_v) > 0 else None,
        "mid": round(val, 0),
        "high": None,
        "variante": "tcgmatch",
        "actualizado_en": now_iso,
    }


def _get_tcgmatch_api_key() -> str:
    env_k = os.environ.get("TCGMATCH_API_KEY", "").strip()
    if env_k:
        return env_k
    try:
        return str(load_settings().get("tcgmatch_api_key", "") or "").strip()
    except Exception:
        return ""


def consultar_precio_tcgmatch(
    card_name: str,
    number: str = None,
    set_name: str = None,
    set_id: str = None,
) -> dict | None:
    """
    Consulta precio de mercado en TCGMatch (Chile, CLP -> USD):
      1. API oficial (api.tcgmatch.cl/v1/marketplace/cards) si hay TCGMATCH_API_KEY configurada.
      2. Buscador público en vivo (api.tcgmatch.cl/catalog/search) sin requerir llave.
      3. Respaldo por página de set pública (tcgmatch.cl/cartas/pokemon/<slug>).
    """
    if not card_name:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    clean_name = _clean_search_query(card_name)
    if not clean_name:
        return None
    norm_name = _normalize_text(clean_name)
    num_clean = _clean_number_token(number)
    norm_set = _normalize_text(set_name or "")

    # Nivel 1: API oficial v1 si el usuario configuró su API key
    api_key = _get_tcgmatch_api_key()
    if api_key:
        try:
            q_str = f"{clean_name} {num_clean}".strip() if num_clean else clean_name
            r = requests.get(
                "https://api.tcgmatch.cl/v1/marketplace/cards",
                params={"q": q_str, "game": "pokemon", "limit": 10},
                headers={**_HTTP_HEADERS, "Authorization": f"Bearer {api_key}"},
                timeout=6,
            )
            if r.status_code == 200:
                payload = r.json()
                items = payload if isinstance(payload, list) else (
                    payload.get("data") or payload.get("results") or payload.get("cards") or []
                )
                best_item = None
                best_sc = -1
                for item in (items or []):
                    if not isinstance(item, dict):
                        continue
                    sc, _pv = _score_tcgmatch_candidate(item, norm_name, num_clean, norm_set)
                    if sc > best_sc:
                        best_sc = sc
                        best_item = item
                if best_item and best_sc >= 25:
                    raw_mkt = (
                        best_item.get("market_price")
                        or best_item.get("marketPrice")
                        or best_item.get("avg_price")
                        or best_item.get("price")
                        or best_item.get("min_price")
                        or best_item.get("lowestPrice")
                    )
                    if raw_mkt and float(raw_mkt) > 0:
                        val = float(raw_mkt)
                        currency = str(best_item.get("currency", "CLP")).upper()
                        usd_val = round(val * get_clp_to_usd_rate(), 2) if currency == "CLP" else round(val, 2)
                        low_v = best_item.get("min_price") or best_item.get("low_price") or best_item.get("lowestPrice")
                        high_v = best_item.get("max_price") or best_item.get("high_price")
                        return {
                            "moneda": currency,
                            "precio_usd": usd_val,
                            "precio_original": round(val, 0 if currency == "CLP" else 2),
                            "low": round(float(low_v), 0 if currency == "CLP" else 2) if low_v else None,
                            "mid": round(val, 0 if currency == "CLP" else 2),
                            "high": round(float(high_v), 0 if currency == "CLP" else 2) if high_v else None,
                            "variante": "tcgmatch",
                            "actualizado_en": best_item.get("updated_at") or now_iso,
                        }
        except Exception:
            pass

    # Nivel 2: Catálogo público en vivo de tcgmatch.cl (/catalog/search)
    queries = []
    clean_set = _clean_search_query(set_name) if (set_name and set_name not in ("TCGDex", "N/A")) else ""
    if clean_set:
        # Quitar prefijos cortos tipo "HS " que confunden la búsqueda exacta
        short_set = re.sub(r"^(HS|EX|SV|XY|BW|DP|SM)\s+", "", clean_set, flags=re.IGNORECASE).strip()
        if short_set:
            queries.append((f"{clean_name} {short_set}", 12))
    if num_clean:
        queries.append((f"{clean_name} {num_clean}", 15))
    queries.append((clean_name, 25))

    seen_q = set()
    best_match = None
    best_score = -1
    for q_text, lim in queries:
        if q_text in seen_q:
            continue
        seen_q.add(q_text)
        try:
            r = requests.get(
                "https://api.tcgmatch.cl/catalog/search",
                params={"q": q_text, "tcg": "pokemon", "type": "card", "limit": lim},
                headers=_TCGMATCH_PUBLIC_HEADERS,
                timeout=6,
            )
            if r.status_code != 200:
                continue
            products = r.json().get("products") or []
            if not isinstance(products, list) or not products:
                continue
            for item in products:
                if not isinstance(item, dict):
                    continue
                sc, _pv = _score_tcgmatch_candidate(item, norm_name, num_clean, norm_set)
                if sc > best_score:
                    best_score = sc
                    best_match = item
            # Si encontramos coincidencia de set + número muy fuerte, no seguimos consultando
            if best_score >= 70:
                break
        except Exception:
            continue

    if best_match is not None:
        # Verificar umbral mínimo para evitar asignar precio de otra carta homónima si conocemos número+set
        min_required = 35 if (num_clean and norm_set and norm_set not in ("tcgdex", "n a")) else 28
        if best_score >= min_required:
            mkt = best_match.get("marketPrice")
            low_v = best_match.get("lowestPrice")
            val = float(mkt if (mkt and float(mkt) > 0) else (low_v or 0.0))
            if val > 0:
                return {
                    "moneda": "CLP",
                    "precio_usd": round(val * get_clp_to_usd_rate(), 2),
                    "precio_original": round(val, 0),
                    "low": round(float(low_v), 0) if (low_v and float(low_v) > 0) else None,
                    "mid": round(val, 0),
                    "high": None,
                    "variante": "tcgmatch",
                    "actualizado_en": now_iso,
                }

    # Nivel 3: Página estática del set en tcgmatch.cl
    return _search_tcgmatch_set_page_fallback(clean_name, number, set_name, set_id=set_id)


def _extract_pokemontcg_price(c_info: dict) -> dict | None:
    """Extrae precio representativo desde una carta de api.pokemontcg.io/v2."""
    now_iso = datetime.now(timezone.utc).isoformat()
    tcg_prices = c_info.get("tcgplayer", {}).get("prices", {})
    if isinstance(tcg_prices, dict):
        priority = ["normal", "holofoil", "reverseHolofoil", "1stEditionHolofoil", "unlimitedHolofoil"]
        vkeys = [k for k in priority if k in tcg_prices] + [k for k in tcg_prices.keys() if k not in priority]
        for variant_name in vkeys:
            price_dict = tcg_prices.get(variant_name)
            if not isinstance(price_dict, dict):
                continue
            m_price = price_dict.get("market") or price_dict.get("mid") or price_dict.get("low")
            if m_price and float(m_price) > 0:
                val = float(m_price)
                return {
                    "moneda": "USD",
                    "precio_usd": round(val, 2),
                    "precio_original": round(val, 2),
                    "low": round(float(price_dict["low"]), 2) if price_dict.get("low") else None,
                    "mid": round(float(price_dict["mid"]), 2) if price_dict.get("mid") else None,
                    "high": round(float(price_dict["high"]), 2) if price_dict.get("high") else None,
                    "variante": variant_name,
                    "actualizado_en": c_info.get("tcgplayer", {}).get("updatedAt") or now_iso,
                }

    cm = c_info.get("cardmarket", {}).get("prices", {})
    if isinstance(cm, dict):
        cm_val = cm.get("trendPrice") or cm.get("averageSellPrice") or cm.get("lowPrice")
        if cm_val and float(cm_val) > 0:
            eur = float(cm_val)
            rate = get_eur_to_usd_rate()
            return {
                "moneda": "EUR",
                "precio_usd": round(eur * rate, 2),
                "precio_original": round(eur, 2),
                "low": round(float(cm["lowPrice"]), 2) if cm.get("lowPrice") else None,
                "mid": round(float(cm["avg30"]), 2) if cm.get("avg30") else None,
                "high": round(float(cm["avg1"]), 2) if cm.get("avg1") else None,
                "variante": "cardmarket",
                "actualizado_en": c_info.get("cardmarket", {}).get("updatedAt") or now_iso,
            }

    return None


def _get_tcgcsv_groups(category_id: int = 3) -> list:
    with _tcgcsv_lock:
        cached = _tcgcsv_groups_by_cat.get(category_id)
        if cached is not None:
            return cached
    groups = []
    try:
        r = requests.get(
            f"https://tcgcsv.com/tcgplayer/{category_id}/groups",
            headers=_HTTP_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            groups = r.json().get("results", [])
    except Exception:
        pass
    with _tcgcsv_lock:
        _tcgcsv_groups_by_cat[category_id] = groups
    return groups


def _match_tcgcsv_group_id(groups: list, set_name: str, set_id: str | None = None) -> int | None:
    norm_set = _normalize_text(set_name)
    norm_abbr = _normalize_text(set_id or "")
    if not norm_set and not norm_abbr:
        return None

    set_tokens = [w for w in norm_set.split() if len(w) >= 2]
    best_id = None
    best_sc = 0
    for g in groups:
        gname = _normalize_text(g.get("name", ""))
        gabbr = _normalize_text(g.get("abbreviation", ""))
        sc = 0
        if gname == norm_set and norm_set:
            sc += 100
        elif norm_set and (norm_set in gname or (len(gname) >= 4 and gname in norm_set)):
            sc += 65
        elif set_tokens:
            ov = sum(1 for w in set_tokens if w in gname.split() or w in gname)
            if ov == len(set_tokens):
                sc += 50
            elif ov >= max(1, len(set_tokens) - 1) and len(set_tokens) >= 2:
                sc += ov * 18

        if norm_abbr and gabbr and norm_abbr == gabbr:
            sc += 35

        if sc > best_sc:
            best_sc = sc
            best_id = g.get("groupId")

    return best_id if best_sc >= 35 else None


def _fetch_tcgcsv_price(
    card_name: str,
    set_name: str,
    number: str,
    idioma: str = "en",
    set_id: str | None = None,
) -> dict | None:
    """Busca precio en el espejo público diario TCGCSV (tcgcsv.com) para el set y carta dados."""
    if not set_name or set_name in ("N/A", "TCGDex") or not card_name:
        return None

    categories = [85, 3] if normalize_lang_code(idioma) == "ja" else [3]
    for cat_id in categories:
        groups = _get_tcgcsv_groups(cat_id)
        if not groups:
            continue
        matched_group_id = _match_tcgcsv_group_id(groups, set_name, set_id=set_id)
        if not matched_group_id:
            continue

        cache_key = (cat_id, int(matched_group_id))
        with _tcgcsv_lock:
            cached = _tcgcsv_group_cache.get(cache_key)

        if cached is None:
            try:
                r_prod = requests.get(
                    f"https://tcgcsv.com/tcgplayer/{cat_id}/{matched_group_id}/products",
                    headers=_HTTP_HEADERS,
                    timeout=10,
                )
                r_prc = requests.get(
                    f"https://tcgcsv.com/tcgplayer/{cat_id}/{matched_group_id}/prices",
                    headers=_HTTP_HEADERS,
                    timeout=10,
                )
                if r_prod.status_code != 200 or r_prc.status_code != 200:
                    continue
                products = r_prod.json().get("results", [])
                prices_raw = r_prc.json().get("results", [])
                prices_map = {}
                for pr in prices_raw:
                    pid = pr.get("productId")
                    if pid is not None:
                        prices_map.setdefault(pid, []).append(pr)
                cached = (products, prices_map)
                with _tcgcsv_lock:
                    _tcgcsv_group_cache[cache_key] = cached
            except Exception:
                continue

        products, prices_map = cached
        norm_name = _normalize_text(card_name)
        name_tokens = [w for w in norm_name.split() if w not in ("delta", "species") and len(w) >= 2] or norm_name.split()
        num_clean = _clean_number_token(number)

        best_product_id = None
        best_prod_sc = -1
        for prod in products:
            pname = _normalize_text(prod.get("name", ""))
            if not pname:
                continue
            sc = 0
            if norm_name in pname:
                sc += 40
            elif name_tokens and all(w in pname for w in name_tokens):
                sc += 28
            else:
                continue

            if num_clean:
                ext_data = prod.get("extendedData", [])
                ext_num = None
                for ed in ext_data:
                    if str(ed.get("name", "")).lower() == "number":
                        ext_num = _clean_number_token(ed.get("value"))
                        break
                if ext_num:
                    if ext_num == num_clean:
                        sc += 55
                    else:
                        sc -= 20

            if sc > best_prod_sc:
                best_prod_sc = sc
                best_product_id = prod.get("productId")

        if best_product_id is None or best_prod_sc < 28:
            continue

        entries = prices_map.get(best_product_id, [])
        # Preferir Normal o Holofoil con marketPrice válido
        sorted_entries = sorted(
            entries,
            key=lambda e: 0 if str(e.get("subTypeName", "")).lower() in ("normal", "holofoil") else 1,
        )
        for entry in sorted_entries:
            mp = entry.get("marketPrice") or entry.get("midPrice") or entry.get("lowPrice")
            if mp and float(mp) > 0:
                val = float(mp)
                return {
                    "moneda": "USD",
                    "precio_usd": round(val, 2),
                    "precio_original": round(val, 2),
                    "low": round(float(entry["lowPrice"]), 2) if entry.get("lowPrice") else None,
                    "mid": round(float(entry["midPrice"]), 2) if entry.get("midPrice") else None,
                    "high": round(float(entry["highPrice"]), 2) if entry.get("highPrice") else None,
                    "variante": entry.get("subTypeName") or "market",
                    "actualizado_en": datetime.now(timezone.utc).isoformat(),
                }

    return None


def guardar_precios_carta_bd(session, carta_id: str, precios_por_fuente: dict):
    """Guarda/actualiza los precios por fuente en carta_precios y sincroniza Cartas.price."""
    if not carta_id or not precios_por_fuente:
        return

    for fuente, info in precios_por_fuente.items():
        precio_usd = float(info.get("precio_usd") or 0.0)
        precio_orig = float(info.get("precio_original") or precio_usd)
        if precio_usd <= 0 and precio_orig <= 0:
            continue

        row = (
            session.query(CartaPrecio)
            .filter(CartaPrecio.carta_id == carta_id, CartaPrecio.fuente == fuente)
            .first()
        )
        if row:
            row.moneda = info.get("moneda", "USD")
            row.precio_usd = precio_usd
            row.precio_original = precio_orig
            row.precio_low = info.get("low")
            row.precio_mid = info.get("mid")
            row.precio_high = info.get("high")
            row.variante = info.get("variante", "market")
            row.actualizado_en = info.get("actualizado_en")
        else:
            session.add(
                CartaPrecio(
                    carta_id=carta_id,
                    fuente=fuente,
                    moneda=info.get("moneda", "USD"),
                    precio_usd=precio_usd,
                    precio_original=precio_orig,
                    precio_low=info.get("low"),
                    precio_mid=info.get("mid"),
                    precio_high=info.get("high"),
                    variante=info.get("variante", "market"),
                    actualizado_en=info.get("actualizado_en"),
                )
            )

    # Sincronizar Cartas.price en todos los idiomas con el mejor precio USD disponible
    primary_usd = 0.0
    for src in ("TCGPlayer", "TCGCSV", "PokemonTCG", "Cardmarket", "TCGMatch"):
        if src in precios_por_fuente and float(precios_por_fuente[src].get("precio_usd") or 0) > 0:
            primary_usd = float(precios_por_fuente[src]["precio_usd"])
            break

    if primary_usd > 0:
        session.query(Cartas).filter(Cartas.id_api == carta_id).update({"price": primary_usd})


def obtener_precios_carta_bd(carta_id: str) -> dict:
    """Lee todos los precios multi-API guardados localmente en BD para una carta."""
    if not carta_id:
        return {}
    session = SessionLocal()
    try:
        rows = session.query(CartaPrecio).filter(CartaPrecio.carta_id == carta_id).all()
        res = {}
        for r in rows:
            res[r.fuente] = {
                "moneda": r.moneda,
                "precio_usd": float(r.precio_usd or 0.0),
                "precio_original": float(r.precio_original or 0.0),
                "low": float(r.precio_low) if r.precio_low is not None else None,
                "mid": float(r.precio_mid) if r.precio_mid is not None else None,
                "high": float(r.precio_high) if r.precio_high is not None else None,
                "variante": r.variante or "market",
                "actualizado_en": r.actualizado_en,
            }
        return res
    except Exception as e:
        print(f"Error leyendo precios BD para {carta_id}: {e}")
        return {}
    finally:
        session.close()


def obtener_precios_multiples_cartas_bd(carta_ids: list[str]) -> tuple[dict, dict]:
    """
    Lee en una sola consulta SQL los precios multi-API y el precio base (Cartas.price)
    para una lista de id_api. Ideal para calcular valores acumulados de carpetas/binders.
    """
    unique_ids = list({cid for cid in carta_ids if cid})
    if not unique_ids:
        return {}, {}

    session = SessionLocal()
    try:
        multi_prices = {}
        rows = session.query(CartaPrecio).filter(CartaPrecio.carta_id.in_(unique_ids)).all()
        for r in rows:
            multi_prices.setdefault(r.carta_id, {})[r.fuente] = {
                "moneda": r.moneda,
                "precio_usd": float(r.precio_usd or 0.0),
                "precio_original": float(r.precio_original or 0.0),
            }

        base_prices = {}
        card_rows = (
            session.query(Cartas.id_api, Cartas.price)
            .filter(Cartas.id_api.in_(unique_ids))
            .all()
        )
        for cid, pr in card_rows:
            if pr and float(pr) > 0:
                if cid not in base_prices or float(pr) > base_prices[cid]:
                    base_prices[cid] = float(pr)

        return multi_prices, base_prices
    except Exception as e:
        print(f"Error leyendo precios múltiples BD: {e}")
        return {}, {}
    finally:
        session.close()


def _fetch_tcgdex_card(id_api: str, idioma: str = "en", cancel_check=None) -> tuple[dict | None, dict]:
    """Consulta TCGdex v2 (en inglés primero para metadatos canónicos + pricing completo)."""
    lang_code = normalize_lang_code(idioma)
    tcgdex_lang = TCGDEX_LANG_MAP.get(lang_code, "en")
    langs_to_try = ["en"] if tcgdex_lang == "en" else ["en", tcgdex_lang]
    id_variants = _tcgdex_id_variants(id_api)

    tcgdex_data = None
    extracted = {}
    for t_lang in langs_to_try:
        for cid_try in id_variants:
            if cancel_check and cancel_check():
                return tcgdex_data, extracted
            try:
                r = requests.get(
                    f"https://api.tcgdex.net/v2/{t_lang}/cards/{cid_try}",
                    headers=_HTTP_HEADERS,
                    timeout=7,
                )
                if r.status_code == 200:
                    tcgdex_data = r.json()
                    extracted = _extract_tcgdex_prices(tcgdex_data)
                    if tcgdex_data:
                        return tcgdex_data, extracted
            except Exception:
                continue
    return tcgdex_data, extracted


def _fetch_pokemontcg_card(id_api: str, cancel_check=None) -> tuple[dict | None, dict | None]:
    ptcg_id = tcgdex_to_pokemontcg_id(id_api)
    candidates = [id_api]
    if ptcg_id and ptcg_id not in candidates:
        candidates.append(ptcg_id)

    for cand_id in candidates:
        if cancel_check and cancel_check():
            return None, None
        try:
            r = requests.get(
                f"https://api.pokemontcg.io/v2/cards/{cand_id}",
                headers=_HTTP_HEADERS,
                timeout=7,
            )
            if r.status_code == 200:
                c_data = r.json().get("data", {})
                if c_data:
                    return c_data, _extract_pokemontcg_price(c_data)
        except Exception:
            continue
    return None, None


def fetch_multi_api_prices(
    id_api: str,
    idioma: str = "en",
    card_name: str = None,
    set_name: str = None,
    number: str = None,
    include_tcgcsv: bool = True,
    save_to_db: bool = True,
    cancel_check=None,
) -> dict:
    """
    Consulta múltiples APIs de Pokémon TCG en vivo para una carta:
      1. TCGdex v2 -> TCGPlayer (USD) + Cardmarket (EUR -> USD) + metadatos canónicos
      2. TCGMatch (tcgmatch.cl) -> Mercado chileno / latinoamericano (CLP -> USD)
      3. Pokémon TCG API (pokemontcg.io) -> PokemonTCG (USD/EUR)
      4. TCGCSV (tcgcsv.com) -> TCGCSV (USD)
    """
    if not id_api:
        return {}

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    card_name, set_name, number = _resolve_canonical_en_meta(
        id_api, card_name=card_name, set_name=set_name, number=number
    )
    set_id_hint = id_api.split("-", 1)[0] if "-" in id_api else None

    precios = {}

    # 1. Ejecutar TCGdex + PokemonTCG primero para resolver metadatos reales si faltaba set_name (ej. 'TCGDex')
    with ThreadPoolExecutor(max_workers=2) as meta_pool:
        fut_tcgdex = meta_pool.submit(_fetch_tcgdex_card, id_api, idioma, _cancelled)
        fut_ptcg = meta_pool.submit(_fetch_pokemontcg_card, id_api, _cancelled)

        tcgdex_data, tcgdex_prices = fut_tcgdex.result()
        ptcg_data, ptcg_price = fut_ptcg.result()

    if tcgdex_prices:
        precios.update(tcgdex_prices)
    if tcgdex_data:
        t_set = tcgdex_data.get("set", {}).get("name")
        t_name = tcgdex_data.get("name")
        t_num = tcgdex_data.get("localId")
        if t_set and (not set_name or set_name in ("TCGDex", "N/A")):
            set_name = t_set
        if t_name and not card_name:
            card_name = t_name
        if t_num and (not number or number == "N/A"):
            number = t_num

    if ptcg_price:
        precios["PokemonTCG"] = ptcg_price
    if ptcg_data:
        p_set = ptcg_data.get("set", {}).get("name")
        p_name = ptcg_data.get("name")
        p_num = ptcg_data.get("number")
        if p_set and (not set_name or set_name in ("TCGDex", "N/A")):
            set_name = p_set
        if p_name and not card_name:
            card_name = p_name
        if p_num and (not number or number == "N/A"):
            number = p_num

    if _cancelled():
        return precios

    # 2. En paralelo consultar TCGMatch (Chile / CLP) y TCGCSV (espejo TCGPlayer) ya con set_name y card_name exactos
    if card_name:
        with ThreadPoolExecutor(max_workers=2) as mkt_pool:
            fut_tcgm = mkt_pool.submit(
                consultar_precio_tcgmatch,
                card_name,
                number=number,
                set_name=set_name,
                set_id=set_id_hint,
            )
            fut_csv = (
                mkt_pool.submit(
                    _fetch_tcgcsv_price,
                    card_name,
                    set_name,
                    number,
                    idioma=idioma,
                    set_id=set_id_hint,
                )
                if (include_tcgcsv and set_name and set_name not in ("TCGDex", "N/A"))
                else None
            )

            tcgm_price = fut_tcgm.result()
            if tcgm_price:
                precios["TCGMatch"] = tcgm_price
            if fut_csv is not None:
                csv_price = fut_csv.result()
                if csv_price:
                    precios["TCGCSV"] = csv_price

    if save_to_db and precios:
        session = SessionLocal()
        try:
            guardar_precios_carta_bd(session, id_api, precios)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error guardando precios multi-API para {id_api}: {e}")
        finally:
            session.close()

    return precios


class SingleCardPriceThread(QThread):
    """Hilo ligero para consultar precios comparativos de múltiples APIs de una carta individual."""
    prices_loaded = pyqtSignal(str, dict)  # (id_api, precios_por_fuente)
    error = pyqtSignal(str)

    def __init__(self, id_api: str, idioma: str = "en", card_name: str = None, set_name: str = None, number: str = None, parent=None):
        super().__init__(parent)
        self.id_api = id_api
        self.idioma = idioma
        self.card_name = card_name
        self.set_name = set_name
        self.number = number
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self):
        try:
            precios = fetch_multi_api_prices(
                self.id_api,
                idioma=self.idioma,
                card_name=self.card_name,
                set_name=self.set_name,
                number=self.number,
                include_tcgcsv=True,
                save_to_db=True,
                cancel_check=self._cancel_event.is_set,
            )
            if not self._cancel_event.is_set():
                self.prices_loaded.emit(self.id_api, precios)
        except Exception as e:
            if not self._cancel_event.is_set():
                self.error.emit(str(e))


class PriceUpdaterThread(QThread):
    """
    Hilo en segundo plano que sincroniza precios en tiempo real desde múltiples APIs:
    - Pokémon TCG API (pokemontcg.io) por lotes
    - TCGdex v2 (TCGPlayer USD + Cardmarket EUR)
    - TCGCSV (respaldo diario TCGPlayer USD con caché por set)
    - TCGMatch (mercado chileno CLP -> USD)
    """
    progress = pyqtSignal(int, int)  # (actual, total)
    finished = pyqtSignal(int)       # (total_actualizadas)
    error = pyqtSignal(str)

    def __init__(self, id_apis=None, parent=None):
        super().__init__(parent)
        self.id_apis = id_apis
        self.is_running = True

    def stop(self):
        self.is_running = False

    def _clean_input_ids(self, raw_ids) -> list[tuple[str, str]]:
        seen = set()
        cleaned = []
        for item in raw_ids:
            if not item:
                continue
            if isinstance(item, (tuple, list)):
                cid = str(item[0])
                lang = str(item[1]) if len(item) > 1 else "en"
            elif isinstance(item, dict):
                cid = str(item.get("id_api", ""))
                lang = str(item.get("idioma", "en"))
            else:
                s = str(item)
                if ":" in s:
                    cid, lang = s.split(":", 1)
                else:
                    cid, lang = s, "en"
            if cid and cid not in seen:
                seen.add(cid)
                cleaned.append((cid, normalize_lang_code(lang)))
        return cleaned

    def run(self):
        session = SessionLocal()
        try:
            if not self.id_apis:
                cartas_db = session.query(Cartas.id_api, Cartas.idioma).distinct(Cartas.id_api).all()
                targets = self._clean_input_ids(cartas_db)
            else:
                targets = self._clean_input_ids(self.id_apis)

            total = len(targets)
            if total == 0:
                self.finished.emit(0)
                return

            self.progress.emit(0, total)
            total_actualizadas = 0

            # Precargar metadatos canónicos (prefiriendo fila en inglés) para mejorar cobertura
            meta_by_id: dict[str, tuple[str | None, str | None, str | None]] = {}
            target_cids = [cid for cid, _ in targets]
            for i in range(0, len(target_cids), 400):
                batch_ids = target_cids[i:i + 400]
                rows = (
                    session.query(Cartas.id_api, Cartas.idioma, Cartas.nombre, Cartas.set_name, Cartas.number)
                    .filter(Cartas.id_api.in_(batch_ids))
                    .all()
                )
                for cid_r, lang_r, nom_r, set_r, num_r in rows:
                    prev = meta_by_id.get(cid_r)
                    if prev is None or lang_r == "en":
                        meta_by_id[cid_r] = (nom_r, set_r, num_r)

            # Fase 1: Consultar Pokémon TCG API en lotes de 25
            ptcg_results = {}
            chunk_size = 25
            for i in range(0, total, chunk_size):
                if not self.is_running:
                    break
                chunk = targets[i:i + chunk_size]
                ptcg_to_orig = {}
                query_ids = []
                for cid, _ in chunk:
                    norm_id = tcgdex_to_pokemontcg_id(cid)
                    ptcg_to_orig[cid.lower()] = cid
                    if norm_id:
                        ptcg_to_orig[norm_id.lower()] = cid
                        query_ids.append(norm_id)
                    if cid not in query_ids:
                        query_ids.append(cid)

                escaped = [f'id:"{qid}"' for qid in query_ids[:45]]
                query_str = " OR ".join(escaped)
                url = f"https://api.pokemontcg.io/v2/cards?q={requests.utils.quote(query_str)}"
                try:
                    resp = requests.get(url, headers=_HTTP_HEADERS, timeout=10)
                    if resp.status_code == 200:
                        for c_info in resp.json().get("data", []):
                            ret_id = str(c_info.get("id", "")).lower()
                            orig_cid = ptcg_to_orig.get(ret_id)
                            if orig_cid:
                                p_dict = _extract_pokemontcg_price(c_info)
                                if p_dict:
                                    ptcg_results[orig_cid] = p_dict
                except Exception as e:
                    print(f"Aviso lote PokemonTCG.io: {e}")

            # Fase 2: TCGdex (TCGPlayer + Cardmarket), TCGCSV y TCGMatch en paralelo por lotes pequeños
            def _fetch_card_extras(cid_item: str, lang_item: str) -> tuple[str, dict]:
                res_carta = {}
                if cid_item in ptcg_results:
                    res_carta["PokemonTCG"] = ptcg_results[cid_item]

                card_name, set_name, number = meta_by_id.get(cid_item, (None, None, None))
                set_id_hint = cid_item.split("-", 1)[0] if "-" in cid_item else None

                tcgdex_data, tcgdex_ext = _fetch_tcgdex_card(
                    cid_item, lang_item, cancel_check=lambda: not self.is_running
                )
                if tcgdex_ext:
                    res_carta.update(tcgdex_ext)
                if tcgdex_data:
                    if not set_name or set_name in ("TCGDex", "N/A"):
                        set_name = tcgdex_data.get("set", {}).get("name") or set_name
                    if not card_name:
                        card_name = tcgdex_data.get("name")
                    if not number or number == "N/A":
                        number = tcgdex_data.get("localId") or number

                if card_name and set_name and set_name not in ("TCGDex", "N/A"):
                    csv_p = _fetch_tcgcsv_price(card_name, set_name, number, idioma=lang_item, set_id=set_id_hint)
                    if csv_p:
                        res_carta["TCGCSV"] = csv_p

                if card_name and total <= 250 and self.is_running:
                    tcgm_p = consultar_precio_tcgmatch(
                        card_name,
                        number=number,
                        set_name=set_name,
                        set_id=set_id_hint,
                    )
                    if tcgm_p:
                        res_carta["TCGMatch"] = tcgm_p
                return cid_item, res_carta

            processed = 0
            batch_step = 4
            with ThreadPoolExecutor(max_workers=batch_step) as pool:
                for i in range(0, total, batch_step):
                    if not self.is_running:
                        break
                    sub_targets = targets[i:i + batch_step]
                    futs = [pool.submit(_fetch_card_extras, c_id, c_lang) for c_id, c_lang in sub_targets]
                    for fut in futs:
                        if not self.is_running:
                            break
                        cid_res, precios_carta = fut.result()
                        processed += 1
                        if precios_carta:
                            guardar_precios_carta_bd(session, cid_res, precios_carta)
                            total_actualizadas += 1
                        self.progress.emit(processed, total)
                    session.commit()

            session.commit()
            self.finished.emit(total_actualizadas)

        except Exception as e:
            session.rollback()
            self.error.emit(str(e))
        finally:
            session.close()
