# W5 검토 UI와 등록 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. 헬퍼가 스크래치 사본에서 검증한 코드를 작업 트리에 **직접 적용**하고 새 개념·설계 이유를 설명한다(메모리 `education-mode-full-code`). 사용자는 설치(네트워크), 서버·LLM 실행, 화면 확인을 한다. 이 문서는 작업 단위의 인터페이스·테스트·DoD를 고정한다. 코드는 실행 시점에 검증 후 적용한다. 서브에이전트 실행은 사용자가 요청할 때만. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 담당자가 브라우저에서 사양서를 올리고, 원문 하이라이트를 보며 값을 고치고, 중복·유사 판정에 따라 "기존 레코드에 연결 / 별도 등록 / 취소"를 고르면, 등록 DB 레코드·표준 JSON·수정 이력·감사 기록이 남는다(계획서 S1·S2, W5 DoD).

**Architecture:** W4의 `process_document` 단계를 LangGraph 노드로 나눈 **등록 그래프**를 만든다. 사람이 판단할 지점(클래스 unknown, 검토·등록 확정)은 `interrupt()`로 멈추고 상태는 SqliteSaver 체크포인트에 남긴다. 담당자 수정은 LLM 없이 결정론 재검증·재판정 루프를 돈다. 등록 노드는 멱등 키를 가진 단일 트랜잭션으로 `products`·`product_facts`·`human_edits`·`registration_events`에 쓴다. FastAPI가 작업(job) API를 제공하고, **React·TypeScript·Vite** 단일 페이지 앱(결정 1, D-061)이 같은 출처에서 그 API를 쓴다.

**Tech Stack:** 기존 Python 스택 + **langgraph, langgraph-checkpoint-sqlite**. 프런트엔드(결정 1): Vite + React + TypeScript, TanStack Query, openapi-typescript + openapi-fetch, react-pdf(pdf.js), Tailwind CSS, Biome, Vitest + React Testing Library + MSW. 버전은 설치 시점에 레지스트리에서 확인하고 lock 파일로 고정한다(기억으로 정하지 않음).

**Spec:** [계획서](../../spec-bridge-project-plan.md) S1·S2·S3, FR-12, NFR-01·02·05·07, 5-2 구성요소(노드)·등록 모드, W5 표. [W4 보고서](../../reports/w4-validation-dedup.md), decisions.md D-054~D-059.

## Global Constraints

