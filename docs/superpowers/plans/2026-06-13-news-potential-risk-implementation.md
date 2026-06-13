# News Potential Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최근 72시간 RSS와 Codex 심층 분석을 보유 자산 직접 리스크와 시장 전반 잠재 리스크로 분류해 기존 리스크 화면에 안전하게 표시한다.

**Architecture:** Python Watchdog은 RSS 뉴스와 현재 포트폴리오 비중을 사용해 `news_risk_payload_v1`을 생성하고, 별도 `codex_news_risk_v1` 파일을 검증·병합한 뒤 기존 `/api/upload`로 전송한다. Next.js는 뉴스 리스크 전용 Private Blob을 독립적으로 읽고, 현재 수치 리스크 아래에 2열 데스크톱·1열 모바일 섹션을 렌더링한다. 뉴스 수집 실패는 자산 동기화와 기존 리스크 화면을 막지 않는다.

**Tech Stack:** Python 3.11, pytest, argparse, requests, Next.js App Router, React 19, TypeScript, Node test runner, Vercel Blob

---

## Scope And File Map

| 파일 | 책임 |
| --- | --- |
| `src/portfolio_watchdog/news_analysis.py` | 시장 잠재 위험 RSS 검색어 제공 |
| `src/portfolio_watchdog/news_risk.py` | 후보 판정, 사건 식별, 점수, 병합, payload 검증·저장 |
| `src/portfolio_watchdog/app.py` | 수집·병합·업로드 애플리케이션 흐름 |
| `src/portfolio_watchdog/cli.py` | 뉴스 리스크 전용 CLI 명령 |
| `src/portfolio_watchdog/scheduler.py` | 시간별 뉴스 리스크 갱신 작업 |
| `tests/test_news_risk.py` | Python 규칙·병합·보안 계약 테스트 |
| `tests/test_news_risk_cli.py` | 뉴스 리스크 CLI 파서 테스트 |
| `tests/test_weekly_report.py` | 앱 수집·병합·업로드 흐름 테스트 |
| `tests/test_scheduler.py` | 시간별 스케줄 테스트 |
| `dashboard/src/lib/news-risk-payload.ts` | TypeScript 계약과 런타임 검증 |
| `dashboard/src/lib/news-risk-view.ts` | 정렬, 건수, 표시용 상태 계산 |
| `dashboard/src/lib/storage.ts` | 뉴스 리스크 Blob 읽기·쓰기 |
| `dashboard/src/app/api/upload/route.ts` | 뉴스 리스크 payload 업로드 허용 |
| `dashboard/src/app/risk/page.tsx` | 기존 수치 리스크 아래 뉴스 리스크 표시 |
| `dashboard/src/app/globals.css` | 데스크톱·모바일 뉴스 리스크 스타일 |
| `dashboard/tests/news-risk-payload.test.ts` | 웹 계약 검증 테스트 |
| `dashboard/tests/news-risk-view.test.ts` | 웹 표시 모델 테스트 |
| `dashboard/tests/storage.test.ts` | 뉴스 리스크 Blob 키 테스트 |
| `README.md` | 운영 명령과 데이터 갱신 방식 |

`news_risk.py`는 외부 API 호출을 하지 않는다. 입력을 구조화된 payload로 변환하는 순수 로직과 파일 저장만 담당한다. RSS 호출과 대시보드 업로드는 기존 애플리케이션·업로드 경로를 재사용한다.

### Task 1: RSS 뉴스에서 설명 가능한 잠재 리스크 생성

**Files:**
- Create: `src/portfolio_watchdog/news_risk.py`
- Modify: `src/portfolio_watchdog/news_analysis.py`
- Create: `tests/test_news_risk.py`

- [ ] **Step 1: 후보 판정, 영역 분리, 점수 계산 실패 테스트 작성**

`tests/test_news_risk.py`에 다음 핵심 테스트를 작성한다.

