import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples" / "python"))
import registry_client as rc  # noqa: E402

DOC = json.loads((ROOT / "conformance" / "cases.json").read_text(encoding="utf-8"))


class ConformanceTest(unittest.TestCase):
    def test_cases(self):
        reg = rc.parse_registry(DOC["registry"])
        for c in DOC["cases"]:
            with self.subTest(c["name"]):
                op = c["op"]
                if op == "parse":
                    doc = {**copy.deepcopy(DOC["registry"]), **c["patch"]}
                    try:
                        rc.parse_registry(doc)
                        got = "ok"
                    except ValueError:
                        got = "error"
                    self.assertEqual(got, c["expect"])
                elif op == "options":
                    opts = rc.build_options(reg["models"], set(c["allowed"]), set(c["supports"]),
                                            tuple(c["required_caps"]))
                    self.assertEqual([{"id": o["id"], "selectable": o["selectable"], "reason": o["reason"]}
                                      for o in opts], c["expect"])
                elif op == "price":
                    self.assertEqual(rc.price_for(reg["models"], c["id"], c["on"]), c["expect"])
                elif op == "default":
                    opts = rc.build_options(reg["models"], set(c["allowed"]), set(c["supports"]))
                    self.assertEqual(rc.pick_default(reg["models"], reg["recommended"], c["provider"], opts,
                                                     c["tier"], c["builtin"]), c["expect"])
                else:
                    self.fail(f"모르는 op: {op}")

    def test_today_kst_format(self):
        self.assertRegex(rc.today_kst(), r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
