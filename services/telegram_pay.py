from aiogram import Bot
from aiogram.types import LabeledPrice


async def send_telegram_invoice(bot: Bot, chat_id: int, title: str, description: str, payload: str, provider_token: str, amount_rub: int) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=provider_token,
        currency='RUB',
        prices=[LabeledPrice(label=title, amount=amount_rub * 100)],
        start_parameter='shop-balance-topup',
    )
