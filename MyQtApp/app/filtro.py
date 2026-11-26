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
    ("Expansión", "set_id"),
]

# Catálogo oficial ordenado de Series y Expansiones de Pokémon TCG (Issue #77)
EXPANSION_SERIES = [
    (
        "1. Serie Mega Evolution (2025 – 2026)",
        "1. Mega Evolution Series (2025 – 2026)",
        [
            {"key": "me_base", "name": "Mega Evolution", "set_ids": ("me1", "me01", "M1L", "M1S"), "set_names": ("Mega Evolution",)},
            {"key": "me_pf", "name": "Mega Evolution—Phantasmal Flames", "set_ids": ("me2", "me02", "M2"), "set_names": ("Phantasmal Flames", "Mega Evolution—Phantasmal Flames")},
            {"key": "me_ah", "name": "Mega Evolution—Ascended Heroes (Especial)", "set_ids": ("me2pt5", "me02.5", "M2a"), "set_names": ("Ascended Heroes", "Mega Evolution—Ascended Heroes")},
            {"key": "me_po", "name": "Mega Evolution—Perfect Order", "set_ids": ("me3", "me03", "M3"), "set_names": ("Perfect Order", "Mega Evolution—Perfect Order")},
            {"key": "me_cr", "name": "Mega Evolution—Chaos Rising", "set_ids": ("me4", "me04", "M4"), "set_names": ("Chaos Rising", "Mega Evolution—Chaos Rising")},
            {"key": "me_pb", "name": "Mega Evolution—Pitch Black", "set_ids": ("me5", "me05", "M5"), "set_names": ("Pitch Black", "Mega Evolution—Pitch Black")},
            {"key": "me_30th", "name": "30th Celebration (Especial)", "set_ids": ("me30", "me05.5", "me5pt5"), "set_names": ("30th Celebration",)},
            {"key": "me_dr", "name": "Mega Evolution—Delta Reign", "set_ids": ("me6", "me06", "M6"), "set_names": ("Delta Reign", "Mega Evolution—Delta Reign")},
        ],
    ),
    (
        "2. Serie Escarlata y Púrpura (2023 – 2025)",
        "2. Scarlet & Violet Series (2023 – 2025)",
        [
            {"key": "sv1", "name": "Scarlet & Violet", "set_ids": ("sv1", "sv01", "SV1S", "SV1V"), "set_names": ("Scarlet & Violet",)},
            {"key": "sv2", "name": "Paldea Evolved", "set_ids": ("sv2", "sv02", "SV1a", "SV2D", "SV2P"), "set_names": ("Paldea Evolved",)},
            {"key": "sv3", "name": "Obsidian Flames", "set_ids": ("sv3", "sv03", "SV3"), "set_names": ("Obsidian Flames",)},
            {"key": "sv3pt5", "name": "151 (Especial)", "set_ids": ("sv3pt5", "sv03.5", "SV2a"), "set_names": ("151",)},
            {"key": "sv4", "name": "Paradox Rift", "set_ids": ("sv4", "sv04", "SV3a", "SV4K", "SV4M"), "set_names": ("Paradox Rift",)},
            {"key": "sv4pt5", "name": "Paldean Fates (Especial)", "set_ids": ("sv4pt5", "sv04.5", "SV4a"), "set_names": ("Paldean Fates",)},
            {"key": "sv5", "name": "Temporal Forces", "set_ids": ("sv5", "sv05", "SV5K", "SV5M"), "set_names": ("Temporal Forces",)},
            {"key": "sv6", "name": "Twilight Masquerade", "set_ids": ("sv6", "sv06", "SV5a", "SV6"), "set_names": ("Twilight Masquerade",)},
            {"key": "sv6pt5", "name": "Shrouded Fable (Especial)", "set_ids": ("sv6pt5", "sv06.5", "SV6a"), "set_names": ("Shrouded Fable",)},
            {"key": "sv7", "name": "Stellar Crown", "set_ids": ("sv7", "sv07", "SV7"), "set_names": ("Stellar Crown",)},
            {"key": "sv8", "name": "Surging Sparks", "set_ids": ("sv8", "sv08", "SV7a", "SV8"), "set_names": ("Surging Sparks",)},
            {"key": "sv8pt5", "name": "Prismatic Evolutions (Especial)", "set_ids": ("sv8pt5", "sv08.5", "SV8a"), "set_names": ("Prismatic Evolutions",)},
            {"key": "sv9", "name": "Journey Together", "set_ids": ("sv9", "sv09", "SV9"), "set_names": ("Journey Together",)},
            {"key": "sv10", "name": "Destined Rivals", "set_ids": ("sv10", "SV9a", "SV10"), "set_names": ("Destined Rivals",)},
            {"key": "sv10pt5", "name": "Black Bolt & White Flare (Especiales)", "set_ids": ("zsv10pt5", "rsv10pt5", "sv10.5b", "sv10.5w", "SV11B", "SV11W"), "set_names": ("Black Bolt", "White Flare", "Black Bolt & White Flare")},
        ],
    ),
    (
        "3. Serie Espada y Escudo (2020 – 2023)",
        "3. Sword & Shield Series (2020 – 2023)",
        [
            {"key": "swsh1", "name": "Sword & Shield", "set_ids": ("swsh1",), "set_names": ("Sword & Shield",)},
            {"key": "swsh2", "name": "Rebel Clash", "set_ids": ("swsh2",), "set_names": ("Rebel Clash",)},
            {"key": "swsh3", "name": "Darkness Ablaze", "set_ids": ("swsh3",), "set_names": ("Darkness Ablaze",)},
            {"key": "swsh35", "name": "Champion's Path (Especial)", "set_ids": ("swsh35", "swsh3.5"), "set_names": ("Champion's Path",)},
            {"key": "swsh4", "name": "Vivid Voltage", "set_ids": ("swsh4", "S4"), "set_names": ("Vivid Voltage",)},
            {"key": "swsh45", "name": "Shining Fates (Especial)", "set_ids": ("swsh45", "swsh45sv", "swsh4.5", "swsh4.5sv", "S4a"), "set_names": ("Shining Fates", "Shining Fates Shiny Vault")},
            {"key": "swsh5", "name": "Battle Styles", "set_ids": ("swsh5", "S5I", "S5R"), "set_names": ("Battle Styles",)},
            {"key": "swsh6", "name": "Chilling Reign", "set_ids": ("swsh6", "S5a", "S6H", "S6K"), "set_names": ("Chilling Reign",)},
            {"key": "swsh7", "name": "Evolving Skies", "set_ids": ("swsh7", "S6a", "S7D", "S7R"), "set_names": ("Evolving Skies",)},
            {"key": "cel25", "name": "Celebrations (Especial 25.º Aniversario)", "set_ids": ("cel25", "cel25c", "cel25cc", "S8a"), "set_names": ("Celebrations", "Celebrations: Classic Collection")},
            {"key": "swsh8", "name": "Fusion Strike", "set_ids": ("swsh8", "S8"), "set_names": ("Fusion Strike",)},
            {"key": "swsh9", "name": "Brilliant Stars", "set_ids": ("swsh9", "swsh9tg", "swsh9.5tg", "S8b", "S9"), "set_names": ("Brilliant Stars", "Brilliant Stars Trainer Gallery")},
            {"key": "swsh10", "name": "Astral Radiance", "set_ids": ("swsh10", "swsh10tg", "swsh10.5tg", "S9a", "S10D", "S10P"), "set_names": ("Astral Radiance", "Astral Radiance Trainer Gallery")},
            {"key": "pgo", "name": "Pokémon GO (Especial)", "set_ids": ("pgo", "swsh10.5", "S10b"), "set_names": ("Pokémon GO",)},
            {"key": "swsh11", "name": "Lost Origin", "set_ids": ("swsh11", "swsh11tg", "swsh11.5tg", "S10a", "S11"), "set_names": ("Lost Origin", "Lost Origin Trainer Gallery")},
            {"key": "swsh12", "name": "Silver Tempest", "set_ids": ("swsh12", "swsh12tg", "swsh12.5tg", "S11a", "S12"), "set_names": ("Silver Tempest", "Silver Tempest Trainer Gallery")},
            {"key": "swsh12pt5", "name": "Crown Zenith (Especial)", "set_ids": ("swsh12pt5", "swsh12pt5gg", "swsh12.5", "swsh12.5gg", "S12a"), "set_names": ("Crown Zenith", "Crown Zenith Galarian Gallery")},
        ],
    ),
    (
        "4. Serie Sol y Luna (2017 – 2019)",
        "4. Sun & Moon Series (2017 – 2019)",
        [
            {"key": "sm1", "name": "Sun & Moon", "set_ids": ("sm1",), "set_names": ("Sun & Moon",)},
            {"key": "sm2", "name": "Guardians Rising", "set_ids": ("sm2",), "set_names": ("Guardians Rising",)},
            {"key": "sm3", "name": "Burning Shadows", "set_ids": ("sm3",), "set_names": ("Burning Shadows",)},
            {"key": "sm35", "name": "Shining Legends (Especial)", "set_ids": ("sm35", "sm3.5"), "set_names": ("Shining Legends",)},
            {"key": "sm4", "name": "Crimson Invasion", "set_ids": ("sm4",), "set_names": ("Crimson Invasion",)},
            {"key": "sm5", "name": "Ultra Prism", "set_ids": ("sm5",), "set_names": ("Ultra Prism",)},
            {"key": "sm6", "name": "Forbidden Light", "set_ids": ("sm6",), "set_names": ("Forbidden Light",)},
            {"key": "sm7", "name": "Celestial Storm", "set_ids": ("sm7",), "set_names": ("Celestial Storm",)},
            {"key": "sm75", "name": "Dragon Majesty (Especial)", "set_ids": ("sm75", "sm7.5"), "set_names": ("Dragon Majesty",)},
            {"key": "sm8", "name": "Lost Thunder", "set_ids": ("sm8",), "set_names": ("Lost Thunder",)},
            {"key": "sm9", "name": "Team Up", "set_ids": ("sm9",), "set_names": ("Team Up",)},
            {"key": "det1", "name": "Detective Pikachu (Especial)", "set_ids": ("det1",), "set_names": ("Detective Pikachu",)},
            {"key": "sm10", "name": "Unbroken Bonds", "set_ids": ("sm10", "SM10"), "set_names": ("Unbroken Bonds",)},
            {"key": "sm11", "name": "Unified Minds", "set_ids": ("sm11",), "set_names": ("Unified Minds",)},
            {"key": "sm115", "name": "Hidden Fates (Especial)", "set_ids": ("sm115", "sma"), "set_names": ("Hidden Fates", "Hidden Fates Shiny Vault")},
            {"key": "sm12", "name": "Cosmic Eclipse", "set_ids": ("sm12", "SM11b", "SM12", "SM12a"), "set_names": ("Cosmic Eclipse",)},
        ],
    ),
    (
        "5. Serie XY (2013 – 2016)",
        "5. XY Series (2013 – 2016)",
        [
            {"key": "xy0", "name": "Kalos Starter Set", "set_ids": ("xy0",), "set_names": ("Kalos Starter Set",)},
            {"key": "xy1", "name": "XY", "set_ids": ("xy1",), "set_names": ("XY",)},
            {"key": "xy2", "name": "Flashfire", "set_ids": ("xy2",), "set_names": ("Flashfire",)},
            {"key": "xy3", "name": "Furious Fists", "set_ids": ("xy3",), "set_names": ("Furious Fists",)},
            {"key": "xy4", "name": "Phantom Forces", "set_ids": ("xy4",), "set_names": ("Phantom Forces",)},
            {"key": "xy5", "name": "Primal Clash", "set_ids": ("xy5",), "set_names": ("Primal Clash",)},
            {"key": "dc1", "name": "Double Crisis (Especial)", "set_ids": ("dc1", "CP1"), "set_names": ("Double Crisis",)},
            {"key": "xy6", "name": "Roaring Skies", "set_ids": ("xy6",), "set_names": ("Roaring Skies",)},
            {"key": "xy7", "name": "Ancient Origins", "set_ids": ("xy7",), "set_names": ("Ancient Origins",)},
            {"key": "xy8", "name": "BREAKthrough", "set_ids": ("xy8",), "set_names": ("BREAKthrough",)},
            {"key": "xy9", "name": "BREAKpoint", "set_ids": ("xy9",), "set_names": ("BREAKpoint",)},
            {"key": "g1", "name": "Generations (Especial 20.º Aniversario)", "set_ids": ("g1",), "set_names": ("Generations",)},
            {"key": "xy10", "name": "Fates Collide", "set_ids": ("xy10",), "set_names": ("Fates Collide",)},
            {"key": "xy11", "name": "Steam Siege", "set_ids": ("xy11",), "set_names": ("Steam Siege",)},
            {"key": "xy12", "name": "Evolutions", "set_ids": ("xy12",), "set_names": ("Evolutions",)},
        ],
    ),
    (
        "6. Serie Negro y Blanco (2011 – 2013)",
        "6. Black & White Series (2011 – 2013)",
        [
            {"key": "bw1", "name": "Black & White", "set_ids": ("bw1",), "set_names": ("Black & White",)},
            {"key": "bw2", "name": "Emerging Powers", "set_ids": ("bw2",), "set_names": ("Emerging Powers",)},
            {"key": "bw3", "name": "Noble Victories", "set_ids": ("bw3",), "set_names": ("Noble Victories",)},
            {"key": "bw4", "name": "Next Destinies", "set_ids": ("bw4",), "set_names": ("Next Destinies",)},
            {"key": "bw5", "name": "Dark Explorers", "set_ids": ("bw5",), "set_names": ("Dark Explorers",)},
            {"key": "bw6", "name": "Dragons Exalted", "set_ids": ("bw6",), "set_names": ("Dragons Exalted",)},
            {"key": "dv1", "name": "Dragon Vault (Especial)", "set_ids": ("dv1",), "set_names": ("Dragon Vault",)},
            {"key": "bw7", "name": "Boundaries Crossed", "set_ids": ("bw7",), "set_names": ("Boundaries Crossed",)},
            {"key": "bw8", "name": "Plasma Storm", "set_ids": ("bw8",), "set_names": ("Plasma Storm",)},
            {"key": "bw9", "name": "Plasma Freeze", "set_ids": ("bw9",), "set_names": ("Plasma Freeze",)},
            {"key": "bw10", "name": "Plasma Blast", "set_ids": ("bw10",), "set_names": ("Plasma Blast",)},
            {"key": "bw11", "name": "Legendary Treasures", "set_ids": ("bw11",), "set_names": ("Legendary Treasures",)},
        ],
    ),
    (
        "7. Era HeartGold & SoulSilver y Call of Legends (2010 – 2011)",
        "7. HeartGold & SoulSilver & Call of Legends (2010 – 2011)",
        [
            {"key": "hgss1", "name": "HeartGold & SoulSilver", "set_ids": ("hgss1",), "set_names": ("HeartGold & SoulSilver",)},
            {"key": "hgss2", "name": "Unleashed", "set_ids": ("hgss2",), "set_names": ("HS—Unleashed", "Unleashed")},
            {"key": "hgss3", "name": "Undaunted", "set_ids": ("hgss3",), "set_names": ("HS—Undaunted", "Undaunted")},
            {"key": "hgss4", "name": "Triumphant", "set_ids": ("hgss4",), "set_names": ("HS—Triumphant", "Triumphant")},
            {"key": "col1", "name": "Call of Legends", "set_ids": ("col1",), "set_names": ("Call of Legends",)},
        ],
    ),
    (
        "8. Serie Platino (2009)",
        "8. Platinum Series (2009)",
        [
            {"key": "pl1", "name": "Platinum", "set_ids": ("pl1",), "set_names": ("Platinum",)},
            {"key": "pl2", "name": "Rising Rivals", "set_ids": ("pl2",), "set_names": ("Rising Rivals",)},
            {"key": "pl3", "name": "Supreme Victors", "set_ids": ("pl3",), "set_names": ("Supreme Victors",)},
            {"key": "pl4", "name": "Arceus", "set_ids": ("pl4",), "set_names": ("Arceus",)},
        ],
    ),
    (
        "9. Serie Diamante y Perla (2007 – 2008)",
        "9. Diamond & Pearl Series (2007 – 2008)",
        [
            {"key": "dp1", "name": "Diamond & Pearl", "set_ids": ("dp1",), "set_names": ("Diamond & Pearl",)},
            {"key": "dp2", "name": "Mysterious Treasures", "set_ids": ("dp2",), "set_names": ("Mysterious Treasures",)},
            {"key": "dp3", "name": "Secret Wonders", "set_ids": ("dp3",), "set_names": ("Secret Wonders",)},
            {"key": "dp4", "name": "Great Encounters", "set_ids": ("dp4",), "set_names": ("Great Encounters",)},
            {"key": "dp5", "name": "Majestic Dawn", "set_ids": ("dp5",), "set_names": ("Majestic Dawn",)},
            {"key": "dp6", "name": "Legends Awakened", "set_ids": ("dp6",), "set_names": ("Legends Awakened",)},
            {"key": "dp7", "name": "Stormfront", "set_ids": ("dp7",), "set_names": ("Stormfront",)},
        ],
    ),
    (
        "10. Serie EX (2003 – 2007)",
        "10. EX Series (2003 – 2007)",
        [
            {"key": "ex1", "name": "Ruby & Sapphire", "set_ids": ("ex1",), "set_names": ("Ruby & Sapphire",)},
            {"key": "ex2", "name": "Sandstorm", "set_ids": ("ex2",), "set_names": ("Sandstorm",)},
            {"key": "ex3", "name": "Dragon", "set_ids": ("ex3",), "set_names": ("Dragon",)},
            {"key": "ex4", "name": "Team Magma vs Team Aqua", "set_ids": ("ex4",), "set_names": ("Team Magma vs Team Aqua",)},
            {"key": "ex5", "name": "Hidden Legends", "set_ids": ("ex5", "ex5.5"), "set_names": ("Hidden Legends",)},
            {"key": "ex6", "name": "FireRed & LeafGreen", "set_ids": ("ex6", "PCG1"), "set_names": ("FireRed & LeafGreen",)},
            {"key": "ex7", "name": "Team Rocket Returns", "set_ids": ("ex7", "PCG2"), "set_names": ("Team Rocket Returns",)},
            {"key": "ex8", "name": "Deoxys", "set_ids": ("ex8", "PCG3"), "set_names": ("Deoxys",)},
            {"key": "ex9", "name": "Emerald", "set_ids": ("ex9",), "set_names": ("Emerald",)},
            {"key": "ex10", "name": "Unseen Forces", "set_ids": ("ex10", "exu", "PCG4"), "set_names": ("Unseen Forces",)},
            {"key": "ex11", "name": "Delta Species", "set_ids": ("ex11", "PCG5"), "set_names": ("Delta Species",)},
            {"key": "ex12", "name": "Legend Maker", "set_ids": ("ex12", "PCG6"), "set_names": ("Legend Maker",)},
            {"key": "ex13", "name": "Holon Phantoms", "set_ids": ("ex13", "PCG7"), "set_names": ("Holon Phantoms",)},
            {"key": "ex14", "name": "Crystal Guardians", "set_ids": ("ex14", "PCG8"), "set_names": ("Crystal Guardians",)},
            {"key": "ex15", "name": "Dragon Frontiers", "set_ids": ("ex15", "PCG9"), "set_names": ("Dragon Frontiers",)},
            {"key": "ex16", "name": "Power Keepers", "set_ids": ("ex16",), "set_names": ("Power Keepers",)},
        ],
    ),
    (
        "11. Era Wizards of the Coast (1999 – 2003)",
        "11. Wizards of the Coast Era (1999 – 2003)",
        [
            {"key": "base1", "name": "Base Set", "set_ids": ("base1", "PMCG1"), "set_names": ("Base", "Base Set")},
            {"key": "base2", "name": "Jungle", "set_ids": ("base2", "PMCG2"), "set_names": ("Jungle",)},
            {"key": "base3", "name": "Fossil", "set_ids": ("base3", "PMCG3"), "set_names": ("Fossil",)},
            {"key": "base4", "name": "Base Set 2", "set_ids": ("base4",), "set_names": ("Base Set 2",)},
            {"key": "base5", "name": "Team Rocket", "set_ids": ("base5", "PMCG4"), "set_names": ("Team Rocket",)},
            {"key": "gym1", "name": "Gym Heroes", "set_ids": ("gym1", "PMCG5"), "set_names": ("Gym Heroes",)},
            {"key": "gym2", "name": "Gym Challenge", "set_ids": ("gym2", "PMCG6"), "set_names": ("Gym Challenge",)},
            {"key": "neo1", "name": "Neo Genesis", "set_ids": ("neo1",), "set_names": ("Neo Genesis",)},
            {"key": "neo2", "name": "Neo Discovery", "set_ids": ("neo2",), "set_names": ("Neo Discovery",)},
            {"key": "neo3", "name": "Neo Revelation", "set_ids": ("neo3",), "set_names": ("Neo Revelation",)},
            {"key": "neo4", "name": "Neo Destiny", "set_ids": ("neo4",), "set_names": ("Neo Destiny",)},
            {"key": "base6", "name": "Legendary Collection", "set_ids": ("base6", "lc"), "set_names": ("Legendary Collection",)},
            {"key": "ecard1", "name": "Expedition Base Set", "set_ids": ("ecard1", "E1"), "set_names": ("Expedition Base Set",)},
            {"key": "ecard2", "name": "Aquapolis", "set_ids": ("ecard2", "E2", "E3"), "set_names": ("Aquapolis",)},
            {"key": "ecard3", "name": "Skyridge", "set_ids": ("ecard3", "E4", "E5"), "set_names": ("Skyridge",)},
        ],
    ),
]

