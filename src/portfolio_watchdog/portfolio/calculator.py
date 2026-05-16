from typing import Dict, List

from ..config import AssetConfig
from ..models import AssetEvaluation, PortfolioEvaluation, PriceQuote


def evaluate_portfolio(assets: List[AssetConfig], prices: Dict[str, PriceQuote]) -> PortfolioEvaluation:
    evaluations: List[AssetEvaluation] = []
    total = 0.0
    for asset in assets:
        quote = prices.get(asset.symbol)
        value = asset.manual_value_krw or 0.0
        if asset.asset_type == "coin" and quote is not None and asset.current_quantity is not None:
            value = asset.current_quantity * quote.price_krw
        elif value <= 0 and asset.current_quantity is not None and asset.average_buy_price_krw is not None:
            value = asset.current_quantity * asset.average_buy_price_krw
        total += value
        avg = asset.average_buy_price_krw
        profit_rate = asset.profit_loss_rate_pct
        profit_krw = asset.profit_loss_krw
        if avg and asset.current_quantity:
            cost = avg * asset.current_quantity
            if cost > 0:
                profit_krw = value - cost
                profit_rate = profit_krw / cost * 100
        evaluations.append(
            AssetEvaluation(
                symbol=asset.symbol,
                name=asset.name,
                asset_type=asset.asset_type,
                target_weight=asset.target_weight,
                current_quantity=asset.current_quantity,
                manual_value_krw=asset.manual_value_krw,
                average_buy_price_krw=avg,
                profit_loss_krw=profit_krw,
                profit_loss_rate_pct=profit_rate,
                alert_threshold_percent=asset.alert_threshold_percent or 0.0,
                current_value_krw=value,
                price_quote=quote,
            )
        )
    for item in evaluations:
        item.current_weight = item.current_value_krw / total if total else 0.0
        item.weight_diff_pct = item.current_weight - item.target_weight
    return PortfolioEvaluation(assets=evaluations, total_value_krw=total)
