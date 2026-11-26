from sqlalchemy import or_
from sqlalchemy.orm import Session

try:
    from MyQtApp.models import Cartas, UsuarioCarta
except ImportError:  # pragma: no cover
    from models import Cartas, UsuarioCarta


# Orden lógico e intuitivo de filtros en la fila 2 (Buscar y Colecciones)
FILTER_FIELDS_ORDER = [
    ("Etapa", "stage"),
    ("Rule Box", "especial_type"),
    ("Entrenador", "trainer"),
    ("Rareza", "rarity"),
    ("Tag", "tag"),
]

# Valores basura / internos que NUNCA deben aparecer en los desplegables
EXCLUDED_FILTER_VALUES = {
    "Desconocido",
    "Desconocida",
    "Ninguno",
    "Normal",
    "N/A",
    "",
    "TCGDex",
}
_EXCLUDED_FILTER_VALUES_LOWER = {v.lower() for v in EXCLUDED_FILTER_VALUES} | {"none", "null"}

# Orden canónico por categoría de filtro
TYPE_ORDER = [
    "Grass",
    "Fire",
    "Water",
    "Lightning",
    "Psychic",
    "Fighting",
    "Darkness",
    "Metal",
    "Dragon",
    "Fairy",
    "Colorless",
]

STAGE_ORDER = [
    "Basic",
    "Stage 1",
    "Stage 2",
    "Baby",
    "Restored",
]

TRAINER_ORDER = [
    "Supporter",
    "Item",
    "Pokémon Tool",
    "Stadium",
    "Technical Machine",
]

RULE_BOX_ORDER = [
    "ex",
    "EX",
    "V",
    "VMAX",
    "VSTAR",
    "V-UNION",
    "GX",
    "MEGA",
    "Radiant",
    "BREAK",
    "LEGEND",
    "Level-Up",
    "ACE SPEC",
    "Prism Star",
    "Eternamax",
]

TAG_ORDER = [
    "Desconocido",
    "Tera",
    "Ancient",
    "Future",
    "Rapid Strike",
    "Single Strike",
    "Fusion Strike",
    "Ultra Beast",
    "Team Plasma",
    "TAG TEAM",
    "SP",
    "Star",
    "Prime",
]

_ORDER_BY_FIELD = {
    "type": TYPE_ORDER,
    "stage": STAGE_ORDER,
    "trainer": TRAINER_ORDER,
    "especial_type": RULE_BOX_ORDER,
}

# Traducciones amigables para opciones de filtros según idioma activo
TYPE_LABELS_ES = {
    "Water": "Agua",
    "Fire": "Fuego",
    "Grass": "Planta",
    "Lightning": "Rayo",
    "Electric": "Rayo",
    "Psychic": "Psíquico",
    "Fighting": "Lucha",
    "Darkness": "Oscuro",
    "Metal": "Metálico",
    "Dragon": "Dragón",
    "Fairy": "Hada",
    "Colorless": "Incoloro",
}

STAGE_LABELS_ES = {
    "Basic": "Básico",
    "Stage 1": "Etapa 1",
    "Stage 2": "Etapa 2",
    "Baby": "Bebé",
    "Restored": "Restaurado",
}

TRAINER_LABELS_ES = {
    "Supporter": "Partidario (Supporter)",
    "Item": "Objeto (Item)",
    "Pokémon Tool": "Herramienta Pokémon",
    "Pokemon Tool": "Herramienta Pokémon",
    "Stadium": "Estadio",
    "Technical Machine": "Máquina Técnica",
}

RULE_BOX_LABELS = {
    "Level-Up": "Level-Up (LV.X)",
}


def is_valid_filter_value(raw_value) -> bool:
    """Retorna True si el valor de BD es válido y no pertenece a valores basura/internos."""
    if raw_value is None:
        return False
    clean = str(raw_value).strip()
    if not clean:
        return False
    if clean in EXCLUDED_FILTER_VALUES or clean.lower() in _EXCLUDED_FILTER_VALUES_LOWER:
        return False
    return True


