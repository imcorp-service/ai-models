// ai-models 목록 조회 예제 (Node 18+, 의존성 없음). 기준: ai-models schema_version 1.
// 서비스 레포에 복사해 쓰고, 복사한 뒤에는 서비스 코드로 관리한다.
// 서버에서 조회(브라우저 X), 3초 제한, 1시간 캐시, 실패 시 마지막 캐시 → FALLBACK_MODELS.

export interface Model {
  id: string; provider: string; label: string; kind: "chat" | "embedding"; status: string;
  alias_of?: string; tier?: string; capabilities?: string[]; requires?: string[];
  retire_not_before?: string; retire_on?: string; retired_on?: string; replace_with?: string; note?: string;
  pricing?: PriceEntry[]; pricing_verified?: string;
}
export interface PriceEntry { from: string; unit: string; input: number; output?: number; source: string }
export interface Price { input: number; output: number | null }   // USD / 1M 토큰, 표준 조건
export interface Registry { models: Model[]; recommended: Record<string, Record<string, string>> }
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
const PRICE_UNIT = "usd_per_mtok";
const FALLBACK_REGISTRY: Registry = { models: FALLBACK_MODELS, recommended: {} };
let cache: { registry: Registry; at: number } | null = null;
let inflight: Promise<[Registry, Source]> | null = null;

/** 단가 적용 기준일(KST, YYYY-MM-DD). */
export function todayKst(): string {
  return new Date(Date.now() + 9 * 3_600_000).toISOString().slice(0, 10);
}

/** 목록 문서 형식 검사. 모르는 필드는 무시한다. */
export function parseRegistry(data: unknown): Registry {
  const d = data as { schema_version?: unknown; models?: unknown; recommended?: unknown } | null;
  const ok = d?.schema_version === 1 && Array.isArray(d.models) && d.models.every(
    (m: unknown) => typeof m === "object" && m !== null
      && REQUIRED_STR.every((k) => typeof (m as Record<string, unknown>)[k] === "string"));
  if (!ok || !d) throw new Error("unsupported registry format");
  const rec = typeof d.recommended === "object" && d.recommended !== null ? d.recommended : {};
  return { models: d.models as Model[], recommended: rec as Registry["recommended"] };
}

async function fetchRegistry(): Promise<Registry> {
  // AbortSignal.timeout 은 본문 읽기까지 포함한 전체 시간을 자른다.
  const res = await fetch(REGISTRY_URL, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return parseRegistry(await res.json());
}

export function loadRegistry(): Promise<[Registry, Source]> {
  if (cache && Date.now() - cache.at < TTL_MS) return Promise.resolve([cache.registry, "cache"]);
  // 동시에 여러 요청이 와도 원격 조회는 1번만 한다.
  inflight ??= fetchRegistry()
    .then((registry): [Registry, Source] => { cache = { registry, at: Date.now() }; return [registry, "registry"]; })
    .catch((): [Registry, Source] => (cache ? [cache.registry, "cache"] : [FALLBACK_REGISTRY, "fallback"]))
    .finally(() => { inflight = null; });
  return inflight;
}

export async function loadModels(): Promise<[Model[], Source]> {
  const [registry, source] = await loadRegistry();
  return [registry.models, source];
}

export function buildOptions(models: Model[], allowed: Set<string>, supports: Set<string>,
                             requiredCaps: string[] = ["text"]): Option[] {
  const options = models
    .filter((m) => m.kind === "chat" && allowed.has(m.provider) && m.status !== "retired"
      && !m.alias_of && requiredCaps.every((c) => m.capabilities?.includes(c)))
    .map((m) => {
      const missing = (m.requires ?? []).filter((r) => !supports.has(r));
      return { ...m, selectable: missing.length === 0, reason: missing.length ? "코드 업데이트 필요" : null };
    });
  options.sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    || (TIER_ORDER[a.tier ?? ""] ?? 9) - (TIER_ORDER[b.tier ?? ""] ?? 9) || a.label.localeCompare(b.label));
  return options;
}

export async function modelOptions(requiredCaps: string[] = ["text"]): Promise<[Option[], Source]> {
  const [models, source] = await loadModels();
  return [buildOptions(models, ALLOWED_PROVIDERS, SUPPORTS, requiredCaps), source];
}

const validPrice = (v: unknown): v is number => typeof v === "number" && v >= 0 && v <= 1000;

/** onDate(KST, YYYY-MM-DD) 에 적용되는 표준 단가. 모르면 null → 서비스는 내장표 → 비싼 기본값. */
export function priceFor(models: Model[], modelId: string, onDate: string): Price | null {
  const byId = new Map(models.map((m) => [m.id, m]));
  let m = byId.get(modelId);
  if (m?.alias_of) {
    m = byId.get(m.alias_of);
    if (m?.alias_of) m = undefined;   // 다단계 별칭은 믿지 않는다
  }
  if (!m) return null;
  let best: PriceEntry | null = null;
  for (const p of m.pricing ?? []) {
    if (p?.unit !== PRICE_UNIT || typeof p.from !== "string") continue;
    if (p.from <= onDate && (!best || p.from > best.from)) best = p;
  }
  if (!best || !validPrice(best.input)) return null;
  if (best.output !== undefined && best.output !== null && !validPrice(best.output)) return null;
  return { input: best.input, output: best.output ?? null };
}

/** 저장값이 없을 때의 기본 모델. 권장값 → 같은 tier 의 active(목록 순서) → builtin, 모두 같은 검사. */
export function pickDefault(models: Model[], recommended: Registry["recommended"], provider: string,
                            options: Option[], tier = "balanced", builtin: string | null = null): string | null {
  const usable = new Set(options.filter((o) => o.selectable && (o.status === "active" || o.status === "legacy")).map((o) => o.id));
  const candidates = [recommended?.[provider]?.[tier],
    ...models.filter((m) => m.provider === provider && m.tier === tier && m.status === "active" && !m.alias_of).map((m) => m.id),
    builtin];
  return candidates.find((c): c is string => typeof c === "string" && usable.has(c)) ?? null;
}

/** 현재 저장값 설명. 목록에 없으면 undefined → 화면에 '목록에 없음' 표시(값은 그대로 유지). */
export async function describe(modelId: string): Promise<Model | undefined> {
  const [models] = await loadModels();
  return models.find((m) => m.id === modelId);
}
