import sys
import os
import json
import shutil

APP_VERSION = "1.5.0"

# Rutas absolutas del proyecto
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    EXE_DIR = BUNDLE_DIR

PROJECT_ROOT = BUNDLE_DIR

# Carpetas de assets estáticos (empaquetados con el exe)
ASSETS_DIR = os.path.join(BUNDLE_DIR, "assets")
ICONS_DIR = os.path.join(ASSETS_DIR, "icons")
PERFIL_DIR = os.path.join(ASSETS_DIR, "perfil")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")
STYLE_FILE = os.path.join(ASSETS_DIR, "style.qss")
STYLE_DARK_FILE = os.path.join(ASSETS_DIR, "style_dark.qss")

# Directorio persistente local de datos del usuario (sobrevive a actualizaciones del launcher)
def get_user_data_dir() -> str:
    override = os.environ.get("POKEBINDER_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "PokeBinder")
    else:
        path = os.path.join(os.path.expanduser("~"), ".pokebinder")
    os.makedirs(path, exist_ok=True)
    return path

USER_DATA_DIR = get_user_data_dir()
BACKUPS_DIR = os.path.join(USER_DATA_DIR, "backups")
os.makedirs(BACKUPS_DIR, exist_ok=True)
HOLO_MASKS_DIR = os.path.join(USER_DATA_DIR, "holo_masks")
os.makedirs(HOLO_MASKS_DIR, exist_ok=True)

# Carpeta de imágenes descargadas (en la ruta del ejecutable para aprovechar assets-v1 del launcher)
IMAGES_DIR = os.path.join(EXE_DIR, "assets", "images")
IMAGES_HD_DIR = os.path.join(EXE_DIR, "assets", "images_hd")
IMAGES_WEBP_DIR = os.path.join(EXE_DIR, "assets", "images_webp")
os.makedirs(IMAGES_HD_DIR, exist_ok=True)
os.makedirs(IMAGES_WEBP_DIR, exist_ok=True)

TCGDEX_LANG_MAP = {
    "es": "es",
    "en": "en",
    "ja": "ja",
    "fr": "fr",
    "pt": "pt",
    "zh": "zh-tw"
}

LANG_NORMALIZE_MAP = {
    "es": "es", "español": "es", "espanol": "es", "spanish": "es",
    "en": "en", "inglés": "en", "ingles": "en", "english": "en",
    "ja": "ja", "japonés": "ja", "japones": "ja", "japanese": "ja",
    "fr": "fr", "francés": "fr", "frances": "fr", "french": "fr",
    "pt": "pt", "portugués": "pt", "portugues": "pt", "portuguese": "pt",
    "zh": "zh", "chino": "zh", "chinese": "zh", "zh-tw": "zh", "tw": "zh"
}

def normalize_lang_code(lang: str) -> str:
    if not lang:
        return "es"
    clean = str(lang).strip().lower()
    return LANG_NORMALIZE_MAP.get(clean, clean[:2] if len(clean) >= 2 else "es")

VARIANT_COLOR_MAP = {
    "Normal": {"name": "Normal", "color": "#0284c7", "border": "#38bdf8"},
    "Holográfica": {"name": "Holográfica", "color": "#9333ea", "border": "#c084fc"},
    "Holográfica Reverse": {"name": "Holográfica Reverse", "color": "#16a34a", "border": "#4ade80"},
    "Pokeball": {"name": "Pokeball", "color": "#dc2626", "border": "#f87171"},
    "Masterball": {"name": "Masterball", "color": "#a21caf", "border": "#e879f9"},
    "Full Art": {"name": "Full Art", "color": "#d97706", "border": "#fbbf24"},
    "Cosmo Holo": {"name": "Cosmo Holo", "color": "#4f46e5", "border": "#818cf8"},
    "Cracked Ice Holo": {"name": "Cracked Ice Holo", "color": "#06b6d4", "border": "#67e8f9"},
    "Confetti Holo": {"name": "Confetti Holo", "color": "#ec4899", "border": "#f9a8d4"},
}

LEGACY_VARIANT_MAP = {
    "holo": "Holográfica",
    "holografica": "Holográfica",
    "holográfica": "Holográfica",
    "reverse": "Holográfica Reverse",
    "reverse holo": "Holográfica Reverse",
    "holografica reverse": "Holográfica Reverse",
    "holográfica reverse": "Holográfica Reverse",
    "pokeball": "Pokeball",
    "masterball": "Masterball",
    "full art": "Full Art",
    "cosmo holo": "Cosmo Holo",
    "cracked ice holo": "Cracked Ice Holo",
    "confetti holo": "Confetti Holo",
    "normal": "Normal",
    "normal / base": "Normal",
}


def normalize_variant_name(variante: str | None) -> str:
    """Normaliza cualquier nombre de variante (incluyendo heredados) al catálogo oficial de Variantes."""
    if not variante:
        return "Normal"
    if variante in VARIANT_COLOR_MAP:
        return variante
    key = str(variante).strip().lower()
    return LEGACY_VARIANT_MAP.get(key, "Normal")


# Base de datos y persistencia de usuario en AppData/Local/PokeBinder
SEED_DB_PATH = os.path.join(BUNDLE_DIR, "PokeDatabase.db")
DB_PATH = os.path.join(USER_DATA_DIR, "PokeDatabase.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Configuración y Persistencia de Carpetas/Binders
SETTINGS_FILE = os.path.join(USER_DATA_DIR, "settings.json")
BINDER_DATA_FILE = os.path.join(USER_DATA_DIR, "binder_data.json")


def ensure_user_data_initialized():
    """
    Inicializa los archivos persistentes del usuario en USER_DATA_DIR (%LOCALAPPDATA%\\PokeBinder)
    si aún no existen, migrando datos previos de la carpeta instalada/bundle cuando corresponda.
    Así el usuario jamás pierde sus sesiones, colecciones ni binders al actualizar la aplicación.
    """
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    # 1. Base de datos SQLite
    if not os.path.exists(DB_PATH):
        legacy_candidates = [
            os.path.join(EXE_DIR, "PokeDatabase.db"),
            os.path.join(EXE_DIR, "_internal", "PokeDatabase.db"),
            SEED_DB_PATH,
        ]
        for cand in legacy_candidates:
            if cand and os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(DB_PATH):
                try:
                    shutil.copy2(cand, DB_PATH)
                    print(f"[Storage] Base de datos inicializada en {DB_PATH} desde {cand}")
                    break
                except Exception as e:
                    print(f"[Storage] Error copiando DB desde {cand}: {e}")

    # 2. Datos de Binders (binder_data.json)
    if not os.path.exists(BINDER_DATA_FILE):
        migrated = False
        legacy_binder_candidates = [
            os.path.join(EXE_DIR, "assets", "binder_data.json"),
            os.path.join(EXE_DIR, "_internal", "assets", "binder_data.json"),
            os.path.join(ASSETS_DIR, "binder_data.json"),
        ]
        for cand in legacy_binder_candidates:
            if cand and os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(BINDER_DATA_FILE):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        content = json.load(f)
                    if isinstance(content, dict) and len(content) > 0:
                        shutil.copy2(cand, BINDER_DATA_FILE)
                        print(f"[Storage] binder_data.json migrado desde {cand}")
                        migrated = True
                        break
                except Exception:
                    pass
        if not migrated:
            try:
                with open(BINDER_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=4)
            except Exception as e:
                print(f"[Storage] Error inicializando binder_data.json: {e}")

    # 3. Configuración (settings.json)
    if not os.path.exists(SETTINGS_FILE):
        legacy_settings_candidates = [
            os.path.join(EXE_DIR, "assets", "settings.json"),
            os.path.join(ASSETS_DIR, "settings.json"),
        ]
        for cand in legacy_settings_candidates:
            if cand and os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(SETTINGS_FILE):
                try:
                    shutil.copy2(cand, SETTINGS_FILE)
                    break
                except Exception:
                    pass


ensure_user_data_initialized()

DEFAULT_SETTINGS = {
    "volumen_musica": 20,
    "volumen_sonido": 80,
    "pista_musica": 1,
    "animaciones": True,
    "velocidad_animaciones": "Equilibrado",
    "tema_oscuro": False,
    "tamano_fuente": 14,
    "idioma": "Español",
    "tamano_cartas": "Normal",
    "tcgmatch_api_key": "",
    "moneda": "USD",
}

SUPPORTED_CURRENCIES = {
    "USD": {"name": "USD - Dólar ($)", "symbol": "$", "decimals": 2, "rate_from_usd": 1.0},
    "CLP": {"name": "CLP - Peso Chileno ($)", "symbol": "$", "decimals": 0, "rate_from_usd": 950.0},
    "EUR": {"name": "EUR - Euro (€)", "symbol": "€", "decimals": 2, "rate_from_usd": 0.92},
    "MXN": {"name": "MXN - Peso Mexicano ($)", "symbol": "$", "decimals": 2, "rate_from_usd": 20.2},
    "ARS": {"name": "ARS - Peso Argentino ($)", "symbol": "$", "decimals": 0, "rate_from_usd": 1000.0},
    "COP": {"name": "COP - Peso Colombiano ($)", "symbol": "$", "decimals": 0, "rate_from_usd": 4400.0},
    "PEN": {"name": "PEN - Sol Peruano (S/)", "symbol": "S/", "decimals": 2, "rate_from_usd": 3.75},
    "BRL": {"name": "BRL - Real Brasileño (R$)", "symbol": "R$", "decimals": 2, "rate_from_usd": 5.80},
}

ANIMATION_SPEED_FACTORS = {
    "Rápido": 0.65,
    "Equilibrado": 1.0,
    "Cinematográfico": 1.42,
}


def get_animation_duration_scale() -> float:
    """Retorna el multiplicador de duración de animaciones según el ritmo configurado."""
    settings = load_settings()
    speed_key = settings.get("velocidad_animaciones", "Equilibrado")
    return ANIMATION_SPEED_FACTORS.get(speed_key, 1.0)


def scale_anim_duration(base_ms: int, min_ms: int = 90) -> int:
    """Escala una duración base en milisegundos según el ritmo de animaciones activo."""
    return max(int(min_ms), int(round(base_ms * get_animation_duration_scale())))

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {**DEFAULT_SETTINGS, **data}
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error guardando settings: {e}")

def apply_global_style(app):
    import re
    settings = load_settings()
    es_oscuro = settings.get("tema_oscuro", False)
    font_size = settings.get("tamano_fuente", 14)
    
    path = STYLE_DARK_FILE if es_oscuro else STYLE_FILE
    if not os.path.exists(path):
        return
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        scale = font_size / 14.0
        
        def repl(match):
            orig_val = int(match.group(1))
            new_val = max(6, int(orig_val * scale))
            return f"font-size: {new_val}px;"
            
        new_content = re.sub(r"font-size\s*:\s*(\d+)px\s*;", repl, content)
        app.setStyleSheet(new_content)
    except Exception as e:
        print(f"Error applying stylesheet: {e}")

MUSIC_TRACK_NAMES = {
    1: "Calum Bowen - Everything's Gonna Be Okay",
    2: "Tsundere Twintails - Morning Alarm",
    3: "Pokemón - Lake",
    4: "Kokonoku - 1:21 Pm",
    5: "2010 Toyota Corolla",
    6: "Dosbomb. - Meow.",
    7: "Ryo Aratani - Neko Atsume no Theme",
    8: "Tsundere Twintails - Rest Area",
    9: "Tsundere Twintails - A Letter",
    10: "Tsundere Twintails - Sunshine",
    11: "Tsundere Twintails - Waiting",
}

def get_music_track_path(pista: int) -> str:
    """Retorna la ruta completa al archivo de música de la pista dada, probando extensiones mp3, m4a, wav, ogg."""
    for ext in [".mp3", ".m4a", ".wav", ".ogg"]:
        filename = f"musica_fondo_{pista}{ext}"
        path = os.path.join(SOUNDS_DIR, filename)
        if os.path.exists(path):
            return path
    return os.path.join(SOUNDS_DIR, f"musica_fondo_{pista}.mp3")

def get_available_music_tracks() -> list:
    """Retorna la lista ordenada de números de pista musicales presentes en assets/sounds."""
    tracks = set()
    if os.path.exists(SOUNDS_DIR):
        for fname in os.listdir(SOUNDS_DIR):
            if fname.startswith("musica_fondo_"):
                base = fname.replace("musica_fondo_", "")
                parts = base.split(".")
                if parts[0].isdigit():
                    tracks.add(int(parts[0]))
    return sorted(list(tracks)) if tracks else [1, 2, 3]
