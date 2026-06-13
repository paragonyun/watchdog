from portfolio_watchdog.cli import build_parser


def test_news_risk_cli_commands_are_available() -> None:
    parser = build_parser()

    assert parser.parse_args(["collect-news-risks"]).command == "collect-news-risks"
    assert parser.parse_args(["merge-news-risks", "--path", "codex.json"]).command == "merge-news-risks"
    assert parser.parse_args(["sync-news-risks", "--path", "latest.json"]).command == "sync-news-risks"
