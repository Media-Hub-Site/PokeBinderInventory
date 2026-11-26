import copy
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


def _normalize_binder_folder(f_data: dict, fallback_name: str = "Mi Binder") -> dict:
    """
    Garantiza que una carpeta de binder conserve íntegros todos sus campos de diseño,
    configuración y cartas asignadas por hoja/bolsillo (page_slot).
    """
    if not isinstance(f_data, dict):
        f_data = {}
    out = copy.deepcopy(f_data)
    out["name"] = f_data.get("name") or fallback_name
    out["color"] = f_data.get("color", "auto")
    out["design"] = f_data.get("design", "Pokédex Clásica")
    out["custom_image"] = f_data.get("custom_image", None)
    out["interior_color"] = f_data.get("interior_color", "#14161f")
    out["advanced_design"] = (
        copy.deepcopy(f_data["advanced_design"])
        if "advanced_design" in f_data and f_data["advanced_design"] is not None
        else {}
    )
    out["locked"] = bool(f_data.get("locked", False))
    out["mode"] = f_data.get("mode", "3x3")
    out["cards"] = copy.deepcopy(f_data["cards"]) if isinstance(f_data.get("cards"), dict) else {}
    return out


def _extract_folders_dict(raw_bucket: dict) -> dict:
    """
    Extrae el diccionario de carpetas desde un bucket de usuario en binder_data,
    soportando tanto el formato {"folders": {...}} como carpetas en el nivel raíz.
    """
    if not isinstance(raw_bucket, dict):
        return {}
    if "folders" in raw_bucket and isinstance(raw_bucket.get("folders"), dict):
        source = raw_bucket["folders"]
    else:
        source = {
            k: v for k, v in raw_bucket.items()
            if k != "folders" and isinstance(v, dict)
        }
    normalized = {}
    for f_id, f_data in source.items():
        if isinstance(f_data, dict):
            normalized[str(f_id)] = _normalize_binder_folder(f_data, fallback_name=str(f_id))
    return normalized


def _get_user_binders_case_insensitive(all_binders: dict, usuario: str) -> dict:
    """
    Busca los binders del usuario en `all_binders` primero por coincidencia exacta
    y luego de forma case-insensitive (.lower()), unificando carpetas si existieran
    claves con distinto case para el mismo usuario.
    """
    if not isinstance(all_binders, dict) or not usuario:
        return {"folders": {}}

    merged_folders: dict = {}
    u_lower = usuario.strip().lower()

    # Primero claves que coinciden case-insensitive (para que la clave exacta tenga prioridad si ambas existen)
    for k, bucket in all_binders.items():
        if isinstance(k, str) and k != usuario and k.strip().lower() == u_lower:
            merged_folders.update(_extract_folders_dict(bucket))

    # Luego coincidencia exacta
    if usuario in all_binders:
        merged_folders.update(_extract_folders_dict(all_binders.get(usuario)))

    return {"folders": merged_folders}


