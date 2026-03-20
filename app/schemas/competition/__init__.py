# backend/app/schemas/competition/__init__.py
from .competition import (
    CompetitionBase, CompetitionCreate, CompetitionUpdate, 
    CompetitionResponse, CompetitionWithTeams, CompetitionTemplate,
    CompetitionStats
)
from .team import (
    TeamBase, TeamCreate, TeamUpdate, TeamResponse,
    CompetitionTeamCreate, CompetitionTeamResponse
)
from .match import (
    MatchBase, MatchCreate, MatchUpdate, MatchResponse
)
from .round import (
    RoundBase, RoundCreate, RoundUpdate, RoundResponse,
    RoundWithMatches
)

__all__ = [
    # Competition schemas
    "CompetitionBase",
    "CompetitionCreate", 
    "CompetitionUpdate",
    "CompetitionResponse",
    "CompetitionWithTeams",
    "CompetitionTemplate",
    "CompetitionStats",
    
    # Team schemas
    "TeamBase",
    "TeamCreate",
    "TeamUpdate",
    "TeamResponse",
    "CompetitionTeamCreate",
    "CompetitionTeamResponse",
    
    # Match schemas
    "MatchBase",
    "MatchCreate",
    "MatchUpdate",
    "MatchResponse",
    "MatchEvent",
    "MatchStatistics",
    
    # Round schemas
    "RoundBase",
    "RoundCreate",
    "RoundUpdate",
    "RoundResponse",
    "RoundWithMatches",
]