```python
from datetime import datetime, timezone

from portfolio_watchdog.models import AssetEvaluation, NewsItem, PortfolioEvaluation
from portfolio_watchdog.news_risk import build_news_risk_payload


NOW = datetime(2026, 6, 13, 9, 0, tzinfo=timezone.utc)


def _portfolio() -> PortfolioEvaluation:
    return PortfolioEvaluation(
        assets=[
            AssetEvaluation(
                symbol="BTC",
                name="비트코인",
                asset_type="coin",
                target_weight=0.2,
                current_quantity=None,
                manual_value_krw=None,
                current_value_krw=20,
                current_weight=0.2,
            ),
            AssetEvaluation(
                symbol="TIGER_SP500",
                name="S&P500",
                asset_type="equity",
                target_weight=0.8,
                current_quantity=None,
                manual_value_krw=None,
                current_value_krw=80,
                current_weight=0.8,
            ),
        ],
        total_value_krw=100,
    )


def test_builds_direct_and_market_risks_but_excludes_positive_news() -> None:
    items = [
        NewsItem(
            title="비트코인 거래 제한 우려",
            summary="규제 강화 가능성",
            source="Reuters",
            url="https://example.com/btc",
            published_at=NOW,
            related_assets=["BTC"],
            impact="부정",
            reason="방향: 부정",
        ),
        NewsItem(
            title="연준 긴축 장기화 가능성",
            summary="국채금리 급등 위험",
            source="Federal Reserve",
            url="https://example.com/rates",
            published_at=NOW,
            related_assets=[],
            impact="중립",
            reason="시장 키워드: 금리 / 방향: 중립",
        ),
        NewsItem(
            title="S&P500 강세",
            summary="기업 실적 개선",
            source="Reuters",
            url="https://example.com/good",
            published_at=NOW,
            related_assets=["TIGER_SP500"],
            impact="긍정",
            reason="방향: 긍정",
        ),
    ]

    payload = build_news_risk_payload(items, _portfolio(), generated_at=NOW)

    assert [item["scope"] for item in payload["direct_risks"]] == ["direct"]
    assert [item["scope"] for item in payload["market_risks"]] == ["market"]
    assert all("강세" not in item["title"] for item in payload["direct_risks"] + payload["market_risks"])
    assert payload["direct_risks"][0]["related_asset_weight_pct"] == 20.0
    assert payload["direct_risks"][0]["priority_reasons"]
```

같은 파일에 다음 테스트를 추가한다.

```python
def test_risk_id_is_stable_when_title_and_source_url_change() -> None:
    first = NewsItem(title="비트코인 규제 우려", summary="", source="A", url="https://a.example", published_at=NOW, related_assets=["BTC"], impact="부정")
    second = NewsItem(title="비트코인 규제 강화 전망", summary="", source="B", url="https://b.example", published_at=NOW, related_assets=["BTC"], impact="부정")

    first_id = build_news_risk_payload([first], _portfolio(), generated_at=NOW)["direct_risks"][0]["risk_id"]
    second_id = build_news_risk_payload([second], _portfolio(), generated_at=NOW)["direct_risks"][0]["risk_id"]

    assert first_id == second_id


def test_priority_boundaries_are_explainable() -> None:
    item = NewsItem(
        title="비트코인 규제 거래 제한 보안 사고",
        summary="규제 강화와 거래 제한",
        source="Federal Reserve",
        url="https://example.com/risk",
        published_at=NOW,
        related_assets=["BTC"],
        impact="부정",
    )

    risk = build_news_risk_payload([item], _portfolio(), generated_at=NOW)["direct_risks"][0]

    assert risk["priority"] in {"urgent", "caution", "watch"}
    assert any("직접 관련" in reason for reason in risk["priority_reasons"])
```

- [ ] **Step 2: 테스트 실패 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_news_risk.py -q
```

Expected: `ModuleNotFoundError: No module named 'portfolio_watchdog.news_risk'`

- [ ] **Step 3: 시장 위험 검색어와 최소 규칙 엔진 구현**

`src/portfolio_watchdog/news_analysis.py`에 다음 함수를 추가한다.

```python
def risk_news_queries() -> List[str]:
    return [
        *default_news_queries(),
        "금리 국채 중앙은행 긴축",
        "물가 CPI 인플레이션",
        "달러 원화 환율 급등",
        "경기 둔화 침체 고용 악화",
        "금융 규제 가상자산 규제 거래 제한",
        "지정학 충돌 제재 무역 갈등",
        "시장 유동성 자금 유출 신용 위험",
    ]
```

`src/portfolio_watchdog/news_risk.py`에 정확히 다음 공개 함수를 구현한다.

- `build_news_risk_payload(items: Sequence[NewsItem], portfolio: PortfolioEvaluation, generated_at: datetime | None = None) -> dict[str, Any]`
- `stable_risk_id(topic: str, scope: str, assets: Sequence[str], asset_groups: Sequence[str]) -> str`

구현 규칙:

- `부정` 뉴스 또는 위험 키워드가 있는 `중립` 뉴스만 후보로 사용한다.
- 직접 관련 자산이 있으면 `direct`, 없고 시장 위험 범주가 자산군에 연결되면 `market`으로 분류한다.
- `equity`는 cloud payload에서 `isa`로 변환한다.
- `risk_id`는 `category|strongest risk signal|scope|sorted assets|sorted groups`를 정규화하고 SHA-256 앞 16자를 사용한다. 예를 들어 같은 BTC 규제 기사는 묶지만 BTC 보안 사고는 별도 사건으로 유지한다.
- 같은 `risk_id`를 가진 RSS 항목은 하나의 사건으로 묶고, 독립 출처 수와 반복 기사 수를 우선순위 점수에 반영한다.
- 설계 문서의 점수표와 임계값을 그대로 적용하고 `priority_reasons`에 실제 가점 이유를 기록한다.
- `source_links`에는 안전한 HTTP(S) URL만 포함한다.
- `first_seen_at`, `last_updated_at`, `freshness`는 입력 발행 시각과 생성 시각으로 계산한다.
- 결과는 우선순위 점수, 관련 비중, 최신 시각 순으로 정렬한다.

- [ ] **Step 4: 규칙 테스트 통과 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_news_risk.py -q
```

