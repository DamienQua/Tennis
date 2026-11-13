"""Suivi cumulatif des sélections Alpha 5+ dans un classeur Excel."""

from datetime import datetime
import os
from typing import Any, Dict, List, Tuple
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

TRACKING_FILE = "Paris_Alpha_5_Plus.xlsx"
SESSION_BETS: List[Dict[str, Any]] = []

HEADERS = [
    "Date Détection",
    "Tournoi",
    "Surface",
    "Joueur 1",
    "Joueur 2",
    "Pari Conseillé",
    "Cote Bookmaker",
    "Cote Modèle",
    "Probabilité Modèle",
    "EV (%)",
    "Écart ELO",
    "Statut",
    "Résultat",
    "URL Match",
]


def get_session_bets() -> List[Dict[str, Any]]:
    """Retourne une copie des sélections de la session."""
    return list(SESSION_BETS)


def clear_session_bets() -> None:
    """Vide la liste en mémoire des paris de la session."""
    SESSION_BETS.clear()


def _create_header_style():
    fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return fill, font, align


def _init_sheet(sheet) -> None:
    sheet.title = "Sélections Alpha 5+"
    sheet.append(HEADERS)
    fill, font, align = _create_header_style()
    for col_idx in range(1, len(HEADERS) + 1):
        cell = sheet.cell(row=1, column=col_idx)
        cell.fill = fill
        cell.font = font
        cell.alignment = align
    sheet.row_dimensions[1].height = 26


def _create_or_load_wb(filepath: str):
    if os.path.exists(filepath):
        try:
            workbook = openpyxl.load_workbook(filepath)
            return workbook, workbook.active
        except (openpyxl.utils.exceptions.InvalidFileException, OSError, KeyError, ValueError):
            pass
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    _init_sheet(sheet)
    return workbook, sheet


def _row_matches(row: tuple, clean_url: str, p1_l: str, p2_l: str) -> bool:
    if len(row) < 5:
        return False
    row_url = str(row[-1] or "").strip().lower()
    if clean_url and row_url == clean_url:
        return True
    r_p1 = str(row[3] or "").strip().lower()
    r_p2 = str(row[4] or "").strip().lower()
    return r_p1 == p1_l and r_p2 == p2_l


def _is_duplicate(sheet, match_url: str, player1: str, player2: str) -> bool:
    clean_url = (match_url or "").strip().lower()
    p1_l = (player1 or "").strip().lower()
    p2_l = (player2 or "").strip().lower()
    return any(
        _row_matches(row, clean_url, p1_l, p2_l)
        for row in sheet.iter_rows(min_row=2, values_only=True)
        if row
    )


def _build_row(meta: Tuple[str, str, str, str], alpha_res: Dict[str, Any], match_url: str) -> list:
    tournament, surface, player1, player2 = meta
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    return [
        now_str,
        tournament,
        surface,
        player1,
        player2,
        alpha_res.get("selected_player", ""),
        alpha_res.get("book_odds", 0.0),
        alpha_res.get("model_odds", 0.0),
        f"{alpha_res.get('model_prob', 0.0) * 100:.1f}%",
        f"{alpha_res.get('ev_percent', 0.0):+.1f}%",
        f"{alpha_res.get('elo_diff', 0.0):+.0f}",
        "En attente",
        "",
        match_url,
    ]


def _style_appended_row(sheet, row_idx: int) -> None:
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    green_font = Font(bold=True, color="375623")
    for col_idx in range(1, len(HEADERS) + 1):
        cell = sheet.cell(row=row_idx, column=col_idx)
        cell.border = thin
        if col_idx == 6:
            cell.fill = green_fill
            cell.font = green_font
        elif col_idx in (7, 8, 9, 10, 11, 12):
            cell.alignment = Alignment(horizontal="center")


def _auto_fit_columns(sheet) -> None:
    for col in sheet.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)


def _save_safely(workbook, filepath: str) -> str:
    try:
        workbook.save(filepath)
        return filepath
    except PermissionError:
        base, ext = os.path.splitext(filepath)
        fallback = f"{base}_backup{ext}"
        workbook.save(fallback)
        return fallback


def record_alpha_selection(
    tournament: str,
    surface: str,
    player1: str,
    player2: str,
    alpha_res: Dict[str, Any],
    match_url: str = "",
    filepath: str = TRACKING_FILE,
) -> bool:
    """Enregistre une recommandation Alpha 5+ dans le classeur cumulatif."""
    if not alpha_res.get("bet_recommended"):
        return False

    SESSION_BETS.append({
        "tournament": tournament,
        "surface": surface,
        "player1": player1,
        "player2": player2,
        "selected_player": alpha_res.get("selected_player", ""),
        "book_odds": alpha_res.get("book_odds", 0.0),
        "model_odds": alpha_res.get("model_odds", 0.0),
        "model_prob": alpha_res.get("model_prob", 0.0),
        "ev_percent": alpha_res.get("ev_percent", 0.0),
        "elo_diff": alpha_res.get("elo_diff", 0.0),
        "match_url": match_url,
    })

    workbook, sheet = _create_or_load_wb(filepath)
    if _is_duplicate(sheet, match_url, player1, player2):
        return False

    row_data = _build_row((tournament, surface, player1, player2), alpha_res, match_url)
    sheet.append(row_data)
    _style_appended_row(sheet, sheet.max_row)
    _auto_fit_columns(sheet)
    saved_path = _save_safely(workbook, filepath)
    print(f"Sélection sauvegardée dans '{saved_path}' (Ligne {sheet.max_row})")
    return True