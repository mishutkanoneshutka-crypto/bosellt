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
from states import PromoStates, SearchStates, SupportStates, TopUpStates
from utils.texts import format_price


router = Router()
PAGE_SIZE = 5


def paginate(items: list, page: int, page_size: int = PAGE_SIZE) -> tuple[list, int]:
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total_pages


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, config: Config):
    if command.args and command.args.startswith('ref_'):
        ref_raw = command.args.replace('ref_', '', 1)
        if ref_raw.isdigit():
            async with db.SessionLocal() as session:
                await set_referrer(session, message.from_user.id, int(ref_raw))

    referral_link = f'https://t.me/{(await message.bot.me()).username}?start=ref_{message.from_user.id}'
    text = (
        f'Добро пожаловать в <b>{config.shop_name}</b>.\n'
        'Выберите действие ниже.\n\n'
        f'👥 Ваша реферальная ссылка:\n{referral_link}\n'
        'За пополнение приглашённого пользователя вы получаете бонус.'
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.callback_query(F.data == 'noop')
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == 'main_menu')
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text('Главное меню', reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == 'catalog')
async def show_catalog(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        categories = await get_categories(session)
    await callback.message.edit_text('Каталог товаров', reply_markup=catalog_menu_kb(bool(categories)))
    await callback.answer()


@router.callback_query(F.data == 'catalog:categories')
async def show_categories(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        categories = await get_categories(session)
    if not categories:
        await callback.answer('Категорий пока нет.', show_alert=True)
        return
    data = [(item.id, item.title) for item in categories]
    await callback.message.edit_text('Выберите категорию:', reply_markup=categories_kb(data))
    await callback.answer()


@router.callback_query(F.data == 'catalog:all')
@router.callback_query(F.data.startswith('catalog_page:'))
async def show_products_page(callback: CallbackQuery):
    page = 1
    if callback.data.startswith('catalog_page:'):
        page = int(callback.data.split(':')[1])
    async with db.SessionLocal() as session:
        products = await get_active_products(session)
    if not products:
        await callback.message.edit_text('Сейчас нет доступных товаров.', reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    page_items, total_pages = paginate(products, page)
    kb_products = [(product.id, product.title, format_price(product.price)) for product in page_items]
    await callback.message.edit_text('Каталог товаров:', reply_markup=products_kb(kb_products, page, total_pages))
    await callback.answer()


@router.callback_query(F.data.startswith('catalog:category:'))
async def show_category_products(callback: CallbackQuery):
    category_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        products = await get_active_products(session, category_id=category_id)
    if not products:
        await callback.message.edit_text('В этой категории пока нет товаров.', reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    page_items, total_pages = paginate(products, 1)
    kb_products = [(product.id, product.title, format_price(product.price)) for product in page_items]
    await callback.message.edit_text('Товары категории:', reply_markup=products_kb(kb_products, 1, total_pages, prefix=f'category_page:{category_id}'))
    await callback.answer()


@router.callback_query(F.data.startswith('category_page:'))
async def show_category_products_page(callback: CallbackQuery):
    _, category_id, page = callback.data.split(':')
    async with db.SessionLocal() as session:
        products = await get_active_products(session, category_id=int(category_id))
    if not products:
        await callback.answer('Товаров нет.', show_alert=True)
        return
    page_items, total_pages = paginate(products, int(page))
    kb_products = [(product.id, product.title, format_price(product.price)) for product in page_items]
    await callback.message.edit_text(
        'Товары категории:',
        reply_markup=products_kb(kb_products, int(page), total_pages, prefix=f'category_page:{category_id}'),
    )
    await callback.answer()


@router.callback_query(F.data == 'reviews')
async def show_reviews(callback: CallbackQuery):
    REVIEWS_TEXT = (
    "💬 Белый лёд\\Новый Усад: Касание! Ровненько всё!!!!\n"
    "💬 Шишки\\Пригородное: В касание, два раза взял! Шишки вкусные! 😋\n"
    "💬 ГАШ - 🍫 Питерский\\Самаевка: Лучший магазин. Наконец-то хоть кто-то открылся 🔥\n"
    "💬 Белый лёд\\Новый Усад: Спасибо поддержке, помогли найти ❤️\n"
    "💬 Альфа PVP\\Атюрьево: Всё чётко, быстро поднял. Качество топ 💯\n"
    "💬 Шишки\\Барановка: Забрал без проблем, место удобное 👍\n"
    "💬 Белый лёд\\Гумны: Всё ровно, адрес точный, спасибо 🤝\n"
    "💬 ГАШ\\Куликово: Клад на месте, упаковка хорошая 😎\n"
    "💬 Меф\\Первомайск: Быстро выдали, сервис радует 🚀\n"
    "💬 Шишки\\Слободские Дубровки: Всё чётко, качество огонь 🔥\n"
    "💬 Белый лёд\\Пригородное: Уже третий раз беру, всё стабильно 💎\n"
    "💬 ГАШ\\Самаевка: Место спокойное, нашёл сразу 😍\n"
    "💬 Альфа PVP\\Новый Усад: Всё как всегда на уровне, уважение 🤝\n"
    "💬 Шишки\\Куликово: Отличный стафф, вернусь ещё 😋\n"
    "💬 Белый лёд\\Атюрьево: Поднял быстро, настроение топ 😁\n"
    "💬 Меф\\Барановка: Всё нашли быстро, место тихое 👍\n"
    "💬 Шишки\\Гумны: С первого раза, чётко сделано 💯\n"
    "💬 Белый лёд\\Первомайск: Всё красиво, качество радует 😍\n"
    "💬 ГАШ\\Пригородное: Лучший выбор по району 🔥\n"
    "💬 Альфа PVP\\Самаевка: Адрес ровный, без лишних движений 🤝\n"
    "💬 Шишки\\Атюрьево: Взял вечерком, всё на месте 😎\n"
    "💬 Белый лёд\\Куликово: Всё чётко, поддержка красавцы ❤️\n"
    "💬 ГАШ\\Слободские Дубровки: Качество мощное, вернусь ещё 🚀\n"
    "💬 Меф\\Новый Усад: Нашёл быстро, место понятное 👍\n"
    "💬 Шишки\\Первомайск: Уже не первый раз, всё стабильно 😋\n"
    "💬 Белый лёд\\Барановка: Ровно, спокойно, без проблем 💎\n"
    "💬 Альфа PVP\\Гумны: Всё как надо, магазин топ 🔥\n"
    "💬 ГАШ\\Атюрьево: Поднял быстро, качество на высоте 😍\n"
    "💬 Шишки\\Самаевка: Лучшая точка, спасибо магазину 🤝\n"
    "💬 Белый лёд\\Слободские Дубровки: Всё супер, нашёл сразу 💯\n"
)

    await callback.message.edit_text(
        text,
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == 'reviews')
async def show_reviews(callback: CallbackQuery):
     REVIEWS_TEXT = (
    "💬 Белый лёд\\Новый Усад: Касание! Ровненько всё!!!!\n"
    "💬 Шишки\\Пригородное: В касание, два раза взял! Шишки вкусные! 😋\n"
    "💬 ГАШ - 🍫 Питерский\\Самаевка: Лучший магазин. Наконец-то хоть кто-то открылся 🔥\n"
    "💬 Белый лёд\\Новый Усад: Спасибо поддержке, помогли найти ❤️\n"
    "💬 Альфа PVP\\Атюрьево: Всё чётко, быстро поднял. Качество топ 💯\n"
    "💬 Шишки\\Барановка: Забрал без проблем, место удобное 👍\n"
    "💬 Белый лёд\\Гумны: Всё ровно, адрес точный, спасибо 🤝\n"
    "💬 ГАШ\\Куликово: Клад на месте, упаковка хорошая 😎\n"
    "💬 Меф\\Первомайск: Быстро выдали, сервис радует 🚀\n"
    "💬 Шишки\\Слободские Дубровки: Всё чётко, качество огонь 🔥\n"
    "💬 Белый лёд\\Пригородное: Уже третий раз беру, всё стабильно 💎\n"
    "💬 ГАШ\\Самаевка: Место спокойное, нашёл сразу 😍\n"
    "💬 Альфа PVP\\Новый Усад: Всё как всегда на уровне, уважение 🤝\n"
    "💬 Шишки\\Куликово: Отличный стафф, вернусь ещё 😋\n"
    "💬 Белый лёд\\Атюрьево: Поднял быстро, настроение топ 😁\n"
    "💬 Меф\\Барановка: Всё нашли быстро, место тихое 👍\n"
    "💬 Шишки\\Гумны: С первого раза, чётко сделано 💯\n"
    "💬 Белый лёд\\Первомайск: Всё красиво, качество радует 😍\n"
    "💬 ГАШ\\Пригородное: Лучший выбор по району 🔥\n"
    "💬 Альфа PVP\\Самаевка: Адрес ровный, без лишних движений 🤝\n"
    "💬 Шишки\\Атюрьево: Взял вечерком, всё на месте 😎\n"
    "💬 Белый лёд\\Куликово: Всё чётко, поддержка красавцы ❤️\n"
    "💬 ГАШ\\Слободские Дубровки: Качество мощное, вернусь ещё 🚀\n"
    "💬 Меф\\Новый Усад: Нашёл быстро, место понятное 👍\n"
    "💬 Шишки\\Первомайск: Уже не первый раз, всё стабильно 😋\n"
    "💬 Белый лёд\\Барановка: Ровно, спокойно, без проблем 💎\n"
    "💬 Альфа PVP\\Гумны: Всё как надо, магазин топ 🔥\n"
    "💬 ГАШ\\Атюрьево: Поднял быстро, качество на высоте 😍\n"
    "💬 Шишки\\Самаевка: Лучшая точка, спасибо магазину 🤝\n"
    "💬 Белый лёд\\Слободские Дубровки: Всё супер, нашёл сразу 💯\n"
)

    await callback.message.edit_text(
        text,
        reply_markup=back_to_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith('product:'))
async def show_product(callback: CallbackQuery):
    product_id = int(callback.data.split(':')[1])
    async with db.SessionLocal() as session:
        product = await get_product(session, product_id)
        stock = await get_product_stock(session, product_id)
    if not product:
        await callback.answer('Товар не найден.', show_alert=True)
        return
    category_text = product.category.title if product.category else 'Без категории'
    final_price = calculate_discounted_price(product.price, product.discount_percent)
    discount_text = f'\n🔥 Скидка: <b>{product.discount_percent}%</b>' if product.discount_percent else ''
    text = (
        f'🛍 <b>{product.title}</b>\n\n'
        f'🗂 Категория: <b>{category_text}</b>\n'
        f'{product.description}\n\n'
        f'💵 Цена: <b>{format_price(product.price)} ₽</b>{discount_text}\n'
        f'💸 К оплате: <b>{format_price(final_price)} ₽</b>\n'
        f'📦 Остаток: <b>{stock}</b>'
    )
    await callback.message.edit_text(text, reply_markup=product_kb(product_id))
    await callback.answer()


@router.callback_query(F.data.startswith('buy:'))
async def buy_product_handler(callback: CallbackQuery):
    product_id = int(callback.data.split(':')[1])
    async with db.SessionLocal() as session:
        success, text, order = await buy_product(session, callback.from_user.id, product_id)
        if not success:
            await callback.answer(text, show_alert=True)
            return
        content = order.product_item.content
    await callback.message.answer(
        f'✅ Покупка успешна!\n\nТовар: <b>{order.product.title}</b>\nВаши данные:\n<code>{content}</code>',
        reply_markup=order_detail_kb(order.id),
    )
    await callback.answer('Товар выдан.')


@router.callback_query(F.data.startswith('cart_add:'))
async def add_product_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split(':')[1])
    async with db.SessionLocal() as session:
        result = await add_to_cart(session, callback.from_user.id, product_id)
    await callback.answer('Добавлено в корзину.' if result else 'Не удалось добавить товар.', show_alert=True)


async def _render_cart_text(user_id: int) -> tuple[str, list[int]]:
    async with db.SessionLocal() as session:
        cart_items = await get_cart_items(session, user_id)
        products = {product.id: product for product in await get_active_products(session)}
    if not cart_items:
        return 'Корзина пуста.', []
    total = Decimal('0.00')
    lines = []
    visible_ids: list[int] = []
    for item in cart_items:
        product = products.get(item.product_id)
        if not product:
            continue
        price = calculate_discounted_price(product.price, product.discount_percent)
        total += price * item.quantity
        visible_ids.append(item.id)
        lines.append(f'#{item.id} | {product.title}\nКоличество: {item.quantity}\nЦена: {format_price(price)} ₽')
    return '🛒 Корзина\n\n' + '\n\n'.join(lines) + f'\n\nИтого: <b>{format_price(total)} ₽</b>', visible_ids


@router.callback_query(F.data == 'cart_menu')
async def cart_menu(callback: CallbackQuery):
    text, visible_ids = await _render_cart_text(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=cart_menu_kb(bool(visible_ids)))
    for cart_item_id in visible_ids[:10]:
        await callback.message.answer(f'Управление позицией #{cart_item_id}:', reply_markup=cart_actions_kb(cart_item_id))
    await callback.answer()


@router.callback_query(F.data.startswith('cart:increase:'))
async def cart_increase(callback: CallbackQuery):
    cart_item_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        items = await get_cart_items(session, callback.from_user.id)
        target = next((item for item in items if item.id == cart_item_id), None)
        if not target:
            await callback.answer('Позиция не найдена.', show_alert=True)
            return
        await update_cart_quantity(session, cart_item_id, callback.from_user.id, target.quantity + 1)
    text, visible_ids = await _render_cart_text(callback.from_user.id)
    await callback.message.answer('✅ Количество увеличено.')
    await callback.message.answer(text, reply_markup=cart_menu_kb(bool(visible_ids)))
    await callback.answer()


@router.callback_query(F.data.startswith('cart:decrease:'))
async def cart_decrease(callback: CallbackQuery):
    cart_item_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        items = await get_cart_items(session, callback.from_user.id)
        target = next((item for item in items if item.id == cart_item_id), None)
        if not target:
            await callback.answer('Позиция не найдена.', show_alert=True)
            return
        await update_cart_quantity(session, cart_item_id, callback.from_user.id, target.quantity - 1)
    text, visible_ids = await _render_cart_text(callback.from_user.id)
    await callback.message.answer('✅ Количество изменено.')
    await callback.message.answer(text, reply_markup=cart_menu_kb(bool(visible_ids)))
    await callback.answer()


@router.callback_query(F.data.startswith('cart:remove:'))
async def cart_remove(callback: CallbackQuery):
    cart_item_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        result = await remove_cart_item(session, cart_item_id, callback.from_user.id)
    text, visible_ids = await _render_cart_text(callback.from_user.id)
    await callback.message.answer('🗑 Товар удален из корзины.' if result else 'Позиция не найдена.')
    await callback.message.answer(text, reply_markup=cart_menu_kb(bool(visible_ids)))
    await callback.answer()


@router.callback_query(F.data == 'cart:clear')
async def cart_clear(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        await clear_cart(session, callback.from_user.id)
    await callback.message.edit_text('Корзина очищена.', reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == 'cart:buy_all')
async def cart_buy_all(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        success, text, orders = await buy_cart(session, callback.from_user.id)
    if not success:
        await callback.answer(text, show_alert=True)
        return
    response = ['✅ Корзина успешно оплачена.']
    for order in orders[:20]:
        response.append(f'\nТовар: {order.product.title}\n<code>{order.product_item.content}</code>')
    await callback.message.answer('\n'.join(response), reply_markup=main_menu_kb())
    await callback.answer('Покупка завершена.')


@router.callback_query(F.data == 'my_orders')
async def my_orders(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        orders = await get_user_orders(session, callback.from_user.id)
    if not orders:
        await callback.message.edit_text('У вас пока нет покупок.', reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    parts = []
    for order in orders[:20]:
        parts.append(
            f'Заказ #{order.id}\n'
            f'Товар: {order.product.title}\n'
            f'Сумма: {format_price(order.amount)} ₽\n'
            f'Для просмотра товара нажмите: /order_{order.id}'
        )
    await callback.message.edit_text('\n\n'.join(parts), reply_markup=back_to_menu_kb())
    await callback.answer()


@router.message(F.text.regexp(r'^/order_(\d+)$'))
async def show_order_by_command(message: Message):
    order_id = int(message.text.split('_')[1])
    async with db.SessionLocal() as session:
        order = await get_order(session, order_id, user_id=message.from_user.id)
    if not order:
        await message.answer('Заказ не найден.')
        return
    await message.answer(
        f'Заказ #{order.id}\nТовар: {order.product.title}\nДанные:\n<code>{order.product_item.content}</code>',
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data.startswith('order:'))
async def show_order_detail(callback: CallbackQuery):
    order_id = int(callback.data.split(':')[1])
    async with db.SessionLocal() as session:
        order = await get_order(session, order_id, user_id=callback.from_user.id)
    if not order:
        await callback.answer('Заказ не найден.', show_alert=True)
        return
    await callback.message.answer(
        f'Заказ #{order.id}\nТовар: {order.product.title}\nДанные:\n<code>{order.product_item.content}</code>',
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == 'my_balance')
async def my_balance(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        user = await get_user(session, callback.from_user.id)
    balance = format_price(user.balance if user else 0)
    await callback.message.edit_text(f'Ваш баланс: <b>{balance} ₽</b>', reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == 'my_payments')
async def my_payments(callback: CallbackQuery):
    async with db.SessionLocal() as session:
        payments = await get_user_payments(session, callback.from_user.id)
    if not payments:
        await callback.message.edit_text('У вас пока нет платежей.', reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    text = '\n\n'.join(
        f'Платеж #{payment.id}\nСумма: {format_price(payment.amount)} ₽\nМетод: {payment.method}\nСтатус: {payment.status}'
        for payment in payments[:20]
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == 'topup_menu')
async def topup_menu(callback: CallbackQuery, config: Config, state: FSMContext, crypto: CryptoPayService):
    await state.set_state(TopUpStates.waiting_for_amount)
    await callback.message.edit_text(
        'Введите сумму пополнения в рублях. Например: 500\n\nЕсли у вас есть промокод — используйте команду /promo',
        reply_markup=topup_methods_kb(crypto.enabled, bool(config.provider_token)),
    )
    await callback.answer()


@router.callback_query(F.data == 'promo_menu')
async def promo_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.waiting_for_code)
    await callback.message.edit_text('Введите промокод:', reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(F.data == 'support_menu')
async def support_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_for_message)
    await callback.message.edit_text('Опишите вашу проблему одним сообщением:', reply_markup=cancel_kb())
    await callback.answer()


@router.message(SupportStates.waiting_for_message)
async def support_message(message: Message, state: FSMContext, config: Config, bot: Bot):
    text = (message.text or '').strip()
    if len(text) < 5:
        await message.answer('Опишите проблему подробнее.')
        return
    async with db.SessionLocal() as session:
        ticket = await create_support_ticket(session, message.from_user.id, text)
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f'🆘 Новый тикет #{ticket.id}\nПользователь: {message.from_user.id}\n\n{text}',
            )
        except Exception:
            pass
    await state.clear()
    await message.answer(f'✅ Обращение создано. Номер тикета: #{ticket.id}', reply_markup=main_menu_kb())


@router.message(F.text == '/promo')
async def promo_command(message: Message, state: FSMContext):
    await state.set_state(PromoStates.waiting_for_code)
    await message.answer('Введите промокод:', reply_markup=cancel_kb())


@router.message(PromoStates.waiting_for_code)
async def promo_apply(message: Message, state: FSMContext):
    code = (message.text or '').strip()
    if not code:
        await message.answer('Введите промокод текстом.')
        return
    async with db.SessionLocal() as session:
        success, text, amount = await apply_promo_code(session, message.from_user.id, code)
    await state.clear()
    if success:
        await message.answer(f'✅ {text}\nНачислено: <b>{format_price(amount)} ₽</b>', reply_markup=main_menu_kb())
        return
    await message.answer(text, reply_markup=back_to_menu_kb())


@router.callback_query(F.data.startswith('topup_method:'))
async def select_topup_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(':')[1]
    await state.update_data(method=method)
    await callback.answer(f'Способ оплаты: {method}')


@router.message(TopUpStates.waiting_for_amount)
async def process_topup_amount(message: Message, state: FSMContext, config: Config, bot: Bot, crypto: CryptoPayService):
    try:
        amount = Decimal((message.text or '').replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, AttributeError):
        await message.answer('Введите корректную сумму числом.')
        return

    data = await state.get_data()
    method = data.get('method')
    if not method:
        await message.answer('Сначала выберите способ оплаты кнопкой ниже.', reply_markup=topup_methods_kb(crypto.enabled, bool(config.provider_token)))
        return

    async with db.SessionLocal() as session:
        payment = await create_payment(session, message.from_user.id, amount, method=method)

        if method == 'crypto':
            if not crypto.enabled:
                await message.answer('Crypto Bot не настроен.')
                return
            invoice = await crypto.create_invoice(amount=amount, payload=f'user:{message.from_user.id}:payment:{payment.id}')
            if not invoice:
                await message.answer('Не удалось создать crypto invoice.')
                return
            payment.external_id = str(invoice['invoice_id'])
            payment.method = 'crypto_bot'
            await session.commit()
            await state.clear()
            await message.answer(
                f'Сумма пополнения: <b>{format_price(amount)} ₽</b>\n\nОплатить: {invoice["bot_invoice_url"]}',
                reply_markup=payment_check_kb(str(invoice['invoice_id'])),
            )
            return

        if method == 'telegram':
            if not config.provider_token:
                await message.answer('Telegram Payments не настроен.')
                return
            payload = f'tgpay:{payment.id}'
            await send_telegram_invoice(
                bot=bot,
                chat_id=message.chat.id,
                title='Пополнение баланса',
                description=f'Пополнение баланса на {format_price(amount)} ₽',
                payload=payload,
                provider_token=config.provider_token,
                amount_rub=int(amount),
            )
            await state.clear()
            await message.answer('Инвойс Telegram Payments отправлен отдельным сообщением.', reply_markup=back_to_menu_kb())
            return

    await message.answer('Неизвестный способ оплаты.')


@router.message(F.text.regexp(r'^/check_(\d+)$'))
async def check_crypto_payment_by_command(message: Message, crypto: CryptoPayService):
    invoice_id = message.text.split('_', 1)[1]
    await _check_crypto_payment(message, invoice_id, crypto)


@router.callback_query(F.data.startswith('check_payment:'))
async def check_crypto_payment_callback(callback: CallbackQuery, crypto: CryptoPayService):
    invoice_id = callback.data.split(':')[1]
    await _check_crypto_payment(callback.message, invoice_id, crypto)
    await callback.answer()


async def _check_crypto_payment(message: Message, invoice_id: str, crypto: CryptoPayService):
    if not crypto.enabled:
        await message.answer('Crypto Bot не настроен.')
        return

    invoice = await crypto.get_invoice(invoice_id)
    if not invoice:
        await message.answer('Инвойс не найден.')
        return

    async with db.SessionLocal() as session:
        payment = await get_payment_by_external_id(session, invoice_id)
        if not payment:
            await message.answer('Платеж не найден в базе.')
            return
        if invoice.get('status') == 'paid':
            await mark_payment_paid(session, payment.id)
            await message.answer('✅ Оплата подтверждена, баланс пополнен.', reply_markup=main_menu_kb())
        else:
            await message.answer(f'Текущий статус: {invoice.get("status", "unknown")}')


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if not payload.startswith('tgpay:'):
        return
    payment_id = int(payload.split(':')[1])
    async with db.SessionLocal() as session:
        await mark_payment_paid(session, payment_id)
    await message.answer('✅ Баланс успешно пополнен через Telegram Payments.', reply_markup=main_menu_kb())
