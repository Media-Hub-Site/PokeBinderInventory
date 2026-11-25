import json
import os
import zipfile
from datetime import datetime

from MyQtApp.config import USER_DATA_DIR, BINDER_DATA_FILE, SETTINGS_FILE, load_settings, save_settings
from MyQtApp.session import SessionLocal
from MyQtApp.models import UsuarioCarta, Categoria, Mazo, MazoCarta


DECK_BOXES_STYLE_FILE = os.path.join(USER_DATA_DIR, "deck_boxes.json")


def _read_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_safe(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_user_backup_zip(usuario: str, zip_path: str) -> dict:
    """
    Exporta todos los datos del usuario (Colección, Carpetas, Binders, Mazos, Portamazos 3D y Ajustes)
    a un único archivo .zip portable que puede guardarse en Drive, USB o disco externo.
    Retorna un diccionario resumen con los conteos exportados.
    """
    session = SessionLocal()
    try:
        # 1. Colección y carpetas de colección
        uc_rows = session.query(UsuarioCarta).filter(UsuarioCarta.usuario_nombre == usuario).all()
        collection_list = [
            {
                "carta_id": r.carta_id,
                "idioma": r.idioma or "es",
                "variante": r.variante or "Normal",
                "categoria": r.categoria,
                "cantidad": max(1, int(getattr(r, "cantidad", 1) or 1)),
            }
            for r in uc_rows
        ]

        cat_rows = session.query(Categoria).filter(Categoria.usuario_nombre == usuario).all()
        folders_list = [c.nombre for c in cat_rows if c.nombre]

        # 2. Mazos + cartas + estilos de portamazos 3D
        deck_styles_all = _read_json_safe(DECK_BOXES_STYLE_FILE)
        mazo_rows = session.query(Mazo).filter(Mazo.usuario_nombre == usuario).all()
        decks_list = []
        for m in mazo_rows:
            style_info = deck_styles_all.get(str(m.id), {})
            decks_list.append({
                "nombre": m.nombre,
                "design": style_info.get("design", "Charizard Fuego"),
                "color": style_info.get("color", "auto"),
                "cartas": [
                    {
                        "id_api": mc.id_api,
                        "nombre_carta": mc.nombre_carta,
                        "cantidad": int(mc.cantidad or 1),
                        "idioma": mc.idioma or "es",
                        "edition": mc.edition or "",
                    }
                    for mc in m.cartas
                ],
            })

        # 3. Binders del usuario
        all_binders = _read_json_safe(BINDER_DATA_FILE)
        user_binders = all_binders.get(usuario, {})
        binders_count = len(user_binders.get("folders", {})) if isinstance(user_binders, dict) else 0

        # 4. Ajustes
        settings_data = load_settings()

        manifest = {
            "format": "pokebinder-portable-backup",
            "version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "source_user": usuario,
            "counts": {
                "collection_cards": len(collection_list),
                "collection_folders": len(folders_list),
                "decks": len(decks_list),
                "binders": binders_count,
            },
        }

        os.makedirs(os.path.dirname(os.path.abspath(zip_path)), exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            zf.writestr(
                "user_collection.json",
                json.dumps({"cards": collection_list, "folders": folders_list}, indent=2, ensure_ascii=False),
            )
            zf.writestr("user_decks.json", json.dumps({"decks": decks_list}, indent=2, ensure_ascii=False))
            zf.writestr("user_binders.json", json.dumps(user_binders, indent=2, ensure_ascii=False))
            zf.writestr("user_settings.json", json.dumps(settings_data, indent=2, ensure_ascii=False))

            # Incluir imágenes personalizadas de portadas de binders si existen
            covers_dir = os.path.join(USER_DATA_DIR, "binder_covers")
            if os.path.isdir(covers_dir) and isinstance(user_binders, dict):
                referenced = set()
                for f_data in user_binders.get("folders", {}).values():
                    if isinstance(f_data, dict) and f_data.get("custom_image"):
                        referenced.add(os.path.basename(str(f_data["custom_image"])))
                for fname in referenced:
                    fpath = os.path.join(covers_dir, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, arcname=f"binder_covers/{fname}")

        return manifest["counts"]
    finally:
        session.close()


def import_user_backup_zip(target_usuario: str, zip_path: str) -> dict:
    """
    Importa un archivo .zip portable de PokeBinder y restaura Colección, Carpetas, Binders,
    Mazos, diseños de Portamazos 3D y Ajustes asignándolos automáticamente a `target_usuario`
    (incluso si es una sesión nueva creada desde cero en otro computador).
    """
    if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
        raise ValueError("El archivo seleccionado no es una copia de seguridad válida (.zip).")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("El archivo .zip no corresponde a un respaldo portable de PokeBinder.")

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != "pokebinder-portable-backup":
            raise ValueError("Formato de copia de seguridad no reconocido.")

        col_payload = json.loads(zf.read("user_collection.json").decode("utf-8")) if "user_collection.json" in names else {}
        decks_payload = json.loads(zf.read("user_decks.json").decode("utf-8")) if "user_decks.json" in names else {}
        binders_payload = json.loads(zf.read("user_binders.json").decode("utf-8")) if "user_binders.json" in names else {}
        settings_payload = json.loads(zf.read("user_settings.json").decode("utf-8")) if "user_settings.json" in names else None

        # Restaurar imágenes personalizadas de portadas de binders si vienen en el ZIP
        covers_dir = os.path.join(USER_DATA_DIR, "binder_covers")
        for member in names:
            if member.startswith("binder_covers/") and not member.endswith("/"):
                fname = os.path.basename(member)
                if fname:
                    os.makedirs(covers_dir, exist_ok=True)
                    with open(os.path.join(covers_dir, fname), "wb") as out_f:
                        out_f.write(zf.read(member))

    session = SessionLocal()
    try:
        # 1. Restaurar Carpetas de Colección (fusionando sin duplicar)
        restored_folders = 0
        existing_cats = {
            c.nombre
            for c in session.query(Categoria).filter(Categoria.usuario_nombre == target_usuario).all()
        }
        for folder_name in col_payload.get("folders", []):
            if folder_name and folder_name not in existing_cats:
                session.add(Categoria(usuario_nombre=target_usuario, nombre=folder_name))
                existing_cats.add(folder_name)
                restored_folders += 1

        # 2. Restaurar Cartas de Colección (evitando duplicar filas por carta+idioma)
        restored_cards = 0
        existing_cards = {
            (r.carta_id, r.idioma or "es")
            for r in session.query(UsuarioCarta).filter(UsuarioCarta.usuario_nombre == target_usuario).all()
        }
        for entry in col_payload.get("cards", []):
            cid = entry.get("carta_id")
            if not cid:
                continue
            lang = entry.get("idioma") or "es"
            var = entry.get("variante") or "Normal"
            cat = entry.get("categoria")
            try:
                qty = max(1, int(entry.get("cantidad") or 1))
            except (ValueError, TypeError):
                qty = 1
            sig = (cid, lang)
            if sig in existing_cards:
                continue
            session.add(
                UsuarioCarta(
                    usuario_nombre=target_usuario,
                    carta_id=cid,
                    idioma=lang,
                    variante=var,
                    categoria=cat,
                    cantidad=qty,
                )
            )
            existing_cards.add(sig)
            restored_cards += 1

        # 3. Restaurar Mazos y estilos de Portamazos 3D
        restored_decks = 0
        deck_styles_all = _read_json_safe(DECK_BOXES_STYLE_FILE)
        existing_deck_names = {
            m.nombre
            for m in session.query(Mazo).filter(Mazo.usuario_nombre == target_usuario).all()
        }
        for deck_info in decks_payload.get("decks", []):
            base_name = (deck_info.get("nombre") or "Mazo Importado").strip()
            final_name = base_name
            suffix = 2
            while final_name in existing_deck_names:
                final_name = f"{base_name} ({suffix})"
                suffix += 1
            existing_deck_names.add(final_name)

            nuevo_mazo = Mazo(usuario_nombre=target_usuario, nombre=final_name)
            session.add(nuevo_mazo)
            session.flush()  # Obtener nuevo_mazo.id

            for c in deck_info.get("cartas", []):
                cid = c.get("id_api")
                if not cid:
                    continue
                session.add(
                    MazoCarta(
                        mazo_id=nuevo_mazo.id,
                        id_api=cid,
                        nombre_carta=c.get("nombre_carta") or cid,
                        cantidad=max(1, int(c.get("cantidad") or 1)),
                        idioma=c.get("idioma") or "es",
                        edition=c.get("edition") or "",
                    )
                )

            deck_styles_all[str(nuevo_mazo.id)] = {
                "design": deck_info.get("design", "Charizard Fuego"),
                "color": deck_info.get("color", "auto"),
            }
            restored_decks += 1

        session.commit()
        _write_json_safe(DECK_BOXES_STYLE_FILE, deck_styles_all)

        # 4. Restaurar Binders del usuario (fusionando carpetas de binders)
        restored_binders = 0
        if isinstance(binders_payload, dict) and binders_payload.get("folders"):
            all_binders = _read_json_safe(BINDER_DATA_FILE)
            target_bucket = all_binders.setdefault(target_usuario, {"folders": {}})
            if not isinstance(target_bucket, dict):
                target_bucket = {"folders": {}}
                all_binders[target_usuario] = target_bucket
            target_folders = target_bucket.setdefault("folders", {})

            for f_id, f_data in binders_payload.get("folders", {}).items():
                new_id = f_id
                idx = 2
                while new_id in target_folders:
                    new_id = f"{f_id}_{idx}"
                    idx += 1
                target_folders[new_id] = f_data
                restored_binders += 1

            _write_json_safe(BINDER_DATA_FILE, all_binders)

        # 5. Restaurar Ajustes si vienen incluidos
        if isinstance(settings_payload, dict) and settings_payload:
            merged = {**load_settings(), **settings_payload}
            save_settings(merged)

        return {
            "collection_cards": restored_cards,
            "collection_folders": restored_folders,
            "decks": restored_decks,
            "binders": restored_binders,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
