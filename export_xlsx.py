# -*- coding: utf-8 -*-
"""按省份导出「系统 + 建设厂商」Excel。

数据源：data/bids.db（225 条，其中 89 条已公示中选/成交厂商）。
输出：各省系统与建设厂商.xlsx（4 个工作表）
"""
import sqlite3
import datetime as dt

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DB = "data/bids.db"
OUT = "各省系统与建设厂商.xlsx"

GROUP = {"集团": "集团总部", "总部": "集团总部",
         "研究院": "集团直属", "联通智网创新中心": "集团直属"}

THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=10)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def load():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        """select id,title,notice_type,publish_date,deadline,amount_value,winner,
                  operator,region,build_content,url,snapshot_path,status
           from bids order by publish_date desc""")]
    con.close()
    for r in rows:
        rg = (r["region"] or "").strip() or "未标注"
        r["省份"] = GROUP.get(rg, rg)
        r["系统"] = (r["build_content"] or "").strip() or (r["title"] or "").strip()
        r["厂商"] = (r["winner"] or "").strip()
    return rows


def head(ws, cols, widths):
    ws.append(cols)
    for i, (_c, w) in enumerate(zip(cols, widths), start=1):
        cell = ws.cell(row=1, column=i)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = CENTER
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"


def body(ws, ncol, money_cols=(), center_cols=()):
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=ncol):
        for cell in row:
            cell.font = BODY_FONT
            cell.border = BORDER
            cell.alignment = CENTER if cell.column in center_cols else LEFT
        ws.row_dimensions[row[0].row].height = 30
    for c in money_cols:
        for cell in ws[get_column_letter(c)][1:]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right", vertical="center")
    ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{ws.max_row}"


