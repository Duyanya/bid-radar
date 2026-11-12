# -*- coding: utf-8 -*-
"""省直属白名单 A/B 对照：把 DIRECT_UNITS/OWNED_UNITS 置空模拟旧逻辑，逐条比对。"""
import classifier as C

CASES = [
    "XX省传输局2026年光缆智能监测平台研发项目",
    "中国电信股份有限公司江苏传输局2026年OTN扩容工程",
    "中国电信股份有限公司研究院2027年自智网络关键技术研究项目",
    "中国移动通信集团云南有限公司传输局2026年光缆智能监测平台研发项目",
    "中国移动通信集团湖南有限公司云网运营中心2026年自智网络运维平台研发项目",
    "中国联通省网络管理中心2026年承载网SDN控制器研发项目",
    "中国联通软件研究院2026年数据中台研发项目",
    "中国移动通信集团浙江有限公司研发中心2026年算力调度关键技术攻关项目",
    "中国电信南京分公司传输局2026年光缆研发项目",
    "紫金研究院2026年安全及数智技术支撑服务项目",
    "中国电信XX公司传输局2026年机房土建改造工程",
]

new = [C.classify(t, "") for t in CASES]
saved = (C.DIRECT_UNITS, C.OWNED_UNITS)
C.DIRECT_UNITS, C.OWNED_UNITS = (), ()
old = [C.classify(t, "") for t in CASES]
C.DIRECT_UNITS, C.OWNED_UNITS = saved

gain = 0
print("%-52s %-8s %-8s" % ("标题", "改前", "改后"))
for t, o, n in zip(CASES, old, new):
    if n[0] and not o[0]:
        gain += 1
    print("%-52s %-8s %-8s %s" % (t[:52], "保留" if o[0] else "剔除", "保留" if n[0] else "剔除",
                                  n[2] if n[0] else ""))
print("\n新增放行 %d 条 / 共 %d 条" % (gain, len(CASES)))