Expected: 모든 Task 1 테스트 PASS

- [ ] **Step 5: 커밋**

```powershell
git add -- src/portfolio_watchdog/news_analysis.py src/portfolio_watchdog/news_risk.py tests/test_news_risk.py
git commit -m "Add explainable news risk rules"
```

### Task 2: Codex 보강 병합, 검증, 원자적 저장

**Files:**
- Modify: `src/portfolio_watchdog/news_risk.py`
- Modify: `tests/test_news_risk.py`

- [ ] **Step 1: 병합·보안·상태 실패 테스트 작성**

`tests/test_news_risk.py`에 다음 테스트를 추가한다.

```python
import pytest

from portfolio_watchdog.news_risk import merge_codex_news_risks, save_news_risk_payload, validate_news_risk_payload


def test_codex_enriches_existing_risk_and_adds_new_event(tmp_path) -> None:
    base = build_news_risk_payload(
        [NewsItem(title="비트코인 규제 우려", summary="", source="Reuters", url="https://example.com/a", published_at=NOW, related_assets=["BTC"], impact="부정")],
        _portfolio(),
        generated_at=NOW,
    )
    risk_id = base["direct_risks"][0]["risk_id"]
    codex = {
        "schema_version": "codex_news_risk_v1",
        "generated_at": NOW.isoformat(),
        "risks": [
            {
                "risk_id": risk_id,
                "scope": "direct",
                "title": "비트코인 규제 우려",
                "category": "규제",
                "facts": ["당국이 규제 검토를 공식 발표"],
                "potential_impact": "거래 유동성 위축 가능성",
                "transmission_path": "거래 제한 → 유동성 축소 → 가격 변동성 확대",
                "related_assets": ["BTC"],
                "related_asset_groups": ["coin"],
                "watch_indicators": ["거래소 순유출"],
                "counter_evidence": ["아직 시행 일정은 없음"],
                "source_links": [{"title": "공식 발표", "url": "https://example.com/official"}],
                "change_reason": "공식 발표 확인",
            },
            {
                "risk_id": None,
                "scope": "market",
                "title": "달러 유동성 축소",
                "category": "유동성",
                "facts": ["달러 조달 비용 상승"],
                "potential_impact": "위험 자산 압력",
                "transmission_path": "달러 강세 → 위험 선호 약화",
                "related_assets": [],
                "related_asset_groups": ["isa", "coin"],
                "watch_indicators": ["달러 인덱스"],
                "counter_evidence": [],
                "source_links": [{"title": "Reuters", "url": "https://example.com/usd"}],
                "change_reason": None,
            },
        ],
    }

    merged = merge_codex_news_risks(base, codex, _portfolio(), merged_at=NOW)

    assert merged["direct_risks"][0]["facts"] == ["당국이 규제 검토를 공식 발표"]
    assert "codex_research" in merged["direct_risks"][0]["source_type"]
    assert len(merged["market_risks"]) == 1
    assert merged["codex_generated_at"] == NOW.isoformat()


def test_rejects_sensitive_fields_and_unsafe_urls(tmp_path) -> None:
    payload = build_news_risk_payload([], _portfolio(), generated_at=NOW)
    payload["direct_risks"] = [{"quantity": 1}]
    with pytest.raises(ValueError, match="forbidden cloud field"):
        validate_news_risk_payload(payload)

    codex = {
        "schema_version": "codex_news_risk_v1",
        "generated_at": NOW.isoformat(),
        "risks": [{
            "risk_id": None,
            "scope": "market",
            "title": "위험",
            "category": "유동성",
            "facts": ["사실"],
            "potential_impact": "영향",
            "transmission_path": "경로",
            "related_assets": [],
            "related_asset_groups": ["coin"],
            "watch_indicators": [],
            "counter_evidence": [],
            "source_links": [{"title": "bad", "url": "javascript:alert(1)"}],
            "change_reason": None,
        }],
    }
    merged = merge_codex_news_risks(build_news_risk_payload([], _portfolio(), generated_at=NOW), codex, _portfolio(), merged_at=NOW)
    assert merged["market_risks"][0]["source_links"] == []


def test_save_news_risk_payload_is_atomic(tmp_path) -> None:
    path = tmp_path / "news_risk_latest.json"
    payload = build_news_risk_payload([], _portfolio(), generated_at=NOW)
    save_news_risk_payload(payload, path)
    assert path.exists()
    assert '"schema_version": "news_risk_payload_v1"' in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: 병합 테스트 실패 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_news_risk.py -q
```

Expected: 새 병합·검증·저장 함수 import 실패

- [ ] **Step 3: 병합·검증·저장 구현**

`src/portfolio_watchdog/news_risk.py`에 정확히 다음 공개 함수를 추가한다.

