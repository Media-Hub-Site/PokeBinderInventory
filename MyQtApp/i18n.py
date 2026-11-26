from PyQt6.QtCore import QObject, pyqtSignal
from MyQtApp.config import load_settings, save_settings

# Diccionario de traducciones para los 5 idiomas requeridos:
# "Español", "English", "日本語", "Français", "Português"
TRANSLATIONS = {
    # ── Ajustes / Settings ──
    "Ajustes": {
        "Español": "Ajustes",
        "English": "Settings",
        "日本語": "設定",
        "Français": "Paramètres",
        "Português": "Configurações"
    },
    "Audio": {
        "Español": "Audio",
        "English": "Audio",
        "日本語": "オーディオ",
        "Français": "Audio",
        "Português": "Áudio"
    },
    "Música de fondo": {
        "Español": "Música de fondo",
        "English": "Background Music",
        "日本語": "BGM",
        "Français": "Musique de fondo",
        "Português": "Música de fundo"
    },
    "Efectos de sonido": {
        "Español": "Efectos de sonido",
        "English": "Sound Effects",
        "日本語": "効果音",
        "Français": "Effets sonores",
        "Português": "Efeitos sonoros"
    },
    "Pista de música": {
        "Español": "Pista de música",
        "English": "Music Track",
        "日本語": "音楽トラック",
        "Français": "Piste musicale",
        "Português": "Faixa de música"
    },
    "Apariencia": {
        "Español": "Apariencia",
        "English": "Appearance",
        "日本語": "外観",
        "Français": "Apparence",
        "Português": "Aparência"
    },
    "Tema de color": {
        "Español": "Tema de color",
        "English": "Color Theme",
        "日本語": "カラーテーマ",
        "Français": "Thème de couleur",
        "Português": "Tema de cor"
    },
    "Tamaño de cartas": {
        "Español": "Tamaño de cartas",
        "English": "Card Size",
        "日本語": "カードのサイズ",
        "Français": "Taille des cartes",
        "Português": "Tamanho das cartas"
    },
    "Tamaño de fuente": {
        "Español": "Tamaño de fuente",
        "English": "Font Size",
        "日本語": "フォントサイズ",
        "Français": "Taille de police",
        "Português": "Tamanho de fonte"
    },
    "Sistema": {
        "Español": "Sistema",
        "English": "System",
        "日本語": "システム",
        "Français": "Système",
        "Português": "Sistema"
    },
    "Animaciones UI": {
        "Español": "Animaciones UI",
        "English": "UI Animations",
        "日本語": "UIアニメーション",
        "Français": "Animations UI",
        "Português": "Animações da UI"
    },
    "Idioma": {
        "Español": "Idioma",
        "English": "Language",
        "日本語": "言語",
        "Français": "Langue",
        "Português": "Idioma"
    },
    "Cerrar sesión": {
        "Español": "Cerrar sesión",
        "English": "Log Out",
        "日本語": "ログアウト",
        "Français": "Déconnexion",
        "Português": "Sair"
    },
    "Restaurar valores": {
        "Español": "Restaurar valores",
        "English": "Restore Defaults",
        "日本語": "初期値に戻す",
        "Français": "Restaurer",
        "Português": "Restaurar padrões"
    },
    "Guardar": {
        "Español": "Guardar",
        "English": "Save",
        "日本語": "保存",
        "Français": "Enregistrer",
        "Português": "Salvar"
    },
    "Tema Oscuro": {
        "Español": "🌙 Umbreon (Oscuro)",
        "English": "🌙 Umbreon (Dark)",
        "日本語": "🌙 ブラッキー (ダーク)",
        "Français": "🌙 Noctali (Sombre)",
        "Português": "🌙 Umbreon (Escuro)"
    },
    "Tema Claro": {
        "Español": "☀️ Sylveon (Claro)",
        "English": "☀️ Sylveon (Light)",
        "日本語": "☀️ ニンフィア (ライト)",
        "Français": "☀️ Nymphali (Clair)",
        "Português": "☀️ Sylveon (Claro)"
    },
    "Pequeño": {
        "Español": "Pequeño",
        "English": "Small",
        "日本語": "小",
        "Français": "Petit",
        "Português": "Pequeno"
    },
    "Normal": {
        "Español": "Normal",
        "English": "Normal",
        "日本語": "標準",
        "Français": "Normal",
        "Português": "Normal"
    },
    "Grande": {
        "Español": "Grande",
        "English": "Large",
        "日本語": "大",
        "Français": "Grand",
        "Português": "Grande"
    },
    "SI": {
        "Español": "✅ SI",
        "English": "✅ YES",
        "日本語": "✅ はい",
        "Français": "✅ OUI",
        "Português": "✅ SIM"
    },
    "NO": {
        "Español": "❌ NO",
        "English": "❌ NO",
        "日本語": "❌ いいえ",
        "Français": "❌ NON",
        "Português": "❌ NÃO"
    },
    "Ajustes Guardados": {
        "Español": "Ajustes Guardados",
        "English": "Settings Saved",
        "日本語": "設定を保存しました",
        "Français": "Paramètres enregistrés",
        "Português": "Configurações Salvas"
    },
    "Mensaje Guardado": {
        "Español": "Los ajustes se han guardado y aplicado correctamente.",
        "English": "Settings have been successfully saved and applied.",
        "日本語": "設定が正常に保存され、適用されました。",
        "Français": "Les paramètres ont été enregistrés et appliqués avec succès.",
        "Português": "As configurações foram salvas e aplicadas com sucesso."
    },

    # ── Navegación Lateral / Navigation ──
    "Buscar": {
        "Español": "Buscar",
        "English": "Search",
        "日本語": "検索",
        "Français": "Rechercher",
        "Português": "Buscar"
    },
    "Binder": {
        "Español": "Binder",
        "English": "Binder",
        "日本語": "バインダー",
        "Français": "Classeur",
        "Português": "Fichário"
    },
    "Colección": {
        "Español": "Colección",
        "English": "Collection",
        "日本語": "コレクション",
        "Français": "Collection",
        "Português": "Coleção"
    },
    "Mazos": {
        "Español": "🃏 Mazos",
        "English": "🃏 Decks",
        "日本語": "🃏 デッキ",
        "Français": "🃏 Decks",
        "Português": "🃏 Decks"
    },
    "Mis Mazos": {
        "Español": "Mis Mazos",
        "English": "My Decks",
        "日本語": "マイデッキ",
        "Français": "Mes Decks",
        "Português": "Meus Decks"
    },
    "Nuevo Mazo": {
        "Español": "Nuevo Mazo",
        "English": "New Deck",
        "日本語": "新規デッキ",
        "Français": "Nouveau Deck",
        "Português": "Novo Deck"
    },
    "Print": {
        "Español": "🖨️ Print",
        "English": "🖨️ Print",
        "日本語": "🖨️ 印刷",
        "Français": "🖨️ Imprimer",
        "Português": "🖨️ Imprimir"
    },
    "Imprimir Proxies": {
        "Español": "Imprimir Proxies",
        "English": "Print Proxies",
        "日本語": "プロキシ印刷",
        "Français": "Imprimer Proxies",
        "Português": "Imprimir Proxies"
    },
    "Generar PDF": {
        "Español": "📄 Generar PDF",
        "English": "📄 Generate PDF",
        "日本語": "📄 PDF作成",
        "Français": "📄 Générer PDF",
        "Português": "📄 Gerar PDF"
    },
    "Importar Mazo": {
        "Español": "📋 Importar Mazo",
        "English": "📋 Import Decklist",
        "日本語": "📋 デッキのインポート",
        "Français": "📋 Importer un deck",
        "Português": "📋 Importar Deck"
    },
    "Limpiar Cola": {
        "Español": "🗑️ Limpiar Cola",
        "English": "🗑️ Clear Queue",
        "日本語": "🗑️ キューを消去",
        "Français": "🗑️ Vider la file",
        "Português": "🗑️ Limpar Fila"
    },
    "Tamaño de papel": {
        "Español": "Tamaño de papel",
        "English": "Paper Size",
        "日本語": "用紙サイズ",
        "Français": "Taille del papel",
        "Português": "Tamanho do papel"
    },
    "Medidas de carta": {
        "Español": "Medidas de carta",
        "English": "Card Dimensions",
        "日本語": "カード寸法",
        "Français": "Dimensions des cartes",
        "Português": "Dimensões da carta"
    },
    "Marcas de corte": {
        "Español": "Marcas de corte (Crop marks)",
        "English": "Crop Marks (Cutting lines)",
        "日本語": "切り取り線 (クロップマーク)",
        "Français": "Repères de coupe",
        "Português": "Marcas de corte"
    },
    "Espacio entre cartas": {
        "Español": "Espacio entre cartas",
        "English": "Card Spacing",
        "日本語": "カード間隔",
        "Français": "Espacement des cartes",
        "Português": "Espaçamento entre cartas"
    },
    "Agregar": {
        "Español": "Agregar",
        "English": "Add",
        "日本語": "追加",
        "Français": "Ajouter",
        "Português": "Adicionar"
    },
    "Eliminar": {
        "Español": "Eliminar",
        "English": "Delete",
        "日本語": "削除",
        "Français": "Supprimer",
        "Português": "Excluir"
    },
    "Vaciar": {
        "Español": "Vaciar",
        "English": "Clear All",
        "日本語": "すべて消去",
        "Français": "Vider",
        "Português": "Esvaziar"
    },
    "Salir": {
        "Español": "Salir",
        "English": "Exit",
        "日本語": "終了",
        "Français": "Quitter",
        "Português": "Sair"
    },
    "Salir del programa": {
        "Español": "Salir",
        "English": "Exit",
        "日本語": "終了",
        "Français": "Quitter",
        "Português": "Sair"
    },
    "Menú Principal": {
        "Español": "Menú Principal - Usuario",
        "English": "Main Menu - User",
        "日本語": "メインメニュー - ユーザー",
        "Français": "Menu Principal - Utilisateur",
        "Português": "Menu Principal - Usuário"
    },
    "Usuario:": {
        "Español": "Usuario:",
        "English": "User:",
        "日本語": "ユーザー:",
        "Français": "Utilisateur:",
        "Português": "Usuário:"
    },

    # ── Galería y Búsqueda / Gallery & Search ──
    "Buscar carta por nombre...": {
        "Español": "🔍 Buscar carta por nombre...",
        "English": "🔍 Search card by name...",
        "日本語": "🔍 カード名で検索...",
        "Français": "🔍 Rechercher une carte par nom...",
        "Português": "🔍 Buscar carta por nome..."
    },
    "Actualizar Precios": {
        "Español": "🔄 Actualizar Precios",
        "English": "🔄 Update Prices",
        "日本語": "🔄 価格を更新",
        "Français": "🔄 Mettre à jour les prix",
        "Português": "🔄 Atualizar Preços"
    },
    "Precios Real-Time": {
        "Español": "🔄 Precios Real-Time",
        "English": "🔄 Real-Time Prices",
        "日本語": "🔄 リアルタイム価格",
        "Français": "🔄 Prix en temps réel",
        "Português": "🔄 Preços Em Tempo Real"
    },
    "Rareza": {
        "Español": "Rareza",
        "English": "Rarity",
        "日本語": "レアリティ",
        "Français": "Rareté",
        "Português": "Raridade"
    },
    "Tipo": {
        "Español": "Tipo",
        "English": "Type",
        "日本語": "タイプ",
        "Français": "Type",
        "Português": "Tipo"
    },
    "Edición": {
        "Español": "Edición",
        "English": "Edition",
        "日本語": "エディション",
        "Français": "Édition",
        "Português": "Edição"
    },
    "Tag": {
        "Español": "Tag",
        "English": "Tag",
        "日本語": "タグ",
        "Français": "Tag",
        "Português": "Tag"
    },
    "Tag (Etiqueta)": {
        "Español": "Tag (Etiqueta)",
        "English": "Tag (Label)",
        "日本語": "タグ（ラベル）",
        "Français": "Tag (Étiquette)",
        "Português": "Tag (Etiqueta)"
    },
    "Etapa": {
        "Español": "Etapa",
        "English": "Stage",
        "日本語": "ステージ",
        "Français": "Stade",
        "Português": "Estágio"
    },
    "Entrenador": {
        "Español": "Entrenador",
        "English": "Trainer",
        "日本語": "トレーナー",
        "Français": "Dresseur",
        "Português": "Treinador"
    },
    "Especial": {
        "Español": "Especial",
        "English": "Special",
        "日本語": "スペシャル",
        "Français": "Spécial",
        "Português": "Especial"
    },
    "Todos": {
        "Español": "Todos",
        "English": "All",
        "日本語": "すべて",
        "Français": "Tous",
        "Português": "Todos"
    },
    "Limpiar Filtros": {
        "Español": "Limpiar Filtros",
        "English": "Clear Filters",
        "日本語": "フィルター解除",
        "Français": "Effacer les filtres",
        "Português": "Limpar Filtros"
    },
    "Anterior": {
        "Español": "⬅ Anterior",
        "English": "⬅ Previous",
        "日本語": "⬅ 前へ",
        "Français": "⬅ Précédent",
        "Português": "⬅ Anterior"
    },
    "Siguiente": {
        "Español": "Siguiente ➡",
        "English": "Next ➡",
        "日本語": "次へ ➡",
        "Français": "Suivant ➡",
        "Português": "Próximo ➡"
    },
    "Página": {
        "Español": "Página",
        "English": "Page",
        "日本語": "ページ",
        "Français": "Page",
        "Português": "Página"
    },
    "de": {
        "Español": "de",
        "English": "of",
        "日本語": "/",
        "Français": "de",
        "Português": "de"
    },
    "Valor Inventario": {
        "Español": "💰 Valor Inventario:",
        "English": "💰 Inventory Value:",
        "日本語": "💰 インベントリ総額:",
        "Français": "💰 Valeur de l'inventaire:",
        "Português": "💰 Valor do Inventário:"
    },

    # ── Binder ──
    "Página Vaciada": {
        "Español": "Página vacía",
        "English": "Empty page",
        "日本語": "空のページ",
        "Français": "Page vide",
        "Português": "Página vazia"
    },
    "Cambiar Binder": {
        "Español": "Cambiar Binder",
        "English": "Switch Binder",
        "日本語": "バインダー切替",
        "Français": "Changer de classeur",
        "Português": "Mudar de Fichário"
    },

    # ── Login / Autenticación ──
    "Inicio de Sesión": {
        "Español": "Inicio de Sesión",
        "English": "Login",
        "日本語": "ログイン",
        "Français": "Connexion",
        "Português": "Iniciar Sessão"
    },
    "Ingresa tu nombre de usuario:": {
        "Español": "Ingresa tu nombre de usuario:",
        "English": "Enter your username:",
        "日本語": "ユーザー名を入力してください:",
        "Français": "Entrez votre nom d'utilisateur :",
        "Português": "Digite seu nome de usuário:"
    },
    "Nombre de usuario": {
        "Español": "Nombre de usuario",
        "English": "Username",
        "日本語": "ユーザー名",
        "Français": "Nom d'utilisateur",
        "Português": "Nome de usuário"
    },
    "Entrar / Crear usuario": {
        "Español": "Entrar / Crear usuario",
        "English": "Enter / Create user",
        "日本語": "ログイン / ユーザー作成",
        "Français": "Entrer / Créer un utilisateur",
        "Português": "Entrar / Criar usuário"
    },
    "Bienvenido": {
        "Español": "Bienvenido",
        "English": "Welcome",
        "日本語": "ようこそ",
        "Français": "Bienvenue",
        "Português": "Bem-vindo"
    },
    "Bienvenido de nuevo": {
        "Español": "Bienvenido de nuevo",
        "English": "Welcome back",
        "日本語": "おかえりなさい",
        "Français": "Bon retour",
        "Português": "Bem-vindo de volta"
    },
    "Usuario creado": {
        "Español": "Usuario creado",
        "English": "User created",
        "日本語": "ユーザーを作成しました",
        "Français": "Utilisateur créé",
        "Português": "Usuário criado"
    },
    "Error": {
        "Español": "Error",
        "English": "Error",
        "日本語": "エラー",
        "Français": "Erreur",
        "Português": "Erro"
    },
    "Debes ingresar un nombre de usuario.": {
        "Español": "Debes ingresar un nombre de usuario.",
        "English": "You must enter a username.",
        "日本語": "ユーザー名を入力する必要があります。",
        "Français": "Vous devez entrer un nom d'utilisateur.",
        "Português": "Você deve digitar um nome de usuário."
    },

    # ── Detalle de Carta / Card Tooltip ──
    "Precio mercado:": {
        "Español": "Precio mercado:",
        "English": "Market Price:",
        "日本語": "市場価格:",
        "Français": "Prix du marché :",
        "Português": "Preço de mercado:"
    },
    "Set / Serie:": {
        "Español": "Set / Serie:",
        "English": "Set / Series:",
        "日本語": "セット / シリーズ:",
        "Français": "Série / Extension :",
        "Português": "Conjunto / Série:"
    },
    "Número:": {
        "Español": "Número:",
        "English": "Number:",
        "日本語": "番号:",
        "Français": "Numéro :",
        "Português": "Número:"
    },
    "No disponible": {
        "Español": "No disponible",
        "English": "N/A",
        "日本語": "該当なし",
        "Français": "Non disponible",
        "Português": "Não disponível"
    },

    # ── Actualización / Update Dialog ──
    "Actualización Disponible": {
        "Español": "Actualización Disponible",
        "English": "Update Available",
        "日本語": "利用可能なアップデートがあります",
        "Français": "Mise à jour disponible",
        "Português": "Atualização Disponível"
    },
    "¡Nueva actualización disponible!": {
        "Español": "¡Nueva actualización disponible!",
        "English": "New update available!",
        "日本語": "新しいアップデートが利用可能です！",
        "Français": "Nouvelle mise à jour disponible !",
        "Português": "Nova atualização disponível!"
    },
    "Versión actual": {
        "Español": "Versión actual",
        "English": "Current version",
        "日本語": "現在のバージョン",
        "Français": "Version actuelle",
        "Português": "Versão atual"
    },
    "Nueva versión": {
        "Español": "Nueva versión",
        "English": "New version",
        "日本語": "新バージョン",
        "Français": "Nouvelle version",
        "Português": "Nova versão"
    },
    "Notas de la versión:": {
        "Español": "Notas de la versión:",
        "English": "Release notes:",
        "日本語": "リリースノート:",
        "Français": "Notes de version :",
        "Português": "Notas da versão:"
    },
    "Actualizar más tarde": {
        "Español": "Actualizar más tarde",
        "English": "Update later",
        "日本語": "後でアップデート",
        "Français": "Mettre à jour plus tard",
        "Português": "Atualizar mais tarde"
    },
    "Actualizar ahora": {
        "Español": "Actualizar ahora",
        "English": "Update now",
        "日本語": "今すぐアップデート",
        "Français": "Mettre à jour maintenant",
        "Português": "Atualizar agora"
    },
    "Descargando actualización...": {
        "Español": "Descargando actualización...",
        "English": "Downloading update...",
        "日本語": "アップデートをダウンロード中...",
        "Français": "Téléchargement de la mise à jour...",
        "Português": "Baixando atualização..."
    },
    "Confirma vaciar": {
        "Español": "¿Estás seguro de que deseas vaciar toda tu colección?",
        "English": "Are you sure you want to clear your entire collection?",
        "日本語": "コレクション全体を全消去してもよろしいですか？",
        "Français": "Êtes-vous sûr de vouloir vider toute votre collection ?",
        "Português": "Tem certeza de que deseja esvaziar toda a sua coleção?"
    },
    "Confirma salir": {
        "Español": "¿Deseas salir del programa?",
        "English": "Do you want to exit the program?",
        "日本語": "プログラムを終了しますか？",
        "Français": "Voulez-vous quitter le programme ?",
        "Português": "Deseja sair do programa?"
    },
    # ── Issues #77, #78, #79 (Expansión, Sleeve color, TopLoader Binder) ──
    "Expansión": {
        "Español": "Expansión",
        "English": "Expansion",
        "日本語": "拡張パック",
        "Français": "Extension",
        "Português": "Expansão"
    },
    "Filtrar por expansión de Pokémon TCG": {
        "Español": "Filtrar por expansión de Pokémon TCG",
        "English": "Filter by Pokémon TCG expansion",
        "日本語": "ポケモンカード拡張パックで絞り込み",
        "Français": "Filtrer par extension Pokémon JCC",
        "Português": "Filtrar por expansão do Pokémon Estampas Ilustradas"
    },
    "Tipo de Binder": {
        "Español": "Tipo de Binder",
        "English": "Binder Type",
        "日本語": "バインダータイプ",
        "Français": "Type de classeur",
        "Português": "Tipo de Fichário"
    },
    "TopLoader": {
        "Español": "TopLoader",
        "English": "TopLoader",
        "日本語": "トップローダー",
        "Français": "TopLoader",
        "Português": "TopLoader"
    },
    "Cambiar color de fondo (sleeve)": {
        "Español": "Cambiar color de fondo (sleeve)",
        "English": "Change background color (sleeve)",
        "日本語": "背景色（スリーブ）を変更",
        "Français": "Changer la couleur de fond (sleeve)",
        "Português": "Alterar cor de fundo (sleeve)"
    },
    "Más colores...": {
        "Español": "Más colores...",
        "English": "More colors...",
        "日本語": "その他の色...",
        "Français": "Plus de couleurs...",
        "Português": "Mais cores..."
    },
    "Quitar fondo": {
        "Español": "Quitar fondo",
        "English": "Remove background",
        "日本語": "背景色を削除",
        "Français": "Retirer le fond",
        "Português": "Remover fundo"
    },
    "Fondo de carta actualizado": {
        "Español": "Fondo de carta actualizado",
        "English": "Card background updated",
        "日本語": "カードの背景色を更新しました",
        "Français": "Fond de carte mis à jour",
        "Português": "Fundo da carta atualizado"
    },
    "Fondo de carta quitado": {
        "Español": "Fondo de carta quitado",
        "English": "Card background removed",
        "日本語": "カードの背景色を削除しました",
        "Français": "Fond de carte retiré",
        "Português": "Fundo da carta removido"
    },
    "Activa o desactiva la variante, burbuja de info, idioma y color de fondo (sleeve) en las cartas": {
        "Español": "Activa o desactiva la variante, burbuja de info, idioma y color de fondo (sleeve) en las cartas",
        "English": "Toggle variant, info bubble, language and sleeve background color on binder cards",
        "日本語": "バインダー上のカードのバリエーション、情報アイコン、言語、スリーブ背景色の表示を切り替えます",
        "Français": "Afficher ou masquer la variante, l'info, la langue et la couleur de sleeve sur les cartes",
        "Português": "Ativa ou desativa variante, ícone de info, idioma e cor de sleeve nas cartas"
    }
}


class LanguageManager(QObject):
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        settings = load_settings()
        self._current_language = settings.get("idioma", "Español")

    @property
    def current_language(self) -> str:
        return self._current_language

    def set_language(self, lang: str):
        if lang in ["Español", "English", "日本語", "Français", "Português"]:
            if self._current_language != lang:
                self._current_language = lang
                settings = load_settings()
                settings["idioma"] = lang
                save_settings(settings)
                self.language_changed.emit(lang)

    def t(self, key: str) -> str:
        """Devuelve la traducción para 'key' según el idioma activo."""
        if key in TRANSLATIONS:
            lang_dict = TRANSLATIONS[key]
            return lang_dict.get(self._current_language, lang_dict.get("Español", key))
        return key


# Instancia global del gestor de idiomas
language_manager = LanguageManager()


def t(key: str) -> str:
    """Función de conveniencia para traducir textos."""
    return language_manager.t(key)
