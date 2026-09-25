# ai-models

AI 모델 목록 공용 저장소입니다. 서비스 관리 화면이 이 목록을 불러와 **모델 선택지**로 보여주고, 모델이 은퇴하거나 새로 나오면 이 저장소의 목록 한 곳만 고칩니다. 서비스는 다시 배포하지 않아도 다음 조회 때 바뀐 선택지를 받습니다.

- 목록: [`ai-models.json`](ai-models.json)
- 게시 주소: `https://raw.githubusercontent.com/imcorp-service/ai-models/main/ai-models.json`
- 형식: [`schema.json`](schema.json) (JSON Schema 2020-12), `schema_version: 1`

> 이 목록은 편의를 위한 참고 자료입니다. 각 제공사의 공식 문서와 다를 수 있으니, 실제 적용 전에는 서비스에서 **실제 호출로 검증**해야 합니다(아래 "서비스에서 쓰는 법" 4번).

## 무엇이 들어 있나

모델마다 다음 정보를 담습니다.

| 필드 | 뜻 |
|---|---|
| `id` | 제공사 API에 넣는 모델 ID 그대로 |
| `provider` | `anthropic` · `openai` · `gemini` |
| `kind` | `chat` (대화·생성) · `embedding` (임베딩) |
| `status` | `active` 권장 · `legacy` 동작하지만 교체 권장 · `deprecated` 종료일 공지됨 · `preview` 프리뷰 · `retired` 호출 불가 |
| `tier` | `fast` · `balanced` · `best` (속도·비용 대 성능 구분) |
| `capabilities` | `text` · `vision` · `tools` |
| `requires` | 이 모델을 쓰려면 호출 코드가 지켜야 하는 요청 형식 (아래 표) |
| `retire_not_before` | 제공사가 약속한 "이 날짜 전에는 은퇴하지 않음" |
| `retire_on` | 공지된 종료 예정일 (`deprecated`) |
| `retired_on` | 실제 종료일 (`retired`) |
| `replace_with` | 교체 권장 모델 (같은 제공사) |
| `alias_of` | 같은 모델의 다른 이름 (예: 날짜 붙은 스냅샷 ID). 선택지에는 대표 ID만 보여줍니다 |
| `dimensions` | 임베딩 차원 (`embedding`만) |
| `note` | 접근 제한 등 참고 사항 |

`retired` 항목은 선택지에 쓰지 않습니다. 이미 저장된 값이 은퇴했는지 알려주고 교체 대상을 안내하는 용도로 남겨 둡니다.

### 요청 형식 플래그 (`requires`)

모델을 바꿀 때 **ID만 바꾸면 안 되고 호출 코드도 달라져야 하는 경우**를 플래그로 표시합니다. 서비스는 자기 코드가 지키는 플래그를 `SUPPORTS`로 선언하고, 모델의 `requires`가 모두 `SUPPORTS`에 들어 있을 때만 선택할 수 있습니다. 해당 파라미터를 **아예 보내지 않는 코드**라면 그 플래그를 지원하는 것입니다.

| 플래그 | 뜻 |
|---|---|
| `no_sampling_params` | `temperature` · `top_p` · `top_k`를 기본값 외로 보내면 오류(400) |
| `no_thinking_budget` | `thinking.budget_tokens`를 보내면 오류 |
| `no_forced_tool_choice` | `tool_choice`의 `any` · `tool` 강제 지정 불가 |
| `thinking_always_on` | `thinking: {type: "disabled"}`를 보내면 오류 |
| `max_completion_tokens` | `max_tokens` 대신 `max_completion_tokens`를 써야 함 |

예: 어떤 서비스가 `temperature: 0.7`을 보낸다면 `no_sampling_params`를 지원하지 않으므로, 이 플래그가 필요한 최신 모델은 "코드 업데이트 필요"로 표시되고 선택할 수 없습니다.

## 서비스에서 쓰는 법

[`examples/`](examples)에 Python · Java · TypeScript 예제가 있습니다. 서비스 저장소에 복사해 쓰고, 복사한 뒤에는 그 서비스의 코드로 관리합니다.

새 서비스에 적용할 때의 체크리스트와 실제 적용에서 드러난 함정은 [`docs/INTEGRATION.md`](docs/INTEGRATION.md)에 있습니다.

1. **서버에서 조회합니다.** 브라우저가 직접 가져가지 않습니다. 타임아웃 3초, 결과는 1시간 캐시합니다.
2. **실패해도 화면을 막지 않습니다.** 조회 실패 → 마지막 캐시 → 서비스에 내장한 최소 목록 순서로 씁니다. 어느 출처를 썼는지(`registry` · `cache` · `fallback`)를 함께 표시합니다. 조회 주소는 환경변수 `AI_MODELS_URL`로 바꿀 수 있습니다(폐쇄망 등).
3. **걸러서 보여줍니다.** `kind == "chat"`, 서비스가 허용한 제공사, `retired` 아님, `alias_of` 없음, 필요한 `capabilities` 보유. `requires`가 맞지 않는 모델은 숨기지 않고 "코드 업데이트 필요"로 비활성 표시합니다.
4. **저장 전에 실제로 호출해 검증합니다.** 서비스가 실제로 쓰는 호출 함수로 짧은 요청을 1회 보내 성공해야 저장합니다. 목록은 선택지를 줄 뿐, 동작을 보장하지 않습니다. 유일한 예외는 제공사 일시 장애(429·5xx·타임아웃)이며, 조건은 [`docs/INTEGRATION.md`](docs/INTEGRATION.md) §3에 있습니다.
5. **현재 저장값은 목록에 없어도 그대로 보여줍니다.** "목록에 없음" 또는 "은퇴됨 — 교체 권장: …"으로 표시하고, 다른 설정을 저장할 때 모델 값이 바뀌지 않게 합니다.
6. **임베딩 모델은 선택지로 쓰지 않습니다.** 차원이 다른 모델로 바꾸면 기존 벡터 데이터와 맞지 않습니다. 임베딩 교체는 재색인과 함께 따로 진행합니다.

반영 시간: 이 저장소에 머지된 뒤 GitHub raw 캐시(최대 약 5분) + 서비스 캐시(1시간) 안에 반영됩니다.

## 목록을 고치는 법

1. `ai-models.json`을 수정하는 PR을 엽니다. 새 모델 추가, `status` · 날짜 · `replace_with` 갱신, 필요한 `requires` 플래그를 적습니다.
2. CI(`scripts/validate.py`)가 스키마와 규칙을 검사합니다: ID 중복, 존재하지 않는 형태의 ID, `replace_with` · `alias_of`가 목록에 있고 같은 제공사인지, 은퇴 모델에 날짜와 교체 대상이 있는지.
3. 리뷰 후 `main`에 머지합니다.

`main`은 보호되어 있습니다: 직접 푸시·강제 푸시·삭제 불가, PR과 CI(`validate`) 통과 필수, 스쿼시 머지만 허용. 외부 기여자의 PR은 관리자가 승인해야 CI가 실행됩니다.

로컬 검사:

```bash
pip install "jsonschema==4.24.0"
python scripts/validate.py
python -m unittest discover -s tests -q
```

새로운 요청 형식 차이가 생기면 플래그를 `schema.json`, `scripts/validate.py`의 검사, 이 README 표에 함께 추가합니다.

## 출처

목록은 각 제공사의 공식 문서를 기준으로 사람이 갱신합니다.

- Anthropic: [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) · [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- OpenAI: [Deprecations](https://developers.openai.com/api/docs/deprecations)
- Google: [Gemini models](https://ai.google.dev/gemini-api/docs/models) · [Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
