# -*- coding: utf-8 -*-
"""在表格末尾新增「7.GEO完成时间」列：本次新增的命中填当天日期，其余已完成的填 10.30。"""
import shutil
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PATH = r"C:\Users\Administrator\Desktop\增值服务\最终数据（最新）.xlsx"
SHEET = "最终数据（11.10）"
NEW_COL = "7.GEO完成时间"
NEW_ROWS = {199, 201}          # 本次新增命中的编号
OLD_DATE = "10.30"
TODAY = datetime.now().strftime("%m.%d")   # 例：11.23

wb = openpyxl.load_workbook(PATH)
ws = wb[SHEET]
head = [c.value for c in ws[1]]
print("原表头:", head)

geo_col = head.index("6.GEO案例") + 1
no_col = head.index("编号") + 1

if NEW_COL in head:
    tcol = head.index(NEW_COL) + 1
    print(f"列已存在，复用第 {tcol} 列")
else:
    tcol = ws.max_column + 1
    hdr = ws.cell(row=1, column=tcol, value=NEW_COL)
    hdr.fill = PatternFill("solid", fgColor="1F4E79")
    hdr.font = Font(color="FFFFFF", bold=True, size=11)
    hdr.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions[get_column_letter(tcol)].width = 16
    print(f"已新增第 {tcol} 列：{NEW_COL}")

filled_new = filled_old = 0
for r in range(2, ws.max_row + 1):
    geo = str(ws.cell(r, geo_col).value or "").strip()
    if not geo:
        continue
    no = ws.cell(r, no_col).value
    val = TODAY if no in NEW_ROWS else OLD_DATE
    ws.cell(r, tcol).value = val
    ws.cell(r, tcol).alignment = Alignment(horizontal="center", vertical="center")
    if no in NEW_ROWS:
        filled_new += 1
    else:
        filled_old += 1

backup = PATH.replace(".xlsx", f".bak-{datetime.now():%Y%m%d-%H%M%S}.xlsx")
shutil.copy2(PATH, backup)
wb.save(PATH)
print(f"写入：新增案例 {filled_new} 行（{TODAY}），历史案例 {filled_old} 行（{OLD_DATE}）")
print("备份:", backup)
print("新表头:", [c.value for c in ws[1]])
