SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS schema_version_single_row ON schema_version ((1))",
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        total_value_krw REAL NOT NULL,
        data_status TEXT NOT NULL,
        UNIQUE(provider, captured_at)
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collection_cursors (
        provider TEXT NOT NULL,
        stream TEXT NOT NULL,
        cursor_value TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(provider, stream)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS target_allocation_versions (
        id INTEGER PRIMARY KEY,
        effective_from TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS target_allocation_items (
        version_id INTEGER NOT NULL,
        asset_group TEXT NOT NULL,
        target_weight REAL NOT NULL,
        benchmark_symbol TEXT NOT NULL,
        PRIMARY KEY(version_id, asset_group),
        FOREIGN KEY(version_id) REFERENCES target_allocation_versions(id) ON DELETE CASCADE
    )
    """,
)
