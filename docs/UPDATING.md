# 목록 정기 갱신 절차

새 모델 출시는 자동으로 감지되지 않습니다. 정기 점검은 날짜(은퇴일·단가 확인일)만 봅니다. 그래서 **월 1회 사람이 제공사 공식 문서와 목록을 대조**합니다. 이 문서는 그 작업을 누가 해도, 에이전트에게 맡겨도 같은 결과가 나오게 하는 절차입니다.

## 언제 하나

| 계기 | 할 일 |
|---|---|
| 정기 점검 이슈에 **"월간 갱신 시점"**이 뜸(`updated` 후 30일) | 이 문서 전체 절차 |
| 점검 이슈에 **"은퇴일 지남"·"은퇴 임박"** | 해당 모델만 2·3단계로 상태 갱신. 이때는 `updated` 를 올리지 않습니다(월간 알림이 전체 대조 시점을 놓치지 않게). 전체 대조를 같이 했으면 올립니다. |
| 제공사의 새 모델 발표·지원 종료 메일 | 다음 월간 갱신을 기다리지 말고 바로 전체 절차 |

정기 점검 이슈(라벨 `audit`)는 매주 월요일에 갱신되고, 확인할 항목이 없어지면 자동으로 닫힙니다. 이슈 담당자는 저장소 변수 `AUDIT_ASSIGNEE` 입니다.

## 1. 공식 출처 — 이 페이지들만 근거로 쓴다

