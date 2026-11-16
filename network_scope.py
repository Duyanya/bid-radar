"""Network operations software scope; a presentation decision, never a deletion rule.

General network nouns or R&D alone are insufficient. Existing records and snapshots
remain available even when the current scope decision is false.
"""
import re

RULE_VERSION = '2026-11-16'
SEARCH_TERMS = [
    '网管', 'OSS', '网络监控', '网络运维', '故障调度', '网络指挥',
    '网络资源', '装维', '业务编排', '网络运营', '网络质量', '自智网络',
    '网络孪生', '网络沙盘', '核心网工作台', '传输网工作台', 'IP网工作台',
    '云网大脑', '算网调度', '网络中台', '网络智能体', '网优平台',
    '监控大屏', '监控可视化', '大屏可视化',
]
NETWORK = (
    '核心网', '承载网', '传输网', '接入网', '无线网', '无线运营', '无线孪生',
    '移动网', '移网', '无线运维', '传输运维', '网络优化', 'IP网', 'IP运维', 'IP融合专线', '光网', '家宽', '装维',
    '智慧营维', '政企业务运维', '政企调度开通', '网优', '网管', 'OSS', 'O域',
    '网络运营', '网络运维', '网络监控', '网络指挥', '网络调度', '网络保障',
    '网络质量', '网络质差', '网络资源', '网络中台', '网络大脑', '云网大脑',
    '自智网络', '智慧网络', '数字化网络', '云网运营', '云网调度', '算网调度',
    '算网运营', '业务编排', '故障调度', '故障管理', '故障能力中心',
    '网络投诉', '网络服务', '网络创新', '网络云', 'CMNET', 'DNS', 'DPI',
    '信令分析', '业务拨测', '专线客户网管', '网络设备配置', '网络变更',
    '通信网络', '5G', '6G', '室分', '光缆', '光纤', '宽带', '算力网络',
)
SOFTWARE = ('平台', '系统', '软件', '工作台', '智能体', '中台', '数仓',
            '应用', '工具', '模块', '数字孪生', '数字沙盘', '网络沙盘',
            '指令中心', '资源中心', '编排中心', '数据治理', '数据资产')
DEVELOPMENT = ('研发', '开发', '定制', '研究', '算法', '建模', '仿真', '验证')
SOFTWARE_CHANGE = ('研发', '开发', '建设', '新建', '升级', '改造', '扩容', '定制', '适配', '重构')
OUTSIDE = {
    '安全域': ('网络安全', '综合安全', '安全管理', '安全治理', '安全数据', '数据安全',
              '安全防护', '安全测评', '等保', '密码', '反诈', '诈骗', '垃圾短信',
              '僵木蠕', '态势感知', '上网日志留存', '授权及权限'),
    '经营及企业管理域': ('BOSS', 'PBOSS', 'CRMBOSS', 'CRM', '管理信息域', '财务', '营销', '市场经营',
                     '零售库存', '渠道类', '内容运营', '商客沙盘', '客户运营',
                     '公众服务', '无纸化', '印章管理', '招商', 'DICT项目管理',
                     '管理中台', '生态运营', '泛生态', '对外变现', '科研辅助',
                     '随销', '办公网', '桌面虚拟化'),
    '行业客户应用': ('无人车', '教育AI', '政务场景', '制造企业', '海洋人工智能',
                  '智能产线', '实训', '线下超市', '煤业', '工厂5G', '国网辽宁电力'),
    '工程施工及配套': ('工程施工', '施工服务', '施工一体化', '改造施工', '建设施工',
                    '施工项目', '迁改整治', '专网迁移', '机房建设', '机房改造',
                    '土建', '装修', '综合布线', '勘察设计', '监理', 'EPC总承包'),
    '硬件及物资供货': ('硬件集成', '分布式块存储', '木杆', '光模块', '板卡',
                    '一体化大功率基站', '基站车', '通信车', '蓄电池', '机柜',
                    '显示屏采购', '拼接屏', '大屏设备', 'LED显示'),
    '硬件技术研发': ('射频拓展', '通信舱'),
    '通信线路及连接服务': ('信令转接服务', '专线延伸服务', '链路）服务',
                        '链路)服务', '云网络连接服务'),
    '其他采购': ('租赁', '房租', '物业', '劳务', '审计', '保险', '废旧', '回收', '印刷'),
}
MAINTENANCE = ('维保', '协维', '代维', '维护服务', '支撑服务', '服务支撑',
               '技术支撑服务', '技术服务', '优化服务', '运营保障', '重保支撑',
               '外协服务', '规划咨询', '集成服务')


