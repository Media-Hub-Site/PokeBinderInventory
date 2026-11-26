from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from MyQtApp.session import SessionLocal
from MyQtApp.models import UsuarioCarta, Cartas, Categoria

def agregar_cartas_usuario(usuario_nombre, cartas_info, categoria=None):
    """
    Agrega una lista de cartas a un usuario específico indicando su id_api, idioma y cantidad de copias.
    cartas_info puede ser una lista de dicts [{'id_api': ..., 'idioma': ..., 'cantidad': ...}],
    tuplas (id_api, idioma), o cadenas id_api.
    categoria: nombre opcional de la categoría asignada.
    Retorna el total de copias agregadas con éxito.
    """
    exitos = 0
    session = SessionLocal()
    try:
        for item in cartas_info:
            if isinstance(item, dict):
                carta_id = item.get("id_api")
                idioma = item.get("idioma", "es")
                item_cat = item.get("categoria", categoria)
                try:
                    qty = max(1, int(item.get("cantidad", 1) or 1))
                except (ValueError, TypeError):
                    qty = 1
            elif isinstance(item, (tuple, list)):
                carta_id = item[0]
                idioma = item[1] if len(item) > 1 else "es"
                item_cat = categoria
                qty = 1
            else:
                carta_id = str(item)
                idioma = "es"
                item_cat = categoria
                qty = 1

            if not carta_id:
                continue

            # Verificar si ya existe esa carta en el idioma específico
            existe = session.query(UsuarioCarta).filter_by(
                usuario_nombre=usuario_nombre, carta_id=carta_id, idioma=idioma
            ).first()

            if not existe:
                nueva_carta = UsuarioCarta(
                    usuario_nombre=usuario_nombre,
                    carta_id=carta_id,
                    idioma=idioma,
                    categoria=item_cat,
                    cantidad=qty,
                )
                session.add(nueva_carta)
                exitos += qty
            else:
                existe.cantidad = max(1, int(getattr(existe, "cantidad", 1) or 1)) + qty
                if item_cat:
                    existe.categoria = item_cat
                exitos += qty

        session.commit()
    except Exception as e:
        print(f"Error al agregar cartas: {e}")
        session.rollback()
    finally:
        session.close()

    return exitos


def obtener_categorias_usuario(usuario_nombre):
    """Retorna la lista de nombres de categorías creadas por el usuario."""
    session = SessionLocal()
    try:
        cats = session.query(Categoria.nombre).filter_by(usuario_nombre=usuario_nombre).order_by(Categoria.nombre.asc()).all()
        return [c[0] for c in cats]
    finally:
        session.close()


def crear_categoria_usuario(usuario_nombre, nombre_categoria):
    """Crea una nueva categoría para el usuario si no existe."""
    nombre = nombre_categoria.strip()
    if not nombre:
        return False
    session = SessionLocal()
    try:
        existe = session.query(Categoria).filter_by(usuario_nombre=usuario_nombre, nombre=nombre).first()
        if not existe:
            cat = Categoria(usuario_nombre=usuario_nombre, nombre=nombre)
            session.add(cat)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        print(f"Error al crear categoría: {e}")
        return False
    finally:
        session.close()


def eliminar_categoria_usuario(usuario_nombre, nombre_categoria):
    """Elimina una categoría del usuario y desvincula las cartas de esa categoría."""
    session = SessionLocal()
    try:
        session.query(Categoria).filter_by(usuario_nombre=usuario_nombre, nombre=nombre_categoria).delete()
        session.query(UsuarioCarta).filter_by(usuario_nombre=usuario_nombre, categoria=nombre_categoria).update({"categoria": None})
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error al eliminar categoría: {e}")
        return False
    finally:
        session.close()

def eliminar_cartas_usuario(usuario_nombre, cartas_info, mode="all"):
    """
    Elimina una lista de cartas del inventario de un usuario específico respetando idioma.
    mode="all" elimina el registro completo (todas las copias);
    mode="one" resta una copia (o elimina el registro si solo quedaba 1).
    Retorna la cantidad de copias/registros eliminados.
    """
    eliminados = 0
    session = SessionLocal()
    try:
        for item in cartas_info:
            if isinstance(item, dict):
                carta_id = item.get("id_api")
                idioma = item.get("idioma")
            elif isinstance(item, (tuple, list)):
                carta_id = item[0]
                idioma = item[1] if len(item) > 1 else None
            else:
                carta_id = str(item)
                idioma = None

            if not carta_id:
                continue

            q = session.query(UsuarioCarta).filter_by(usuario_nombre=usuario_nombre, carta_id=carta_id)
            if idioma:
                q = q.filter_by(idioma=idioma)

            registro = q.first()
            if registro:
                qty_actual = max(1, int(getattr(registro, "cantidad", 1) or 1))
                if mode == "one" and qty_actual > 1:
                    registro.cantidad = qty_actual - 1
                    eliminados += 1
                else:
                    session.delete(registro)
                    eliminados += qty_actual

        session.commit()
    except Exception as e:
        print(f"Error al eliminar cartas: {e}")
        session.rollback()
    finally:
        session.close()

    return eliminados


def actualizar_cantidades_usuario(usuario_nombre: str, cambios: list[dict]) -> tuple[int, int]:
    """
    Actualiza las cantidades de cartas existentes en UsuarioCarta.
    cambios: lista de dicts {'id_api': str, 'idioma': str, 'cantidad': int}.
    Si cantidad <= 0, elimina la carta de la colección.
    Retorna (actualizadas, eliminadas).
    """
    if not cambios:
        return 0, 0
    actualizadas = 0
    eliminadas = 0
    session = SessionLocal()
    try:
        for item in cambios:
            carta_id = item.get("id_api")
            idioma = item.get("idioma")
            try:
                new_qty = int(item.get("cantidad", 1))
            except (TypeError, ValueError):
                continue
            if not carta_id:
                continue

            q = session.query(UsuarioCarta).filter(
                UsuarioCarta.usuario_nombre == usuario_nombre,
                UsuarioCarta.carta_id == carta_id,
            )
            registro = None
            if idioma:
                registro = q.filter(
                    func.coalesce(UsuarioCarta.idioma, "es") == idioma
                ).first()
            if not registro:
                registro = q.first()

            if not registro:
                continue

            if new_qty <= 0:
                session.query(UsuarioCarta).filter(UsuarioCarta.id == registro.id).delete()
                eliminadas += 1
            else:
                new_qty = min(99, new_qty)
                if int(getattr(registro, "cantidad", 1) or 1) != new_qty:
                    registro.cantidad = new_qty
                    actualizadas += 1

        session.commit()
    except Exception as e:
        print(f"Error al actualizar cantidades: {e}")
        session.rollback()
        return 0, 0
    finally:
        session.close()

    return actualizadas, eliminadas


def obtener_cartas_usuario(usuario_nombre):
    """
    Retorna todas las relaciones UsuarioCarta de un usuario.
    """
    session = SessionLocal()
    try:
        return session.query(UsuarioCarta).filter_by(usuario_nombre=usuario_nombre).all()
    finally:
        session.close()
