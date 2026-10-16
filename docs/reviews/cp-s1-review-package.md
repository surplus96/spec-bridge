# 🔶 CP-S1 교차 검토 패키지 — W1 온톨로지와 등록 저장소

2026-10-11 · 작성: 헬퍼 모델 · 상태: **검토 완료 — 보완 필요**([검토 결과](cp-s1-review-result.md), decisions.md `CP-S1` 항목). 헬퍼는 통과 판정을 하지 않는다(H2-4).

## 1. 배경 (5줄)

1. spec-bridge는 선박 기자재 6종 제품 문서에서 속성을 추출·정규화·검증해 중복을 검사하고 등록하는 로컬 우선 도구다.
2. W1은 이 흐름의 진실원천인 간이 온톨로지(YAML)와, 그것에서 파생되는 로더·무결성 검사·후보 JSON Schema·정의서·SQLite 등록 저장소를 만들었다.
3. 평가 데이터는 확정된 합성 데이터셋 v1(사양서 40·등록 150, 개발 24/테스트 16, D-019)이며 W1 코드·테스트는 테스트 분할 정답을 읽지 않았다(D-020).
4. 모든 도메인 사실은 출처 표기만 있고 사용자 검증(`verified_by`)은 0건이다. 클래스·필수 정책은 프로젝트의 합성 정책이다.
5. 이 검토 결과에 따라 W2(파서)로 넘어가기 전에 온톨로지를 수정하거나 미검증 항목을 `origin: synthetic`으로 전환·제거한다.

## 2. 검토 대상

| 파일 | 역할 |
|---|---|
| `ontology/ontology.yaml` | 클래스 10(말단 6·상위 4), 속성 27, 단위 12, 차원 10, 기준 어휘 4종·조건 9종, 라벨 별칭 21 |
| `spec_bridge/ontology/definitions.py` | YAML 형태 모델(Pydantic, extra=forbid) |
| `spec_bridge/ontology/loader.py` | 교차 검사: 부모·순환·필수 참조·pint 차원·별칭 충돌·어휘 |
| `spec_bridge/ontology/facts.py`, `schema.py` | 공통 사실 모델, 클래스별 후보/등록 모델·JSON Schema 생성 |
| `spec_bridge/ontology/policy.py` | 등록 필수 해석(`missing_required`, ready/missing/review) |
| `spec_bridge/ontology/gold.py` | handwritten 정답 v2 → 후보 변환 |
| `spec_bridge/ontology/docs.py` → `docs/ontology/definition.md` | 정의서 자동 생성(어긋남 감지 테스트 포함) |
| `spec_bridge/registry/identity.py`, `store.py` | 식별 규칙, SQLite 7테이블 등록 저장소(D-021) |
| `tests/` | 103개 테스트 |

**산출 수치(명령 결과, 2026-10-11):**

| 확인 | 결과 |
|---|---|
| `uv run pytest -q` | 102 passed, 1 xfailed |
| `uv run ruff check .` / `uv run mypy spec_bridge`(strict) | 오류 0 / 오류 0 |
| W1 DoD: handwritten 정답 1건(HW-PUMP-001) 생성 스키마 검증 | 통과 |
| 확장 DoD(D-020): 개발 24건 정답 스키마 검증, `missing_required` 일치 | 24/24 |
| handwritten 나머지 5건 | 4 통과, HW-SEP-001 xfail(점도 v2 문자열) |
| 등록 DB | dev: 제품 90·사실 840·관계 6 / test: 60·585·6, 재적재 멱등 |
| 데이터셋 v1 해시(`shasum -c data/synth/SHA256SUMS`) | 불일치 0 |

말단 클래스별 속성 수(상속 포함): Pump 12, AirCompressor 11, Separator 10, TwoStrokeMainEngine 11, FourStrokeEngine 12, Turbocharger 8(계획 8~12 범위; Turbocharger 확장 후보는 open-issues U-09).

## 3. CP-S1 검토 질문 (계획서 H4)

1. **클래스 경계가 겹치지 않아 문서 하나가 한 클래스로 정해지는가?**
   - 계층은 D-002 그대로(말단 6, 상위 Equipment·FluidMachinery·Engine·EngineComponent).
   - 우려: `keywords`가 단어 하나씩이다(`pump`, `two-stroke` 등). 과급기 문서에 `two-stroke engines`(적용 엔진 조건), 분리기 문서에 `feed pump`(범위 문구), 4행정 E4 문서에 `fire pump drive`가 나온다. 키워드만으로 매핑하면 겹친다. 키워드는 W3 분류기의 단서일 뿐 판정 규칙이 아니라고 보는데, 이 구분이 충분한가?
2. **필수 속성이 "등록에 꼭 필요한 정보"로 정당화되는가?**
   - 근거: [schema-design.md](../ontology-scope/schema-design.md) §5 표(프로젝트 등록 준비 정책, 실제 법적·기술적 요건 아님). 선택 속성 누락은 오류로 처리하지 않는다.
   - 형식 미상 펌프는 조건부 필수를 적용하지 않고 `review` 상태(테스트로 고정).
