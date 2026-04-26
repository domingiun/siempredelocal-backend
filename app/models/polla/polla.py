# backend/app/models/polla/polla.py
"""
Modelos para la Polla Mundial 2026.

Flujo:
  1. Admin crea una Polla (edition_year=2026, status=upcoming).
  2. Admin agrega PollaMatches (vinculados a Match existentes) con su fase.
  3. Admin abre la Polla (status=open) → usuarios pueden inscribirse pagando 8 créditos.
  4. Predicciones se van habilitando partido a partido (cierra 1h antes del kickoff).
  5. Al finalizar cada partido → se puntúa automáticamente vía sync_scores.
  6. Al finalizar cada fase → se calculan bonificaciones (racha + más aciertos).
  7. Al terminar el torneo → se distribuye el premio.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from app.db import Base


class PollaStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class PollaPhase(str, enum.Enum):
    GROUPS = "groups"
    R32 = "r32"      # Ronda de 32 (16 partidos)
    R16 = "r16"      # Octavos (8 partidos)
    QF = "qf"        # Cuartos (4 partidos)
    SF = "sf"        # Semifinales (2 partidos)
    THIRD = "third"  # Tercer puesto (1 partido)
    FINAL = "final"  # Final (1 partido)


# Puntos base por fase
PHASE_POINTS: dict[str, int] = {
    "groups": 1,
    "r32": 2,
    "r16": 2,
    "qf": 3,
    "sf": 3,
    "third": 3,
    "final": 3,
}

# Bonificación "más aciertos" por fase (1ª fase=+5, 2ª fase=+5, 3ª en adelante=+3)
PHASE_BONUS_MOST_CORRECT: dict[str, int] = {
    "groups": 5,
    "r32": 5,
    "r16": 3,
    "qf": 3,
    "sf": 3,
    "third": 3,
    "final": 3,
}

# Orden cronológico de las fases
PHASE_ORDER: list[str] = ["groups", "r32", "r16", "qf", "sf", "third", "final"]


class Polla(Base):
    __tablename__ = "pollas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default=PollaStatus.UPCOMING.value, nullable=False)
    edition_year = Column(Integer, nullable=False, default=2026)

    # Economía
    entry_credits = Column(Integer, default=8, nullable=False)
    guaranteed_prize_cop = Column(Integer, default=1_000_000, nullable=False)
    prize_per_user_cop = Column(Integer, default=32_000, nullable=False)
    threshold_users = Column(Integer, default=33, nullable=False)
    platform_fee_pct = Column(Integer, default=20, nullable=False)

    # Ventana de inscripción (abrir/cerrar registro)
    registration_open_at = Column(DateTime, nullable=True)
    registration_close_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    participants = relationship(
        "PollaParticipant", back_populates="polla", cascade="all, delete-orphan"
    )
    polla_matches = relationship(
        "PollaMatch", back_populates="polla", cascade="all, delete-orphan",
        order_by="PollaMatch.id",
    )

    __table_args__ = (
        CheckConstraint("entry_credits > 0", name="ck_polla_credits_positive"),
        CheckConstraint("guaranteed_prize_cop >= 0", name="ck_polla_prize_non_negative"),
        CheckConstraint("platform_fee_pct between 0 and 100", name="ck_polla_fee_pct"),
    )

    @property
    def current_prize_cop(self) -> int:
        """Premio actual basado en participantes inscritos."""
        n = len(self.participants)
        natural = n * self.prize_per_user_cop
        return max(self.guaranteed_prize_cop, natural)

    def __repr__(self):
        return f"<Polla {self.name} {self.edition_year} - {self.status}>"


class PollaMatch(Base):
    """
    Un partido del mundial dentro de la polla.
    Vinculado a un Match existente; el admin asigna la fase manualmente.
    """
    __tablename__ = "polla_matches"

    id = Column(Integer, primary_key=True, index=True)
    polla_id = Column(Integer, ForeignKey("pollas.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)

    phase = Column(String, nullable=False)       # PollaPhase value
    match_order = Column(Integer, default=0)     # orden dentro de la fase

    # Resultado real (se llena al finalizar el partido)
    # Para grupos: "L" (local gana), "E" (empate), "V" (visitante gana)
    # Para eliminatorias: NULL (usamos actual_winner_id)
    actual_result = Column(String, nullable=True)
    actual_winner_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    is_scored = Column(Boolean, default=False, nullable=False)
    close_at = Column(DateTime, nullable=True)   # 1h antes del partido

    polla = relationship("Polla", back_populates="polla_matches")
    match = relationship("Match")
    actual_winner = relationship("Team", foreign_keys=[actual_winner_id])
    predictions = relationship(
        "PollaPrediction", back_populates="polla_match", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("polla_id", "match_id", name="uq_polla_match"),
    )

    def __repr__(self):
        return f"<PollaMatch polla={self.polla_id} match={self.match_id} phase={self.phase}>"


class PollaParticipant(Base):
    """Un usuario inscrito en la polla."""
    __tablename__ = "polla_participants"

    id = Column(Integer, primary_key=True, index=True)
    polla_id = Column(Integer, ForeignKey("pollas.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    base_points = Column(Integer, default=0, nullable=False)
    bonus_points = Column(Integer, default=0, nullable=False)
    total_points = Column(Integer, default=0, nullable=False)
    rank = Column(Integer, nullable=True)

    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prize_won_cop = Column(Integer, default=0, nullable=False)
    prize_distributed = Column(Boolean, default=False, nullable=False)

    polla = relationship("Polla", back_populates="participants")
    user = relationship("User")
    predictions = relationship(
        "PollaPrediction", back_populates="participant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("polla_id", "user_id", name="uq_polla_participant"),
    )

    def __repr__(self):
        return f"<PollaParticipant polla={self.polla_id} user={self.user_id} pts={self.total_points}>"


class PollaPrediction(Base):
    """Predicción de un participante para un partido de la polla."""
    __tablename__ = "polla_predictions"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("polla_participants.id"), nullable=False)
    polla_match_id = Column(Integer, ForeignKey("polla_matches.id"), nullable=False)

    # Para grupos
    prediction_result = Column(String, nullable=True)    # "L", "E", "V"
    # Para eliminatorias
    predicted_winner_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    points = Column(Integer, default=0, nullable=False)
    is_correct = Column(Boolean, nullable=True)          # NULL = aún no puntuado

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow, nullable=True)

    participant = relationship("PollaParticipant", back_populates="predictions")
    polla_match = relationship("PollaMatch", back_populates="predictions")
    predicted_winner = relationship("Team", foreign_keys=[predicted_winner_id])

    __table_args__ = (
        UniqueConstraint("participant_id", "polla_match_id", name="uq_polla_prediction"),
    )

    def __repr__(self):
        return f"<PollaPrediction participant={self.participant_id} match={self.polla_match_id}>"
