import os
import importlib
from typing import List

from sqlalchemy import create_engine, text


SQLITE_URL = os.getenv("SQLITE_URL", "sqlite:///./siempredelocal.db")
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal",
)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_sqlite_tables(sqlite_engine) -> List[str]:
    with sqlite_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        )
        return [row[0] for row in result.fetchall()]


def get_table_columns(sqlite_engine, table_name: str) -> List[str]:
    with sqlite_engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({quote_identifier(table_name)})"))
        return [row[1] for row in result.fetchall()]


def get_postgres_boolean_columns(postgres_engine, table_name: str) -> List[str]:
    with postgres_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND data_type = 'boolean'
                """
            ),
            {"table_name": table_name},
        )
        return [row[0] for row in result.fetchall()]


def coerce_to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "t", "true", "yes", "y"}:
            return True
        if normalized in {"0", "f", "false", "no", "n"}:
            return False
    return value


def ensure_schema(postgres_engine) -> None:
    # Crea el esquema desde los modelos antes de copiar datos.
    from app.db import Base
    importlib.import_module("app.models")

    Base.metadata.create_all(bind=postgres_engine)


def table_exists_in_postgres(postgres_engine, table_name: str) -> bool:
    with postgres_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        )
        return bool(result.scalar())


def copy_table(sqlite_engine, postgres_engine, table_name: str) -> int:
    columns = get_table_columns(sqlite_engine, table_name)
    if not columns:
        return 0

    quoted_table = quote_identifier(table_name)
    quoted_columns = ", ".join(quote_identifier(col) for col in columns)
    bind_columns = ", ".join(f":{col}" for col in columns)

    select_sql = text(f"SELECT {quoted_columns} FROM {quoted_table}")
    truncate_sql = text(f"TRUNCATE TABLE {quoted_table} RESTART IDENTITY CASCADE")
    insert_sql = text(
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({bind_columns})"
    )

    bool_columns = get_postgres_boolean_columns(postgres_engine, table_name)
    bool_columns_set = set(bool_columns)

    with sqlite_engine.connect() as sqlite_conn:
        rows = [dict(row) for row in sqlite_conn.execute(select_sql).mappings().all()]
        if bool_columns_set:
            for row in rows:
                for col in bool_columns_set:
                    if col in row:
                        row[col] = coerce_to_bool(row[col])

    with postgres_engine.begin() as pg_conn:
        pg_conn.execute(truncate_sql)
        if rows:
            pg_conn.execute(insert_sql, rows)

    return len(rows)


def main() -> None:
    print("Iniciando migracion SQLite -> PostgreSQL")
    print(f"SQLite: {SQLITE_URL}")
    print(f"PostgreSQL: {POSTGRES_URL}")

    sqlite_engine = create_engine(SQLITE_URL)
    postgres_engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    ensure_schema(postgres_engine)

    tables = get_sqlite_tables(sqlite_engine)
    if not tables:
        print("No se encontraron tablas en SQLite.")
        return

    # Ordenar tablas para respetar llaves foráneas típicas.
    table_order = [
        "users",
        "competitions",
        "rounds",
        "teams",
        "competition_teams",
        "matches",
        "betdates",
        "bets",
        "bet_predictions",
        "bet_date_matches",
        "user_wallets",
        "transactions",
        "bet_plans",
        "bet_plans_old",
    ]
    ordered_tables = [t for t in table_order if t in tables] + [
        t for t in tables if t not in table_order
    ]

    migrated = 0
    for table in ordered_tables:
        if not table_exists_in_postgres(postgres_engine, table):
            print(f"Omitiendo tabla '{table}': no existe en PostgreSQL.")
            continue

        count = copy_table(sqlite_engine, postgres_engine, table)
        print(f"Tabla '{table}': {count} filas migradas.")
        migrated += 1

    print(f"Migracion completada. Tablas procesadas: {migrated}")


if __name__ == "__main__":
    main()
