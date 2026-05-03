from aiogram.utils.keyboard import InlineKeyboardBuilder


def catalog_menu_kb(has_categories: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text='📦 Все товары', callback_data='catalog:all')
    if has_categories:
        builder.button(text='🗂 Категории', callback_data='catalog:categories')
    builder.button(text='⬅️ В меню', callback_data='main_menu')
    builder.adjust(1)
    return builder.as_markup()


def categories_kb(categories: list[tuple[int, str]]):
    builder = InlineKeyboardBuilder()
    for category_id, title in categories:
        builder.button(text=title, callback_data=f'catalog:category:{category_id}')
    builder.button(text='⬅️ Назад', callback_data='catalog')
    builder.adjust(1)
    return builder.as_markup()


def products_kb(products: list[tuple[int, str, str]], page: int, total_pages: int, prefix: str = 'catalog_page'):
    builder = InlineKeyboardBuilder()
    for product_id, title, price in products:
        builder.button(text=f'{title} — {price} ₽', callback_data=f'product:{product_id}')
    if total_pages > 1:
        if page > 1:
            builder.button(text='⬅️', callback_data=f'{prefix}:{page - 1}')
        builder.button(text=f'{page}/{total_pages}', callback_data='noop')
        if page < total_pages:
            builder.button(text='➡️', callback_data=f'{prefix}:{page + 1}')
    builder.button(text='⬅️ Назад', callback_data='catalog')
    builder.adjust(1)
    return builder.as_markup()


def product_kb(product_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text='🛒 Купить', callback_data=f'buy:{product_id}')
    builder.button(text='➕ В корзину', callback_data=f'cart_add:{product_id}')
    builder.button(text='⬅️ К каталогу', callback_data='catalog')
    builder.adjust(1)
    return builder.as_markup()


def order_detail_kb(order_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text='🔐 Показать товар', callback_data=f'order:{order_id}')
    builder.button(text='⬅️ Назад', callback_data='my_orders')
    builder.adjust(1)
    return builder.as_markup()


def topup_methods_kb(has_crypto: bool, has_telegram: bool):
    builder = InlineKeyboardBuilder()
    if has_crypto:
        builder.button(text='💎 Crypto Bot', callback_data='topup_method:crypto')
    if has_telegram:
        builder.button(text='💳 Telegram Payments', callback_data='topup_method:telegram')
    builder.button(text='⬅️ В меню', callback_data='main_menu')
    builder.adjust(1)
    return builder.as_markup()


def payment_check_kb(invoice_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Проверить оплату', callback_data=f'check_payment:{invoice_id}')
    builder.button(text='⬅️ В меню', callback_data='main_menu')
    builder.adjust(1)
    return builder.as_markup()
