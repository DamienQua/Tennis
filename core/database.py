"""Persistance SQLite des matchs, paris Alpha 5+, CLV, ROI et dump SQL texte."""

from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from typing import Any, Dict, Iterator, List, Set
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from core.models import MatchAnalysisData

DB_FILE = "tennis_ai.db"
SQL_DUMP_FILE = "tennis_ai_dump.sql"
LEGACY_REVIEWED_FILE = "Reviewed_Matchs.txt"
TRACKING_FILE = "Paris_Alpha_5_Plus.xlsx"

EXCEL_HEADERS = [
    "Date Détection",
    "Tournoi",
    "Surface",
    "Joueur 1",
    "Joueur 2",
    "Pari Conseillé",
    "Cote Prise",
    "Cote Clôture",
    "CLV (%)",
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
    cleaned = val.strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


class TennisDatabase:
    """Gère le stockage SQLite (mode WAL), le dump SQL Git, la CLV et l'export Excel."""

    def __init__(self, db_path: str = DB_FILE, dump_path: str = SQL_DUMP_FILE) -> None:
        self.db_path = db_path
        self.dump_path = dump_path
        self._restore_from_dump_if_needed()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Gère la transaction et ferme systématiquement le descripteur de fichier."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _restore_from_dump_if_needed(self) -> None:
        """Reconstruit la base SQLite depuis le dump texte si le .db est absent."""
        if os.path.exists(self.db_path) or not os.path.exists(self.dump_path):
            return
        with open(self.dump_path, "r", encoding="utf-8") as f_dump:
            sql_script = f_dump.read()
        if not sql_script.strip():
            return
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(sql_script)
            conn.commit()
        finally:
            conn.close()

    def export_sql_dump(self, dump_path: str = "") -> str:
        """Exporte la base SQLite en fichier texte SQL léger pour Git."""
        target = dump_path or self.dump_path
        with self._session() as conn:
            lines = list(conn.iterdump())
        with open(target, "w", encoding="utf-8", newline="\n") as f_out:
            f_out.write("\n".join(lines) + "\n")
        return target

    def _init_schema(self) -> None:
        with self._session() as conn:
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
                    closing_odds REAL DEFAULT 0.0,
                    clv_percent REAL DEFAULT 0.0,
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
            self._migrate_bets_columns(conn)
            self._import_legacy_reviewed(conn)

    @staticmethod
    def _migrate_bets_columns(conn: sqlite3.Connection) -> None:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(bets)").fetchall()
        }
        if "closing_odds" not in existing:
            conn.execute("ALTER TABLE bets ADD COLUMN closing_odds REAL DEFAULT 0.0;")
        if "clv_percent" not in existing:
            conn.execute("ALTER TABLE bets ADD COLUMN clv_percent REAL DEFAULT 0.0;")

    @staticmethod
    def _parse_legacy_line(line: str, now_iso: str):
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
        with self._session() as conn:
            row = conn.execute(
                "SELECT 1 FROM matches WHERE match_url = ? LIMIT 1",
                (match_url.strip(),),
            ).fetchone()
            return row is not None

    def load_reviewed_urls(self) -> Set[str]:
        with self._session() as conn:
            rows = conn.execute("SELECT match_url FROM matches").fetchall()
            return {row["match_url"] for row in rows}

    def save_match(self, match: MatchAnalysisData, daily_file: str = "Matchs.txt") -> bool:
        if self.is_match_analyzed(match.match_url):
            return False

        pa, pb = match.player_a, match.player_b
        summary = match.to_summary_line()
        with self._session() as conn:
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
        if not alpha_res.get("bet_recommended"):
            return False
        book_odds = alpha_res["book_odds"]
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO bets (
                    match_url, detected_at, tournament, surface, player_a, player_b,
                    selected_player, book_odds, closing_odds, clv_percent,
                    model_odds, model_prob, ev_percent, elo_diff, kelly_stake_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match.match_url.strip(),
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    match.tournament,
                    match.surface,
                    match.player_a.name,
                    match.player_b.name,
                    alpha_res["selected_player"],
                    book_odds,
                    book_odds,
                    0.0,
                    alpha_res["model_odds"],
                    alpha_res["model_prob"],
                    alpha_res["ev_percent"],
                    alpha_res["elo_diff"],
                    alpha_res.get("kelly_stake_pct", 0.0),
                ),
            )
            return cursor.rowcount > 0

    def update_closing_odds(self, match_url: str, closing_odds: float) -> None:
        if closing_odds <= 1.0:
            return
        with self._session() as conn:
            row = conn.execute(
                "SELECT book_odds FROM bets WHERE match_url = ? AND status = 'En attente'",
                (match_url,),
            ).fetchone()
            if not row or row["book_odds"] <= 1.0:
                return
            clv_pct = round(((row["book_odds"] / closing_odds) - 1.0) * 100.0, 2)
            conn.execute(
                "UPDATE bets SET closing_odds = ?, clv_percent = ? WHERE match_url = ?",
                (closing_odds, clv_pct, match_url),
            )

    def get_pending_bets(self) -> List[Dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM bets WHERE status = 'En attente'"
            ).fetchall()
            return [dict(row) for row in rows]

    def settle_bet(
        self, match_url: str, winner_name: str, is_void: bool = False
    ) -> None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT selected_player, book_odds, kelly_stake_pct FROM bets WHERE match_url = ?",
                (match_url,),
            ).fetchone()
            if not row:
                return

            if is_void:
                status = "Remboursé"
                profit = 0.0
            else:
                won = row["selected_player"].lower() in winner_name.lower()
                stake = row["kelly_stake_pct"] or 1.0
                status = "Gagné" if won else "Perdu"
                profit = round(stake * (row["book_odds"] - 1.0), 2) if won else round(-stake, 2)

            conn.execute(
                "UPDATE bets SET status = ?, winner = ?, profit_units = ? WHERE match_url = ?",
                (status, winner_name, profit, match_url),
            )

    def get_roi_summary(self) -> Dict[str, Any]:
        query = """
            SELECT
                COUNT(*) AS settled,
                COALESCE(SUM(CASE WHEN status = 'Gagné' THEN 1 ELSE 0 END), 0) AS won,
                COALESCE(SUM(CASE WHEN kelly_stake_pct > 0 THEN kelly_stake_pct ELSE 1.0 END), 0.0) AS staked,
                COALESCE(SUM(profit_units), 0.0) AS profit,
                COALESCE(AVG(COALESCE(clv_percent, 0.0)), 0.0) AS avg_clv
            FROM bets
            WHERE status IN ('Gagné', 'Perdu')
        """
        with self._session() as conn:
            row = conn.execute(query).fetchone()

        settled = int(row["settled"])
        if settled == 0:
            return {"settled": 0, "won": 0, "winrate": 0.0, "profit": 0.0, "roi": 0.0, "avg_clv": 0.0}

        won = int(row["won"])
        staked = float(row["staked"])
        profit = float(row["profit"])
        return {
            "settled": settled,
            "won": won,
            "winrate": round(100.0 * won / settled, 1),
            "profit": round(profit, 2),
            "roi": round(100.0 * profit / staked, 2) if staked > 0 else 0.0,
            "avg_clv": round(float(row["avg_clv"]), 2),
        }

    def export_bets_to_excel(self, filepath: str = TRACKING_FILE) -> str:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()

        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = "Sélections Alpha 5+"
        _style_header(sheet)

        for row in rows:
            closing_val = row["closing_odds"] or row["book_odds"]
            clv_val = row["clv_percent"] or 0.0
            sheet.append([
                row["detected_at"],
                row["tournament"],
                row["surface"],
                row["player_a"],
                row["player_b"],
                row["selected_player"],
                row["book_odds"],
                closing_val,
                f"{clv_val:+.2f}%",
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
        "Remboursé": ("D9E1F2", "1F4E79"),
        "En attente": ("FFEB9C", "9C6500"),
    }
    bg, fg = status_colors.get(status, ("FFFFFF", "000000"))
    for col_idx in range(1, len(EXCEL_HEADERS) + 1):
        cell = sheet.cell(row=row_idx, column=col_idx)
        cell.border = thin
        if col_idx == 15:
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(bold=True, color=fg)
        elif col_idx >= 7 and col_idx != 18:
            cell.alignment = Alignment(horizontal="center")


def _fit_columns(sheet) -> None:
    for col in sheet.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        sheet.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 12)