def sort_filter_values(field_name: str, raw_values) -> list[str]:
    """Filtra valores basura y ordena las opciones de un campo de manera intuitiva para jugadores de Pokémon TCG."""
    if field_name == "tag":
        return list(TAG_ORDER)

    cleaned_unique = []
    seen = set()
    for val in raw_values:
        if not isinstance(val, (str, bytes)) and hasattr(val, "__getitem__"):
            val = val[0] if len(val) > 0 else None
        if not is_valid_filter_value(val):
            continue
        s_val = str(val).strip()
        if s_val not in seen:
            seen.add(s_val)
            cleaned_unique.append(s_val)

    priority_list = _ORDER_BY_FIELD.get(field_name)
    if not priority_list:
        return sorted(cleaned_unique, key=lambda x: x.lower())

    priority_index = {name: idx for idx, name in enumerate(priority_list)}
    return sorted(
        cleaned_unique,
        key=lambda x: (0, priority_index[x]) if x in priority_index else (1, x.lower()),
    )


def _is_english_language(lang: str | None) -> bool:
    if not lang:
        return False
    norm = str(lang).strip().lower()
    return norm in ("english", "en", "inglés", "ingles")


def format_filter_option_label(field_name: str, raw_value: str, lang: str | None = None) -> str:
    """Devuelve la etiqueta traducida y formateada para mostrar en el QComboBox conservando raw_value en UserRole."""
    if raw_value is None:
        return ""
    val = str(raw_value).strip()
    is_en = _is_english_language(lang)

    if field_name == "especial_type":
        return RULE_BOX_LABELS.get(val, val)

    if field_name == "type":
        if is_en:
            return val
        return TYPE_LABELS_ES.get(val, val)

    if field_name == "stage":
        if is_en:
            return val
        return STAGE_LABELS_ES.get(val, val)

    if field_name == "trainer":
        if is_en:
            return val
        return TRAINER_LABELS_ES.get(val, val)

    if field_name == "tag":
        if is_en and val == "Desconocido":
            return "Unknown"
        return val

    return val


def apply_tag_filter(query, column, val):
    """Filtra una consulta SQLAlchemy por Tag individual o combinado (separado por ', ')."""
    if not val:
        return query
    if val == "Desconocido":
        return query.filter(or_(column == "Desconocido", column.is_(None), column == ""))
    return query.filter(
        or_(
            column == val,
            column.like(f"{val}, %"),
            column.like(f"%, {val}"),
            column.like(f"%, {val}, %"),
        )
    )


def filtro_cartas_sqlalchemy(
        session: Session,
        user,
        id_api=None, nPokemon=None, tipo=None, precio=None, rareza=None,
        number=None, set_id=None, set_name=None, stage=None, especial_type=None,
        trainer=None, edition=None, tag=None
    ):

    # Filtros dinámicos según tu diccionario original
    filtros = {
        "id_api": id_api,
        "nombre": nPokemon,
        "type": tipo,
        "price": precio,
        "rarity": rareza,
        "number": number,
        "set_id": set_id,
        "set_name": set_name,
        "stage": stage,
        "especial_type": especial_type,
        "trainer": trainer,
        "edition": edition
    }

    campos_like = ["nombre", "type", "rarity", "edition", "set_name", "especial_type", "trainer"]

    # Query base con JOIN a la tabla intermedia
    query = (
        session.query(Cartas)
        .join(UsuarioCarta, Cartas.id_api == UsuarioCarta.carta_id)
        .filter(UsuarioCarta.usuario_nombre == user)
    )

    # Construcción de filtros dinámicos
    for campo, valor in filtros.items():
        if valor not in (None, "", []):
            columna = getattr(Cartas, campo)
            if campo in campos_like:
                query = query.filter(columna.ilike(f"%{valor}%"))
            else:
                query = query.filter(columna == valor)

    if tag not in (None, "", []):
        query = apply_tag_filter(query, Cartas.tag, tag)

    resultados = query.all()

    for carta in resultados:
        print(
            f"{carta.nombre} | ID: {carta.id_api} | Tipo: {carta.type} | Precio: {carta.price}"
        )

    return resultados

