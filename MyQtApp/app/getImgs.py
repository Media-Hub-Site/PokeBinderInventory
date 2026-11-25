import io
import os
import re
import threading
import requests
from PIL import Image
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QThreadPool, QRect
from MyQtApp.ui.pixmap_cache import get_cached_pixmap

from MyQtApp.config import (
    ASSETS_DIR,
    EXE_DIR,
    IMAGES_DIR,
    IMAGES_HD_DIR,
    IMAGES_WEBP_DIR,
    TCGDEX_LANG_MAP,
    normalize_lang_code,
)

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(IMAGES_HD_DIR, exist_ok=True)
os.makedirs(IMAGES_WEBP_DIR, exist_ok=True)

# Caché en memoria thread-safe para evitar os.walk e hilos de carga pesados
_cache_lock = threading.RLock()
_image_cache = {}
_cache_initialized = False
_pixmap_cache = {}
_placeholder_cache = {}

# Índice ligero de URLs de imagen por idioma obtenido desde TCGdex (1 petición por idioma/sesión)
_tcgdex_index_lock = threading.Lock()
_tcgdex_image_index = {}  # lang_code -> {card_id_lower: image_base_url}
_failed_downloads = set()  # (clean_id, lang_code) que fallaron en esta sesión

_HTTP_HEADERS = {
    "User-Agent": "PokeBinder/1.5 (https://github.com/Media-Hub-Site/PokeBinderInventory)"
}


def _clean_card_filename(nombre_archivo: str) -> str:
    raw = str(nombre_archivo or "card").lower().replace(" ", "_")
    cleaned = "".join(c for c in raw if c.isalnum() or c == "_")
    return cleaned or "card"


