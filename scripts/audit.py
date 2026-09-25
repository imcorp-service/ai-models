"""정기 점검: 사람이 갱신을 잊기 쉬운 항목을 찾는다.

사용: python scripts/audit.py   → 발견 사항을 마크다운 목록으로 출력(없으면 빈 출력). 항상 종료 코드 0.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STALE_DAYS = 90
SOON_DAYS = 30


def audit(data: dict, today: date) -> list[str]:
    found = []
    t = today.isoformat()
    soon = (today + timedelta(days=SOON_DAYS)).isoformat()
    stale = (today - timedelta(days=STALE_DAYS)).isoformat()
    by_id = {m["id"]: m for m in data["models"]}
    for m in data["models"]:
        mid, st, ro = m["id"], m["status"], m.get("retire_on")
        if st != "retired" and ro and ro < t:
            found.append(f"은퇴일 지남: `{mid}` retire_on={ro}, status={st}")
        elif st == "deprecated" and ro and ro <= soon:
            found.append(f"은퇴 임박({SOON_DAYS}일 이내): `{mid}` retire_on={ro}")
        if st == "retired" or m.get("alias_of") or m["kind"] not in ("chat", "embedding"):
            continue
        v = m.get("pricing_verified")
        if not v or v < stale:
            found.append(f"단가 재확인 필요({STALE_DAYS}일 경과): `{mid}` pricing_verified={v}")
        if not any(p.get("unit") == "usd_per_mtok" and p.get("from", "9999-12-31") <= t for p in m.get("pricing") or []):
            found.append(f"오늘 적용할 단가 없음: `{mid}`")
    for prov, tiers in (data.get("recommended") or {}).items():
        for tier, rid in tiers.items():
            if by_id.get(rid, {}).get("status") != "active":
                found.append(f"권장값이 active 아님: {prov}.{tier} = `{rid}`")
    return found


def today_kst() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


if __name__ == "__main__":
    data = json.loads((ROOT / "ai-models.json").read_text(encoding="utf-8"))
    for f in audit(data, today_kst()):
        print(f"- {f}")
