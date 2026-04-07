# backend/app/models/__init__.py
# Importar todos los modelos para facilitar el acceso
from .user.user import User, UserRole

# Importar modelos de competencia
from .competition.competition import Competition, CompetitionType, CompetitionFormat, CompetitionStatus
from .competition.team import Team, CompetitionTeam
from .competition.match import Match, MatchStatus
from .competition.round import Round, RoundType

# M7: Tabla de auditoría inmutable para operaciones admin
from .bet.audit_log import AuditLog

# Contenido: artículos del admin para el homepage
from .content.article import Article

__all__ = [
    # User models
    "User", "UserRole",

    # Competition models
    "Competition", "CompetitionType", "CompetitionFormat", "CompetitionStatus",
    "Team", "CompetitionTeam",
    "Match", "MatchStatus",
    "Round", "RoundType",

    # Audit
    "AuditLog",

    # Content
    "Article",
]