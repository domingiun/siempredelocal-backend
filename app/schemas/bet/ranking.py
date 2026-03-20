# backend/app/schemas/bet/ranking.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ==================== ENTRY DE RANKING ====================
class RankingEntryBase(BaseModel):
    """Base para entrada de ranking"""
    user_id: int
    points: int = 0
    exact_scores: int = 0
    correct_winners: int = 0
    position: int = 1

class RankingEntryCreate(RankingEntryBase):
    """Para crear entrada de ranking"""
    bet_id: int
    username: str = "Usuario"

class RankingEntryRead(RankingEntryBase):
    """Para leer entrada de ranking"""
    id: Optional[int] = None
    bet_id: int
    username: str
    submitted_at: datetime
    
    class Config:
        from_attributes = True


# ==================== RANKING COMPLETO ====================
class RankingBase(BaseModel):
    """Base para ranking completo"""
    betdate_id: int
    betdate_name: str
    total_prize: int = 0
    prize_paid_total: int = 0
    qualifies_for_prize: bool = False

class RankingCreate(RankingBase):
    """Para crear ranking"""
    ranking_entries: List[RankingEntryCreate] = []

class RankingRead(RankingBase):
    """Para leer ranking completo"""
    id: Optional[int] = None
    status: str
    winner_required_points: int = Field(default=13, description="Puntos mínimos para ganar premio")
    ranking: List[RankingEntryRead]
    generated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== RESPONSE DE RANKING ====================
class RankingResponse(BaseModel):
    """Respuesta estándar para endpoints de ranking"""
    success: bool = True
    message: str = ""
    data: RankingRead
    
    class Config:
        from_attributes = True


# ==================== PREVIEW DE RANKING ====================
class RankingPreviewEntry(BaseModel):
    """Entrada para preview de ranking"""
    user_id: int
    username: str
    current_points: int = 0
    bet_id: int
    submitted_at: Optional[str] = None
    is_finalized: bool = False

class RankingPreviewResponse(BaseModel):
    """Respuesta para preview de ranking"""
    betdate_id: int
    betdate_name: str
    status: str
    total_prize: int
    pending_matches: int = 0
    total_bets: int = 0
    ranking_preview: List[RankingPreviewEntry]
    
    class Config:
        from_attributes = True


# ==================== FINALIZACIÓN ====================
class FinalizeRequest(BaseModel):
    """Request para finalizar fecha"""
    force: bool = Field(default=False, description="Forzar finalización aunque haya partidos pendientes")

class FinalizeResponse(BaseModel):
    """Respuesta de finalización"""
    message: str
    betdate_id: int
    betdate_name: str
    winner_user_id: Optional[int] = None
    winner_username: Optional[str] = None
    winner_points: Optional[int] = None
    prize_distributed: Optional[int] = None
    prize_accumulated: Optional[int] = None
    ranking_generated: bool
    qualified_for_prize: bool
    next_betdate_prize: Optional[int] = Field(
        default=None, 
        description="Premio que tendrá la próxima fecha (si se acumuló)"
    )
    
    class Config:
        from_attributes = True


# ==================== ESTADÍSTICAS ====================
class RankingStats(BaseModel):
    """Estadísticas de ranking"""
    total_users: int
    average_points: float
    max_points: int
    min_points: int
    users_above_13: int = Field(description="Usuarios que califican para premio")
    total_exact_scores: int
    total_correct_winners: int
    most_common_score: Optional[str] = Field(description="Marcador más común predicho")
    
    class Config:
        from_attributes = True

class DetailedRankingResponse(BaseModel):
    """Respuesta detallada con estadísticas"""
    ranking: RankingRead
    stats: RankingStats
    betdate_info: dict
    
    class Config:
        from_attributes = True
