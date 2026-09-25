import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from audit import audit  # noqa: E402

BASE = json.loads((ROOT / "ai-models.json").read_text(encoding="utf-8"))
TODAY = date(2026, 9, 25)


def model(**f):
    m = {"id": "m", "provider": "anthropic", "label": "M", "kind": "chat", "tier": "fast", "status": "active",
         "capabilities": ["text"], "requires": [],
         "pricing": [{"from": "2026-09-25", "unit": "usd_per_mtok", "input": 1, "output": 5, "source": "https://x"}],
         "pricing_verified": "2026-09-25"}
    m.update(f)
    return {"schema_version": 1, "updated": "2026-09-25", "models": [m]}


class AuditTest(unittest.TestCase):
    def test_current_file_on_first_day(self):
        # 2026-09-25 기준 실제로 30일 안에 은퇴하는 deprecated 모델만 나와야 한다(단가·권장값 문제는 없음).
        found = audit(copy.deepcopy(BASE), TODAY)
        self.assertTrue(found)
        self.assertTrue(all(f.startswith("은퇴 임박") for f in found), found)

    def test_retire_date_passed(self):
        self.assertTrue(any("은퇴일 지남" in f for f in audit(model(status="deprecated", retire_on="2026-09-01"), TODAY)))

    def test_retire_soon(self):
        self.assertTrue(any("은퇴 임박" in f for f in audit(model(status="deprecated", retire_on="2026-10-10"), TODAY)))

    def test_pricing_stale(self):
        self.assertTrue(any("재확인" in f for f in audit(model(pricing_verified="2026-06-01"), TODAY)))

    def test_no_price_today(self):
        future = [{"from": "2026-12-01", "unit": "usd_per_mtok", "input": 1, "output": 5, "source": "https://x"}]
        self.assertTrue(any("오늘 적용할 단가" in f for f in audit(model(pricing=future), TODAY)))

    def test_recommended_not_active(self):
        data = model(status="legacy")
        data["recommended"] = {"anthropic": {"fast": "m"}}
        self.assertTrue(any("권장값" in f for f in audit(data, TODAY)))

    def test_alias_and_retired_skipped(self):
        data = model()
        data["models"].append({"id": "m-2026", "alias_of": "m", "provider": "anthropic", "label": "M", "kind": "chat", "status": "active"})
        data["models"].append({"id": "old", "provider": "anthropic", "label": "Old", "kind": "chat", "status": "retired",
                               "retired_on": "2026-01-01", "replace_with": "m"})
        self.assertEqual(audit(data, TODAY), [])


if __name__ == "__main__":
    unittest.main()
