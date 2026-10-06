#!/usr/bin/env python3
"""
build_excel.py — generate WC2026_Live_Odds_Calculator.xlsx, a self-contained
spreadsheet that reproduces the live Dixon-Coles model in Excel formulas (no
Python needed to use it). You type teams + score + minute + the live Polymarket
prices; it returns model / market / blended win-draw-loss probabilities, the
draw probability, the edge, and a buy/sell verdict.
"""
import os, json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation

OUT = os.path.join(os.path.dirname(__file__), "..", "outputs", "WC2026_Live_Odds_Calculator.xlsx")
FIT = json.load(open(os.path.join(os.path.dirname(__file__), "..", "outputs", "fitted_ratings.json")))
TEAMS = sorted(FIT["teams"].keys())
C, GAMMA = FIT["c"], FIT["gamma"]
HOSTS = ["United States", "Mexico", "Canada"]

wb = openpyxl.Workbook()

# ---------- styles ----------
H1 = Font(size=16, bold=True, color="FFFFFF")
HDR = Font(size=11, bold=True, color="FFFFFF")
BOLD = Font(bold=True)
BIG = Font(size=14, bold=True)
navy = PatternFill("solid", fgColor="1F3864")
blue = PatternFill("solid", fgColor="2E5496")
yellow = PatternFill("solid", fgColor="FFF2CC")   # input cells
green = PatternFill("solid", fgColor="C6E0B4")     # output
grey = PatternFill("solid", fgColor="EDEDED")
thin = Border(*[Side(style="thin", color="BBBBBB")] * 4)
ctr = Alignment(horizontal="center", vertical="center")
left = Alignment(horizontal="left", vertical="center", wrap_text=True)

# ====================================================== RATINGS sheet
rs = wb.active; rs.title = "Ratings"
rs["A1"] = "Team"; rs["B1"] = "attack"; rs["C1"] = "defence"
rs["E1"] = "c"; rs["F1"] = C
rs["E2"] = "gamma(home)"; rs["F2"] = GAMMA
rs["H1"] = "Hosts"
for i, h in enumerate(HOSTS): rs.cell(row=2 + i, column=8, value=h)
for c in ("A1", "B1", "C1", "E1", "E2", "H1"): rs[c].font = BOLD
for i, t in enumerate(TEAMS):
    r = 2 + i
    rs.cell(row=r, column=1, value=t)
    rs.cell(row=r, column=2, value=round(FIT["teams"][t]["atk"], 4))
    rs.cell(row=r, column=3, value=round(FIT["teams"][t]["dfn"], 4))
rs.column_dimensions["A"].width = 24
note = rs.cell(row=2, column=10,
               value="Ratings exported from the fitted Dixon-Coles model (re-run scripts/build_excel.py after each daily refit to refresh).")
note.alignment = left

# ====================================================== CALCULATOR sheet
ws = wb.create_sheet("Live Calculator", 0)
ws.sheet_view.showGridLines = False
for col, w in {"A": 2, "B": 22, "C": 13, "D": 3, "E": 16, "F": 11, "G": 11, "H": 11, "I": 11, "J": 11}.items():
    ws.column_dimensions[col].width = w

ws.merge_cells("B1:J1")
ws["B1"] = "  2026 WORLD CUP — LIVE ODDS & DRAW-PROBABILITY CALCULATOR"
ws["B1"].font = H1; ws["B1"].fill = navy; ws["B1"].alignment = Alignment(vertical="center")
ws.row_dimensions[1].height = 28
ws.merge_cells("B2:J2")
ws["B2"] = ("Type into the YELLOW cells only. Green cells are the answer. "
            "Prices are 0–1 (e.g. 27¢ = 0.27). Leave market prices blank to see model-only.")
ws["B2"].alignment = left; ws["B2"].fill = grey

