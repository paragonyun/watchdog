# Watchdog Dashboard v2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 민감 원본을 로컬 SQLite에 보관하고, 거래·현금흐름을 대사해 TWR와 혼합 벤치마크를 계산하며, 개인정보가 제거된 v2 요약을 생성하는 Watchdog 기반을 구축한다.

**Architecture:** 기존 파일 기반 스냅샷과 `dashboard_payload_v1`은 호환성을 위해 유지한다. 새 `ledger` 패키지가 SQLite 원장과 수집 상태를 소유하고, `performance` 패키지가 원장 데이터만 입력받아 성과를 계산한다. 앱 계층은 제공자 어댑터를 통해 거래를 수집하고, 대사가 완료된 계산 결과만 허용 필드 기반 v2 payload로 내보낸다.

**Tech Stack:** Python 3.11, 표준 라이브러리 `sqlite3`, `dataclasses`, `requests`, pytest, 기존 Portfolio Watchdog CLI 및 Windows Task Scheduler

---

## 계획 범위

이 계획은 승인 설계의 Phase 0~1과 Phase 2의 최소 데이터 계약까지만 구현한다.

- 포함: 개인정보 계약, SQLite 원장, 기존 JSON 스냅샷 가져오기, Upbit/KIS 거래 수집 기반, 수동 현금흐름, 대사, TWR, 낙폭, 혼합 벤치마크 계산, v2 비식별 payload, 로컬 스케줄
- 제외: Neon 스키마, GitHub Actions, 공개 시세 수집, 대시보드 화면 개편, 뉴스 큐, 의견 승인 UI, 웹 리포트

후속 계획은 이 계획 완료 후 다음 순서로 작성한다.

1. `watchdog-dashboard-v2-cloud-sync`
2. `watchdog-dashboard-v2-core-ui`
3. `watchdog-dashboard-v2-research-reports`
4. `watchdog-dashboard-v2-operations`

## 파일 구조

### 새 Python 모듈

| 파일 | 책임 |
|---|---|
| `src/portfolio_watchdog/cloud_contract.py` | 클라우드 허용·금지 필드와 payload 검사 |
| `src/portfolio_watchdog/ledger/models.py` | 원장 이벤트와 평가 스냅샷 타입 |
| `src/portfolio_watchdog/ledger/schema.py` | SQLite 스키마 버전과 마이그레이션 |
| `src/portfolio_watchdog/ledger/repository.py` | 원장 저장·조회·중복 방지·수집 커서 |
| `src/portfolio_watchdog/ledger/import_history.py` | 기존 `history.json` 일회성 가져오기 |
| `src/portfolio_watchdog/ledger/ingestion.py` | 제공자별 거래 수집 및 원장 적재 오케스트레이션 |
| `src/portfolio_watchdog/ledger/reconciliation.py` | 거래·현금흐름·평가 스냅샷 대사 |
| `src/portfolio_watchdog/performance/twr.py` | TWR와 월간 수익률 계산 |
| `src/portfolio_watchdog/performance/risk.py` | 낙폭 계산 |
| `src/portfolio_watchdog/performance/benchmark.py` | 버전이 있는 목표 비중 혼합 벤치마크 |
| `src/portfolio_watchdog/performance/service.py` | 성과 계산 결과 조립 |

### 수정할 기존 모듈

| 파일 | 변경 |
|---|---|
| `src/portfolio_watchdog/models.py` | 데이터 상태와 성과 결과 타입 추가 |
| `src/portfolio_watchdog/config.py` | 원장 경로와 대사 허용오차 설정 |
| `src/portfolio_watchdog/providers/upbit.py` | 현재 공식 거래·입출금 조회 메서드 추가 |
| `src/portfolio_watchdog/providers/kis.py` | 주식일별주문체결조회 파서와 조회 메서드 추가 |
| `src/portfolio_watchdog/dashboard_data.py` | v2 payload 생성, 로컬 저장, 기존 v1 업로드 전 개인정보 검사 |
| `src/portfolio_watchdog/report_data.py` | 확정된 성과 요약을 리포트 원본에 포함 |
| `src/portfolio_watchdog/app.py` | 원장 동기화·성과 계산 흐름 연결 |
| `src/portfolio_watchdog/cli.py` | `sync-ledger`, `add-cash-flow`, `performance-summary` 추가 |
| `src/portfolio_watchdog/scheduler.py` | 실제 계좌 수집 작업 4개 등록 |
| `.env.example` | 원장·대시보드 환경변수 설명 보완 |
| `config/config.example.yaml` | 원장 설정 예시 추가 |

### API 참고

- Upbit 현재 완료 주문 조회: `GET /v1/orders/closed`, 최대 조회 구간 7일
- Upbit 입금 조회: `GET /v1/deposits`
- Upbit 출금 조회: `GET /v1/withdraws`
- KIS: 개발자센터의 `주식일별주문체결조회`를 사용하고 주문·계좌 조회 API의 연속 조회 키를 처리

공식 문서:

- Upbit 완료 주문: <https://global-docs.upbit.com/reference/closed-order>
- Upbit 입금 목록: <https://global-docs.upbit.com/reference/list-deposits>
- KIS API 서비스: <https://apiportal.koreainvestment.com/apiservice>
- KIS API 카테고리: <https://apiportal.koreainvestment.com/apiservice-category>

구현 시작 시 실제 계정 호출 전 공식 API 문서와 응답 fixture를 다시 확인한다. 테스트는 네트워크를 호출하지 않는다.

---

### Task 1: 클라우드 개인정보 계약 고정

**Files:**
- Create: `src/portfolio_watchdog/cloud_contract.py`
- Create: `tests/test_cloud_contract.py`
- Modify: `src/portfolio_watchdog/dashboard_data.py`