- `merge_codex_news_risks(base_payload: dict[str, Any], codex_payload: dict[str, Any], portfolio: PortfolioEvaluation, merged_at: datetime | None = None) -> dict[str, Any]`
- `load_json_object(path: Path) -> dict[str, Any]`
- `validate_news_risk_payload(payload: dict[str, Any]) -> None`
- `validate_codex_news_risk_payload(payload: dict[str, Any]) -> None`
- `save_news_risk_payload(payload: dict[str, Any], path: Path) -> None`

구현 규칙:

- 기존 사건은 `risk_id`로 찾아 Codex 필드를 보강하고 `source_type`에 `codex_research`를 추가한다.
- 신규 사건은 연결 자산·자산군을 검증한 뒤 Watchdog이 `risk_id`, 관련 비중, 점수를 생성한다.
- Codex가 제목, 우선순위 의미, 전달 경로를 바꾸면 `change_reason`이 비어 있으면 거부한다.
- 최상위 상태는 `delayed > refresh_required > actual` 우선순위로 계산한다.
- `assert_cloud_safe`를 호출한 뒤 임시 파일과 `os.replace`로 원자 저장한다.
- URL은 `http://`와 `https://`만 허용하고 localhost, loopback, private IP, 사용자 정보 포함 URL은 제외한다.

- [ ] **Step 4: 병합·보안 테스트 통과 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_news_risk.py tests/test_cloud_contract.py -q
```

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add -- src/portfolio_watchdog/news_risk.py tests/test_news_risk.py
git commit -m "Add Codex news risk merge contract"
```

### Task 3: Watchdog 앱, CLI, 시간별 스케줄 연결

