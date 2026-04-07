from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


# ==================== PARTIDOS DISPONIBLES ====================
class AvailableMatch(BaseModel):
    """Schema para un partido disponible"""
    id: int
    home_team: str
    away_team: str
    match_date: datetime
    competition: Optional[str] = None
    stadium: Optional[str] = None
    competition_id: Optional[int] = None
    round_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class AvailableMatchesResponse(BaseModel):
    """Respuesta para partidos disponibles"""
    matches: List[AvailableMatch]
    total_count: int
    competition_id: Optional[int] = None
    available_for_betdate: bool = Field(
        default=True,
        description="Indica si hay suficientes partidos (≥10) para crear fecha"
    )
    
    class Config:
        from_attributes = True


# ==================== CREACIÓN DE FECHA ====================
class CreateBetDateRequest(BaseModel):
    """Request para crear fecha de pronósticos"""
    name: str = Field(..., min_length=3, max_length=100, description="Nombre de la fecha")
    start_datetime: datetime = Field(description="Fecha/hora de inicio de la fecha")
    match_ids: List[int] = Field(
        ...,
        min_items=10,
        max_items=10,
        description="IDs de exactamente 10 partidos"
    )
    prize_cop: int = Field(
        default=0,
        ge=0,
        description="Premio inicial en pesos colombianos"
    )
    required_credits: int = Field(
        default=1,
        ge=1,
        description="Créditos requeridos para apostar"
    )
    
    @validator('match_ids')
    def validate_unique_match_ids(cls, v):
        """Validar que no haya IDs duplicados"""
        if len(v) != len(set(v)):
            raise ValueError("Los IDs de partidos no deben repetirse")
        return v
    
    @validator('start_datetime')
    def validate_future_datetime(cls, v):
        """Validar que sea una fecha futura"""
        if v <= datetime.now():
            raise ValueError("La fecha de inicio debe ser futura")
        return v

class BetDateCreatedResponse(BaseModel):
    """Respuesta cuando se crea una fecha exitosamente"""
    id: int
    name: str
    start_datetime: datetime
    close_datetime: datetime
    status: str
    prize_cop: int
    match_count: int
    required_credits: int
    estimated_prize_contribution: int = Field(
        description="Contribución estimada al premio si todos los cupos se llenan"
    )
    
    class Config:
        from_attributes = True


# ==================== PREDICCIÓN DE APUESTAS ====================
class PredictionRequest(BaseModel):
    """Request para una predicción individual"""
    match_id: int
    predicted_home_score: int = Field(ge=0, le=20, description="Goles del equipo local")
    predicted_away_score: int = Field(ge=0, le=20, description="Goles del equipo visitante")
    
    @validator('predicted_home_score', 'predicted_away_score')
    def validate_realistic_score(cls, v):
        """Validar que el marcador sea realista (opcional)"""
        if v > 15:
            raise ValueError("El marcador parece poco realista")
        return v

class PlaceBetRequest(BaseModel):
    """Request completo para colocar una apuesta"""
    bet_date_id: int
    predictions: List[PredictionRequest] = Field(
        ...,
        min_items=10,
        max_items=10,
        description="Lista de 10 predicciones"
    )
    
    @validator('predictions')
    def validate_unique_matches(cls, v):
        """Validar que no haya partidos duplicados"""
        match_ids = [p.match_id for p in v]
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("No puede predecir el mismo partido más de una vez")
        return v

class PlaceBetResponse(BaseModel):
    """Respuesta al colocar una apuesta exitosamente"""
    success: bool
    message: str
    bet_id: int
    credits_used: int
    credits_remaining: int
    prize_contribution: int = Field(description="Cantidad añadida al premio pool")
    total_prize: int = Field(description="Premio total actualizado")
    submitted_at: Optional[str] = None
    bet_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detalles adicionales de la apuesta"
    )
    
    class Config:
        from_attributes = True


# ==================== DETALLE DE FECHA CON PARTIDOS ====================
class MatchInBetDate(BaseModel):
    """Partido dentro de una fecha de pronósticos"""
    id: int
    home_team: str
    away_team: str
    home_team_logo: Optional[str] = None
    away_team_logo: Optional[str] = None
    match_date: datetime
    stadium: Optional[str]
    status: str
    competition: Optional[str]
    
    class Config:
        from_attributes = True

class BetDateWithMatches(BaseModel):
    """Fecha de los pronósticos con detalles completos de partidos"""
    id: int
    name: str
    start_datetime: datetime
    close_datetime: datetime
    status: str
    prize_cop: int
    accumulated_prize: int
    total_prize: int
    required_credits: int
    is_betting_open: bool
    matches: List[MatchInBetDate]
    bet_count: int = Field(description="Número de pronósticos recibidos")
    remaining_time: Optional[str] = Field(
        description="Tiempo restante para apostar (si está abierto)"
    )
    
    class Config:
        from_attributes = True


# ==================== ESTADÍSTICAS DE INTEGRACIÓN ====================
class IntegrationStats(BaseModel):
    """Estadísticas del sistema de integración"""
    total_betdates: int
    active_betdates: int
    completed_betdates: int
    total_bets: int
    total_prize_pool: int
    average_bets_per_date: float
    most_popular_competition: Optional[str]
    total_users: int = 0
    
    class Config:
        from_attributes = True

class UserBettingStatus(BaseModel):
    """Estado de los pronósticos de un usuario"""
    user_id: int
    total_bets: int
    total_points: int
    average_points: float
    wins: int = Field(description="Veces que ha ganado premio")
    total_prizes_won: int
    credits_available: int
    balance_cop: int
    active_betdates: List[int] = Field(description="IDs de fechas activas donde puede apostar")
    
    class Config:
        from_attributes = True


# ==================== VALIDACIÓN DE APUESTAS ====================
class BetValidationRequest(BaseModel):
    """Request para validar una apuesta antes de enviarla"""
    bet_date_id: int
    predictions: List[PredictionRequest]
    user_id: int

class BetValidationResponse(BaseModel):
    """Respuesta de validación de apuesta"""
    valid: bool
    message: str
    errors: List[str] = []
    warnings: List[str] = []
    estimated_points: Optional[int] = Field(
        description="Puntos estimados basados en estadísticas históricas"
    )
    required_credits: int
    user_has_credits: bool
    betdate_is_open: bool
    has_previous_bet: bool
    
    class Config:
        from_attributes = True


# ==================== FILTROS DE BÚSQUEDA ====================
class MatchFilter(BaseModel):
    """Filtros para búsqueda de partidos"""
    competition_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    team_name: Optional[str] = None
    status: Optional[str] = "Programado"
    limit: Optional[int] = Field(default=50, le=100)
    offset: Optional[int] = 0
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validar rango de fechas"""
        if 'start_date' in values and values['start_date'] and v:
            if v <= values['start_date']:
                raise ValueError("end_date debe ser posterior a start_date")
        return v


# ==================== RESPUESTAS DE ERROR ====================
class IntegrationError(BaseModel):
    """Schema para errores de integración"""
    error: str
    code: str
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None
    
    class Config:
        from_attributes = True

class ValidationError(BaseModel):
    """Schema para errores de validación"""
    field: str
    message: str
    value: Any
    
    class Config:
        from_attributes = True
