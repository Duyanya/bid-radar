"""省级主体检查与网络运营软件范围判定；不删除既有数据。"""

import re

NON_PROVINCE = [
    ("市分公司", ["分公司"]),                 # 北京公司丰台卢沟桥网格、文山分公司、凉山分公司
    ("专业子公司", ["中移动信息", "产业互联网", "视频科技", "沃音乐", "国际有限公司", "（新加坡）", "(新加坡)",
                    "终端有限公司", "中移信息技术", "中移服务", "在线营销服务中心",
                    "咪咕", "中移物联", "中移建设", "中移系统集成", "中移在线",
                    "中移互联网", "中移金科", "中移研究院", "苏研", "杭研",
                    "浙江融创", "中移资本", "中移财务"]),
    ("内部部门", ["纪委办", "工会", "党群", "办公室", "后勤", "机关"]),
]

DIRECT_UNITS = ("传输局", "长途电信传输局", "云网中心", "云网运营中心", "智能云网中心",
                "智能云网调度运营中心", "云网调度运营中心",
                "网络管理中心", "省网络管理中心", "网络操作维护中心", "网络运营中心",
                "研究院", "研发中心", "创新中心", "重点实验室", "技术研究中心")

OWNED_UNITS = ("传输局", "长途电信传输局", "云网中心", "云网运营中心", "智能云网中心",
               "智能云网调度运营中心", "云网调度运营中心",
               "网络操作维护中心", "省网络管理中心")

def check_province(title):
    """判断是否运营商省级主体。返回 (ok, reason)。"""
    # 必须能识别出运营商主体（集团 / 省级公司 / 省简称+运营商）
    STRONG = ("中国移动", "中国电信", "中国联通", "移动通信集团", "电信集团", "联通集团")
    PROV_SHORT = ("移动", "电信", "联通", "广电")

    # 明显的地市/区县主体
    CITY_PREFIX = ("宣城", "广德", "泉州", "休宁", "沙湖", "芜湖", "蚌埠", "阜阳",
                   "安庆", "马鞍山", "滁州", "宿州", "六安", "亳州", "池州", "铜陵", "黄山",
                   "贺州", "桂林", "南宁", "河池", "柳州", "梧州", "北海", "钦州", "防城港",
                   "贵港", "玉林", "百色", "来宾", "崇左", "都安", "富川", "绥化", "绥棱",
                   "毕节", "六盘水", "克拉玛依", "和田", "石家庄", "武汉", "清远", "徐州")
    # 省直属专业单位豁免：不算地市/分公司误杀（市分公司仍然排除）
    direct = [u for u in DIRECT_UNITS if u in title]
    if not any(o in title for o in ("电信", "移动", "联通", "铁塔")):
        # 标题没写运营商名：只认运营商专属单位（传输局/云网中心…），研究院这类不推断归属
        direct = [u for u in direct if u in OWNED_UNITS]
    if "分公司" in title:
        direct = []      # 市分公司不得靠单位名豁免（电信南京分公司传输局 仍属市分公司）
    # 把省直属单位名从标题里摘掉再做主体判定，避免「研究院」被当成「子公司」
    probe = title
    for u in direct:
        probe = probe.replace(u, "")

    if not direct and not any(o in title for o in STRONG + PROV_SHORT):
        return False, "非运营商主体"

    # 明显的地市/区县主体
    for c in (() if direct else CITY_PREFIX):
        for op in PROV_SHORT:
            if f"{c}{op}" in title or f"{c}市{op}" in title:
                return False, f"地市分公司:{c}{op}"

    # 单独出现的"电信/移动/联通"但前面紧跟地名 → 非省公司
    PROVINCES = ("北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
                 "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
                 "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
                 "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门")
    for op in (() if direct else PROV_SHORT):
        idx = title.find(op)
        if idx > 0:
            prefix = title[:idx]
            # 前缀是省名或含"中国/集团"等 → 省公司，放行
            if any(p in prefix for p in PROVINCES):
                continue
            if any(p in prefix for p in ("中国", "省", "集团", "股份", "通信")):
                continue
            # 前缀是2-4个汉字且不是省名 → 地市级
            if 2 <= len(prefix) <= 4:
                return False, f"疑似地市主体:{prefix}{op}"

    for cat, kws in NON_PROVINCE:
        if direct and cat in ("子公司", "分公司"):
            continue    # 省直属单位：传输局/云网中心/研究院 等，即便字面含"分公司"也放行
        hit = [k for k in kws if k in probe]
        if hit:
            return False, f"{cat}:{hit[:2]}"
    return True, ""

def classify(title, content=""):
    from network_scope import classify_network
    return classify_network(title, content)
