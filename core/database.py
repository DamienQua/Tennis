"""Persistance SQLite des matchs, paris Alpha 5+ et suivi automatique du ROI."""

from datetime import datetime
import os
import sqlite3
from typing import Any, Dict, List, Set
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from core.models import MatchAnalysisData

DB_FILE = "tennis_ai.db"
LEGACY_REVIEWED_FILE = "Reviewed_Matchs.txt"
TRACKING_FILE = "Paris_Alpha_5_Plus.xlsx"

EXCEL_HEADERS = [
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
    "Mise Kelly (%)",
    "Statut",
    "Résultat",
    "Profit (u)",
    "URL Match",
]


def _to_float(val: str) -> float:
    """Convertit une chaîne numérique (éventuellement vide) en float."""
    cleaned = val.strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


class TennisDatabase:
    """Gère le stockage SQLite (mode WAL) et l'export Excel cumulatif."""

    def __init__(self, db_path: str = DB_FILE) -> None:
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS matches (
                    match_url TEXT PRIMARY KEY,
                    analyzed_at TEXT NOT NULL,
                    tournament TEXT,
                    surface TEXT,
                    player_a TEXT,
                    player_b TEXT,
                    model_odds_a REAL,
                    model_odds_b REAL,
                    book_odds_a REAL,
                    book_odds_b REAL,
                    elo_a REAL,
                    elo_b REAL,
                    confidence_index REAL,
                    summary_line TEXT
                );

                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_url TEXT UNIQUE NOT NULL,
                    detected_at TEXT NOT NULL,
                    tournament TEXT,
                    surface TEXT,
                    player_a TEXT,
                    player_b TEXT,
                    selected_player TEXT,
                    book_odds REAL,
                    model_odds REAL,
                    model_prob REAL,
                    ev_percent REAL,
                    elo_diff REAL,
                    kelly_stake_pct REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'En attente',
                    winner TEXT DEFAULT '',
                    profit_units REAL DEFAULT 0.0
                );
                """
            )
            self._import_legacy_reviewed(conn)

    @staticmethod
    def _parse_legacy_line(line: str, now_iso: str):
        """Parse une ligne CSV de Reviewed_Matchs.txt en tuple SQL."""
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 16 or not parts[-1].startswith("http"):
            return None
        match_url = parts[-1]
        summary_line = ", ".join(parts[:-1])
        return (
            match_url,
            now_iso,
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            _to_float(parts[4]),
            _to_float(parts[5]),
            _to_float(parts[6]),
            _to_float(parts[7]),
            _to_float(parts[8]),
            _to_float(parts[9]),
            _to_float(parts[12]),
            summary_line,
        )

    @classmethod
    def _import_legacy_reviewed(
        cls, conn: sqlite3.Connection, filepath: str = LEGACY_REVIEWED_FILE
    ) -> None:
        """Importe de façon idempotente tous les matchs de Reviewed_Matchs.txt."""
        if not os.path.exists(filepath):
            return
        now_iso = datetime.now().isoformat(timespec="seconds")
        rows_to_insert = []
        with open(filepath, "r", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                line = raw_line.strip()
                if not line:
                    continue
                parsed = cls._parse_legacy_line(line, now_iso)
                if parsed:
                    rows_to_insert.append(parsed)

        if rows_to_insert:
            conn.executemany(
                """
                INSERT OR IGNORE INTO matches (
                    match_url, analyzed_at, tournament, surface, player_a, player_b,
                    model_odds_a, model_odds_b, book_odds_a, book_odds_b,
                    elo_a, elo_b, confidence_index, summary_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

    def is_match_analyzed(self, match_url: str) -> bool:
        """Vérifie directement en base si l'URL du match a déjà été analysée."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM matches WHERE match_url = ? LIMIT 1",
                (match_url.strip(),),
            ).fetchone()
            return row is not None

    def load_reviewed_urls(self) -> Set[str]:
        """Retourne l'ensemble des URLs déjà analysées en O(1)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT match_url FROM matches").fetchall()
            return {row["match_url"] for row in rows}

    def save_match(self, match: MatchAnalysisData, daily_file: str = "Matchs.txt") -> bool:
        """Enregistre le match dans SQLite s'il n'existe pas déjà et met à jour Matchs.txt."""
        if self.is_match_analyzed(match.match_url):
            return False

        pa, pb = match.player_a, match.player_b
        summary = match.to_summary_line()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO matches (
                    match_url, analyzed_at, tournament, surface, player_a, player_b,
                    model_odds_a, model_odds_b, book_odds_a, book_odds_b,
                    elo_a, elo_b, confidence_index, summary_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match.match_url.strip(),
                    datetime.now().isoformat(timespec="seconds"),
                    match.tournament,
                    match.surface,
                    pa.name,
                    pb.name,
                    pa.model_odds,
                    pb.model_odds,
                    pa.book_odds,
                    pb.book_odds,
                    pa.elo,
                    pb.elo,
                    match.confidence.final_index,
                    summary,
                ),
            )
            inserted = cursor.rowcount > 0

        if inserted:
            with open(daily_file, "a", encoding="utf-8") as f_daily:
                f_daily.write(f"{summary}, {match.match_url}\n")
        return inserted

    def save_bet(self, match: MatchAnalysisData, alpha_res: Dict[str, Any]) -> bool:
        """Insère un pari Alpha 5+ détecté (ignoré si déjà présent)."""
        if not alpha_res.get("bet_recommended"):
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO bets (
                    match_url, detected_at, tournament, surface, player_a, player_b,
                    selected_player, book_odds, model_odds, model_prob,
                    ev_percent, elo_diff, kelly_stake_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match.match_url.strip(),
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    match.tournament,
                    match.surface,
                    match.player_a.name,
                    match.player_b.name,
                    alpha_res["selected_player"],
                    alpha_res["book_odds"],
                    alpha_res["model_odds"],
                    alpha_res["model_prob"],
                    alpha_res["ev_percent"],
                    alpha_res["elo_diff"],
                    alpha_res.get("kelly_stake_pct", 0.0),
                ),
            )
            return cursor.rowcount > 0

    def get_pending_bets(self) -> List[Dict[str, Any]]:
        """Retourne tous les paris en attente de résultat."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bets WHERE status = 'En attente'"
            ).fetchall()
            return [dict(row) for row in rows]

    def settle_bet(self, match_url: str, winner_name: str) -> None:
        """Met à jour le statut (Gagné/Perdu) et le profit d'un pari terminé."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT selected_player, book_odds, kelly_stake_pct FROM bets WHERE match_url = ?",
                (match_url,),
            ).fetchone()
            if not row:
                return
            won = row["selected_player"].lower() in winner_name.lower()
            stake = row["kelly_stake_pct"] or 1.0
            status = "Gagné" if won else "Perdu"
            profit = round(stake * (row["book_odds"] - 1.0), 2) if won else round(-stake, 2)
            conn.execute(
                """
                UPDATE bets
                SET status = ?, winner = ?, profit_units = ?
                WHERE match_url = ?
                """,
                (status, winner_name, profit, match_url),
            )

    def get_roi_summary(self) -> Dict[str, Any]:
        """Calcule les statistiques globales de performance (ROI, Winrate)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, kelly_stake_pct, profit_units FROM bets WHERE status != 'En attente'"
            ).fetchall()
            if not rows:
                return {"settled": 0, "won": 0, "winrate": 0.0, "profit": 0.0, "roi": 0.0}
            won = sum(1 for r in rows if r["status"] == "Gagné")
            staked = sum((r["kelly_stake_pct"] or 1.0) for r in rows)
            profit = sum(r["profit_units"] for r in rows)
            return {
                "settled": len(rows),
                "won": won,
                "winrate": round(100.0 * won / len(rows), 1),
                "profit": round(profit, 2),
                "roi": round(100.0 * profit / staked, 2) if staked > 0 else 0.0,
            }

    def export_bets_to_excel(self, filepath: str = TRACKING_FILE) -> str:
        """Exporte l'intégralité de la table bets vers Excel en une seule passe."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()

        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = "Sélections Alpha 5+"
        _style_header(sheet)

        for row in rows:
            sheet.append([
                row["detected_at"],
                row["tournament"],
                row["surface"],
                row["player_a"],
                row["player_b"],
                row["selected_player"],
                row["book_odds"],
                row["model_odds"],
                f"{row['model_prob'] * 100:.1f}%",
                f"{row['ev_percent']:+.1f}%",
                f"{row['elo_diff']:+.0f}",
                f"{row['kelly_stake_pct']:.2f}%",
                row["status"],
                row["winner"],
                row["profit_units"],
                row["match_url"],
            ])
            _style_data_row(sheet, sheet.max_row, row["status"])

        _fit_columns(sheet)
        try:
            wb.save(filepath)
            return filepath
        except PermissionError:
            fallback = filepath.replace(".xlsx", "_backup.xlsx")
            wb.save(fallback)
            return fallback


def _style_header(sheet) -> None:
    sheet.append(EXCEL_HEADERS)
    fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for idx in range(1, len(EXCEL_HEADERS) + 1):
        cell = sheet.cell(row=1, column=idx)
        cell.fill = fill
        cell.font = font
        cell.alignment = align
    sheet.row_dimensions[1].height = 26


def _style_data_row(sheet, row_idx: int, status: str) -> None:
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    status_colors = {
        "Gagné": ("C6EFCE", "006100"),
        "Perdu": ("FFC7CE", "9C0006"),
        "En attente": ("FFEB9C", "9C6500"),
    }
    bg, fg = status_colors.get(status, ("FFFFFF", "000000"))
    for col_idx in range(1, len(EXCEL_HEADERS) + 1):
        cell = sheet.cell(row=row_idx, column=col_idx)
        cell.border = thin
        if col_idx == 13:
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(bold=True, color=fg)
        elif col_idx >= 7 and col_idx != 16:
            cell.alignment = Alignment(horizontal="center")


def _fit_columns(sheet) -> None:
    for col in sheet.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        sheet.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 12)