- [ ] **Step 1: 금지 필드 재귀 검사 실패 테스트 작성**

```python
# tests/test_cloud_contract.py
import pytest

from portfolio_watchdog.cloud_contract import assert_cloud_safe


@pytest.mark.parametrize(
    "field",
    [
        "quantity",
        "current_quantity",
        "average_buy_price_krw",
        "account_no",
        "order_id",
        "uuid",
        "api_key",
        "secret_key",
        "raw_response",
    ],
)
def test_assert_cloud_safe_rejects_forbidden_fields_at_any_depth(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        assert_cloud_safe({"safe": [{"nested": {field: "secret"}}]})


def test_assert_cloud_safe_accepts_dashboard_summary() -> None:
    assert_cloud_safe(
        {
            "schema_version": "dashboard_payload_v2",
            "generated_at": "2026-06-06T08:00:00",
            "total_value_krw": 1000,
            "assets": [{"symbol": "BTC", "value_krw": 1000}],
        }
    )
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cloud_contract.py -q`

Expected: FAIL with `ModuleNotFoundError: portfolio_watchdog.cloud_contract`

- [ ] **Step 3: 금지 필드 검사 구현**

```python
# src/portfolio_watchdog/cloud_contract.py
from __future__ import annotations

from typing import Any


FORBIDDEN_CLOUD_FIELDS = frozenset(
    {
        "quantity",
        "current_quantity",
        "average_buy_price_krw",
        "account_no",
        "account_product_code",
        "order_id",
        "order_no",
        "uuid",
        "access_key",
        "api_key",
        "app_key",
        "secret_key",
        "app_secret",
        "raw_response",
        "raw_api_response",
    }
)


def assert_cloud_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.lower() in FORBIDDEN_CLOUD_FIELDS:
                raise ValueError(f"forbidden cloud field: {child_path}")
            assert_cloud_safe(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_cloud_safe(child, f"{path}[{index}]")
```

`upload_dashboard_payload()`에서 HTTP 요청 직전에 `assert_cloud_safe(payload)`를 호출한다. 기존 `build_dashboard_payload()` 테스트는 계속 통과해야 한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cloud_contract.py tests\test_dashboard_data.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/cloud_contract.py src/portfolio_watchdog/dashboard_data.py tests/test_cloud_contract.py
git commit -m "Add cloud payload privacy contract"
```

---

### Task 2: SQLite 원장 스키마와 설정 추가

**Files:**
- Create: `src/portfolio_watchdog/ledger/__init__.py`
- Create: `src/portfolio_watchdog/ledger/models.py`
- Create: `src/portfolio_watchdog/ledger/schema.py`
- Create: `src/portfolio_watchdog/ledger/repository.py`
- Create: `tests/test_ledger_repository.py`
- Modify: `src/portfolio_watchdog/config.py`
- Modify: `config/config.example.yaml`

- [ ] **Step 1: 원장 생성·중복 방지 테스트 작성**

```python
# tests/test_ledger_repository.py
from datetime import datetime

from portfolio_watchdog.ledger.models import LedgerEvent
from portfolio_watchdog.ledger.repository import LedgerRepository