# ---- INPUTS ----
ws["B4"] = "INPUTS"; ws["B4"].font = HDR; ws["B4"].fill = blue
ws.merge_cells("B4:C4")
inputs = [
    ("Home team", "Brazil"),
    ("Away team", "Haiti"),
    ("Home score (now)", 0),
    ("Away score (now)", 0),
    ("Minute (0–94)", 0),
    ("Polymarket: Home price", 0.0),
    ("Polymarket: Draw price", 0.0),
    ("Polymarket: Away price", 0.0),
    ("Blend weight on market", 0.6),
]
for i, (label, default) in enumerate(inputs):
    r = 5 + i
    ws.cell(row=r, column=2, value=label).font = BOLD
    c = ws.cell(row=r, column=3, value=default)
    c.fill = yellow; c.border = thin; c.alignment = ctr
# refs
HOME, AWAY, HS, AS, MIN = "$C$5", "$C$6", "$C$7", "$C$8", "$C$9"
PMH, PMD, PMA, WM = "$C$10", "$C$11", "$C$12", "$C$13"

# dropdowns for teams
dv = DataValidation(type="list", formula1=f"=Ratings!$A$2:$A${1+len(TEAMS)}", allow_blank=False)
ws.add_data_validation(dv); dv.add(ws["C5"]); dv.add(ws["C6"])

# ---- ENGINE (lookups + Poisson) ----
ws["B16"] = "ENGINE (auto — do not edit)"; ws["B16"].font = HDR; ws["B16"].fill = blue
ws.merge_cells("B16:C16")
eng = [
    ("atk_home", f"=VLOOKUP({HOME},Ratings!$A:$C,2,FALSE)"),
    ("dfn_home", f"=VLOOKUP({HOME},Ratings!$A:$C,3,FALSE)"),
    ("atk_away", f"=VLOOKUP({AWAY},Ratings!$A:$C,2,FALSE)"),
    ("dfn_away", f"=VLOOKUP({AWAY},Ratings!$A:$C,3,FALSE)"),
    ("host_home", f"=IF(ISNUMBER(MATCH({HOME},Ratings!$H:$H,0)),1,0)"),
    ("host_away", f"=IF(ISNUMBER(MATCH({AWAY},Ratings!$H:$H,0)),1,0)"),
    ("xG home (pre)", f"=EXP(Ratings!$F$1+$C$17-$C$20+Ratings!$F$2*$C$21)"),
    ("xG away (pre)", f"=EXP(Ratings!$F$1+$C$19-$C$18+Ratings!$F$2*$C$22)"),
    ("mins-left frac", f"=MAX(0,(94-{MIN})/90)"),
    ("remaining xG home", "=$C$23*$C$25"),
    ("remaining xG away", "=$C$24*$C$25"),
]
for i, (label, f) in enumerate(eng):
    r = 17 + i
    ws.cell(row=r, column=2, value=label).font = Font(size=9, italic=True, color="808080")
    cc = ws.cell(row=r, column=3, value=f); cc.font = Font(size=9, color="808080"); cc.alignment = ctr
LAMR, NUR = "$C$27", "$C$28"   # remaining xG home/away

# Poisson engine grid: additional goals i (rows) x j (cols), 0..8
g0r, g0c = 31, 6   # grid top-left at F31; headers row 30 / col E
ws.cell(row=30, column=5, value="i\\j").font = Font(size=8, color="AAAAAA")
for j in range(9):
    ws.cell(row=30, column=g0c + j, value=j).font = Font(size=8, color="AAAAAA")
for i in range(9):
    ws.cell(row=g0r + i, column=5, value=i).font = Font(size=8, color="AAAAAA")
    for j in range(9):
        col = g0c + j
        cell = ws.cell(row=g0r + i, column=col)
        # joint prob of home adding i AND away adding j
        cell.value = (f"=POISSON.DIST($E{g0r+i},{LAMR},FALSE)"
                      f"*POISSON.DIST({openpyxl.utils.get_column_letter(col)}$30,{NUR},FALSE)")
        cell.font = Font(size=8, color="C0C0C0")
