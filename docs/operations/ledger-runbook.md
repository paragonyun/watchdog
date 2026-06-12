# Portfolio Watchdog 원장 운영 Runbook

## 기본 명령

```powershell
python -m portfolio_watchdog sync-ledger --sync-dashboard
python -m portfolio_watchdog add-cash-flow --amount 1000000 --occurred-at 2026-06-06T12:00:00 --memo "cash deposit"
python -m portfolio_watchdog performance-summary
python -m portfolio_watchdog install-schedule
```

`sync-ledger`는 조회 전용 API 수집, 현재 평가 저장, 보유수량 대사, 성과 계산, 로컬 v2 payload 저장을 순서대로 실행합니다. `--sync-dashboard`를 함께 사용하면 같은 v2 payload를 Vercel 대시보드에 업로드합니다. `performance-summary`는 API를 호출하지 않고 SQLite만 읽습니다.

## SQLite 위치와 백업

기본 경로는 `snapshots/watchdog.db`이며 `.env`의 `WATCHDOG_LEDGER_PATH`가 설정되면 우선합니다.

동기화 또는 수동 수정 전에는 Watchdog을 중지하고 DB와 WAL 파일을 함께 백업합니다.

```powershell
Copy-Item snapshots\watchdog.db snapshots\watchdog.backup.db
Copy-Item snapshots\watchdog.db-wal snapshots\watchdog.backup.db-wal -ErrorAction SilentlyContinue
Copy-Item snapshots\watchdog.db-shm snapshots\watchdog.backup.db-shm -ErrorAction SilentlyContinue
```

복구 시에는 Watchdog을 중지한 상태에서 현재 DB 파일을 별도 보관하고 백업 파일을 원래 경로로 되돌립니다.

## 상태 의미

- `confirmed`: 필요한 평가값과 대사가 확인된 성과
- `provisional`: 대사 실패, fallback 평가, 또는 정확한 입출금 경계 평가값이 없는 잠정 성과
- `insufficient_data`: 성과 계산에 필요한 평가점이 부족한 상태
- `actual`: 실제 API 평가값
- `estimated`: 추정 평가값
- `stale`: 최신성이 부족한 평가값
- `fallback`: API 실패 후 설정값 등 대체 데이터를 사용한 평가값

## 대사 실패 확인 순서

1. `python -m portfolio_watchdog performance-summary`에서 `reconciliation_status`를 확인합니다.
2. 최신 두 개의 실제 `portfolio` 스냅샷 사이 거래가 모두 수집됐는지 확인합니다.
3. Upbit/KIS API 오류와 fallback 여부를 확인합니다.
4. 매수 수량은 양수, 매도 수량은 음수인지 확인합니다.
5. 외부 입출금 또는 종목 이동이 누락됐다면 원인을 확인한 뒤 다시 `sync-ledger`를 실행합니다.
6. 원장 이벤트를 직접 삭제하거나 수정하기 전 DB를 백업합니다.

## 수동 현금흐름

입금은 양수, 출금은 음수로 입력합니다. 같은 금액·시각·메모를 다시 실행하면 결정론적 키로 중복 저장되지 않습니다.

잘못 입력한 수동 흐름은 먼저 DB를 백업한 뒤 해당 `provider='manual'` 이벤트를 확인합니다. 기존 이벤트를 직접 덮어쓰기보다 올바른 반대 방향 흐름을 새 메모로 추가해 감사 이력을 남기는 방식을 우선합니다.

## Legacy 이력 검증과 롤백

기존 `history.json`은 삭제하거나 변경하지 않습니다. 가져오기 결과는 다음 SQL로 확인합니다.

```sql
SELECT provider, data_status, COUNT(*) FROM account_snapshots
WHERE provider='legacy_history' GROUP BY provider,data_status;

SELECT COUNT(*) FROM asset_snapshots WHERE provider='legacy_history';
```

Legacy 가져오기만 롤백하려면 DB 백업 후 다음 트랜잭션을 실행합니다.

```sql
BEGIN IMMEDIATE;
DELETE FROM asset_snapshots WHERE provider='legacy_history';
DELETE FROM account_snapshots WHERE provider='legacy_history';
COMMIT;
```

## 클라우드 금지 필드

다음 정보는 v2 payload나 Vercel Blob에 업로드하지 않습니다.

- 수량과 현재 수량
- 평균 매입가
- 계좌번호와 계좌 상품 코드
- 주문번호, 주문 ID, UUID
- API 키, 앱 키, 비밀 키
- 원본 API 응답
- 거래 메모
- 원문 오류 상세

## Fixture와 실제 API 안전 점검

API 스키마가 변경되면 실제 계정 호출 전에 fixture와 파서 테스트를 먼저 갱신합니다.

실제 `sync-ledger` 최초 실행 전 확인 사항:

1. Upbit/KIS 키가 로컬 `.env`에만 있는지 확인
2. 주문 API가 아닌 잔고·거래·입출금 조회 API만 사용하는지 확인
3. SQLite 백업 완료
4. 최초 주문·체결 수집 범위가 최근 7일인지 확인
5. 실행 후 신규 이벤트 수, 현재 평가액, 대사 상태를 수동 대조

실제 API 호출 중 오류가 발생하면 재실행 전에 cursor와 최근 원장 이벤트를 확인합니다. 수집은 7일 겹침 구간과 멱등 upsert를 사용하므로 정상 재실행 시 중복 저장되지 않습니다.
