// ai-models 목록 조회 예제 (Node 18+, 의존성 없음). 기준: ai-models schema_version 1.
// 서비스 레포에 복사해 쓰고, 복사한 뒤에는 서비스 코드로 관리한다.
// 서버에서 조회(브라우저 X), 3초 제한, 1시간 캐시, 실패 시 마지막 캐시 → FALLBACK_MODELS.

export interface Model {
  id: string; provider: string; label: string; kind: "chat" | "embedding"; status: string;
  alias_of?: string; tier?: string; capabilities?: string[]; requires?: string[];
  retire_not_before?: string; retire_on?: string; retired_on?: string; replace_with?: string; note?: string;
}
export type Source = "registry" | "cache" | "fallback";
export interface Option extends Model { selectable: boolean; reason: string | null }

const REGISTRY_URL = process.env.AI_MODELS_URL
  ?? "https://raw.githubusercontent.com/imcorp-service/ai-models/main/ai-models.json";
const TTL_MS = 3_600_000;
const TIMEOUT_MS = 3_000;

// ── 서비스마다 바꾸는 부분 ──────────────────────────────────────────
const ALLOWED_PROVIDERS = new Set(["anthropic"]);
const SUPPORTS = new Set(["no_sampling_params", "no_thinking_budget"]); // 코드가 지키는 요청 형식 플래그 (README 참고)
const FALLBACK_MODELS: Model[] = [
  { id: "claude-haiku-4-5", provider: "anthropic", label: "Claude Haiku 4.5", kind: "chat",
    tier: "fast", status: "active", capabilities: ["text", "vision", "tools"], requires: [] },
];
// ────────────────────────────────────────────────────────────────

const STATUS_ORDER: Record<string, number> = { active: 0, legacy: 1, deprecated: 2, preview: 3 };
const TIER_ORDER: Record<string, number> = { best: 0, balanced: 1, fast: 2 };
const REQUIRED_STR = ["id", "provider", "label", "kind", "status"] as const;
let cache: { models: Model[]; at: number } | null = null;
let inflight: Promise<[Model[], Source]> | null = null;

async function fetchModels(): Promise<Model[]> {
  // AbortSignal.timeout 은 본문 읽기까지 포함한 전체 시간을 자른다.
  const res = await fetch(REGISTRY_URL, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const valid = data?.schema_version === 1 && Array.isArray(data.models) && data.models.every(
    (m: unknown) => typeof m === "object" && m !== null
      && REQUIRED_STR.every((k) => typeof (m as Record<string, unknown>)[k] === "string"));
  if (!valid) throw new Error("unsupported registry format");
  return data.models;
}

export function loadModels(): Promise<[Model[], Source]> {
  if (cache && Date.now() - cache.at < TTL_MS) return Promise.resolve([cache.models, "cache"]);
  // 동시에 여러 요청이 와도 원격 조회는 1번만 한다.
  inflight ??= fetchModels()
    .then((models): [Model[], Source] => { cache = { models, at: Date.now() }; return [models, "registry"]; })
    .catch((): [Model[], Source] => (cache ? [cache.models, "cache"] : [FALLBACK_MODELS, "fallback"]))
    .finally(() => { inflight = null; });
  return inflight;
}

export async function modelOptions(requiredCaps: string[] = ["text"]): Promise<[Option[], Source]> {
  const [models, source] = await loadModels();
  const options = models
    .filter((m) => m.kind === "chat" && ALLOWED_PROVIDERS.has(m.provider) && m.status !== "retired"
      && !m.alias_of && requiredCaps.every((c) => m.capabilities?.includes(c)))
    .map((m) => {
      const missing = (m.requires ?? []).filter((r) => !SUPPORTS.has(r));
      return { ...m, selectable: missing.length === 0, reason: missing.length ? "코드 업데이트 필요" : null };
    });
  options.sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    || (TIER_ORDER[a.tier ?? ""] ?? 9) - (TIER_ORDER[b.tier ?? ""] ?? 9) || a.label.localeCompare(b.label));
  return [options, source];
}

/** 현재 저장값 설명. 목록에 없으면 undefined → 화면에 '목록에 없음' 표시(값은 그대로 유지). */
export async function describe(modelId: string): Promise<Model | undefined> {
  const [models] = await loadModels();
  return models.find((m) => m.id === modelId);
}
