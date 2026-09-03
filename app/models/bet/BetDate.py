# backend/app/models/bet/BetDate.py 
from sqlalchemy import Column, Integer, String, DateTime, Table, ForeignKey, CheckConstraint, Enum
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime, timedelta
from app.db import Base
from app.constants.bet_constants import MAX_BETDATE_MATCHES
import enum

# Definir la tabla asociativa PRIMERO
bet_date_matches = Table(
    "bet_date_matches",
    Base.metadata,
    Column("bet_date_id", Integer, ForeignKey("betdates.id"), primary_key=True),
    Column("match_id", Integer, ForeignKey("matches.id"), primary_key=True)
)

class BetDateStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    FINISHED = "finished"
    CANCELLED = "cancelled"

class BetDate(Base):
    __tablename__ = "betdates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    close_datetime = Column(DateTime, nullable=False)  # Fecha de cierre de pronósticos
    status = Column(Enum(BetDateStatus), default=BetDateStatus.OPEN)
    prize_cop = Column(Integer, default=0)
    accumulated_prize = Column(Integer, default=0)
    required_credits = Column(Integer, default=1)
    
    # Relación con Bets
    bets = relationship(
        "Bet",
        back_populates="bet_date",
        cascade="all, delete-orphan"
    )
    
    # Relación muchos a muchos con Match
    matches = relationship(
        "Match",
        secondary=bet_date_matches,
        back_populates="bet_dates"
    )
    
    __table_args__ = (
        CheckConstraint('prize_cop >= 0', name='check_prize_non_negative'),
        CheckConstraint('accumulated_prize >= 0', name='check_accumulated_non_negative'),
        CheckConstraint('required_credits > 0', name='check_credits_positive'),
    )
    
    @validates('matches')
    def validate_matches(self, key, matches):
        """
        Validar que sean exactamente MAX_BETDATE_MATCHES partidos.
        Este método se llama cuando se asigna una NUEVA lista de matches.
        """
        # Si matches es una lista (cuando se crea/actualiza)
        if isinstance(matches, list):
            if len(matches) != MAX_BETDATE_MATCHES:
                raise ValueError(f"Una fecha de pronósticos debe tener exactamente {MAX_BETDATE_MATCHES} partidos")
        # Si matches es un objeto Match individual (cuando se añade uno por uno)
        # En este caso, no validamos aquí, validamos en el servicio
        
        return matches
    
    @hybrid_property
    def total_prize(self):
        """Premio total (prize + acumulado)"""
        return self.prize_cop + self.accumulated_prize
    
    @hybrid_property
    def is_betting_open(self):
        """Verificar si las pronósticos están abiertas"""
        now = datetime.utcnow()
        close_dt = self.close_datetime
        if close_dt is None and self.matches:
            match_dates = [m.match_date for m in self.matches if m.match_date]
            if match_dates:
                close_dt = min(match_dates) - timedelta(hours=1)
        return (
            self.status == BetDateStatus.OPEN.value and
            close_dt is not None and
            now <= close_dt
        )

    
    def add_to_prize(self, amount: int):
        """Añadir al premio acumulado"""
        self.accumulated_prize += amount
    
    def finalize(self):
        """Finalizar la fecha de pronósticos"""
        self.status = BetDateStatus.FINISHED.value
    
    def __repr__(self):
        return f"<BetDate {self.name} - {self.status}>"
