"""ai-models.json 검사: JSON Schema + 스키마로 표현하기 어려운 규칙.

사용: python scripts/validate.py [파일 경로]   (기본: ai-models.json)
종료 코드 0 = 통과, 1 = 위반.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 과거에 실제로 쓰였던 존재하지 않는 ID 형태 — 다시 들어오지 않게 막는다.
KNOWN_TYPOS = {"claude-haiku-3-5", "claude-sonnet-4-5-20250514", "claude-haiku-4-20250514"}
# 4.6 세대 이후 Claude ID 는 날짜가 붙지 않는다 (예: claude-sonnet-4-6-2026xxxx 는 오타).
DATED_NEW_CLAUDE = re.compile(r"^claude-(opus|sonnet|haiku|fable)-(4-[6-9]|[5-9])(-\d+)?-\d{8}$")


DATE_FIELDS = ("retire_not_before", "retire_on", "retired_on")
# 단가를 공식 문서에서 확인할 수 없어 일시적으로 빼 두는 모델. 추가할 때는 이유를 주석으로 남긴다.
PRICING_EXEMPT: set[str] = set()


def _bad_date(value) -> bool:
    try:
        date.fromisoformat(value)
        return False
    except (TypeError, ValueError):
        return True


def rule_errors(data: dict) -> list[str]:
    errors = []
    if _bad_date(data["updated"]):
        errors.append(f"updated 가 실제 날짜가 아님: {data['updated']}")
    models = data["models"]
    by_id = {}
    for m in models:
        if m["id"] in by_id:
            errors.append(f"중복 id: {m['id']}")
        by_id[m["id"]] = m

    for m in models:
        mid = m["id"]
        if mid in KNOWN_TYPOS or DATED_NEW_CLAUDE.match(mid):
            errors.append(f"존재하지 않는 형태의 id: {mid}")
        for f in DATE_FIELDS:
            if f in m and _bad_date(m[f]):
                errors.append(f"{mid}.{f} 가 실제 날짜가 아님: {m[f]}")
        for ref_field in ("replace_with", "alias_of"):
            ref = m.get(ref_field)
            if ref is None:
                continue
            target = by_id.get(ref)
            if target is None:
                errors.append(f"{mid}.{ref_field} 가 목록에 없는 id 를 가리킴: {ref}")
            elif target["provider"] != m["provider"]:
                errors.append(f"{mid}.{ref_field} 가 다른 제공사를 가리킴: {ref}")
            elif ref_field == "replace_with" and target["status"] == "retired":
                errors.append(f"{mid}.replace_with 가 은퇴 모델을 가리킴: {ref}")
            elif ref_field == "replace_with" and target["kind"] != m["kind"]:
                errors.append(f"{mid}.replace_with 의 kind 가 다름: {ref}")
            elif ref_field == "replace_with" and "alias_of" in target:
                errors.append(f"{mid}.replace_with 가 별칭(선택지에 안 나옴)을 가리킴: {ref} → {target['alias_of']} 로")
        if m.get("kind") == "embedding" and (m.get("requires") or m.get("tier")):
            errors.append(f"{mid}: embedding 에는 tier·requires 를 쓰지 않는다")
        pricing = m.get("pricing")
        if m.get("alias_of") is not None:
            if pricing is not None or "pricing_verified" in m:
                errors.append(f"{mid}: 별칭은 pricing·pricing_verified 를 갖지 않는다(원본 단가를 쓴다)")
            target = by_id.get(m["alias_of"])
            if target is not None and "alias_of" in target:
                errors.append(f"{mid}.alias_of 가 별칭을 가리킴(다단계·자기 참조 금지): {m['alias_of']}")
            elif target is not None and target["kind"] != m["kind"]:
                errors.append(f"{mid}.alias_of 의 kind 가 다름: {m['alias_of']}")
        if pricing is not None:
            if "pricing_verified" not in m:
                errors.append(f"{mid}: pricing 이 있으면 pricing_verified 가 필요하다")
            elif _bad_date(m["pricing_verified"]):
                errors.append(f"{mid}.pricing_verified 가 실제 날짜가 아님: {m['pricing_verified']}")
            froms = [p["from"] for p in pricing]
            for f in froms:
                if _bad_date(f):
                    errors.append(f"{mid}.pricing.from 이 실제 날짜가 아님: {f}")
            if any(a >= b for a, b in zip(froms, froms[1:])):
                errors.append(f"{mid}.pricing 은 from 오름차순이고 같은 날이 두 번 나오면 안 된다: {froms}")
            if m["kind"] == "chat" and any("output" not in p for p in pricing):
                errors.append(f"{mid}.pricing: chat 모델은 output 단가가 필요하다")
        if (m["status"] != "retired" and m.get("alias_of") is None
                and m["kind"] in ("chat", "embedding") and pricing is None and mid not in PRICING_EXEMPT):
            errors.append(f"{mid}: 은퇴하지 않은 모델은 단가(pricing)가 필요하다")
    for prov, tiers in (data.get("recommended") or {}).items():
        for tier, rid in tiers.items():
            t = by_id.get(rid)
            where = f"recommended.{prov}.{tier}"
            if t is None:
                errors.append(f"{where} 가 목록에 없는 id 를 가리킴: {rid}")
            elif t["provider"] != prov:
                errors.append(f"{where} 가 다른 제공사 모델을 가리킴: {rid}")
            elif "alias_of" in t:
                errors.append(f"{where} 가 별칭을 가리킴: {rid}")
            elif t["kind"] != "chat" or t.get("tier") != tier:
                errors.append(f"{where} 의 kind·tier 가 맞지 않음: {rid} ({t['kind']}/{t.get('tier')})")
            elif t["status"] != "active":
                errors.append(f"{where} 는 active 모델만 가능: {rid} ({t['status']})")
    return errors


def validate(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"읽기 실패: {e}"]
    import jsonschema  # CI 에서 설치. 규칙 검사만 필요하면 rule_errors() 를 직접 쓴다.
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    schema_errors = [f"스키마: {'/'.join(map(str, e.absolute_path))}: {e.message}"
                     for e in jsonschema.Draft202012Validator(schema).iter_errors(data)]
    if schema_errors:
        return schema_errors  # 구조가 틀리면 규칙 검사가 KeyError 로 죽으므로 여기서 멈춘다
    return rule_errors(data)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ai-models.json"
    errs = validate(target)
    for e in errs:
        print(f"ERROR {e}")
    print("OK" if not errs else f"{len(errs)}건 위반")
    sys.exit(1 if errs else 0)
