# backend/app/services/bet_service.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

class BetService:

    @staticmethod
    def update_betdate_status(session: Session, betdate) -> bool:
        """
        Actualizar el estado de la fecha de pronósticos segun:
        - Si TODOS los partidos estan finalizados -> finished
        - Si ALGÚN partido ya pasó la fecha actual -> closed
        """
        from app.models.bet.BetDate import BetDateStatus

        if not betdate:
            return False

        # No modificar estados terminales
        if betdate.status in [BetDateStatus.FINISHED.value, BetDateStatus.CANCELLED.value]:
            return False

        matches = betdate.matches or []
        if not matches:
            return False

        match_dates = [m.match_date for m in matches if m.match_date]
        if not match_dates:
            return False

        earliest_match = min(match_dates)
        computed_close = earliest_match - timedelta(hours=1)
        changed = False
        if not betdate.close_datetime or betdate.close_datetime != computed_close:
            betdate.close_datetime = computed_close
            changed = True

        def normalize(status: str) -> str:
            return str(status).strip().lower() if status else ""

        now = datetime.utcnow()
        all_finished = all(normalize(m.status) in ["finalizado", "finished"] for m in matches)

        if all_finished and betdate.status != BetDateStatus.FINISHED.value:
            try:
                from app.routes.bet.finalize import finalize_betdate
                from app.schemas.bet.finalize import FinalizeRequest
                finalize_betdate(
                    betdate.id,
                    request=FinalizeRequest(),
                    session=session
                )
            except Exception:
                # Si falla la finalización automática, no cambiar a finished aquí
                return False
            return True

        if betdate.status == BetDateStatus.OPEN.value:
            has_past_match = any(
                m.match_date and m.match_date < now for m in matches
            )
            close_by_time = betdate.close_datetime and now > betdate.close_datetime
            if has_past_match or close_by_time:
                betdate.status = BetDateStatus.CLOSED.value
                return True
        return changed
    
    @staticmethod
    def get_available_matches_for_betdate(
        session: Session, 
        competition_id: Optional[int] = None
    ) -> List:
        """
        Obtener partidos disponibles para crear fecha de pronósticos
        """
        from app.models.competition.match import Match, MatchStatus
        from app.models.bet.BetDate import BetDate
        
        # Obtener todos los partidos programados
        query = session.query(Match).filter(
            Match.status == MatchStatus.SCHEDULED.value
        )
        
        if competition_id:
            query = query.filter(Match.competition_id == competition_id)
        
        # Excluir partidos que ya están en fechas de pronósticos abiertas
        active_betdates = session.query(BetDate).filter(
            BetDate.status.in_(["open", "closed"])
        ).all()
        
        active_match_ids = []
        for betdate in active_betdates:
            for match in betdate.matches:
                active_match_ids.append(match.id)
        
        if active_match_ids:
            query = query.filter(~Match.id.in_(active_match_ids))
        
        # Ordenar por fecha
        query = query.order_by(Match.match_date)
        
        return query.all()
    
    @staticmethod
    def create_betdate_with_matches(
        session: Session,
        name: str,
        start_datetime: datetime,
        match_ids: List[int],
        prize_cop: int = 0
    ):
        """
        Crear una nueva fecha de pronósticos con 10 partidos
        """
        from app.models.competition.match import Match, MatchStatus
        from app.models.bet.BetDate import BetDate
        
        if len(match_ids) != 10:
            raise ValueError("Debe seleccionar exactamente 10 partidos")
        
        # Verificar que todos los partidos existan y estén programados
        matches = session.query(Match).filter(Match.id.in_(match_ids)).all()
        if len(matches) != 10:
            raise ValueError("Algunos partidos no existen")
        
        # Verificar que todos estén programados
        for match in matches:
            if match.status != MatchStatus.SCHEDULED.value:
                raise ValueError(f"El partido {match.id} no está programado")
        
        # Calcular fecha de cierre (1 hora antes del primer partido)
        earliest_match = min(matches, key=lambda m: m.match_date)
        close_datetime = earliest_match.match_date - timedelta(hours=1)
        
        # Crear BetDate
        betdate = BetDate(
            name=name,
            start_datetime=start_datetime,
            close_datetime=close_datetime,
            prize_cop=prize_cop,
            required_credits=1
        )
        
        session.add(betdate)
        session.flush()  # Para obtener el ID
        
        # Asignar partidos
        betdate.matches = matches
        
        session.commit()
        
        return betdate
    
    @staticmethod
    def place_bet(
        session: Session,
        user_id: int,
        bet_date_id: int,
        predictions: List[Dict]
    ):
        """
        Colocar una apuesta con validaciones
        """
        from app.models.bet.BetDate import BetDate
        from app.models.bet.Bet import Bet
        from app.models.bet.BetPrediction import BetPrediction
        from app.models.bet.UserWallet import UserWallet
        
        # Verificar que la fecha de pronósticos esté abierta
        betdate = session.query(BetDate).get(bet_date_id)
        if not betdate:
            raise ValueError("Fecha de pronósticos no encontrada")
        
        if not betdate.is_betting_open:
            raise ValueError("Los pronósticos para esta fecha están cerrados")
        
        # Verificar que el usuario tenga suficientes créditos
        wallet = session.query(UserWallet).filter_by(user_id=user_id).first()
        if not wallet or wallet.credits < betdate.required_credits:
            raise ValueError("Créditos insuficientes")
        
        # Verificar que no haya apostado ya en esta fecha
        existing_bet = session.query(Bet).filter_by(
            user_id=user_id,
            bet_date_id=bet_date_id
        ).first()
        
        if existing_bet:
            raise ValueError("Ya has apostado en esta fecha")
        
        # Verificar que sean 10 predicciones
        if len(predictions) != 10:
            raise ValueError("Debe hacer 10 predicciones")
        
        # Verificar que todos los partidos sean de esta fecha
        betdate_match_ids = [m.id for m in betdate.matches]
        for pred in predictions:
            if pred["match_id"] not in betdate_match_ids:
                raise ValueError(f"El partido {pred['match_id']} no pertenece a esta fecha")
        
        # Crear la apuesta
        bet = Bet(
            user_id=user_id,
            bet_date_id=bet_date_id,
            is_finalized=False
        )
        
        session.add(bet)
        session.flush()  # Para obtener el ID
        
        # Crear predicciones
        for pred in predictions:
            bet_pred = BetPrediction(
                bet_id=bet.id,
                match_id=pred["match_id"],
                predicted_home_score=pred["predicted_home_score"],
                predicted_away_score=pred["predicted_away_score"]
            )
            session.add(bet_pred)
        
        # Descontar créditos
        wallet.credits -= betdate.required_credits
        
        # Añadir al premio (1950 por crédito)
        betdate.prize_cop += 1950 * betdate.required_credits
        
        session.commit()
        
        return bet
    
    @staticmethod
    def calculate_betdate_results(session: Session, bet_date_id: int) -> Dict:
        """
        Calcular resultados de una fecha de los pronósticos
        """
        from app.models.bet.BetDate import BetDate
        from app.models.bet.Bet import Bet
        from app.models.bet.BetPrediction import BetPrediction
        from app.models.competition.match import MatchStatus
        
        betdate = session.query(BetDate).get(bet_date_id)
        if not betdate:
            raise ValueError("Fecha de pronósticos no encontrada")
        
        # Verificar que todos los partidos hayan finalizado
        for match in betdate.matches:
            if match.status != MatchStatus.FINISHED.value:
                raise ValueError(f"El partido {match.id} no ha finalizado")
        
        # Calcular puntos para todas los pronósticos
        bets = session.query(Bet).filter_by(bet_date_id=bet_date_id).all()
        
        for bet in bets:
            total_points = 0
            for prediction in bet.predictions:
                points = prediction.calculate_match_points()
                prediction.points = points
                total_points += points
            
            bet.points = total_points
            bet.is_finalized = True
        
        session.commit()
        
        # Ordenar por puntos (descendente) y tiempo (ascendente)
        sorted_bets = sorted(
            bets,
            key=lambda b: (-b.points, b.submitted_at)
        )
        
        # Asignar posiciones
        for i, bet in enumerate(sorted_bets, 1):
            bet.rank = i
        
        session.commit()
        
        # Verificar si hay ganador (13 puntos o más)
        winner = None
        if sorted_bets and sorted_bets[0].points >= 13:
            winner = sorted_bets[0]
        
        return {
            "betdate": betdate,
            "ranking": [b.get_ranking_info() for b in sorted_bets],
            "winner": winner.get_ranking_info() if winner else None,
            "total_prize": betdate.total_prize,
            "qualifies_for_prize": winner is not None
        }
