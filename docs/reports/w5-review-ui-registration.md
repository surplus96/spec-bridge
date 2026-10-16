# W5 검토 UI와 등록 — 결과 기록

2026-10-14 · 작성: 헬퍼 모델 · 상태: **W5 결과 기록**. 헬퍼는 DoD 통과를 판정하지 않는다(판정 자료: D-073, D-079).

근거 결정은 D-060~D-079다. 모든 시연은 개발 분할 문서(SYN-004, 011, 024)만 썼다. 테스트 분할은 실행하지 않았다(D-020). 채점기 ID는 `2d5f9c663da8`이고, 테스트로 고정했다(D-070).

## 1. 만든 것

```
브라우저(React·TS·Vite, FastAPI가 같은 출처로 서빙)
  └ 작업 API (/api/jobs …, 작업자 1개, request_id 중복 방지, 409 사유)
      └ LangGraph 등록 그래프 (SqliteSaver 체크포인트)
          parse → classify ─(unknown)→ ⏸ choose_class
                 └→ extract(C + E1SV RAG) → normalize → check(E1~E5, 중복·유사) → ⏸ review
          ⏸ review ─ edit → apply_edit → check → ⏸ review      (LLM 없음)
                   ─ register_new / link → register(멱등) → 끝
      └ 등록 저장소 (SQLite 스키마 2: products, product_facts, human_edits, registration_events, audit_events)
```

| 구성요소 | 파일 | 결정 |
|---|---|---|
| 서비스 배선 분리 | `spec_bridge/service.py`, `api/deps.py` | D-062 |
| 파이프라인 단계 함수 | `spec_bridge/pipeline.py` | — |
| 등록 그래프·HITL | `spec_bridge/graph/` | D-062 |
| 사람 수정(결정론 재정규화) | `spec_bridge/registry/edits.py` | D-063 |
| 등록·연결·수정 이력·감사(멱등) | `spec_bridge/registry/store.py` | D-063, D-064 |
| 보강 요청 목록 | `spec_bridge/registry/supplement.py` | D-066 |
| 설명형 표시 | `spec_bridge/registry/explain.py` | D-071, D-072, D-076 |
| 작업 API·OpenAPI 계약 | `spec_bridge/api/jobs.py`, `web/openapi.json` | D-061 |
| 검토 UI 3분할, 제품 상세 | `web/src/features/` | D-061, D-074 |
| 화면 표시명(origin synthetic) | `ontology/display-labels.yaml` | D-074 |

## 2. 핵심 설계 (실측으로 확인한 성질)

- **중단점은 두 곳**(`choose_class`, `review`)이다. LangGraph는 재개할 때 멈춘 노드를 처음부터 다시 실행한다(탐침으로 확인). 그래서 DB 쓰기는 `register` 노드에만 둔다.
- **수정 후에는 LLM을 부르지 않는다.** 사람 수정도 추출값과 같은 정규화기를 거친다. 단위가 틀리면 E2가 되어 등록이 막힌다.
- **재시작 후 같은 화면에서 이어진다.** 체크포인트를 쓰고, LLM 호출은 0이다(테스트).
- **멱등은 세 겹이다.** API `request_id`, 그래프 판본(revision), 저장소 멱등 키다.
- **자동 병합이 없다.** 연결은 사건만 남기고 사실은 바꾸지 않는다(S2, 실행마다 "사실 불변 True").
- **근거 100%다(NFR-07).** 등록 사실은 원문 위치(`observed`) 또는 수정 기록(`human_edit`)을 가진다. 문서 밖 값은 입력할 수 없고(D-063 보완), 빠진 값은 보강 요청 목록으로 안내한다(D-066).
- **화면은 판단하지 않는다.** 허용 선택지·차단 사유·설명은 서버가 계산하고, 조회할 때마다 다시 계산한다(D-071 보완).

## 3. 시연 결과