# margin grid (home final - away final) 9x9 at row 42
m0r = 42
for i in range(9):
    ws.cell(row=m0r + i, column=5, value=i).font = Font(size=8, color="AAAAAA")
    for j in range(9):
        col = g0c + j
        cell = ws.cell(row=m0r + i, column=col)
        cell.value = (f"=({HS}+$E{m0r+i})-({AS}+{openpyxl.utils.get_column_letter(col)}$30)")
        cell.font = Font(size=8, color="C0C0C0")
JG = f"$F${g0r}:$N${g0r+8}"      # joint grid range
MG = f"$F${m0r}:$N${m0r+8}"      # margin grid range

# model probs (helper cells C53/54/55)
ws["B52"] = "model P (home/draw/away)"; ws["B52"].font = Font(size=9, italic=True, color="808080")
ws["C53"] = f"=SUMPRODUCT(({MG}>0)*{JG})/SUM({JG})"
ws["C54"] = f"=SUMPRODUCT(({MG}=0)*{JG})/SUM({JG})"
ws["C55"] = f"=SUMPRODUCT(({MG}<0)*{JG})/SUM({JG})"
for r in (53, 54, 55): ws.cell(row=r, column=3).font = Font(size=9, color="808080")
MOD_H, MOD_D, MOD_A = "$C$53", "$C$54", "$C$55"

# market de-vig + blend helpers
ws["C57"] = f"=IF({PMH}+{PMD}+{PMA}>0,{PMH}+{PMD}+{PMA},0)"          # overround
OVER = "$C$57"
ws["C58"] = f"=IF({OVER}=0,{MOD_H},{PMH}/{OVER})"                     # market iH
ws["C59"] = f"=IF({OVER}=0,{MOD_D},{PMD}/{OVER})"
ws["C60"] = f"=IF({OVER}=0,{MOD_A},{PMA}/{OVER})"
IH, ID, IA = "$C$58", "$C$59", "$C$60"
# blended (renormalised)
ws["C61"] = f"={WM}*{IH}+(1-{WM})*{MOD_H}"
ws["C62"] = f"={WM}*{ID}+(1-{WM})*{MOD_D}"
ws["C63"] = f"={WM}*{IA}+(1-{WM})*{MOD_A}"
ws["C64"] = "=$C$61+$C$62+$C$63"
BH, BD, BA, BS = "$C$61", "$C$62", "$C$63", "$C$64"

# ---- OUTPUT TABLE ----
ws["E4"] = "RESULTS"; ws["E4"].font = HDR; ws["E4"].fill = blue
ws.merge_cells("E4:J4")
heads = ["Outcome", "Model", "Market", "Blended (fair)", "Price paid", "Edge"]
for k, h in enumerate(heads):
    cc = ws.cell(row=5, column=5 + k, value=h); cc.font = HDR; cc.fill = blue; cc.alignment = ctr; cc.border = thin
rows_out = [
    ("Home win", MOD_H, IH, f"={BH}/{BS}", PMH),
    ("Draw",     MOD_D, ID, f"={BD}/{BS}", PMD),
    ("Away win", MOD_A, IA, f"={BA}/{BS}", PMA),
]
for i, (lbl, mod, mkt, blend, paid) in enumerate(rows_out):
    r = 6 + i
    ws.cell(row=r, column=5, value=lbl).font = BOLD
    ws.cell(row=r, column=6, value=f"={mod}")
    ws.cell(row=r, column=7, value=f"={mkt}")
    ws.cell(row=r, column=8, value=blend)
    ws.cell(row=r, column=9, value=f"={paid}")
    ws.cell(row=r, column=10, value=f"={blend.strip('=')}-{paid}")
    for col in range(6, 11):
        cell = ws.cell(row=r, column=col); cell.border = thin; cell.alignment = ctr
        if col in (6, 7, 8, 9): cell.number_format = "0.0%"
        if col == 10: cell.number_format = "+0.0%;-0.0%"
    ws.cell(row=r, column=8).fill = green; ws.cell(row=r, column=8).font = BOLD

