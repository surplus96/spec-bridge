# 합성 데이터셋 v1 (확정)

2026-10-08 · 사용자 결정 [D-019](../../docs/decisions.md) · origin: synthetic

6개 클래스(TwoStrokeMainEngine·FourStrokeEngine·Pump·AirCompressor·Separator·Turbocharger)의 제품 문서 추출·검증·중복 비교 평가용 합성 데이터셋이다. 실제 제조사·제품·수치가 아니다. 파일 무결성은 `shasum -a 256 -c data/synth/SHA256SUMS`(저장소 루트에서 실행)로 확인한다.

## 구성

| 자료 | 위치 | 수량 | 모델 입력 여부 |
|---|---|---:|---|
| 사양서 PDF·XLSX·DOCX | [inputs/](inputs/) | 20·12·8 | 입력 |
| 등록 제품(분할별)·제조사·합성 별칭 | [registry/](registry/README.md) | 개발 90·테스트 60 | 입력(해당 분할만) |
| 정답 v3(관찰·사실·오류·필수 누락·관계) | [answers/](answers/) | 40 | 평가기 전용 |
| 입력↔정답 매핑·분할·해시 | [dataset-manifest.yaml](dataset-manifest.yaml) | 40 | 평가기 전용 |
| 문서별 계열·사례·레이아웃 메타데이터 | [case-plan.yaml](case-plan.yaml) | 40 | 평가기 전용 |
| 전체 비교 정답(duplicate·similar, 나머지 new) | [comparison-candidates.yaml](comparison-candidates.yaml) | 40건(6·254) | 평가기 전용 |
| 설계 비교 시나리오 부분집합 | [comparison-pairs.yaml](comparison-pairs.yaml) | 중복 6·유사 4 | 평가기 전용 |
| 합성 BOM(공급 범위 포함 관계) | [boms/](boms/) | 4 | S3 시나리오 입력 |
| 채점 계약 | [answer-contract.yaml](answer-contract.yaml), [설명](answer-contract.md) | — | 평가기 전용 |
| 원본 표기 출현(문서·페이지) | [variant-catalog.yaml](variant-catalog.yaml) | 79 | W1 동의어 근거 |
| 작성 본문 Markdown(정답 `source_path`) | dev/sources, test/sources | 24·16 | 평가기 전용 |

분할은 제품 계열 기준(계열 24개)이며 개발 24·테스트 16건이다. 사례는 정상 10·E1~E5 20·중복 6·유사 4건, 레이아웃은 table 18·mixed 15·narrative 7건이다. 온톨로지 명세는 [data/ontology/dataset-contract.yaml](../ontology/dataset-contract.yaml)이다.

## 평가할 때 지킬 것

- 모델에는 `inputs/`의 파일과 같은 분할의 `registry/`만 준다.
- 채널(클래스·사실·관찰·오류·비교)별 분모는 [정답 계약](answer-contract.md)을 따른다. `main_equipment` 범위와 `unknown`/`not_applicable` 기준은 본문에 쓰지 않는 정책 기본값이다.
- **지름길 기준선을 함께 보고한다.** 개발셋 라벨 사전만으로 테스트 관찰의 91.6%를 속성에 대응할 수 있고, 모델명 시리즈 접두사 규칙만으로 similar 판정이 P/R 1.0이다. 제조사명 접미사(A/B 개발, C/D 테스트)는 분할과 일치한다.
- 같은 에이전트·절차로 작성한 계열 분리 합성 평가이며 외부 블라인드·사람 독립 작성 평가가 아니다. 별도 보완 후보셋 [handwritten 6건](../eval/handwritten/)은 따로 보고한다.

## 상태와 출처

사용자가 2026-10-08 확정을 결정했다(D-019). 도메인 의미(E4 문자열·열거 표시형·식별 규칙·similar 정의)는 사용자 검증 없이 합성 정책으로 확정했고 `reviewed_by`/`verified_by`는 사용자가 직접 채운다. MS Office GUI 확인은 하지 않았고 VS Code Office Viewer 4.2.0으로 확인했다. 작성 이력은 [decisions.md](../../docs/decisions.md) D-006~D-019에 있고, 생성 스크립트·원장·검사 기록은 [data/backups/](../backups/README.md)의 작성 자료 보관본에 있다.
