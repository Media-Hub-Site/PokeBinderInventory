import os
import re
import time
import threading
from datetime import datetime, timezone
import requests
from PyQt6.QtCore import QThread, pyqtSignal

from MyQtApp.session import SessionLocal
from MyQtApp.models import Cartas, CartaPrecio
from MyQtApp.config import TCGDEX_LANG_MAP, normalize_lang_code
from MyQtApp.app.getImgs import tcgdex_to_pokemontcg_id

_HTTP_HEADERS = {
    "User-Agent": "PokeBinder/1.5 (https://github.com/Media-Hub-Site/PokeBinderInventory)"
}

# Caché en memoria de tasa EUR -> USD y grupos/precios de TCGCSV
_rate_lock = threading.Lock()
_cached_eur_usd = None

_tcgcsv_lock = threading.Lock()
_tcgcsv_groups = None  # list of dicts from /tcgplayer/3/groups
_tcgcsv_group_cache = {}  # groupId -> (products_by_id, prices_by_product_id)

# Orden estándar de presentación de fuentes de precio
PRICE_SOURCE_ORDER = ["TCGPlayer", "TCGMatch", "PokemonTCG", "TCGCSV"]


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


def _normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _extract_tcgdex_prices(card_json: dict) -> dict:
    """Extrae precios de TCGPlayer (USD) y Cardmarket (EUR) de una respuesta TCGdex v2."""
    result = {}
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
        # Prioridad de variantes para obtener un precio representativo
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

    return result


_clp_to_usd_rate = None
_clp_rate_lock = threading.Lock()


def get_clp_to_usd_rate() -> float:
    """Obtiene la tasa CLP -> USD en vivo (con respaldo seguro ~1/950 USD)."""
    global _clp_to_usd_rate
    with _clp_rate_lock:
        if _clp_to_usd_rate is not None:
            return _clp_to_usd_rate
    rate = 1.0 / 950.0
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", headers=_HTTP_HEADERS, timeout=5)
        if r.status_code == 200:
            clp = r.json().get("rates", {}).get("CLP")
            if clp and float(clp) > 0:
                rate = 1.0 / float(clp)
    except Exception:
        pass
    with _clp_rate_lock:
        _clp_to_usd_rate = rate
    return rate


