"""Génération de la fiche Excel détaillée pour un match analysé."""

from datetime import datetime
import os
from typing import Any, Optional
import openpyxl
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from core.models import H2HMetrics, MatchAnalysisData, PlayerStats
from strategy.alpha_strategy import evaluate_alpha_strategy


def _safe_get(vec: Any, idx: int, default: Any = "") -> Any:
    return vec[idx] if len(vec) > idx else default


def _to_float(val: Any) -> float:
    try:
        return float(str(val).strip()) if str(val).strip() else 0.0
    except ValueError:
        return 0.0


def _to_int(val: Any) -> int:
    try:
        return int(float(str(val).strip())) if str(val).strip() else 1000
    except ValueError:
        return 1000


def _coerce_match_data(
    match_or_vec: Any, player1: Optional[str] = None, player2: Optional[str] = None
) -> MatchAnalysisData:
    if isinstance(match_or_vec, MatchAnalysisData):
        return match_or_vec
    vec = match_or_vec
    return MatchAnalysisData(
        match_url="",
        tournament=str(_safe_get(vec, 0)),
        surface=str(_safe_get(vec, 1, "Hard")),
        player_a=PlayerStats(
            name=player1 or str(_safe_get(vec, 2)),
            ranking=_to_int(_safe_get(vec, 4, 1000)),
            win_pct_last_10=_to_float(_safe_get(vec, 14)),
            win_pct_last_50=_to_float(_safe_get(vec, 15)),
            win_pct_1y=_to_float(_safe_get(vec, 16)),
            win_pct_career=_to_float(_safe_get(vec, 17)),
            win_pct_1y_surface=_to_float(_safe_get(vec, 18)),
            win_pct_career_surface=_to_float(_safe_get(vec, 19)),
            matches_last_month=_to_int(_safe_get(vec, 20, 0)),
            tournament_minutes=_to_int(_safe_get(vec, 21, 0)),
            first_serve_pct=_to_float(_safe_get(vec, 22)),
            first_serve_pts_won=_to_float(_safe_get(vec, 23)),
            break_points_saved_pct=_to_float(_safe_get(vec, 24)),
            model_odds=_to_float(_safe_get(vec, 36)),
            book_odds=_to_float(_safe_get(vec, 38)),
            elo=_to_float(_safe_get(vec, 40)),
        ),
        player_b=PlayerStats(
            name=player2 or str(_safe_get(vec, 3)),
            ranking=_to_int(_safe_get(vec, 5, 1000)),
            win_pct_last_10=_to_float(_safe_get(vec, 25)),
            win_pct_last_50=_to_float(_safe_get(vec, 26)),
            win_pct_1y=_to_float(_safe_get(vec, 27)),
            win_pct_career=_to_float(_safe_get(vec, 28)),
            win_pct_1y_surface=_to_float(_safe_get(vec, 29)),
            win_pct_career_surface=_to_float(_safe_get(vec, 30)),
            matches_last_month=_to_int(_safe_get(vec, 31, 0)),
            tournament_minutes=_to_int(_safe_get(vec, 32, 0)),
            first_serve_pct=_to_float(_safe_get(vec, 33)),
            first_serve_pts_won=_to_float(_safe_get(vec, 34)),
            break_points_saved_pct=_to_float(_safe_get(vec, 35)),
            model_odds=_to_float(_safe_get(vec, 37)),
            book_odds=_to_float(_safe_get(vec, 39)),
            elo=_to_float(_safe_get(vec, 41)),
        ),
        h2h=H2HMetrics(
            all_time=(_to_float(_safe_get(vec, 6)), _to_float(_safe_get(vec, 7))),
            last_year=(_to_float(_safe_get(vec, 8)), _to_float(_safe_get(vec, 9))),
            surface=(_to_float(_safe_get(vec, 10)), _to_float(_safe_get(vec, 11))),
            games=(_to_float(_safe_get(vec, 12)), _to_float(_safe_get(vec, 13))),
        ),
    )


def generate_match_xlsx(match_or_vec: Any) -> str:
    """Génère le classeur Excel individuel du match et retourne son chemin."""
    match = _coerce_match_data(match_or_vec)
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    xlsx_data = _prepare_match_data(match)
    for row in xlsx_data:
        sheet.append(row)

    _adjust_column_widths(sheet)
    _apply_cell_borders(sheet)
    _apply_strategy_styling(sheet)

    file_path = _save_workbook(
        workbook, now, date_str, match.tournament, match.player_a.name, match.player_b.name
    )
    print(f"Excel file '{file_path}' has been generated.")
    return file_path


