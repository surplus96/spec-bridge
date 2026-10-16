# 합성 평가 후보셋 답안 개요

갱신: 2026-10-06 · dataset_revision: **2** · 상태: **보완 완료, 온톨로지 연결·사용자 검토 전**
작성 이력: Claude 초안 → Codex 보완 · 근거: [D-003](../../../docs/decisions.md)

본문·정답의 의미와 출현 라벨을 보완했다. 모델 입력은 [inputs](inputs/)의 중립 파일명 문서 6건이다. 이 문서와 정답 YAML·manifest·관찰 메모는 평가기 전용이다. 평가 입력용 폴더를 통째로 읽을 때도 `inputs/`의 지정 파일만 사용한다.

검토 순서: 이 개요 → [채점 정책](SCORING-POLICY.md) → 기술 사양 본문 → 대응 정답 YAML → [보완 결과](../reviews/REMEDIATION-2026-10-06.md).

## 1. 문서 구성

모두 합성 제조사·형식명·수치로 작성했다. 오류 E1~E7 양성 사례를 주입하지 않았고 표기 변형 V1만 포함한다. 실제 허용 범위를 검증한 상태는 아니다.

| 입력 ID | 문서 ID | 클래스 | 가상 제조사 | 형식명 | 대표 속성 | V1 |
|---|---|---|---|---|---|---|
| DOC-001 | HW-PUMP-001 | Pump | Brekkhaug Marine AS | BMH-150/30 | 9 | 4 |
| DOC-002 | HW-COMP-001 | AirCompressor | Brekkhaug Marine AS | BKA-85/30 | 9 | 4 |
| DOC-003 | HW-SEP-001 | Separator | Hallmar Separation AB | HSX 40 | 9 | 3 |
| DOC-004 | HW-2S-001 | TwoStrokeMainEngine | Torvane Engine Works | TXL-650/6 | 10 | 3 |
| DOC-005 | HW-4S-001 | FourStrokeEngine | Torvane Engine Works | TMG-6A | 11 | 3 |
| DOC-006 | HW-TC-001 | Turbocharger | Torvane Engine Works | TTA-70 | 7 | 3 |

대표 속성은 **55개**, SEP의 추가 조건 처리량까지 포함한 값 채점 단위는 **56개**다. 반복 출현은 추가 속성 TP로 세지 않는다. 2S의 `has_component`는 TTA-70/HW-TC-001을 가리키며 관계는 별도 지표다.

제조사는 3곳으로 묶었다. 제조사가 같다는 이유만으로 제품을 중복 판정하지 않는다. 현재 등록 목록과 중복 양성 사례가 없어 중복·유사 성능은 평가하지 않는다.

## 2. 본문과 정답에 반영한 기준

- 2S: 본문에서 bhp를 기계식 마력, `1 bhp = 0.7457 kW`로 정의했다. 환산 반올림 허용 상대오차는 0.001이다. 실제 참고 문서의 다른 BHP 정의와 혼동하지 않는다.
- 4S: 출력은 연속 엔진 축출력이며 발전기 전기 출력이 아니다. ton은 본문에서 미터톤으로 정의했다.
- COMP: 용량은 FAD이며 기준 온도·절대압을 정답에 보존한다. 작동 압력은 gauge 기준이다.
- SEP: 점도는 50 °C 기준의 연료 특성이다. 실제 분리기 입구 점도·온도라는 의미로 쓰지 않는다. 380/700 조건의 처리량을 모두 정상 정답으로 평가한다.
- COMP·SEP·TC: Weight/Net weight 문구에 건조 상태와 포함 구성품 범위를 추가했다. 치수도 같은 범위의 유닛/모듈을 대상으로 한다.
- PUMP의 seawater, COMP의 air-cooled/작동 매체, SEP의 heavy fuel oil, 4S의 generating sets 등 본문에 직접 진술된 반복 출현을 추가했다.