- **로컬 우선(NFR-01)**: 서버는 `127.0.0.1`만 바인딩한다. 프런트엔드는 빌드 결과를 FastAPI가 같은 출처로 서빙한다(CORS 불필요). 실행 시 CDN·외부 폰트·원격 스크립트를 쓰지 않는다. npm 설치에만 네트워크를 쓰고, 설치는 사용자 터미널에서 한다.
- **자동 병합 금지(S2)**: 기존 레코드의 사실을 새 문서 값으로 바꾸지 않는다. "연결"은 사건(event) 기록만 남긴다.
- **근거 추적(NFR-07)**: 등록되는 모든 사실은 `observed`(원문 위치) 또는 `human_edit`(수정 기록 ID)를 근거로 가진다. 근거 없는 값은 등록하지 않는다.
- **감사(NFR-02)**: 사람의 결정·수정과 등록은 SQLite에 남긴다. LLM 호출 감사의 저장 위치는 결정 4를 따른다.
- **채점기 ID `2d5f9c663da8` 유지**: 해시 대상 모듈(scoring, locations, validation_scoring, validator, findings, dedup_scoring, matcher)은 고치지 않는다. 고쳐야 하면 새 ID를 기록하고 재채점한다(D-036).
- **평가 경로와 분리**: 앱은 작업 DB `var/app/registry.sqlite`(개발 seed로 초기화)를 쓴다. `data/synth/registry/*.jsonl`과 평가 실행은 바뀌지 않는다. 테스트 분할 문서는 앱에 올리지 않는다(D-020).
- **H3**: 화면 문구·검증 메시지에 장비 수치·규제 해석을 새로 쓰지 않는다. 온톨로지·Finding이 가진 문구만 표시한다.
- 완료 판정: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy spec_bridge tests`, 그리고 `npm --prefix web run check`, `npm --prefix web run build`. 커밋·푸시는 사용자 요청 시에만.

## Review Focus

1. **등록 버튼을 두 번 누르거나, 응답 전에 재시도할 때**: 제품은 하나만 생기고, 두 번째 요청은 같은 결과를 돌려준다 → Task 3(멱등 키)·Task 4(`request_id`) 테스트.
2. **검토 대기 중 서버를 재시작할 때**: 같은 작업을 다시 열면 같은 검토 화면에서 이어지고, LLM 노드가 다시 돌지 않는다 → Task 2 테스트(새 그래프 인스턴스 + 같은 체크포인트 DB, 가짜 제공자의 호출 수 0).
3. **duplicate에서 "별도 등록"을 고를 때**: 식별(제조사·모델 키)이 같으면 DB 유일 제약과 충돌한다. 500이 아니라 거부 사유를 보여 주고, 식별 값을 고치면(사람 수정) 다시 판정한다 → Task 3·4 테스트.
4. **담당자가 단위가 틀린 값이나 허용 목록 밖 값을 입력할 때**: 예외가 아니라 재검증 Finding으로 표시되고 등록이 막힌다 → Task 2 테스트.
5. **DOCX·XLSX(좌표 없음)와 PDF(좌표 있음)**: PDF는 페이지 위 상자로, 나머지는 블록 목록의 해당 행으로 하이라이트한다. 좌표 원점 변환(PDF 좌하단 → 화면 좌상단)이 틀리면 상자가 뒤집힌다 → Task 6 테스트.

---

## 결정 1 (승인됨, D-061): 검토 UI 스택 — Streamlit → React·TypeScript·Vite

### 평가

| 기준 | Streamlit (계획서 원안) | React·TS·Vite (제안) |
|---|---|---|
| 원문 하이라이트(S1 핵심) | PDF 위 상자 표시 기본 기능 없음. 어차피 커스텀 컴포넌트(= JS/React)가 필요 | react-pdf로 페이지를 그리고 상자를 겹친다. 좌표 변환만 직접 작성 |
| HITL 다단계 상태 | 위젯이 바뀔 때마다 스크립트 전체를 재실행. 대기 중 작업·수정 초안·중복 선택을 `session_state`로 직접 관리해야 함 | 서버(LangGraph 체크포인트)가 상태의 원본, 화면은 조회·전송만. 재실행 모델이 없음 |
| API 계약 | Python 함수를 직접 호출하기 쉬움(대신 API를 거치지 않는 경로가 생김) | FastAPI OpenAPI → TS 타입 자동 생성. 서버 모델이 바뀌면 `tsc`가 깨져 바로 드러남 |
| 테스트 | UI 테스트 도구가 제한적 | Vitest·RTL·MSW로 컴포넌트·흐름 테스트, `tsc`·Biome = mypy·ruff 대응 |
| 데모·포트폴리오(계획서 데모 항목) | 빠르지만 "내부 도구" 인상 | 일반 웹앱 형태 |
| 비용 | Python만, 코드 적음 | Node 도구 체인과 두 번째 언어, 코드량 증가(1주 일정 압박) |
| 로컬 우선 | 문제 없음 | 빌드 결과를 FastAPI가 서빙하면 실행 시 네트워크 0. 설치 시에만 npm 네트워크 |
| 커리큘럼 ⑥(멀티에이전트 제어) | 영향 없음 | 영향 없음. 학습 대상은 LangGraph HITL이며 UI는 수단 |

**판단:** 재구성을 권한다. S1의 핵심인 "원문 위치 하이라이트"와 S2의 "중복 처리 선택"은 Streamlit에서도 커스텀 JS가 필요하고, HITL 상태를 서버 그래프에 두는 설계와 Streamlit의 재실행 모델이 맞지 않는다. 비용(1주 안 코드량)은 다음 세 가지로 줄인다.

1. **백엔드 먼저**: Task 0~4(그래프·등록·API)를 끝내면 S1·S2를 API(curl 스크립트)로 끝까지 시연할 수 있다. UI가 늦어도 계획서 위험 대응("W5 UI는 CLI+리포트로 대체 가능")을 지킨다.
2. **화면은 3개만**: 작업 목록·업로드, 작업 검토(3분할), 등록 제품 상세(수정 이력).
3. **부가 도구는 역할이 겹치지 않게 최소로**:

| 도구 | 역할 | 대신 쓰지 않는 것과 이유 |
|---|---|---|
| Vite | 개발 서버(`/api` 프록시), 빌드 | — |
| TypeScript (strict) | 타입 검사(`tsc --noEmit`) | — |
| openapi-typescript + openapi-fetch | OpenAPI → 타입, 타입이 붙은 fetch | 손으로 쓴 타입(서버와 어긋남), axios(불필요) |
| TanStack Query | 서버 상태 캐시, 작업 상태 폴링(`refetchInterval`), 요청 후 무효화 | Redux 등 전역 상태(서버가 상태의 원본이라 불필요) |
| react-pdf (pdf.js) | PDF 페이지 렌더, 상자 겹침 | PDF를 이미지로 서버 렌더(추가 의존성) |
| Tailwind CSS | 스타일 | 컴포넌트 라이브러리 전체(화면 3개에 과함). 필요하면 나중에 추가 |
| Biome | 린트 + 포맷(ruff 대응, 도구 1개) | ESLint + Prettier(설정 2개) |
| Vitest + React Testing Library + MSW | 컴포넌트·흐름 테스트, API 모킹 | — |
| (선택) Playwright | 브라우저 E2E 1개 | 브라우저 내려받기가 필요해서 선택으로 둠 |

라우팅은 화면 3개라 라우터 없이 URL 해시 또는 상태로 처리한다. 필요해지면 그때 추가한다(YAGNI). 폼 라이브러리도 쓰지 않는다. 수정 폼은 속성 하나에 입력 칸 몇 개뿐이고, 검증은 서버(온톨로지 규칙)가 한다.

**승인되면 바뀌는 문서:** 계획서 FR-12·5-3 스택·폴더 구조(`app/`)·W5 표·데모 항목의 "Streamlit" → "React·TS·Vite(FastAPI 서빙)", 변경 이력 행, decisions.md D-061.

**거부되면:** Task 5~7을 Streamlit 3개 화면으로 바꾸고, PDF 하이라이트는 서버에서 페이지 이미지 + 상자를 그려 보여 준다(pypdfium2는 이미 의존성에 있음). Task 0~4는 그대로다.

## 결정 2 (승인됨, D-062): 그래프 구조와 중단점

```
START → parse → classify ─(unknown)→ [choose_class ⏸] ─┐
                    │ (leaf)                             │
                    └────────────→ extract ←─────────────┘
