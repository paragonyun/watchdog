import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import requests

from ..config import AssetConfig
from .portfolio_provider import PortfolioProvider

logger = logging.getLogger(__name__)


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
