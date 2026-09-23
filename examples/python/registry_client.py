"""ai-models 목록 조회 예제 (Python 3.9+, 표준 라이브러리만).

서비스 레포에 복사해 쓰고, 복사한 뒤에는 서비스 코드로 관리한다. 기준: ai-models schema_version 1.
- 서버에서 조회한다(브라우저 X). 3초 제한, 1시간 캐시.
- 실패 시 마지막 캐시 → FALLBACK_MODELS 순. 예외를 밖으로 던지지 않는다.
"""
import json
import os
import threading
import time
import urllib.request

REGISTRY_URL = os.environ.get(
    "AI_MODELS_URL", "https://raw.githubusercontent.com/imcorp-service/ai-models/main/ai-models.json")
TTL_SECONDS = 3600
TIMEOUT_SECONDS = 3

# ── 서비스마다 바꾸는 부분 ──────────────────────────────────────────
ALLOWED_PROVIDERS = {"anthropic"}          # 호출 코드를 가진 제공사만
SUPPORTS = {"no_sampling_params", "no_thinking_budget"}  # 코드가 지키는 요청 형식 플래그 (README 참고)
FALLBACK_MODELS = [                        # 목록을 못 받을 때 보여줄 최소 목록
    {"id": "claude-sonnet-5", "provider": "anthropic", "label": "Claude Sonnet 5", "kind": "chat",
     "tier": "balanced", "status": "active", "capabilities": ["text", "vision", "tools"],
     "requires": ["no_sampling_params", "no_thinking_budget"]},
]
# ────────────────────────────────────────────────────────────────

_STATUS_ORDER = {"active": 0, "legacy": 1, "deprecated": 2, "preview": 3}
_TIER_ORDER = {"best": 0, "balanced": 1, "fast": 2}
_lock = threading.Lock()
_cache = {"models": None, "at": 0.0}


MAX_BYTES = 1_000_000
_REQUIRED_STR = ("id", "provider", "label", "kind", "status")


def _fetch():
    # urlopen 의 timeout 은 소켓 동작 1회 기준이라, 전체 소요 시간은 직접 잘라낸다.
    # ponytail: 멈춘 read() 는 소켓 타임아웃으로 끊기므로 최악 약 2×TIMEOUT(6초). 엄밀한 상한이 필요하면 스레드+join(timeout).
    deadline = time.monotonic() + TIMEOUT_SECONDS
    req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": "ai-models-client"})
    body = b""
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        while chunk := resp.read(65536):
            body += chunk
            if time.monotonic() > deadline or len(body) > MAX_BYTES:
                raise TimeoutError("registry fetch too slow or too large")
    data = json.loads(body.decode("utf-8"))
    models = data.get("models") if isinstance(data, dict) else None
    if (not isinstance(models, list) or data.get("schema_version") != 1
            or not all(isinstance(m, dict) and all(isinstance(m.get(k), str) for k in _REQUIRED_STR)
                       for m in models)):
        raise ValueError("unsupported registry format")
    return models


def load_models():
    """(models, source) 반환. source 는 'registry' | 'cache' | 'fallback'."""
    with _lock:
        if _cache["models"] is not None and time.time() - _cache["at"] < TTL_SECONDS:
            return _cache["models"], "cache"
    try:  # 조회 중에는 잠금을 잡지 않는다 — 느린 조회가 다른 요청의 캐시 읽기를 막지 않게
        models = _fetch()
    except Exception:  # 네트워크·형식 오류 모두 화면을 막지 않는다
        with _lock:
            if _cache["models"] is not None:
                return _cache["models"], "cache"
        return FALLBACK_MODELS, "fallback"
    with _lock:
        _cache["models"], _cache["at"] = models, time.time()
    return models, "registry"


def model_options(required_caps=("text",)):
    """선택 상자용 목록. 각 항목에 selectable·reason 을 붙여 돌려준다."""
    models, source = load_models()
    options = []
    for m in models:
        if (m.get("kind") != "chat" or m.get("provider") not in ALLOWED_PROVIDERS
                or m.get("status") == "retired" or m.get("alias_of")
                or not set(required_caps) <= set(m.get("capabilities", []))):
            continue
        missing = set(m.get("requires", [])) - SUPPORTS
        options.append({**m, "selectable": not missing,
                        "reason": "코드 업데이트 필요" if missing else None})
    options.sort(key=lambda m: (_STATUS_ORDER.get(m["status"], 9),
                                _TIER_ORDER.get(m.get("tier"), 9), m["label"]))
    return options, source


def describe(model_id):
    """현재 저장값 설명. 목록에 없으면 None → 화면에 '목록에 없음' 표시(값은 그대로 유지)."""
    models, _ = load_models()
    return next((m for m in models if m["id"] == model_id), None)


if __name__ == "__main__":
    opts, src = model_options()
    print(f"source={src}")
    for o in opts:
        print(f"{'  ' if o['selectable'] else 'x '}{o['id']:<28} {o['status']:<10} {o.get('reason') or ''}")
    cur = describe("claude-sonnet-4-20250514")
    print("current:", cur and f"{cur['status']} → {cur.get('replace_with')}")