def _calculate_win_percentage(odds_value: float) -> float:
    return round(90.0 / odds_value, 2) if odds_value > 0 else 0.0


def _prepare_match_data(
    match_or_vec: Any, player1: Optional[str] = None, player2: Optional[str] = None
) -> list:
    match = _coerce_match_data(match_or_vec, player1, player2)
    pa, pb, h2h = match.player_a, match.player_b, match.h2h
    alpha = evaluate_alpha_strategy(match)

    return [
        ["", pa.name, pb.name],
        ["Classement mondial", pa.ranking, pb.ranking],
        ["% Victoires carrière", pa.win_pct_career, pb.win_pct_career],
        ["% Victoires surface", pa.win_pct_career_surface, pb.win_pct_career_surface],
        ["", "", ""],
        ["Ratio V/D carrière", h2h.all_time[0], h2h.all_time[1]],
        ["Ratio V/D 1 an", h2h.last_year[0], h2h.last_year[1]],
        ["Ratio V/D surface", h2h.surface[0], h2h.surface[1]],
        ["% Sets gagnés", h2h.games[0], h2h.games[1]],
        ["", "", ""],
        ["% Victoires 1 an", pa.win_pct_1y, pb.win_pct_1y],
        ["% Victoires 1 an surface", pa.win_pct_1y_surface, pb.win_pct_1y_surface],
        ["% Victoires 50 derniers matchs", pa.win_pct_last_50, pb.win_pct_last_50],
        ["% Victoires 10 derniers matchs", pa.win_pct_last_10, pb.win_pct_last_10],
        ["Nombre matchs joués dernier mois", pa.matches_last_month, pb.matches_last_month],
        ["Durée cumulée des derniers matchs tournoi en cours", pa.tournament_minutes, pb.tournament_minutes],
        ["", "", ""],
        ["% 1er service", pa.first_serve_pct, pb.first_serve_pct],
        ["% points gagnés service", pa.first_serve_pts_won, pb.first_serve_pts_won],
        ["% balles de break sauvées", pa.break_points_saved_pct, pb.break_points_saved_pct],
        ["", "", ""],
        [
            "Pourcentage victoire",
            _calculate_win_percentage(pa.model_odds),
            _calculate_win_percentage(pb.model_odds),
        ],
        ["", "", ""],
        ["Côte estimée", pa.model_odds or "", pb.model_odds or ""],
        ["Cote Bookmaker", pa.book_odds or "", pb.book_odds or ""],
        ["Classement ELO", pa.elo or "", pb.elo or ""],
        ["", "", ""],
        ["STRATÉGIE ALPHA 5+", alpha["signal_j1"], alpha["signal_j2"]],
        ["Espérance de gain (EV)", alpha["ev_j1_str"], alpha["ev_j2_str"]],
        ["Écart ELO (ΔELO)", alpha["elo_diff_j1_str"], alpha["elo_diff_j2_str"]],
    ]


def _adjust_column_widths(sheet) -> None:
    for column in sheet.columns:
        max_len = max((len(str(cell.value or "")) for cell in column), default=0)
        col_letter = get_column_letter(column[0].column)
        sheet.column_dimensions[col_letter].width = max_len + 2


def _apply_cell_borders(sheet) -> None:
    thin = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    for row in sheet.iter_rows(
        min_row=1, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column
    ):
        for cell in row:
            cell.border = thin


def _apply_strategy_styling(sheet) -> None:
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    green_font = Font(color="006100", bold=True)
    bold_font = Font(bold=True)
    for row in sheet.iter_rows(
        min_row=1, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column
    ):
        header = str(row[0].value or "")
        if "STRATÉGIE ALPHA 5+" in header:
            row[0].font = bold_font
            for cell in row[1:]:
                if cell.value == "PARI CONSEILLÉ":
                    cell.fill = green_fill
                    cell.font = green_font


def _extract_year_from_tournament(tournament: str, default_year: int) -> int:
    for word in tournament.split():
        if word.isdigit() and len(word) == 4 and word.startswith("20"):
            return int(word)
    return default_year


def _save_workbook(
    workbook, now: datetime, date_str: str, tournament: str, player1: str, player2: str
) -> str:
    year = _extract_year_from_tournament(tournament, now.year)
    month = now.strftime("%B")
    folder_path = os.path.join("Matchs", str(year), month, tournament.replace(" ", "_"))
    os.makedirs(folder_path, exist_ok=True)

    safe_date = date_str.replace("/", "-")
    filename = f"{safe_date}_{player1.replace(' ', '_')}_vs_{player2.replace(' ', '_')}.xlsx"
    full_path = os.path.join(folder_path, filename)
    workbook.save(full_path)
    return full_path