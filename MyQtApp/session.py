from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

from MyQtApp.config import DB_PATH, DATABASE_URL, ensure_user_data_initialized

ensure_user_data_initialized()
print(f"Usando base de datos en: {DB_PATH}")

engine = create_engine(DATABASE_URL, echo=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Configura PRAGMAs de rendimiento de SQLite en cada conexión."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA temp_store=MEMORY;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.execute("PRAGMA mmap_size=268435456;")
    except Exception:
        pass
    finally:
        cursor.close()


def ensure_performance_indexes(target_engine=engine):
    """Crea índices de rendimiento si no existen en las tablas principales."""
    index_statements = (
        "CREATE INDEX IF NOT EXISTS idx_cartas_id_api_idioma ON Cartas(id_api, idioma)",
        "CREATE INDEX IF NOT EXISTS idx_cartas_nombre ON Cartas(nombre)",
        "CREATE INDEX IF NOT EXISTS idx_cartas_type ON Cartas(type)",
        "CREATE INDEX IF NOT EXISTS idx_cartas_rarity ON Cartas(rarity)",
        "CREATE INDEX IF NOT EXISTS idx_cartas_idioma ON Cartas(idioma)",
        "CREATE INDEX IF NOT EXISTS idx_usuario_carta_user_card_lang ON usuario_carta(usuario_nombre, carta_id, idioma)",
        "CREATE INDEX IF NOT EXISTS idx_usuario_carta_user_cat ON usuario_carta(usuario_nombre, categoria)",
        "CREATE INDEX IF NOT EXISTS idx_mazocarta_mazo_id ON MazoCarta(mazo_id)",
    )
    try:
        with target_engine.begin() as conn:
            for stmt in index_statements:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    # Alguna tabla podría no haberse creado todavía
                    pass
    except Exception:
        pass


ensure_performance_indexes(engine)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

# Las tablas se crearán desde main.py