3. **동의어 사전이 한 정규 표기로 수렴하는가(한 별칭이 두 속성에 걸리지 않는가)?**
   - 로더가 casefold 기준으로 한 라벨→두 속성을 거부한다(테스트 고정). 현재 21개 별칭 충돌 0.
   - 정책 테스트: 건조 여부가 없는 `Weight (kg)`는 `dry_weight`에 연결할 수 없다(→ `reported_weight`).
4. **실제 세계 사실에 근거한 항목에 출처가 있고 `verified_by`가 채워졌는가?**
   - 출처 있는 항목은 라벨 별칭 21개뿐이며 모두 `source`(REF ID)·`location`(PDF 페이지) 보유, **`verified_by`는 21/21 비어 있다.**
   - 허용 범위·형식명 해석·실제 제조사 별칭은 넣지 않았다(H3). application 허용값 2종은 합성 닫힌 목록(D-007).
   - 계획서 CP-S1 규칙상 W2 전에 (a) 사용자가 원본 페이지를 확인해 `verified_by`를 채우거나 (b) 해당 별칭을 `origin: synthetic`으로 전환하거나 (c) 제거해야 한다. **이 결정은 사용자 몫이다.**

## 4. 헬퍼가 확신이 낮은 지점

| # | 지점 | 현재 처리 | 확인 요청 |
|---|---|---|---|
| L1 | `Final pressure`(REF-COMP-02) → `working_pressure` | 명세 정의("작동/최종 압력")를 따름 | U-05(최대/작동 압력 의미)가 미해결인데 별칭으로 고정해도 되는가 |
| L2 | `nominal flow rate`는 합성 문서 중 **테스트 분할에만** 등장 | 출처가 원본 REF-PUMP-01 p.3이므로 유지 | 테스트 정답 기반 사전 조정으로 볼 여지가 있는가 |
| L3 | handwritten v2 `conditional_values`의 기준·범위 | 부모의 `rating_basis`·`scope`를 상속하도록 변환 | 변환기의 해석이 정답 의도와 맞는가 |
| L4 | HW-SEP-001 점도 `"380 cSt at 50 °C"` 문자열 | 변환기가 파싱하지 않고 xfail(strict) | 정답 v2→v3 이전을 할지, 보완 후보셋으로 남길지 |
| L5 | `rpm`과 `Hz`가 pint에서 같은 차원(1/time) | `rotational_frequency`·`frequency` 이름만 구분 | 단위 검사로 회전수/주파수 혼동을 못 잡는 한계가 수용 가능한가 |
| L6 | 등록 시드 사실의 근거 | `evidence_kind = registry_seed`(문서 관측 아님) | NFR-07(모든 값은 관측 또는 사람 수정 참조)과의 관계 — 시드를 별도 근거 종류로 두는 것이 타당한가 |
| L7 | 동적 모델 생성 | `create_model`+`Literal[tuple(...)]`, `list[fact]`에 `type: ignore[valid-type]` 1곳 | 정적 타입 검사 공백이 W3 구조화 출력에 위험한가 |
| L8 | 정격점 토큰 `R1/R2` | 합성 어휘로 등록 | 실제 엔진 정격점 명칭 관례와 무관함을 명시하면 충분한가 [미검증] |

## 5. 전제·가정

- 클래스 구조·필수 정책·어휘·식별 규칙은 프로젝트가 정한 합성 정책이다(`origin: synthetic`). 업계 표준 분류라고 주장하지 않는다.
- 후보 스키마는 구조 오류만 막고, 누락(E1)·허용값 위반(E4)·상충(E5)은 W4 검증기가 판정한다. 그래서 `fire pump drive` 같은 원문은 후보로 보존된다.
- 식별은 정확 일치(모델명 대소문자·공백·하이픈 무시, 제조사 등록명/합성 별칭)만 하고 근사 일치는 W4다.
- 등록 DB는 분할별 파일이며 데이터셋 jsonl에서 재생성 가능한 산출물(`var/`, gitignore)이다.

## 6. W1 범위에서 하지 않은 것

- 공유 모듈 이식(제공자 어댑터·오프라인 가드·감사 로그·평가 실행기): 원본 위치 미확인으로 보류(D-020).
- DNV Gmod `external_ref` 코드 연결: D-002 미해결 항목, 데이터 조회 전.
- 문서 관측값·판정·사람 수정 테이블: W4~W5(D-021).

## 7. 검토 결과 기록 방법

검토 결과를 받으면 [decisions.md](../decisions.md)에 `날짜 · CP-S1 · 지적 사항 · 조치 · 미해결`로 기록하고, 지적 사항을 해결한 뒤 W2로 진행한다.