| 제공사 | 모델 목록 | 단가 | 지원 종료 | 모델별 기능·요청 형식 |
|---|---|---|---|---|
| Anthropic | [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) | [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) | [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) (아래 "API parameter deprecations" 표 포함) | [Migration guide](https://platform.claude.com/docs/en/about-claude/models/migration-guide) |
| OpenAI | [Models](https://developers.openai.com/api/docs/models) | [Pricing](https://developers.openai.com/api/docs/pricing) | [Deprecations](https://developers.openai.com/api/docs/deprecations) | `https://developers.openai.com/api/docs/models/<모델 ID>`, [Latest model guide](https://developers.openai.com/api/docs/guides/latest-model) |
| Gemini | [Models](https://aistudio.google.com/docs/models) | [Pricing](https://aistudio.google.com/docs/pricing) | [Deprecations](https://aistudio.google.com/docs/deprecations) | `https://aistudio.google.com/docs/models/<모델 ID>`, [Thinking](https://aistudio.google.com/docs/thinking) |

- Gemini 문서는 2026-11 기준 `ai.google.dev/gemini-api/docs/*` 에서 `aistudio.google.com/docs/*` 로 옮겨졌습니다(301). 기존 항목의 `source` 는 그대로 두고, 새로 적는 단가에만 새 주소를 씁니다.
- 블로그·뉴스·기억에 의존하지 않습니다. 주소가 바뀌었으면 이 표를 고칩니다.

## 2. 대조 — 제공사마다 아래 6가지

상태가 겹치면 **`retired` > `deprecated` > `legacy`** 순으로 정합니다. 종료일이 공지된 모델은 후속 모델이 있어도 `deprecated` 입니다(종료 임박 알림이 빠지지 않게).

1. **새 모델**: 제공사 목록의 현행 모델 중 `ai-models.json` 에 없는 것 → 추가.
2. **지원 종료 공지**: 종료일이 공지된 모델 → `deprecated` + `retire_on` + `replace_with`.
3. **종료일 지남**: `retire_on` 이 지났거나 제공사 표에 Retired → `retired` + `retired_on` + `replace_with`. `retire_on`·`retire_not_before`·`tier`·`capabilities`·`requires` 는 뺍니다. **`pricing`·`pricing_verified` 는 남깁니다** — 서비스가 과거 사용량을 그 시점 단가로 다시 계산합니다([INTEGRATION.md](INTEGRATION.md) §6).
4. **후속 모델 생김**: 종료 공지가 없는 모델 중 같은 계열의 새 버전이 나온 것 → 제공사가 여전히 Active 라도 `legacy` + `replace_with`(새 버전).
5. **단가**: 값이 같으면 `pricing_verified` 만 대조일로. 바뀌었거나 예정 변경이 공지됐으면 새 `from` 항목을 추가합니다. **이미 발효된 항목(`from` ≤ 오늘)은 고치지 않습니다.** 아직 발효 전인 예정 항목은 제공사가 정정·취소했으면 고치거나 지울 수 있고, 새 변경의 발효일이 기존 예정 항목보다 이르면 날짜 순서에 맞게 끼워 넣습니다(`from` 오름차순, 같은 날 두 번 금지 — `validate.py` 가 검사).
6. **권장값(`recommended`)**: 제공사가 안내하는 현행 fast / balanced / best 로. 권장값은 반드시 `active` 모델.

추가하는 모델은 모델별 페이지에서 **이미지 입력·도구(함수) 호출·요청 형식 제약**(샘플링 파라미터, thinking/추론 끄기, 강제 도구 호출, `max_tokens` 이름, 도구 호출에 필요한 API)을 확인합니다.

## 3. 판단 기준

| 상황 | 기준 |
|---|---|
| 목록 순서 | 같은 제공사·같은 등급 안에서 **위에 있을수록 우선**. 새 현행 모델은 그 등급의 기존 항목보다 앞에 둡니다. |
| `replace_with` | 제공사가 권장한 교체 대상. 그 대상이 목록에 없거나 구세대면 **같은 등급의 현행 모델**로 하고 PR 에 적습니다. retired·별칭은 가리킬 수 없습니다. |
| 넣지 않는 것 | 이미 구세대가 된 처음 보는 ID, 검증된 조직 전용 모델(예: Claude Mythos), 별도 절차가 필요한 임베딩 교체. PR 에 "넣지 않은 것"으로 적습니다. |
| 문서로 확인 안 되는 기능 | `capabilities` 에 넣지 않습니다(확인된 것만). |
| 문서로 확인 안 되는 제약 | 의심되면 `requires` 에 **붙입니다**(서비스가 고르지 못하는 쪽이 안전). note 에 "문서에 없어 보수적으로 표시"라고 적습니다. |
| 스키마에 칸이 없는 정보 | 장문맥 구간 단가, 자동 연결(라우팅), 일부 조건의 예외 등은 `note` 에 한국어 한 문장으로. |
| 새 요청 형식 차이 | 기존 플래그의 **의미를 바꾸지 않습니다**([COMPATIBILITY.md](COMPATIBILITY.md)). 새 플래그를 `schema.json` enum 끝에 추가하고 README 표·[INTEGRATION.md](INTEGRATION.md)·테스트를 함께 고칩니다. **기존 모델에 새 플래그를 붙이면 그 플래그를 모르는 모든 서비스에서 그 모델이 선택 불가가 됩니다** — 영향이 크면 데이터 대신 문서(선언 기준)로 안내하는 방법을 검토합니다. |

## 4. 조사 결과 검증 — 실제로 있었던 함정

- **요약·하위 에이전트의 결과는 핵심 사실(상태·종료일·교체 대상·단가)을 원문 표에서 한 번 더 확인합니다.** 2026-11 갱신 때 첫 조사에서 두 가지가 틀렸습니다.
  - `gemini-3.7-flash` 를 "은퇴"로 보고했는데, 원문은 "종료하지 않고 `gemini-3.8-flash` 로 자동 연결"이었습니다.
  - 기존 목록의 `gpt-5.4` 지원 종료(2026-10-01)는 실제로는 `gpt-5.4-cyber` 의 것이었습니다.
- 긴 페이지는 도구가 뒷부분을 잘라 요약할 수 있습니다. 필요한 행은 원문으로 확인합니다.
- 단가표의 각주(임시 가격·예정 인상·프로모션)를 읽습니다. 예: Sonnet 5 의 임시 가격이 정식 가격이 됨, Gemini 4 Carbon 의 12-01 인상.
- 같은 제공사 문서끼리 말이 다를 수 있습니다(예: 모델 페이지 vs 마이그레이션 가이드). 더 구체적인 쪽을 따르고, 남는 차이는 PR 에 적습니다.
- 확인한 날짜를 `pricing_verified`·`updated`·PR 본문에 적습니다. 문서를 편집만 하고 대조하지 않았으면 날짜를 올리지 않습니다.

## 5. 수정·검증

```bash
git switch -c feat/models-YYYY-MM
# ai-models.json 수정 (기존 서식: 한 모델 묶음·키 순서 유지). updated 는 세 제공사 전체 대조를 마쳤을 때만 대조일로
python scripts/validate.py
python -m unittest discover -s tests -q
python scripts/audit.py   # 남는 항목은 "은퇴 임박" 같은 정상 알림뿐이어야 함
```

- 테스트 중에는 현재 목록의 특정 모델을 예시로 쓰는 것이 있습니다(예: 권장값 예시). 상태를 바꾼 모델이 걸리면 테스트의 예시를 현행 모델로 바꿉니다 — 검사 자체를 약하게 만들지 않습니다.
- `examples/` 의 내장 기본 목록(FALLBACK)이 `legacy`·`retired` 가 된 모델이면 현행 모델로 바꿉니다(예제의 `SUPPORTS` 로 선택 가능한 모델).
- Java 적합성은 PR CI 가 실행합니다.

## 6. 리뷰·PR·머지

1. 수정한 에이전트와 **다른 에이전트**가 diff 를 리뷰합니다(사내 공통 규칙의 교차 리뷰). 리뷰어에게는 명세(대조 결과)와 diff, 검증 결과를 줍니다.
2. PR 본문 양식: **요약 표**(추가 모델·권장값) / **상태 변경** / **확인하지 못해 보수적으로 둔 것** / **넣지 않은 것** / **검증·리뷰 결과**.
3. 브랜치 푸시만으로는 워크플로가 돌지 않습니다. PR 을 열면 `validate` 와 `conformance-java` 가 돕니다. 둘 다 통과한 뒤 스쿼시 머지합니다.
4. 머지 후 `main` 의 `validate` 통과를 확인하고, 점검 이슈가 다음 정기 점검에서 닫히는지 봅니다(바로 보려면 Actions 에서 `audit` 를 수동 실행).
5. **서비스 영향 알림**: 권장값이 바뀌면 이 목록을 쓰는 서비스의 기본 모델이 바뀝니다. 지원 종료 임박 모델을 쓰는 서비스가 있으면 담당자에게 교체 일정을 알립니다.

## 7. 에이전트에게 맡길 때 지시문

아래를 그대로 주면 1~6단계를 한 번에 진행합니다. 머지는 사람이 지시합니다.

```text
imcorp-service/ai-models 의 docs/UPDATING.md 절차대로 이번 달 목록 갱신을 해 줘.
- 1단계 표의 공식 페이지만 근거로, Anthropic·OpenAI·Gemini 세 제공사 모두 2단계 6가지를 대조한다.
- 조사 결과의 상태·종료일·교체 대상·단가는 원문 표에서 다시 확인한다(4단계).
- 3단계 기준으로 ai-models.json 을 고치고 5단계 검증을 모두 돌린다.
- 수정과 다른 에이전트에게 교차 리뷰를 받고, 6단계 양식으로 PR 을 연다. 머지는 하지 않는다.
- 문서로 확인되지 않은 것은 추측하지 말고 보수적으로 표시한 뒤 PR 에 적는다.
```

## 기록

갱신 이력은 PR 과 `git log -- ai-models.json` 에 남습니다. 별도 작업 일지는 만들지 않습니다.
