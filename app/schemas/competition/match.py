# backend/app/schemas/competition/match.py
from pydantic import BaseModel, Field, validator,field_validator, model_validator
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.competition.match import MatchStatus

class MatchBase(BaseModel):
    competition_id: int
    round_id: int
    home_team_id: int
    away_team_id: int
    match_date: datetime
    stadium: Optional[str] = None
    city: Optional[str] = None

class MatchCreate(MatchBase):
    status: Optional[str] = "Programado"  # Valor por defecto
    home_score: Optional[int] = Field(None, ge=0, le=50)
    away_score: Optional[int] = Field(None, ge=0, le=50)
    
    @field_validator("status", mode="before")
    @classmethod
    def validate_status_create(cls, v):
        """Validar y normalizar el estado en creación"""
        if v is None:
            return "Programado"  # Valor por defecto si es None
        
        if isinstance(v, str):
            v_lower = v.lower()
            
            status_map = {
                # Español
                "programado": "Programado",
                "en curso": "En curso",
                "finalizado": "Finalizado",
                "aplazado": "Aplazado",
                "cancelado": "Cancelado",
                
                # Inglés (por si acaso)
                "scheduled": "Programado",
                "in_progress": "En curso",
                "finished": "Finalizado",
                "postponed": "Aplazado",
                "cancelled": "Cancelado",
            }
            
            result = status_map.get(v_lower)
            
            if result is None:
                # Si no está en el mapa, usar el valor original (capitalizado)
                return v.capitalize()
            
            print(f"✅ Validando status en CREATE: '{v}' -> '{result}'")
            return result
        
        return v
    
    @model_validator(mode="before")
    @classmethod
    def validate_scores_based_on_status(cls, data):
        """Validar scores según el estado del partido"""
        if isinstance(data, dict):
            status = data.get('status')
            
            if status == "Finalizado":
                # Para partidos finalizados, los scores son obligatorios
                if data.get('home_score') is None:
                    raise ValueError("Para partidos FINALIZADOS, home_score es requerido")
                if data.get('away_score') is None:
                    raise ValueError("Para partidos FINALIZADOS, away_score es requerido")
            elif status == "Programado":
                # Para partidos programados, forzar 0 si son None
                if data.get('home_score') is None:
                    data['home_score'] = 0
                if data.get('away_score') is None:
                    data['away_score'] = 0
        
        return data
    
    @model_validator(mode="after")
    def validate_different_teams(self):
        """Validar que los equipos sean diferentes"""
        if self.home_team_id == self.away_team_id:
            raise ValueError('Los equipos no pueden ser iguales')
        return self
    
    @field_validator('home_score', 'away_score', mode='before')
    @classmethod
    def parse_scores(cls, v):
        """Convertir valores vacíos o nulos a 0"""
        if v is None or v == '':
            return 0
        return v

class MatchUpdate(BaseModel):
    home_score: Optional[int] = Field(None, ge=0, le=50)
    away_score: Optional[int] = Field(None, ge=0, le=50)
    status: Optional[str] = None
    match_date: Optional[datetime] = None
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    stadium: Optional[str] = None
    city: Optional[str] = None
    round_id: Optional[int] = None
    competition_id: Optional[int] = None
    is_postponed: Optional[bool] = None
    postponed_reason: Optional[str] = None
    postponed_date: Optional[datetime] = None
    postponed_details: Optional[str] = None
    observations: Optional[str] = None
    
    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v

        if isinstance(v, str):
            v_lower = v.lower()

            status_map = {
                "programado": "Programado",
                "scheduled": "Programado",
                "en curso": "En curso",
                "en_curso": "En curso",
                "in_progress": "En curso",
                "finalizado": "Finalizado",
                "finished": "Finalizado",
                "aplazado": "Aplazado",
                "postponed": "Aplazado",
                "cancelado": "Cancelado",
                "cancelled": "Cancelado",
            }

            result = status_map.get(v_lower)
            print(f"🔄 Validando status: '{v}' -> '{result}'")
            return result

        return v
    
    @field_validator('home_score', 'away_score', mode='before')
    @classmethod
    def convert_empty_to_zero(cls, v):
        if v is None or v == '':
            return 0
        return v
    
    class Config:
        extra = 'ignore'

class TeamSimple(BaseModel):
    id: int
    name: str
    short_name: Optional[str]
    logo_url: Optional[str]
        
    class Config:
        from_attributes = True

# Schema para ronda simplificada
class RoundSimple(BaseModel):
    id: int
    name: str
    round_number: int
    
    class Config:
        from_attributes = True

class MatchResponse(BaseModel):
    id: int
    competition_id: int
    round_id: int
    home_team_id: int
    away_team_id: int
    match_date: datetime
    stadium: Optional[str]
    city: Optional[str]
    home_score: int
    away_score: int
    status: MatchStatus
    created_at: datetime
    updated_at: datetime
    
    # Usar los schemas simplificados
    home_team: Optional[Dict[str, Any]] = None
    away_team: Optional[Dict[str, Any]] = None
    competition: Optional[Dict[str, Any]] = None
    round: Optional[Dict[str, Any]] = None  # Información de jornada
    
    class Config:
        from_attributes = True

class MatchSimpleResponse(BaseModel):
    id: int
    match_date: datetime
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    stadium: Optional[str]
    city: Optional[str]
    home_team_id: int
    away_team_id: int
    home_team_name: Optional[str]
    away_team_name: Optional[str]
    home_team_logo: Optional[str]  # ← AÑADIR
    away_team_logo: Optional[str]  # ← AÑADIR
    home_team_country: Optional[str]
    away_team_country: Optional[str]
    home_score: int
    away_score: int
    status: MatchStatus
    competition_id: Optional[int] = None  # ← AÑADIR
    round_id: Optional[int] = None  # ← AÑADIR
    round_name: Optional[str] = None  # ← AÑADIR
    round_number: Optional[int] = None  # ← AÑADIR
    round_is_completed: Optional[bool] = None  # ← AÑADIR
    competition_name: Optional[str] = None  # ← AÑADIR
    
    class Config:
        from_attributes = True