def consultar_precio_tcgmatch(card_name: str, number: str = None, set_name: str = None) -> dict | None:
    """
    Consulta precio de mercado en TCGMatch (tcgmatch.cl) para una carta Pokémon.
    Usa api.tcgmatch.cl (con Bearer token si TCGMATCH_API_KEY está configurada) o búsqueda pública.
    """
    if not card_name:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    query_str = f"{card_name} {number}".strip() if number and number != "N/A" else card_name.strip()
    headers = dict(_HTTP_HEADERS)
    api_key = os.environ.get("TCGMATCH_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    endpoints = [
        ("https://api.tcgmatch.cl/v1/cards", {"q": query_str, "game": "pokemon", "limit": 5}),
        ("https://tcgmatch.cl/api/cards", {"search": query_str, "game": "pokemon"}),
    ]
    for url, params in endpoints:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            payload = r.json()
            items = payload if isinstance(payload, list) else (payload.get("data") or payload.get("results") or payload.get("cards") or [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_price = (
                    item.get("market_price")
                    or item.get("avg_price")
                    or item.get("price")
                    or item.get("min_price")
                )
                if raw_price and float(raw_price) > 0:
                    val = float(raw_price)
                    currency = str(item.get("currency", "CLP")).upper()
                    if currency == "CLP":
                        usd_val = round(val * get_clp_to_usd_rate(), 2)
                    else:
                        usd_val = round(val, 2)
                    low_v = item.get("min_price") or item.get("low_price")
                    high_v = item.get("max_price") or item.get("high_price")
                    return {
                        "moneda": currency,
                        "precio_usd": usd_val,
                        "precio_original": round(val, 2),
                        "low": round(float(low_v), 2) if low_v else None,
                        "mid": round(val, 2),
                        "high": round(float(high_v), 2) if high_v else None,
                        "variante": "tcgmatch",
                        "actualizado_en": item.get("updated_at") or now_iso,
                    }
        except Exception:
            continue
    return None


def _extract_pokemontcg_price(c_info: dict) -> dict | None:
    """Extrae precio representativo desde una carta de api.pokemontcg.io/v2."""
    now_iso = datetime.now(timezone.utc).isoformat()
    tcg_prices = c_info.get("tcgplayer", {}).get("prices", {})
    if isinstance(tcg_prices, dict):
        for variant_name, price_dict in tcg_prices.items():
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


def _get_tcgcsv_groups() -> list:
    global _tcgcsv_groups
    with _tcgcsv_lock:
        if _tcgcsv_groups is not None:
            return _tcgcsv_groups
    groups = []
    try:
        r = requests.get("https://tcgcsv.com/tcgplayer/3/groups", headers=_HTTP_HEADERS, timeout=10)
        if r.status_code == 200:
            groups = r.json().get("results", [])
    except Exception:
        pass
    with _tcgcsv_lock:
        _tcgcsv_groups = groups
    return groups


def _fetch_tcgcsv_price(card_name: str, set_name: str, number: str) -> dict | None:
    """Busca precio en el espejo público diario TCGCSV (tcgcsv.com) para el set y carta dados."""
    if not set_name or set_name in ("N/A", "TCGDex") or not card_name:
        return None

    groups = _get_tcgcsv_groups()
    if not groups:
        return None

    norm_set = _normalize_text(set_name)
    matched_group_id = None
    for g in groups:
        gname = _normalize_text(g.get("name", ""))
        if gname == norm_set or (len(norm_set) >= 4 and (norm_set in gname or gname in norm_set)):
            matched_group_id = g.get("groupId")
            break

    if not matched_group_id:
        return None

    with _tcgcsv_lock:
        cached = _tcgcsv_group_cache.get(matched_group_id)

    if cached is None:
        try:
            r_prod = requests.get(
                f"https://tcgcsv.com/tcgplayer/3/{matched_group_id}/products",
                headers=_HTTP_HEADERS,
                timeout=10,
            )
            r_prc = requests.get(
                f"https://tcgcsv.com/tcgplayer/3/{matched_group_id}/prices",
                headers=_HTTP_HEADERS,
                timeout=10,
            )
            if r_prod.status_code != 200 or r_prc.status_code != 200:
                return None
            products = r_prod.json().get("results", [])
            prices_raw = r_prc.json().get("results", [])
            prices_map = {}
            for pr in prices_raw:
                pid = pr.get("productId")
                if pid is not None:
                    prices_map.setdefault(pid, []).append(pr)
            cached = (products, prices_map)
            with _tcgcsv_lock:
                _tcgcsv_group_cache[matched_group_id] = cached
        except Exception:
            return None

    products, prices_map = cached
    norm_name = _normalize_text(card_name)
    num_clean = str(number or "").lstrip("0") if str(number or "").isdigit() else str(number or "").strip().lower()

    best_product_id = None
    for prod in products:
        pname = _normalize_text(prod.get("name", ""))
        if norm_name not in pname:
            continue
        # Verificar número si está en extendedData
        if num_clean:
            ext_data = prod.get("extendedData", [])
            ext_num = None
            for ed in ext_data:
                if ed.get("name", "").lower() == "number":
                    val = str(ed.get("value", "")).split("/")[0].strip().lower()
                    ext_num = val.lstrip("0") if val.isdigit() else val
                    break
            if ext_num and ext_num == num_clean:
                best_product_id = prod.get("productId")
                break
        if best_product_id is None:
            best_product_id = prod.get("productId")

    if best_product_id is None:
        return None

    entries = prices_map.get(best_product_id, [])
    for entry in entries:
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

    # Sincronizar Cartas.price con el precio primario USD más confiable
    primary_usd = 0.0
    for src in ("TCGPlayer", "TCGMatch", "PokemonTCG", "TCGCSV"):
        if src in precios_por_fuente and precios_por_fuente[src].get("precio_usd", 0) > 0:
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
    Retorna:
      - multi_prices: {id_api -> {fuente -> {moneda, precio_usd, precio_original}}}
      - base_prices:  {id_api -> float (Cartas.price)}
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


def fetch_multi_api_prices(
    id_api: str,
    idioma: str = "en",
    card_name: str = None,
    set_name: str = None,
    number: str = None,
    include_tcgcsv: bool = True,
    save_to_db: bool = True,
) -> dict:
    """
    Consulta múltiples APIs de Pokémon TCG en vivo para una carta:
      1. TCGdex v2 -> TCGPlayer (USD) + Cardmarket (EUR)
      2. Pokémon TCG API (pokemontcg.io) -> PokemonTCG (USD/EUR)
      3. TCGCSV (tcgcsv.com) -> TCGCSV (USD)
    Guarda resultados en BD si save_to_db=True y retorna diccionario por fuente.
    """
    if not id_api:
        return {}

    precios = {}
    lang_code = normalize_lang_code(idioma)
    tcgdex_lang = TCGDEX_LANG_MAP.get(lang_code, "en")

    # 1. TCGdex (provee TCGPlayer gratis y sin clave)
    tcgdex_data = None
    for t_lang in ([tcgdex_lang, "en"] if tcgdex_lang != "en" else ["en"]):
        try:
            r = requests.get(
                f"https://api.tcgdex.net/v2/{t_lang}/cards/{id_api}",
                headers=_HTTP_HEADERS,
                timeout=8,
            )
            if r.status_code == 200:
                tcgdex_data = r.json()
                extracted = _extract_tcgdex_prices(tcgdex_data)
                if extracted:
                    precios.update(extracted)
                    if not set_name or set_name in ("TCGDex", "N/A"):
                        set_name = tcgdex_data.get("set", {}).get("name") or set_name
                    if not card_name:
                        card_name = tcgdex_data.get("name")
                    if not number or number == "N/A":
                        number = tcgdex_data.get("localId") or number
                    break
        except Exception:
            pass

    # 1b. TCGMatch (mercado latinoamericano / tcgmatch.cl)
    if card_name:
        tcgm_price = consultar_precio_tcgmatch(card_name, number=number, set_name=set_name)
        if tcgm_price:
            precios["TCGMatch"] = tcgm_price

    # 2. Pokémon TCG API (api.pokemontcg.io)
    ptcg_id = tcgdex_to_pokemontcg_id(id_api)
    candidates_ptcg = [id_api]
    if ptcg_id and ptcg_id != id_api:
        candidates_ptcg.append(ptcg_id)

    for cand_id in candidates_ptcg:
        try:
            r_ptcg = requests.get(
                f"https://api.pokemontcg.io/v2/cards/{cand_id}",
                headers=_HTTP_HEADERS,
                timeout=8,
            )
            if r_ptcg.status_code == 200:
                c_data = r_ptcg.json().get("data", {})
                if c_data:
                    p_info = _extract_pokemontcg_price(c_data)
                    if p_info:
                        precios["PokemonTCG"] = p_info
                    if not set_name or set_name in ("TCGDex", "N/A"):
                        set_name = c_data.get("set", {}).get("name") or set_name
                    if not card_name:
                        card_name = c_data.get("name")
                    if not number or number == "N/A":
                        number = c_data.get("number") or number
                    break
        except Exception:
            continue

    # 3. TCGCSV (espejo público diario de TCGplayer)
    if include_tcgcsv and card_name and set_name and set_name not in ("TCGDex", "N/A"):
        csv_price = _fetch_tcgcsv_price(card_name, set_name, number)
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
            )
            self.prices_loaded.emit(self.id_api, precios)
        except Exception as e:
            self.error.emit(str(e))


class PriceUpdaterThread(QThread):
    """
    Hilo en segundo plano que sincroniza precios en tiempo real desde múltiples APIs:
    - TCGdex v2 (TCGPlayer USD + Cardmarket EUR)
    - Pokémon TCG API (pokemontcg.io)
    Almacena precios por fuente en `carta_precios` y sincroniza `Cartas.price`.
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
        """Normaliza IDs que pueden venir como 'id_api', 'id_api:lang', o (id_api, lang)."""
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

            # Fase 1: Consultar Pokémon TCG API en lotes de 25 para obtener fuente "PokemonTCG"
            ptcg_results = {}  # original_id -> price_dict
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
                    resp = requests.get(url, headers=_HTTP_HEADERS, timeout=12)
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

            # Fase 2: Consultar TCGdex (TCGPlayer + Cardmarket) por carta y consolidar en BD
            for idx, (cid, lang) in enumerate(targets, start=1):
                if not self.is_running:
                    break

                precios_carta = {}
                if cid in ptcg_results:
                    precios_carta["PokemonTCG"] = ptcg_results[cid]

                tcgdex_lang = TCGDEX_LANG_MAP.get(lang, "en")
                for t_lang in ([tcgdex_lang, "en"] if tcgdex_lang != "en" else ["en"]):
                    try:
                        r = requests.get(
                            f"https://api.tcgdex.net/v2/{t_lang}/cards/{cid}",
                            headers=_HTTP_HEADERS,
                            timeout=7,
                        )
                        if r.status_code == 200:
                            ext = _extract_tcgdex_prices(r.json())
                            if ext:
                                precios_carta.update(ext)
                                break
                    except Exception:
                        pass

                if precios_carta:
                    guardar_precios_carta_bd(session, cid, precios_carta)
                    total_actualizadas += 1
                    if total_actualizadas % 5 == 0 or idx == total:
                        session.commit()

                self.progress.emit(idx, total)
                time.sleep(0.05)

            session.commit()
            self.finished.emit(total_actualizadas)

        except Exception as e:
            session.rollback()
            self.error.emit(str(e))
        finally:
            session.close()
