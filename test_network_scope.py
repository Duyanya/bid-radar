import unittest
from classifier import classify


class ScopeTests(unittest.TestCase):
    def test_network_domain_and_resource_software(self):
        from network_scope import SEARCH_TERMS, hits

        titles = [
            '中国移动网络域平台建设项目',
            '四川移动宽带资源核配系统软件开发服务采购项目',
            '河北移动管线管理系统开发服务采购项目',
            '广东电信通信管道台账管理软件建设项目',
            '安徽移动杆路和管孔资源调度平台建设项目',
            '福建电信纤芯资源可视化软件开发项目',
            '湖北联通线路资源管理平台软件定制开发服务框架采购项目',
            '山东移动管线施工管理系统软件开发服务采购项目',
            '浙江移动管道资源租赁管理平台开发服务采购项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(hits(title, SEARCH_TERMS))
                self.assertTrue(classify(title)[0], classify(title))

    def test_resource_terms_do_not_admit_hardware_construction_or_standalone_services(self):
        titles = [
            '河北移动管线工程施工采购项目',
            '河北移动管线资源管理平台配套综合布线工程采购项目',
            '浙江移动网络域系统配套硬件框架集中采购项目',
            '安徽移动宽带管理系统配套设备及备件采购项目',
            '江西电信OLT设备研发项目',
            '浙江电信线路资源用光缆供货采购项目',
            '广东电信家宽业务交付运营系统服务保障项目',
            '广西移动管线资源管理系统建设技术支撑服务项目',
            '湖北移动通信网络风险资源防范能力验证服务采购项目',
            '江苏移动管线资源管理系统运维服务采购项目',
            '江苏移动管线资源盘点服务采购项目',
            '山东移动管线资源管理平台开发项目第三方测试服务采购项目',
            '福建移动人力资源管理系统软件开发采购项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(classify(title)[0], classify(title))

    def test_procurement_details_can_confirm_an_ambiguous_network_project(self):
        from network_scope import needs_detail

        title = '湖南移动网络域能力提升采购项目'
        self.assertTrue(needs_detail(title))
        self.assertTrue(classify(title, '采购内容：开发工单调度软件和可视化模块。')[0])
        title = '湖南移动管线资源管理服务采购项目'
        self.assertTrue(needs_detail(title))
        self.assertTrue(classify(title, '服务内容：开发管线资源台账管理软件和可视化模块。')[0])
        self.assertFalse(classify(title, '服务内容：提供管线资源管理系统日常运维服务。')[0])
        self.assertFalse(classify(title, '资格要求：具备管线资源管理软件开发经验。')[0])
        self.assertFalse(needs_detail('湖南移动管线资源管理系统维保服务采购项目'))

    def test_broadband_software_and_discovery(self):
        from network_scope import SEARCH_TERMS, hits
        titles = [
            '四川移动家庭宽带质量分析平台开发项目',
            '浙江移动千兆宽带业务感知系统建设项目',
            '广东电信万兆宽带智能诊断平台研发项目',
            '江苏联通家宽装维管理系统升级项目',
            '山东移动固网业务开通平台开发项目',
            '河北移动光接入资源管理系统建设项目',
            '福建电信全光组网质量分析平台研发项目',
            '湖北移动光纤到户业务测试软件研发项目',
            '陕西联通fttr质量分析系统开发项目',
            '安徽移动FTTH运维平台建设项目',
            '江西电信XGS-PON性能分析平台建设项目',
            '辽宁联通OLT配置管理平台开发项目',
            '云南移动ONU远程诊断系统研发项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(hits(title, SEARCH_TERMS), title)
                self.assertTrue(classify(title)[0], classify(title))

    def test_broadband_does_not_bypass_scope_boundaries(self):
        titles = [
            '四川移动家庭宽带工程施工采购项目',
            '浙江移动FTTR终端采购项目',
            '安徽电信GPON设备采购项目',
            '江西移动宽带代维服务采购项目',
            '广东电信家庭宽带营销系统开发项目',
            '中国电信南京分公司宽带诊断系统开发项目',
            '四川移动FRONT平台研发项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(classify(title)[0], classify(title))
        self.assertTrue(classify(
            '湖南移动质量分析平台开发项目',
            '采购内容：建设FTTR业务质量分析平台，支持业务诊断。')[0])

    def test_positive_network_software(self):
        titles = [
            '浙江移动网络指挥调度系统研发采购项目',
            '中国移动浙江公司2026年网络运营应用研发项目装维服务调度系统采购项目',
            '中国联通黑龙江接入网综合网管系统适配研发项目',
            '河北移动无线运维工作台研发采购项目',
            '辽宁移动传输运维工作台研发项目',
            '重庆移动网络优化管理系统功能研发采购项目',
            '云南移动家宽装维智能体方案研究项目',
            '河北移动数字化网络运营沙盘研发项目',
            '中国移动北京公司网管系统开发及维保框架采购项目',
            '中国移动江西公司OSS域资源及动环支撑研发项目',
            '江西移动OSS域传输运维管理研发服务采购项目',
            '江西移动智慧装维统一能力委托研发服务采购项目',
            '中国电信新疆长途传输局光网智能运维管理平台研发项目',
            '中国联通智能网络中台网络资源中心资源数据治理软件研发项目',
            '浙江移动IP网络设备配置核查助手软件研发项目',
            '中国移动广西公司2026年监控大屏可视化开发工程采购项目_询比公告',
            '广西移动大屏监控可视化软件定制开发采购项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(classify(title)[0], classify(title))

    def test_excluded_or_unproven(self):
        titles = [
            '山东移动2026-2028年室分工程施工采购项目_中标结果公示',
            '浙江移动国铁电话专网建设施工服务采购项目',
            '广西移动有线接入网迁改整治服务采购项目',
            '海南移动一体化大功率基站采购项目',
            '新疆移动传输网防腐油木杆采购项目',
            '中国移动网络云资源池工程硬件集成服务采购项目',
            '浙江移动核心网协维服务采购项目',
            '广西移动网管系统通用支撑服务采购项目',
            '江苏移动核心网设备采购项目',
            '福建移动财务运营管理平台研发采购项目',
            '甘肃移动BOSS&CRM系统研发采购项目',
            '河南联通云网综合安全管理平台研发项目',
            '广西移动僵木蠕监控系统软件开发采购项目',
            '山东移动垃圾短信系统开发采购项目',
            '安徽移动无人车智能调度软件开发采购项目',
            '北京移动教育AI应用服务平台研发项目',
            '江西移动商客沙盘研发采购项目',
            '湖南移动AI赋能生产研发采购项目',
            '湖南移动数字孪生可视化平台研发项目',
            '浙江移动数据中台研发项目',
            '浙江移动BOSS系统研发项目',
            '安徽移动PBOSS非资源及投诉预处理系统软件开发项目',
            '中国电信南京分公司云网智能调度平台研发项目',
            '广西移动监控中心LED显示屏采购项目',
            '广西移动监控大屏可视化设备采购项目',
            '广西移动监控大屏可视化软件维保服务采购项目',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(classify(title)[0], classify(title))

    def test_body_boilerplate_cannot_establish_domain(self):
        self.assertFalse(classify('湖南移动通用平台研发项目', '资格要求：具备5G网管软件开发业绩；代理机构：网络科技公司')[0])
        self.assertTrue(classify('湖南移动数字孪生平台研发项目', '采购内容：建设网络资源数字孪生平台，实现网络资源管理。')[0])
        self.assertFalse(classify('山东移动室分工程施工采购项目', '采购内容：建设网络监控软件平台。')[0])


if __name__ == '__main__':
    unittest.main()
