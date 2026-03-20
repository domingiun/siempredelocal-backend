from sqlalchemy import create_engine, text

sqlite_url = "sqlite:///./siempredelocal.db"
pg_url = "postgresql+psycopg://admin:admin123@db:5432/siempredelocal"

ordered_tables = [
    "users",
    "competitions",
    "teams",
    "rounds",
    "matches",
    "competition_teams",
]

def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

s_engine = create_engine(sqlite_url)
p_engine = create_engine(pg_url)

def get_boolean_cols(table: str):
    sql = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :t
          AND data_type = 'boolean'
    """)
    with p_engine.connect() as c:
        return {r[0] for r in c.execute(sql, {"t": table}).fetchall()}

def to_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(v)

with p_engine.begin() as c:
    c.execute(text("""
        TRUNCATE TABLE competition_teams, matches, rounds, teams, competitions, users
        RESTART IDENTITY CASCADE
    """))

for table in ordered_tables:
    bool_cols = get_boolean_cols(table)

    with s_engine.connect() as sc:
        cols = [r[1] for r in sc.execute(text(f"PRAGMA table_info({q(table)})")).fetchall()]
        if not cols:
            print(f"Skip {table}: sin columnas")
            continue

        col_sql = ", ".join(q(c) for c in cols)
        rows = [dict(r) for r in sc.execute(text(f"SELECT {col_sql} FROM {q(table)}")).mappings().all()]

    if not rows:
        print(f"{table}: 0")
        continue

    for r in rows:
        for bc in bool_cols:
            if bc in r:
                r[bc] = to_bool(r[bc])

    binds = ", ".join(f":{c}" for c in cols)
    ins = text(f"INSERT INTO {q(table)} ({col_sql}) VALUES ({binds})")

    with p_engine.begin() as pc:
        pc.execute(ins, rows)

    print(f"{table}: {len(rows)}")

print("OK")
