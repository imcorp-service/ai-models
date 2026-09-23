// ai-models 목록 조회 예제 (Java 17+, Jackson databind). 기준: ai-models schema_version 1.
// 서비스 레포에 복사해 패키지를 붙여 쓰고, 복사한 뒤에는 서비스 코드로 관리한다.
// 서버에서 조회(브라우저 X), 3초 제한, 1시간 캐시, 실패 시 마지막 캐시 → FALLBACK_MODELS.

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
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
    public record Loaded(List<JsonNode> models, String source) {}   // source: registry | cache | fallback

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

    private record Cache(List<JsonNode> models, long at) {}
    private volatile Cache cache;   // 조회 중 잠금을 잡지 않는다 — 느린 조회가 캐시 읽기를 막지 않게

    public Loaded loadModels() {
        Cache c = cache;
        if (c != null && System.currentTimeMillis() - c.at() < TTL_MS) return new Loaded(c.models(), "cache");
        try {
            List<JsonNode> models = fetch();
            cache = new Cache(models, System.currentTimeMillis());
            return new Loaded(models, "registry");
        } catch (Exception e) {   // 네트워크·형식 오류 모두 화면을 막지 않는다
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            c = cache;
            return c != null ? new Loaded(c.models(), "cache") : new Loaded(fallback(), "fallback");
        }
    }

    public record Options(List<Option> options, String source) {}

    public Options modelOptions(Set<String> requiredCaps) {
        Loaded loaded = loadModels();
        List<Option> options = new ArrayList<>();
        for (JsonNode m : loaded.models()) {
            if (!"chat".equals(m.path("kind").asText())
                    || !ALLOWED_PROVIDERS.contains(m.path("provider").asText())
                    || "retired".equals(m.path("status").asText())
                    || m.hasNonNull("alias_of")
                    || !texts(m.path("capabilities")).containsAll(requiredCaps)) continue;
            boolean ok = SUPPORTS.containsAll(texts(m.path("requires")));
            options.add(new Option(m, ok, ok ? null : "코드 업데이트 필요"));
        }
        options.sort(Comparator
                .comparingInt((Option o) -> STATUS_ORDER.getOrDefault(o.model().path("status").asText(), 9))
                .thenComparingInt(o -> TIER_ORDER.getOrDefault(o.model().path("tier").asText(), 9))
                .thenComparing(o -> o.model().path("label").asText()));
        return new Options(options, loaded.source());
    }

    /** 현재 저장값 설명. 비어 있으면 화면에 '목록에 없음' 표시(값은 그대로 유지). */
    public Optional<JsonNode> describe(String modelId) {
        return loadModels().models().stream().filter(m -> modelId.equals(m.path("id").asText())).findFirst();
    }

    private List<JsonNode> fetch() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(URI.create(REGISTRY_URL)).timeout(TIMEOUT).GET().build();
        // get(timeout) 으로 본문 수신까지 포함한 전체 시간을 자른다.
        HttpResponse<String> res = HTTP.sendAsync(req, HttpResponse.BodyHandlers.ofString())
                .get(TIMEOUT.toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
        if (res.statusCode() != 200) throw new IllegalStateException("HTTP " + res.statusCode());
        JsonNode root = MAPPER.readTree(res.body());
        if (root.path("schema_version").asInt() != 1 || !root.path("models").isArray())
            throw new IllegalStateException("unsupported registry format");
        List<JsonNode> models = StreamSupport.stream(root.path("models").spliterator(), false).toList();
        for (JsonNode m : models)
            for (String k : List.of("id", "provider", "label", "kind", "status"))
                if (!m.path(k).isTextual()) throw new IllegalStateException("unsupported registry format");
        return models;
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
    }
}
