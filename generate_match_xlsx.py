import os
import openpyxl
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime

async def generate_match_xlsx(match_vs):
    date = datetime.now().strftime("%d/%m/%Y")
    tournament = match_vs[0]
    player1, player2 = match_vs[2], match_vs[3]

    workbook = openpyxl.Workbook()
    sheet = workbook.active

    xlsx_data = [
        ["", player1, player2],
        ["Classement mondial", match_vs[4], match_vs[5]],
        ["% Victoires carrière", match_vs[17], match_vs[28]],
        ["% Victoires surface", match_vs[19], match_vs[30]],
        ["", "", ""],
        ["Ratio V/D carrière", match_vs[6], match_vs[7]],
        ["Ratio V/D 1 an", match_vs[8], match_vs[9]], 
        ["Ratio V/D surface", match_vs[10], match_vs[11]],
        ["% Sets gagnés", match_vs[12], match_vs[13]],
        ["", "", ""],
        ["% Victoires 1 an", match_vs[16], match_vs[27]],
        ["% Victoires 1 an surface", match_vs[18], match_vs[29]],
        ["% Victoires 50 derniers matchs", match_vs[15], match_vs[26]],
        ["% Victoires 10 derniers matchs", match_vs[14], match_vs[25]],
        ["Nombre matchs joués dernier mois", match_vs[20], match_vs[31]],
        ["Durée cumulée des derniers matchs tournoi en cours", match_vs[21], match_vs[32]], 
        ["", "", ""],
        ["% 1er service", match_vs[22], match_vs[33]],
        ["% points gagnés service", match_vs[23], match_vs[34]],
        ["% balles de break sauvées", match_vs[24], match_vs[35]],
        ["", "", ""],
        ["Pourcentage victoire", round(90 / float(match_vs[36]), 2), round(90 / float(match_vs[37]), 2)],
        ["", "", ""],
        ["Côte estimée", match_vs[36], match_vs[37]],
    ]

    for row in xlsx_data:
        sheet.append(row)

    for column in sheet.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        sheet.column_dimensions[column_letter].width = adjusted_width

    thin_border = Border(left=Side(style='thin'), 
                         right=Side(style='thin'), 
                         top=Side(style='thin'), 
                         bottom=Side(style='thin'))

    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column):
        for cell in row:
            cell.border = thin_border

    year = datetime.now().year
    month = datetime.now().strftime("%B")  # Full month name

    matchs_folder = os.path.join("Matchs", str(year), month, tournament.replace(' ', '_'))
    os.makedirs(matchs_folder, exist_ok=True)

    filename = f"{date.replace('/', '-')}_{player1.replace(' ', '_')}_vs_{player2.replace(' ', '_')}.xlsx"

    full_path = os.path.join(matchs_folder, filename)

    workbook.save(full_path)

    print(f"Excel file '{full_path}' has been generated.")