def main():
    rows = load()
    wb = Workbook()

    # ---------- Sheet1 中标明细 ----------
    ws = wb.active
    ws.title = "中标明细"
    cols = ["省份", "运营商", "系统/建设内容", "建设厂商", "公告类型",
            "发布日期", "金额(元)", "金额(万元)", "项目标题", "公告链接"]
    widths = [10, 10, 46, 30, 12, 12, 14, 12, 56, 30]
    head(ws, cols, widths)
    won = [r for r in rows if r["厂商"]]
    won.sort(key=lambda r: r["publish_date"] or "", reverse=True)          # 先按日期倒序
    won.sort(key=lambda r: ((r["省份"] in ("集团总部", "集团直属")), r["省份"]))  # 再按省份，集团排最后
    for r in won:
        amt = r["amount_value"]
        ws.append([r["省份"], r["operator"], r["系统"], r["厂商"], r["notice_type"],
                   r["publish_date"], amt,
                   round(amt / 10000.0, 2) if isinstance(amt, (int, float)) and amt else None,
                   r["title"], r["url"]])
    body(ws, len(cols), money_cols=(7, 8), center_cols=(1, 2, 5, 6))

    # ---------- Sheet2 全部在库项目 ----------
    ws9 = wb.create_sheet("全部在库项目")
    cols9 = ["省份", "运营商", "系统/建设内容", "建设厂商", "公告类型",
             "发布日期", "金额(元)", "项目标题", "公告链接"]
    widths9 = [10, 10, 44, 26, 12, 12, 13, 54, 28]
    head(ws9, cols9, widths9)
    allrows = sorted(rows, key=lambda r: ((r["省份"] in ("集团总部", "集团直属")), r["省份"], r["publish_date"] or ""),
                     reverse=False)
    for r in allrows:
        amt = r["amount_value"]
        ws9.append([r["省份"], r["operator"], r["系统"], r["厂商"] or "未公示", r["notice_type"],
                    r["publish_date"], amt, r["title"], r["url"]])
    body(ws9, len(cols9), money_cols=(7,), center_cols=(1, 2, 5, 6))

    # ---------- Sheet3 省份汇总 ----------
    ws2 = wb.create_sheet("省份汇总")
    cols2 = ["省份", "在库项目数", "已公示厂商数", "涉及厂商数", "主要厂商（按中标数）", "涉及系统（前 6）"]
    widths2 = [12, 12, 14, 12, 46, 70]
    head(ws2, cols2, widths2)
    provinces = sorted({r["省份"] for r in rows},
                       key=lambda p: (p in ("集团总部", "集团直属"), p))
    for p in provinces:
        sub = [r for r in rows if r["省份"] == p]
        wsub = [r for r in sub if r["厂商"]]
        cnt = {}
        for r in wsub:
            for v in r["厂商"].split("、"):
                cnt[v] = cnt.get(v, 0) + 1
        top = "、".join(f"{k}({v})" for k, v in sorted(cnt.items(), key=lambda x: -x[1])[:5])
        sysl = []
        for r in sub:
            s = r["系统"][:26]
            if s and s not in sysl:
                sysl.append(s)
        ws2.append([p, len(sub), len(wsub), len(cnt), top or "—", "；".join(sysl[:6]) or "—"])
    body(ws2, len(cols2), center_cols=(1, 2, 3, 4))

    # ---------- Sheet3 厂商中标榜 ----------
    ws3 = wb.create_sheet("厂商中标榜")
    cols3 = ["建设厂商", "中标项目数", "覆盖省份数", "覆盖省份", "对应系统"]
    widths3 = [34, 12, 12, 40, 80]
    head(ws3, cols3, widths3)
    vendor = {}
    for r in rows:
        if not r["厂商"]:
            continue
        for v in r["厂商"].split("、"):
            d = vendor.setdefault(v, {"n": 0, "p": set(), "s": []})
            d["n"] += 1
            d["p"].add(r["省份"])
            if r["系统"][:26] not in d["s"]:
                d["s"].append(r["系统"][:26])
    for v, d in sorted(vendor.items(), key=lambda x: -x[1]["n"]):
        ws3.append([v, d["n"], len(d["p"]), "、".join(sorted(d["p"])), "；".join(d["s"][:4])])
    body(ws3, len(cols3), center_cols=(2, 3))

    # ---------- Sheet4 待公示 ----------
    ws4 = wb.create_sheet("结果未公示厂商")
    cols4 = ["省份", "运营商", "公告类型", "发布日期", "项目标题", "系统/建设内容", "公告链接", "原因"]
    widths4 = [10, 10, 14, 12, 56, 40, 30, 22]
    head(ws4, cols4, widths4)
    pend = [r for r in rows if not r["厂商"] and
            ("结果" in (r["notice_type"] or "") or "候选人" in (r["notice_type"] or ""))]
    for r in pend:
        reason = "联通候选人公示接口需登录态" if r["operator"] == "中国联通" else (
                 "电信详情接口 401，仅列表字段" if r["operator"] == "中国电信" else "正文未含中选人字段")
        ws4.append([r["省份"], r["operator"], r["notice_type"], r["publish_date"],
                    r["title"], r["系统"], r["url"], reason])
    body(ws4, len(cols4), center_cols=(1, 2, 3, 4))

    # 说明页
    ws5 = wb.create_sheet("说明")
    ws5.column_dimensions["A"].width = 100
    ws5["A1"] = "投标雷达 · 各省系统与建设厂商"
    ws5["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    lines = [
        f"导出时间：{dt.datetime.now():%Y-%m-%d %H:%M}",
        f"数据源：中国移动 / 中国电信 / 中国联通招标网公开公告（本地 SQLite 快照）",
        f"在库项目 {len(rows)} 条；已公示中选/成交厂商 {len(won)} 条；涉及厂商 {len(vendor)} 家；覆盖 {len(provinces)} 个省份/单位",
        "",
        "字段口径：",
        "  系统/建设内容：从公告正文提炼的建设内容名称（非标题照抄），不含预算、资格、工期等要素。",
        "  建设厂商：公告中的中选人 / 中标人 / 成交供应商 / 第一中选候选人；多个标包用「、」连接。",
        "  金额：公告公开的预算或中选金额，单位元（空=未公示），万元列为换算值。",
        "  省份：省公司所在省份；集团总部与集团直属（研究院、智网创新中心）单列。",
        "",
        "未覆盖说明（如实标注，不编造）：",
        "  中国联通 6 条候选人公示需登录态接口，正文未取到 → 厂商列为空，见「结果未公示厂商」表。",
        "  中国电信详情接口持续 401，仅能取列表字段 → 厂商多数未公示。",
        "  采购公告 / 询比公告尚未开标，本身没有中选厂商（不在「中标明细」表内）。",
    ]
    for i, t in enumerate(lines, start=3):
        ws5[f"A{i}"] = t
        ws5[f"A{i}"].font = Font(name="微软雅黑", size=10, bold=(i == 3))
    ws5["A3"].font = Font(name="微软雅黑", size=10, bold=True)

    wb.save(OUT)
    print(f"已生成 {OUT}")
    print(f"  中标明细 {len(won)} 行 / 省份汇总 {len(provinces)} 行 / 厂商 {len(vendor)} 家 / 待公示 {len(pend)} 行")


if __name__ == "__main__":
    main()
