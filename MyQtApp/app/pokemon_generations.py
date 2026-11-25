"""Mapeo offline preciso de especies Pokémon (1-1025) a su Generación/Región de debut."""

from __future__ import annotations
import os
import re
import sqlite3
import unicodedata

GENERATIONS_ORDER = [
    "Kanto", "Johto", "Hoenn", "Sinnoh", "Teselia",
    "Kalos", "Alola", "Galar", "Paldea",
]

_BY_GEN = {
    "Kanto": [
        "bulbasaur", "ivysaur", "venusaur", "charmander", "charmeleon", "charizard",
        "squirtle", "wartortle", "blastoise", "caterpie", "metapod", "butterfree",
        "weedle", "kakuna", "beedrill", "pidgey", "pidgeotto", "pidgeot", "rattata",
        "raticate", "spearow", "fearow", "ekans", "arbok", "pikachu", "raichu",
        "sandshrew", "sandslash", "nidoran-f", "nidorina", "nidoqueen", "nidoran-m",
        "nidorino", "nidoking", "clefairy", "clefable", "vulpix", "ninetales",
        "jigglypuff", "wigglytuff", "zubat", "golbat", "oddish", "gloom", "vileplume",
        "paras", "parasect", "venonat", "venomoth", "diglett", "dugtrio", "meowth",
        "persian", "psyduck", "golduck", "mankey", "primeape", "growlithe", "arcanine",
        "poliwag", "poliwhirl", "poliwrath", "abra", "kadabra", "alakazam", "machop",
        "machoke", "machamp", "bellsprout", "weepinbell", "victreebel", "tentacool",
        "tentacruel", "geodude", "graveler", "golem", "ponyta", "rapidash", "slowpoke",
        "slowbro", "magnemite", "magneton", "farfetchd", "doduo", "dodrio", "seel",
        "dewgong", "grimer", "muk", "shellder", "cloyster", "gastly", "haunter",
        "gengar", "onix", "drowzee", "hypno", "krabby", "kingler", "voltorb",
        "electrode", "exeggcute", "exeggutor", "cubone", "marowak", "hitmonlee",
        "hitmonchan", "lickitung", "koffing", "weezing", "rhyhorn", "rhydon", "chansey",
        "tangela", "kangaskhan", "horsea", "seadra", "goldeen", "seaking", "staryu",
        "starmie", "mr-mime", "scyther", "jynx", "electabuzz", "magmar", "pinsir",
        "tauros", "magikarp", "gyarados", "lapras", "ditto", "eevee", "vaporeon",
        "jolteon", "flareon", "porygon", "omanyte", "omastar", "kabuto", "kabutops",
        "aerodactyl", "snorlax", "articuno", "zapdos", "moltres", "dratini",
        "dragonair", "dragonite", "mewtwo", "mew",
    ],
    "Johto": [
        "chikorita", "bayleef", "meganium", "cyndaquil", "quilava", "typhlosion",
        "totodile", "croconaw", "feraligatr", "sentret", "furret", "hoothoot",
        "noctowl", "ledyba", "ledian", "spinarak", "ariados", "crobat", "chinchou",
        "lanturn", "pichu", "cleffa", "igglybuff", "togepi", "togetic", "natu",
        "xatu", "mareep", "flaaffy", "ampharos", "bellossom", "marill", "azumarill",
        "sudowoodo", "politoed", "hoppip", "skiploom", "jumpluff", "aipom", "sunkern",
        "sunflora", "yanma", "wooper", "quagsire", "espeon", "umbreon", "murkrow",
        "slowking", "misdreavus", "unown", "wobbuffet", "girafarig", "pineco",
        "forretress", "dunsparce", "gligar", "steelix", "snubbull", "granbull",
        "qwilfish", "scizor", "shuckle", "heracross", "sneasel", "teddiursa",
        "ursaring", "slugma", "magcargo", "swinub", "piloswine", "corsola",
        "remoraid", "octillery", "delibird", "mantine", "skarmory", "houndour",
        "houndoom", "kingdra", "phanpy", "donphan", "porygon2", "stantler",
        "smeargle", "tyrogue", "hitmontop", "smoochum", "elekid", "magby", "miltank",
        "blissey", "raikou", "entei", "suicune", "larvitar", "pupitar", "tyranitar",
        "lugia", "ho-oh", "celebi",
    ],
    "Hoenn": [
        "treecko", "grovyle", "sceptile", "torchic", "combusken", "blaziken",
        "mudkip", "marshtomp", "swampert", "poochyena", "mightyena", "zigzagoon",
        "linoone", "wurmple", "silcoon", "beautifly", "cascoon", "dustox", "lotad",
        "lombre", "ludicolo", "seedot", "nuzleaf", "shiftry", "taillow", "swellow",
        "wingull", "pelipper", "ralts", "kirlia", "gardevoir", "surskit", "masquerain",
        "shroomish", "breloom", "slakoth", "vigoroth", "slaking", "nincada", "ninjask",
        "shedinja", "whismur", "loudred", "exploud", "makuhita", "hariyama", "azurill",
        "nosepass", "skitty", "delcatty", "sableye", "mawile", "aron", "lairon",
        "aggron", "meditite", "medicham", "electrike", "manectric", "plusle", "minun",
        "volbeat", "illumise", "roselia", "gulpin", "swalot", "carvanha", "sharpedo",
        "wailmer", "wailord", "numel", "camerupt", "torkoal", "spoink", "grumpig",
        "spinda", "trapinch", "vibrava", "flygon", "cacnea", "cacturne", "swablu",
        "altaria", "zangoose", "seviper", "lunatone", "solrock", "barboach", "whiscash",
        "corphish", "crawdaunt", "baltoy", "claydol", "lileep", "cradily", "anorith",
        "armaldo", "feebas", "milotic", "castform", "kecleon", "shuppet", "banette",
        "duskull", "dusclops", "tropius", "chimecho", "absol", "wynaut", "snorunt",
        "glalie", "spheal", "sealeo", "walrein", "clamperl", "huntail", "gorebyss",
        "relicanth", "luvdisc", "bagon", "shelgon", "salamence", "beldum", "metang",
        "metagross", "regirock", "regice", "registeel", "latias", "latios", "kyogre",
        "groudon", "rayquaza", "jirachi", "deoxys",
    ],
    "Sinnoh": [
        "turtwig", "grotle", "torterra", "chimchar", "monferno", "infernape", "piplup",
        "prinplup", "empoleon", "starly", "staravia", "staraptor", "bidoof", "bibarel",
        "kricketot", "kricketune", "shinx", "luxio", "luxray", "budew", "roserade",
        "cranidos", "rampardos", "shieldon", "bastiodon", "burmy", "wormadam", "mothim",
        "combee", "vespiquen", "pachirisu", "buizel", "floatzel", "cherubi", "cherrim",
        "shellos", "gastrodon", "ambipom", "drifloon", "drifblim", "buneary", "lopunny",
        "mismagius", "honchkrow", "glameow", "purugly", "chingling", "stunky",
        "skuntank", "bronzor", "bronzong", "bonsly", "mime-jr", "happiny", "chatot",
        "spiritomb", "gible", "gabite", "garchomp", "munchlax", "riolu", "lucario",
        "hippopotas", "hippowdon", "skorupi", "drapion", "croagunk", "toxicroak",
        "carnivine", "finneon", "lumineon", "mantyke", "snover", "abomasnow",
        "weavile", "magnezone", "lickilicky", "rhyperior", "tangrowth", "electivire",
        "magmortar", "togekiss", "yanmega", "leafeon", "glaceon", "gliscor",
        "mamoswine", "porygon-z", "gallade", "probopass", "dusknoir", "froslass",
        "rotom", "uxie", "mesprit", "azelf", "dialga", "palkia", "heatran",
        "regigigas", "giratina", "cresselia", "phione", "manaphy", "darkrai",
        "shaymin", "arceus",
    ],
    "Teselia": [
        "victini", "snivy", "servine", "serperior", "tepig", "pignite", "emboar",
        "oshawott", "dewott", "samurott", "patrat", "watchog", "lillipup", "herdier",
        "stoutland", "purrloin", "liepard", "pansage", "simisage", "pansear",
        "simisear", "panpour", "simipour", "munna", "musharna", "pidove", "tranquill",
        "unfezant", "blitzle", "zebstrika", "roggenrola", "boldore", "gigalith",
        "woobat", "swoobat", "drilbur", "excadrill", "audino", "timburr", "gurdurr",
        "conkeldurr", "tympole", "palpitoad", "seismitoad", "throh", "sawk",
        "sewaddle", "swadloon", "leavanny", "venipede", "whirlipede", "scolipede",
        "cottonee", "whimsicott", "petilil", "lilligant", "basculin", "sandile",
        "krokorok", "krookodile", "darumaka", "darmanitan", "maractus", "dwebble",
        "crustle", "scraggy", "scrafty", "sigilyph", "yamask", "cofagrigus",
        "tirtouga", "carracosta", "archen", "archeops", "trubbish", "garbodor",
        "zorua", "zoroark", "minccino", "cinccino", "gothita", "gothorita",
        "gothitelle", "solosis", "duosion", "reuniclus", "ducklett", "swanna",
        "vanillite", "vanillish", "vanilluxe", "deerling", "sawsbuck", "emolga",
        "karrablast", "escavalier", "foongus", "amoonguss", "frillish", "jellicent",
        "alomomola", "joltik", "galvantula", "ferroseed", "ferrothorn", "klink",
        "klang", "klinklang", "tynamo", "eelektrik", "eelektross", "elgyem",
        "beheeyem", "litwick", "lampent", "chandelure", "axew", "fraxure", "haxorus",
        "cubchoo", "beartic", "cryogonal", "shelmet", "accelgor", "stunfisk",
        "mienfoo", "mienshao", "druddigon", "golett", "golurk", "pawniard", "bisharp",
        "bouffalant", "rufflet", "braviary", "vullaby", "mandibuzz", "heatmor",
        "durant", "deino", "zweilous", "hydreigon", "larvesta", "volcarona",
        "cobalion", "terrakion", "virizion", "tornadus", "thundurus", "reshiram",
        "zekrom", "landorus", "kyurem", "keldeo", "meloetta", "genesect",
    ],
    "Kalos": [
        "chespin", "quilladin", "chesnaught", "fennekin", "braixen", "delphox",
        "froakie", "frogadier", "greninja", "bunnelby", "diggersby", "fletchling",
        "fletchinder", "talonflame", "scatterbug", "spewpa", "vivillon", "litleo",
        "pyroar", "flabebe", "floette", "florges", "skiddo", "gogoat", "pancham",
        "pangoro", "furfrou", "espurr", "meowstic", "honedge", "doublade", "aegislash",
        "spritzee", "aromatisse", "swirlix", "slurpuff", "inkay", "malamar", "binacle",
        "barbaracle", "skrelp", "dragalge", "clauncher", "clawitzer", "helioptile",
        "heliolisk", "tyrunt", "tyrantrum", "amaura", "aurorus", "sylveon", "hawlucha",
        "dedenne", "carbink", "goomy", "sliggoo", "goodra", "klefki", "phantump",
        "trevenant", "pumpkaboo", "gourgeist", "bergmite", "avalugg", "noibat",
        "noivern", "xerneas", "yveltal", "zygarde", "diancie", "hoopa", "volcanion",
    ],
    "Alola": [
        "rowlet", "dartrix", "decidueye", "litten", "torracat", "incineroar",
        "popplio", "brionne", "primarina", "pikipek", "trumbeak", "toucannon",
        "yungoos", "gumshoos", "grubbin", "charjabug", "vikavolt", "crabrawler",
        "crabominable", "oricorio", "cutiefly", "ribombee", "rockruff", "lycanroc",
        "wishiwashi", "mareanie", "toxapex", "mudbray", "mudsdale", "dewpider",
        "araquanid", "fomantis", "lurantis", "morelull", "shiinotic", "salandit",
        "salazzle", "stufful", "bewear", "bounsweet", "steenee", "tsareena", "comfey",
        "oranguru", "passimian", "wimpod", "golisopod", "sandygast", "palossand",
        "pyukumuku", "type-null", "silvally", "minior", "komala", "turtonator",
        "togedemaru", "mimikyu", "bruxish", "drampa", "dhelmise", "jangmo-o",
        "hakamo-o", "kommo-o", "tapu-koko", "tapu-lele", "tapu-bulu", "tapu-fini",
        "cosmog", "cosmoem", "solgaleo", "lunala", "nihilego", "buzzwole",
        "pheromosa", "xurkitree", "celesteela", "kartana", "guzzlord", "necrozma",
        "magearna", "marshadow", "poipole", "naganadel", "stakataka", "blacephalon",
        "zeraora", "meltan", "melmetal",
    ],
    "Galar": [
        "grookey", "thwackey", "rillaboom", "scorbunny", "raboot", "cinderace",
        "sobble", "drizzile", "inteleon", "skwovet", "greedent", "rookidee",
        "corvisquire", "corviknight", "blipbug", "dottler", "orbeetle", "nickit",
        "thievul", "gossifleur", "eldegoss", "wooloo", "dubwool", "chewtle", "drednaw",
        "yamper", "boltund", "rolycoly", "carkol", "coalossal", "applin", "flapple",
        "appletun", "silicobra", "sandaconda", "cramorant", "arrokuda", "barraskewda",
        "toxel", "toxtricity", "sizzlipede", "centiskorch", "clobbopus", "grapploct",
        "sinistea", "polteageist", "hatenna", "hattrem", "hatterene", "impidimp",
        "morgrem", "grimmsnarl", "obstagoon", "perrserker", "cursola", "sirfetchd",
        "mr-rime", "runerigus", "milcery", "alcremie", "falinks", "pincurchin", "snom",
        "frosmoth", "stonjourner", "eiscue", "indeedee", "morpeko", "cufant",
        "copperajah", "dracozolt", "arctozolt", "dracovish", "arctovish", "duraludon",
        "dreepy", "drakloak", "dragapult", "zacian", "zamazenta", "eternatus", "kubfu",
        "urshifu", "zarude", "regieleki", "regidrago", "glastrier", "spectrier",
        "calyrex", "wyrdeer", "kleavor", "ursaluna", "basculegion", "sneasler",
        "overqwil", "enamorus",
    ],
    "Paldea": [
        "sprigatito", "floragato", "meowscarada", "fuecoco", "crocalor", "skeledirge",
        "quaxly", "quaxwell", "quaquaval", "lechonk", "oinkologne", "tarountula",
        "spidops", "nymble", "lokix", "pawmi", "pawmo", "pawmot", "tandemaus",
        "maushold", "fidough", "dachsbun", "smoliv", "dolliv", "arboliva",
        "squawkabilly", "nacli", "naclstack", "garganacl", "charcadet", "armarouge",
        "ceruledge", "tadbulb", "bellibolt", "wattrel", "kilowattrel", "maschiff",
        "mabosstiff", "shroodle", "grafaiai", "bramblin", "brambleghast",
        "toedscool", "toedscruel", "klawf", "capsakid", "scovillain", "rellor",
        "rabsca", "flittle", "espathra", "tinkatink", "tinkatuff", "tinkaton",
        "wiglett", "wugtrio", "bombirdier", "finizen", "palafin", "varoom",
        "revavroom", "cyclizar", "orthworm", "glimmet", "glimmora", "greavard",
        "houndstone", "flamigo", "cetoddle", "cetitan", "veluza", "dondozo",
        "tatsugiri", "annihilape", "clodsire", "farigiraf", "dudunsparce", "kingambit",
        "great-tusk", "scream-tail", "brute-bonnet", "flutter-mane", "slither-wing",
        "sandy-shocks", "iron-treads", "iron-bundle", "iron-hands", "iron-jugulis",
        "iron-moth", "iron-thorns", "frigibax", "arctibax", "baxcalibur", "gimmighoul",
        "gholdengo", "wo-chien", "chien-pao", "ting-lu", "chi-yu", "roaring-moon",
        "iron-valiant", "koraidon", "miraidon", "walking-wake", "iron-leaves",
        "dipplin", "poltchageist", "sinistcha", "okidogi", "munkidori", "fezandipiti",
        "ogerpon", "archaludon", "hydrapple", "gouging-fire", "raging-bolt",
        "iron-boulder", "iron-crown", "terapagos", "pecharunt",
    ],
}


