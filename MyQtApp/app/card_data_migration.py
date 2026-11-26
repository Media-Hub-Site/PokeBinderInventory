"""Migración y normalización transaccional de metadatos de cartas en SQLite (Tarea #72)."""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

CARD_DATA_MIGRATION_VERSION = 72

VALID_STAGES = ("Basic", "Stage 1", "Stage 2", "Baby", "Restored", "Ninguno")

STAGE_TRAINER_SUBTYPES = (
    "Supporter",
    "Item",
    "Pokémon Tool",
    "Pokémon Tool F",
    "Stadium",
    "Technical Machine",
    "Rocket's Secret Machine",
    "Goldenrod Game Corner",
)

STAGE_MECHANICS_SUBTYPES = (
    "VMAX",
    "VSTAR",
    "MEGA",
    "Level-Up",
    "BREAK",
    "V-UNION",
    "LEGEND",
    "Single Strike",
    "Rapid Strike",
    "Fusion Strike",
)

TRAINER_RULE_BOX_VALUES = (
    "ex",
    "GX",
    "Ultra Beast",
    "Single Strike",
    "Rapid Strike",
    "Future",
    "Ancient",
    "Team Plasma",
    "Tera",
    "Fusion Strike",
    "ACE SPEC",
)

ESPECIAL_TRAINER_VALUES = (
    "Supporter",
    "Item",
    "Pokémon Tool",
    "Special",
)


def _needs_migration(cur: sqlite3.Cursor, current_version: int) -> bool:
    """Verifica instantáneamente si la base de datos requiere normalización."""
    if current_version < CARD_DATA_MIGRATION_VERSION:
        return True
    return False


