from portfolio_watchdog.config import AssetConfig
from portfolio_watchdog.portfolio.calculator import evaluate_portfolio


def test_equity_manual_value_is_not_overwritten_by_average_buy_price() -> None:
    portfolio = evaluate_portfolio(
        [
            AssetConfig(
                symbol="TIGER_SP500",
                name="TIGER S&P500",
                asset_type="equity",
                current_quantity=10,
                manual_value_krw=12_000,
                average_buy_price_krw=1_000,
                profit_loss_rate_pct=20,
            )
        ],
        {},
    )

    asset = portfolio.assets[0]
    assert asset.current_value_krw == 12_000
    assert asset.profit_loss_krw == 2_000
    assert asset.profit_loss_rate_pct == 20
