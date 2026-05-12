from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from config import Config
import database.base as db

from database.crud import (
    add_to_cart,
    apply_promo_code,
    buy_cart,
    buy_product,
    calculate_discounted_price,
    clear_cart,
    create_payment,
    create_support_ticket,
    get_active_products,
    get_cart_items,
    get_categories,
    get_order,
    get_payment_by_external_id,
    get_product,
    get_product_stock,
    get_user,
    get_user_orders,
    get_user_payments,
    mark_payment_paid,
    remove_cart_item,
    set_referrer,
    update_cart_quantity,
)

from keyboards.common import back_to_menu_kb, cancel_kb, main_menu_kb
from keyboards.shop import (
    catalog_menu_kb,
    categories_kb,
    order_detail_kb,
    payment_check_kb,
    product_kb,
    products_kb,
    topup_methods_kb,
)
from keyboards.tickets import cart_actions_kb, cart_menu_kb

from services.crypto_pay import CryptoPayService
from services.telegram_pay import send_telegram_invoice

from states import PromoStates, SupportStates, TopUpStates
from utils.texts import format_price


router = Router()
PAGE_SIZE = 5


# ==================================================
# HELPERS
# ==================================================

def paginate(items: list, page: int, page_size: int = PAGE_SIZE):
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total_pages


REVIEWS_TEXT = """
💬 Белый лёд | Новый Усад: Касание! Ровненько всё!!!!
💬 Шишки | Пригородное: В касание, два раза взял! 😋
💬 ГАШ | Самаевка: Лучший магазин 🔥
💬 Белый лёд | Новый Усад: Спасибо поддержке ❤️
💬 Альфа PVP | Атюрьево: Всё чётко 💯
💬 Шишки | Барановка: Забрал без проблем 👍
💬 Белый лёд | Гумны: Всё ровно 🤝
💬 ГАШ | Куликово: Клад на месте 😎
💬 Меф | Первомайск: Быстро выдали 🚀
💬 Шишки | Слободские Дубровки: Качество огонь 🔥
💬 Белый лёд | Пригородное: Уже третий раз беру 💎
💬 ГАШ | Самаевка: Нашёл сразу 😍
💬 Альфа PVP | Новый Усад: Всё на уровне 🤝
💬 Шишки | Куликово: Отличный стафф 😋
💬 Белый лёд | Атюрьево: Поднял быстро 😁
"""


# ==================================================
# START
# ==================================================

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, config: Config):
    if command.args and command.args.startswith("ref_"):
        ref_raw = command.args.replace("ref_", "", 1)
        if ref_raw.isdigit():
            async with db.SessionLocal() as session:
                await set_referrer(session, message.from_user.id, int(ref_raw))

    referral_link = f"https://t.me/{(await message.bot.me()).username}?start=ref_{message.from_user.id}"

    text = (
        f"Добро пожаловать в <b>{config.shop_name}</b>\n\n"
        f"👥 Ваша ссылка:\n{referral_link}"
    )

    await message.answer(text, reply_markup=main_menu_kb())


# ==================================================
# MENU
# ==================================================

