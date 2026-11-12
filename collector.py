"""抓取器：Playwright 真实浏览器绕过 WAF，抓取移动/电信招标公告并落库。

设计要点：
1. 官网有 WAF（阿里云盾/瑞数），requests 直接被拦 -> 必须用真实浏览器
2. 电信有 IP 限流 -> 页间强制 sleep
3. 金额列表接口不返回 -> 进详情页正则抽取，抽不到留空（不编造）
4. 抓到的详情 HTML 存快照，官网下线后仍可查
"""
import re, time, random, json, sys, html as htmllib, base64, io
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import db
import classifier
from pypdf import PdfReader

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def launch(p):
    b = p.chromium.launch(headless=True,
                          args=["--disable-blink-features=AutomationControlled",
                                "--no-sandbox"])
    ctx = b.new_context(locale="zh-CN", user_agent=UA,
                        viewport={"width": 1440, "height": 900},
                        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    pg = ctx.new_page()
    pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return b, pg


# ---------------- 金额解析 ----------------
AMT_PATTERNS = [
    r"(?:预算|概算|采购金额|项目金额|合同估算价|最高限价|控制价|限价)[^\d]{0,10}([0-9][0-9,，.]*)\s*(万元|万|亿元|亿|元)",
    r"(?:金额|总价)[^\d]{0,6}([0-9][0-9,，.]*)\s*(万元|万|亿元|亿|元)",
    r"([0-9][0-9,，.]*)\s*(万元|亿元)",
]
UNIT = {"元": 1, "万": 1e4, "万元": 1e4, "亿": 1e8, "亿元": 1e8}


def fmt_amount(v):
    """把元为单位的数值格式化成易读文本：亿/万/元。"""
    if not v:
        return None
    if v >= 1e8:
        s = f"{v / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{s} 亿元"
    if v >= 1e4:
        s = f"{v / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{s} 万元"
    return f"{v:,.0f} 元"


def amount_to_value(txt):
    """把 "239.40 万元" / "2.63 亿元" 这类文本转回元为单位的数值。"""
    if not txt:
        return None
    m = re.search(r"([\d.]+)\s*(亿元|亿|万元|万|元)", txt)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v * UNIT.get(m.group(2), 1)


def parse_amount(text):
    """识别金额，返回纯数字（元为单位的整数），识别不到返回 None。

    只输出数字，不带单位/描述。前端按需显示。
    """
    if not text:
        return None
    t = re.sub(r"\s+", " ", text)
    for pat in AMT_PATTERNS:
        for m in re.finditer(pat, t):
            num, unit = m.group(1), m.group(2)
            try:
                v = float(num.replace(",", "").replace("，", ""))
            except ValueError:
                continue
            v *= UNIT.get(unit, 1)
            if v < 1000 or v > 1e11:   # 过滤明显误匹配
                continue
            return int(round(v))
    return None


WINNER_PATTERNS = [
    # 标准写法：中选人：XXX / 成交人：XXX / 中标人：XXX
    r"(?:中选人|成交人|中标人|中选单位|成交单位|中标单位|中选供应商|成交供应商|中标供应商)[：:\s]*([^\s，,。；;、）（()]{2,50}(?:公司|集团|中心|院|所|厂|社|台|部|局|大学|学校))",
    # 带序号：1.XXX公司
    r"(?:中选人|成交人|中标人)[：:\s]*\d+[.、．]\s*([^\s，,。；;、]{2,50}(?:公司|集团|中心|院|所|厂|社|台|部|局))",
    # 标包N的中选人：XXX
    r"标包\s*\d+\s*的(?:中选人|成交人|中标人)[：:\s]*([^\s，,。；;、]{2,50}(?:公司|集团|中心|院|所))",
    # 兜底：任意位置的中选人后跟机构名
    r"(?:中选|成交|中标)[^\n]{0,15}?([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40}(?:有限公司|股份有限公司|集团|研究院|设计院))",
]

# 公司名后常见粘连词，用于截断
CUT_WORDS = ("采购人", "招标人", "招标代理", "代理机构", "公示期", "公示时间",
             "成交份额", "中选份额", "中标份额", "金额", "日期", "特此")


def _cut_name(w):
    """截断公司名后面粘连的说明文字。"""
    for cw in CUT_WORDS:
        i = w.find(cw)
        if i > 3:
            w = w[:i]
    # 按机构后缀收尾（贪婪到最后一个后缀，避免"集团"抢先截断"集团有限公司"）
    m = re.search(r"^(.{2,60}(?:有限公司|股份有限公司|有限责任公司|公司|集团|研究院|设计院|研究所|中心))", w)
    if m:
        return m.group(1)
    return w


WINNER_KEYS = ("中选人", "中选供应商", "中选单位", "中选厂商", "成交供应商", "成交人",
               "成交单位", "中标人", "中标供应商", "中标单位", "推荐的中选人")
_GOOD_TAIL = ("公司", "集团", "研究院", "设计院", "厂", "中心", "事务所", "合伙", "商行",
              "银行", "大学", "学院")


def parse_winner(text):
    """抽取中选/成交厂商。

    支持「包1的中选人：\\n深圳市名通科技股份有限公司」这种标点后换行的写法，
    多个标包的结果合并为「A、B」。排除「中选人数量1个」「详见附件」这类噪声。
    """
    if not text:
        return None
    # 归一化：标点后的硬换行拼回同一行（PDF 常见断行）
    flat = re.sub(r"(?<=[：:，,。；;、])\s*\n\s*", "", text)
    flat = re.sub(r"(?<=[\u4e00-\u9fa5])\s*\n\s*(?=[\u4e00-\u9fa5])", "", flat)
    flat = re.sub(r"\s+", " ", flat)

    BAD = ("数量", "份额", "详见", "见附件", "另行", "公示", "序号")
    found = []
    for key in WINNER_KEYS:
        pat = re.escape(key) + r"\s*(?:名称)?\s*[：:为]?\s*([^，。；;、\s]{4,60})"
        for m in re.finditer(pat, flat):
            w = m.group(1).strip(" ：:，,。.．、0123456789（）()")
            w = re.sub(r"^[（(]?\d+[)）]?[.、．]?\s*", "", w)
            w = _cut_name(w)   # 先剁掉「…采购人/招标代理机构…」这类粘连的后半截
            if not (4 <= len(w) <= 60):
                continue
            if any(b in w[:4] for b in BAD):
                continue
            # 必须是机构名，避免把「1个」「无」当厂商
            if not any(t in w for t in _GOOD_TAIL):
                continue
            if w and w not in found:
                found.append(w)
    if not found:
        return None
    return "、".join(found[:3])


BUILD_KEYS = [
    "项目建设内容", "建设内容", "采购内容", "采购清单", "项目内容", "项目概况",
    "采购范围", "招标范围", "招标内容", "服务内容", "项目简介", "需求内容",
    "采购标的", "采购规模", "项目规模",
]


# 泛词：建设内容里不允许出现（用户 2026-11-12：不要「项目」「询比」这类字眼）
_GENERIC_WORDS = ("公开询比", "公开招标", "竞争性谈判", "单一来源", "集中采购", "框架采购",
                  "询比", "比选", "招标", "采购", "购置", "项目", "公告", "公示",
                  "结果", "中选", "中标", "成交", "研发", "研究", "谈判", "服务采购")


# 正文里不是建设内容的条款（预算/工期/评审/资格…）
_BODY_NOISE = ("预算", "万元", "不含税", "含税", "满足期", "工期", "服务期", "合同期",
               "签订", "付款", "支付", "评审", "评分", "资格", "投标人", "应答人",
               "供应商应", "详见", "如下", "见附件", "备注", "税率", "报价", "开标")


def _balance_paren(s):
    """括号配平：删词/截断造成的半截括号，从最后一个未闭合左括号处断开。"""
    for _ in range(8):
        a = s.count("（") + s.count("(")
        b = s.count("）") + s.count(")")
        if a == b:
            break
        if a > b:
            i = max(s.rfind("（"), s.rfind("("))
            if i <= 0:
                s = re.sub(r"[（(]", "", s)
            else:
                s = s[:i]
        else:
            s = s.replace("）", "", 1) if "）" in s else s.replace(")", "", 1)
    return s


def clean_build(s):
    """把项目名清洗成『建设内容 / 系统名称』：去泛词、期次、公告后缀。"""
    if not s:
        return None
    s = re.sub(r"[（(]\s*(第[一二三四五六七八九十\d]+次|[一二三四五六七八九十\d]+次|二次|三次|五次|"
               r"重新招标|非标|一采非标)\s*[)）]", "", s)
    for g in _GENERIC_WORDS:
        s = s.replace(g, "")
    s = re.sub(r"^(本项目|本次|该项目|该|为|对|关于|进行|开展)[：:，、]?", "", s)
    s = re.sub(r"[（(]\s*(第?[一二三四五六七八九十\d]+(次|期|批|阶段)|二次|重新招标|非标|一采非标)\s*[)）]", "", s)
    s = re.sub(r"[（(]\s*[)）]", "", s)
    s = re.sub(r"[，、]{2,}", "，", s)
    s = s.strip(" 　_-—–，、（）:《》|｜:：;；。 ")
    if len(s) < 4:
        return None
    s = _balance_paren(s)
    if len(s) > 60:
        cut = s[:60]
        m = max(cut.rfind("）"), cut.rfind("、"))
        s = cut[:m + 1] if m > 30 else cut
        s = _balance_paren(s)
    return s.strip(" 　_-—，、（）|｜")


def _from_body_core(text):
    """正文里『建设内容 / 采购内容 / 项目概况』后的第一段有效描述。"""
    if not text:
        return None
    flat = re.sub(r"(?<=[\u4e00-\u9fa5，、；：])\n(?=[\u4e00-\u9fa5])", "", text)
    flat = re.sub(r"[ \t\u3000]+", " ", flat)
    for key in BUILD_KEYS:
        for m in re.finditer(key + r"\s*[：:]", flat):
            seg = flat[m.end():m.end() + 400]
            for clause in re.split(r"[。；\n]", seg):
                c = clause.strip(" \u3000:：，、")
                c = re.sub(r"^(本项目|本次|该项目|主要|拟|将|需|包括|包含|采购|建设)[：:]?", "", c)
                if not (4 <= len(c) <= 80):
                    continue
                # 条款编号（1）/1.1.1/一、）开头的多是流程性条款，不是建设内容
                if re.match(r"^\s*(\d+(\.\d+)*[.、）)]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.])", c):
                    continue
                if any(n in c for n in (_NOISE + _BODY_NOISE)) or any(p in c for p in _EMPTY_PHRASES):
                    continue
                if re.fullmatch(r"[\d\s、，.%（）()\-]+", c):
                    continue
                return c[:60]
    return None


_PROCESS_WORDS = ("框架协议", "截止时间", "执行完毕", "自动终止", "终止", "投标", "应答",
                  "评审", "付款", "保证金", "签订", "工作量", "人天", "标准功能", "功能点",
                  "违约", "税率", "发票", "异议", "澄清", "中标通知书", "招标文件", "服务期")

# 建设内容的落点：系统/平台类名词
_SYS_NOUN = ("系统", "平台", "中心", "模块", "引擎", "中台", "大脑", "门户", "工作台",
             "软件", "沙盘", "可视化", "数据库", "算法", "模型")


def _valid_body_build(c):
    """正文候选只有长得像『系统/平台名』才用，否则宁可走标题。

    实测教训：正文首段常是合同条款（框架协议/截止时间）或需求条款（二是满足…），
    按段落长度截取会把这类垃圾当建设内容。
    """
    if not c or not (6 <= len(c) <= 30):
        return None
    if any(x in c for x in ("，", "。", "；", "：", "“", "”")):
        return None
    if any(w in c for w in _PROCESS_WORDS):
        return None
    if re.match(r"^(一是|二是|三是|四是|五是|首先|其次|最后|如果|若|如因|根据|按照|同时|"
                r"其中|在|对|为|由|经|\d|[（(])", c):
        return None
    if not any(n in c for n in _SYS_NOUN):
        return None
    return c


# 建设动作 + 网元/网络技术词 → 正文里的「技术方案型」建设内容
_BUILD_VERBS = ("上收", "迁移", "搬迁", "割接", "扩容", "新建", "改造", "升级", "部署",
                "替换", "退网", "整合", "融合", "打通", "承载", "上云", "入云", "开通",
                "并网", "下沉")
_TECH_NOUNS = ("HSS", "UDM", "5GC", "4G", "5G", "UPF", "SMF", "AMF", "MME", "SGW", "PGW",
               "网元", "核心网", "承载网", "传输网", "接入网", "城域网", "骨干网", "基站",
               "切片", "专网", "资源池", "网管", "信令", "机房", "光纤", "光缆", "波分",
               "OTN", "SPN", "IP网", "云网", "算网", "中台")
_EVO_BAD = _PROCESS_WORDS + ("预算", "限价", "资格", "应答人", "投标人", "代理机构",
                             "不含税", "税率", "金额", "有效期", "保证金", "评审",
                             "以下简称", "计划实施", "采购人", "采购代理", "编号",
                             "项目概况", "详见", "见附件")


_ENUM_RE = re.compile(r"^(?:一是|二是|三是|四是|五是|六是|七是|八是|其一|其二|其三|其四)")


def _from_body_enum(text):
    """正文用「一是/二是/三是/四是」列举建设能力时，整段保留。

    这类列举就是公告披露的建设内容本身（智能城域网纳管、CPE 自动上线、
    跨域专线开通、FlexE 切片管理等），不能压成标题，也不能只留第一句。
    """
    if not text:
        return None
    flat = re.sub(r"[ \t\u3000]+", " ", text)
    items = []
    for clause in re.split(r"[\n。；;]", flat):
        c = clause.strip(" \u3000:：，、")
        if not _ENUM_RE.match(c):
            continue
        if not (12 <= len(c) <= 300):
            continue
        if any(b in c for b in ("预算", "限价", "资格", "应答人", "投标人", "保证金", "税率")):
            continue
        for w in ("询比", "招标", "公告", "标包", "采购项目", "本项目"):
            c = c.replace(w, "")
        c = re.sub(r"[（(]\s*不含税\s*[)）]", "", c).strip(" ：:，、")
        if c not in items:
            items.append(c)
    if len(items) < 3:
        return None
    return "；".join(items)[:500]


def _evo_ok(c):
    """挡住「物资清单行/章节名/编号条款/PDF断行碎片/标题重复」这类伪建设内容。"""
    if ":" in c or "：" in c or "_" in c or ";" in c:
        return False
    if re.match(r"^[调对将按经由从于在为由和及等又并各本]", c):
        return False          # 被截断的半句（调各部门进行…）
    if re.match(r"^[（(]?[一二三四五六七八九十\d]+[)）、.]", c):
        return False
    if re.match(r"^(一是|二是|三是|四是|五是|首先|其次|同时|此外|另外|概况|概括|总的来说)", c):
        return False
    if any(x in c for x in ("中国移动通信集团", "中国联合网络通信", "中国电信股份", "中国铁塔股份")):
        return False          # 正文里的主体/标题重复
    han = len(re.findall(r"[一-龥]", c))
    if han / max(len(c), 1) < 0.55:
        return False          # 物资清单/规格表
    if len(re.findall(r"[一-龥]\s[一-龥]", c)) >= 2:
        return False          # PDF 转文本断行碎片
    return True


def _from_body_evo(text):
    """正文里「建设动作 + 网元/网络技术词」的句子。

    HSS 上收至 UDM、5GC 网元搬迁、3/4G 业务迁移至 UDM 这类描述属于网络域建设内容，
    不因出现设备型号（HSS/UDM）、厂家名（中兴/华为）而按「设备采购」剔除。
    """
    if not text:
        return None
    flat = re.sub(r"[ \t\u3000]+", " ", text)
    out = []
    for clause in re.split(r"[。；\n]", flat):
        c = clause.strip(" \u3000:：，、;")
        c = re.sub(r"^\d+(\.\d+)*\s*", "", c)                 # 1.2.1 这类条款编号
        for _ in range(3):     # 「根据…，本期工程将…」要剥两轮
            c2 = re.sub(r"^(根据[^，。]{0,40}[，,]|因[^，。]{0,30}[，,]|本期工程|本次工程|本工程|"
                        r"本次|其中|拟|将|对)", "", c).strip()
            if c2 == c:
                break
            c = c2
        c = re.sub(r"[（(]\s*不含税\s*[)）]", "", c)
        for w in ("询比", "招标", "公告", "标包", "采购项目", "本项目", "项目"):
            c = c.replace(w, "")
        c = re.sub(r"\s{2,}", " ", c).strip(" ：:，、")
        if not (12 <= len(c) <= 160):
            continue
        if not any(v in c for v in _BUILD_VERBS):
            continue
        if sum(1 for t in _TECH_NOUNS if t in c) < 2:
            continue          # 至少两个技术词，挡掉「承载网集成服务」这类标题重复句
        if any(b in c for b in _EVO_BAD):
            continue
        if not _evo_ok(c):
            continue
        if c not in out:
            out.append(c)
        if len(out) >= 2:
            break
    return "；".join(out) if out else None


_SEC_START = ("采购内容", "建设内容", "招标范围", "采购范围", "项目概况", "工程概况",
              "建设规模", "本期工程", "采购需求", "项目内容", "建设目标", "服务内容")
_SEC_STOP = ("投标人资格", "资格要求", "供应商资格", "应答人资格", "投标人须知", "评审办法",
             "评标办法", "评分办法", "获取招标文件", "获取询比文件", "获取采购文件",
             "应答文件的递交", "投标文件的递交", "开标", "联系方式", "公告发布", "监督部门")
# 条款/流程/商务句：不是建设内容
_BDROP = ("资格", "业绩", "财务", "信誉", "保证金", "递交", "截止时间", "开标", "评审", "评标",
          "评分", "中标人", "中选人", "付款", "违约", "保密", "异议", "投诉", "联系电话",
          "邮箱", "报名", "售价", "发票", "项目编号", "招标人", "采购人", "代理机构",
          "投标人", "应答人", "供应商", "服务周期", "实施地点", "实施地域", "质量标准",
          "承包方式", "计划工期", "合同有效期", "限价", "预算", "资金", "人天", "份额",
          "工期", "试运行", "合同生效", "上线后", "投标报价", "报价", "天数", "保修",
          "合同签订", "进度安排", "服务类别", "咨询成果", "服务商应具备", "付款方式", "验收")
# 网域/建设相关性词：命中才算建设内容候选
_BNET = ("网", "专线", "切片", "基站", "核心网", "网元", "平台", "系统", "中台", "编排",
         "承载", "传输", "接入", "带宽", "光缆", "云", "5G", "FlexE", "CMNET", "DCN",
         "OSS", "O域", "B域", "运维", "运营", "监控", "告警", "资源", "数据", "智能",
         "算法", "仿真", "孪生", "沙盘", "工作台", "APP", "能力", "组网", "城域网")


def _norm_body(t):
    """正文归一：合并 PDF/HTML 折断的行，去掉多余空白。"""
    t = t.replace("\r", "")
    t = re.sub(r"[ \t\u3000]+", " ", t)
    out = []
    for ln in t.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if out and not re.search(r"[。！？；：，、）)】”]$", out[-1]) \
                and not re.match(r"^(第[一二三四五六七八九十]+[章节条]|[一二三四五六七八九十]、|\d+(\.\d+)*[、.]?\s|标段|标包|包段)", ln):
            out[-1] += ln          # 断行接回去
        else:
            out.append(ln)
    return "\n".join(out)


def _body_section(t):
    """截出「采购内容/招标范围」等建设段，止于资格、开标等章节。"""
    sec = _norm_body(t)
    pos = None
    for k in _SEC_START:
        i = sec.find(k)
        if i >= 0 and (pos is None or i < pos):
            pos = i
    if pos is None:
        return None
    seg = sec[pos:pos + 1600]
    for s in _SEC_STOP:
        j = seg.find(s)
        if j > 15:
            seg = seg[:j]
    # 表格一开始就不是建设内容了：在「标包1 / 标段一 / 序号 产品名称」处截断
    m = re.search(r"(标包\s*\d|标段\s*[一二三四五六七八九十\d]|包段\s*\d|序号\s*\S{0,6}产品|产品名称\s*产品单位"
                  r"|服务类别\s*主要服务内容|咨询成果|保修期)", seg)
    if m and m.start() > 30:
        seg = seg[:m.start()]
    return seg


_BNOISE = ("表格", "自动生成", "不作为参考", "仅供参考", "解释权", "以下为", "本表")


_BUILD_VERB_OK = ("建设", "研发", "开发", "升级", "改造", "扩容", "支撑", "实现", "具备", "提供",
                  "开展", "打造", "新增", "优化", "纳管", "开通", "采集", "迁移", "上收", "搬迁",
                  "集成", "部署", "构建", "赋能", "管理", "分析", "监控", "诊断", "编排", "割接",
                  "下沉", "替换", "打通", "承载", "覆盖", "检测", "验证", "研究")


def _clean_sent(c):
    """剥掉编号与「概况/内容/名称」这类版式词，砍掉「详见附件」尾巴。"""
    for _ in range(3):
        c2 = re.sub(r"^\d+(\.\d+)+\s*[、.．)）]?\s*", "", c)      # 1.2 / 2.1.1
        c2 = re.sub(r"^\d{1,2}\s*[、.．)）]\s*", "", c2)          # 一、1、 (year-safe)
        c2 = re.sub(r"^(项目|采购|招标|建设|工程|服务)?(概况|内容|范围|名称|需求|规模|简介|说明|编号|数量)"
                    r"(?:[、和与及]\s*(?:概况|内容|范围|名称|需求|规模|简介|说明|编号|数量))*\s*[:：为]?\s*",
                    "", c2)
        c2 = c2.lstrip("、，,：:；; 　")
        if c2 == c:
            break
        c = c2
    c = re.sub(r"^(本|该)次", "", c)                                    # 「本次」整词（不能只砍「本」）
    c = re.sub(r"^[^，。；：]{0,12}?部\s*\d{4}\s*年至\s*\d{4}\s*年\s*[（(][^）)]{1,12}[）)]\s*", "", c)   # 「网络部2026年至2027年（12个月）」
    c = re.sub(r"^(?:[^，。；：]{0,10}?(?:部|中心|室|科))?\s*\d{4}\s*年至\s*\d{4}\s*年(?:度)?\s*", "", c)
    c = re.sub(r"^(本|该)(?=(项目|工程|次|采购|业务))", "", c)            # 「本项目」「该业务」残头
    c = re.sub(r"^(本|该)(主要|将|拟)", "", c)                            # 「本主要」「本将」
    c = re.sub(r"^(包括|包含|其中|主要有|内容为|主要内容|服务内容|采购内容)\s*[:：]?\s*", "", c)
    c = re.sub(r"^\d{1,2}\s*[)）、.．]\s*", "", c)                        # 「1)」「2、」条目号
    c = re.sub(r"^\d+([.．]\d+)*\s*[、.．)）]?\s*(?=[\u4e00-\u9fa5])", "", c)   # 「1物联网…」残号
    c = re.sub(r"^\d+\s+", "", c)                                     # 表格首列编号
    c = re.sub(r"[，,；;：:]?\s*(?:主要)?(?:采购|服务|建设|工作)?内容\s*(?:如下|如上|包括|包含|为)\s*[:：]?\s*$", "", c)  # 「…，主要内容如下：」引导语
    c = re.sub(r"[，,；;：:]?\s*(?:主要)?(?:采购|服务|建设|工作)内容\s*[:：]\s*$", "", c)
    c = re.sub(r"本(项目)?的?(建设|研发|开发|升级|改造)", r"项目\2", c)
    c = re.sub(r"[，,；;](具体)?(内容|技术规范)?(详见|参见|见)[^。]{0,30}$", "", c)
    # 只砍「…，主要内容为对合肥」这种停在介词上的残尾（必须带 为/是/包含 才动手）
    c = re.sub(r"[，,](?:主要)?(?:内容|范围|工作)?(?:为|是|包括|包含|含)[^，。]{0,12}$", "", c) if len(c) > 30 else c
    # 数量表尾巴：「；1 宽带网络发展关键指标数据服务 120」「；4 低速率数据分析服务 146合计」
    c = re.sub(r"[；;]?\s*\d+\s+[^；。]{2,30}\s\d{1,6}(合计|小计)?\s*$", "", c)
    c = re.sub(r"\s\d{2,6}(合计|小计)$", "", c)
    c = clean_build(c) or ""
    c = re.sub(r"^\d{1,2}\s*[)）、.．]\s*", "", c)      # clean_build 会吃掉括号，条目号要再剥一次
    c = re.sub(r"^\d+([.．]\d+)*\s*[、.．)）]?\s*(?=[\u4e00-\u9fa5])", "", c)
    c = re.sub(r"^年", "", c)                          # 「2026年…」被吃掉年份后的残「年」
    c = re.sub(r"^(主要为|内容为|主要为开展|主要开展|主要为对|主要对)", "", c)
    c = c.strip("、，,：:；; 　")
    return re.sub(r"(的|等|及|和|中|内)$", "", c)


def _same(a, b):
    """句子是否与标题/已选句高度重复。"""
    if not b:
        return False
    ga = set(a) - set("，。、：；（）()的与和及等为在")
    gb = set(b) - set("，。、：；（）()的与和及等为在")
    if not ga or not gb:
        return False
    return len(ga & gb) / max(1, min(len(ga), len(gb))) > 0.92


def _from_body_section(t, title=""):
    """从正文建设段挑句提炼：切句 → 剔条款/商务/模板句 → 网域相关性过滤 → 依序合成。"""
    if not t:
        return None
    seg = _body_section(t) or _norm_body(t)
    picked = []
    # 除标点外，还在「1.2采购内容：」这类小节标签前断句，避免粘成一长串
    parts = re.split(r"[。！？；\n]|(?=\d+(?:\.\d+)+\s*[\u4e00-\u9fa5]{2,6}\s*[:：])", seg)
    for c in parts:
        c = (c or "").strip(" \u3000:：，、.、）)】")
        if not (10 <= len(c) <= 240):
            continue
        if any(n in c for n in _BNOISE):
            continue                      # 「以下表格为系统自动生成」这类免责句
        if any(d in c for d in _BDROP):
            continue
        if not any(w in c for w in _BNET):
            continue
        if re.search(r"人\s*天|\d+[,，]\d{3}", c):   # 人天/数量表碎片
            continue
        if re.match(r"^\d+\s+\S", c):
            continue                      # 「1 重要场馆 可视化…」表格行
        if re.search(r"[^\s]\s[^\s]\s[^\s]\s[^\s]", c):   # 制表符碎片：「服 务 项 2271」
            continue
        if sum(ch.isdigit() for ch in c) > len(c) * 0.3:
            continue
        c = _clean_sent(c)
        if len(c) < 10:
            continue
        if re.search(r"(^|[；;，,\s])包\s*\d|的人$", c):
            continue                      # 中选公示/标包表碎片
        if not any(v in c for v in _BUILD_VERB_OK):
            continue                      # 没有建设动作词，不是建设内容
        if _same(c, title) or any(_same(c, p) for p in picked):
            continue                      # 与标题/已有句重复，不重复占位
        picked.append(c)
    if not picked:
        return None
    out, total = [], 0
    for c in picked[:4]:
        if out and total + len(c) > 300:
            break
        out.append(c)
        total += len(c) + 1
    return "；".join(out) if out else None


_BUILD_VERB_OK = ("建设", "研发", "开发", "升级", "改造", "扩容", "支撑", "实现", "具备", "提供",
                  "开展", "打造", "新增", "优化", "纳管", "开通", "采集", "迁移", "上收", "搬迁",
                  "集成", "部署", "构建", "赋能", "管理", "分析", "监控", "诊断", "编排", "割接",
                  "下沉", "扩容", "替换", "打通", "承载", "覆盖", "检测", "验证", "研究")


def _build_ok(s, title=""):
    """正文提炼结果的质量闸门：像建设内容才用，否则回退标题。"""
    if not s or not (16 <= len(s) <= 300):
        return False
    if re.search(r"标包\s*\d|标段\s*\d|包段\s*\d", s):
        return False
    if re.search(r"(项|台|套|个|许可|人|次)\s*\d+$", s):
        return False          # 数量表行
    if not any(v in s for v in _BUILD_VERB_OK):
        return False
    if _same(s, title):
        return False
    if title and len(set(s) - set(title)) < 8:
        return False          # 只是在标题上加了「开发服务」这类尾巴，没提供新信息
    return True


def parse_build_content(text, title=""):
    """建设内容 / 系统名称。

    优先级：正文「建设动作 + 网元/技术词」的具体描述（最具体，如 HSS 上收至 UDM）
    → 正文系统/平台名 → 标题提炼。
    这样不会再把「如果在截止时间前框架协议金额执行完毕」这种条款当成建设内容。
    """
    enum = _from_body_enum(text) if text else None
    if enum:
        return enum          # 「一是…四是」列举 = 完整建设内容，优先保留
    sec = _from_body_section(text, title) if text else None
    if sec and _build_ok(sec, title):
        return sec           # 正文建设段逐句筛选提炼（主力通道）
    evo = _from_body_evo(text) if text else None
    if evo:
        return evo[:200]
    frombody = _valid_body_build(clean_build(_from_body_core(text))) if text else None
    fromtitle = clean_build(_from_title(title))
    out = frombody or fromtitle
    # 标题截断常留悬垂虚词（「…开发服务的」），入库前统一削掉
    return re.sub(r"(的|等|及|和)$", "", out.strip()) if out else out

# 标题里的噪声后缀
_TITLE_NOISE = ("_招标公告", "_询比公告", "_比选公告", "_采购公告", "_中选结果公示",
                "_中标结果公示", "_结果公示", "_候选人公示", "_单一来源", "_竞争性谈判")


def _from_title(title):
    """从标题解析项目本体：去掉运营商主体和公告后缀。"""
    if not title:
        return None
    s = title
    for n in _TITLE_NOISE:
        s = s.replace(n, "")
    # 去掉运营商主体前缀
    s = re.sub(r"^(中国移动通信集团[\u4e00-\u9fa5]{2,6}有限公司|中国移动通信集团[\u4e00-\u9fa5]{2,6}公司|"
               r"中国移动[\u4e00-\u9fa5]{2,4}公司|China Mobile[\u4e00-\u9fa5]{0,6})", "", s)
    s = re.sub(r"^中国电信(股份有限公司)?[\u4e00-\u9fa5]{0,8}(公司|局|中心)?", "", s)
    s = re.sub(r"^中国联通|^中国铁塔", "", s)
    # 电信常见写法：XX电信、省名+电信、地市名+电信
    s = re.sub(r"^[\u4e00-\u9fa5]{2,6}电信(股份有限公司)?[\u4e00-\u9fa5]{0,10}(分公司|公司|局)?", "", s)
    # 省市简称+移动/联通：河北移动、北京联通、新疆移动
    s = re.sub(r"^[\u4e00-\u9fa5]{2,4}(移动|联通)(通信)?(股份有限公司|有限公司|公司|分公司)?\d{0,4}年?", "", s)
    # 内部部门前缀：算网运营事业群 / 政企事业部 / 网络部
    s = re.sub(r"^[\u4e00-\u9fa5]{0,12}(事业群|事业部|本部|部门)", "", s)
    s = re.sub(r"^\d{4}年", "", s)
    # 去掉 "至2028年" / "-2027年" 这类残留的年份区间前缀
    s = re.sub(r"^(至|-|—|~)\s*\d{4}\s*年?", "", s)
    s = re.sub(r"^\d{4}\s*[-至]\s*\d{4}\s*年?", "", s)
    # 去掉残留的"运营中心2026年"这类前缀
    s = re.sub(r"^[\u4e00-\u9fa5]{0,8}(运营中心|调度中心|传输局)\d{4}年?", "", s)
    s = re.sub(r"^[（(]第二次[)）]", "", s)
    # 折叠运营商前缀重复："中国联通联通时科" → "中国联通时科"
    s = re.sub(r"^(中国联通)联通", r"\1", s)
    s = re.sub(r"^(中国移动)移动", r"\1", s)
    s = re.sub(r"^(中国电信)电信", r"\1", s)
    # 去掉尾部公告类型（电信标题常直接跟"询比公告"，无下划线）
    s = re.sub(r"(招标公告|询比公告|比选公告|采购公告|中标候选人公示|中选候选人公示|中选结果公告|中标结果公示|结果公示|候选人公示|询价公告|竞争性谈判公告|单一来源公示)$", "", s)
    s = re.sub(r"(中标|中选|成交)$", "", s)
    s = re.sub(r"[（(]\s*第[一二三四五六七八九十\d]+次\s*$", "", s)
    s = re.sub(r"[（(]\s*[)）]\s*$", "", s)
    s = s.strip(" _-—，、（）")
    # strip 之后再清一次"（第二次"这类残留（右括号已被 strip 吃掉）
    s = re.sub(r"[（(]\s*第[一二三四五六七八九十\d]+次\s*[)）]?$", "", s)
    s = re.sub(r"[（(]\s*[)）]?$", "", s)
    s = s.strip(" _-—，、（）")
    # 标包/标段编号（"…服务标包1" → "…服务"）、子项目括注一并清掉
    s = re.sub(r"[（(]?\s*(标包|包|标段)\s*\d+\s*[)）]?", "", s)
    s = re.sub(r"[（(]\s*子项目[^)）]*[)）]", "", s)
    # 尾部建设/采购动作词，只留系统本体名：…定制化软件研发 → …
    _TAIL = ("直接采购需求公示", "采购需求公示", "需求公示", "直接采购", "采购需求",
             "研究与应用", "研究及应用", "与研究", "与应用", "及应用", "和分析", "和建设",
             "公开询比采购", "公开询比", "询比采购", "公开招标采购", "公开招标", "竞争性谈判",
             "单一来源", "直接采购", "集中采购", "框架采购", "采购", "招标", "询比", "比选",
             "定制化软件开发", "定制软件开发", "软件开发", "软件研发", "软件定制", "软件",
             "研发服务", "委托研发", "研发", "服务", "委托", "研究", "方案", "实践", "许可",
             "工程", "建设", "项目", "扩容", "改造", "新建", "升级", "购新", "定制化", "定制",
             "和", "与")
    for _ in range(5):
        for w in _TAIL:
            if len(s) > 7 and s.endswith(w):
                s = s[: -len(w)].rstrip(" _-—，、（")
                break
        else:
            break
    s = re.sub(r"(研发)?项$", "", s)          # "升级研发项工程" → 残留的「项」
    s = re.sub(r"[（(]\s*\d{4,}\s*[)）]", "", s)  # 纯数字编号括注（经开（016211））
    # 截断留下的半个括号（"（集中调度系统、故障调度智能体"）整段砍掉
    while s.count("（") > s.count("）") and "（" in s:
        s = s[: s.rfind("（")].rstrip(" _-—，、（")
    # 年份被吃掉后运营商主体露到最前（2026年中国联通河北… → 中国联通河北…），再剥一层
    for _ in range(2):
        s2 = re.sub(r"^(中国联通|中国移动|中国电信|中国铁塔|中国广电)[\u4e00-\u9fa5]{0,4}?(省|市)?(公司|分公司)?", "", s)
        if s2 == s or len(s2) < 6:
            break
        s = s2
    if len(s) < 4:
        return None
    return s[:60]


# 正文里值得提取的规模要素（只要真实数量/范围，不要流程性文字）
_SCALE_PATS = [
    r"(\d{1,6}\s*(?:台|套|块|面|架|辆|组|间|处|端|条|个站|个基站))",
    r"(\d{1,6}\s*(?:公里|km|千米))",
    r"(\d{1,3}\s*个标包)",
    r"(覆盖[\u4e00-\u9fa5]{2,12}(?:市|县|区|省|地市))",
]

# 流程性/合同性噪声词：命中则丢弃该片段
_NOISE = ("样品", "联系人", "电话", "合同主体", "发货地点", "投标人", "供应商应",
          "资格", "公章", "扫描件", "保证金", "签字", "盖章", "递交", "澄清", "异议",
          "评审", "评标", "开标", "投标文件", "应答文件")


def _from_body(text):
    """从正文提取规模/范围补充信息（真实数量、标包、覆盖范围）。"""
    if not text:
        return None
    flat = re.sub(r"(?<=[\u4e00-\u9fa5，、；：])\n(?=[\u4e00-\u9fa5])", "", text)
    flat = re.sub(r"[ \t\u3000]+", " ", flat)
    # 定位到"采购内容/项目概况"之后
    start = 0
    for key in BUILD_KEYS:
        m = re.search(key + r"\s*[：:]", flat)
        if m:
            start = m.end()
            break
    seg = flat[start:start + 2000]

    # 丢弃含噪声词的整句，避免表格/流程文字混入
    sentences = re.split(r"[。；\n]", seg)
    clean = [s for s in sentences if not any(n in s for n in _NOISE)]
    seg = "。".join(clean)

    bits = []
    for pat in _SCALE_PATS:
        for m in re.finditer(pat, seg):
            v = m.group(1).strip()
            if any(n in v for n in _NOISE):
                continue
            if v not in bits:
                bits.append(v)
        if len(bits) >= 2:
            break
    if not bits:
        return None
    return "、".join(bits[:2])[:50]


# 空话短语：命中则视为无有效内容
_EMPTY_PHRASES = ("详见附件", "见附件", "详见采购清单", "详见招标文件", "详见公告",
                  "具体详见", "详见工程量清单", "详见技术规范", "另见", "见清单",
                  "详见第四章", "详见第五章", "详见第六章", "以采购文件为准",
                  "_招标公告", "_询比公告", "_中选结果公示", "_中标结果公示",
                  "招标项目名称", "项目编号", "本招标项目为")


def _summarize(raw):
    """把原文段落归纳成简短描述。"""
    if not raw:
        return None
    s = re.sub(r"\s+", " ", raw).strip(" ：:、.．-—")
    s = re.sub(r"^[\d\.、．]+", "", s).strip()

    # 去掉公告头部/编号等噪声
    s = re.sub(r"（?招标项目名称[：:][^、）]{0,80}", "", s)
    s = re.sub(r"、?\s*项目编号[：:]?\s*[A-Z0-9\-]{4,30}", "", s)
    s = re.sub(r"本招标项目为", "", s)
    s = s.strip(" ，、（）")

    # 纯空话
    if any(p in s for p in _EMPTY_PHRASES) and len(s) < 45:
        return None
    if len(s) < 10:
        return None

    # 截到第一个句号/分号，控制长度；避开在数字中间截断
    mm = re.search(r"[。；]", s)
    if mm and mm.start() > 12:
        s = s[:mm.start()]
    if len(s) > 150:
        cut = s[:150]
        # 避免截在数字/金额中间
        if re.search(r"[\d,.]$", cut):
            back = re.search(r"[\d,.]+\s*$", cut)
            if back:
                cut = cut[:back.start()]
        s = cut.rstrip(" ，、,.")
    s = s.strip(" ，、（）")
    if len(s) < 8:
        return None
    return s


def _clean(s):
    s = re.sub(r"\s+", " ", s).strip(" ：:、.．-—")
    if len(s) < 8:
        return None
    # 截到第一个句号/分号，避免拖太长
    m = re.search(r"[。；]", s)
    if m and m.start() > 15:
        s = s[:m.start()]
    return s[:600]


# ---------------- 中国移动 ----------------
CMCC_LIST = "/api-b2b/api-sync-es/white_list_api/b2b/publish/queryList"
CMCC_DETAIL_URL = "https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html#/noticeDetail?id={id}"


def fetch_cmcc(pg, pages=3, page_size=20, notice_type="PROCUREMENT"):
    """抓移动公告列表。notice_type: PROCUREMENT=采购公告, SELECTION_RESULTS=结果公示。

    分页参数实测是 current/size，不是 pageNum/pageSize。
    """
    rows = []
    for pno in range(1, pages + 1):
        try:
            j = pg.evaluate("""async ([path, body]) => {
                const r = await fetch(path, {method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify(body)});
                return await r.json();
            }""", [CMCC_LIST, {"current": pno, "size": page_size,
                               "publishOneType": notice_type,
                               "sfactApplColumn5": "PC"}])
        except Exception as e:
            print(f"  [CMCC] page {pno} error: {e}")
            break

        content = (j.get("data") or {}).get("content") or []
        if not content:
            print(f"  [CMCC] page {pno} empty, stop")
            break

        for it in content:
            title = it.get("name") or ""
            if not title.strip():
                continue
            rows.append({
                "id": "cmcc_" + str(it.get("id")),
                "uuid": str(it.get("uuid") or ""),
                "title": title,
                "notice_type": it.get("publishOneType_dictText") or "采购公告",
                "publish_date": (it.get("publishDate") or "")[:10],
                "deadline": (it.get("backDate") or it.get("tenderSaleDeadline") or "")[:16],
                "operator": "中国移动",
                "region": it.get("companyTypeName") or "",
                "source": "中国移动采购与招标网",
                "url": f"https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html#/noticeDetail?publishId={it.get('id')}&publishUuid={it.get('uuid')}&publishType={it.get('publishType') or 'PROCUREMENT'}",
                "content": "",
                "publish_type": notice_type,
            })
        print(f"  [CMCC/{notice_type}] page {pno}: +{len(content)}")
        time.sleep(random.uniform(1.2, 2.2))
    return rows


# ---- 关键词补扫（实测 name 参数就是关键词过滤）----
# 只翻最新 N 页会漏掉窗口外的公告：河北移动数字化网络运营沙盘（11-11 16:41 发布）
# 当时就没进最新 300 条。用 name=关键词 精确捞回来。
CMCC_SWEEP_KW = ["沙盘", "数字化网络运营", "数字孪生", "自智网络", "网络运营", "算力网络",
                 "承载网", "核心网", "接入网", "传输网", "网管", "OSS", "编排", "云网",
                 "专网", "网优", "数据中台", "智能体", "网络中台", "网络大脑"]


def _cmcc_row(it, notice_type):
    title = it.get("name") or ""
    if not title.strip():
        return None
    return {
        "id": "cmcc_" + str(it.get("id")),
        "uuid": str(it.get("uuid") or ""),
        "title": title,
        "notice_type": it.get("publishOneType_dictText") or "采购公告",
        "publish_date": (it.get("publishDate") or "")[:10],
        "deadline": (it.get("backDate") or it.get("tenderSaleDeadline") or "")[:16],
        "operator": "中国移动",
        "region": it.get("companyTypeName") or "",
        "source": "中国移动采购与招标网",
        "url": f"https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html#/noticeDetail?publishId={it.get('id')}&publishUuid={it.get('uuid')}&publishType={it.get('publishType') or 'PROCUREMENT'}",
        "content": "",
        "publish_type": notice_type,
    }


def fetch_cmcc_keyword(pg, kw, notice_type="PROCUREMENT", size=20):
    """按关键词捞移动公告（name 参数），补最新窗口之外的相关公告。"""
    try:
        j = pg.evaluate("""async ([path, body]) => {
            const r = await fetch(path, {method:'POST',
                headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
            return await r.json();
        }""", [CMCC_LIST, {"current": 1, "size": size, "publishOneType": notice_type,
                            "sfactApplColumn5": "PC", "name": kw}])
    except Exception as e:
        print(f"  [CMCC-KW] {kw} error: {str(e)[:60]}")
        return []
    content = (j.get("data") or {}).get("content") or []
    rows = [r for r in (_cmcc_row(it, notice_type) for it in content) if r]
    print(f"  [CMCC-KW] {kw}/{notice_type}: +{len(rows)}")
    return rows


def sweep_cmcc(pg, keywords=None, notice_types=("PROCUREMENT", "SELECTION_RESULTS")):
    """关键词补扫：每个关键词一次请求，跨采购公告+结果公示。"""
    out, seen = [], set()
    for kw in (keywords or CMCC_SWEEP_KW):
        for nt in notice_types:
            for r in fetch_cmcc_keyword(pg, kw, nt):
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                out.append(r)
            time.sleep(random.uniform(0.8, 1.5))
    return out


# ---------------- 中国电信 ----------------
CT_LIST = "/portal/base/announcementJoin/queryListNew"
# 栏目 -> type 值（实测点击首页各栏目抓到的真实参数）
CT_TYPES = {
    "e2no": "招标公告",
    "e3erht": "询比公告",
    "n0eves": "采购结果公示",
    "e8vif": "谈判采购公告",
    "xi9s": "资格预审公告",
    "ow7t": "直接采购公示",
    "cgjh10": "采购计划",
}


def fetch_ct(pg, pages=2, page_size=20, types=None):
    """抓电信公告。返回结构实测为 data.pageInfo.list。

    电信有 IP 限流，连续约 8 次请求即被封，必须 3-5 秒间隔。
    """
    rows = []
    seen_ids = set()
    for tp in (types or ["e2no", "e3erht", "n0eves"]):
        tname = CT_TYPES.get(tp, tp)
        for pno in range(1, pages + 1):
            try:
                j = pg.evaluate("""async ([path, body]) => {
                    const r = await fetch(path, {method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify(body)});
                    return await r.json();
                }""", [CT_LIST, {"pageNum": pno, "pageSize": page_size, "type": tp}])
            except Exception as e:
                print(f"  [CT] {tname} p{pno} error: {str(e)[:60]}")
                break
            pi = ((j.get("data") or {}).get("pageInfo") or {})
            lst = pi.get("list") or []
            if not lst:
                print(f"  [CT/{tname}] p{pno} 空返回（可能被限流）")
                break
            # 翻页去重校验：电信限流时可能重复返回第一页
            first_id = lst[0].get("id")
            if first_id and first_id in seen_ids:
                print(f"  [CT/{tname}] p{pno} 内容重复（限流），跳过")
                break
            for it in lst:
                if it.get("id"):
                    seen_ids.add(it.get("id"))
            for it in lst:
                title = it.get("docTitle") or ""
                if not title.strip():
                    continue
                # 电信列表自带发布/截止时间，不必进详情
                p_start = it.get("pStartDate") or it.get("pstartDate") or ""
                p_end = it.get("pEndDate") or it.get("pendDate") or ""
                rows.append({
                    "id": "ct_" + str(it.get("id")),
                    "uuid": str(it.get("docId") or ""),
                    "title": title,
                    "notice_type": it.get("docType") or tname,
                    "publish_date": (it.get("createDate") or "")[:10],
                    "deadline": p_end[:16] if p_end else "",
                    "operator": "中国电信",
                    "region": it.get("provinceName") or "",
                    "source": "中国电信阳光采购网",
                    "url": ("https://caigou.chinatelecom.com.cn/portal/noticeDetail"
                            f"?id={it.get('id')}&docId={it.get('docId')}"),
                    "content": "",
                    "publish_type": tp,
                })
            print(f"  [CT/{tname}] p{pno}: +{len(lst)} (总 {pi.get('total')})")
            time.sleep(random.uniform(5.0, 8.0))   # 电信限流严格，间隔要够长
    return rows


# ---------------- 详情（PDF正文）----------------
CMCC_DETAIL = "/api-b2b/api-sync-es/white_list_api/b2b/publish/queryDetail"


def fetch_cmcc_detail(pg, item):
    """用正确参数 publishId/publishUuid/publishType 调 queryDetail，返回 PDF 提取的正文。

    实测：noticeContent 是 base64 PDF（约 200KB），必须解码后抽取文字。
    """
    body = {
        "publishId": str(item["id"]),
        "publishUuid": str(item["uuid"]),
        "publishType": item.get("publishType") or "PROCUREMENT",
        "sfactApplColumn5": "PC",
    }
    try:
        r = pg.evaluate("""async ([path, body]) => {
            const r = await fetch(path, {method:'POST',
                headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
            return await r.text();
        }""", [CMCC_DETAIL, body])
    except Exception as e:
        return None, None, str(e)[:80]

    if '"code":0' not in r:
        return None, None, r[:100]

    try:
        d = json.loads(r).get("data") or {}
    except Exception:
        return None, None, "json parse fail"

    nc = d.get("noticeContent") or ""
    if not nc:
        return None, d, "no content"

    # base64 PDF -> 文字
    try:
        raw = base64.b64decode(nc)
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        # 有些是 HTML 富文本，直接剥离标签
        text = re.sub(r"<[^>]+>", " ", htmllib.unescape(str(nc)))

    return re.sub(r"[ \t]+", " ", text), d, None


def enrich_detail(pg, rows, limit=0):
    """进详情（PDF）补建设内容/金额/中选厂商，并保存快照。"""
    done = 0
    for r in rows:
        if limit and done >= limit:
            break
        # 电信详情接口需登录态，列表接口已带标题/发布日/截止日。
        # 不能走移动的 queryDetail（会拼出错误 URL），改为按标题归纳建设内容，
        # 金额/中选厂商详情取不到就留空，不编造。
        if r["id"].startswith("ct_"):
            bc = parse_build_content("", r.get("title", ""))
            if bc:
                r["build_content"] = bc
            ok, lv, why = classifier.classify(r.get("title", ""), "")
            r["relevance"], r["relevance_reason"] = lv, why
            done += 1
            print(f"    ok {r['id']} 金额=None 建设内容={'Y' if bc else 'N'}（电信详情不可达，按标题归纳）")
            continue
        # publishType 必须与公告类型匹配，否则移动返回瑞数混淆页（实测）
        pt = r.get("publish_type") or "PROCUREMENT"
        if re.search(r"结果公示|中选|中标|成交|候选人", r.get("title", "")):
            pt = "SELECTION_RESULTS"
        it = {"id": r["id"].replace("cmcc_", ""), "uuid": r.get("uuid", ""),
              "publishType": pt}
        if not it["uuid"]:
            print(f"    skip {r['id']}: 无 uuid（列表未带出）")
            continue
        text, meta, err = fetch_cmcc_detail(pg, it)
        if err:
            print(f"    detail fail {r['id']}: {err}")
            continue
        if text:
            r["content"] = text[:8000]
            a_num = parse_amount(text)
            if a_num:
                r["amount_value"] = a_num
                r["amount_raw"] = str(a_num)
            w = parse_winner(text)
            if w:
                r["winner"] = w
            bc = parse_build_content(text, r.get("title", ""))
            if bc:
                r["build_content"] = bc
            ok, lv, why = classifier.classify(r.get("title", ""), text)
            r["relevance"], r["relevance_reason"] = lv, why
            r["snapshot_path"] = db.save_snapshot(r["id"], text)
            done += 1
            print(f"    ok {r['id']} 金额={r.get('amount_value')} 建设内容={'Y' if bc else 'N'}")
        time.sleep(random.uniform(0.8, 1.6))
    return done


# ---------------- 中国联通 ----------------
# 站点有瑞数动态防护（Riversafe）：桌面 UA / 爬虫 UA 全部返回 412，
# 只有移动端（iOS Safari）UA 能通过。别改这个 UA。
CU_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
         "Mobile/15E148 Safari/604.1")