def normalize_cards_database(db_path: str, force: bool = False) -> dict[str, Any]:
    """
    Corrige y normaliza las columnas `stage`, `trainer`, `especial_type`, `type`, `rarity` y `edition`
    de la tabla `Cartas`, y propaga metadatos desde `idioma='en'` al resto de idiomas por `id_api`.

    Es idempotente y se ejecuta en una única transacción SQL rápida (< 2 segundos).
    """
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "db_path": db_path,
        "exists": bool(db_path and os.path.exists(db_path)),
        "applied": False,
        "user_version": 0,
        "updates": {},
        "total_updates": 0,
        "elapsed_ms": 0.0,
    }

    if not result["exists"]:
        return result

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        table_exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Cartas'"
        ).fetchone()
        if not table_exists:
            return result

        current_version = int(cur.execute("PRAGMA user_version").fetchone()[0] or 0)
        result["user_version"] = current_version

        if not force and not _needs_migration(cur, current_version):
            result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            return result

        updates: dict[str, int] = {}

        # 1. En `trainer`: mover valores que son Rule Box / Especial a `especial_type`
        #    (si `especial_type` está en 'Normal' / None / 'Ninguno') y normalizar 'Desconocido' / None -> 'Ninguno'.
        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = CASE
                    WHEN especial_type IS NULL OR TRIM(especial_type) = '' OR especial_type IN ('Normal', 'Ninguno')
                    THEN trainer
                    ELSE especial_type
                END,
                trainer = 'Ninguno'
            WHERE trainer IN (
                'ex', 'GX', 'Ultra Beast', 'Single Strike', 'Rapid Strike',
                'Future', 'Ancient', 'Team Plasma', 'Tera', 'Fusion Strike', 'ACE SPEC'
            )
            """
        )
        updates["trainer_rulebox_to_especial"] = max(0, cur.rowcount)

        cur.execute(
            """
            UPDATE Cartas
            SET trainer = 'Ninguno'
            WHERE trainer IS NULL OR TRIM(trainer) = '' OR trainer = 'Desconocido'
            """
        )
        updates["trainer_unknown_to_ninguno"] = max(0, cur.rowcount)

        # 2. En `stage`: mover subtipos de Entrenador a `trainer` (con normalización) y poner stage = 'Ninguno'.
        cur.execute(
            """
            UPDATE Cartas
            SET trainer = CASE stage
                    WHEN 'Pokémon Tool F' THEN 'Pokémon Tool'
                    WHEN 'Rocket''s Secret Machine' THEN 'Technical Machine'
                    WHEN 'Goldenrod Game Corner' THEN 'Stadium'
                    ELSE stage
                END,
                stage = 'Ninguno'
            WHERE stage IN (
                'Supporter', 'Item', 'Pokémon Tool', 'Pokémon Tool F',
                'Stadium', 'Technical Machine', 'Rocket''s Secret Machine', 'Goldenrod Game Corner'
            )
            """
        )
        updates["stage_trainer_to_trainer"] = max(0, cur.rowcount)

        # 3. En `especial_type`: mover subtipos de Entrenador ('Supporter', 'Item', 'Pokémon Tool', 'Special')
        #    a `trainer` (salvo 'Special' que queda con su trainer y pasa a 'Normal') y poner especial_type = 'Normal'.
        cur.execute(
            """
            UPDATE Cartas
            SET trainer = CASE
                    WHEN especial_type = 'Special' THEN trainer
                    WHEN trainer = 'Pokémon Tool' AND especial_type = 'Item' THEN trainer
                    ELSE especial_type
                END,
                especial_type = 'Normal'
            WHERE especial_type IN ('Supporter', 'Item', 'Pokémon Tool', 'Special')
            """
        )
        updates["especial_trainer_to_trainer"] = max(0, cur.rowcount)

        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = 'Normal'
            WHERE especial_type IS NULL OR TRIM(especial_type) = '' OR especial_type = 'Ninguno'
            """
        )
        updates["especial_null_to_normal"] = max(0, cur.rowcount)

        # 4. En `stage`: mover mecánicas / Rule Box a `especial_type`
        #    (si `especial_type` es 'Normal', 'Ninguno', None o 'V') y poner stage = 'Ninguno'.
        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = CASE
                    WHEN especial_type IS NULL OR TRIM(especial_type) = '' OR especial_type IN ('Normal', 'Ninguno', 'V')
                    THEN stage
                    ELSE especial_type
                END,
                stage = 'Ninguno'
            WHERE stage IN (
                'VMAX', 'VSTAR', 'MEGA', 'Level-Up', 'BREAK', 'V-UNION',
                'LEGEND', 'Single Strike', 'Rapid Strike', 'Fusion Strike'
            )
            """
        )
        updates["stage_mechanics_to_especial"] = max(0, cur.rowcount)

        # 5. En `stage`: subtipo de energía 'Special' y cualquier valor fuera de etapas válidas -> 'Ninguno'.
        cur.execute(
            """
            UPDATE Cartas
            SET stage = 'Ninguno'
            WHERE stage IS NULL
               OR stage NOT IN ('Basic', 'Stage 1', 'Stage 2', 'Baby', 'Restored', 'Ninguno')
            """
        )
        updates["stage_invalid_to_ninguno"] = max(0, cur.rowcount)

        # 6. Por sufijo del nombre (`nombre`): asegurar VMAX, VSTAR y V-UNION en `especial_type`.
        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = 'VMAX'
            WHERE (nombre LIKE '% VMAX' OR nombre LIKE '% V-MAX')
              AND (especial_type IS NULL OR especial_type != 'VMAX')
            """
        )
        vmax_by_name = max(0, cur.rowcount)

        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = 'VSTAR'
            WHERE nombre LIKE '% VSTAR'
              AND (especial_type IS NULL OR especial_type != 'VSTAR')
            """
        )
        vstar_by_name = max(0, cur.rowcount)

        cur.execute(
            """
            UPDATE Cartas
            SET especial_type = 'V-UNION'
            WHERE nombre LIKE '% V-UNION'
              AND (especial_type IS NULL OR especial_type != 'V-UNION')
            """
        )
        vunion_by_name = max(0, cur.rowcount)
        updates["especial_by_name_suffix"] = vmax_by_name + vstar_by_name + vunion_by_name

        # 7. En `type`: normalizar 'Electric' -> 'Lightning'.
        cur.execute(
            """
            UPDATE Cartas
            SET type = 'Lightning'
            WHERE type = 'Electric'
            """
        )
        updates["type_electric_to_lightning"] = max(0, cur.rowcount)

        # 8. Propagación multilingüe por `id_api` desde la fila `idioma='en'` hacia el resto de idiomas.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cartas_id_api ON Cartas(id_api)")

        cur.execute(
            """
            UPDATE Cartas
            SET type = CASE
                    WHEN (Cartas.type IS NULL OR Cartas.type IN ('', 'Desconocido'))
                         AND en.type IS NOT NULL AND en.type NOT IN ('', 'Desconocido')
                    THEN en.type
                    ELSE Cartas.type
                END,
                rarity = CASE
                    WHEN (Cartas.rarity IS NULL OR Cartas.rarity IN ('', 'Desconocida', 'Desconocido'))
                         AND en.rarity IS NOT NULL AND en.rarity NOT IN ('', 'Desconocida', 'Desconocido')
                    THEN en.rarity
                    ELSE Cartas.rarity
                END,
                stage = CASE
                    WHEN (Cartas.stage IS NULL OR Cartas.stage IN ('', 'Ninguno', 'Desconocido'))
                         AND en.stage IS NOT NULL AND en.stage NOT IN ('', 'Ninguno', 'Desconocido')
                    THEN en.stage
                    ELSE Cartas.stage
                END,
                trainer = CASE
                    WHEN (Cartas.trainer IS NULL OR Cartas.trainer IN ('', 'Ninguno', 'Desconocido'))
                         AND en.trainer IS NOT NULL AND en.trainer NOT IN ('', 'Ninguno', 'Desconocido')
                    THEN en.trainer
                    ELSE Cartas.trainer
                END,
                especial_type = CASE
                    WHEN (Cartas.especial_type IS NULL OR Cartas.especial_type IN ('', 'Normal', 'Ninguno', 'Desconocido'))
                         AND en.especial_type IS NOT NULL AND en.especial_type NOT IN ('', 'Normal', 'Ninguno', 'Desconocido')
                    THEN en.especial_type
                    ELSE Cartas.especial_type
                END,
                edition = CASE
                    WHEN (Cartas.edition IS NULL OR Cartas.edition IN ('', 'Ninguno', 'Desconocido'))
                         AND en.edition IS NOT NULL AND en.edition NOT IN ('', 'Ninguno', 'Desconocido')
                    THEN en.edition
                    ELSE Cartas.edition
                END
            FROM Cartas AS en
            WHERE en.id_api = Cartas.id_api
              AND en.idioma = 'en'
              AND Cartas.idioma != 'en'
              AND (
                  ((Cartas.type IS NULL OR Cartas.type IN ('', 'Desconocido'))
                   AND en.type IS NOT NULL AND en.type NOT IN ('', 'Desconocido'))
                  OR ((Cartas.rarity IS NULL OR Cartas.rarity IN ('', 'Desconocida', 'Desconocido'))
                      AND en.rarity IS NOT NULL AND en.rarity NOT IN ('', 'Desconocida', 'Desconocido'))
                  OR ((Cartas.stage IS NULL OR Cartas.stage IN ('', 'Ninguno', 'Desconocido'))
                      AND en.stage IS NOT NULL AND en.stage NOT IN ('', 'Ninguno', 'Desconocido'))
                  OR ((Cartas.trainer IS NULL OR Cartas.trainer IN ('', 'Ninguno', 'Desconocido'))
                      AND en.trainer IS NOT NULL AND en.trainer NOT IN ('', 'Ninguno', 'Desconocido'))
                  OR ((Cartas.especial_type IS NULL OR Cartas.especial_type IN ('', 'Normal', 'Ninguno', 'Desconocido'))
                      AND en.especial_type IS NOT NULL AND en.especial_type NOT IN ('', 'Normal', 'Ninguno', 'Desconocido'))
                  OR ((Cartas.edition IS NULL OR Cartas.edition IN ('', 'Ninguno', 'Desconocido'))
                      AND en.edition IS NOT NULL AND en.edition NOT IN ('', 'Ninguno', 'Desconocido'))
              )
            """
        )
        updates["multilingual_propagated"] = max(0, cur.rowcount)

        new_version = max(current_version, CARD_DATA_MIGRATION_VERSION)
        cur.execute(f"PRAGMA user_version = {new_version}")
        conn.commit()

        result["applied"] = True
        result["user_version"] = new_version
        result["updates"] = updates
        result["total_updates"] = sum(updates.values())
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        return result
    finally:
        conn.close()