| 경로 | 문서 | 결과 | 기록 |
|---|---|---|---|
| API 스크립트, 로컬 | SYN-011, 004, 011 | S1 등록(11/0/0), S2 연결, S2b가 방금 등록한 제품을 duplicate로 판정 | D-068 |
| API 스크립트, 클라우드 | 같음 | 동작. SYN-011 `rated_power` 기준 누락 1건(Finding 0이어도 값이 모두 맞는 것은 아님) | D-068 |
| UI, 클라우드 | SYN-024, 011, 004 | PDF 하이라이트, 설명형 오류, 수정·등록·연결 | D-073 |
| **UI, 로컬(OFFLINE)** | SYN-011, 004, 011 | S1 등록(근거 원문 10·수정 1), S2 연결, S2b duplicate 판정. LLM 54회, 실패 0 | D-079 |

## 4. 화면 확인에서 발견해 고친 것

| # | 현상 | 원인 | 결정 |
|---|---|---|---|
| 1 | 클라우드 S1 작업 실패 | strict 아닌 응답(필드가 문자열)에서 `verify()`가 예외 | D-067 |
| 2 | 오류 문구가 코드·좌표뿐, "kg kg" | 표시 설계 부족 | D-071 |
| 3 | 수정 전에 멈춘 작업은 예전 안내를 보임 | interrupt 페이로드가 체크포인트에 고정 | D-071 보완 |
| 4 | 문맥 확인 사유가 사실마다 10개 이상 | 클라우드가 모든 축을 null로 보냄, 지어낸 축 | D-072 |
| 5 | 로컬 서버 첫 로드 500 | 서비스 동시 생성으로 임베딩 요청이 겹침 | D-075 |
| 6 | 등록 목록에 없는 제조사로 등록 시도 → 누른 뒤에야 거부 | 검토 단계에서 미리 확인하지 않음 | D-076 |
| 7 | seed 제품에 빈 문맥 칩 15개, 치수 순서 뒤바뀜 | seed는 모든 축을 기본값으로 저장 | D-077 |
| 8 | S2b가 duplicate 대신 similar에 연결 | 연결 후보 순서와 화면 기본값 | D-079 |
| 9 | 패키지 전체 포맷으로 채점기 ID가 바뀜 | 해시 대상 파일의 공백 변경 | D-070(원복, ID 고정 테스트) |

1·4는 클라우드(strict 아님)에서만 생겼다. 5·8은 화면이 실제로 여러 요청을 보내거나 사람이 기본값을 그대로 쓸 때만 드러났다. 단위 테스트만으로는 찾지 못한 결함이라는 점에서 사용자 화면 확인의 가치가 컸다.

## 5. 검사

- Python: 718 passed / 5 skipped / 1 xfailed, ruff·mypy(135파일) 깨끗.
- 프런트: `npm run check`(tsc·Biome·Vitest 31) 통과, `npm run build` 성공(기본 번들 약 290 kB, pdf.js는 PDF를 열 때만 불러옴). 화면이 외부에서 불러오는 자원은 0이다.

## 6. 한계와 남긴 것

- **시연은 기능 확인이다.** 문서 3종, 실행 몇 건이다. 성능 수치는 W4-R 개발셋 실험(D-053)을 인용한다.
- **사람 수정의 내용은 시스템이 검증하지 않는다.** 로컬 S1에서 `bore`를 원문 210에서 200으로 바꿨다. 정규화·검증은 통과했고 수정 기록으로 추적된다. 원문과 다른 값을 막는 것은 이 시스템의 범위가 아니고, 사유와 이력으로 책임을 남긴다.
- **문맥 누락은 규칙으로 잡히지 않는다.** 클라우드 `rated_power` 기준 누락이 그 예다. 문맥 확인 표시(D-069)는 모델이 제시했다가 거부된 경우만 보인다.
- seed와 신규 등록의 저장 형태 차이(D-077)와 `fact_key` 위치 정리는 W6 정리 후보다.
- 이후 확장: BOM(D-060), 호스트 연동(Atlas CMMS, D-078, `docs/research/atlas-cmms-host-integration.md`).

## 7. 다음

W6: 채점기·프롬프트·KB 해시 재고정, 테스트 분할과 독립 수기 사양서로 E1SV를 1회 평가(W4-R ③), 최종 비교표, 오프라인 테스트, README·데모, 🔶 CP-S4.
