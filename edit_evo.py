# -*- coding: utf-8 -*-
"""给 collector 加「正文技术描述」通道：网元上收/迁移/搬迁类建设内容。"""
import io

P = "collector.py"
src = io.open(P, encoding="utf-8").read()

NEW_FUNC = '''
# 建设动作 + 网元/网络技术词 → 正文里的「技术方案型」建设内容
_BUILD_VERBS = ("上收", "迁移", "搬迁", "割接", "扩容", "新建", "改造", "升级", "部署",
                "替换", "退网", "整合", "融合", "打通", "承载", "上云", "入云", "开通",
                "并网", "下沉")
_TECH_NOUNS = ("HSS", "UDM", "5GC", "4G", "5G", "UPF", "SMF", "AMF", "MME", "SGW", "PGW",
               "网元", "核心网", "承载网", "传输网", "接入网", "城域网", "骨干网", "基站",
               "切片", "专网", "资源池", "网管", "信令", "机房", "光纤", "光缆", "波分",
               "OTN", "SPN", "IP网", "云网", "算网", "中台")
_EVO_BAD = _PROCESS_WORDS + ("预算", "限价", "资格", "应答人", "投标人", "代理机构",
                             "不含税", "税率", "金额", "有效期", "保证金", "评审")


def _from_body_evo(text):
    """正文里「建设动作 + 网元/网络技术词」的句子。

    HSS 上收至 UDM、5GC 网元搬迁、3/4G 业务迁移至 UDM 这类描述属于网络域建设内容，
    不因出现设备型号（HSS/UDM）、厂家名（中兴/华为）而按「设备采购」剔除。
    """
    if not text:
        return None
    flat = re.sub(r"[ \\t\\u3000]+", " ", text)
    out = []
    for clause in re.split(r"[。；\\n]", flat):
        c = clause.strip(" \\u3000:：，、;")
        c = re.sub(r"^\\d+(\\.\\d+)*\\s*", "", c)                 # 1.2.1 这类条款编号
        c = re.sub(r"^(根据[^，。]{0,40}[，,]|因[^，。]{0,30}[，,]|本期工程|本次工程|本工程|本次|"
                   r"其中|拟|将|对)", "", c).strip()
        c = re.sub(r"[（(]\\s*不含税\\s*[)）]", "", c)
        for w in ("询比", "招标", "公告", "标包", "采购项目", "本项目", "项目"):
            c = c.replace(w, "")
        c = re.sub(r"\\s{2,}", " ", c).strip(" ：:，、")
        if not (8 <= len(c) <= 160):
            continue
        if not any(v in c for v in _BUILD_VERBS):
            continue
        if not any(t in c for t in _TECH_NOUNS):
            continue
        if any(b in c for b in _EVO_BAD):
            continue
        if c not in out:
            out.append(c)
        if len(out) >= 2:
            break
    return "；".join(out) if out else None


'''

anchor = 'def parse_build_content(text, title=""):'
assert anchor in src, "anchor missing"
src = src.replace(anchor, NEW_FUNC.lstrip("\n") + anchor, 1)

OLD_BODY = '''    frombody = _valid_body_build(clean_build(_from_body_core(text))) if text else None
    fromtitle = clean_build(_from_title(title))
    return frombody or fromtitle'''
NEW_BODY = '''    evo = _from_body_evo(text) if text else None
    if evo:
        return evo[:200]
    frombody = _valid_body_build(clean_build(_from_body_core(text))) if text else None
    fromtitle = clean_build(_from_title(title))
    return frombody or fromtitle'''
assert OLD_BODY in src, "body anchor missing"
src = src.replace(OLD_BODY, NEW_BODY, 1)

src = src.replace('''以标题提炼为主（标题一定是这个项目的本体），正文只做严格校验后的补充：
    必须是 6–30 字、不含标点、不含合同/流程词、以系统平台类名词落点。''',
'''优先级：正文「建设动作 + 网元/技术词」的具体描述（最具体，如 HSS 上收至 UDM）
    → 正文系统/平台名 → 标题提炼。''')

io.open(P, "w", encoding="utf-8", newline="\n").write(src)
print("patched", len(src))
