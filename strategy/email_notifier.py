"""
Email notification module for daily tennis predictions and Alpha 5+ bets.

Sends an email summary with:
- Detected Alpha 5+ betting opportunities in a styled HTML table
- Total matches processed
- The updated 'Paris_Alpha_5_Plus.xlsx' spreadsheet attached
"""

import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import dotenv_values

DEFAULT_TRACKING_FILE = "Paris_Alpha_5_Plus.xlsx"

def _get_setting(env_file: dict, key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    return env_file.get(key, default)

def _load_smtp_config() -> Dict[str, str]:
    env_file = dotenv_values(".env") if os.path.exists(".env") else {}
    user = _get_setting(env_file, "SMTP_USER", "")
    return {
        "host": _get_setting(env_file, "SMTP_HOST", "smtp.gmail.com"),
        "port": _get_setting(env_file, "SMTP_PORT", "587"),
        "user": user,
        "password": _get_setting(env_file, "SMTP_PASSWORD", ""),
        "recipient": _get_setting(env_file, "EMAIL_RECIPIENT", user)
    }

def _is_config_valid(cfg: Dict[str, str]) -> bool:
    return bool(cfg.get("user") and cfg.get("password") and cfg.get("recipient"))

def _build_subject(bets_count: int, date_str: str) -> str:
    if bets_count > 0:
        return f"🎾 Tennis AI - {bets_count} Pari(s) Alpha 5+ Détecté(s) - {date_str}"
    return f"🎾 Tennis AI - Rapport Quotidien (0 pari détecté) - {date_str}"

def _build_table_rows(bets: List[Dict[str, Any]]) -> str:
    rows = []
    for bet_item in bets:
        prob = f"{bet_item.get('model_prob', 0.0) * 100:.1f}%"
        exp_val = f"{bet_item.get('ev_percent', 0.0):+.1f}%"
        diff = f"{bet_item.get('elo_diff', 0.0):+.0f}"
        tourn = bet_item.get('tournament', '')
        surf = bet_item.get('surface', '')
        player1 = bet_item.get('player1', '')
        player2 = bet_item.get('player2', '')
        sel = bet_item.get('selected_player', '')
        rows.append(f"""
        <tr style="border-bottom: 1px solid #e0e0e0; text-align: center;">
            <td style="padding: 10px; text-align: left;"><b>{tourn}</b> ({surf})</td>
            <td style="padding: 10px; text-align: left;">{player1} vs {player2}</td>
            <td style="padding: 10px; color: #2e7d32; font-weight: bold;
                background-color: #e8f5e9;">
                {sel}
            </td>
            <td style="padding: 10px; font-weight: bold;">{bet_item.get('book_odds', 0.0):.2f}</td>
            <td style="padding: 10px;">{bet_item.get('model_odds', 0.0):.2f} ({prob})</td>
            <td style="padding: 10px; color: #2e7d32; font-weight: bold;">{exp_val}</td>
            <td style="padding: 10px;">{diff}</td>
        </tr>
        """)
    return "".join(rows)

def _build_html_content(bets: List[Dict[str, Any]], total_matches: int, date_str: str) -> str:
    count = len(bets)
    if count > 0:
        headline = (
            f"<h2 style='color: #2e7d32;'>🎯 {count} opportunité(s) Alpha 5+ "
            f"All-Court détectée(s)</h2>"
        )
        table_style = (
            "width: 100%; border-collapse: collapse; "
            "font-family: Arial, sans-serif; font-size: 13px;"
        )
        details = f"""
        <table style="{table_style}">
            <thead>
                <tr style="background-color: #1F4E79; color: white;">
                    <th style="padding: 10px;">Tournoi</th>
                    <th style="padding: 10px;">Affiche</th>
                    <th style="padding: 10px;">Pari Conseillé</th>
                    <th style="padding: 10px;">Cote Book</th>
                    <th style="padding: 10px;">Cote Modèle</th>
                    <th style="padding: 10px;">EV (%)</th>
                    <th style="padding: 10px;">ΔELO</th>
                </tr>
            </thead>
            <tbody>
                {_build_table_rows(bets)}
            </tbody>
        </table>
        """
    else:
        headline = "<h2 style='color: #555;'>⚪ Aucun pari qualifié aujourd'hui</h2>"
        details = (
            "<p style='color: #666;'>Tous les matchs analysés ont été filtrés car aucun "
            "ne réunit les 3 critères stricts (EV > 3%, ΔELO ≥ 150, Cotes [1.40-2.50]).</p>"
        )

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 20px;">
        <h1 style="color: #1F4E79; margin-bottom: 5px;">
            🎾 Rapport Quotidien - Prédictions Tennis
        </h1>
        <p style="color: #777; margin-top: 0;">
            Date d'analyse : <b>{date_str}</b> | Matchs analysés : <b>{total_matches}</b>
        </p>
        <hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;" />
        {headline}
        {details}
        <br/>
        <p style="font-size: 12px; color: #888;">
            Le fichier Excel complet et mis à jour (<code>Paris_Alpha_5_Plus.xlsx</code>)
            est joint à cet email.
        </p>
    </body>
    </html>
    """

def _attach_excel(msg: MIMEMultipart, filepath: str) -> None:
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "rb") as file_handle:
            part = MIMEApplication(file_handle.read(), Name=os.path.basename(filepath))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(filepath)}"'
            msg.attach(part)
    except OSError as err:
        print(f"⚠️ Impossible d'attacher le fichier Excel {filepath}: {err}")

def _dispatch_smtp(cfg: Dict[str, str], msg: MIMEMultipart) -> None:
    port = int(cfg["port"])
    with smtplib.SMTP(cfg["host"], port, timeout=15) as server:
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)

def send_daily_email(
        bets: List[Dict[str, Any]],
        total_matches: int = 0,
        filepath: str = DEFAULT_TRACKING_FILE,
        config: Optional[Dict[str, str]] = None
) -> bool:
    """Builds and sends daily summary email with attached selection report."""
    cfg = config or _load_smtp_config()
    if not _is_config_valid(cfg):
        msg_cfg = (
            "ℹ️ Identifiants email non configurés (SMTP_USER/SMTP_PASSWORD). "
            "Notification par email ignorée."
        )
        print(msg_cfg)
        return False

    date_str = datetime.now().strftime("%d/%m/%Y")
    subject = _build_subject(len(bets), date_str)
    html_body = _build_html_content(bets, total_matches, date_str)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["recipient"]

    msg.attach(MIMEText(html_body, "html", "utf-8"))
    _attach_excel(msg, filepath)

    try:
        _dispatch_smtp(cfg, msg)
        print(f"📧 Email récapitulatif envoyé avec succès à {cfg['recipient']}")
        return True
    except (smtplib.SMTPException, socket.error, OSError, TimeoutError) as err:
        print(f"⚠️ Erreur lors de l'envoi de l'email : {err}")
        return False