@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "reviews")
async def show_reviews(callback: CallbackQuery):
    await callback.message.edit_text(
        REVIEWS_TEXT,
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()


# ==================================================
# CATALOG
# ==================================================

@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        categories = await get_categories(session)

    await callback.message.edit_text(
        "Каталог товаров",
        reply_markup=catalog_menu_kb(bool(categories))
    )
    await callback.answer()


@router.callback_query(F.data == "catalog:categories")
async def show_categories(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        categories = await get_categories(session)

    if not categories:
        await callback.answer("Категорий нет", show_alert=True)
        return

    data = [(x.id, x.title) for x in categories]

    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=categories_kb(data)
    )
    await callback.answer()


@router.callback_query(F.data == "catalog:all")
@router.callback_query(F.data.startswith("catalog_page:"))
async def show_products_page(callback: CallbackQuery):
    page = 1

    if callback.data.startswith("catalog_page:"):
        page = int(callback.data.split(":")[1])

    async with db.SessionLocal() as session:
        products = await get_active_products(session)

    if not products:
        await callback.message.edit_text(
            "Товаров нет",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return

    page_items, total_pages = paginate(products, page)

    kb = [
        (x.id, x.title, format_price(x.price))
        for x in page_items
    ]

    await callback.message.edit_text(
        "Каталог товаров:",
        reply_markup=products_kb(kb, page, total_pages)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with db.SessionLocal() as session:
        product = await get_product(session, product_id)
        stock = await get_product_stock(session, product_id)

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    final_price = calculate_discounted_price(
        product.price,
        product.discount_percent
    )

    text = (
        f"🛍 <b>{product.title}</b>\n\n"
        f"{product.description}\n\n"
        f"💵 Цена: <b>{format_price(final_price)} ₽</b>\n"
        f"📦 Остаток: <b>{stock}</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=product_kb(product_id)
    )
    await callback.answer()


# ==================================================
# BUY
# ==================================================

@router.callback_query(F.data.startswith("buy:"))
async def buy_handler(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with db.SessionLocal() as session:
        success, text, order = await buy_product(
            session,
            callback.from_user.id,
            product_id
        )

    if not success:
        await callback.answer(text, show_alert=True)
        return

    await callback.message.answer(
        f"✅ Покупка успешна!\n\n"
        f"{order.product.title}\n"
        f"<code>{order.product_item.content}</code>",
        reply_markup=main_menu_kb()
    )

    await callback.answer()


# ==================================================
# BALANCE
# ==================================================

@router.callback_query(F.data == "my_balance")
async def my_balance(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        user = await get_user(session, callback.from_user.id)

    balance = format_price(user.balance if user else 0)

    await callback.message.edit_text(
        f"Баланс: <b>{balance} ₽</b>",
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()


# ==================================================
# TOPUP
# ==================================================

@router.callback_query(F.data == "topup_menu")
async def topup_menu(
    callback: CallbackQuery,
    config: Config,
    crypto: CryptoPayService,
    state: FSMContext
):
    await state.set_state(TopUpStates.waiting_for_amount)

    await callback.message.edit_text(
        "Введите сумму пополнения:",
        reply_markup=topup_methods_kb(
            crypto.enabled,
            bool(config.provider_token)
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_method:"))
async def topup_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    await state.update_data(method=method)
    await callback.answer(f"Выбрано: {method}")


@router.message(TopUpStates.waiting_for_amount)
async def process_topup(
    message: Message,
    state: FSMContext,
    config: Config,
    bot: Bot,
    crypto: CryptoPayService
):
    try:
        amount = Decimal(message.text.replace(",", "."))
    except:
        await message.answer("Введите число")
        return

    data = await state.get_data()
    method = data.get("method")

    if not method:
        await message.answer("Сначала выберите метод")
        return

    async with db.SessionLocal() as session:
        payment = await create_payment(
            session,
            message.from_user.id,
            amount,
            method
        )

        if method == "telegram":
            payload = f"tgpay:{payment.id}"

            await send_telegram_invoice(
                bot=bot,
                chat_id=message.chat.id,
                title="Пополнение",
                description=f"Пополнение {amount} ₽",
                payload=payload,
                provider_token=config.provider_token,
                amount_rub=int(amount),
            )

            await state.clear()
            return

    await message.answer("Ошибка оплаты")


# ==================================================
# SUPPORT
# ==================================================

@router.callback_query(F.data == "support_menu")
async def support_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_for_message)

    await callback.message.edit_text(
        "Опишите проблему:",
        reply_markup=cancel_kb()
    )

    await callback.answer()


@router.message(SupportStates.waiting_for_message)
async def support_message(
    message: Message,
    state: FSMContext,
    config: Config,
    bot: Bot
):
    text = message.text.strip()

    async with db.SessionLocal() as session:
        ticket = await create_support_ticket(
            session,
            message.from_user.id,
            text
        )

    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"Новый тикет #{ticket.id}\n{text}"
            )
        except:
            pass

    await state.clear()

    await message.answer(
        "Обращение отправлено",
        reply_markup=main_menu_kb()
    )


# ==================================================
# PAYMENTS
# ==================================================

@router.pre_checkout_query()
async def process_pre_checkout_query(
    pre_checkout_query: PreCheckoutQuery,
    bot: Bot
):
    await bot.answer_pre_checkout_query(
        pre_checkout_query.id,
        ok=True
    )


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload

    if not payload.startswith("tgpay:"):
        return

    payment_id = int(payload.split(":")[1])

    async with db.SessionLocal() as session:
        await mark_payment_paid(session, payment_id)

    await message.answer(
        "✅ Баланс пополнен",
        reply_markup=main_menu_kb()
    )