**Files:**
- Modify: `src/portfolio_watchdog/app.py`
- Modify: `src/portfolio_watchdog/cli.py`
- Modify: `src/portfolio_watchdog/scheduler.py`
- Create: `tests/test_news_risk_cli.py`
- Modify: `tests/test_weekly_report.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 앱 흐름과 CLI 파서 실패 테스트 작성**

`tests/test_weekly_report.py`에 다음 테스트를 추가한다.

```python
def test_collect_news_risks_saves_and_optionally_uploads(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(
        _app_config(tmp_path),
        env={
            "WATCHDOG_DASHBOARD_UPLOAD_URL": "https://example.com/api/upload",
            "WATCHDOG_UPLOAD_TOKEN": "token",
        },
    )
    output = tmp_path / "news_risk_latest.json"
    watchdog.config.news.snapshot_path = str(tmp_path / "news_state.json")
    monkeypatch.setattr(watchdog, "_evaluate_current_portfolio", lambda: ([], PortfolioEvaluation([], 0)))
    monkeypatch.setattr(app_module, "RssNewsProvider", lambda *args, **kwargs: type("Provider", (), {"get_market_summary": lambda self: []})())
    uploads = []
    monkeypatch.setattr(app_module, "upload_dashboard_payload", lambda payload, endpoint, token: uploads.append((payload, endpoint, token)) or {"ok": True})

    payload = watchdog.collect_news_risks(output, sync_dashboard=True)

    assert output.exists()
    assert payload["schema_version"] == "news_risk_payload_v1"
    assert uploads[0][1:] == ("https://example.com/api/upload", "token")


def test_merge_and_sync_news_risks(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(
        _app_config(tmp_path),
        env={
            "WATCHDOG_DASHBOARD_UPLOAD_URL": "https://example.com/api/upload",
            "WATCHDOG_UPLOAD_TOKEN": "token",
        },
    )
    base = tmp_path / "news_risk_latest.json"
    codex = tmp_path / "codex.json"
    base.write_text('{"schema_version":"news_risk_payload_v1","generated_at":"2026-06-13T09:00:00+00:00","lookback_hours":72,"rss_generated_at":"2026-06-13T09:00:00+00:00","codex_generated_at":null,"status":"actual","direct_risks":[],"market_risks":[]}', encoding="utf-8")
    codex.write_text('{"schema_version":"codex_news_risk_v1","generated_at":"2026-06-13T09:00:00+00:00","risks":[]}', encoding="utf-8")
    monkeypatch.setattr(watchdog, "_evaluate_current_portfolio", lambda: ([], PortfolioEvaluation([], 0)))
    uploads = []
    monkeypatch.setattr(app_module, "upload_dashboard_payload", lambda payload, endpoint, token: uploads.append(payload) or {"ok": True})

    merged = watchdog.merge_news_risks(codex, base, sync_dashboard=True)
    synced = watchdog.sync_news_risks(base)

    assert merged["schema_version"] == "news_risk_payload_v1"
    assert synced["schema_version"] == "news_risk_payload_v1"
    assert len(uploads) == 2
```

`tests/test_news_risk_cli.py`를 생성하고 다음 테스트를 추가한다.

```python
from portfolio_watchdog.cli import build_parser


def test_news_risk_cli_commands_are_available() -> None:
    parser = build_parser()
    assert parser.parse_args(["collect-news-risks"]).command == "collect-news-risks"
    assert parser.parse_args(["merge-news-risks", "--path", "codex.json"]).command == "merge-news-risks"
    assert parser.parse_args(["sync-news-risks", "--path", "latest.json"]).command == "sync-news-risks"
```

`tests/test_scheduler.py`는 작업 수가 6개가 되고 `PortfolioWatchdogNewsRiskHourly`가 `collect-news-risks --sync-dashboard`를 실행하는지 검증하도록 수정한다.

- [ ] **Step 2: 통합 테스트 실패 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_weekly_report.py tests/test_scheduler.py -q
```

Expected: 앱 메서드 및 CLI 명령 미구현으로 FAIL

- [ ] **Step 3: 앱 메서드와 CLI 명령 구현**

`PortfolioWatchdogApp`에 정확히 다음 메서드를 추가한다.

- `collect_news_risks(self, output_path: Path | None = None, sync_dashboard: bool = False) -> dict[str, object]`
- `merge_news_risks(self, codex_path: Path, output_path: Path | None = None, sync_dashboard: bool = False) -> dict[str, object]`
- `sync_news_risks(self, path: Path) -> dict[str, object]`

구현 규칙:

- 기본 출력 경로는 `config.news.snapshot_path`의 부모 아래 `news_risk_latest.json`이다.
- `collect_news_risks`는 `RssNewsProvider(config.assets, risk_news_queries(), 72, 60, 5)`를 직접 사용해 OpenAI API를 호출하지 않는다.
- 포트폴리오 평가는 기존 `_evaluate_current_portfolio()`를 재사용한다.
- 수집 예외 시 기존 파일이 있으면 `status=delayed`로 저장하고, 없으면 예외를 그대로 알린다.
- 업로드는 기존 `upload_dashboard_payload`와 기존 환경변수를 재사용한다.
- CLI `--output`은 수집·병합 결과 경로에도 사용한다.
- `merge-news-risks`와 `sync-news-risks`에는 `--path`가 필수다.

`scheduler.py`에 다음 작업을 추가한다.

```python
("PortfolioWatchdogNewsRiskHourly", "collect-news-risks --sync-dashboard", "HOURLY", "00:10", None),
```

- [ ] **Step 4: 앱·CLI·스케줄 테스트 통과 확인**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_weekly_report.py tests/test_scheduler.py tests/test_news_risk.py -q
```

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add -- src/portfolio_watchdog/app.py src/portfolio_watchdog/cli.py src/portfolio_watchdog/scheduler.py tests/test_weekly_report.py tests/test_scheduler.py tests/test_news_risk_cli.py
git commit -m "Connect news risk CLI and scheduler"
```

### Task 4: Next.js 뉴스 리스크 계약, 업로드, Private Blob 저장

**Files:**
- Create: `dashboard/src/lib/news-risk-payload.ts`
- Modify: `dashboard/src/lib/storage.ts`
- Modify: `dashboard/src/app/api/upload/route.ts`
- Create: `dashboard/tests/news-risk-payload.test.ts`
- Modify: `dashboard/tests/storage.test.ts`

- [ ] **Step 1: 웹 payload 검증 및 Blob 키 실패 테스트 작성**

`dashboard/tests/news-risk-payload.test.ts`를 생성한다.

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { validateNewsRiskPayload } from "../src/lib/news-risk-payload";

const valid = {
  schema_version: "news_risk_payload_v1",
  generated_at: "2026-06-13T09:00:00+00:00",
  lookback_hours: 72,
  rss_generated_at: "2026-06-13T09:00:00+00:00",
  codex_generated_at: null,
  status: "actual",
  direct_risks: [],
  market_risks: [],
};

test("accepts privacy-safe news risk payload", () => {
  assert.equal(validateNewsRiskPayload(valid), true);
});

test("rejects malformed or sensitive news risk payload", () => {
  assert.equal(validateNewsRiskPayload({ ...valid, status: "unknown" }), false);
  assert.equal(validateNewsRiskPayload({ ...valid, direct_risks: [{ quantity: 1 }] }), false);
});
```

`dashboard/tests/storage.test.ts`에 다음 테스트를 추가한다.

```typescript
import { NEWS_RISK_BLOB_KEY } from "../src/lib/storage";

test("news risk payload uses an independent private blob key", () => {
  assert.equal(NEWS_RISK_BLOB_KEY, "dashboard/news-risk-latest.json");
});
```

- [ ] **Step 2: 웹 계약 테스트 실패 확인**

Run:

```powershell
cd dashboard
npm test
```

Expected: `news-risk-payload` 및 `NEWS_RISK_BLOB_KEY` 미구현으로 FAIL

- [ ] **Step 3: TypeScript 계약과 업로드 분기 구현**

`dashboard/src/lib/news-risk-payload.ts`에 설계 문서와 동일한 `NewsRiskPayload`, `NewsRiskItem`, `NewsRiskPriority`, `NewsRiskStatus` 타입과 `validateNewsRiskPayload(value)`를 구현한다.

검증 규칙:

- 최상위 필수 필드와 enum 검증
- 각 위험의 필수 문자열·배열·유한 숫자 검증
- `source_links`는 HTTP(S) URL만 허용하고 localhost, loopback, private IP, 사용자 정보 포함 URL은 거부
- 기존 금지 필드 재귀 검사와 같은 목록 적용
- `direct_risks`에는 `scope=direct`, `market_risks`에는 `scope=market`만 허용

`dashboard/src/lib/storage.ts`에 다음 인터페이스를 추가한다.

```typescript
export const NEWS_RISK_BLOB_KEY = "dashboard/news-risk-latest.json";

export async function getLatestNewsRiskPayload(): Promise<NewsRiskPayload | null> {
  const value = await readBlobPayload(NEWS_RISK_BLOB_KEY);
  return validateNewsRiskPayload(value) ? value : null;
}

export async function saveLatestNewsRiskPayload(payload: NewsRiskPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(NEWS_RISK_BLOB_KEY, JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
}
```

`dashboard/src/app/api/upload/route.ts`는 기존 dashboard payload면 기존 저장 함수를, 뉴스 리스크 payload면 `saveLatestNewsRiskPayload`를 호출하고 둘 다 아니면 `invalid_dashboard_payload` 대신 `invalid_upload_payload`를 반환한다.

- [ ] **Step 4: 웹 계약·저장 테스트 통과 확인**

Run:

```powershell
cd dashboard
npm test
```

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add -- dashboard/src/lib/news-risk-payload.ts dashboard/src/lib/storage.ts dashboard/src/app/api/upload/route.ts dashboard/tests/news-risk-payload.test.ts dashboard/tests/storage.test.ts
git commit -m "Add news risk Blob contract"
```

### Task 5: 뉴스 리스크 표시 모델 구현

**Files:**
- Create: `dashboard/src/lib/news-risk-view.ts`
- Create: `dashboard/tests/news-risk-view.test.ts`

- [ ] **Step 1: 정렬·건수·상태 실패 테스트 작성**

`dashboard/tests/news-risk-view.test.ts`를 생성한다.

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { buildNewsRiskView } from "../src/lib/news-risk-view";
import type { NewsRiskPayload } from "../src/lib/news-risk-payload";

const payload = {
  schema_version: "news_risk_payload_v1",
  generated_at: "2026-06-13T09:00:00+00:00",
  lookback_hours: 72,
  rss_generated_at: "2026-06-13T09:00:00+00:00",
  codex_generated_at: null,
  status: "actual",
  direct_risks: [
    { risk_id: "watch", scope: "direct", priority: "watch", title: "관찰", category: "규제", source_type: ["rss_rule"], facts: [], potential_impact: "영향", transmission_path: "경로", related_assets: ["BTC"], related_asset_groups: ["coin"], related_asset_weight_pct: 10, watch_indicators: [], counter_evidence: [], priority_reasons: [], source_links: [], first_seen_at: "2026-06-12T09:00:00+00:00", last_updated_at: "2026-06-12T09:00:00+00:00", freshness: "active", change_reason: null },
    { risk_id: "urgent", scope: "direct", priority: "urgent", title: "긴급", category: "규제", source_type: ["codex_research"], facts: [], potential_impact: "영향", transmission_path: "경로", related_assets: ["BTC"], related_asset_groups: ["coin"], related_asset_weight_pct: 20, watch_indicators: [], counter_evidence: [], priority_reasons: [], source_links: [], first_seen_at: "2026-06-13T08:00:00+00:00", last_updated_at: "2026-06-13T08:00:00+00:00", freshness: "new", change_reason: null },
  ],
  market_risks: [],
} satisfies NewsRiskPayload;

test("sorts by priority and exposes summary counts", () => {
  const view = buildNewsRiskView(payload);
  assert.equal(view.direct[0].riskId, "urgent");
  assert.equal(view.newCount, 1);
  assert.equal(view.directCount, 2);
  assert.equal(view.marketCount, 0);
  assert.equal(view.needsRefresh, false);
});
```

- [ ] **Step 2: 표시 모델 테스트 실패 확인**

Run:

```powershell
cd dashboard
npm test
```

Expected: `news-risk-view` 미구현으로 FAIL

- [ ] **Step 3: 표시 모델 구현**

`dashboard/src/lib/news-risk-view.ts`에 다음 타입과 `buildNewsRiskView(payload: NewsRiskPayload): NewsRiskView` 공개 함수를 구현한다.

```typescript
export type NewsRiskViewItem = {
  riskId: string;
  priority: "urgent" | "caution" | "watch";
  priorityLabel: "긴급 확인" | "주의" | "관찰";
  title: string;
  category: string;
  relatedLabel: string;
  potentialImpact: string;
  transmissionPath: string;
  facts: string[];
  watchIndicators: string[];
  counterEvidence: string[];
  priorityReasons: string[];
  sourceLinks: Array<{ title: string; url: string }>;
  sourceLabels: string[];
  freshness: "new" | "active" | "refresh_required";
  changeReason: string | null;
};

export type NewsRiskView = {
  direct: NewsRiskViewItem[];
  market: NewsRiskViewItem[];
  directCount: number;
  marketCount: number;
  newCount: number;
  needsRefresh: boolean;
  codexGeneratedAt: string | null;
  status: "actual" | "delayed" | "refresh_required";
};

```

함수 구현은 `direct_risks`와 `market_risks`를 각각 표시 항목으로 변환하고, `directCount`, `marketCount`, `newCount`, `needsRefresh`, `codexGeneratedAt`, `status`를 계산해 반환한다. 정렬은 `urgent > caution > watch`, `new > active > refresh_required`, `related_asset_weight_pct` 내림차순을 적용한다. 한국어 우선순위와 출처 배지는 이 모듈에서 변환한다.

- [ ] **Step 4: 표시 모델 테스트 통과 확인**

Run:

```powershell
cd dashboard
npm test
```

Expected: PASS

- [ ] **Step 5: 커밋**

```powershell
git add -- dashboard/src/lib/news-risk-view.ts dashboard/tests/news-risk-view.test.ts
git commit -m "Add news risk presentation model"
```

### Task 6: 기존 리스크 화면 아래 뉴스 잠재 리스크 UI 추가

**Files:**
- Modify: `dashboard/src/app/risk/page.tsx`
- Modify: `dashboard/src/app/globals.css`

- [ ] **Step 1: 리스크 페이지에 독립 데이터 로드와 빈 상태 추가**

`dashboard/src/app/risk/page.tsx`에서 자산 payload와 뉴스 리스크 payload를 병렬로 읽는다.

```typescript
const [{ v1, v2 }, newsRiskPayload] = await Promise.all([
  getLatestDashboardPayloads(),
  getLatestNewsRiskPayload(),
]);
```

기존 수치 리스크 데이터가 없더라도 뉴스 리스크가 있으면 페이지 전체 빈 상태로 보내지 않는다. 기존 수치 리스크 섹션과 뉴스 리스크 섹션은 각각 독립 빈 상태를 표시한다.

- [ ] **Step 2: 뉴스 리스크 요약과 2열 목록 구현**

기존 수치 리스크 섹션 아래에 다음 구조를 추가한다.

```tsx
<section className="news-risk-section" aria-label="뉴스 기반 잠재 리스크">
  <header className="news-risk-heading">
    <div>
      <span>FORWARD RISK MONITOR</span>
      <h2>뉴스 기반 잠재 리스크</h2>
      <p>최근 72시간 뉴스에서 보유 자산으로 전달될 수 있는 위험을 별도로 표시합니다.</p>
    </div>
    <NewsRiskStatus view={newsRisk} />
  </header>
  <div className="news-risk-summary">
    <article><span>직접 리스크</span><strong>{newsRisk.directCount}건</strong></article>
    <article><span>시장 리스크</span><strong>{newsRisk.marketCount}건</strong></article>
    <article><span>최근 24시간 신규</span><strong>{newsRisk.newCount}건</strong></article>
  </div>
  <div className="news-risk-columns">
    <NewsRiskColumn title="보유 자산 직접 리스크" items={newsRisk.direct} />
    <NewsRiskColumn title="시장 전반 잠재 리스크" items={newsRisk.market} />
  </div>
</section>
```

각 열은 우선순위순 상위 5건을 펼쳐 표시하고, 나머지는 `<details>` 안에 넣는다. 각 카드의 기본 상태에는 우선순위, 신규 배지, 제목, 관련 자산·자산군, 예상 영향을 표시한다. 카드의 상세 `<details>`에는 사실, 전달 경로, 관찰 지표, 반대 근거, 점수 근거, 변경 이유, 출처 링크를 표시한다.

- [ ] **Step 3: 데스크톱·모바일 CSS 구현**

`dashboard/src/app/globals.css`에 다음 원칙으로 스타일을 추가한다.

- 데스크톱: 뉴스 리스크 영역은 최대 폭 1520px, 직접·시장 2열
- 모바일: 직접 리스크 먼저, 시장 리스크 다음의 1열
- 긴 제목·관련 자산 태그·출처 URL에 `overflow-wrap: anywhere`
- `urgent`, `caution`, `watch`는 기존 red/orange/green 토큰 사용
- 뉴스 영역은 기존 수치 리스크와 시각적으로 구분하되 별도 떠 있는 대형 카드로 만들지 않음
- 클릭 가능한 출처와 상세보기는 충분한 터치 영역 확보
- `refresh_required`와 `delayed` 상태는 상단 상태 문구로 표시

- [ ] **Step 4: 웹 테스트와 프로덕션 빌드 확인**

Run:

```powershell
cd dashboard
npm test
npm run build
```

Expected: 테스트 PASS, Next.js production build 성공

- [ ] **Step 5: 로컬 브라우저 QA**

Run:

```powershell
cd dashboard
npm run dev
```

Browser QA:

- 데스크톱 `1440x1000`: 뉴스 리스크 2열, 가로 넘침 없음
- 모바일 `390x844`: 직접 리스크 후 시장 리스크, 하단 내비게이션과 내용 겹침 없음
- 상세보기 열기·닫기 동작
- 긴 제목과 다수 관련 자산 표시
- 뉴스 Blob 없음, Codex 없음, `delayed`, `refresh_required` 상태
- 기존 수치 리스크 KPI와 패널 회귀 없음

- [ ] **Step 6: 커밋**

```powershell
git add -- dashboard/src/app/risk/page.tsx dashboard/src/app/globals.css
git commit -m "Show potential news risks on risk dashboard"
```

### Task 7: 운영 문서, 실제 데이터 생성, 배포 검증

**Files:**
- Modify: `README.md`
- Create: `docs/operations/news-risk-runbook.md`

- [ ] **Step 1: 운영 문서 작성**

`README.md`와 `docs/operations/news-risk-runbook.md`에 다음 명령을 정확히 기록한다.

```powershell
python -m portfolio_watchdog collect-news-risks --sync-dashboard
python -m portfolio_watchdog merge-news-risks --path snapshots/codex_news_risk.json --sync-dashboard
python -m portfolio_watchdog sync-news-risks --path snapshots/news_risk_latest.json
python -m portfolio_watchdog install-schedule
```

문서에는 다음을 명시한다.

- RSS 자동 분석은 OpenAI API 비용이 발생하지 않음
- Codex 분석은 정기 리포트·주요 분석 요청 시 생성
- 자산 API와 뉴스 RSS는 독립 실패 처리
- 뉴스 리스크는 매수·매도 추천이 아님
- Blob 키는 `dashboard/news-risk-latest.json`
- 수집 주기는 시간별, 자산 동기화는 기존 하루 4회 유지

- [ ] **Step 2: 전체 테스트 실행**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp build\pytest-tmp -o cache_dir=build\pytest-cache
cd dashboard
npm test
npm run build
```

Expected: Python 전체 테스트 PASS, Next.js 전체 테스트 PASS, production build 성공

- [ ] **Step 3: 실제 RSS 데이터로 로컬 payload 생성**

Run:

```powershell
.\.venv\Scripts\python.exe -m portfolio_watchdog collect-news-risks
```

검증:

- `snapshots/news_risk_latest.json` 생성
- 보유 자산 연결 근거 없는 일반 뉴스 제외
- 긍정 뉴스 제외
- 민감 필드 없음
- 출처 링크가 HTTP(S)만 포함

- [ ] **Step 4: Codex 심층 검색 결과 생성·병합**

최근 72시간의 한국은행·금융당국·거래소·Fed·기업 공시 등 1차 출처와 Reuters/Bloomberg 보조 출처를 검색한다. 결과를 `codex_news_risk_v1` 계약에 맞춰 로컬 `snapshots/codex_news_risk.json`에 저장하고 병합한다.

Run:

```powershell
.\.venv\Scripts\python.exe -m portfolio_watchdog merge-news-risks --path snapshots\codex_news_risk.json
```

검증:

- RSS 사건과 Codex 사건 중복 없음
- Codex 보강 사건에 사실·전달 경로·반대 근거·관찰 지표 존재
- 해석 변경 시 `change_reason` 존재

- [ ] **Step 5: 최종 변경 커밋 및 GitHub push**

```powershell
git add -- README.md docs/operations/news-risk-runbook.md
git commit -m "Document news risk operations"
git push origin main
```

- [ ] **Step 6: Vercel 배포 후 실제 payload 업로드**

GitHub push로 Vercel 배포가 완료된 뒤 실행한다.

```powershell
.\.venv\Scripts\python.exe -m portfolio_watchdog sync-news-risks --path snapshots\news_risk_latest.json
```

Expected: `/api/upload`가 `{ "ok": true }`를 반환하고 Private Blob `dashboard/news-risk-latest.json`이 갱신된다.

- [ ] **Step 7: 프로덕션 브라우저 QA**

`https://watchdog-398k.vercel.app/risk`에서 확인한다.

- 로그인 후 기존 수치 리스크와 뉴스 리스크가 함께 표시
- 데스크톱 2열과 모바일 1열 배치
- 상위 5건과 접힌 나머지 목록
- 출처 링크는 새 탭에서 안전하게 열림
- 콘솔 오류 및 런타임 경고 없음
- 뉴스 리스크 Blob이 없거나 잘못되어도 기존 수치 리스크는 정상 표시

## Post-Risk Continuation

뉴스 잠재 리스크 배포 검증 후 다음 기능을 각각 별도 설계·계획·검증 단위로 연속 진행한다.

1. **투자 의견:** 수치 리스크와 뉴스 잠재 리스크를 근거로 `관찰·유지·재검토` 의견을 제시하되 매수·매도 자동 추천은 하지 않는다.
2. **리포트:** 대시보드에서 최신 Markdown/PDF 리포트 목록과 본문·상세 부록을 조회한다.
3. **설정/운영 상태:** API 제공자 상태, 마지막 동기화, 스케줄 상태, Blob 갱신 상태를 확인한다. 비밀키 값은 표시하지 않는다.

각 후속 기능은 현재 뉴스 리스크 데이터 계약을 재사용하고, 완료 후 GitHub push·Vercel 배포·모바일 QA까지 수행한다.
