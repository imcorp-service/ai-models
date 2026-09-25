import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from validate import validate  # noqa: E402

BASE = json.loads((ROOT / "ai-models.json").read_text(encoding="utf-8"))


def run(data) -> list[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
    try:
        return validate(Path(f.name))
    finally:
        Path(f.name).unlink()


def with_model(**fields):
    data = copy.deepcopy(BASE)
    m = {"id": "claude-x", "provider": "anthropic", "label": "X", "kind": "chat", "tier": "fast",
         "status": "active", "capabilities": ["text"], "requires": []}
    m.update(fields)
    data["models"].append(m)
    return data


class ValidateTest(unittest.TestCase):
    def test_current_file_passes(self):
        self.assertEqual(run(BASE), [])

    def test_duplicate_id(self):
        self.assertTrue(any("중복" in e for e in run(with_model(id="claude-sonnet-5"))))

    def test_known_typo(self):
        self.assertTrue(any("존재하지 않는" in e for e in run(with_model(id="claude-haiku-3-5"))))

    def test_dated_new_generation_claude(self):
        self.assertTrue(any("존재하지 않는" in e for e in run(with_model(id="claude-sonnet-5-20260101"))))

    def test_replace_with_missing(self):
        self.assertTrue(any("목록에 없는" in e for e in run(with_model(replace_with="claude-nope"))))

    def test_replace_with_retired(self):
        self.assertTrue(any("은퇴 모델" in e for e in run(with_model(replace_with="claude-3-opus-20240229"))))

    def test_replace_with_other_provider(self):
        self.assertTrue(any("다른 제공사" in e for e in run(with_model(replace_with="gpt-4o"))))

    def test_retired_requires_date(self):
        errs = run(with_model(status="retired", replace_with="claude-sonnet-5"))
        self.assertTrue(any("retired_on" in e for e in errs))

    def test_impossible_date(self):
        self.assertTrue(any("실제 날짜" in e for e in run(with_model(retire_not_before="2026-02-31"))))

    def test_updated_not_a_date(self):
        data = copy.deepcopy(BASE)
        data["updated"] = "not-a-date"
        self.assertTrue(any("updated" in e for e in run(data)))

    def test_replace_with_alias(self):
        self.assertTrue(any("별칭" in e for e in run(with_model(replace_with="claude-haiku-4-5-20251001"))))

    def test_unknown_flag(self):
        self.assertTrue(any("스키마" in e for e in run(with_model(requires=["no_temperature"]))))

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{")
        try:
            self.assertTrue(validate(Path(f.name))[0].startswith("읽기 실패"))
        finally:
            Path(f.name).unlink()

    P = {"from": "2026-09-25", "unit": "usd_per_mtok", "input": 1, "output": 5,
         "source": "https://example.com/pricing"}

    def test_pricing_ok(self):
        self.assertEqual(run(with_model(pricing=[self.P], pricing_verified="2026-09-25")), [])

    def test_pricing_unknown_unit(self):
        errs = run(with_model(pricing=[{**self.P, "unit": "usd_per_image"}], pricing_verified="2026-09-25"))
        self.assertTrue(any("스키마" in e for e in errs))

    def test_pricing_negative(self):
        errs = run(with_model(pricing=[{**self.P, "input": -1}], pricing_verified="2026-09-25"))
        self.assertTrue(any("스키마" in e for e in errs))

    def test_pricing_http_source(self):
        errs = run(with_model(pricing=[{**self.P, "source": "http://example.com"}], pricing_verified="2026-09-25"))
        self.assertTrue(any("스키마" in e for e in errs))

    def test_pricing_order(self):
        later = {**self.P, "from": "2027-01-01"}
        errs = run(with_model(pricing=[later, self.P], pricing_verified="2026-09-25"))
        self.assertTrue(any("pricing" in e and "오름차순" in e for e in errs))

    def test_pricing_same_day_twice(self):
        errs = run(with_model(pricing=[self.P, {**self.P, "input": 2}], pricing_verified="2026-09-25"))
        self.assertTrue(any("pricing" in e and "오름차순" in e for e in errs))

    def test_pricing_impossible_date(self):
        errs = run(with_model(pricing=[{**self.P, "from": "2026-02-31"}], pricing_verified="2026-09-25"))
        self.assertTrue(any("실제 날짜" in e for e in errs))

    def test_chat_pricing_needs_output(self):
        p = {k: v for k, v in self.P.items() if k != "output"}
        errs = run(with_model(pricing=[p], pricing_verified="2026-09-25"))
        self.assertTrue(any("output" in e for e in errs))

    def test_pricing_needs_verified(self):
        errs = run(with_model(pricing=[self.P]))
        self.assertTrue(any("pricing_verified" in e for e in errs))

    def test_alias_with_pricing(self):
        errs = run(with_model(id="claude-x-alias", alias_of="claude-sonnet-5",
                              pricing=[self.P], pricing_verified="2026-09-25"))
        self.assertTrue(any("별칭" in e and "pricing" in e for e in errs))

    def test_alias_of_alias(self):
        errs = run(with_model(id="claude-x-alias", alias_of="claude-haiku-4-5-20251001"))
        self.assertTrue(any("별칭" in e and "별칭을 가리킴" in e for e in errs))

    def test_alias_self(self):
        errs = run(with_model(id="claude-x", alias_of="claude-x"))
        self.assertTrue(any("별칭을 가리킴" in e for e in errs))

    def test_alias_kind_mismatch(self):
        data = with_model(id="claude-x-emb", kind="embedding", dimensions=8, alias_of="claude-sonnet-5")
        for k in ("tier", "requires", "capabilities"):
            data["models"][-1].pop(k, None)
        self.assertTrue(any("kind" in e and "alias_of" in e for e in run(data)))

    def test_selectable_model_needs_pricing(self):
        errs = run(with_model())   # with_model 기본값은 단가 없는 active chat
        self.assertTrue(any("claude-x" in e and "단가" in e for e in errs))

    def test_retired_model_needs_no_pricing(self):
        errs = run(with_model(status="retired", retired_on="2026-01-01", replace_with="claude-sonnet-5"))
        self.assertFalse(any("단가" in e for e in errs))

    def with_rec(self, rec):
        data = copy.deepcopy(BASE)
        data["recommended"] = rec
        return data

    def test_recommended_ok(self):
        self.assertEqual(run(self.with_rec({"anthropic": {"balanced": "claude-sonnet-5"}})), [])

    def test_recommended_unknown_tier(self):
        errs = run(self.with_rec({"anthropic": {"cheap": "claude-haiku-4-5"}}))
        self.assertTrue(any("스키마" in e for e in errs))

    def test_recommended_unknown_provider(self):
        errs = run(self.with_rec({"someai": {"fast": "claude-haiku-4-5"}}))
        self.assertTrue(any("스키마" in e for e in errs))

    def test_recommended_missing_id(self):
        errs = run(self.with_rec({"anthropic": {"fast": "claude-nope"}}))
        self.assertTrue(any("recommended" in e and "목록에 없는" in e for e in errs))

    def test_recommended_wrong_provider(self):
        errs = run(self.with_rec({"anthropic": {"balanced": "gpt-4.1"}}))
        self.assertTrue(any("recommended" in e and "제공사" in e for e in errs))

    def test_recommended_wrong_tier(self):
        errs = run(self.with_rec({"anthropic": {"fast": "claude-sonnet-5"}}))
        self.assertTrue(any("recommended" in e and "tier" in e for e in errs))

    def test_recommended_not_active(self):
        errs = run(self.with_rec({"gemini": {"best": "gemini-3.1-pro-preview"}}))
        self.assertTrue(any("recommended" in e and "active" in e for e in errs))

    def test_recommended_alias(self):
        errs = run(self.with_rec({"anthropic": {"fast": "claude-haiku-4-5-20251001"}}))
        self.assertTrue(any("recommended" in e and "별칭" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
