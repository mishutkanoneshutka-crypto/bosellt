from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database.base import SessionLocal
from database.crud import get_or_create_user


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)

        full_name = ' '.join(part for part in [user.first_name, user.last_name] if part)
        async with SessionLocal() as session:
            db_user = await get_or_create_user(session, user.id, user.username, full_name)

        if db_user.is_blocked:
            if isinstance(event, Message):
                await event.answer('Ваш аккаунт заблокирован. Обратитесь к администратору.')
            elif isinstance(event, CallbackQuery):
                await event.answer('Ваш аккаунт заблокирован.', show_alert=True)
            return None

        data['db_user'] = db_user
        return await handler(event, data)
