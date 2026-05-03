from __future__ import annotations

from decimal import Decimal


def format_price(value: Decimal | int | float | str) -> str:
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    return f'{number:.2f}'
