# backend/app/schemas/competition/standing.py
from pydantic import BaseModel, Field
from typing import Optional

class StandingSchema(BaseModel):
    id: int
    position: int
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    team_short_name: Optional[str] = None
    matches_played: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int

# O usa un modelo anidado
class TeamInfo(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    logo_url: Optional[str] = None

class StandingWithTeamSchema(BaseModel):
    id: int
    position: int
    matches_played: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    team: TeamInfo

    class Config:
        from_attributes = True