def _collect_referenced_sticker_filenames(obj, out_set: set):
    """
    Recorre recursivamente una estructura `advanced_design` recolectando nombres de archivo
    de elementos con `kind == "image"` y `key`.
    """
    if isinstance(obj, dict):
        if obj.get("kind") == "image" and obj.get("key"):
            fname = os.path.basename(str(obj["key"]))
            if fname:
                out_set.add(fname)
        for v in obj.values():
            _collect_referenced_sticker_filenames(v, out_set)
    elif isinstance(obj, list):
        for item in obj:
            _collect_referenced_sticker_filenames(item, out_set)


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
            if not isinstance(style_info, dict):
                style_info = {}
            decks_list.append({
                "nombre": m.nombre,
                "design": style_info.get("design", "Charizard Fuego"),
                "color": style_info.get("color", "auto"),
                "interior_color": style_info.get("interior_color", "#14161f"),
                "custom_image": style_info.get("custom_image", None),
                "advanced_design": copy.deepcopy(style_info.get("advanced_design", {})),
                "locked": bool(style_info.get("locked", False)),
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

        # 3. Binders del usuario (búsqueda exacta + case-insensitive)
        all_binders = _read_json_safe(BINDER_DATA_FILE)
        user_binders = _get_user_binders_case_insensitive(all_binders, usuario)
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

            written_arcnames = set()

            # Incluir imágenes personalizadas de portadas de binders (binder_covers/)
            covers_dir = os.path.join(USER_DATA_DIR, "binder_covers")
            referenced_covers = set()
            if isinstance(user_binders, dict):
                for f_data in user_binders.get("folders", {}).values():
                    if isinstance(f_data, dict) and f_data.get("custom_image"):
                        c_img = str(f_data["custom_image"])
                        referenced_covers.add(os.path.basename(c_img))
                        if os.path.isabs(c_img) and os.path.isfile(c_img):
                            arc = f"binder_covers/{os.path.basename(c_img)}"
                            if arc not in written_arcnames:
                                zf.write(c_img, arcname=arc)
                                written_arcnames.add(arc)

            if os.path.isdir(covers_dir):
                all_cover_files = set(os.listdir(covers_dir)) | referenced_covers
                for fname in sorted(all_cover_files):
                    fpath = os.path.join(covers_dir, fname)
                    arc = f"binder_covers/{fname}"
                    if os.path.isfile(fpath) and arc not in written_arcnames:
                        zf.write(fpath, arcname=arc)
                        written_arcnames.add(arc)

            # Incluir stickers personalizados usados en advanced_design (custom_stickers/)
            stickers_dir = os.path.join(USER_DATA_DIR, "custom_stickers")
            referenced_stickers = set()
            if isinstance(user_binders, dict):
                for f_data in user_binders.get("folders", {}).values():
                    if isinstance(f_data, dict):
                        _collect_referenced_sticker_filenames(f_data.get("advanced_design"), referenced_stickers)
            for d_info in decks_list:
                if isinstance(d_info, dict):
                    _collect_referenced_sticker_filenames(d_info.get("advanced_design"), referenced_stickers)

            if os.path.isdir(stickers_dir):
                all_sticker_files = set(os.listdir(stickers_dir)) | referenced_stickers
                for fname in sorted(all_sticker_files):
                    fpath = os.path.join(stickers_dir, fname)
                    arc = f"custom_stickers/{fname}"
                    if os.path.isfile(fpath) and arc not in written_arcnames:
                        zf.write(fpath, arcname=arc)
                        written_arcnames.add(arc)

        return manifest["counts"]
    finally:
        session.close()


def _call_safe(obj, method_name: str):
    fn = getattr(obj, method_name, None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def _get_page_widget(paginas, index: int):
    try:
        if hasattr(paginas, "count") and callable(paginas.count):
            cnt = paginas.count()
            if isinstance(cnt, int) and index >= cnt:
                return None
        return paginas.widget(index)
    except Exception:
        return None


def _extract_paginas_widgets(window) -> list:
    """
    Busca widgets `paginas` (QStackedWidget) en `window`, en su ventana raíz o en sus hijos `MainWindow`.
    Si `window` es None, inspecciona las ventanas activas de `QApplication`.
    """
    candidates = []
    if window is None:
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                for top in app.topLevelWidgets():
                    for st in _extract_paginas_widgets(top):
                        if st not in candidates:
                            candidates.append(st)
        except Exception:
            pass
        return candidates

    seen = set()

    def _add_if_valid(stack):
        if stack is not None and id(stack) not in seen and hasattr(stack, "widget"):
            seen.add(id(stack))
            candidates.append(stack)

    _add_if_valid(getattr(window, "paginas", None))

    if hasattr(window, "window") and callable(window.window):
        try:
            top_win = window.window()
            if top_win is not None and top_win is not window:
                _add_if_valid(getattr(top_win, "paginas", None))
        except Exception:
            pass

    if hasattr(window, "findChildren") and callable(window.findChildren):
        try:
            from PyQt6.QtWidgets import QWidget, QStackedWidget
            for child in window.findChildren(QWidget):
                if hasattr(child, "paginas"):
                    _add_if_valid(getattr(child, "paginas", None))
            if not candidates:
                for st in window.findChildren(QStackedWidget):
                    _add_if_valid(st)
        except Exception:
            pass

    for attr_name in ("main_window", "central_widget", "content"):
        sub = getattr(window, attr_name, None)
        if sub is not None:
            _add_if_valid(getattr(sub, "paginas", None))

    return candidates


def refresh_main_window_after_import(window=None) -> bool:
    """
    Busca `paginas` (QStackedWidget) en `window` (o en sus hijos `MainWindow`) y refresca en vivo:
    - BinderView (paginas.widget(1)): load_binder_data(), render_folders_grid(),
      update_folder_combo(), mostrar_vista_carpetas(), refresh_inventory().
    - GaleriaCartasInventario (paginas.widget(2)): cargar_categorias_combo(), reset_page_and_actualizar().
    - MazosView (paginas.widget(3)): cargar_mazos(), mostrar_vista_mazos().
    """
    stacks = _extract_paginas_widgets(window)
    refreshed = False
    for paginas in stacks:
        binder_view = _get_page_widget(paginas, 1)
        if binder_view is not None:
            _call_safe(binder_view, "load_binder_data")
            _call_safe(binder_view, "render_folders_grid")
            _call_safe(binder_view, "update_folder_combo")
            _call_safe(binder_view, "mostrar_vista_carpetas")
            _call_safe(binder_view, "refresh_inventory")
            refreshed = True

        inv_view = _get_page_widget(paginas, 2)
        if inv_view is not None:
            _call_safe(inv_view, "cargar_categorias_combo")
            _call_safe(inv_view, "reset_page_and_actualizar")
            refreshed = True

        mazos_view = _get_page_widget(paginas, 3)
        if mazos_view is not None:
            _call_safe(mazos_view, "cargar_mazos")
            _call_safe(mazos_view, "mostrar_vista_mazos")
            refreshed = True

    return refreshed


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

        # Restaurar imágenes personalizadas de portadas de binders y stickers personalizados
        covers_dir = os.path.join(USER_DATA_DIR, "binder_covers")
        stickers_dir = os.path.join(USER_DATA_DIR, "custom_stickers")
        for member in names:
            if member.startswith("binder_covers/") and not member.endswith("/"):
                fname = os.path.basename(member)
                if fname:
                    os.makedirs(covers_dir, exist_ok=True)
                    with open(os.path.join(covers_dir, fname), "wb") as out_f:
                        out_f.write(zf.read(member))
            elif member.startswith("custom_stickers/") and not member.endswith("/"):
                fname = os.path.basename(member)
                if fname:
                    os.makedirs(stickers_dir, exist_ok=True)
                    with open(os.path.join(stickers_dir, fname), "wb") as out_f:
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
                "interior_color": deck_info.get("interior_color", "#14161f"),
                "custom_image": deck_info.get("custom_image", None),
                "advanced_design": copy.deepcopy(deck_info.get("advanced_design", {})),
                "locked": bool(deck_info.get("locked", False)),
            }
            restored_decks += 1

        session.commit()
        _write_json_safe(DECK_BOXES_STYLE_FILE, deck_styles_all)

        # 4. Restaurar Binders del usuario (soportando formato con "folders" o directo, y unificando case)
        restored_binders = 0
        incoming_folders = _extract_folders_dict(binders_payload) if isinstance(binders_payload, dict) else {}
        if incoming_folders:
            all_binders = _read_json_safe(BINDER_DATA_FILE)
            target_folders: dict = {}
            target_lower = (target_usuario or "").strip().lower()

            # Unificar claves existentes con distinto case para el mismo usuario bajo `target_usuario`
            other_case_keys = [
                k for k in list(all_binders.keys())
                if isinstance(k, str) and k != target_usuario and k.strip().lower() == target_lower
            ]
            for old_key in other_case_keys:
                old_bucket = all_binders.pop(old_key, None)
                target_folders.update(_extract_folders_dict(old_bucket))

            if target_usuario in all_binders:
                target_folders.update(_extract_folders_dict(all_binders.get(target_usuario)))

            for f_id, f_data in incoming_folders.items():
                norm_data = _normalize_binder_folder(f_data, fallback_name=str(f_id))
                if f_id not in target_folders:
                    target_folders[f_id] = norm_data
                else:
                    existing_folder = target_folders.get(f_id)
                    if isinstance(existing_folder, dict) and (
                        existing_folder.get("name") == norm_data.get("name")
                        or existing_folder == norm_data
                    ):
                        # Mismo ID y mismo nombre/contenido: actualizar/sobrescribir configuración, diseños y cartas
                        target_folders[f_id] = norm_data
                    else:
                        # Nombre distinto con colisión de ID: crear nuevo ID sin sobrescribir el otro binder
                        new_id = f_id
                        idx = 2
                        while (
                            new_id in target_folders
                            and isinstance(target_folders.get(new_id), dict)
                            and target_folders[new_id].get("name") != norm_data.get("name")
                        ):
                            new_id = f"{f_id}_{idx}"
                            idx += 1
                        target_folders[new_id] = norm_data
                restored_binders += 1

            all_binders[target_usuario] = {"folders": target_folders}
            _write_json_safe(BINDER_DATA_FILE, all_binders)

        # 5. Restaurar Ajustes si vienen incluidos
        if isinstance(settings_payload, dict) and settings_payload:
            merged = {**load_settings(), **settings_payload}
            save_settings(merged)

        # Refrescar en vivo cualquier ventana principal activa si hay instancia Qt corriendo
        try:
            refresh_main_window_after_import(None)
        except Exception:
            pass

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