CU_HOME = "https://www.chinaunicombidding.cn/"
CU_LIST = "/api/v1/bizAnno/getAnnoList"
# annoType → (显示名, 是否结果公示)
CU_TYPES = {
    "022002": ("招标公告", False),
    "022003": ("询比公告", False),
    "022004": ("谈判公告", False),
    "022001": ("采购需求公示", False),
    "023001": ("中标候选人公示", True),
    "023002": ("中选候选人公示", True),
}


def cuisine(p):
    """联通专用浏览器上下文：必须 iOS UA 才能过瑞数防护。"""
    b = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = b.new_context(
        user_agent=CU_UA, locale="zh-CN",
        viewport={"width": 390, "height": 844}, timezone_id="Asia/Shanghai",
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    return b, ctx, ctx.new_page()


def fetch_cu(pg, pages=2, page_size=20):
    """抓联通公告列表。返回统一结构的 rows。

    注意：接口实际每页返回 10 条（不按 pageSize 给），所以不能用
    len(recs) < page_size 判断结束，必须用 total/pages 计算。
    """
    out = []
    seen = set()
    for tp, (tname, is_result) in CU_TYPES.items():
        last_ids = None
        for pno in range(1, pages + 1):
            try:
                js = """async (args) => {
                    const [url, body] = args;
                    const r = await fetch(url, {
                        method:'POST',
                        headers:{'Content-Type':'application/json;charset=UTF-8'},
                        body: JSON.stringify(body)
                    });
                    return await r.json();
                }"""
                data = pg.evaluate(js, [
                    CU_LIST,
                    {"pageNo": str(pno), "pageSize": str(page_size),
                     "modeNo": "BizAnnoVoBtable", "annoType": tp},
                ])
            except Exception as e:
                print(f"  [CU/{tname}] p{pno} 异常: {str(e)[:60]}")
                break

            d = (data or {}).get("data") or {}
            recs = d.get("records") or []
            if not recs:
                break
            total = d.get("total", 0)
            # 防重复页（接口忽略 pageNo 时会出现）
            cur_ids = tuple(it.get("id") for it in recs)
            if last_ids is not None and cur_ids == last_ids:
                print(f"  [CU/{tname}] p{pno}: 与上页重复，停止")
                break
            last_ids = cur_ids

            new = 0
            for it in recs:
                nid = it.get("id")
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                new += 1
                out.append({
                    "id": f"cu_{nid}",
                    "uuid": nid,
                    "title": (it.get("annoName") or "").strip(),
                    "notice_type": tname,
                    "publish_date": (it.get("createDate") or "")[:10],
                    "deadline": "",
                    "amount_raw": "",
                    "amount_value": None,
                    "winner": "",
                    "operator": "中国联通",
                    "region": _cu_region(it.get("provinceName"), it.get("bidCompany")),
                    "source": "中国联通采购与招标网",
                    "url": f"https://www.chinaunicombidding.cn/#/noticeDetail?id={nid}",
                    "snapshot_path": "",
                    "build_content": "",
                    "publish_type": "023002" if is_result else "022002",
                    "bid_company": it.get("bidCompany") or "",
                })
            print(f"  [CU/{tname}] p{pno}: +{new} (共 {total} 条)")
            # 已抓够总数就不再翻
            if pno * len(recs) >= total:
                break
            time.sleep(random.uniform(1.5, 2.5))
        time.sleep(random.uniform(1.0, 2.0))
    return out


CU_PROVINCES = ("北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
                "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
                "广东", "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西", "甘肃",
                "青海", "宁夏", "新疆", "内蒙古", "集团", "其他")


def _cu_region(prov, bid_company):
    """连通省份字段规范化：接口对集团子公司会把公司名塞进 provinceName。"""
    p = (prov or "").strip()
    if p in CU_PROVINCES and p not in ("其他",):
        return p
    c = bid_company or ""
    if not c or "供应链中心" in c or "集团" in c:
        return "集团"
    return "集团"


def _cu_deadline(text):
    """从联通公告正文里抽投标截止时间，返回 YYYY-MM-DD。"""
    if not text:
        return ""
    pats = [
        r"(?:投标|应答|响应)文件(?:递交|提交)的?截止时间[为:：\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})",
        r"(?:投标|应答|响应)截止时间[为:：\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})",
        r"截止时间[为:：\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})",
    ]
    for p in pats:
        m = re.search(p, text)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


CU_DETAIL = "/api/v1/bizAnno/getAnnoDetailed/"


def fetch_cu_detail(pg, nid):
    """抓联通详情。返回 (纯文本正文, 元信息, 错误)。"""
    try:
        js = """async (url) => {
            const r = await fetch(url, {method:'GET'});
            return await r.json();
        }"""
        d = pg.evaluate(js, CU_DETAIL + str(nid))
    except Exception as e:
        return None, None, f"请求失败:{str(e)[:60]}"

    if not (d or {}).get("success"):
        return None, None, "接口返回失败"

    data = d.get("data") or {}
    html = data.get("annoText") or ""
    if not html:
        return None, data, "无正文"

    # HTML 转纯文本
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
    txt = re.sub(r"</(p|div|tr|li|h\d)>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    txt = re.sub(r"[ \t\u3000]+", " ", txt)
    txt = re.sub(r"\n{2,}", "\n", txt).strip()
    return txt, data, None


def run(which="all", pages=3, details=0):
    from playwright.sync_api import sync_playwright
    db.init()
    all_rows = []
    with sync_playwright() as p:
        b, pg = launch(p)
        try:
            if which in ("all", "cmcc"):
                print("[CMCC] start")
                pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                        wait_until="networkidle", timeout=90000)
                pg.wait_for_timeout(4000)
                # 采购公告（含截止日期）
                r1 = fetch_cmcc(pg, pages=pages, notice_type="PROCUREMENT")
                all_rows += r1
                print("[CMCC] 采购公告 %d" % len(r1))
                time.sleep(random.uniform(2, 4))
                # 结果公示（含中选厂商）
                r2 = fetch_cmcc(pg, pages=max(1, pages), notice_type="SELECTION_RESULTS")
                all_rows += r2
                print("[CMCC] 结果公示 %d" % len(r2))
                # 关键词补扫：只翻最新 N 页会漏掉窗口外的网络数智类公告
                try:
                    r3 = sweep_cmcc(pg)
                    have = {r["id"] for r in all_rows}
                    add = [r for r in r3 if r["id"] not in have]
                    all_rows += add
                    print("[CMCC] 关键词补扫 +%d（窗口外补回）" % len(add))
                except Exception as e:
                    print("[CMCC] 关键词补扫失败: %s" % str(e)[:80])

            if which in ("all", "ct"):
                print("[CT] start")
                pg.goto("https://caigou.chinatelecom.com.cn/",
                        wait_until="networkidle", timeout=90000)
                pg.wait_for_timeout(3000)
                r2 = fetch_ct(pg, pages=min(pages, 2))
                all_rows += r2
                print("[CT] total %d" % len(r2))

            if which in ("all", "cu"):
                print("[CU] start")
                b2 = None
                try:
                    b2, ctx2, pg2 = cuisine(p)
                    pg2.goto(CU_HOME, wait_until="domcontentloaded", timeout=45000)
                    pg2.wait_for_timeout(5000)
                    ttl = pg2.title()
                    if "联通" not in ttl:
                        print(f"[CU] 首页未加载（标题='{ttl}'），跳过")
                    else:
                        r3 = fetch_cu(pg2, pages=max(1, min(pages, 15)))
                        all_rows += r3
                        print("[CU] total %d" % len(r3))
                except Exception as e:
                    print(f"[CU] 采集失败: {type(e).__name__}: {str(e)[:120]}")
                finally:
                    if b2:
                        b2.close()

            # 联通详情单独跑（浏览器上下文不同）
            if details and any(r["id"].startswith("cu_") for r in all_rows):
                print("[CU-DETAIL] start")
                b3 = None
                try:
                    b3, ctx3, pg3 = cuisine(p)
                    pg3.goto(CU_HOME, wait_until="domcontentloaded", timeout=45000)
                    pg3.wait_for_timeout(4000)
                    cu_rows = [r for r in all_rows if r["id"].startswith("cu_")]
                    pre = []
                    for r in cu_rows:
                        ok, lv, why = classifier.classify(r.get("title", ""), "")
                        if ok:
                            pre.append(r)
                    print(f"[CU-DETAIL] 预筛 {len(pre)}/{len(cu_rows)} 条")
                    done = 0
                    for r in pre:
                        if done >= details:
                            break
                        txt, meta, err = fetch_cu_detail(pg3, r["uuid"])
                        if err:
                            print(f"    skip {r['title'][:36]}: {err}")
                            continue
                        done += 1
                        r["content"] = (txt or "")[:8000]
                        a_num = parse_amount(txt or "")
                        if a_num:
                            r["amount_value"] = a_num
                            r["amount_raw"] = str(a_num)
                        bc = parse_build_content(txt or "", r.get("title", ""))
                        if bc:
                            r["build_content"] = bc
                        w = parse_winner(txt or "")
                        if w:
                            r["winner"] = w
                        # 截止日期
                        dl = _cu_deadline(txt or "")
                        if dl:
                            r["deadline"] = dl
                        if meta:
                            r["region"] = _cu_region(meta.get("provinceName"),
                                                     meta.get("bidCompany") or r.get("bid_company"))
                        # 存快照
                        try:
                            r["snapshot_path"] = db.save_snapshot(r["id"], txt or "")
                        except Exception:
                            pass
                        print(f"    ✓ {r['title'][:40]} | 金额={r.get('amount_raw') or '—'}")
                        time.sleep(random.uniform(1.5, 2.5))
                    print(f"[CU-DETAIL] 完成 {done} 条")
                except Exception as e:
                    print(f"[CU-DETAIL] 失败: {type(e).__name__}: {str(e)[:120]}")
                finally:
                    if b3:
                        b3.close()

            if details and all_rows:
                # 先过滤再抽取：只对网络域公告进详情，省流量也不浪费
                pre = []
                for r in all_rows:
                    if r["id"].startswith("cu_"):
                        continue  # 联通已单独处理
                    ok, lv, why = classifier.classify(r.get("title", ""))
                    if ok:
                        r["relevance"], r["relevance_reason"] = lv, why
                        pre.append(r)
                print(f"[DETAIL] 预筛后 {len(pre)}/{len(all_rows)} 条，抽取 {min(details, len(pre))}")
                enrich_detail(pg, pre, limit=details)
        finally:
            b.close()

    # ---- 网络域过滤：无关项目不入库 ----
    kept, dropped = [], []
    for r in all_rows:
        ok, lv, why = classifier.classify(r.get("title", ""), r.get("content", ""))
        if ok:
            r["relevance"] = lv
            r["relevance_reason"] = why
            kept.append(r)
        else:
            dropped.append((r.get("title", "")[:40], why))
    print(f"\n[FILTER] 保留 {len(kept)} 条，剔除 {len(dropped)} 条（非网络域）")
    for t, why in dropped[:8]:
        print(f"   - {t}  [{why}]")

    # 详情页抓不到时（WAF/限流），至少用标题主干生成建设内容，避免页面显示"—"。
    # upsert 只补空字段，所以这里不会覆盖已抓到的正文级描述。
    for r in kept:
        if not (r.get("build_content") or "").strip():
            bc = parse_build_content("", r.get("title", ""))
            if bc:
                r["build_content"] = bc

    ins, upd = db.upsert(kept)
    # 下架判定：用「本轮所有抓到的」而不是「过滤后保留的」，
    # 避免规则收紧把老记录误标成下架；同时用最早发布日期兜底。
    seen_by_op = {}
    for r in all_rows:
        seen_by_op.setdefault(r["operator"], []).append(r)
    stale_n = 0
    for op, rs in seen_by_op.items():
        ids = [r["id"] for r in rs]
        dates = [r["publish_date"] for r in rs if r.get("publish_date")]
        # 兜底下限必须"稳健"：列表里偶尔混进往年旧公告（如 2025-01-28 的联通国际项目），
        # 用绝对最小日期会把下限拉到一年前，导致本期窗口外的近期记录全被误判下架。
        # 只取最近 120 天内的日期算下限，且样本不足 10 条时放弃下架判定（宁可不标，不可错标）。
        cutoff = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        recent = [d for d in dates if d >= cutoff]
        floor = min(recent) if len(recent) >= 10 else ""
        n = db.mark_stale(op, ids, floor)
        stale_n += n
        if n:
            print(f"   {op}: {n} 条本轮未见，标为已下架存档")
    db.log_run(which, len(all_rows), ins, upd, "")
    print(f"\nDONE fetched={len(all_rows)} kept={len(kept)} inserted={ins} updated={upd}")
    return len(all_rows), ins, upd
    try:                      # 每轮收尾自愈：缺正文的记录补列表页快照，保证快照链接不空
        import snapshot_fill
        snapshot_fill.fill(True)
    except Exception as e:
        print(f"  [snapshot] skip: {type(e).__name__}: {e}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    details = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    run(which, pages, details)
