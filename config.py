from dataclasses import dataclass
import os
from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    database_url: str
    crypto_bot_token: str | None
    crypto_bot_api_url: str
    provider_token: str | None
    support_username: str | None
    shop_name: str
    web_admin_username: str
    web_admin_password: str


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(','):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


def load_config() -> Config:
    return Config(
        bot_token=os.getenv('BOT_TOKEN', ''),
        admin_ids=_parse_admin_ids(os.getenv('ADMIN_IDS', '')),
        database_url=os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///shop.db'),
        crypto_bot_token=os.getenv('CRYPTO_BOT_TOKEN') or None,
        crypto_bot_api_url=os.getenv('CRYPTO_BOT_API_URL', 'https://pay.crypt.bot/api'),
        provider_token=os.getenv('PROVIDER_TOKEN') or None,
        support_username=os.getenv('SUPPORT_USERNAME') or None,
        shop_name=os.getenv('SHOP_NAME', 'My Telegram Shop'),
        web_admin_username=os.getenv('WEB_ADMIN_USERNAME', 'admin'),
        web_admin_password=os.getenv('WEB_ADMIN_PASSWORD', 'admin123'),
    )