extract → qualify(E1SV) → normalize → check(validate ∥ dedup) → [review ⏸]
[review ⏸] ─ edit ──→ apply_edits → check → [review ⏸]      (결정론 루프, LLM 없음)
           ─ register_new / link ─→ register → END
           ─ cancel ─→ END
parse·classify·extract 실패 → [review ⏸] (선택지: 취소만, 사유 표시)
```

- **노드 = 계획서 5-2의 구성요소**다. W4 `process_document` 안의 단계를 함수로 꺼내 그래프와 MVP API가 같은 함수를 쓴다. 사람 개입 없이 끝까지 돌린 그래프 결과는 `process_document` 결과와 같아야 한다(Task 1 테스트).
- **중단점은 두 개**다. `choose_class`(분류 unknown)와 `review`(값 수정·중복 처리·등록 확정을 한 화면에서). S1의 "수정 → 확인 → 등록"과 S2의 "연결/별도/취소"가 같은 검토 단계의 다른 선택이기 때문이다. 중단점을 나누면 화면 전환만 늘어난다.
- **`interrupt()`가 있는 노드에는 부작용을 두지 않는다.** LangGraph는 재개 시 그 노드를 처음부터 다시 실행한다. 그래서 DB 쓰기는 `register` 노드에만 둔다. LLM 호출은 앞 노드에서 끝나고 체크포인트에 결과가 남으므로, 재개해도 다시 호출되지 않는다.
- **상태는 JSON으로 직렬화할 수 있는 값만 둔다**(dict·list·str). Pydantic 모델은 노드 경계에서 `model_dump(mode="json")`한다. 체크포인트 직렬화가 라이브러리 버전에 덜 묶이게 하기 위해서다.

## 결정 3 (승인됨, D-063): 등록 규칙(S1·S2)

| 상황 | 허용 선택 | 등록 가능 조건 |
|---|---|---|
| 판정 new | 별도 등록, 취소 | 재검증 E1~E5 Finding 0, REVIEW는 모두 "확인함" 표시 |
| 판정 similar | 별도 등록(기본), 기존 레코드에 연결, 취소 | 별도 등록은 위와 같은 조건. 연결은 대상 1개 선택 |
| 판정 duplicate | 기존 레코드에 연결, 취소. **별도 등록은 식별 값을 고친 뒤에만** | 같은 제조사·모델 키는 DB 유일 제약(`UNIQUE(maker_id, model_key)`)과 충돌한다. 식별 값을 고치면 재판정 결과를 따른다 |
| 처리 실패(파싱·분류·추출) | 취소 | — |

- **연결(link)**: 새 제품을 만들지 않는다. 대상 제품에 `registration_events(event_type='linked_document')`를 남긴다. 페이로드에는 작업 ID, 문서 해시, 값이 다른 속성 목록이 들어간다. 사실은 바꾸지 않는다(자동 병합 금지).
- **E1~E5가 남은 채로 등록하는 "강제 등록"은 두지 않는다.** 값이 문서에 없으면 담당자가 값을 입력(사람 수정, 근거 `human_edit`)하거나 취소한다. 등록 레코드에 검증 오류가 남지 않게 하기 위해서다.
- 사유 입력: 수정마다 사유(필수, 자유 문장)를 받는다. HumanEdit 정의(계획서 6장: 이전 값, 새 값, 사유, 시각)를 따른다.

## 결정 4 (승인됨, D-064): 저장 위치

- **작업 DB** `var/app/registry.sqlite`: 첫 기동 때 개발 seed(`manufacturers.json`, `dev.jsonl`)로 만든다. 등록 결과도 여기에 쌓인다. 중복 판정은 jsonl 대신 이 DB의 제품 목록으로 한다. 그래야 등록한 제품이 다음 업로드의 중복 후보가 된다(S2 시연).
- **체크포인트 DB** `var/app/checkpoints.sqlite`(LangGraph 전용, 분리).
- **업로드 원본** `var/app/uploads/<job_id><suffix>`: 원문 보기에 필요하므로 요청 뒤에도 남긴다(W4 API는 요청이 끝나면 지웠다). 로컬 `var/`이고 git 제외다.
- **감사(NFR-02)**: 작업 DB에 `audit_events(job_id, kind, actor, occurred_at, payload_json)`를 추가한다. 사람 결정·수정·등록은 여기에 기록한다. LLM 호출 감사는 기존 `AuditLog`에 SQLite 기록 대상을 더해 같은 표에 `kind='llm_call'`, `job_id`와 함께 남긴다. jsonl 기록은 실험 경로 호환을 위해 유지한다.
- **스키마 판본**: `SCHEMA_VERSION` "1" → "2". 새 표와 컬럼만 추가하는 마이그레이션이고 기존 seed는 바뀌지 않는다.

## 결정 5 (승인됨, D-060): BOM 일괄 모드(S3)는 이후 확장

W5 범위에서 뺀다. 관계 모델(`has_component`, `relations` 표)과 합성 BOM 4건은 그대로 둔다. 확장 시 출발점은 이 문서 끝 "이월 사항"에 적었다.

---

## 작업 목록

| ID | 작업 | 주체 | 승인 필요 |
|---|---|---|---|
| W5-0 | 서비스 배선 모듈 분리(`service.py`), 의존성 추가 | 헬퍼 적용 + 사용자 설치 | — |
| W5-1 | 파이프라인 단계 함수 분리 | 헬퍼 적용 | — |
| W5-2 | LangGraph 등록 그래프 + HITL + SqliteSaver | 헬퍼 적용 | 결정 2 |
| W5-3 | 등록 저장소: 등록·연결·수정·감사(멱등) | 헬퍼 적용 | 결정 3·4 |
| W5-4 | 작업 API(jobs) + OpenAPI 내보내기 + S1·S2 API 시연 스크립트 | 헬퍼 적용 + 사용자 실행 | — |
| W5-5 | 프런트엔드 골격(Vite·TS·도구·생성 타입·FastAPI 서빙) | 헬퍼 적용 + 사용자 `npm install` | **결정 1** |
| W5-6 | 검토 화면 3분할(원문 하이라이트 / 속성 편집 / 오류·중복) | 헬퍼 적용 | 결정 1 |
| W5-7 | 작업 목록·제품 상세 화면, S1·S2 UI 시연(DoD) | 헬퍼 적용 + 사용자 시연 | — |
| W5-9 | W5 보고서, 계획서·결정 기록 갱신 | 헬퍼 | — |

## 파일 구조

| 경로 | 책임 |
|---|---|
| `spec_bridge/service.py` (신규) | `make_provider`·`make_rag`·`normalizer_for`·`prompt_hashes`를 실험 실행기에서 옮겨 온 운영 배선. 실험 실행기는 여기서 import한다(해시 대상 아님) |
| `spec_bridge/pipeline.py` (수정) | 단계 함수 `parse_step`·`classify_step`·`extract_step`·`check_step` 등. `process_document`는 이 함수들의 조합으로 유지 |
| `spec_bridge/graph/state.py` | `JobState`(TypedDict), 재개 명령 모델(`ResumeCommand` 판별 유니언) |
| `spec_bridge/graph/registration.py` | `build_graph(deps, checkpointer) -> CompiledStateGraph`, 노드·간선·중단점 |
| `spec_bridge/registry/store.py` (수정) | 스키마 2: `human_edits`, `audit_events`, `jobs` 표. `register_product`·`link_document`·`records()`(중복 판정 입력) |
| `spec_bridge/registry/edits.py` | 사람 수정 적용: `apply_edits(facts, edits) -> (facts, HumanEdit 행)`, 근거 종류 전환 |
| `spec_bridge/llm/audit.py` (수정) | 선택적 SQLite 기록 대상(결정 4) |
| `spec_bridge/api/app.py` (수정) | `/api/jobs…`, `/api/products…`, 정적 파일 서빙. `/health`·`/documents` 유지 |
| `spec_bridge/api/openapi.py` | 서버 없이 `web/openapi.json` 내보내기 |
| `scripts/s1_s2_api_demo.sh` | API만으로 S1·S2 끝까지 시연 |
| `web/` | Vite 앱: `src/api/`(생성 타입·클라이언트), `src/features/jobs/`, `src/features/review/`, `src/features/products/`, `src/lib/bbox.ts` |
| `docs/reports/w5-review-ui-registration.md` | W5 결과 |

---

### Task 0 (W5-0): 서비스 배선 분리와 의존성

**목적:** API가 실험 실행기(`eval.experiment`)를 import하는 정리 대상(W4 보고서 §6)을 해소한다. 그래프와 API가 같은 배선을 쓰게 한다.

- [ ] `spec_bridge/service.py`로 `make_provider`, `make_rag`, `normalizer_for`, `prompt_hashes`, `sha256_file`, `RAG_*` 상수를 옮긴다. `eval/experiment.py`는 다시 내보낸다(re-export, 기존 import 호환).
- [ ] `rescore.evaluation_hashes()` 결과가 `2d5f9c663da8` 그대로인지 확인한다(옮기는 모듈은 해시 대상이 아님).
- [ ] 사용자 터미널: `uv add langgraph langgraph-checkpoint-sqlite` 실행 후 설치된 버전을 decisions.md에 기록한다.
- [ ] 확인: `uv run python -c "import langgraph, langgraph.checkpoint.sqlite"`

**DoD:** 기존 테스트 전부 통과(647 passed 기준), `ruff`·`mypy` 깨끗, 채점기 ID 불변.

### Task 1 (W5-1): 파이프라인 단계 함수

**Interfaces (Produces):**
```python
def parse_step(path: Path, document_id: str) -> Document          # ParseError 전파
def classify_step(onto, document, provider) -> Classification     # LlmError 전파
def extract_step(onto, document, class_id, provider, rag) -> Extraction   # C + E1SV
def check_step(onto, class_id, facts, unresolved, registry, makers) -> tuple[Validation, list[Match]]
def process_document(...) -> RegistrationResult                   # 위 함수 조합, 동작 불변
```

- [ ] 실패 테스트(`tests/test_pipeline.py` 신규): 가짜 제공자로 단계 함수를 차례로 부른 결과와 `process_document` 결과가 같다.
- [ ] `pipeline.py`에서 단계를 꺼낸다. 실패 처리(`_failed`)는 `process_document`에 남긴다.
- [ ] 기존 `tests/api/test_app.py`가 바뀌지 않고 통과한다.

**DoD:** `uv run pytest tests/api tests/test_pipeline.py -q` 통과, 전체 3종 검사 깨끗.

### Task 2 (W5-2): 등록 그래프와 HITL

**Interfaces (Produces):**
```python
class JobState(TypedDict, total=False):
    job_id: str; document_id: str; file_name: str; path: str
    document: dict            # Document.model_dump(mode="json")
    class_id: str; class_candidates: list[str]
    facts: list[dict]; unresolved: list[dict]
    validation: dict; matches: list[dict]
    edits: list[dict]         # 누적 HumanEdit 행
    acknowledged: list[str]   # 확인한 REVIEW Finding id
    decision: dict | None     # 마지막 재개 명령
    product_id: str | None; outcome: Literal["registered", "linked", "cancelled"] | None
    failure: str | None

