from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='📊 Статистика', callback_data='admin:stats')
    builder.button(text='🗂 Добавить категорию', callback_data='admin:add_category')
    builder.button(text='➕ Добавить товар', callback_data='admin:add_product')
    builder.button(text='📋 Список товаров', callback_data='admin:list_products')
    builder.button(text='📥 Загрузить позиции', callback_data='admin:add_items')
    builder.button(text='📄 Загрузить позиции файлом', callback_data='admin:add_items_file')
    builder.button(text='🎟 Создать промокод', callback_data='admin:create_promo')
    builder.button(text='📢 Рассылка', callback_data='admin:broadcast')
    builder.button(text='📤 Экспорт CSV', callback_data='admin:export_csv')
    builder.button(text='✏️ Редактировать товар', callback_data='admin:edit_product')
    builder.button(text='🧹 Очистить остатки', callback_data='admin:clear_stock')
    builder.button(text='💬 Ответить на тикет', callback_data='admin:reply_ticket')
    builder.button(text='📬 Открытые тикеты', callback_data='admin:tickets_open')
    builder.button(text='✅ Закрытые тикеты', callback_data='admin:tickets_closed')
    builder.button(text='🔁 Вкл/выкл товар', callback_data='admin:toggle_product')
    builder.button(text='🚫 Блокировка пользователя', callback_data='admin:block_user')
    builder.button(text='💰 Изменить баланс', callback_data='admin:change_balance')
    builder.adjust(1)
    return builder.as_markup()


def block_action_kb(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text='🚫 Заблокировать', callback_data=f'admin:block:{user_id}')
    builder.button(text='✅ Разблокировать', callback_data=f'admin:unblock:{user_id}')
    builder.adjust(1)
    return builder.as_markup()
