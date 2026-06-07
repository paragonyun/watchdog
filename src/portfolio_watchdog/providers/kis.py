import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List

import requests

from ..config import AssetConfig
from ..ledger.models import LedgerEvent
from .portfolio_provider import PortfolioProvider

logger = logging.getLogger(__name__)
MAX_DAILY_EXECUTION_PAGES = 1000
KST = timezone(timedelta(hours=9), "Asia/Seoul")


def _kis_required_text(row: Dict, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"KIS {field} is required")
    return value


def _kis_number(row: Dict, field: str) -> Decimal:
    try:
        value = Decimal(str(row[field]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"KIS {field} must be numeric") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"KIS {field} must be a non-negative finite number")
    return value


def _kis_occurred_at(row: Dict) -> datetime:
    ord_dt = _kis_required_text(row, "ord_dt")
    time_value = next(
        (row[field] for field in ("ccld_tmd", "ccld_time", "ord_tmd") if row.get(field)),
        "000000",
    )
    try:
        local = datetime.strptime(f"{ord_dt}{time_value}", "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except (TypeError, ValueError) as exc:
        raise ValueError("KIS ord_dt and execution time must use YYYYMMDD and HHMMSS") from exc
    return local.astimezone(timezone.utc)


def _kis_fee(row: Dict) -> Decimal:
    fee = Decimal("0")
    for field, raw_value in row.items():
        normalized = field.lower()
        if not any(token in normalized for token in ("fee", "tax", "cmsn", "tlex")):
            continue
        if raw_value in ("", None):
            continue
        fee += _kis_number(row, field)
    return fee


def parse_kis_daily_executions(
    rows: list[dict], broker_symbol_to_symbol: Dict[str, str]
) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    for row in rows:
        quantity = _kis_number(row, "tot_ccld_qty")
        if quantity == 0:
            continue
        unit_price = _kis_number(row, "avg_prvs")
        amount = _kis_number(row, "tot_ccld_amt")
        if quantity * unit_price != amount:
            raise ValueError("KIS tot_ccld_amt must equal tot_ccld_qty * avg_prvs")

        broker_symbol = _kis_required_text(row, "pdno")
        try:
            asset_symbol = broker_symbol_to_symbol[broker_symbol]
        except KeyError as exc:
            raise ValueError(f"KIS pdno has no canonical symbol mapping: {broker_symbol}") from exc
        side = _kis_required_text(row, "sll_buy_dvsn_cd")
        if side not in {"01", "02"}:
            raise ValueError("KIS sll_buy_dvsn_cd must be 01 or 02")

        fee = _kis_fee(row)
        is_buy = side == "02"
        events.append(
            LedgerEvent(
                provider="kis",
                provider_event_id=":".join(
                    (
                        _kis_required_text(row, "ord_dt"),
                        _kis_required_text(row, "ord_gno_brno"),
                        _kis_required_text(row, "odno"),
                    )
                ),
                occurred_at=_kis_occurred_at(row),
                event_type="buy" if is_buy else "sell",
                asset_symbol=asset_symbol,
                cash_flow_krw=float(-(amount + fee) if is_buy else amount - fee),
                quantity=float(quantity if is_buy else -quantity),
                unit_price_krw=float(unit_price),
                fee_krw=float(fee),
            )
        )
    return events


class KisTokenClient:
    def __init__(self, app_key: str, app_secret: str, env: str = "real", token_cache_path: str = "snapshots/kis_token.json") -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self.token_cache_path = Path(token_cache_path)
        self.base_url = "https://openapi.koreainvestment.com:9443" if env == "real" else "https://openapivts.koreainvestment.com:29443"

    def get_access_token(self) -> str:
        cached = self._load_cached_token()
        if cached:
            return cached
        response = requests.post(
            f"{self.base_url}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_cache_path.write_text(
            json.dumps({"access_token": token, "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in - 300)).isoformat()}, ensure_ascii=False),
            encoding="utf-8",
        )
        return token

    def _load_cached_token(self):
        if not self.token_cache_path.exists():
            return None
        try:
            data = json.loads(self.token_cache_path.read_text(encoding="utf-8"))
            if datetime.fromisoformat(data["expires_at"]) > datetime.utcnow():
                return data["access_token"]
        except Exception:
            return None
        return None


class KisDomesticStockClient:
    def __init__(self, token_client: KisTokenClient, account_no: str, account_product_code: str) -> None:
        self.token_client = token_client
        self.account_no = account_no
        self.account_product_code = account_product_code

    def get_balance(self) -> List[Dict]:
        token = self.token_client.get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.token_client.app_key,
            "appsecret": self.token_client.app_secret,
            "tr_id": "TTTC8434R" if self.token_client.env == "real" else "VTTC8434R",
        }
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        response = requests.get(
            f"{self.token_client.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("output1", [])

    def get_daily_executions(self, start_date: str, end_date: str) -> List[Dict]:
        if any(
            not isinstance(value, str) or len(value) != 8 or not value.isdigit()
            for value in (start_date, end_date)
        ):
            raise ValueError("start_date and end_date must use YYYYMMDD")
        try:
            start = datetime.strptime(start_date, "%Y%m%d")
            end = datetime.strptime(end_date, "%Y%m%d")
        except (TypeError, ValueError) as exc:
            raise ValueError("start_date and end_date must use YYYYMMDD") from exc
        if start > end:
            raise ValueError("start_date must not be after end_date")
        if end - start > timedelta(days=90):
            raise ValueError("date range must not exceed 90 days")

        token = self.token_client.get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.token_client.app_key,
            "appsecret": self.token_client.app_secret,
            "tr_id": "TTTC0081R" if self.token_client.env == "real" else "VTTC0081R",
            "tr_cont": "",
        }
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "INQR_STRT_DT": start_date,
            "INQR_END_DT": end_date,
            "SLL_BUY_DVSN_CD": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "INQR_DVSN": "00",
            "INQR_DVSN_3": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "EXCG_ID_DVSN_CD": "KRX",
        }
        rows: List[Dict] = []
        seen_cursors = {("", "")}
        for _ in range(MAX_DAILY_EXECUTION_PAGES):
            response = requests.get(
                f"{self.token_client.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=headers.copy(),
                params=params.copy(),
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            output = payload.get("output1") if isinstance(payload, dict) else None
            if not isinstance(output, list):
                raise ValueError("KIS output1 must be a list")
            rows.extend(output)

            tr_cont = response.headers.get("tr_cont", "")
            if tr_cont not in {"M", "F"}:
                return rows
            cursor = (
                str(payload.get("ctx_area_fk100") or payload.get("CTX_AREA_FK100") or ""),
                str(payload.get("ctx_area_nk100") or payload.get("CTX_AREA_NK100") or ""),
            )
            if cursor in seen_cursors or not all(cursor):
                raise RuntimeError("KIS repeated or missing continuation cursor")
            seen_cursors.add(cursor)
            params["CTX_AREA_FK100"], params["CTX_AREA_NK100"] = cursor
            headers["tr_cont"] = "N"
        raise RuntimeError("KIS daily execution page limit reached")


class KisPortfolioProvider(PortfolioProvider):
    def __init__(self, base_provider: PortfolioProvider, stock_client: KisDomesticStockClient, fallback_to_config: bool) -> None:
        self.base_provider = base_provider
        self.stock_client = stock_client
        self.fallback_to_config = fallback_to_config
        self.used_fallback = False
        self.last_error = None

    def get_assets(self) -> List[AssetConfig]:
        base_assets = self.base_provider.get_assets()
        self.used_fallback = False
        self.last_error = None
        try:
            rows = self.stock_client.get_balance()
        except Exception as exc:
            self.used_fallback = self.fallback_to_config
            self.last_error = str(exc)
            logger.warning("KIS balance lookup failed: %s", exc)
            if self.fallback_to_config:
                return base_assets
            raise
        by_code = {str(row.get("pdno", "")).upper(): row for row in rows}
        result: List[AssetConfig] = []
        for asset in base_assets:
            row = by_code.get((asset.broker_symbol or "").upper())
            if asset.asset_type == "equity" and row:
                qty = float(row.get("hldg_qty", 0) or 0)
                value = float(row.get("evlu_amt", 0) or 0)
                avg = float(row.get("pchs_avg_pric", 0) or 0)
                profit_krw = float(row.get("evlu_pfls_amt", 0) or 0)
                profit_rate = float(row.get("evlu_pfls_rt", 0) or 0)
                result.append(
                    AssetConfig(
                        **{
                            **asset.__dict__,
                            "current_quantity": qty,
                            "manual_value_krw": value,
                            "average_buy_price_krw": avg,
                            "profit_loss_krw": profit_krw,
                            "profit_loss_rate_pct": profit_rate,
                        }
                    )
                )
            else:
                result.append(asset)
        return result
