// 적합성 케이스(conformance/cases.json)를 Java 예제로 실행한다. 실패가 있으면 종료 코드 1.
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class Conformance {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode doc = mapper.readTree(Files.readString(Path.of(args.length > 0 ? args[0] : "conformance/cases.json")));
        JsonNode registry = doc.path("registry");
        RegistryClient.Registry reg = RegistryClient.parse(registry);
        List<String> failures = new ArrayList<>();
        for (JsonNode c : doc.path("cases")) {
            String name = c.path("name").asText();
            switch (c.path("op").asText()) {
                case "parse" -> {
                    ObjectNode patched = registry.deepCopy();
                    c.path("patch").fields().forEachRemaining(e -> patched.set(e.getKey(), e.getValue()));
                    String got;
                    try { RegistryClient.parse(patched); got = "ok"; } catch (IllegalStateException e) { got = "error"; }
                    check(failures, name, got, c.path("expect").asText());
                }
                case "options" -> {
                    List<RegistryClient.Option> opts = RegistryClient.buildOptions(reg.models(),
                            set(c.path("allowed")), set(c.path("supports")), set(c.path("required_caps")));
                    List<String> got = new ArrayList<>();
                    for (RegistryClient.Option o : opts) got.add(o.id() + "|" + o.selectable() + "|" + o.reason());
                    List<String> want = new ArrayList<>();
                    for (JsonNode e : c.path("expect"))
                        want.add(e.path("id").asText() + "|" + e.path("selectable").asBoolean() + "|"
                                + (e.path("reason").isNull() ? "null" : e.path("reason").asText()));
                    check(failures, name, got.toString(), want.toString());
                }
                case "price" -> {
                    Optional<RegistryClient.Price> p = RegistryClient.priceFor(reg.models(), c.path("id").asText(), c.path("on").asText());
                    JsonNode e = c.path("expect");
                    boolean ok = e.isNull() ? p.isEmpty()
                            : p.isPresent() && Math.abs(p.get().input() - e.path("input").asDouble()) < 1e-9
                              && (e.path("output").isNull() ? p.get().output() == null
                                  : p.get().output() != null && Math.abs(p.get().output() - e.path("output").asDouble()) < 1e-9);
                    check(failures, name, ok ? "match" : String.valueOf(p), "match");
                }
                case "default" -> {
                    List<RegistryClient.Option> opts = RegistryClient.buildOptions(reg.models(),
                            set(c.path("allowed")), set(c.path("supports")), Set.of("text"));
                    Optional<String> d = RegistryClient.pickDefault(reg.models(), reg.recommended(), c.path("provider").asText(),
                            opts, c.path("tier").asText(), c.path("builtin").isTextual() ? c.path("builtin").asText() : null);
                    check(failures, name, d.orElse("null"), c.path("expect").isNull() ? "null" : c.path("expect").asText());
                }
                default -> failures.add(name + ": 모르는 op");
            }
        }
        failures.forEach(f -> System.out.println("FAIL " + f));
        System.out.println(failures.isEmpty() ? "OK" : failures.size() + "건 실패");
        System.exit(failures.isEmpty() ? 0 : 1);
    }

    // 호출하지 않는다 — 예전 예제의 공개 API(loadModels().models())가 계속 컴파일되는지 확인하는 용도.
    @SuppressWarnings("unused")
    private static List<JsonNode> legacyApiStillCompiles(RegistryClient client) {
        return client.loadModels().models();
    }

    private static void check(List<String> failures, String name, String got, String want) {
        if (!got.equals(want)) failures.add(name + ": got=" + got + " want=" + want);
    }

    private static Set<String> set(JsonNode arr) {
        Set<String> s = new HashSet<>();
        arr.forEach(x -> s.add(x.asText()));
        return s;
    }
}
