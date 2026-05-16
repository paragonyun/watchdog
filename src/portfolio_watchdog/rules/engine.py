from datetime import date
from typing import List, Optional

from ..config import AlertConfig, AssetConfig
from ..models import Alert, AssetEvaluation, PortfolioEvaluation
from ..repositories.base import SnapshotRepository


def _build_alert_key(rule: str, subject: str, alert_date: date) -> str:
    return f"{rule}:{subject}:{alert_date.isoformat()}"


class RuleEngine:
    def __init__(self, alert_config: AlertConfig, repository: SnapshotRepository, current_date: Optional[date] = None) -> None:
        self.alert_config = alert_config
        self.repository = repository
        self.current_date = current_date or date.today()
        self.seen_alert_keys = set(self.repository.load().get("alert_keys", []))

    def evaluate(self, portfolio: PortfolioEvaluation, assets: List[AssetConfig]) -> List[Alert]:
        _ = assets
        alerts: List[Alert] = []
        alerts.extend(self._evaluate_price_movements(portfolio.assets))
        alerts.extend(self._evaluate_weight_differences(portfolio.assets))
        coin_alert = self._evaluate_coin_weight(portfolio.assets)
        if coin_alert:
            alerts.append(coin_alert)
        alerts.extend(self._evaluate_data_health(portfolio.assets))
        new_alerts = [alert for alert in alerts if alert.key not in self.seen_alert_keys]
        if new_alerts:
            updated = self.seen_alert_keys.union({alert.key for alert in new_alerts})
            self.repository.save({"alert_keys": sorted(updated)})
            self.seen_alert_keys = updated
        return new_alerts

    def _evaluate_price_movements(self, evaluations: List[AssetEvaluation]) -> List[Alert]:
        alerts: List[Alert] = []
        for asset in evaluations:
            quote = asset.price_quote
            threshold = asset.alert_threshold_percent or self.alert_config.price_change_threshold_percent
            if quote is None or quote.change_pct_24h is None or abs(quote.change_pct_24h) < threshold:
                continue
            direction = "상승" if quote.change_pct_24h > 0 else "하락"
            alerts.append(Alert(key=_build_alert_key("price", asset.symbol, self.current_date), title=f"가격 급변 감지: {asset.symbol}", message=f"{asset.name}({asset.symbol}) 가격이 24시간 동안 {quote.change_pct_24h:.2f}% {direction}했습니다. 현재가 {quote.price_krw:,.0f} KRW, 임계값 {threshold:.1f}% 이상입니다.", severity="warning"))
        return alerts

    def _evaluate_weight_differences(self, evaluations: List[AssetEvaluation]) -> List[Alert]:
        alerts: List[Alert] = []
        for asset in evaluations:
            diff_pct = asset.weight_diff_pct * 100
            threshold = self.alert_config.weight_deviation_threshold_pct
            if abs(diff_pct) >= threshold:
                alerts.append(Alert(key=_build_alert_key("weight", asset.symbol, self.current_date), title=f"비중 이탈 감지: {asset.symbol}", message=f"{asset.name}({asset.symbol}) 현재 비중은 {asset.current_weight*100:.2f}%, 목표 비중 {asset.target_weight*100:.2f}% 대비 {diff_pct:+.2f}%p 차이입니다.", severity="warning"))
        return alerts

    def _evaluate_coin_weight(self, evaluations: List[AssetEvaluation]) -> Optional[Alert]:
        coin_total = sum(item.current_weight for item in evaluations if item.asset_type == "coin")
        if coin_total > self.alert_config.total_coin_weight_limit:
            return Alert(key=_build_alert_key("coin_weight", "total", self.current_date), title="코인 비중 과열 감지", message=f"전체 코인 비중이 {coin_total*100:.2f}%로 설정 상한 {self.alert_config.total_coin_weight_limit*100:.0f}%를 초과했습니다.", severity="warning")
        return None

    def _evaluate_data_health(self, evaluations: List[AssetEvaluation]) -> List[Alert]:
        alerts: List[Alert] = []
        missing = [item.symbol for item in evaluations if item.asset_type == "coin" and item.price_quote is None]
        if missing:
            alerts.append(Alert(key=_build_alert_key("data", "missing_prices", self.current_date), title="데이터 조회 경고", message=f"다음 코인 가격을 가져오지 못했습니다: {', '.join(missing)}.", severity="warning"))
        fallback = [item.symbol for item in evaluations if item.asset_type == "coin" and item.price_quote is not None and item.price_quote.source == "fallback"]
        if fallback:
            alerts.append(Alert(key=_build_alert_key("data", "fallback_prices", self.current_date), title="데이터 조회 경고", message=f"다음 코인은 실시간 가격 조회에 실패해 fallback 가격을 사용했습니다: {', '.join(fallback)}.", severity="warning"))
        return alerts
