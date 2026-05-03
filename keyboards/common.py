from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='🛍 Каталог', callback_data='catalog')
    builder.button(text='🔎 Поиск', callback_data='search_products')
    builder.button(text='💳 Пополнить баланс', callback_data='topup_menu')
    builder.button(text='🎟 Активировать промокод', callback_data='promo_menu')
    builder.button(text='🛒 Корзина', callback_data='cart_menu')
    builder.button(text='📦 Мои покупки', callback_data='my_orders')
    builder.button(text='💰 Баланс', callback_data='my_balance')
    builder.button(text='🧾 Мои платежи', callback_data='my_payments')
    builder.button(text='🆘 Поддержка', callback_data='support_menu')
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def back_to_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ В меню', callback_data='main_menu')
    return builder.as_markup()


def cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='❌ Отмена', callback_data='cancel_state')
    builder.adjust(1)
    return builder.as_markup()
