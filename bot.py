from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import load_config
from database.base import SessionLocal, setup_database
from database.init_db import init_db
from handlers.admin import router as admin_router
from handlers.user import router as user_router
from middlewares.user_check import UserContextMiddleware
from services.crypto_pay import CryptoPayService
from utils.logger import setup_logging


async def main() -> None:
    setup_logging()
    config = load_config()
    if not config.bot_token:
        raise RuntimeError('BOT_TOKEN is not set')

    setup_database(config.database_url)
    await init_db()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    crypto = CryptoPayService(config.crypto_bot_token, config.crypto_bot_api_url)

    dp['config'] = config
    dp['crypto'] = crypto
    dp['db_sessionmaker'] = SessionLocal

    middleware = UserContextMiddleware()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(user_router)
    dp.include_router(admin_router)

    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