def _norm_key(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = s.replace("♀", "f").replace("♂", "m")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


POKEMON_GENERATION_MAP: dict[str, str] = {}
POKEMON_DEX_ID_MAP: dict[str, int] = {}
_dex_counter = 0
for _gen in GENERATIONS_ORDER:
    for _raw in _BY_GEN[_gen]:
        _dex_counter += 1
        _k1 = _norm_key(_raw)
        _k2 = _k1.replace(" ", "")
        POKEMON_GENERATION_MAP[_k1] = _gen
        POKEMON_GENERATION_MAP[_k2] = _gen
        POKEMON_DEX_ID_MAP[_k1] = _dex_counter
        POKEMON_DEX_ID_MAP[_k2] = _dex_counter

# Aliases y nombres especiales (inglés / español / formas TCG): (generacion, pokedex_id)
_ALIASES = {
    "nidoran": ("Kanto", 29),
    "nidoran f": ("Kanto", 29),
    "nidoran m": ("Kanto", 32),
    "mr mime": ("Kanto", 122),
    "farfetch d": ("Kanto", 83),
    "farfetchd": ("Kanto", 83),
    "ho oh": ("Johto", 250),
    "porygon2": ("Johto", 233),
    "mime jr": ("Sinnoh", 439),
    "porygon z": ("Sinnoh", 474),
    "flabebe": ("Kalos", 669),
    "type null": ("Alola", 772),
    "codigo cero": ("Alola", 772),
    "jangmo o": ("Alola", 782),
    "hakamo o": ("Alola", 783),
    "kommo o": ("Alola", 784),
    "tapu koko": ("Alola", 785),
    "tapu lele": ("Alola", 786),
    "tapu bulu": ("Alola", 787),
    "tapu fini": ("Alola", 788),
    "sirfetch d": ("Galar", 865),
    "sirfetchd": ("Galar", 865),
    "mr rime": ("Galar", 866),
    "great tusk": ("Paldea", 984),
    "colmilargo": ("Paldea", 984),
    "scream tail": ("Paldea", 985),
    "colagrito": ("Paldea", 985),
    "brute bonnet": ("Paldea", 986),
    "furioseta": ("Paldea", 986),
    "flutter mane": ("Paldea", 987),
    "melenaleteo": ("Paldea", 987),
    "slither wing": ("Paldea", 988),
    "reptalada": ("Paldea", 988),
    "sandy shocks": ("Paldea", 989),
    "pelarena": ("Paldea", 989),
    "iron treads": ("Paldea", 990),
    "ferrodada": ("Paldea", 990),
    "iron bundle": ("Paldea", 991),
    "ferrosaco": ("Paldea", 991),
    "iron hands": ("Paldea", 992),
    "ferropalmas": ("Paldea", 992),
    "iron jugulis": ("Paldea", 993),
    "ferrocuello": ("Paldea", 993),
    "iron moth": ("Paldea", 994),
    "ferropolilla": ("Paldea", 994),
    "iron thorns": ("Paldea", 995),
    "ferropuas": ("Paldea", 995),
    "roaring moon": ("Paldea", 1005),
    "bramaluna": ("Paldea", 1005),
    "iron valiant": ("Paldea", 1006),
    "ferropaladin": ("Paldea", 1006),
    "walking wake": ("Paldea", 1009),
    "ondulagua": ("Paldea", 1009),
    "iron leaves": ("Paldea", 1010),
    "ferroverdor": ("Paldea", 1010),
    "gouging fire": ("Paldea", 1020),
    "flamariete": ("Paldea", 1020),
    "raging bolt": ("Paldea", 1021),
    "electrofuria": ("Paldea", 1021),
    "iron boulder": ("Paldea", 1022),
    "ferromole": ("Paldea", 1022),
    "iron crown": ("Paldea", 1023),
    "ferrotesta": ("Paldea", 1023),
    "wo chien": ("Paldea", 1001),
    "chien pao": ("Paldea", 1002),
    "ting lu": ("Paldea", 1003),
    "chi yu": ("Paldea", 1004),
    "oinkologne": ("Paldea", 916),
    "maushold": ("Paldea", 925),
    "melmetal": ("Alola", 809),
    "meltan": ("Alola", 808),
    "bulbizarre": ("Kanto", 1),
    "herbizarre": ("Kanto", 2),
    "florizarre": ("Kanto", 3),
    "salameche": ("Kanto", 4),
    "reptincel": ("Kanto", 5),
    "dracaufeu": ("Kanto", 6),
    "carapuce": ("Kanto", 7),
    "carabaffe": ("Kanto", 8),
    "tortank": ("Kanto", 9),
    "melodelfe": ("Kanto", 36),
    "ptera": ("Kanto", 142),
    "ronflex": ("Kanto", 143),
    "evoli": ("Kanto", 133),
    "zarbi": ("Johto", 201),
    "statitik": ("Teselia", 595),
    "pomdepik": ("Johto", 204),
}
for _ak, (_ag, _adex) in _ALIASES.items():
    _nk = _norm_key(_ak)
    POKEMON_GENERATION_MAP[_nk] = _ag
    POKEMON_GENERATION_MAP[_nk.replace(" ", "")] = _ag
    POKEMON_DEX_ID_MAP[_nk] = _adex
    POKEMON_DEX_ID_MAP[_nk.replace(" ", "")] = _adex

# Ordenar claves por longitud de palabras descendente para hacer match de nombres compuestos primero
_SORTED_KEYS = sorted(
    [k for k in POKEMON_GENERATION_MAP.keys() if " " in k or len(k) >= 3],
    key=lambda x: (-len(x.split()), -len(x)),
)
_SINGLE_WORD_SET = {k: v for k, v in POKEMON_GENERATION_MAP.items() if " " not in k}

_NON_POKEMON_STAGES = {
    "item", "supporter", "stadium", "technical machine",
    "pokémon tool", "pokemon tool", "pokémon tool f", "pokemon tool f",
    "rocket's secret machine", "goldenrod game corner",
}

_STRIP_SUFFIX_RE = re.compile(
    r"(?:\b(?:ex|gx|v|vmax|vstar|lv\s*x|break|prime|legend|prism star|radiant|shining|tag team)\b|\s*-\s*(?:ex|gx))$",
    re.IGNORECASE,
)


def _match_segment_key(segment: str) -> str | None:
    norm = _norm_key(segment)
    if not norm:
        return None
    if norm in POKEMON_GENERATION_MAP:
        return norm

    cleaned = norm
    for _ in range(3):
        next_cleaned = _STRIP_SUFFIX_RE.sub("", cleaned).strip()
        if next_cleaned == cleaned:
            break
        cleaned = next_cleaned
        if cleaned in POKEMON_GENERATION_MAP:
            return cleaned

    padded = f" {cleaned} "
    for k in _SORTED_KEYS:
        if f" {k} " in padded:
            return k

    tokens = cleaned.split()
    for tok in reversed(tokens):
        if tok in _SINGLE_WORD_SET:
            return tok
    return None


def _match_segment(segment: str) -> str | None:
    k = _match_segment_key(segment)
    return POKEMON_GENERATION_MAP[k] if k else None


def detect_card_info(
    card_name: str,
    stage: str | None = None,
    card_type: str | None = None,
) -> tuple[str | None, int | None]:
    """
    Detecta simultáneamente (generaciones_csv, pokedex_id) de una carta Pokémon.
    Para Tag Team devuelve todas las generaciones encontradas y el menor pokedex_id.
    """
    if not card_name:
        return None, None
    if stage and str(stage).strip().lower() in _NON_POKEMON_STAGES:
        return None, None
    low_name = card_name.strip().lower()
    if low_name.startswith(("energía ", "energy ", "basic ", "special energy")):
        if "energy" in low_name or "energía" in low_name or "énergie" in low_name:
            return None, None

    parts = re.split(r"\s*&\s*|\s+(?:and|y|e)\s+", card_name, flags=re.IGNORECASE)
    found_gens: list[str] = []
    found_dex: list[int] = []
    for part in parts:
        key = _match_segment_key(part)
        if key:
            gen = POKEMON_GENERATION_MAP.get(key)
            if gen and gen not in found_gens:
                found_gens.append(gen)
            dex = POKEMON_DEX_ID_MAP.get(key)
            if dex is not None:
                found_dex.append(dex)

    gen_str = ",".join(found_gens) if found_gens else None
    dex_id = min(found_dex) if found_dex else None
    return gen_str, dex_id


def detect_card_generations(
    card_name: str,
    stage: str | None = None,
    card_type: str | None = None,
) -> str | None:
    """
    Detecta la(s) generación(es) Pokémon de una carta a partir de su nombre.
    Retorna cadena separada por comas (ej. 'Kanto' o 'Johto,Kanto' en Tag Team), o None si no aplica.
    """
    gen_str, _ = detect_card_info(card_name, stage=stage, card_type=card_type)
    return gen_str


def detect_card_pokedex_id(
    card_name: str,
    stage: str | None = None,
    card_type: str | None = None,
) -> int | None:
    _, dex_id = detect_card_info(card_name, stage=stage, card_type=card_type)
    return dex_id


def populate_generations_in_db(db_path: str, force: bool = False) -> tuple[int, int]:
    """
    Asegura las columnas `generacion` y `pokedex_id` en `Cartas` y las puebla offline.
    Propaga ambos valores por `id_api` entre idiomas (ja/zh/fr/pt/es/en).
    Retorna (actualizadas, total_con_generacion).
    """
    if not db_path or not os.path.exists(db_path):
        return 0, 0

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(Cartas)").fetchall()]
        if "generacion" not in cols:
            cur.execute("ALTER TABLE Cartas ADD COLUMN generacion TEXT")
            conn.commit()
        if "pokedex_id" not in cols:
            cur.execute("ALTER TABLE Cartas ADD COLUMN pokedex_id INTEGER")
            conn.commit()

        cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_generacion ON Cartas(generacion)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_pokedex_id ON Cartas(pokedex_id)")

        where_clause = "" if force else "WHERE generacion IS NULL OR pokedex_id IS NULL"
        rows = cur.execute(
            f"SELECT id, id_api, nombre, stage, type FROM Cartas {where_clause}"
        ).fetchall()

        if not rows:
            total = cur.execute(
                "SELECT COUNT(*) FROM Cartas WHERE generacion IS NOT NULL AND generacion != ''"
            ).fetchone()[0]
            return 0, total

        updates: list[tuple[str | None, int | None, int]] = []
        by_id_api: dict[str, tuple[str | None, int | None]] = {}

        if not force:
            for api_id, g, dx in cur.execute(
                "SELECT id_api, generacion, pokedex_id FROM Cartas WHERE generacion IS NOT NULL AND generacion != ''"
            ).fetchall():
                if api_id not in by_id_api:
                    by_id_api[api_id] = (g, dx)

        pending_by_api: list[tuple[int, str]] = []
        for row_id, id_api, nombre, stage, ctype in rows:
            gen, dex = detect_card_info(nombre, stage=stage, card_type=ctype)
            if gen or dex is not None:
                updates.append((gen, dex, row_id))
                if id_api not in by_id_api:
                    by_id_api[id_api] = (gen, dex)
            else:
                pending_by_api.append((row_id, id_api))

        for row_id, id_api in pending_by_api:
            info = by_id_api.get(id_api)
            if info and (info[0] or info[1] is not None):
                updates.append((info[0], info[1], row_id))

        if updates:
            cur.executemany("UPDATE Cartas SET generacion = ?, pokedex_id = ? WHERE id = ?", updates)
            conn.commit()

        total = cur.execute(
            "SELECT COUNT(*) FROM Cartas WHERE generacion IS NOT NULL AND generacion != ''"
        ).fetchone()[0]
        return len(updates), total
    finally:
        conn.close()