EXPANSION_BY_KEY = {
    exp["key"]: exp
    for _label_es, _label_en, exps in EXPANSION_SERIES
    for exp in exps
}

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


def apply_expansion_filter(query, expansion_key: str):
    """Filtra una consulta SQLAlchemy por expansión oficial, cubriendo set_id multilingües y set_name."""
    if not expansion_key:
        return query
    exp = EXPANSION_BY_KEY.get(expansion_key)
    if not exp:
        return query.filter(Cartas.set_id == expansion_key)

    conds = []
    set_ids = exp.get("set_ids") or ()
    set_names = exp.get("set_names") or ()
    if set_ids:
        conds.append(Cartas.set_id.in_(set_ids))
    if set_names:
        conds.append(Cartas.set_name.in_(set_names))
    if not conds:
        return query
    return query.filter(conds[0] if len(conds) == 1 else or_(*conds))


def populate_expansion_combo(combo, all_label: str, lang: str | None = None, selected_key: str | None = None):
    """Puebla un QComboBox de expansiones agrupado por Serie (con encabezados no seleccionables)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QFont, QStandardItem
    from PyQt6.QtWidgets import QComboBox

    use_en = _is_english_language(lang)
    combo.blockSignals(True)
    try:
        combo.clear()
        combo.addItem(all_label, None)

        model = combo.model()
        bold_font = QFont()
        bold_font.setBold(True)
        header_fg = QColor("#e11d48")

        for series_es, series_en, expansions in EXPANSION_SERIES:
            header_item = QStandardItem(series_en if use_en else series_es)
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)
            header_item.setData(None, Qt.ItemDataRole.UserRole)
            header_item.setFont(bold_font)
            header_item.setForeground(header_fg)
            model.appendRow(header_item)

            for exp in expansions:
                combo.addItem(f"  {exp['name']}", exp["key"])

        combo.setMaxVisibleItems(18)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        view = combo.view()
        if view is not None:
            view.setMinimumWidth(340)

        if selected_key:
            idx = combo.findData(selected_key)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            combo.setCurrentIndex(0)
    finally:
        combo.blockSignals(False)


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

