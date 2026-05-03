from aiogram.utils.keyboard import InlineKeyboardBuilder


def cart_actions_kb(cart_item_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text='➖', callback_data=f'cart:decrease:{cart_item_id}')
    builder.button(text='❌ Удалить', callback_data=f'cart:remove:{cart_item_id}')
    builder.button(text='➕', callback_data=f'cart:increase:{cart_item_id}')
    builder.adjust(3)
    return builder.as_markup()


def cart_menu_kb(has_items: bool):
    builder = InlineKeyboardBuilder()
    if has_items:
        builder.button(text='✅ Купить всю корзину', callback_data='cart:buy_all')
        builder.button(text='🗑 Очистить корзину', callback_data='cart:clear')
    builder.button(text='⬅️ В меню', callback_data='main_menu')
    builder.adjust(1)
    return builder.as_markup()


def ticket_list_kb(tickets: list[tuple[int, str]]):
    builder = InlineKeyboardBuilder()
    for ticket_id, status in tickets:
        icon = '🟢' if status == 'open' else '⚪️'
        builder.button(text=f'{icon} Тикет #{ticket_id}', callback_data=f'admin:ticket_view:{ticket_id}')
    builder.button(text='📬 Открытые', callback_data='admin:tickets_open')
    builder.button(text='✅ Закрытые', callback_data='admin:tickets_closed')
    builder.button(text='⬅️ Назад', callback_data='noop_admin_back')
    builder.adjust(1)
    return builder.as_markup()


def ticket_view_kb(ticket_id: int, is_open: bool):
    builder = InlineKeyboardBuilder()
    if is_open:
        builder.button(text='💬 Ответить', callback_data=f'admin:ticket_reply:{ticket_id}')
    builder.button(text='📬 Открытые', callback_data='admin:tickets_open')
    builder.button(text='✅ Закрытые', callback_data='admin:tickets_closed')
    builder.adjust(1)
    return builder.as_markup()
