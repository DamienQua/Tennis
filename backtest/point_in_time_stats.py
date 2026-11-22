"""Calculateur chronologiquement pur (zéro look-ahead bias) des stats, H2H et ELO."""

from bisect import bisect_left
from datetime import timedelta
from typing import Dict, List, Tuple
import pandas as pd
from core.models import H2HMetrics
from utils.helpers import normalize_surface

INITIAL_ELO = 1500.0
ELO_K_FACTOR = 32.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _pct(wins: int, total: int, default: float = 50.0) -> float:
    return round((wins / total) * 100.0, 2) if total > 0 else default


class PointInTimeStats:
    """Maintient l'historique, le H2H et l'ELO glissant par surface avant chaque match."""

    def __init__(self, matches_df: pd.DataFrame) -> None:
        # player -> List[(date, surf_bucket, is_win, opponent)]
        self.player_history: Dict[str, List[Tuple[pd.Timestamp, str, bool, str]]] = {}
        self.player_dates: Dict[str, List[pd.Timestamp]] = {}
        # player -> surface -> List[(date, elo_avant_match, elo_apres_match)]
        self.elo_history: Dict[str, Dict[str, List[Tuple[pd.Timestamp, float, float]]]] = {}
        self.elo_dates: Dict[str, Dict[str, List[pd.Timestamp]]] = {}
        self._build_index(matches_df)

    def _record_elo_snapshot(
        self,
        player: str,
        surf: str,
        match_date: pd.Timestamp,
        elo_before: float,
        elo_after: float,
    ) -> None:
        self.elo_history.setdefault(player, {}).setdefault(surf, []).append(
            (match_date, elo_before, elo_after)
        )
        self.elo_dates.setdefault(player, {}).setdefault(surf, []).append(match_date)

    def _build_index(self, matches_df: pd.DataFrame) -> None:
        if matches_df.empty:
            return
        df_sorted = matches_df.copy()
        df_sorted["Date"] = pd.to_datetime(df_sorted["Date"])
        df_sorted.sort_values("Date", inplace=True)

        current_elo: Dict[Tuple[str, str], float] = {}

        for _, row in df_sorted.iterrows():
            match_date = row["Date"]
            surf_key = normalize_surface(str(row.get("Surface", "")))
            winner = str(row.get("Winner", "")).strip().lower()
            loser = str(row.get("Loser", "")).strip().lower()

            if winner:
                self.player_history.setdefault(winner, []).append(
                    (match_date, surf_key, True, loser)
                )
            if loser:
                self.player_history.setdefault(loser, []).append(
                    (match_date, surf_key, False, winner)
                )

            if winner and loser:
                elo_w = current_elo.get((winner, surf_key), INITIAL_ELO)
                elo_l = current_elo.get((loser, surf_key), INITIAL_ELO)
                exp_w = _expected_score(elo_w, elo_l)
                new_elo_w = round(elo_w + ELO_K_FACTOR * (1.0 - exp_w), 1)
                new_elo_l = round(elo_l + ELO_K_FACTOR * (0.0 - (1.0 - exp_w)), 1)

                self._record_elo_snapshot(winner, surf_key, match_date, elo_w, new_elo_w)
                self._record_elo_snapshot(loser, surf_key, match_date, elo_l, new_elo_l)
                current_elo[(winner, surf_key)] = new_elo_w
                current_elo[(loser, surf_key)] = new_elo_l

        for player, entries in self.player_history.items():
            self.player_dates[player] = [item[0] for item in entries]

    def get_player_elo_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> float:
        """Retourne l'ELO du joueur sur la surface strictement avant match_date."""
        p_clean = player_name.strip().lower()
        surf_key = normalize_surface(surface)
        dates = self.elo_dates.get(p_clean, {}).get(surf_key, [])
        if not dates:
            return INITIAL_ELO

        idx = bisect_left(dates, match_date)
        snapshots = self.elo_history[p_clean][surf_key]
        if idx < len(snapshots) and snapshots[idx][0] == match_date:
            return snapshots[idx][1]
        if idx > 0:
            return snapshots[idx - 1][2]
        return INITIAL_ELO

    def get_player_profile_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> Dict[str, float]:
        """Calcule l'ensemble des fenêtres de forme et volume strictement avant match_date."""
        defaults = {
            "win_pct_last_10": 50.0,
            "win_pct_last_50": 50.0,
            "win_pct_1y": 50.0,
            "win_pct_career": 50.0,
            "win_pct_1y_surface": 50.0,
            "win_pct_career_surface": 50.0,
            "matches_last_month": 0,
            "matches_1y": 0,
        }
        p_clean = player_name.strip().lower()
        history = self.player_history.get(p_clean, [])
        if not history:
            return defaults

        end_idx = bisect_left(self.player_dates[p_clean], match_date)
        if end_idx == 0:
            return defaults

        prior = history[:end_idx]
        surf_key = normalize_surface(surface)
        date_12m = match_date - timedelta(days=365)
        date_30d = match_date - timedelta(days=30)

        last_10 = prior[-10:]
        last_50 = prior[-50:]
        w_career = sum(1 for item in prior if item[2])
        w_12m = tot_12m = 0
        w_surf = tot_surf = 0
        w_12m_surf = tot_12m_surf = 0
        matches_30d = 0

        for m_date, m_surf, is_win, _ in prior:
            if m_date >= date_30d:
                matches_30d += 1
            if m_date >= date_12m:
                tot_12m += 1
                w_12m += int(is_win)
                if m_surf == surf_key:
                    tot_12m_surf += 1
                    w_12m_surf += int(is_win)
            if m_surf == surf_key:
                tot_surf += 1
                w_surf += int(is_win)

        return {
            "win_pct_last_10": _pct(sum(1 for item in last_10 if item[2]), len(last_10)),
            "win_pct_last_50": _pct(sum(1 for item in last_50 if item[2]), len(last_50)),
            "win_pct_1y": _pct(w_12m, tot_12m),
            "win_pct_career": _pct(w_career, len(prior)),
            "win_pct_1y_surface": _pct(w_12m_surf, tot_12m_surf),
            "win_pct_career_surface": _pct(w_surf, tot_surf),
            "matches_last_month": matches_30d,
            "matches_1y": tot_12m,
        }

    def get_player_stats_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> Tuple[float, float, int]:
        """Calcule (% victoires 12 mois, % surface, nb matchs 12 mois) avant match_date."""
        profile = self.get_player_profile_before(player_name, match_date, surface)
        return (
            float(profile["win_pct_1y"]),
            float(profile["win_pct_career_surface"]),
            int(profile["matches_1y"]),
        )

    def get_h2h_before(
        self, player_a: str, player_b: str, match_date: pd.Timestamp, surface: str
    ) -> H2HMetrics:
        """Calcule les ratios H2H strictement avant match_date."""
        pa = player_a.strip().lower()
        pb = player_b.strip().lower()
        history = self.player_history.get(pa, [])
        if not history or not pb:
            return H2HMetrics()

        end_idx = bisect_left(self.player_dates[pa], match_date)
        if end_idx == 0:
            return H2HMetrics()

        surf_key = normalize_surface(surface)
        date_12m = match_date - timedelta(days=365)
        w_all = l_all = w_1y = l_1y = w_surf = l_surf = 0

        for m_date, m_surf, is_win, opp in history[:end_idx]:
            if opp != pb:
                continue
            if is_win:
                w_all += 1
                if m_date >= date_12m:
                    w_1y += 1
                if m_surf == surf_key:
                    w_surf += 1
            else:
                l_all += 1
                if m_date >= date_12m:
                    l_1y += 1
                if m_surf == surf_key:
                    l_surf += 1

        def _pair(wa: int, wb: int) -> Tuple[float, float]:
            tot = wa + wb
            return (0.0, 0.0) if tot == 0 else (round(100.0 * wa / tot, 2), round(100.0 * wb / tot, 2))

        return H2HMetrics(
            all_time=_pair(w_all, l_all),
            last_year=_pair(w_1y, l_1y),
            surface=_pair(w_surf, l_surf),
            games=(0.0, 0.0),
        )
