import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collector
import db
import winner_backfill


class WinnerTests(unittest.TestCase):
    def test_pdf_break(self):
        self.assertEqual(collector.parse_winner("中选人为中移（杭州\n）信息技术有限\n公司。采购人：中国移动通信集团广西有限公司"), "中移（杭州）信息技术有限公司")

    def test_all_packages(self):
        names = ["甲方信息有限公司", "乙方通信有限公司", "丙方科技有限公司", "丁方软件有限公司"]
        text = "中标人：\n" + "\n".join(f"{i+1}.{n}" for i, n in enumerate(names)) + "\n采购人：某某集团有限公司"
        self.assertEqual(collector.parse_winner(text), "、".join(names))

    def test_complete_design_institute_name(self):
        self.assertEqual(collector.parse_winner("中选人：1.中国移动通信集团设计院有限公司\n采购人：中国移动通信集团天津有限公司"), "中国移动通信集团设计院有限公司")
        self.assertEqual(collector.parse_winner("成交人：\n中国信息通信研究院\n采购人：某某集团有限公司"), "中国信息通信研究院")

    def test_candidate_labels(self):
        self.assertEqual(collector.parse_winner("成交候选人如下：亚信科技（中国）有限公司\n采购人：某某集团有限公司"), "亚信科技（中国）有限公司")
        self.assertEqual(collector.parse_winner("第一中选候选人：甲方信息有限公司；第二中选候选人：乙方科技有限公司"), "甲方信息有限公司")

    def test_no_false_buyers(self):
        for text in ["中选人数量：1个。采购人：某某集团有限公司", "中选人：详见附件。代理机构：某某咨询有限公司", "中选候选人公示发布媒体：某某信息有限公司", "采购人：某某集团有限公司；代理机构：某某咨询有限公司", "中选人：无。采购人：某某集团有限公司"]:
            self.assertIsNone(collector.parse_winner(text), text)

    def test_backfill_preserves_history(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp); snaps = root / "snapshots"; snaps.mkdir()
            with patch.object(db, "BASE", root), patch.object(db, "DB", root / "bids.db"), patch.object(db, "SNAP", snaps):
                db.init()
                original = snaps / "sample.html"; original.write_text("原始快照", encoding="utf-8")
                with db.conn() as c:
                    c.execute("INSERT INTO bids(id,title,content,status,first_seen,last_seen,snapshot_path) VALUES(?,?,?,?,?,?,?)", ("sample", "中选结果公示", "原有正文", "archived", "2020-01-01", "2020-02-01", "snapshots/sample.html"))
                    row = dict(c.execute("SELECT * FROM bids").fetchone())
                self.assertTrue(winner_backfill.apply_text(row, "中选人：测试信息有限公司"))
                self.assertFalse(winner_backfill.apply_text(row, "中选人：其他信息有限公司"))
                with db.conn() as c:
                    after = dict(c.execute("SELECT * FROM bids").fetchone())
                self.assertEqual({k:v for k,v in after.items() if k != "winner"}, {k:v for k,v in row.items() if k != "winner"})
                self.assertEqual(original.read_text(encoding="utf-8"), "原始快照")
                db.checkpoint()
                c.close()
                import gc
                gc.collect()


if __name__ == "__main__":
    unittest.main()
