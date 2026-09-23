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
    m = {k: v for k, v in m.items() if v is not None}
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

    def test_unknown_kind(self):
        self.assertTrue(any("스키마" in e for e in run(with_model(kind="music"))))

    def test_media_requires_tier(self):
        errs = run(with_model(id="gpt-image-x", provider="openai", kind="image",
                              tier=None, capabilities=None, requires=None))
        self.assertTrue(any("tier" in e for e in errs))

    def test_media_passes(self):
        m = {"id": "gpt-image-x", "provider": "openai", "label": "X", "kind": "image", "tier": "fast", "status": "active"}
        data = copy.deepcopy(BASE)
        data["models"].append(m)
        self.assertEqual(run(data), [])

    def test_media_no_chat_fields(self):
        errs = run(with_model(id="gpt-tts-x", provider="openai", kind="tts"))
        self.assertTrue(any("chat 에만" in e for e in errs))

    def test_dimensions_only_embedding(self):
        self.assertTrue(any("embedding 에만" in e for e in run(with_model(dimensions=8))))

    def test_replace_with_other_kind(self):
        errs = run(with_model(id="gpt-image-x", provider="openai", kind="image", tier="fast",
                              capabilities=None, requires=None, replace_with="gpt-4o"))
        self.assertTrue(any("kind 가 다름" in e for e in errs))

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{")
        try:
            self.assertTrue(validate(Path(f.name))[0].startswith("읽기 실패"))
        finally:
            Path(f.name).unlink()


if __name__ == "__main__":
    unittest.main()
