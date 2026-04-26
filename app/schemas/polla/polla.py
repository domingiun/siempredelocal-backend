# backend/app/schemas/polla/polla.py
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ── Admin: crear/editar Polla ──────────────────────────────────────────────

class PollaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    edition_year: int = 2026
    entry_credits: int = 8
    guaranteed_prize_cop: int = 1_000_000
    prize_per_user_cop: int = 32_000
    threshold_users: int = 33
    platform_fee_pct: int = 20
    registration_open_at: Optional[datetime] = None
    registration_close_at: Optional[datetime] = None


class PollaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    entry_credits: Optional[int] = None
    guaranteed_prize_cop: Optional[int] = None
    prize_per_user_cop: Optional[int] = None
    threshold_users: Optional[int] = None
    platform_fee_pct: Optional[int] = None
    registration_open_at: Optional[datetime] = None
    registration_close_at: Optional[datetime] = None


# ── Admin: agregar partido a la polla ─────────────────────────────────────

class PollaMatchCreate(BaseModel):
    match_id: int
    phase: str          # "groups", "r32", "r16", "qf", "sf", "third", "final"
    match_order: int = 0

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        valid = {"groups", "r32", "r16", "qf", "sf", "third", "final"}
        if v not in valid:
            raise ValueError(f"Fase inválida. Opciones: {valid}")
        return v


# ── Admin: puntuar manualmente un PollaMatch ──────────────────────────────

class PollaMatchScore(BaseModel):
    actual_result: Optional[str] = None        # "L"/"E"/"V" para grupos
    actual_winner_id: Optional[int] = None     # FK team para eliminatorias


# ── Usuario: inscribirse ───────────────────────────────────────────────────

class PollaJoinRequest(BaseModel):
    polla_id: int


# ── Usuario: enviar predicción ─────────────────────────────────────────────

class PollaPredictionSubmit(BaseModel):
    polla_match_id: int
    prediction_result: Optional[str] = None    # "L"/"E"/"V" (grupos)
    predicted_winner_id: Optional[int] = None  # team_id (eliminatorias)

    @field_validator("prediction_result")
    @classmethod
    def validate_result(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"L", "E", "V"}:
            raise ValueError("prediction_result debe ser 'L', 'E' o 'V'")
        return v


# ── Responses ─────────────────────────────────────────────────────────────

class PollaMatchResponse(BaseModel):
    id: int
    polla_id: int
    match_id: Optional[int]
    phase: str
    match_order: int
    actual_result: Optional[str]
    actual_winner_id: Optional[int]
    actual_winner_name: Optional[str] = None
    is_scored: bool
    close_at: Optional[datetime]
    # Info del partido vinculado
    match_date: Optional[datetime] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    home_logo: Optional[str] = None
    away_logo: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    match_status: Optional[str] = None

    model_config = {"from_attributes": True}


class PollaPredictionResponse(BaseModel):
    id: int
    polla_match_id: int
    prediction_result: Optional[str]
    predicted_winner_id: Optional[int]
    predicted_winner_name: Optional[str] = None
    points: int
    is_correct: Optional[bool]
    submitted_at: datetime

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    avatar_url: Optional[str]
    base_points: int
    bonus_points: int
    total_points: int
    prize_won_cop: int


class PollaResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    edition_year: int
    entry_credits: int
    guaranteed_prize_cop: int
    prize_per_user_cop: int
    threshold_users: int
    platform_fee_pct: int
    registration_open_at: Optional[datetime]
    registration_close_at: Optional[datetime]
    created_at: datetime
    participant_count: int
    current_prize_cop: int
    leaderboard: list[LeaderboardEntry] = []

    model_config = {"from_attributes": True}


class MyPollaStatus(BaseModel):
    is_participant: bool
    participant_id: Optional[int]
    rank: Optional[int]
    base_points: int
    bonus_points: int
    total_points: int
    predictions_submitted: int
    predictions_pending: int   # matches open for prediction not yet submitted
