# Importar primero las tablas principales (sin FKs hacia otras tablas aún no definidas)
from .BetDate import BetDate
from .BetPlan import BetPlan
from .UserWallet import UserWallet

# Importar después los modelos que dependen de los anteriores
from .Bet import Bet
from .BetPrediction import BetPrediction

# Importar la tabla asociativa directamente desde BetDate si es necesario
# O definirla aquí si es independiente

__all__ = [
    "Bet",
    "BetDate", 
    "BetPrediction",
    "BetPlan",
    "UserWallet"
]