"""Persistance SQLite des matchs, paris Alpha 5+, CLV, ROI et dump SQL texte."""

from contextlib import contextmanager
from datetime import datetime, timezone
from math import isfinite
import os
import sqlite3
import tempfile
from typing import Any, Dict, Iterator, List, Set
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from core.models import MatchAnalysisData
from utils.player_identity import names_match

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
        number = float(cleaned)
        return number if isfinite(number) else 0.0
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
        directory = os.path.dirname(os.path.abspath(target))
        os.makedirs(directory, exist_ok=True)
        # Remplacement atomique : un arrêt ne tronque pas le dernier état restaurable.
        fd, temporary = tempfile.mkstemp(prefix=".tennis-dump-", suffix=".sql", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f_out:
                f_out.write("\n".join(lines) + "\n")
                f_out.flush()
                os.fsync(f_out.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
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
            self._migrate_match_columns(conn)
            self._import_legacy_reviewed(conn)

    @staticmethod
    def _migrate_match_columns(conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(matches)")}
        columns = {
            "analysis_status": "TEXT NOT NULL DEFAULT 'incomplete'",
            "last_error": "TEXT NOT NULL DEFAULT ''",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE matches ADD COLUMN {name} {definition}")
        if "analysis_status" not in existing:
            conn.execute("""
                UPDATE matches SET analysis_status = 'complete'
                WHERE model_odds_a > 1 AND model_odds_b > 1
                  AND book_odds_a > 1 AND book_odds_b > 1 AND elo_a > 0 AND elo_b > 0
            """)

    @staticmethod
    def _migrate_bets_columns(conn: sqlite3.Connection) -> None:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(bets)").fetchall()
        }
        if "closing_odds" not in existing:
            conn.execute("ALTER TABLE bets ADD COLUMN closing_odds REAL DEFAULT 0.0;")
        if "clv_percent" not in existing:
            conn.execute("ALTER TABLE bets ADD COLUMN clv_percent REAL DEFAULT 0.0;")
        for name in ("odds_observed_at", "closing_observed_at", "scheduled_start"):
            if name not in existing:
                conn.execute(f"ALTER TABLE bets ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")

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
                    complete = all(isfinite(value) and value > 1 for value in parsed[6:12])
                    rows_to_insert.append((*parsed, "complete" if complete else "incomplete"))

        if rows_to_insert:
            conn.executemany(
                """
                INSERT OR IGNORE INTO matches (
                    match_url, analyzed_at, tournament, surface, player_a, player_b,
                    model_odds_a, model_odds_b, book_odds_a, book_odds_b,
                    elo_a, elo_b, confidence_index, summary_line, analysis_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

    def is_match_analyzed(self, match_url: str) -> bool:
        with self._session() as conn:
            row = conn.execute(
                "SELECT 1 FROM matches WHERE match_url = ? AND analysis_status = 'complete' LIMIT 1",
                (match_url.strip(),),
            ).fetchone()
            return row is not None

    def load_reviewed_urls(self) -> Set[str]:
        with self._session() as conn:
            rows = conn.execute("SELECT match_url FROM matches WHERE analysis_status = 'complete'").fetchall()
            return {row["match_url"] for row in rows}

    def save_match(self, match: MatchAnalysisData, daily_file: str = "Matchs.txt") -> bool:
        pa, pb = match.player_a, match.player_b
        summary = match.to_summary_line()
        complete = match.is_complete()
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO matches (
                    match_url, analyzed_at, tournament, surface, player_a, player_b,
                    model_odds_a, model_odds_b, book_odds_a, book_odds_b,
                    elo_a, elo_b, confidence_index, summary_line,
                    analysis_status, last_error, attempt_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(match_url) DO UPDATE SET
                    analyzed_at = excluded.analyzed_at,
                    tournament = excluded.tournament, surface = excluded.surface,
                    player_a = excluded.player_a, player_b = excluded.player_b,
                    model_odds_a = excluded.model_odds_a, model_odds_b = excluded.model_odds_b,
                    book_odds_a = excluded.book_odds_a, book_odds_b = excluded.book_odds_b,
                    elo_a = excluded.elo_a, elo_b = excluded.elo_b,
                    confidence_index = excluded.confidence_index, summary_line = excluded.summary_line,
                    analysis_status = excluded.analysis_status, last_error = excluded.last_error,
                    attempt_count = matches.attempt_count + 1
                WHERE matches.analysis_status <> 'complete'
                """,
                (
                    match.match_url.strip(),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
                    "complete" if complete else "incomplete",
                    "" if complete else "Cotes pré-match, identité ou ELO incomplets",
                ),
            )
            inserted = cursor.rowcount > 0

        if inserted:
            with open(daily_file, "a", encoding="utf-8") as f_daily:
                f_daily.write(f"{summary}, {match.match_url}\n")
        return inserted

    def record_retry(self, match_url: str, reason: str) -> None:
        """Mémorise un échec sans interdire les reprises lors du prochain passage."""
        with self._session() as conn:
            conn.execute("""
                INSERT INTO matches (match_url, analyzed_at, analysis_status, last_error, attempt_count)
                VALUES (?, ?, 'retry', ?, 1)
                ON CONFLICT(match_url) DO UPDATE SET
                    analyzed_at = excluded.analyzed_at, analysis_status = 'retry',
                    last_error = excluded.last_error, attempt_count = matches.attempt_count + 1
                WHERE matches.analysis_status <> 'complete'
            """, (match_url.strip(), datetime.now(timezone.utc).isoformat(timespec="seconds"), reason))

    def save_bet(self, match: MatchAnalysisData, alpha_res: Dict[str, Any]) -> bool:
        if not alpha_res.get("bet_recommended") or not match.is_complete():
            return False
        participants = (match.player_a.name, match.player_b.name)
        if sum(names_match(player, alpha_res.get("selected_player", "")) for player in participants) != 1:
            return False
        book_odds = alpha_res["book_odds"]
        with self._session() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO bets (
                    match_url, detected_at, tournament, surface, player_a, player_b,
                    selected_player, book_odds, closing_odds, clv_percent,
                    model_odds, model_prob, ev_percent, elo_diff, kelly_stake_pct,
                    odds_observed_at, scheduled_start
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    None,
                    None,
                    alpha_res["model_odds"],
                    alpha_res["model_prob"],
                    alpha_res["ev_percent"],
                    alpha_res["elo_diff"],
                    alpha_res.get("kelly_stake_pct", 0.0),
                    match.odds_observed_at,
                    match.scheduled_start,
                ),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _utc_timestamp(value: str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
        except (AttributeError, TypeError, ValueError):
            return None

    def update_closing_odds(
        self, match_url: str, closing_odds: float, observed_at: str = "", scheduled_start: str = ""
    ) -> bool:
        observed = self._utc_timestamp(observed_at)
        if not isfinite(closing_odds) or closing_odds <= 1.0 or observed is None:
            return False
        with self._session() as conn:
            row = conn.execute(
                "SELECT book_odds, scheduled_start, closing_observed_at FROM bets WHERE match_url = ? AND status = 'En attente'",
                (match_url,),
            ).fetchone()
            if not row or row["book_odds"] <= 1.0:
                return False
            # Une revanche future ou un report non identifié n'est pas la clôture
            # de la rencontre initiale. Sa date ne doit jamais être remplacée ici.
            start = self._utc_timestamp(row["scheduled_start"])
            supplied_start = self._utc_timestamp(scheduled_start) if scheduled_start else start
            previous = self._utc_timestamp(row["closing_observed_at"])
            if (start is None or supplied_start != start or observed >= start
                    or (previous is not None and observed <= previous)):
                return False
            clv_pct = round(((row["book_odds"] / closing_odds) - 1.0) * 100.0, 2)
            conn.execute(
                "UPDATE bets SET closing_odds = ?, clv_percent = ?, closing_observed_at = ?, scheduled_start = ? WHERE match_url = ?",
                (closing_odds, clv_pct, observed.isoformat(), start.isoformat(), match_url),
            )
            return True

    def get_pending_bets(self) -> List[Dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM bets WHERE status = 'En attente'"
            ).fetchall()
            return [dict(row) for row in rows]

    def settle_bet(
        self, match_url: str, winner_name: str, is_void: bool = False
    ) -> bool:
        with self._session() as conn:
            row = conn.execute(
                "SELECT player_a, player_b, selected_player, book_odds, kelly_stake_pct FROM bets WHERE match_url = ? AND status = 'En attente'",
                (match_url,),
            ).fetchone()
            if not row:
                return False

            if is_void:
                status = "Remboursé"
                profit = 0.0
            else:
                participants = [row["player_a"], row["player_b"]]
                winners = [player for player in participants if names_match(player, winner_name)]
                selections = [player for player in participants if names_match(player, row["selected_player"])]
                if len(winners) != 1 or len(selections) != 1:
                    return False
                winner_name = winners[0]
                won = names_match(selections[0], winner_name)
                stake = row["kelly_stake_pct"] or 1.0
                status = "Gagné" if won else "Perdu"
                profit = round(stake * (row["book_odds"] - 1.0), 2) if won else round(-stake, 2)

            conn.execute(
                "UPDATE bets SET status = ?, winner = ?, profit_units = ? WHERE match_url = ?",
                (status, winner_name, profit, match_url),
            )
            return True

    def get_roi_summary(self) -> Dict[str, Any]:
        query = """
            SELECT
                COUNT(*) AS settled,
                COALESCE(SUM(CASE WHEN status = 'Gagné' THEN 1 ELSE 0 END), 0) AS won,
                COALESCE(SUM(CASE WHEN kelly_stake_pct > 0 THEN kelly_stake_pct ELSE 1.0 END), 0.0) AS staked,
                COALESCE(SUM(profit_units), 0.0) AS profit,
                AVG(CASE WHEN closing_observed_at <> '' THEN clv_percent END) AS avg_clv,
                SUM(CASE WHEN closing_observed_at <> '' THEN 1 ELSE 0 END) AS clv_samples
            FROM bets
            WHERE status IN ('Gagné', 'Perdu')
        """
        with self._session() as conn:
            row = conn.execute(query).fetchone()

        settled = int(row["settled"])
        if settled == 0:
            return {"settled": 0, "won": 0, "winrate": 0.0, "profit": 0.0, "roi": 0.0, "avg_clv": None, "clv_samples": 0}

        won = int(row["won"])
        staked = float(row["staked"])
        profit = float(row["profit"])
        return {
            "settled": settled,
            "won": won,
            "winrate": round(100.0 * won / settled, 1),
            "profit": round(profit, 2),
            "roi": round(100.0 * profit / staked, 2) if staked > 0 else 0.0,
            "avg_clv": round(float(row["avg_clv"]), 2) if row["avg_clv"] is not None else None,
            "clv_samples": int(row["clv_samples"]),
        }

    def export_bets_to_excel(self, filepath: str = TRACKING_FILE) -> str:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()

        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = "Sélections Alpha 5+"
        _style_header(sheet)

        for row in rows:
            has_closing = bool(row["closing_observed_at"])
            closing_val = round(row["closing_odds"], 2) if has_closing else None
            clv_val = f"{row['clv_percent']:+.2f}%" if has_closing else "Indisponible"
            sheet.append([
                row["detected_at"],
                row["tournament"],
                row["surface"],
                row["player_a"],
                row["player_b"],
                row["selected_player"],
                round(row["book_odds"], 2),
                closing_val,
                clv_val,
                round(row["model_odds"], 2),
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
        if col_idx in (7, 8, 10):
            cell.number_format = "0.00"
        if col_idx == 15:
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(bold=True, color=fg)
        elif col_idx >= 7 and col_idx != 18:
            cell.alignment = Alignment(horizontal="center")


def _fit_columns(sheet) -> None:
    for col in sheet.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        sheet.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 12)