ResumeCommand = Annotated[ChooseClass | Edit | Acknowledge | RegisterNew | Link | Cancel,
                          Field(discriminator="action")]

def build_graph(deps: GraphDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph
def interrupt_payload(state: JobState) -> ReviewPrompt   # 화면이 그릴 선택지·막힌 사유
```

- [ ] 실패 테스트(가짜 제공자, `tmp_path`의 SqliteSaver):
  - 분류 unknown → `choose_class`에서 멈춤 → `ChooseClass` 재개 → `review`에서 멈춤
  - `review` 결과가 `process_document`의 사실·검증·판정과 같음(사람 개입 전 동일성)
  - `Edit`(값 변경) → 재검증 루프 → 다시 `review`, LLM 호출 수 증가 0
  - 단위 차원이 틀린 수정 → 예외 없이 Finding으로 표시, `RegisterNew` 거부 사유 표시(Review Focus 4)
  - **재시작**: 그래프를 새로 만들고 같은 체크포인트 DB·`thread_id`로 상태 조회 → 같은 `review` 화면, 가짜 제공자 호출 0(Review Focus 2)
  - 파싱 실패 → `review`에서 선택지가 `Cancel`만
- [ ] 노드 구현, 조건 간선(`route_after_classify`, `route_after_review`), `interrupt()`는 `choose_class`·`review`에만 둔다.
- [ ] `Edit` 적용은 `registry/edits.py`의 결정론 함수다. 수정된 사실의 근거를 `human_edit`로 바꾸고 원래 occurrence는 이전 값 기록에 남긴다.

**DoD:** `uv run pytest tests/graph -q` 통과, 3종 검사 깨끗.

### Task 3 (W5-3): 등록 저장소 — 등록·연결·수정·감사

**Interfaces (Produces):**
```python
class RegistryStore:
    def records(self) -> list[dict[str, Any]]      # matcher 입력(jsonl 레코드와 같은 모양)
    def register_product(self, job_id: str, result: RegistrationResult,
                         edits: list[HumanEditRow], actor: str) -> str   # product_id, 멱등
    def link_document(self, job_id: str, target_id: str, result: RegistrationResult,
                      actor: str) -> None                                  # 멱등
    def product(self, product_id: str) -> ProductView  # 사실 + 근거 + 수정 이력 + 사건
    def audit(self, job_id: str, kind: str, actor: str, payload: dict) -> None
```

- [ ] 실패 테스트:
  - 같은 `job_id`로 `register_product` 두 번 → 제품 1개, 같은 `product_id` 반환(Review Focus 1)
  - 식별이 같은 기존 제품이 있을 때 `register_product` → `RegistryError("duplicate identity …")`, 표 변경 없음(트랜잭션 롤백, Review Focus 3)
  - 등록된 사실마다 `evidence_kind ∈ {observed, human_edit}`. `human_edit`의 `evidence_ref`가 `human_edits` 행을 가리킴
  - 근거 없는 사실(occurrence도 수정 기록도 없음) → 거부
  - `link_document` → 대상 사실 불변, 사건 1행
  - 스키마 1 DB를 열면 2로 마이그레이션되고 seed 행 수 불변
  - `records()` 결과를 `match()`에 넣은 판정 = jsonl로 넣은 판정(개발 seed 기준)
- [ ] 구현: 단일 트랜잭션(`with conn:`), 멱등 키 `f"{job_id}:register"`·`f"{job_id}:link:{target}"`(`registration_events.idempotency_key UNIQUE`).
- [x] `product_id` 형식: `REG-UP-<sha256(job_id) 앞 10자>`(구현 시 단순화, 클래스는 `class_id` 열에 있음). 합성 seed 번호 체계와 겹치지 않는다(origin `user_registered`).

**DoD:** `uv run pytest tests/registry -q` 통과, 3종 검사 깨끗.

### Task 4 (W5-4): 작업 API와 S1·S2 API 시연

**Endpoints:**

| 메서드·경로 | 동작 | 응답 |
|---|---|---|
| `POST /api/jobs` (multipart) | 업로드 저장, 그래프를 백그라운드로 첫 중단점까지 실행 | 202 `{job_id}`. 415·400은 W4와 같음 |
| `GET /api/jobs` | 작업 목록(최근순) | `JobSummary[]` |
| `GET /api/jobs/{id}` | 단계(`running`·`awaiting_class`·`awaiting_review`·`registered`·`linked`·`cancelled`), 현재 결과, 중단 페이로드(선택지·막힌 사유) | `JobView` |
| `POST /api/jobs/{id}/resume` | `ResumeCommand` + `request_id` | 202 `JobView`. 같은 `request_id` 재전송은 재적용하지 않음. 현재 단계에서 허용되지 않는 명령은 409와 사유 |
| `GET /api/jobs/{id}/source` | 업로드 원본(PDF 보기) | 파일 |
| `GET /api/jobs/{id}/blocks` | 파싱 블록과 위치 | `BlockView[]` |
| `GET /api/products/{id}` | 등록 제품, 근거, 수정 이력, 사건 | `ProductView` |
| `GET /api/jobs/{id}/supplement` | 보강 요청 목록(D-066): 빠진 필수 속성, 필수 사유 규칙, 기대 형식(데이터형·단위·허용값), 판독 실패 값과 위치. LLM 없음 | `SupplementRequest` (JSON, 텍스트 내보내기) |

- 실행 모델: 로컬 LLM은 동시에 하나만 돌린다. 백그라운드 작업은 프로세스 안 단일 작업자 잠금으로 직렬화한다. 화면은 1~2초 간격으로 `GET /api/jobs/{id}`를 폴링한다.
- [ ] 실패 테스트(TestClient + 가짜 서비스): 업로드 → `awaiting_review` → `Edit` → `RegisterNew` → `registered`. 같은 `request_id` 재전송 시 제품 1개. duplicate에서 `RegisterNew` → 409와 사유. 없는 작업 → 404. `/documents`·`/health` 기존 테스트 유지.
- [ ] `uv run python -m spec_bridge.api.openapi` → `web/openapi.json`(커밋 대상, 계약 파일).
- [ ] `scripts/s1_s2_api_demo.sh openai|ollama`(mvp_check와 같은 포트 점검 방식):
  - S1: 개발 문서 1건 업로드 → 값 1개 수정 → 등록 → 제품 상세에 수정 이력
  - S2: duplicate가 있는 개발 문서(SYN-004) 업로드 → 연결 → 기존 제품 사실 불변 + 사건 1행
- [ ] 사용자 터미널: 시연 스크립트를 `openai`(빠른 배선 확인)로 실행하고, 이어서 `ollama`로 1회 실행한다.

**DoD:** 3종 검사 깨끗, 시연 스크립트 출력에 S1 `registered` + 수정 이력 1행, S2 `linked` + 대상 사실 불변. **이 시점에 UI 없이도 S1·S2가 API로 동작한다.**

### Task 5 (W5-5): 프런트엔드 골격 (결정 1 승인 후)

- [ ] 사용자 터미널: `npm create vite@latest web -- --template react-ts`로 만든 뒤, 헬퍼가 적어 둔 `npm install` 명령으로 위 도구를 설치한다. 설치된 버전을 decisions.md에 기록하고 `package-lock.json`을 커밋 대상으로 둔다.
- [ ] `web/package.json` 스크립트:
  - `gen:api` = `openapi-typescript openapi.json -o src/api/schema.d.ts`
  - `check` = `tsc --noEmit && biome check . && vitest run`
  - `build` = `vite build`(출력 `web/dist`, git 제외)
- [ ] `vite.config.ts`: 개발 서버의 `/api`·`/health`를 `http://127.0.0.1:8000`으로 프록시하고, 호스트는 `127.0.0.1`.
- [ ] pdf.js 워커를 번들에 포함한다(CDN 금지). 폰트는 시스템 폰트만 쓴다.
- [ ] FastAPI: `web/dist`가 있으면 `/`에 정적 파일로 마운트한다. 없으면 건너뛴다(테스트·MVP 영향 없음).
- [ ] 테스트: 생성 타입 기반 클라이언트로 `GET /api/jobs`를 MSW로 모킹한 목록 렌더 1개.

**DoD:** `npm --prefix web run check`·`build` 통과, `uv run uvicorn …` 후 `http://127.0.0.1:8000/`에서 빈 작업 목록이 보인다(사용자 확인), Python 3종 검사 깨끗.

### Task 6 (W5-6): 검토 화면 3분할

```
┌──────────── 원문 ────────────┬──────── 추출 속성 ────────┬──── 오류·중복 ────┐
│ PDF: 페이지 + 상자 겹침       │ 속성 | 값 | 단위 | 문맥 | 근거 │ Finding 목록       │
│ DOCX/XLSX: 블록 목록, 행 강조 │ [수정] → 값·단위·사유 입력   │ (속성 클릭 → 강조) │
│ 속성 선택 ↔ 위치 강조 연동    │ 미해결 값 목록               │ duplicate/similar  │
│                              │                              │ 차이 속성, 선택 버튼│
└──────────────────────────────┴──────────────────────────────┴───────────────────┘
          하단: [등록] [연결 → 대상] [취소]  (서버가 준 허용 선택지만 활성)
```

- **문맥 확인 필요 표시**(D-069): `context_hints`의 사실 행에 표시와 사유를 보여 준다. 표시가 없어도 문맥이 완전하다는 뜻이 아니라는 안내를 둔다.
- **보강 요청 탭**(D-066): 등록이 E1로 막히면 오류 영역에 보강 요청 목록과 내보내기 버튼을 보여 준다. 시스템은 빠진 값을 채우지 않는다.
- **좌표 변환**(`src/lib/bbox.ts`): 서버 bbox는 PDF 포인트, 좌하단 원점 `[x0, y0, x1, y1]`이다. 화면 상자는 `left = x0·s`, `top = (H − y1)·s`, `width = (x1 − x0)·s`, `height = (y1 − y0)·s`로 계산한다(`H` = 페이지 높이(pt), `s` = 렌더 배율).
- 버튼 활성 여부는 화면이 계산하지 않는다. 서버의 `interrupt_payload`(허용 선택지·막힌 사유)를 그대로 표시한다. 규칙을 한 곳(서버)에만 두기 위해서다.
- [ ] 테스트(Vitest):
  - `toScreenBox` 변환: 페이지 상단 근처 상자가 화면 상단에 오고, 배율 2배에서 두 배가 된다(Review Focus 5)
  - Location 종류별 강조 대상 선택: `pdf_page+bbox` → 상자, `table/row/column` → 블록 행, `cell_ref` → 블록 행
  - 수정 폼 제출 → `resume` 요청 본문이 `Edit` 형태이고 `request_id`가 있다(MSW)
  - 서버가 `RegisterNew`를 막으면 등록 버튼이 비활성이고 사유가 보인다
  - 폴링: `running` → `awaiting_review`로 바뀌면 3분할이 그려진다

**DoD:** `npm --prefix web run check`·`build` 통과.

### Task 7 (W5-7): 작업 목록·제품 상세와 UI 시연 (W5 DoD)

- [ ] 작업 목록 화면(업로드 버튼, 상태 배지, 클릭 → 검토), 분류 unknown일 때 클래스 선택 화면, 제품 상세(사실·근거 종류·수정 이력·사건).
- [ ] 사용자 시연(로컬 `ollama`, OFFLINE=1):
  - S1: 개발 PDF 1건 업로드 → 하이라이트 확인 → 값 1개 수정(사유) → 등록 → 제품 상세에 수정 이력
  - S2: SYN-004 업로드 → duplicate 표시와 차이 속성 → "기존 레코드에 연결" → 대상 사실 불변
  - S2 보조: 식별 값을 고치지 않고 "별도 등록"이 막히는지 확인
- [ ] (선택) Playwright로 S1 흐름 E2E 1개(가짜 제공자 서버). 브라우저 내려받기가 필요해서 사용자가 원할 때만 한다.

**DoD(계획서 W5):** S1·S2가 UI에서 업로드부터 등록까지 끝까지 동작한다. 시연은 사용자가 확인하고 결과를 decisions.md에 기록한다. 헬퍼는 판정하지 않는다.

### Task 9 (W5-9): 보고서와 문서

- [ ] `docs/reports/w5-review-ui-registration.md`: 그래프 구조, 중단점, 멱등성 확인, 시연 결과(소요 시간, 수정·연결 기록), 한계.
- [ ] 계획서 갱신(결정 1 승인 시 Streamlit 표기 교체, 변경 이력). decisions.md에 승인된 결정과 설치 버전을 기록한다.

---

## 결정 (요약, 2026-10-13 모두 승인)

| # | 결정 | 권장 |
|---|---|---|
| 1 | 검토 UI 스택 | React·TS·Vite + 위 도구 표(FastAPI가 빌드 결과를 서빙). 백엔드를 먼저 완성해 일정 위험을 줄인다 |
| 2 | 그래프 구조 | 중단점 2개(`choose_class`, `review`), 수정은 결정론 재검증 루프, DB 쓰기는 `register` 노드에만 |
| 3 | 등록 규칙 | 강제 등록 없음. duplicate의 별도 등록은 식별 값 수정 후에만. 연결은 사건 기록만 |
| 4 | 저장 위치 | 작업 DB(`var/app/registry.sqlite`, 스키마 2) + 체크포인트 DB 분리, 감사 표에 사람 결정과 LLM 호출 기록 |
| 5 | BOM(S3) | **승인됨(D-060)**: 이후 확장 |

## 이월 사항 (W5 범위 밖, 기록만)

- W4 개선 후보 1~4(숫자 없는 값 E3, 속성 오연결, 근접 오답, `motor_rated`): W6 테스트 평가 전에 반영할지 별도로 정한다. 반영하면 개발셋 조정 4회째로 기록한다.
- `fact_key` 위치 정리: 채점기 해시가 바뀌므로 W6 해시 재고정 때 함께 한다.
- **BOM 일괄 등록(S3, D-060)**: 확장 시 출발점은 dev BOM 2건의 행 → 기존 제품 식별 연결 → `has_component` 생성, 연결 실패 행만 `review`. 등록 그래프를 행마다 하위 그래프로 재사용한다. Excel BOM 생성과 BOM 정답이 먼저 필요하다.
- 구성 D, R8(표시형·라벨 RAG), 클라우드 E1SV 진단: W6에서 다시 판단한다.