# ---- BIG DRAW CALLOUT ----
ws.merge_cells("E11:J11")
ws["E11"] = "PROBABILITY OF A DRAW (blended fair)"
ws["E11"].font = HDR; ws["E11"].fill = navy; ws["E11"].alignment = ctr
ws.merge_cells("E12:G13")
ws["E12"] = f"=TEXT({BD}/{BS},\"0.0%\")"
ws["E12"].font = Font(size=26, bold=True, color="1F3864"); ws["E12"].alignment = ctr; ws["E12"].fill = green
ws.merge_cells("H12:J13")
ws["H12"] = (f'=IF(({BD}/{BS})-{PMD}>0.04,"DRAW UNDERPRICED → value BUY",'
             f'IF(({BD}/{BS})-{PMD}<-0.04,"DRAW OVERPRICED → avoid / SELL",'
             f'IF({PMD}=0,"(enter draw price for a verdict)","DRAW fairly priced → no edge")))')
ws["H12"].font = BIG; ws["H12"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
ws.merge_cells("E14:J14")
ws["E14"] = (f'=CONCATENATE("Model draw ",TEXT({MOD_D},"0.0%"),"  |  Market draw ",'
             f'TEXT({ID},"0.0%"),"  |  You pay ",TEXT({PMD}*100,"0"),"¢  |  Fair ",TEXT({BD}/{BS},"0.0%"))')
ws["E14"].alignment = ctr; ws["E14"].font = Font(italic=True)

# ====================================================== HOW TO USE sheet
hw = wb.create_sheet("How to use")
hw.sheet_view.showGridLines = False
hw.column_dimensions["A"].width = 100
steps = [
    ("HOW TO USE — 2026 World Cup Live Odds Calculator", True),
    ("", False),
    ("1.  Go to the 'Live Calculator' tab. Only type in the YELLOW cells.", False),
    ("2.  Pick Home team and Away team from the dropdowns (use the same spelling as the model).", False),
    ("3.  Enter the CURRENT score and the MINUTE (0 = kickoff, 94 = full time). As the game", False),
    ("     changes, update these and every number recalculates instantly.", False),
    ("4.  Enter the live Polymarket prices as decimals (27¢ → 0.27) for Home win, Draw, Away win.", False),
    ("     Leave them at 0 to see the model-only view.", False),
    ("5.  Read the GREEN cells: the blended fair probabilities, the big DRAW % box, and the verdict.", False),
    ("", False),
    ("WHAT THE NUMBERS MEAN", True),
    ("• Model   = the Dixon-Coles engine using the two teams + current score + minutes left.", False),
    ("• Market  = Polymarket's prices with the bookmaker margin removed ('de-vigged').", False),
    ("• Blended = the two combined (default 60% market / 40% model) — your fair estimate.", False),
    ("• Edge    = Blended fair − Price paid. Positive = underpriced (BUY). Need > +4% to act", False),
    ("            (covers spread/fees/model error).", False),
    ("• Blend weight: raise toward 0.8 in deep/liquid markets; lower toward 0.4 in thin ones.", False),
    ("", False),
    ("KEEPING IT CURRENT", True),
    ("• The team ratings live on the 'Ratings' tab. After each daily model refit, re-run", False),
    ("  scripts/build_excel.py to refresh them (or paste new attack/defence values in).", False),
    ("• For LIVE auto-pulled Polymarket prices, run scripts/polymarket_live.py (see project README).", False),
    ("", False),
    ("IMPORTANT", True),
    ("• This is a forecasting aid, not a guarantee. It cannot see injuries, red cards, momentum.", False),
    ("• Bet responsibly and only what you can afford to lose.", False),
]
for i, (txt, hd) in enumerate(steps):
    c = hw.cell(row=1 + i, column=1, value=txt)
    c.font = Font(size=13, bold=True, color="1F3864") if hd else Font(size=11)
    c.alignment = left

wb.save(OUT)
print("Saved", OUT)
print(f"  Ratings: {len(TEAMS)} teams | sheets: Live Calculator, Ratings, How to use")