def test_ledger_repository_is_idempotent_by_provider_event_id(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    event = LedgerEvent(
        provider="upbit",
        provider_event_id="order-1",
        occurred_at=datetime(2026, 6, 6, 8, 0),
        event_type="buy",
        asset_symbol="BTC",
        cash_flow_krw=-100_000,
        quantity=0.001,
        unit_price_krw=100_000_000,
        fee_krw=500,
    )

    assert repository.upsert_event(event) is True
    assert repository.upsert_event(event) is False
    assert len(repository.list_events()) == 1


def test_ledger_repository_stores_sensitive_detail_only_locally(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")
    repository.upsert_event(
        LedgerEvent(
            provider="kis",
            provider_event_id="branch-order-1",
            occurred_at=datetime(2026, 6, 6, 9, 0),
            event_type="sell",
            asset_symbol="360750",
            cash_flow_krw=120_000,
            quantity=10,
            unit_price_krw=12_000,
            fee_krw=100,
        )
    )

    stored = repository.list_events()[0]
    assert stored.quantity == 10
    assert stored.unit_price_krw == 12_000
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_repository.py -q`

Expected: FAIL because `portfolio_watchdog.ledger` does not exist

- [ ] **Step 3: 원장 모델과 스키마 구현**

```python
# src/portfolio_watchdog/ledger/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class LedgerEvent:
    provider: str
    provider_event_id: str
    occurred_at: datetime
    event_type: str
    asset_symbol: Optional[str]
    cash_flow_krw: float
    quantity: Optional[float] = None
    unit_price_krw: Optional[float] = None
    fee_krw: float = 0.0
    external_cash_flow: bool = False
    memo: Optional[str] = None


@dataclass(frozen=True)
class AccountSnapshot:
    provider: str
    captured_at: datetime
    total_value_krw: float
    data_status: str
```

```python
# src/portfolio_watchdog/ledger/schema.py
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    asset_symbol TEXT,
    cash_flow_krw REAL NOT NULL,
    quantity REAL,
    unit_price_krw REAL,
    fee_krw REAL NOT NULL DEFAULT 0,
    external_cash_flow INTEGER NOT NULL DEFAULT 0,
    memo TEXT,
    UNIQUE(provider, provider_event_id)
);
CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    total_value_krw REAL NOT NULL,
    data_status TEXT NOT NULL,
    UNIQUE(provider, captured_at)
);
CREATE TABLE IF NOT EXISTS asset_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    asset_symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    value_krw REAL NOT NULL,
    quantity REAL,
    unit_price_krw REAL,
    average_buy_price_krw REAL,
    data_status TEXT NOT NULL,
    UNIQUE(provider, captured_at, asset_symbol)
);
CREATE TABLE IF NOT EXISTS collection_cursors (
    provider TEXT NOT NULL,
    stream TEXT NOT NULL,
    cursor_value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(provider, stream)
);
"""
```

`LedgerRepository`는 연결마다 `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, `PRAGMA busy_timeout = 5000`을 설정한다. 쓰기는 트랜잭션으로 처리한다. `upsert_event()`는 신규 이벤트면 `True`, 기존 이벤트면 `False`를 반환하되 KIS 장중 누적 체결처럼 같은 원본 이벤트의 수량·금액이 바뀌면 해당 행을 최신 값으로 갱신한다.

이번 계획에서 고정하는 저장소 공개 메서드는 다음과 같다.

```python
class LedgerRepository:
    def __init__(self, path: str | Path) -> None: ...
    def upsert_event(self, event: LedgerEvent) -> bool: ...
    def list_events(self, since: datetime | None = None, until: datetime | None = None) -> list[LedgerEvent]: ...
    def upsert_account_snapshot(self, snapshot: AccountSnapshot) -> bool: ...
    def list_account_snapshots(self, since: datetime | None = None) -> list[AccountSnapshot]: ...
    def upsert_asset_snapshot(self, snapshot: AssetSnapshot) -> bool: ...
    def list_asset_snapshots(self, captured_at: datetime | None = None) -> list[AssetSnapshot]: ...
    def get_cursor(self, provider: str, stream: str) -> str | None: ...
    def set_cursor(self, provider: str, stream: str, cursor_value: str, updated_at: datetime) -> None: ...
```

`AssetSnapshot`은 `AccountSnapshot`과 같은 파일에 정의하며 provider, captured_at, asset_symbol, asset_type, value_krw, quantity, unit_price_krw, average_buy_price_krw, data_status를 가진다.

- [ ] **Step 4: 원장 설정 파싱 추가**

```python
# src/portfolio_watchdog/config.py
@dataclass
class LedgerConfig:
    path: str = "snapshots/watchdog.db"
    reconciliation_quantity_tolerance: float = 0.00000001
    raw_response_retention_days: int = 30


# AppConfig에 추가
ledger: LedgerConfig = field(default_factory=LedgerConfig)
```

`load_config()`는 최상위 `ledger` 블록을 `_parse_ledger_config()`로 읽는다.

```yaml
# config/config.example.yaml
ledger:
  path: snapshots/watchdog.db
  reconciliation_quantity_tolerance: 0.00000001
  raw_response_retention_days: 30
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_repository.py tests\test_config_runtime.py -q`

Expected: PASS

- [ ] **Step 6: 커밋**

```powershell
git add src/portfolio_watchdog/ledger src/portfolio_watchdog/config.py config/config.example.yaml tests/test_ledger_repository.py
git commit -m "Add local SQLite investment ledger"
```

---

### Task 3: 기존 JSON 평가 이력을 SQLite로 가져오기

**Files:**
- Create: `src/portfolio_watchdog/ledger/import_history.py`
- Create: `tests/test_import_history.py`
- Modify: `src/portfolio_watchdog/ledger/repository.py`

- [ ] **Step 1: 재실행 가능한 가져오기 테스트 작성**

```python
# tests/test_import_history.py
import json

from portfolio_watchdog.ledger.import_history import import_history_json
from portfolio_watchdog.ledger.repository import LedgerRepository


def test_import_history_json_is_repeatable(tmp_path) -> None:
    history_path = tmp_path / "history.json"
    history_path.write_text(
        json.dumps(
            {
                "portfolio_snapshots": [
                    {
                        "captured_at": "2026-06-05T08:00:00",
                        "total_value_krw": 1000,
                        "assets": [
                            {
                                "symbol": "BTC",
                                "asset_type": "coin",
                                "value_krw": 1000,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repository = LedgerRepository(tmp_path / "watchdog.db")

    assert import_history_json(history_path, repository) == 1
    assert import_history_json(history_path, repository) == 0
    assert len(repository.list_account_snapshots()) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_import_history.py -q`

Expected: FAIL because `import_history_json` does not exist

- [ ] **Step 3: 최소 가져오기 구현**

`import_history_json()`는 기존 `portfolio_snapshots`만 읽고 다음 규칙을 적용한다.

- 제공자: `legacy_history`
- 데이터 상태: `actual`
- `captured_at`과 자산 symbol로 중복 방지
- 기존 JSON을 수정하거나 삭제하지 않음
- 민감 필드가 있더라도 로컬 SQLite에만 저장

함수 반환값은 새로 추가한 계좌 스냅샷 수다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_import_history.py tests\test_ledger_repository.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/ledger/import_history.py src/portfolio_watchdog/ledger/repository.py tests/test_import_history.py
git commit -m "Import legacy portfolio history into ledger"
```

---

### Task 4: Upbit 거래·입출금 어댑터 추가

**Files:**
- Create: `tests/fixtures/upbit_closed_orders.json`
- Create: `tests/fixtures/upbit_deposits.json`
- Create: `tests/fixtures/upbit_withdraws.json`
- Create: `tests/test_upbit_transactions.py`
- Modify: `src/portfolio_watchdog/providers/upbit.py`

- [ ] **Step 1: 공식 응답 형태 기반 파서 테스트 작성**

```python
# tests/test_upbit_transactions.py
import json
from pathlib import Path

from portfolio_watchdog.providers.upbit import parse_upbit_closed_orders


def test_parse_upbit_closed_orders_emits_one_event_per_trade() -> None:
    rows = json.loads(Path("tests/fixtures/upbit_closed_orders.json").read_text(encoding="utf-8"))

    events = parse_upbit_closed_orders(rows)

    assert events[0].provider == "upbit"
    assert events[0].provider_event_id == "order-1:trade-1"
    assert events[0].event_type == "buy"
    assert events[0].asset_symbol == "BTC"
    assert events[0].cash_flow_krw < 0
    assert events[0].fee_krw > 0
```

Fixture에는 `uuid`, `market`, `side`, `paid_fee`, `trades[].uuid`, `trades[].price`, `trades[].volume`, `trades[].funds`, `trades[].created_at`을 포함한다.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_upbit_transactions.py -q`

Expected: FAIL because `parse_upbit_closed_orders` does not exist

- [ ] **Step 3: 조회와 파서 구현**

`UpbitAccountClient`에 다음 메서드를 추가한다.

```python
def list_closed_orders(self, start_time: str, end_time: str, page: int = 1, limit: int = 100) -> list[dict]:
    query = {
        "start_time": start_time,
        "end_time": end_time,
        "page": str(page),
        "limit": str(limit),
        "order_by": "asc",
    }
    headers = {"Authorization": f"Bearer {self._jwt_token(query)}"}
    response = requests.get("https://api.upbit.com/v1/orders/closed", headers=headers, params=query, timeout=10)
    response.raise_for_status()
    return response.json()
```

같은 패턴으로 `list_deposits(page, limit)`와 `list_withdraws(page, limit)`를 추가한다. 조회 범위는 최대 7일 단위로 쪼개고, 결과 수가 `limit`보다 작아질 때까지 페이지를 넘긴다.

파서 규칙:

- 매수 `bid`: `cash_flow_krw = -(funds + fee)`
- 매도 `ask`: `cash_flow_krw = funds - fee`
- 매수 수량은 양수, 매도 수량은 음수
- 각 체결 trade UUID를 원장 고유 키에 포함
- KRW 입금·출금만 `external_cash_flow=True`
- 코인 입출금은 자산 이동 이벤트로 저장하되 외부 원화 현금흐름으로 계산하지 않음

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_upbit_transactions.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/providers/upbit.py tests/fixtures/upbit_*.json tests/test_upbit_transactions.py
git commit -m "Add Upbit transaction history adapter"
```

---

### Task 5: KIS 체결내역 어댑터 추가

**Files:**
- Create: `tests/fixtures/kis_daily_executions.json`
- Create: `tests/test_kis_transactions.py`
- Modify: `src/portfolio_watchdog/providers/kis.py`

- [ ] **Step 1: KIS 체결 파서 테스트 작성**

```python
# tests/test_kis_transactions.py
import json
from pathlib import Path

from portfolio_watchdog.providers.kis import parse_kis_daily_executions


def test_parse_kis_daily_executions_ignores_unfilled_orders() -> None:
    payload = json.loads(Path("tests/fixtures/kis_daily_executions.json").read_text(encoding="utf-8"))

    events = parse_kis_daily_executions(payload["output1"], {"360750": "TIGER_SP500"})

    assert len(events) == 1
    assert events[0].provider == "kis"
    assert events[0].provider_event_id == "20260606:001:12345"
    assert events[0].event_type == "buy"
    assert events[0].asset_symbol == "TIGER_SP500"
    assert events[0].quantity == 10
    assert events[0].cash_flow_krw == -120_000
```

Fixture에는 체결 수량이 있는 행과 미체결 행을 모두 넣는다. 필드는 `ord_dt`, `ord_gno_brno`, `odno`, `pdno`, `sll_buy_dvsn_cd`, `tot_ccld_qty`, `avg_prvs`, `tot_ccld_amt`를 사용한다.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_kis_transactions.py -q`

Expected: FAIL because `parse_kis_daily_executions` does not exist

- [ ] **Step 3: 조회와 파서 구현**

`KisDomesticStockClient`에 `get_daily_executions(start_date, end_date)`를 추가한다.

- API: KIS 개발자센터의 `주식일별주문체결조회`
- 연속 조회 키가 있으면 다음 페이지 요청
- 조회 결과가 비어 있거나 체결 수량이 0이면 이벤트 생성 안 함
- `sll_buy_dvsn_cd`를 매수·매도로 명시적으로 매핑
- 매수 수량은 양수, 매도 수량은 음수
- `broker_symbol -> config symbol` 매핑을 파서에 전달해 평가 스냅샷과 같은 canonical symbol을 저장
- 수수료·세금 필드가 응답에 있으면 반영하고 없으면 0으로 저장
- 계좌번호와 주문번호 원문은 SQLite의 로컬 고유 키 구성에만 사용

`provider_event_id`는 `{ord_dt}:{ord_gno_brno}:{odno}` 형식으로 만든다. KIS 응답은 장중 누적 체결값이 바뀔 수 있으므로 같은 ID를 다시 수집하면 원장의 수량·금액을 최신 값으로 갱신한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_kis_transactions.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/providers/kis.py tests/fixtures/kis_daily_executions.json tests/test_kis_transactions.py
git commit -m "Add KIS execution history adapter"
```

---

### Task 6: 수동 현금흐름과 원장 수집 오케스트레이션

**Files:**
- Create: `src/portfolio_watchdog/ledger/ingestion.py`
- Create: `tests/test_ledger_ingestion.py`
- Modify: `src/portfolio_watchdog/ledger/repository.py`

- [ ] **Step 1: 증분 수집과 수동 현금흐름 테스트 작성**

```python
# tests/test_ledger_ingestion.py
from datetime import datetime

from portfolio_watchdog.ledger.ingestion import add_manual_cash_flow
from portfolio_watchdog.ledger.repository import LedgerRepository


def test_manual_cash_flow_is_external_and_repeatable(tmp_path) -> None:
    repository = LedgerRepository(tmp_path / "watchdog.db")

    first = add_manual_cash_flow(
        repository,
        occurred_at=datetime(2026, 6, 6, 12, 0),
        amount_krw=1_000_000,
        memo="농협 현금 추가",
        idempotency_key="manual-20260606-1",
    )
    second = add_manual_cash_flow(
        repository,
        occurred_at=datetime(2026, 6, 6, 12, 0),
        amount_krw=1_000_000,
        memo="농협 현금 추가",
        idempotency_key="manual-20260606-1",
    )

    assert first is True
    assert second is False
    assert repository.list_events()[0].external_cash_flow is True
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_ingestion.py -q`

Expected: FAIL because `ledger.ingestion` does not exist

- [ ] **Step 3: 수집 서비스 구현**

`ingest_provider_events(repository, provider, stream, fetch_page)`는 다음을 보장한다.

- 마지막 성공 cursor 이후만 요청
- 페이지별 이벤트를 하나의 DB 트랜잭션으로 저장
- 페이지 저장 성공 후에만 cursor 갱신
- 같은 페이지 재실행 시 중복 없음
- 오류가 발생하면 cursor를 전진시키지 않음

수동 현금흐름은 `provider="manual"`, `event_type="deposit" | "withdrawal"`, `external_cash_flow=True`로 저장한다. memo는 로컬 테이블에만 보관하고 클라우드 payload에는 포함하지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_ingestion.py tests\test_ledger_repository.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/ledger/ingestion.py src/portfolio_watchdog/ledger/repository.py tests/test_ledger_ingestion.py
git commit -m "Add idempotent ledger ingestion"
```

---

### Task 7: 거래와 실제 보유 수량 대사

**Files:**
- Create: `src/portfolio_watchdog/ledger/reconciliation.py`
- Create: `tests/test_reconciliation.py`
- Modify: `src/portfolio_watchdog/models.py`

- [ ] **Step 1: 대사 결과 테스트 작성**

```python
# tests/test_reconciliation.py
from portfolio_watchdog.ledger.reconciliation import reconcile_asset_quantities


def test_reconciliation_flags_difference_over_tolerance() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"BTC": 1.0, "ETH": 2.0},
        transaction_quantity_deltas={"BTC": 0.1, "ETH": -0.5},
        actual_quantities={"BTC": 1.1, "ETH": 1.4},
        tolerance=0.00000001,
    )

    assert result.status == "reconciliation_required"
    assert result.differences == {"ETH": -0.1}


def test_reconciliation_accepts_rounding_difference() -> None:
    result = reconcile_asset_quantities(
        previous_quantities={"BTC": 1.0},
        transaction_quantity_deltas={"BTC": 0.1},
        actual_quantities={"BTC": 1.100000001},
        tolerance=0.00000001,
    )

    assert result.status == "reconciled"
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_reconciliation.py -q`

Expected: FAIL because reconciliation module does not exist

- [ ] **Step 3: 대사 결과 타입과 계산 구현**

```python
# src/portfolio_watchdog/models.py
@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    differences: dict[str, float]
    tolerance: float
```

```python
# src/portfolio_watchdog/ledger/reconciliation.py
from portfolio_watchdog.models import ReconciliationResult


def reconcile_asset_quantities(
    previous_quantities: dict[str, float],
    transaction_quantity_deltas: dict[str, float],
    actual_quantities: dict[str, float],
    tolerance: float,
) -> ReconciliationResult:
    symbols = previous_quantities.keys() | transaction_quantity_deltas.keys() | actual_quantities.keys()
    differences = {}
    for symbol in symbols:
        expected = previous_quantities.get(symbol, 0.0) + transaction_quantity_deltas.get(symbol, 0.0)
        difference = actual_quantities.get(symbol, 0.0) - expected
        if abs(difference) > tolerance:
            differences[symbol] = round(difference, 12)
    status = "reconciled" if not differences else "reconciliation_required"
    return ReconciliationResult(status, differences, tolerance)
```

거래 이벤트의 매수 수량은 양수, 매도 수량은 음수로 합산한다. 입출고·권리·배당 재투자처럼 조회 API만으로 설명할 수 없는 차이는 대사 차이로 남긴다. 대사 상태는 평가 스냅샷과 성과 결과에 저장하며, 대사 실패 기간의 성과 상태는 `provisional`이어야 한다. 총자산은 시장 가격으로 변하므로 입출금만으로 총액을 강제 대사하지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_reconciliation.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/ledger/reconciliation.py src/portfolio_watchdog/models.py tests/test_reconciliation.py
git commit -m "Add portfolio reconciliation"
```

---

### Task 8: TWR, 월간 수익률, 낙폭 계산

**Files:**
- Create: `src/portfolio_watchdog/performance/__init__.py`
- Create: `src/portfolio_watchdog/performance/twr.py`
- Create: `src/portfolio_watchdog/performance/risk.py`
- Create: `tests/test_performance.py`

- [ ] **Step 1: 현금흐름을 제거한 TWR 검증 테스트 작성**

```python
# tests/test_performance.py
from datetime import datetime

import pytest

from portfolio_watchdog.performance.risk import calculate_drawdowns
from portfolio_watchdog.performance.twr import ValuationPoint, calculate_twr


def test_twr_excludes_external_deposit() -> None:
    points = [
        ValuationPoint(datetime(2026, 6, 1), 1_000_000, 0, "reconciled"),
        ValuationPoint(datetime(2026, 6, 2), 1_200_000, 100_000, "reconciled"),
    ]

    result = calculate_twr(points)

    assert result.cumulative_return_pct == pytest.approx(10.0)
    assert result.status == "confirmed"


def test_twr_is_provisional_when_reconciliation_failed() -> None:
    points = [
        ValuationPoint(datetime(2026, 6, 1), 1_000_000, 0, "reconciled"),
        ValuationPoint(datetime(2026, 6, 2), 1_100_000, 0, "reconciliation_required"),
    ]

    assert calculate_twr(points).status == "provisional"


def test_drawdown_uses_running_peak() -> None:
    assert calculate_drawdowns([100, 120, 90, 108]) == [0, 0, -25, -10]
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_performance.py -q`

Expected: FAIL because performance modules do not exist

- [ ] **Step 3: 계산 구현**

```python
# src/portfolio_watchdog/performance/twr.py
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ValuationPoint:
    captured_at: datetime
    total_value_krw: float
    external_cash_flow_krw: float
    reconciliation_status: str


@dataclass(frozen=True)
class TwrResult:
    cumulative_return_pct: float | None
    period_returns_pct: list[float]
    status: str


def calculate_twr(points: list[ValuationPoint]) -> TwrResult:
    if len(points) < 2 or points[0].total_value_krw <= 0:
        return TwrResult(None, [], "insufficient_data")
    linked = 1.0
    returns: list[float] = []
    status = "confirmed"
    for previous, current in zip(points, points[1:]):
        period_return = (current.total_value_krw - current.external_cash_flow_krw) / previous.total_value_krw - 1
        linked *= 1 + period_return
        returns.append(period_return * 100)
        if current.reconciliation_status != "reconciled":
            status = "provisional"
    return TwrResult(round((linked - 1) * 100, 6), returns, status)
```

`monthly_return`은 월 첫 평가부터 월 마지막 평가까지 같은 계산을 사용한다. `calculate_drawdowns()`는 각 시점의 고점 대비 하락률을 백분율로 반환한다.

정확한 TWR를 위해 외부 현금흐름 발생 시점을 평가 구간 경계로 만든다. 현금흐름 직전·직후 평가값을 만들 수 없는 구간은 계산은 제공하되 `provisional`로 표시한다. 테스트의 `external_cash_flow_krw`는 현재 평가 시점 직전에 발생한 외부 현금흐름을 뜻한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_performance.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/performance tests/test_performance.py
git commit -m "Add TWR and drawdown calculations"
```

---

### Task 9: 목표 비중 버전과 혼합 벤치마크

**Files:**
- Create: `src/portfolio_watchdog/performance/benchmark.py`
- Create: `tests/test_benchmark.py`
- Modify: `src/portfolio_watchdog/ledger/schema.py`
- Modify: `src/portfolio_watchdog/ledger/repository.py`

- [ ] **Step 1: 목표 비중 적용 시점 테스트 작성**

```python
# tests/test_benchmark.py
from datetime import date

import pytest

from portfolio_watchdog.performance.benchmark import BenchmarkWeight, calculate_blended_benchmark


def test_blended_benchmark_uses_weights_effective_on_each_date() -> None:
    weights = [
        BenchmarkWeight(date(2026, 6, 1), "isa", 0.6, "sp500_krw"),
        BenchmarkWeight(date(2026, 6, 1), "coin", 0.3, "btc_krw"),
        BenchmarkWeight(date(2026, 6, 1), "cash", 0.1, "cash_zero"),
    ]
    returns = {"sp500_krw": 0.02, "btc_krw": -0.01, "cash_zero": 0.0}

    assert calculate_blended_benchmark(weights, returns) == pytest.approx(0.009)
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q`

Expected: FAIL because benchmark module does not exist

- [ ] **Step 3: 벤치마크 계산과 저장 구현**

```python
# src/portfolio_watchdog/performance/benchmark.py
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BenchmarkWeight:
    effective_from: date
    asset_group: str
    weight: float
    benchmark_symbol: str


def calculate_blended_benchmark(weights: list[BenchmarkWeight], returns: dict[str, float]) -> float:
    total_weight = sum(item.weight for item in weights)
    if abs(total_weight - 1.0) > 0.0001:
        raise ValueError("benchmark weights must sum to 1")
    return sum(item.weight * returns[item.benchmark_symbol] for item in weights)
```

SQLite에 `target_allocation_versions`와 `target_allocation_items` 테이블을 추가한다. 최초 버전은 기존 `config.yaml` 목표 비중을 ISA·코인·현금으로 합산해 저장한다. 과거 버전은 갱신하지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_benchmark.py tests\test_ledger_repository.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/performance/benchmark.py src/portfolio_watchdog/ledger/schema.py src/portfolio_watchdog/ledger/repository.py tests/test_benchmark.py
git commit -m "Add versioned blended benchmark"
```

---

### Task 10: 성과 서비스와 v2 비식별 payload

**Files:**
- Create: `src/portfolio_watchdog/performance/service.py`
- Create: `tests/test_performance_service.py`
- Modify: `src/portfolio_watchdog/dashboard_data.py`
- Modify: `tests/test_dashboard_data.py`
- Modify: `src/portfolio_watchdog/report_data.py`

- [ ] **Step 1: v2 payload 의미와 개인정보 테스트 작성**

```python
# tests/test_performance_service.py
import json

from portfolio_watchdog.cloud_contract import assert_cloud_safe
from portfolio_watchdog.dashboard_data import build_dashboard_payload_v2


def _performance_summary() -> dict:
    return {
        "generated_at": "2026-06-06T08:00:00",
        "total_value_krw": 1_000_000,
        "data_freshness": {
            "portfolio_status": "actual",
            "last_actual_at": "2026-06-06T08:00:00",
            "reconciliation_status": "reconciled",
        },
        "performance": {
            "cumulative_twr_pct": 10.0,
            "month_twr_pct": 2.0,
            "benchmark_return_pct": 8.0,
            "excess_return_pct": 2.0,
            "max_drawdown_pct": -5.0,
            "status": "confirmed",
        },
        "asset_groups": [
            {
                "asset_group": "isa",
                "value_krw": 600_000,
                "weight_percent": 60.0,
                "target_diff_percentage_points": 5.0,
            }
        ],
        "assets": [],
        "provider_status": [],
    }


def test_dashboard_payload_v2_separates_return_and_allocation() -> None:
    payload = build_dashboard_payload_v2(_performance_summary())

    assert payload["schema_version"] == "dashboard_payload_v2"
    assert payload["performance"]["cumulative_twr_pct"] == 10.0
    assert payload["performance"]["status"] == "confirmed"
    assert payload["asset_groups"][0]["weight_percent"] == 60.0
    assert payload["asset_groups"][0]["target_diff_percentage_points"] == 5.0
    assert payload["data_freshness"]["portfolio_status"] == "actual"

    assert_cloud_safe(payload)
    encoded = json.dumps(payload)
    assert "quantity" not in encoded
    assert "average_buy_price_krw" not in encoded
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_performance_service.py -q`

Expected: FAIL because `build_dashboard_payload_v2` does not exist

- [ ] **Step 3: 성과 요약과 payload 구현**

v2 payload 최상위 구조를 다음으로 고정한다.

```python
{
    "schema_version": "dashboard_payload_v2",
    "generated_at": "...",
    "total_value_krw": 0.0,
    "data_freshness": {
        "portfolio_status": "actual|estimated|stale|fallback",
        "last_actual_at": "...",
        "reconciliation_status": "reconciled|reconciliation_required",
    },
    "performance": {
        "cumulative_twr_pct": None,
        "month_twr_pct": None,
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        "max_drawdown_pct": None,
        "status": "confirmed|provisional|insufficient_data",
    },
    "asset_groups": [],
    "assets": [],
    "provider_status": [],
}
```

`asset_groups`와 `assets`는 평가액, 비중, 목표 편차 `%p`, 누계 평가손익률만 포함한다. 수량, 평단, 계좌·주문 식별자는 포함하지 않는다. `report_data.py`는 기존 trend를 유지하면서 `performance` 요약을 선택적으로 포함한다.

현재 내부 자산 유형 `equity`는 v2 클라우드 계약에서 `isa`로 변환한다. 원장과 거래 대사는 config symbol을 canonical symbol로 사용하며, KIS 종목코드가 v2 payload에 별도 자산처럼 나타나지 않아야 한다.

이번 계획에서는 v2 payload를 `snapshots/dashboard_v2_latest.json`에 원자적으로 저장하고 클라우드에는 아직 업로드하지 않는다. 현재 Vercel API와 `dashboard/latest.json`은 v1 전용이므로 그대로 유지한다. v2 전용 업로드 API와 Blob 경로는 후속 `watchdog-dashboard-v2-cloud-sync` 계획에서 추가한다.

- [ ] **Step 4: v1 호환성과 v2 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_dashboard_data.py tests\test_performance_service.py tests\test_report_data.py -q`

Expected: PASS, including existing `dashboard_payload_v1` tests

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/performance/service.py src/portfolio_watchdog/dashboard_data.py src/portfolio_watchdog/report_data.py tests/test_performance_service.py tests/test_dashboard_data.py
git commit -m "Add privacy-safe dashboard v2 performance payload"
```

---

### Task 11: CLI와 앱 동기화 흐름 연결

**Files:**
- Create: `tests/test_ledger_cli.py`
- Modify: `src/portfolio_watchdog/app.py`
- Modify: `src/portfolio_watchdog/cli.py`
- Modify: `.env.example`

- [ ] **Step 1: CLI 명령 테스트 작성**

```python
# tests/test_ledger_cli.py
from portfolio_watchdog.cli import build_parser


def test_ledger_commands_are_registered() -> None:
    parser = build_parser()

    assert parser.parse_args(["sync-ledger"]).command == "sync-ledger"
    cash = parser.parse_args(
        [
            "add-cash-flow",
            "--amount",
            "1000000",
            "--occurred-at",
            "2026-06-06T12:00:00",
            "--memo",
            "cash",
        ]
    )
    assert cash.amount == 1_000_000
    assert parser.parse_args(["performance-summary"]).command == "performance-summary"
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_cli.py -q`

Expected: FAIL because parser construction is not exposed and commands are missing

- [ ] **Step 3: CLI와 앱 메서드 구현**

`cli.py`의 parser 생성부를 `build_parser()`로 분리하고 다음 명령을 추가한다.

```text
sync-ledger
add-cash-flow --amount <signed KRW> --occurred-at <ISO datetime> --memo <text>
performance-summary
```

`PortfolioWatchdogApp.sync_ledger()` 순서:

1. 기존 history JSON을 SQLite로 가져오기
2. Upbit·KIS 증분 거래 수집
3. 현재 포트폴리오 평가를 SQLite에 저장
4. 거래 변화와 실제 보유 수량 대사
5. 성과 계산
6. v2 비식별 payload를 `snapshots/dashboard_v2_latest.json`에 원자적으로 저장
7. 기존 v1 대시보드 동기화 흐름과 Blob 경로는 변경하지 않음

`performance-summary`는 API를 다시 호출하지 않고 SQLite의 최신 확정·잠정 성과를 콘솔에 출력한다.

`.env.example`에 선택 설정을 추가한다.

```text
WATCHDOG_LEDGER_PATH=snapshots/watchdog.db
```

`WATCHDOG_LEDGER_PATH`가 설정되면 YAML의 `ledger.path`보다 우선한다.
기존 `WATCHDOG_DASHBOARD_UPLOAD_URL`, `WATCHDOG_UPLOAD_TOKEN`은 v1 업로드에만 계속 사용한다.

- [ ] **Step 4: CLI와 전체 Python 테스트 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ledger_cli.py -q`

Expected: PASS

Run: `.\.venv\Scripts\python.exe -m pytest --basetemp build\pytest-tmp -o cache_dir=build\pytest-cache`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/app.py src/portfolio_watchdog/cli.py .env.example tests/test_ledger_cli.py
git commit -m "Connect ledger sync and performance CLI"
```

---

### Task 12: 실제 계좌 수집 스케줄 추가

**Files:**
- Modify: `src/portfolio_watchdog/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 4개 실제 계좌 동기화 작업 테스트로 변경**

```python
# tests/test_scheduler.py 추가 검증
ledger_calls = [call for call in create_calls if "PortfolioWatchdogLedger" in " ".join(call)]

assert len(ledger_calls) == 4
assert {call[call.index("/ST") + 1] for call in ledger_calls} == {
    "08:00",
    "12:00",
    "18:00",
    "22:00",
}
assert all("sync-ledger" in " ".join(call) for call in ledger_calls)
```

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q`

Expected: FAIL because only hourly news task exists

- [ ] **Step 3: 스케줄 구현**

`install_windows_schedule()`의 작업 목록에 다음 일일 작업을 추가한다.

```python
("PortfolioWatchdogLedger0800", "sync-ledger", "DAILY", "08:00", None),
("PortfolioWatchdogLedger1200", "sync-ledger", "DAILY", "12:00", None),
("PortfolioWatchdogLedger1800", "sync-ledger", "DAILY", "18:00", None),
("PortfolioWatchdogLedger2200", "sync-ledger", "DAILY", "22:00", None),
```

기존 전원 설정과 `StartWhenAvailable` 설정을 모든 작업에 적용한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q`

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add src/portfolio_watchdog/scheduler.py tests/test_scheduler.py
git commit -m "Schedule four daily ledger syncs"
```

---

### Task 13: 문서, 전체 회귀, 민감정보 검사

**Files:**
- Modify: `README.md`
- Create: `docs/operations/ledger-runbook.md`

- [ ] **Step 1: 운영 문서 작성**

`README.md`와 runbook에 다음 명령과 의미를 기록한다.

```powershell
python -m portfolio_watchdog sync-ledger
python -m portfolio_watchdog add-cash-flow --amount 1000000 --occurred-at 2026-06-06T12:00:00 --memo "cash deposit"
python -m portfolio_watchdog performance-summary
python -m portfolio_watchdog install-schedule
```

runbook은 다음을 포함한다.

- SQLite 위치와 백업 방법
- `confirmed`, `provisional`, `insufficient_data` 의미
- `actual`, `estimated`, `stale`, `fallback` 의미
- 대사 실패 확인 순서
- 수동 현금흐름 수정 절차
- 클라우드 금지 필드 목록
- API 호출 전 fixture 갱신 절차

- [ ] **Step 2: Python 전체 테스트**

Run: `.\.venv\Scripts\python.exe -m pytest --basetemp build\pytest-tmp -o cache_dir=build\pytest-cache`

Expected: PASS

- [ ] **Step 3: 기존 대시보드 회귀 테스트**

Run: `npm --prefix dashboard test`

Expected: PASS

Run: `npm --prefix dashboard run build`

Expected: successful Next.js production build

- [ ] **Step 4: 클라우드 payload 민감정보 검사**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cloud_contract.py tests\test_dashboard_data.py tests\test_performance_service.py -q
```

Expected: PASS

Run:

```powershell
rg -n '"(quantity|current_quantity|average_buy_price_krw|account_no|order_id|uuid|api_key|secret_key)"' dashboard/src/data reports
```

Expected: 샘플 또는 로컬 리포트 원본 외에는 클라우드 업로드용 payload에서 발견되지 않음. 발견 항목은 업로드 경로에 도달하는지 수동 확인한다.

- [ ] **Step 5: 실제 API 안전 점검**

실제 계정 호출은 아래 조건을 모두 확인한 뒤 한 번만 수동 실행한다.

1. Upbit와 KIS 키가 로컬 `.env`에만 있음
2. 거래·입출금 조회 전용이며 주문 API를 호출하지 않음
3. SQLite 백업 생성 완료
4. 첫 동기화 범위를 최근 7일로 제한
5. 동기화 후 원장 이벤트 수와 현재 평가액을 수동 대조

Run: `.\.venv\Scripts\python.exe -m portfolio_watchdog sync-ledger`

Expected: 신규 이벤트 수, 대사 상태, 성과 상태가 출력되며 주문은 발생하지 않음

- [ ] **Step 6: 최종 커밋**

```powershell
git add README.md docs/operations/ledger-runbook.md
git commit -m "Document ledger and performance operations"
```

---

## 완료 조건

- 기존 `dashboard_payload_v1`과 현재 대시보드가 계속 동작한다.
- 민감 필드가 포함된 payload는 네트워크 요청 전에 실패한다.
- SQLite 원장에 같은 거래를 여러 번 수집해도 중복되지 않는다.
- 기존 JSON 평가 이력을 삭제하지 않고 SQLite로 가져올 수 있다.
- Upbit·KIS 거래 수집 어댑터가 fixture 기반 테스트를 통과한다.
- 수동 현금흐름이 외부 현금흐름으로 TWR에 반영된다.
- 대사 실패 기간은 확정 성과로 표시되지 않는다.
- 누적 TWR, 당월 TWR, 낙폭, 혼합 벤치마크 결과를 계산할 수 있다.
- v2 payload에서 비중 `%`, 목표 편차 `%p`, TWR `%`, 평가손익률 `%`가 분리된다.
- Windows 작업 스케줄러에 08:00, 12:00, 18:00, 22:00 동기화 작업이 등록된다.
- Python 전체 테스트, 대시보드 테스트, Next.js build가 통과한다.
