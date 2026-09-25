// ai-models 목록 조회 예제 (Java 17+, Jackson databind). 기준: ai-models schema_version 1.
// 서비스 레포에 복사해 패키지를 붙여 쓰고, 복사한 뒤에는 서비스 코드로 관리한다.
// 서버에서 조회(브라우저 X), 3초 제한, 1시간 캐시, 실패 시 마지막 캐시 → FALLBACK_MODELS.

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.MissingNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.StreamSupport;

public class RegistryClient {

    public record Option(JsonNode model, boolean selectable, String reason) {
        public String id() { return model.path("id").asText(); }
    }
    public record Loaded(Registry registry, String source) {   // source: registry | cache | fallback
        /** 예전 예제와의 호환: loadModels().models() */
        public List<JsonNode> models() { return registry.models(); }
    }
    public record Registry(List<JsonNode> models, JsonNode recommended) {}
    public record Price(double input, Double output) {}   // USD / 1M 토큰, 표준 조건. output 은 임베딩이면 null
    private static final String PRICE_UNIT = "usd_per_mtok";
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    /** 단가 적용 기준일(KST, YYYY-MM-DD). */
    public static String todayKst() { return LocalDate.now(KST).toString(); }

    /** 목록 문서 형식 검사. 모르는 필드는 무시한다. */
    public static Registry parse(JsonNode root) {
        if (root.path("schema_version").asInt() != 1 || !root.path("models").isArray())
            throw new IllegalStateException("unsupported registry format");
        List<JsonNode> models = StreamSupport.stream(root.path("models").spliterator(), false).toList();
        for (JsonNode m : models)
            for (String k : List.of("id", "provider", "label", "kind", "status"))
                if (!m.path(k).isTextual()) throw new IllegalStateException("unsupported registry format");
        JsonNode rec = root.path("recommended");
        return new Registry(models, rec.isObject() ? rec : MissingNode.getInstance());
    }

    private static final String REGISTRY_URL = Objects.requireNonNullElse(System.getenv("AI_MODELS_URL"),
            "https://raw.githubusercontent.com/imcorp-service/ai-models/main/ai-models.json");
    private static final long TTL_MS = 3_600_000L;
    private static final Duration TIMEOUT = Duration.ofSeconds(3);

    // ── 서비스마다 바꾸는 부분 ──────────────────────────────────────
    private static final Set<String> ALLOWED_PROVIDERS = Set.of("anthropic");
    private static final Set<String> SUPPORTS = Set.of("no_sampling_params", "no_thinking_budget"); // 코드가 지키는 요청 형식 플래그 (README 참고)
    private static final String FALLBACK_JSON = """
            [{"id":"claude-sonnet-5","provider":"anthropic","label":"Claude Sonnet 5","kind":"chat",
              "tier":"balanced","status":"active","capabilities":["text","vision","tools"],
              "requires":["no_sampling_params","no_thinking_budget"]}]""";
    // ────────────────────────────────────────────────────────────

    private static final Map<String, Integer> STATUS_ORDER = Map.of("active", 0, "legacy", 1, "deprecated", 2, "preview", 3);
    private static final Map<String, Integer> TIER_ORDER = Map.of("best", 0, "balanced", 1, "fast", 2);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(TIMEOUT).build();

    private record Cache(Registry registry, long at) {}
    private volatile Cache cache;   // 조회 중 잠금을 잡지 않는다 — 느린 조회가 캐시 읽기를 막지 않게

    public Loaded loadRegistry() {
        Cache c = cache;
        if (c != null && System.currentTimeMillis() - c.at() < TTL_MS) return new Loaded(c.registry(), "cache");
        try {
            Registry reg = fetch();
            cache = new Cache(reg, System.currentTimeMillis());
            return new Loaded(reg, "registry");
        } catch (Exception e) {   // 네트워크·형식 오류 모두 화면을 막지 않는다
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            c = cache;
            return c != null ? new Loaded(c.registry(), "cache")
                    : new Loaded(new Registry(fallback(), MissingNode.getInstance()), "fallback");
        }
    }

    /** 예전 예제와의 호환. 새 코드는 loadRegistry() 를 쓴다. */
    public Loaded loadModels() { return loadRegistry(); }

    public record Options(List<Option> options, String source) {}

    public static List<Option> buildOptions(List<JsonNode> models, Set<String> allowed, Set<String> supports,
                                            Set<String> requiredCaps) {
        List<Option> options = new ArrayList<>();
        for (JsonNode m : models) {
            if (!"chat".equals(m.path("kind").asText())
                    || !allowed.contains(m.path("provider").asText())
                    || "retired".equals(m.path("status").asText())
                    || m.hasNonNull("alias_of")
                    || !texts(m.path("capabilities")).containsAll(requiredCaps)) continue;
            boolean ok = supports.containsAll(texts(m.path("requires")));
            options.add(new Option(m, ok, ok ? null : "코드 업데이트 필요"));
        }
        options.sort(Comparator
                .comparingInt((Option o) -> STATUS_ORDER.getOrDefault(o.model().path("status").asText(), 9))
                .thenComparingInt(o -> TIER_ORDER.getOrDefault(o.model().path("tier").asText(), 9))
                .thenComparing(o -> o.model().path("label").asText()));
        return options;
    }

