from sqlalchemy import create_engine, text

SQLITE_URL = "sqlite:///./siempredelocal.db"
PG_URL = "postgresql+psycopg://admin:admin123@db:5432/siempredelocal"

def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

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

sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(PG_URL)

# Cargar TODOS los modelos para crear tablas faltantes en PostgreSQL
from app.db import Base
from app.models.user.user import User
from app.models.competition.competition import Competition
from app.models.competition.team import Team, CompetitionTeam
from app.models.competition.round import Round
from app.models.competition.match import Match
from app.models.bet.BetDate import BetDate, bet_date_matches
from app.models.bet.BetPlan import BetPlan
from app.models.bet.UserWallet import UserWallet
from app.models.bet.Bet import Bet
from app.models.bet.BetPrediction import BetPrediction
from app.models.bet.transaction import Transaction

Base.metadata.create_all(bind=pg_engine)

with sqlite_engine.connect() as c:
    sqlite_tables = {
        r[0] for r in c.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )).fetchall()
    }

with pg_engine.connect() as c:
    pg_tables = {
        r[0] for r in c.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )).fetchall()
    }

# Tablas con datos reales y orden por FKs
ordered = [
    "users",
    "competitions",
    "teams",
    "rounds",
    "matches",
    "competition_teams",
    "bet_plans",
    "betdates",
    "bet_date_matches",
    "user_wallets",
    "bets",
    "bet_predictions",
    "transactions",
]

to_copy = [t for t in ordered if t in sqlite_tables and t in pg_tables]
if not to_copy:
    print("No hay tablas para copiar.")
    raise SystemExit(0)

with pg_engine.begin() as c:
    c.execute(text(f"TRUNCATE TABLE {', '.join(q(t) for t in to_copy)} RESTART IDENTITY CASCADE"))

for table in to_copy:
    with pg_engine.connect() as c:
        bool_cols = {
            r[0] for r in c.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:t AND data_type='boolean'
            """), {"t": table}).fetchall()
        }

    with sqlite_engine.connect() as c:
        cols = [r[1] for r in c.execute(text(f"PRAGMA table_info({q(table)})")).fetchall()]
        if not cols:
            print(f"{table}: 0")
            continue
        col_sql = ", ".join(q(x) for x in cols)
        rows = [dict(r) for r in c.execute(text(f"SELECT {col_sql} FROM {q(table)}")).mappings().all()]

    if not rows:
        print(f"{table}: 0")
        continue

    for row in rows:
        for bc in bool_cols:
            if bc in row:
                row[bc] = to_bool(row[bc])

    with pg_engine.begin() as c:
        binds = ", ".join(f":{x}" for x in cols)
        c.execute(text(f"INSERT INTO {q(table)} ({col_sql}) VALUES ({binds})"), rows)

    print(f"{table}: {len(rows)}")

print("MIGRACION COMPLETA OK")