**별도 함정 목록은 제거했다.** 조건부 정상값을 오답으로 분류하는 문제를 없앴으며, 오추출은 채점 정책의 속성/조건/클래스 매칭으로 판단한다. 정상 기술 정보인 기준 조건·실린더당 출력·극수·주파수·과급기 회전수·구성품 언급은 본문에 남겨 두었다. 기술 사양 파일 뒤의 설계·함정 메모도 제거했다.

## 3. 정답 형식 v2

| 필드 | 의미 |
|---|---|
| `schema_version: 2`, `dataset_revision: 2` | 함정 목록 제거 및 검증 미확정 상태를 반영한 개정 |
| `origin: synthetic` | 합성 자료 |
| `author`, `revised_by`, `reviewed_by` | 작성·보완·사용자 검토를 구별; 사용자 서명은 null 유지 |
| `files.spec_source`, `files.input_text` | 편집 원본과 클래스 약칭 없는 모델 입력 파일 |
| `files.docx`, `files.pdf` | 현재 미생성이라 null |
| `validation_status: ontology_pending` | W1 온톨로지 검증 전 |
| `missing_required: null`, 속성의 `expected_status: null` | 아직 확정하지 않은 필수 속성·검증 결과; pass로 해석하지 않음 |
| `scoring_policy` | [SCORING-POLICY.md](SCORING-POLICY.md) 경로 |
| `occurrences`, `unit_text` | 직접 진술된 속성 값의 근거 위치와 분리 단위 |
| `condition`, `conditional_values`, `reference_conditions` | 조건부 정답과 기준 조건 |
| `rating_basis`, `capacity_basis`, `pressure_basis` | 정격·용량·압력의 의미 기준 |
| `weight_basis`, `scope` | 건조 상태 및 중량·치수의 대상 범위 |
| `injections[].source_observations` | V1의 참고 문서 ID·PDF 페이지; 합성 변형이 원본과 완전히 동일하다는 뜻은 아님 |
| `open_issues` | W1 스키마 연결 사항 |

## 4. 검증과 한계

재현: `python data/eval/reviews/review_dataset.py`

[현재 실행 결과](../reviews/audit-results-current.json): 원본 12건 식별 대조, 핵심 표기 34건, 합성 출현 위치 99건, 수치·환산·치수·범위 비교 43건에 불일치가 없었다. 6개 입력 파일이 편집 본문과 같고 평가 메타데이터를 포함하지 않는지도 확인했다. 자동 대조가 모든 의미 라벨의 완전성이나 모델 추출 성능을 증명하지는 않는다.

치수·중량·모터 선정의 실제 현실성은 **[미검증]**이다. 내부 계산 근거는 [최초 검토 보고서 6장](EVALUATION-REPORT.md)에 있다. 실제 평균유효압력 허용 범위를 확인한 결과라고 표현하지 않는다.

같은 골격의 문서가 클래스당 1건뿐이다. 실제 문서의 병합 셀·다단 머리글·다중 모델·각주·다단 서술을 충분히 대표하지 않는다. D-003에 따라 독립적인 사람 작성 평가셋이라고 부르지 않는다. 가상 제조사명의 실제 회사명 비중복 여부는 미확인이다.

## 5. 확정 전 남은 절차

- [ ] W1 온톨로지와 클래스·속성·열거값·필수 항목·조건·정격/중량 기준을 대조한다. TC의 속성 7개와 목표 8~12개의 차이도 검토한다.
- [ ] 모델 입력 본문으로 DOCX/PDF를 생성하고 최종 텍스트·페이지 위치를 재대조한다.
- [ ] 사용자가 본문·정답·채점 정책을 검토하고 `reviewed_by`를 작성한다.
- [ ] 평가 전에 정답·정책·입력 파일의 버전과 해시를 고정한다.

본문 수정과 데이터 품질 보완은 수행했지만, 온톨로지 검증·렌더링 파일 생성·사용자 서명·모델 평가는 아직 수행하지 않았다.