    public Options modelOptions(Set<String> requiredCaps) {
        Loaded loaded = loadRegistry();
        return new Options(buildOptions(loaded.registry().models(), ALLOWED_PROVIDERS, SUPPORTS, requiredCaps), loaded.source());
    }

    /** onDate(KST, YYYY-MM-DD) 에 적용되는 표준 단가. 모르면 empty → 서비스는 내장표 → 비싼 기본값. */
    public static Optional<Price> priceFor(List<JsonNode> models, String modelId, String onDate) {
        Map<String, JsonNode> byId = new HashMap<>();
        for (JsonNode m : models) byId.putIfAbsent(m.path("id").asText(), m);
        JsonNode m = byId.get(modelId);
        if (m != null && m.hasNonNull("alias_of")) {
            m = byId.get(m.path("alias_of").asText());
            if (m != null && m.hasNonNull("alias_of")) m = null;   // 다단계 별칭은 믿지 않는다
        }
        if (m == null) return Optional.empty();
        JsonNode best = null;
        for (JsonNode p : m.path("pricing")) {
            if (!PRICE_UNIT.equals(p.path("unit").asText()) || !p.path("from").isTextual()) continue;
            String from = p.path("from").asText();
            if (from.compareTo(onDate) <= 0 && (best == null || from.compareTo(best.path("from").asText()) > 0)) best = p;
        }
        if (best == null || !validPrice(best.path("input"))) return Optional.empty();
        JsonNode out = best.path("output");
        if (!out.isMissingNode() && !out.isNull() && !validPrice(out)) return Optional.empty();
        return Optional.of(new Price(best.path("input").asDouble(), out.isNumber() ? out.asDouble() : null));
    }

    private static boolean validPrice(JsonNode v) {
        return v.isNumber() && v.asDouble() >= 0 && v.asDouble() <= 1000;
    }

    /** 저장값이 없을 때의 기본 모델. 권장값 → 같은 tier 의 active(목록 순서) → builtin, 모두 같은 검사. */
    public static Optional<String> pickDefault(List<JsonNode> models, JsonNode recommended, String provider,
                                               List<Option> options, String tier, String builtin) {
        Set<String> usable = new HashSet<>();
        for (Option o : options) {
            String st = o.model().path("status").asText();
            if (o.selectable() && ("active".equals(st) || "legacy".equals(st))) usable.add(o.id());
        }
        List<String> candidates = new ArrayList<>();
        JsonNode rec = recommended.path(provider).path(tier);
        if (rec.isTextual()) candidates.add(rec.asText());
        for (JsonNode m : models)
            if (provider.equals(m.path("provider").asText()) && tier.equals(m.path("tier").asText())
                    && "active".equals(m.path("status").asText()) && !m.hasNonNull("alias_of"))
                candidates.add(m.path("id").asText());
        if (builtin != null) candidates.add(builtin);
        return candidates.stream().filter(usable::contains).findFirst();
    }

    /** 현재 저장값 설명. 비어 있으면 화면에 '목록에 없음' 표시(값은 그대로 유지). */
    public Optional<JsonNode> describe(String modelId) {
        return loadRegistry().registry().models().stream().filter(m -> modelId.equals(m.path("id").asText())).findFirst();
    }

    private Registry fetch() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(URI.create(REGISTRY_URL)).timeout(TIMEOUT).GET().build();
        // get(timeout) 으로 본문 수신까지 포함한 전체 시간을 자른다.
        HttpResponse<String> res = HTTP.sendAsync(req, HttpResponse.BodyHandlers.ofString())
                .get(TIMEOUT.toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
        if (res.statusCode() != 200) throw new IllegalStateException("HTTP " + res.statusCode());
        return parse(MAPPER.readTree(res.body()));
    }

    private static List<JsonNode> fallback() {
        try {
            return StreamSupport.stream(MAPPER.readTree(FALLBACK_JSON).spliterator(), false).toList();
        } catch (Exception e) {
            return List.of();
        }
    }

    private static Set<String> texts(JsonNode arr) {
        return StreamSupport.stream(arr.spliterator(), false).map(JsonNode::asText)
                .collect(java.util.stream.Collectors.toSet());
    }

    public static void main(String[] args) {
        Options result = new RegistryClient().modelOptions(Set.of("text"));
        System.out.println("source=" + result.source());
        for (Option o : result.options())
            System.out.println((o.selectable() ? "  " : "x ") + o.id() + " " + (o.reason() == null ? "" : o.reason()));
        Registry reg = new RegistryClient().loadRegistry().registry();
        System.out.println("price claude-sonnet-5: " + priceFor(reg.models(), "claude-sonnet-5", todayKst()));
    }
}
