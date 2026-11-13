"""Évaluateur de stratégies de paris pour le backtesting (Confluence & Alpha 5+)."""

from typing import Any, Dict, List, Optional
from strategy.alpha_strategy import evaluate_alpha_strategy


class BetRecord:
    """Enregistre un pari simulé, sa mise, son issue et son P&L."""

    def __init__(
        self,
        match_name: str,
        tournament: str,
        bet_on: str,
        model_odds: float = 0.0,
        market_odds: float = 0.0,
        won: bool = False,
        stake: float = 1.0,
    ) -> None:
        self.match_name = match_name
        self.tournament = tournament
        self.bet_on = bet_on
        self.model_odds = model_odds
        self.market_odds = market_odds
        self.won = won
        self.stake = stake

    @property
    def pnl(self) -> float:
        """Calcule le gain ou la perte nette du pari."""
        if self.won:
            return round(self.stake * (self.market_odds - 1.0), 2)
        return -round(self.stake, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Sérialise l'enregistrement en dictionnaire."""
        return {
            "match": self.match_name,
            "tournament": self.tournament,
            "bet_on": self.bet_on,
            "model_odds": self.model_odds,
            "market_odds": self.market_odds,
            "won": self.won,
            "stake": self.stake,
            "pnl": self.pnl,
        }


def _to_float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_confluence_metrics(args: tuple) -> tuple:
    return tuple(_to_float(args[i]) for i in range(8))


class StrategyEvaluator:
    """Évalue les signaux de paris et calcule les métriques financières globales."""

    def __init__(self, value_edge_threshold: float = 0.05, stake_size: float = 1.0) -> None:
        self.value_edge_threshold = value_edge_threshold
        self.stake_size = stake_size
        self.bets: List[BetRecord] = []

    @staticmethod
    def _is_ok_j1(*args) -> bool:
        ej1, ej2, bj1, bj2, el1, el2, surf_1, surf_2 = _parse_confluence_metrics(args)
        return ej1 < ej2 and bj1 < bj2 and el1 > el2 and surf_1 > surf_2 and bj1 > ej1

    @staticmethod
    def _is_ok_j2(*args) -> bool:
        ej1, ej2, bj1, bj2, el1, el2, surf_1, surf_2 = _parse_confluence_metrics(args)
        return ej1 > ej2 and bj1 > bj2 and el1 < el2 and surf_1 < surf_2 and bj2 > ej2

    @classmethod
    def evaluate_confluence(cls, *args) -> str:
        """Évalue le filtre de confluence historique."""
        if cls._is_ok_j1(*args):
            return "OK J1"
        if cls._is_ok_j2(*args):
            return "OK J2"
        return "PAS OK"

    @classmethod
    def evaluate_alpha_5_plus(cls, *args, **kwargs) -> Dict[str, Any]:
        """Délègue directement à la stratégie de production Alpha 5+."""
        return evaluate_alpha_strategy(*args, **kwargs)

    @classmethod
    def evaluate_optimized_confluence(cls, *args, surface: str = "Clay") -> str:
        """Évalue la confluence avec seuils ELO et cotes spécifiques par surface."""
        s_clean = surface.lower()
        if "grass" in s_clean:
            return "PAS OK"

        raw = cls.evaluate_confluence(*args[:8])
        if raw == "PAS OK":
            return "PAS OK"

        elo_diff = abs(_to_float(args[4]) - _to_float(args[5]))
        bet_odds = _to_float(args[2]) if raw == "OK J1" else _to_float(args[3])

        if "clay" in s_clean:
            return raw if elo_diff >= 50.0 else "PAS OK"
        if "hard" in s_clean:
            return raw if (elo_diff >= 120.0 and bet_odds <= 1.50) else "PAS OK"
        return "PAS OK"

    def evaluate_match_confluence(self, *args) -> Optional[BetRecord]:
        """Enregistre un pari si le filtre de confluence est validé."""
        player_a, player_b, tournament = args[0], args[1], args[2]
        excel_j1, excel_j2, book_j1, book_j2 = args[3], args[4], args[5], args[6]
        winner = args[11]

        status = self.evaluate_confluence(*args[3:11])
        if status == "OK J1":
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_a,
                excel_j1, book_j1, player_a == winner, self.stake_size,
            )
            self.bets.append(record)
            return record
        if status == "OK J2":
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_b,
                excel_j2, book_j2, player_b == winner, self.stake_size,
            )
            self.bets.append(record)
            return record
        return None

    def evaluate_match_alpha_5_plus(
        self,
        player_a: str,
        player_b: str,
        tournament: str,
        model_a: float,
        model_b: float,
        book_a: float,
        book_b: float,
        elo_a: float,
        elo_b: float,
        winner: str,
        use_kelly: bool = True,
    ) -> Optional[BetRecord]:
        """Évalue et enregistre un pari selon la stratégie de production Alpha 5+."""
        res = evaluate_alpha_strategy(
            model_1=model_a,
            model_2=model_b,
            book_1=book_a,
            book_2=book_b,
            elo_1=elo_a,
            elo_2=elo_b,
            player_1=player_a,
            player_2=player_b,
        )
        if not res.get("bet_recommended"):
            return None

        selected = res["selected_player"]
        stake = res["kelly_stake_pct"] if use_kelly else self.stake_size
        record = BetRecord(
            match_name=f"{player_a} vs {player_b}",
            tournament=tournament,
            bet_on=selected,
            model_odds=res["model_odds"],
            market_odds=res["book_odds"],
            won=(selected == winner),
            stake=stake,
        )
        self.bets.append(record)
        return record

    def get_summary(self) -> Dict[str, Any]:
        """Calcule le bilan financier complet (clé cohérente même à 0 pari)."""
        total_bets = len(self.bets)
        if total_bets == 0:
            return {
                "total_bets": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_staked": 0.0,
                "total_pnl": 0.0,
                "roi": 0.0,
                "roi_percent": 0.0,
            }

        wins = sum(1 for bet_item in self.bets if bet_item.won)
        total_staked = round(sum(bet_item.stake for bet_item in self.bets), 2)
        total_pnl = round(sum(bet_item.pnl for bet_item in self.bets), 2)
        roi = round((total_pnl / total_staked) * 100, 2) if total_staked > 0 else 0.0
        win_rate = round((wins / total_bets) * 100, 2)

        return {
            "total_bets": total_bets,
            "wins": wins,
            "losses": total_bets - wins,
            "win_rate": win_rate,
            "total_staked": total_staked,
            "total_pnl": total_pnl,
            "roi": roi,
            "roi_percent": roi,
        }