def _init_cache():
    global _cache_initialized
    with _cache_lock:
        if _cache_initialized:
            return
        print("Inicializando caché de imágenes...")
        dirs_to_scan = [IMAGES_DIR, IMAGES_WEBP_DIR]
        for d in dirs_to_scan:
            if os.path.exists(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        full_path = os.path.join(root, f)
                        f_lower = f.lower()
                        _image_cache[f_lower] = full_path
                        try:
                            rel = os.path.relpath(full_path, d).replace("\\", "/").lower()
                            _image_cache[rel] = full_path
                        except Exception:
                            pass
        _cache_initialized = True
        print(f"Caché de imágenes listo con {len(_image_cache)} archivos registrados.")


def register_image_in_cache(full_path: str, base_dir: str = None):
    """Registra una imagen recién descargada en los diccionarios de caché en memoria."""
    if not full_path or not os.path.exists(full_path):
        return
    with _cache_lock:
        f_lower = os.path.basename(full_path).lower()
        _image_cache[f_lower] = full_path
        for root_dir in [base_dir, IMAGES_DIR, IMAGES_WEBP_DIR]:
            if root_dir:
                try:
                    rel = os.path.relpath(full_path, root_dir).replace("\\", "/").lower()
                    if not rel.startswith(".."):
                        _image_cache[rel] = full_path
                except Exception:
                    pass


def get_pixmap_from_zip(relative_path, size=None, id_api=None):
    """
    Carga una imagen desde la carpeta assets/images y la retorna como QPixmap,
    utilizando un caché en memoria para evitar recargas costosas de disco.
    """
    cache_key = (relative_path, size, id_api)
    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    try:
        _init_cache()

        rel_path = relative_path.replace("\\\\", "/").lstrip("/")
        base_name = os.path.basename(rel_path)
        name_no_ext, ext = os.path.splitext(base_name)

        raw_name = name_no_ext.lower().replace(" ", "_")
        alnum_name = "".join(c for c in raw_name if c.isalnum() or c == "_")

        name_variants = [raw_name]
        if alnum_name != raw_name:
            name_variants.append(alnum_name)

        clean_id = str(id_api).lower() if id_api else None

        found = None
        candidates_keys = []
        extensions = [".webp", ".png", ".jpg", ".jpeg"]

        for n in name_variants:
            if clean_id:
                for e in extensions:
                    candidates_keys.append(f"{n}_{clean_id}{e}")
            if ext:
                candidates_keys.append(f"{n}{ext.lower()}")
            for e in extensions:
                candidates_keys.append(f"{n}{e}")

        if ext and base_name.lower() not in candidates_keys:
            candidates_keys.append(base_name.lower())

        with _cache_lock:
            for key in candidates_keys:
                if key in _image_cache:
                    found = _image_cache[key]
                    break

            if not found and clean_id:
                suffixes = tuple(f"_{clean_id}{e}" for e in extensions)
                for key, path in _image_cache.items():
                    if key.endswith(suffixes):
                        found = path
                        break

        if not found:
            for search_dir in [IMAGES_DIR, IMAGES_WEBP_DIR]:
                for n in name_variants:
                    if clean_id:
                        for e in extensions:
                            for target_id in [id_api, clean_id]:
                                posible = os.path.join(search_dir, f"{n}_{target_id}{e}")
                                if os.path.exists(posible):
                                    found = posible
                                    register_image_in_cache(posible, search_dir)
                                    break
                            if found:
                                break
                    if found:
                        break
                if found:
                    break

        if not found:
            return None

        pix = QPixmap(found)
        if pix.isNull():
            return None

        if size:
            pix = pix.scaled(
                size[0],
                size[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        _pixmap_cache[cache_key] = pix
        return pix

    except Exception as e:
        print(f"Error al procesar la imagen: {str(e)}")
        return None


def save_bytes_as_webp(image_bytes: bytes, target_path: str, quality=85) -> bool:
    """Convierte cualquier byte de imagen (PNG/JPG/WebP) a formato .webp comprimido."""
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        # Si ya viene en formato WebP válido (RIFF....WEBP), guardar directo sin recodificar
        if len(image_bytes) > 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            with open(target_path, "wb") as f:
                f.write(image_bytes)
            return True

        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        img.save(target_path, "WEBP", quality=quality, optimize=True)
        return True
    except Exception as e:
        print(f"Error convirtiendo a WebP: {e}")
        return False


def save_bytes_as_png(image_bytes: bytes, target_path: str) -> bool:
    """Guarda cualquier byte de imagen (PNG/WebP/JPG) en alta definición en formato .png en assets/images_hd."""
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(target_path, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"Error guardando PNG HD: {e}")
        return False


def get_hd_pixmap(id_api, nombre_archivo=None, idioma="es", size=None):
    """Busca y retorna la versión en alta definición (.png) guardada localmente en assets/images_hd."""
    if not id_api:
        return None

    lang_code = normalize_lang_code(idioma)
    clean_id = str(id_api).lower()
    clean_name = _clean_card_filename(nombre_archivo)

    candidates = [
        os.path.join(IMAGES_HD_DIR, lang_code, f"{clean_name}_{clean_id}_hires.png"),
        os.path.join(IMAGES_HD_DIR, lang_code, f"{clean_name}_{clean_id}.png"),
        os.path.join(IMAGES_HD_DIR, f"{clean_name}_{clean_id}_hires.png"),
        os.path.join(IMAGES_HD_DIR, f"{clean_name}_{clean_id}.png"),
    ]

    for path in candidates:
        if os.path.exists(path):
            pix = (
                get_cached_pixmap(path, size[0], size[1], keep_aspect=True, smooth=True)
                if size
                else get_cached_pixmap(path)
            )
            if pix and not pix.isNull():
                return pix
    return None


def get_webp_pixmap(id_api, nombre_archivo=None, idioma="es", size=None, allow_lang_fallback=True):
    """Busca y retorna la versión comprimida en .webp/png/jpg de la carta según idioma."""
    if not id_api:
        return None

    lang_code = normalize_lang_code(idioma)
    clean_id = str(id_api).lower()
    clean_name = _clean_card_filename(nombre_archivo)

    # 1. Probar primero si ya tenemos versión HD guardada localmente
    hd_pix = get_hd_pixmap(id_api, nombre_archivo, idioma, size)
    if hd_pix and not hd_pix.isNull():
        return hd_pix

    _init_cache()

    possible_keys = [
        f"{lang_code}/{clean_name}_{clean_id}.webp",
        f"{lang_code}/{clean_name}_{clean_id}.png",
    ]
    if allow_lang_fallback:
        possible_keys.extend([
            f"en/{clean_name}_{clean_id}.webp",
            f"es/{clean_name}_{clean_id}.webp",
            f"{clean_name}_{clean_id}.webp",
            f"{clean_name}_{clean_id}.png",
        ])

    with _cache_lock:
        for k in possible_keys:
            path = _image_cache.get(k)
            if path and os.path.exists(path):
                pix = (
                    get_cached_pixmap(path, size[0], size[1], keep_aspect=True, smooth=True)
                    if size
                    else get_cached_pixmap(path)
                )
                if pix and not pix.isNull():
                    return pix

    if allow_lang_fallback:
        pix = get_pixmap_from_zip(clean_name, size=size, id_api=clean_id)
        if pix and not pix.isNull():
            return pix

    return None


def has_exact_lang_image(id_api, nombre_archivo=None, idioma="es") -> bool:
    """Verifica rápidamente si existe una imagen local exacta para ese id_api en el idioma dado."""
    if not id_api:
        return False
    _init_cache()
    lang_code = normalize_lang_code(idioma)
    clean_id = str(id_api).lower()
    clean_name = _clean_card_filename(nombre_archivo)
    with _cache_lock:
        for ext in (".webp", ".png", ".jpg"):
            k = f"{lang_code}/{clean_name}_{clean_id}{ext}"
            if k in _image_cache and os.path.exists(_image_cache[k]):
                return True
    return False


def get_card_placeholder_pixmap(size=(120, 170), card_name: str = "") -> QPixmap:
    """Genera un placeholder limpio basado en card_back.png mientras se descarga el .webp."""
    w, h = int(size[0]), int(size[1])
    base_key = (w, h)
    base_pix = _placeholder_cache.get(base_key)

    if base_pix is None:
        card_back_candidates = [
            os.path.join(ASSETS_DIR, "card_back.png"),
            os.path.join(EXE_DIR, "assets", "card_back.png"),
        ]
        loaded = None
        for p in card_back_candidates:
            if os.path.exists(p):
                tmp = QPixmap(p)
                if not tmp.isNull():
                    loaded = tmp.scaled(
                        w, h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    break

        if loaded is None:
            loaded = QPixmap(w, h)
            loaded.fill(Qt.GlobalColor.transparent)
            p = QPainter(loaded)
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor("#2a2038"))
            grad.setColorAt(1.0, QColor("#4a2d4c"))
            p.fillRect(0, 0, w, h, grad)
            p.end()

        _placeholder_cache[base_key] = loaded
        base_pix = loaded

    if not card_name:
        return base_pix

    result = QPixmap(base_pix)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    bar_h = max(24, int(h * 0.22))
    bar_rect = QRect(4, h - bar_h - 4, w - 8, bar_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(15, 23, 42, 200))
    painter.drawRoundedRect(bar_rect, 6, 6)

    painter.setPen(QColor("#f8fafc"))
    font = QFont("Segoe UI", max(7, min(9, int(w / 14))), QFont.Weight.Bold)
    painter.setFont(font)
    display_name = card_name if len(card_name) <= 18 else card_name[:16] + "..."
    painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, display_name)
    painter.end()
    return result


def tcgdex_to_pokemontcg_id(id_api: str) -> str:
    """Convierte IDs estilo TCGdex (ej. sv03.5-001, swsh12.5-111) a formato pokemontcg.io (sv3pt5-1)."""
    if not id_api or "-" not in id_api:
        return id_api or ""
    set_part, num_part = id_api.split("-", 1)
    s = set_part.lower()
    # ej. sv03.5 -> sv3pt5, sv01 -> sv1, swsh12.5 -> swsh12pt5
    s = re.sub(r"^([a-z]+)0+(\d)", r"\1\2", s)
    s = s.replace(".", "pt")
    n = num_part.lstrip("0") if num_part.isdigit() else num_part
    n = n or "0"
    return f"{s}-{n}"


def _get_tcgdex_image_index(lang_code: str) -> dict:
    """
    Descarga y cachea en memoria el mapa {id_lower: base_image_url} de TCGdex para un idioma.
    Solo hace 1 llamada HTTP por idioma en toda la sesión, acelerando drásticamente la galería.
    """
    lang_code = normalize_lang_code(lang_code)
    with _tcgdex_index_lock:
        if lang_code in _tcgdex_image_index:
            return _tcgdex_image_index[lang_code]

    tcgdex_lang = TCGDEX_LANG_MAP.get(lang_code, "en")
    mapping = {}
    try:
        resp = requests.get(
            f"https://api.tcgdex.net/v2/{tcgdex_lang}/cards",
            headers=_HTTP_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            for item in resp.json():
                cid = item.get("id")
                img = item.get("image")
                if cid and img:
                    mapping[cid.lower()] = img
    except Exception as e:
        print(f"No se pudo cargar índice TCGdex [{lang_code}]: {e}")

    with _tcgdex_index_lock:
        _tcgdex_image_index[lang_code] = mapping
    return mapping


def download_card_webp(id_api: str, nombre_archivo: str = None, idioma: str = "es", set_id: str = None, number: str = None) -> str | None:
    """
    Descarga y guarda la imagen .webp de una carta consultando múltiples APIs en cascada:
    1. TCGdex (idioma nativo de la carta, formato .webp directo)
    2. TCGdex (fallback inglés si la edición en ese idioma no tiene escaneo)
    3. Pokémon TCG API / CDN images.pokemontcg.io (conversión automática a .webp)
    Retorna la ruta local del archivo .webp guardado o None si no se encontró en ninguna fuente.
    """
    if not id_api:
        return None

    lang_code = normalize_lang_code(idioma)
    clean_id = str(id_api).lower()
    clean_name = _clean_card_filename(nombre_archivo or id_api)

    target_dir = os.path.join(IMAGES_DIR, lang_code)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, f"{clean_name}_{clean_id}.webp")

    if os.path.exists(target_path) and os.path.getsize(target_path) > 100:
        register_image_in_cache(target_path, IMAGES_DIR)
        return target_path

    fail_key = (clean_id, lang_code)
    if fail_key in _failed_downloads:
        return None

    urls_to_try = []

    # 1. Buscar URL directa en índice TCGdex del idioma nativo
    idx_native = _get_tcgdex_image_index(lang_code)
    base_native = idx_native.get(clean_id)
    if base_native:
        urls_to_try.append(f"{base_native}/low.webp")
        urls_to_try.append(f"{base_native}/high.webp")
    else:
        # Consulta puntual a TCGdex idioma nativo (en caso de ID con mayúsculas/formato distinto)
        tcgdex_lang = TCGDEX_LANG_MAP.get(lang_code, "en")
        try:
            r = requests.get(
                f"https://api.tcgdex.net/v2/{tcgdex_lang}/cards/{id_api}",
                headers=_HTTP_HEADERS,
                timeout=6,
            )
            if r.status_code == 200:
                b = r.json().get("image")
                if b:
                    urls_to_try.append(f"{b}/low.webp")
                    urls_to_try.append(f"{b}/high.webp")
        except Exception:
            pass

    # 2. Fallback a índice TCGdex en inglés si el idioma nativo no tiene imagen escaneada
    if lang_code != "en":
        idx_en = _get_tcgdex_image_index("en")
        base_en = idx_en.get(clean_id)
        if base_en:
            urls_to_try.append(f"{base_en}/low.webp")

    # 3. Fallback a Pokémon TCG CDN (images.pokemontcg.io) con normalización de set_id y número
    ptcg_id = tcgdex_to_pokemontcg_id(id_api)
    if "-" in ptcg_id:
        p_set, p_num = ptcg_id.split("-", 1)
        urls_to_try.append(f"https://images.pokemontcg.io/{p_set}/{p_num}.png")
    if set_id and number:
        num_clean = str(number).lstrip("0") if str(number).isdigit() else str(number)
        urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{number}.png")
        if num_clean and num_clean != str(number):
            urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{num_clean}.png")

    # Deduplicar preservando orden
    seen = set()
    unique_urls = []
    for u in urls_to_try:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    for url in unique_urls:
        try:
            resp = requests.get(url, headers=_HTTP_HEADERS, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 200:
                if save_bytes_as_webp(resp.content, target_path):
                    register_image_in_cache(target_path, IMAGES_DIR)
                    return target_path
        except Exception:
            continue

    _failed_downloads.add(fail_key)
    return None


class _WebpFetchSignals(QObject):
    image_ready = pyqtSignal(str, str)  # (card_key, local_file_path)


class WebpImageFetchWorker(QRunnable):
    """Tarea ligera para descargar una imagen .webp en segundo plano sin bloquear la UI."""

    def __init__(self, card_key: str, id_api: str, nombre: str, idioma: str, set_id: str, number: str, signals: _WebpFetchSignals):
        super().__init__()
        self.card_key = card_key
        self.id_api = id_api
        self.nombre = nombre
        self.idioma = idioma
        self.set_id = set_id
        self.number = number
        self.signals = signals

    def run(self):
        path = download_card_webp(
            self.id_api,
            nombre_archivo=self.nombre,
            idioma=self.idioma,
            set_id=self.set_id,
            number=self.number,
        )
        if path:
            try:
                self.signals.image_ready.emit(self.card_key, path)
            except RuntimeError:
                pass


class CardImageLoaderManager(QObject):
    """Gestor concurrente (QThreadPool) para cargar imágenes .webp faltantes bajo demanda."""
    image_ready = pyqtSignal(str, str)  # (card_key, local_file_path)

    def __init__(self, max_threads: int = 6, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_threads)
        self._in_flight = set()
        self._signals = _WebpFetchSignals()
        self._signals.image_ready.connect(self._on_worker_ready)

    def request_image(self, card_key: str, id_api: str, nombre: str, idioma: str = "es", set_id: str = None, number: str = None):
        if card_key in self._in_flight:
            return
        self._in_flight.add(card_key)
        worker = WebpImageFetchWorker(card_key, id_api, nombre, idioma, set_id, number, self._signals)
        self.pool.start(worker)

    def _on_worker_ready(self, card_key: str, local_path: str):
        self._in_flight.discard(card_key)
        self.image_ready.emit(card_key, local_path)


class HDImageDownloaderThread(QThread):
    """Hilo en segundo plano para obtener e integrar la imagen Full HD en formato .png desde TCGDex o PokéAPI."""
    image_loaded = pyqtSignal(QPixmap, str)  # (pixmap, id_api)

    def __init__(self, id_api, set_id=None, number=None, nombre_archivo=None, idioma="es", parent=None):
        super().__init__(parent)
        self.id_api = id_api
        self.set_id = set_id
        self.number = number
        self.nombre_archivo = nombre_archivo or (id_api or "card")
        self.idioma = normalize_lang_code(idioma)

    def run(self):
        if not self.id_api:
            return

        clean_id = str(self.id_api).lower()
        clean_name = _clean_card_filename(self.nombre_archivo)

        lang_dir = os.path.join(IMAGES_HD_DIR, self.idioma)
        os.makedirs(lang_dir, exist_ok=True)

        hd_png_target = os.path.join(lang_dir, f"{clean_name}_{clean_id}_hires.png")
        root_hd_png_target = os.path.join(IMAGES_HD_DIR, f"{clean_name}_{clean_id}_hires.png")

        # 1. Si la imagen HD PNG ya existe localmente, cargarla directamente
        for target in [hd_png_target, root_hd_png_target]:
            if os.path.exists(target):
                pix = QPixmap(target)
                if pix and not pix.isNull():
                    self.image_loaded.emit(pix, self.id_api)
                    return

        # 2. Si no existe, descargar la imagen Full HD desde TCGDex o PokéAPI
        tcgdex_lang = TCGDEX_LANG_MAP.get(self.idioma, "en")
        urls_to_try = []

        idx_native = _get_tcgdex_image_index(self.idioma)
        base_img = idx_native.get(clean_id)
        if not base_img:
            try:
                api_card_url = f"https://api.tcgdex.net/v2/{tcgdex_lang}/cards/{self.id_api}"
                api_resp = requests.get(api_card_url, headers=_HTTP_HEADERS, timeout=6)
                if api_resp.status_code == 200:
                    base_img = api_resp.json().get("image")
            except Exception:
                pass

        if base_img:
            urls_to_try.append(f"{base_img}/high.png")
            urls_to_try.append(f"{base_img}/high.webp")
            urls_to_try.append(f"{base_img}/low.png")

        ptcg_id = tcgdex_to_pokemontcg_id(self.id_api)
        if "-" in ptcg_id:
            p_set, p_num = ptcg_id.split("-", 1)
            urls_to_try.append(f"https://images.pokemontcg.io/{p_set}/{p_num}_hires.png")
            urls_to_try.append(f"https://images.pokemontcg.io/{p_set}/{p_num}.png")

        set_id = self.set_id
        number = self.number
        if not set_id or not number:
            if "-" in self.id_api:
                parts = self.id_api.split("-")
                set_id = parts[0]
                number = "-".join(parts[1:])

        if set_id and number:
            num_clean = str(number).lstrip("0") if str(number).isdigit() else str(number)
            urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{number}_hires.png")
            urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{number}.png")
            if num_clean and num_clean != str(number):
                urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{num_clean}_hires.png")
                urls_to_try.append(f"https://images.pokemontcg.io/{set_id}/{num_clean}.png")

        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=_HTTP_HEADERS, timeout=12)
                if resp.status_code == 200 and len(resp.content) > 100:
                    if save_bytes_as_png(resp.content, hd_png_target):
                        pix = QPixmap(hd_png_target)
                        if pix and not pix.isNull():
                            self.image_loaded.emit(pix, self.id_api)
                            return
            except Exception as e:
                print(f"Error descargando imagen HD desde {url}: {e}")