def hits(text, words):
    found = []
    for w in words:
        if w.isascii():
            matched = re.search(r'(?<![a-zA-Z])' + re.escape(w) + r'(?![a-zA-Z])', text, re.I)
        else:
            matched = w in text
        if matched:
            found.append(w)
    return found


def _subject(title):
    # Retain the existing provincial/headquarters eligibility check.
    from classifier import check_province
    ok, reason = check_province(title)
    if not ok:
        return False, reason
    if hits(title, ('联通数字科技', '联通数科', '联通视频公司', '产业公司', '量子信息科技')):
        return False, '专业子公司或行业客户项目'
    return True, ''


def classify_network(title, content=''):
    title = str(title or '')
    eligible, why = _subject(title)
    if not eligible:
        return False, '范围外', why
    for category, words in OUTSIDE.items():
        found = hits(title, words)
        if found:
            return False, '范围外', category + '：' + '、'.join(found[:2])
    net = hits(title, NETWORK)
    soft = hits(title, SOFTWARE)
    dev = hits(title, DEVELOPMENT)
    change = hits(title, SOFTWARE_CHANGE)
    visualization = hits(title, ('监控大屏', '大屏监控', '监控可视化'))
    if visualization and hits(title, ('可视化', '软件')) and hits(title, ('开发', '研发', '定制')):
        return True, '强相关', '监控可视化软件开发：' + '、'.join(visualization)
    # Maintenance of a platform is distinct from development of that platform.
    maintenance = hits(title, MAINTENANCE)
    if maintenance and not (soft and change):
        return False, '范围外', '纯维护、技术支撑或工程集成服务：' + maintenance[0]
    if re.search(r'(?:基站|路由器|交换机|服务器|光缆|终端|设备)(?:集中)?(?:采购|购置)', title) and not (soft and change):
        return False, '范围外', '设备或物资供货'
    if net and (soft or dev):
        return True, '强相关', '网络对象：' + '、'.join(net[:2]) + '；交付：' + '、'.join((soft or dev)[:2])
    # Only explicit procurement-scope statements may establish a missing domain.
    # Do not match agency names, qualifications, company descriptions or contacts.
    scope_lines = []
    for line in str(content or '').splitlines():
        m = re.search(r'(?:采购内容|建设内容|项目内容|服务内容|采购范围|建设范围)\s*[:：]\s*(.{8,500})', line)
        if m:
            scope_lines.append(m.group(1))
    for scope in scope_lines:
        if not any(hits(scope, words) for words in OUTSIDE.values()):
            ns = hits(scope, NETWORK)
            if ns and hits(scope, SOFTWARE) and hits(scope, SOFTWARE_CHANGE):
                return True, '强相关', '采购范围明确网络软件建设：' + '、'.join(ns[:2])
    if net:
        return False, '待核验', '涉及网络对象，但未明确软件、平台或研发交付'
    return False, '待核验', '未明确网络运营场景；通用研发、AI或平台名称不单独作为纳入依据'


def needs_detail(title):
    """A candidate may need its procurement scope before final inclusion."""
    keep, level, _ = classify_network(title)
    return keep or (level == '待核验' and bool(hits(title, SOFTWARE)))
