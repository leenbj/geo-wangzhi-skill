# -*- coding: utf-8 -*-
"""主表 <-> geo-shaicha 检测表的桥（适配 2026-11-19 后的 7 列表结构）。

主表列：编号 / 1.注册域名 / 2.企业名称 / 3.简称 / 4.企业资料 / 5.新闻链接 / 6.GEO案例

make-check : 挑出「6.GEO案例」为空的行，生成 geo 能吃的检测副本（域名规范化、简称补齐）
writeback  : 把检测结果按编号回写主表的「6.GEO案例」（只写这一列，不碰其他列）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime

import openpyxl

MASTER = os.environ.get("GEO_XLSX") or r"C:\Users\Administrator\Desktop\增值服务\最终数据（最新）.xlsx"
SHEET = os.environ.get("GEO_SHEET") or "最终数据（11.10）"
H = {"no": "编号", "domain": "1.注册域名", "company": "2.企业名称",
     "short": "3.简称", "info": "4.企业资料", "news": "5.新闻链接", "geo": "6.GEO案例",
     "geotime": "7.GEO完成时间"}

SPLIT = re.compile(r"[、,，;；/|和]")


def norm_domain(raw: str) -> tuple[str, str]:
    original = (raw or "").strip()
    first = SPLIT.split(original)[0].strip()
    if not first:
        return "", original
    first = re.sub(r"\s+", "", first)
    if not first.endswith(".网址"):
        if re.search(r"\.[a-zA-Z]{2,}$", first):
            return first, original
        first += ".网址"
    return first, original


def short_name(name: str) -> str:
    s = re.sub(r"[（(][^）)]*[）)]", "", name or "").strip()
    s = re.sub(r"(股份)?有限(责任)?公司$|集团$|公司$", "", s)
    s = re.sub(r"(厂|店|商行|中心|合作社|经营部|服务部|工作室|事务所|门市部|餐厅)$", "", s)
    s = re.sub(r"^(北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|四川|贵州|云南|陕西|甘肃|青海|宁夏|新疆|内蒙古|西藏)(省|市|自治区)?", "", s)
    return s.strip("·-— ") or (name or "")


def cols(ws) -> dict:
    head = [c.value for c in ws[1]]
    idx = {}
    for key, name in H.items():
        if name in head:
            idx[key] = head.index(name) + 1
    missing = [H[k] for k in ("no", "domain", "company", "geo") if k not in idx]
    if missing:
        sys.exit(f"主表缺少列 {missing}；实际表头 {head}")
    return idx


def cmd_make_check(args):
    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    ws = wb[args.sheet]
    idx = cols(ws)
    picked = []
    for r in range(2, ws.max_row + 1):
        geo = str(ws.cell(r, idx["geo"]).value or "").strip()
        if geo:
            continue
        news = str(ws.cell(r, idx["news"]).value or "").strip() if "news" in idx else ""
        seg = "B" if "http" in news else "A"
        if args.segment and seg not in args.segment.split(","):
            continue
        dom, raw = norm_domain(str(ws.cell(r, idx["domain"]).value or ""))
        comp = str(ws.cell(r, idx["company"]).value or "").strip()
        if not dom or not comp:
            continue
        picked.append({"row": r, "no": ws.cell(r, idx["no"]).value, "domain": dom,
                       "raw_domain": raw, "company": comp, "segment": seg,
                       "short": str(ws.cell(r, idx["short"]).value or "").strip() if "short" in idx else ""})
    if args.limit:
        picked = picked[: args.limit]

    out = openpyxl.Workbook()
    ows = out.active
    ows.title = "Sheet1"
    ows.append(["编号", "域名", "公司名称", "公司简称", "原始域名"])
    for p in picked:
        ows.append([p["no"], p["domain"], p["company"], p["short"] or short_name(p["company"]), p["raw_domain"]])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out.save(args.out)
    side = os.path.splitext(args.out)[0] + ".rows.json"
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(picked, fh, ensure_ascii=False, indent=1)
    print(f"选定 {len(picked)} 行 -> {args.out}")
    print("  编号:", ", ".join(str(p["no"]) for p in picked[:15]) + (" ..." if len(picked) > 15 else ""))


def cmd_writeback(args):
    cwb = openpyxl.load_workbook(args.checked, data_only=True)
    cws = cwb["Sheet1"]
    chead = [c.value for c in cws[1]]
    need = ["编号", "命中平台"]
    missing = [n for n in need if n not in chead]
    if missing:
        sys.exit(f"检测表缺少列 {missing}；实际 {chead}")
    ci = {n: chead.index(n) + 1 for n in chead if n}
    results = []
    for r in range(2, cws.max_row + 1):
        results.append({
            "no": cws.cell(r, ci["编号"]).value,
            "company": cws.cell(r, ci["公司名称"]).value if "公司名称" in ci else "",
            "hits": str(cws.cell(r, ci["命中平台"]).value or "").strip(),
            "state": str(cws.cell(r, ci["状态"]).value or "").strip() if "状态" in ci else "",
        })

    mwb = openpyxl.load_workbook(args.xlsx)
    mws = mwb[SHEET]
    idx = cols(mws)
    by_no = {}
    for r in range(2, mws.max_row + 1):
        by_no.setdefault(mws.cell(r, idx["no"]).value, []).append(r)

    changed = []
    for res in results:
        rows = by_no.get(res["no"], [])
        if not rows:
            print(f"  !! 编号 {res['no']} 在主表找不到")
            continue
        if not res["hits"]:
            continue
        val = f"已完成（{res['hits']}）"
        for r in rows:
            old = str(mws.cell(r, idx["geo"]).value or "").strip()
            if old.startswith("已完成"):
                continue
            changed.append((r, old, val))
            if not args.dry_run:
                mws.cell(r, idx["geo"]).value = val
                if "geotime" in idx:
                    mws.cell(r, idx["geotime"]).value = datetime.now().strftime("%m.%d")
        # 同名合并：命中结果传播到同名企业
        if args.merge_same_name and "company" in idx and res["company"]:
            for r in range(2, mws.max_row + 1):
                if str(mws.cell(r, idx["company"]).value or "").strip() != str(res["company"]).strip():
                    continue
                old = str(mws.cell(r, idx["geo"]).value or "").strip()
                if old.startswith("已完成"):
                    continue
                changed.append((r, old, val))
                if not args.dry_run:
                    mws.cell(r, idx["geo"]).value = val
                    if "geotime" in idx:
                        mws.cell(r, idx["geotime"]).value = datetime.now().strftime("%m.%d")

    for row, old, new in changed:
        print(f"  r{row}: {old!r} -> {new!r}")
    if args.dry_run:
        print(f"[dry-run] 将改 {len(changed)} 行，未落盘")
    else:
        if changed:
            backup = args.xlsx.replace(".xlsx", f".bak-{datetime.now():%Y%m%d-%H%M%S}.xlsx")
            import shutil
            shutil.copy2(args.xlsx, backup)
            mwb.save(args.xlsx)
            print(f"已写回 {len(changed)} 行；备份 {backup}")
        else:
            print("没有需要写回的命中")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mc = sub.add_parser("make-check")
    mc.add_argument("--xlsx", default=MASTER)
    mc.add_argument("--sheet", default=SHEET)
    mc.add_argument("--segment", default="")
    mc.add_argument("--limit", type=int, default=0)
    mc.add_argument("--out", required=True)
    mc.set_defaults(func=cmd_make_check)

    wb = sub.add_parser("writeback")
    wb.add_argument("--xlsx", default=MASTER)
    wb.add_argument("--checked", required=True)
    wb.add_argument("--dry-run", action="store_true")
    wb.add_argument("--merge-same-name", action="store_true", default=True)
    wb.set_defaults(func=cmd_writeback)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
