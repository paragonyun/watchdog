from typing import Any


FORBIDDEN_CLOUD_FIELDS = {
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


def assert_cloud_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if isinstance(key, str) and key.lower() in FORBIDDEN_CLOUD_FIELDS:
                raise ValueError(f"forbidden cloud field: {item_path}")
            assert_cloud_safe(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_cloud_safe(item, f"{path}[{index}]")
