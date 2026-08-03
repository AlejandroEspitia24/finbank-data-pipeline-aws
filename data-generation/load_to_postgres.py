"""Carga los datos sintéticos generados (output/*.parquet) a Amazon RDS PostgreSQL.

Las credenciales de conexión NUNCA se escriben en este archivo: se leen desde
variables de entorno (ver .env.example). Esto es un requisito explícito de la
prueba técnica ("ningún valor de credencial debe aparecer directamente en el
código").

Uso:
    python load_to_postgres.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text

from logging_config import setup_logging

logger = logging.getLogger(__name__)

# Las tablas padre se cargan primero para respetar las FK definidas en schema.sql.
TABLES_IN_LOAD_ORDER: list[str] = [
    "tb_productos_cat",
    "tb_sucursales_red",
    "tb_clientes_core",
    "tb_mov_financieros",
    "tb_obligaciones",
    "tb_comisiones_log",
]

OUTPUT_DIR = Path("output")
SCHEMA_FILE = Path("schema.sql")


def get_engine() -> Engine:
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)


def apply_schema(engine: Engine) -> None:
    ddl = SCHEMA_FILE.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in ddl.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    logger.info("Esquema aplicado (%s)", SCHEMA_FILE)


def load_tables(engine: Engine) -> None:
    for table in TABLES_IN_LOAD_ORDER:
        path = OUTPUT_DIR / f"{table}.parquet"
        df = pd.read_parquet(path)
        df.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=5000)
        logger.info("  Cargada %-20s %10s filas", table, f"{len(df):,}")


def verify_counts(engine: Engine) -> None:
    logger.info("Verificación de carga (SELECT COUNT(*)):")
    with engine.connect() as conn:
        for table in TABLES_IN_LOAD_ORDER:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            logger.info("  %-20s %10s filas", table, f"{count:,}")


def main() -> int:
    load_dotenv()
    setup_logging(Path("output") / "load.log")

    engine = get_engine()
    try:
        apply_schema(engine)
        load_tables(engine)
        verify_counts(engine)
        return 0
    except Exception:
        logger.exception("Fallo no controlado durante la carga a PostgreSQL")
        return 1
    finally:
        # Libera las conexiones del pool explícitamente: en un script de vida
        # corta como este no es crítico, pero es el hábito correcto y evita
        # conexiones colgadas si el script se reutiliza como módulo.
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
