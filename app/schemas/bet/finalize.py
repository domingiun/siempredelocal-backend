# backend/app/schemas/bet/finalize.py
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator


# ==================== REQUEST DE FINALIZACIÓN ====================
class FinalizeRequest(BaseModel):
    """Request para finalizar fecha de pronósticos"""
    force: bool = Field(
        default=False, 
        description="Forzar finalización aunque haya partidos pendientes"
    )
    notify_users: bool = Field(
        default=True,
        description="Enviar notificaciones a los usuarios"
    )
    distribute_prize: bool = Field(
        default=True,
        description="Distribuir premio automáticamente si hay ganador"
    )


# ==================== GANADOR ====================
class WinnerInfo(BaseModel):
    """Información del ganador"""
    user_id: int
    username: str
    points: int
    exact_scores: int = Field(description="Marcadores exactos acertados")
    correct_winners: int = Field(description="Ganadores acertados")
    bet_id: int
    submitted_at: datetime
    prize_amount: int = Field(description="Premio ganado")


# ==================== RESPUESTA DE FINALIZACIÓN ====================
class FinalizeResponse(BaseModel):
    """Respuesta de finalización de fecha"""
    success: bool = True
    message: str
    betdate_id: int
    betdate_name: str
    status: str
    qualified_for_prize: bool = Field(
        description="Si algún usuario calificó para premio (≥13 puntos)"
    )
    winner_info: Optional[WinnerInfo] = None
    winners_info: Optional[list[WinnerInfo]] = None
    prize_distributed: Optional[int] = Field(
        description="Monto distribuido como premio"
    )
    prize_accumulated: Optional[int] = Field(
        description="Monto acumulado para siguiente fecha"
    )
    next_betdate_prize: Optional[int] = Field(
        description="Premio que tendrá la próxima fecha (incluyendo acumulado)"
    )
    ranking_generated: bool
    total_participants: int = Field(description="Número total de pronósticos")
    processed_at: datetime
    
    class Config:
        from_attributes = True


# ==================== RESPUESTA DE CIERRE ====================
class CloseBetDateResponse(BaseModel):
    """Respuesta al cerrar una fecha"""
    message: str
    betdate_id: int
    betdate_name: str
    status: str
    closed_at: datetime
    can_reopen: bool = Field(
        default=False,
        description="Si se puede reabrir la fecha"
    )
    remaining_time: Optional[str] = Field(
        description="Tiempo restante antes del primer partido"
    )
    
    class Config:
        from_attributes = True


# ==================== REAPERTURA ====================
class ReopenBetDateRequest(BaseModel):
    """Request para reabrir una fecha"""
    reason: str = Field(
        ..., 
        min_length=10,
        description="Razón para reabrir la fecha"
    )
    extend_close_time: Optional[int] = Field(
        default=None,
        ge=1,
        le=24,
        description="Extender tiempo de cierre en horas"
    )

class ReopenBetDateResponse(BaseModel):
    """Respuesta de reapertura"""
    message: str
    betdate_id: int
    betdate_name: str
    status: str
    new_close_datetime: Optional[datetime] = None
    reopened_at: datetime
    reason: str


# ==================== ESTADÍSTICAS DE FINALIZACIÓN ====================
class FinalizationStats(BaseModel):
    """Estadísticas de la finalización"""
    betdate_id: int
    total_bets: int
    total_participants: int
    average_points: float
    max_points: int
    min_points: int
    users_above_13: int = Field(description="Usuarios que alcanzaron 13+ puntos")
    total_exact_scores: int
    total_correct_winners: int
    prize_pool_before: int = Field(description="Premio total antes de finalizar")
    prize_pool_after: int = Field(description="Premio total después de finalizar")
    processing_time_ms: int = Field(description="Tiempo de procesamiento en ms")
    
    class Config:
        from_attributes = True


# ==================== NOTIFICACIONES ====================
class NotificationData(BaseModel):
    """Datos para notificaciones"""
    type: str = Field(description="Tipo de notificación: winner, no_winner, closed")
    betdate_name: str
    user_id: Optional[int] = None
    points: Optional[int] = None
    prize_amount: Optional[int] = None
    ranking_position: Optional[int] = None
    timestamp: datetime


# ==================== RESUMEN DE FINALIZACIÓN ====================
class FinalizationSummary(BaseModel):
    """Resumen completo de finalización"""
    finalize_response: FinalizeResponse
    stats: FinalizationStats
    ranking_top_3: list[Dict[str, Any]]
    matches_summary: Dict[str, Any]
    
    class Config:
        from_attributes = True


# ==================== VALIDACIÓN DE FINALIZACIÓN ====================
class FinalizationValidation(BaseModel):
    """Validación antes de finalizar"""
    can_finalize: bool
    reasons: list[str] = Field(description="Razones por las que se puede/no puede finalizar")
    pending_matches: int
    pending_matches_details: list[Dict[str, Any]]
    total_bets: int
    prize_pool: int
    estimated_processing_time: str = Field(description="Tiempo estimado de procesamiento")
    recommendations: list[str] = Field(description="Recomendaciones para finalizar")
    
    class Config:
        from_attributes = True
