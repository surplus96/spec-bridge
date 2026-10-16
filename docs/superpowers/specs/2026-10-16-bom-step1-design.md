# BOM 1단계 설계 (D-101)

2026-10-16 · 상태: **승인**(사용자 "모두 권장안으로 진행해줘", 결정 1~7 모두 권장안) · 근거: D-060, D-065, D-099

**목표**: BOM 표의 각 행을 기존 제품으로 식별하고, 상위 제품과 `has_component`(공급 범위 포함, D-014) 관계를 만든다. 결정론만 쓴다(모델 호출 없음).

## 결정

| # | 결정 | 내용 |
|---|---|---|
| 1 | 입력 | Excel(.xlsx)과 Markdown 표. 머리 정보 `Root model`, `Manufacturer`, 표 열 `Component`, `Model`, `Manufacturer`, `Quantity`. 테스트 Excel은 테스트 안에서 Markdown 사본으로 만든다(데이터셋 파일 불변) |
| 2 | 실행 | 명령줄. 기본은 미리보기, `--apply`일 때만 저장한다 |
| 3 | 식별 실패 행 | 찾은 행만 적용하고 나머지는 "검토 대기"로 남긴다. 상위 제품을 못 찾으면 BOM 전체를 거부한다. 새 제품은 만들지 않는다 |
| 4 | 클래스 | 행의 `Component`가 식별된 제품의 클래스(또는 그 상위 클래스)가 아니면 식별 실패다 |
| 5 | 기존 관계 | 추가만 한다. "이미 있음"과 "BOM에 없는 기존 관계"를 보고한다. 지우거나 덮어쓰지 않는다 |
| 6 | 수량 | 관계 표는 바꾸지 않는다. 적용한 행 전체(수량 포함)를 제품 이벤트 `bom_linked`와 감사 기록에 남긴다 |
| 7 | 확인 | BOM 4건 12행을 정답 `product_id`(YAML)와 대조한다. 기존 목록에서는 "모두 이미 있음", 관계를 비운 저장소에서는 적용 뒤 seed와 같음. 실패 사례를 테스트한다. 기능 확인이며 성능 수치가 아니다(D-060) |

## 형태

- `spec_bridge/bom/reader.py`: `read_bom(path) -> BomDocument`(상위 모델·제조사, 행 목록, 원본 위치). 형식이 맞지 않으면 `BomError`.
- `spec_bridge/bom/linker.py`: `plan(store, onto, bom) -> BomPlan`(행마다 `new`·`existing`·`pending`과 사유, `not_in_bom`), `apply(store, plan, actor) -> int`.
- `RegistryStore`: `product_class`, `relations_of`, `add_components`(관계 추가 + 이벤트 + 감사, 한 트랜잭션, 같은 적용은 한 번만).
- `python -m spec_bridge.bom <BOM 파일> [--registry var/registry/dev.sqlite] [--apply]`.

## 범위 밖

BOM 행에서 새 제품 등록, 비정형 행의 RAG 매핑(G5 후속), 화면 연동(2단계), 호환성 판단(D-014).
