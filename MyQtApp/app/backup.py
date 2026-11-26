import os
import shutil
import sqlite3
from datetime import datetime
from MyQtApp.config import DB_PATH, BACKUPS_DIR, SEED_DB_PATH


def get_backups_dir() -> str:
    """Asegura que exista la carpeta de respaldos y devuelve la ruta."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    return BACKUPS_DIR


def _cleanup_sqlite_sidecars(db_path: str):
    """Elimina archivos temporales WAL/SHM/journal asociados a una ruta SQLite."""
    if not db_path:
        return
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = db_path + suffix
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
            except Exception as e:
                print(f"[Backup] No se pudo limpiar {sidecar}: {e}")


def is_database_healthy(db_path: str) -> bool:
    """Verifica integridad rápida de una base SQLite (PRAGMA quick_check + sqlite_master)."""
    if not db_path or not os.path.exists(db_path) or os.path.getsize(db_path) <= 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        cur = conn.cursor()
        rows = cur.execute("PRAGMA quick_check").fetchall()
        if not rows or rows[0][0] != "ok":
            return False
        cur.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def ensure_database_integrity_or_recover() -> bool:
    """
    Comprueba que la base de datos activa (`DB_PATH`) esté íntegra.
    Si detecta corrupción (`database disk image is malformed`), resguarda el archivo dañando
    y restaura automáticamente el respaldo sano más reciente (o SEED_DB_PATH si no hay backups).
    """
    if os.path.exists(DB_PATH) and is_database_healthy(DB_PATH):
        return True

    if os.path.exists(DB_PATH):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        quarantine_path = f"{DB_PATH}.corrupt_{ts}"
        print(f"[Recovery] Detectada base de datos dañada en {DB_PATH}. Resguardando en {quarantine_path}...")
        try:
            shutil.move(DB_PATH, quarantine_path)
        except Exception as e:
            print(f"[Recovery] No se pudo mover BD dañada ({e}); intentando sobrescribir.")
        _cleanup_sqlite_sidecars(DB_PATH)

    # Buscar el respaldo más reciente que pase la verificación de integridad
    for fname, backup_path, _dt_str in list_backups():
        if is_database_healthy(backup_path):
            try:
                shutil.copy2(backup_path, DB_PATH)
                _cleanup_sqlite_sidecars(DB_PATH)
                if is_database_healthy(DB_PATH):
                    print(f"[Recovery] Base de datos recuperada automáticamente desde respaldo sano: {fname}")
                    return True
            except Exception as e:
                print(f"[Recovery] Fallo al restaurar desde {fname}: {e}")

    # Respaldo final desde SEED_DB_PATH
    if SEED_DB_PATH and os.path.exists(SEED_DB_PATH) and is_database_healthy(SEED_DB_PATH):
        try:
            shutil.copy2(SEED_DB_PATH, DB_PATH)
            _cleanup_sqlite_sidecars(DB_PATH)
            print(f"[Recovery] Base de datos inicializada desde semilla limpia: {SEED_DB_PATH}")
            return True
        except Exception as e:
            print(f"[Recovery] Error restaurando desde semilla: {e}")

    return False


def create_database_backup(tag: str = "manual") -> str:
    """
    Crea una copia de seguridad consistente de PokeDatabase.db.
    Retorna la ruta absoluta del archivo de respaldo creado o None si la base de datos no existe o está corrupta.
    """
    if not os.path.exists(DB_PATH):
        print(f"[Backup] No se encontró la base de datos en: {DB_PATH}")
        return None
    if not is_database_healthy(DB_PATH):
        print("[Backup] Omitiendo respaldo automático porque la BD actual no pasó verificación de integridad.")
        return None

    backups_dir = get_backups_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"PokeDatabase_backup_{tag}_{ts}.db"
    backup_path = os.path.join(backups_dir, backup_filename)

    try:
        # Usar la API de backup nativa de SQLite3 para garantizar una copia segura aun si la DB está abierta
        src_conn = sqlite3.connect(DB_PATH)
        dst_conn = sqlite3.connect(backup_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        print(f"[Backup] Copia de seguridad creada exitosamente: {backup_path}")

        # Limpiar respaldos antiguos mantención máxima
        cleanup_old_backups()
        return backup_path
    except Exception as e:
        print(f"[Backup] Error creando copia de seguridad con sqlite backup, usando fallback shutil: {e}")
        try:
            shutil.copy2(DB_PATH, backup_path)
            cleanup_old_backups()
            return backup_path
        except Exception as err:
            print(f"[Backup] Error en copia fallback: {err}")
            return None


def list_backups() -> list:
    """Devuelve una lista de tuplas (filename, filepath, timestamp_formatted) ordenada de más reciente a más antigua."""
    backups_dir = get_backups_dir()
    if not os.path.exists(backups_dir):
        return []

    items = []
    for f in os.listdir(backups_dir):
        if f.startswith("PokeDatabase_backup_") and f.endswith(".db"):
            full_path = os.path.join(backups_dir, f)
            mtime = os.path.getmtime(full_path)
            dt_str = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M:%S")
            items.append((f, full_path, mtime, dt_str))

    items.sort(key=lambda x: x[2], reverse=True)
    return [(item[0], item[1], item[3]) for item in items]


def restore_database_backup(backup_path: str) -> bool:
    """
    Restaura la base de datos desde un archivo de respaldo especificado.
    Antes de sobrescribir, realiza un respaldo de emergencia de la DB actual si está sana.
    """
    if not os.path.exists(backup_path) or not is_database_healthy(backup_path):
        print(f"[Backup] El archivo de respaldo no existe o está dañado: {backup_path}")
        return False

    try:
        # Crear respaldo preventivo de la DB actual antes de restaurar (solo si está sana)
        if os.path.exists(DB_PATH) and is_database_healthy(DB_PATH):
            pre_restore_tag = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            create_database_backup(tag=pre_restore_tag)

        _cleanup_sqlite_sidecars(DB_PATH)

        # Restaurar copia
        dst_conn = sqlite3.connect(DB_PATH)
        src_conn = sqlite3.connect(backup_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        print(f"[Backup] Base de datos restaurada correctamente desde: {backup_path}")
        return True
    except Exception as e:
        print(f"[Backup] Error restaurando base de datos: {e}")
        try:
            _cleanup_sqlite_sidecars(DB_PATH)
            shutil.copy2(backup_path, DB_PATH)
            return True
        except Exception as err:
            print(f"[Backup] Error en restore fallback: {err}")
            return False


def cleanup_old_backups(keep_count: int = 15):
    """Mantiene solo las últimas `keep_count` copias de seguridad para evitar uso excesivo de disco."""
    backups_dir = get_backups_dir()
    items = []
    for f in os.listdir(backups_dir):
        if f.startswith("PokeDatabase_backup_") and f.endswith(".db"):
            full_path = os.path.join(backups_dir, f)
            mtime = os.path.getmtime(full_path)
            items.append((full_path, mtime))

    items.sort(key=lambda x: x[1], reverse=True)
    if len(items) > keep_count:
        for full_path, _ in items[keep_count:]:
            try:
                os.remove(full_path)
                _cleanup_sqlite_sidecars(full_path)
                print(f"[Backup] Limpieza de respaldo antiguo: {full_path}")
            except Exception as e:
                print(f"[Backup] No se pudo eliminar respaldo antiguo {full_path}: {e}")
