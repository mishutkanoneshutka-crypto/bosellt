from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from config import Config
import database.base as db
from database.crud import (
    add_product_items,
    change_user_balance,
    clear_unsold_items,
    create_category,
    create_product,
    create_promo_code,
    get_all_orders,
    get_all_payments,
    get_all_products,
    get_all_user_ids,
    get_all_users,
    get_categories,
    get_stats,
    get_support_ticket,
    get_support_tickets,
    reply_support_ticket,
    set_user_blocked,
    update_product_field,
    update_product_status,
)
from keyboards.admin import admin_menu_kb, block_action_kb
from keyboards.common import back_to_menu_kb, cancel_kb
from keyboards.tickets import ticket_list_kb, ticket_view_kb
from states import (
    AdminAddCategoryStates,
    AdminAddItemsStates,
    AdminAddProductStates,
    AdminBalanceStates,
    AdminBlockUserStates,
    AdminBroadcastStates,
    AdminClearStockStates,
    AdminEditProductStates,
    AdminExportStates,
    AdminFileUploadStates,
    AdminPromoStates,
    AdminTicketReplyStates,
    AdminToggleProductStates,
)
from utils.texts import format_price


router = Router()


def is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admin_ids


@router.message(Command('admin'))
async def admin_menu(message: Message, config: Config):
    if not is_admin(message.from_user.id, config):
        await message.answer('Доступ запрещен.')
        return
    await message.answer('Админ-панель', reply_markup=admin_menu_kb())


@router.callback_query(F.data == 'cancel_state')
async def cancel_state(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Действие отменено.', reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == 'noop_admin_back')
async def noop_admin_back(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith('admin:'))
async def admin_callbacks(callback: CallbackQuery, config: Config, state: FSMContext):
    if not is_admin(callback.from_user.id, config):
        await callback.answer('Доступ запрещен.', show_alert=True)
        return

    action = callback.data.split(':', 1)[1]

    if action == 'stats':
        async with db.SessionLocal() as session:
            stats = await get_stats(session)
        text = (
            '📊 Статистика\n\n'
            f'Пользователей: <b>{stats["users_count"]}</b>\n'
            f'Товаров: <b>{stats["products_count"]}</b>\n'
            f'Покупок: <b>{stats["orders_count"]}</b>\n'
            f'Оплачено: <b>{format_price(stats["paid_sum"])} ₽</b>'
        )
        await callback.message.edit_text(text, reply_markup=admin_menu_kb())
    elif action == 'add_category':
        await state.set_state(AdminAddCategoryStates.waiting_for_title)
        await callback.message.edit_text('Введите название категории:', reply_markup=cancel_kb())
    elif action == 'add_product':
        await state.set_state(AdminAddProductStates.waiting_for_category_id)
        async with db.SessionLocal() as session:
            categories = await get_categories(session)
        if categories:
            category_lines = '\n'.join(f'{category.id} — {category.title}' for category in categories)
            await callback.message.edit_text(
                'Введите ID категории или 0 без категории:\n\n' + category_lines,
                reply_markup=cancel_kb(),
            )
        else:
            await callback.message.edit_text('Категорий пока нет. Введите 0 для товара без категории.', reply_markup=cancel_kb())
    elif action == 'list_products':
        async with db.SessionLocal() as session:
            products = await get_all_products(session)
        if not products:
            await callback.message.edit_text('Товаров пока нет.', reply_markup=back_to_menu_kb())
        else:
            text = '\n\n'.join(
                (
                    f'ID: {product.id}\n'
                    f'Категория: {product.category.title if product.category else "—"}\n'
                    f'{product.title}\n'
                    f'Цена: {format_price(product.price)} ₽\n'
                    f'Активен: {"да" if product.is_active else "нет"}'
                )
                for product in products[:40]
            )
            await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    elif action == 'add_items':
        await state.set_state(AdminAddItemsStates.waiting_for_product_id)
        await callback.message.edit_text('Введите ID товара, в который нужно загрузить позиции:', reply_markup=cancel_kb())
    elif action == 'toggle_product':
        await state.set_state(AdminToggleProductStates.waiting_for_product_id)
        await callback.message.edit_text('Введите ID товара для переключения активности:', reply_markup=cancel_kb())
    elif action == 'add_items_file':
        await state.set_state(AdminFileUploadStates.waiting_for_product_id)
        await callback.message.edit_text('Введите ID товара для загрузки позиций из .txt файла:', reply_markup=cancel_kb())
    elif action == 'create_promo':
        await state.set_state(AdminPromoStates.waiting_for_code)
        await callback.message.edit_text('Введите код промокода:', reply_markup=cancel_kb())
    elif action == 'broadcast':
        await state.set_state(AdminBroadcastStates.waiting_for_text)
        await callback.message.edit_text('Введите текст рассылки:', reply_markup=cancel_kb())
    elif action == 'export_csv':
        await callback.message.edit_text('Выберите тип экспорта: users / orders / payments', reply_markup=cancel_kb())
        await state.set_state(AdminExportStates.waiting_for_type)
    elif action == 'edit_product':
        await callback.message.edit_text('Введите ID товара для редактирования:', reply_markup=cancel_kb())
        await state.set_state(AdminEditProductStates.waiting_for_product_id)
    elif action == 'clear_stock':
        await callback.message.edit_text('Введите ID товара для очистки непроданных остатков:', reply_markup=cancel_kb())
        await state.set_state(AdminClearStockStates.waiting_for_product_id)
    elif action == 'reply_ticket':
        await callback.message.edit_text('Введите ID тикета:', reply_markup=cancel_kb())
        await state.set_state(AdminTicketReplyStates.waiting_for_ticket_id)
    elif action == 'tickets_open':
        async with db.SessionLocal() as session:
            tickets = await get_support_tickets(session, 'open')
        if not tickets:
            await callback.message.edit_text('Нет открытых тикетов.', reply_markup=admin_menu_kb())
        else:
            await callback.message.edit_text('Открытые тикеты:', reply_markup=ticket_list_kb([(item.id, item.status) for item in tickets[:30]]))
    elif action == 'tickets_closed':
        async with db.SessionLocal() as session:
            tickets = await get_support_tickets(session, 'closed')
        if not tickets:
            await callback.message.edit_text('Нет закрытых тикетов.', reply_markup=admin_menu_kb())
        else:
            await callback.message.edit_text('Закрытые тикеты:', reply_markup=ticket_list_kb([(item.id, item.status) for item in tickets[:30]]))
    elif action == 'block_user':
        await state.set_state(AdminBlockUserStates.waiting_for_user_id)
        await callback.message.edit_text('Введите ID пользователя:', reply_markup=cancel_kb())
    elif action == 'change_balance':
        await state.set_state(AdminBalanceStates.waiting_for_user_id)
        await callback.message.edit_text('Введите ID пользователя:', reply_markup=cancel_kb())

    await callback.answer()


@router.callback_query(F.data.startswith('admin:block:'))
async def admin_block_action(callback: CallbackQuery, config: Config):
    if not is_admin(callback.from_user.id, config):
        await callback.answer('Доступ запрещен.', show_alert=True)
        return
    user_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        result = await set_user_blocked(session, user_id, True)
    await callback.answer('Пользователь заблокирован.' if result else 'Пользователь не найден.', show_alert=True)


@router.callback_query(F.data.startswith('admin:unblock:'))
async def admin_unblock_action(callback: CallbackQuery, config: Config):
    if not is_admin(callback.from_user.id, config):
        await callback.answer('Доступ запрещен.', show_alert=True)
        return
    user_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        result = await set_user_blocked(session, user_id, False)
    await callback.answer('Пользователь разблокирован.' if result else 'Пользователь не найден.', show_alert=True)


@router.message(AdminAddCategoryStates.waiting_for_title)
async def admin_add_category_title(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    title = (message.text or '').strip()
    if not title:
        await message.answer('Название не может быть пустым.')
        return
    async with db.SessionLocal() as session:
        category = await create_category(session, title)
    await state.clear()
    await message.answer(f'✅ Категория создана. ID: {category.id}', reply_markup=admin_menu_kb())


@router.message(AdminAddProductStates.waiting_for_category_id)
async def admin_add_product_category(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').lstrip('-').isdigit():
        await message.answer('Введите ID категории числом или 0.')
        return
    category_id = int(message.text)
    await state.update_data(category_id=None if category_id == 0 else category_id)
    await state.set_state(AdminAddProductStates.waiting_for_title)
    await message.answer('Введите название товара:', reply_markup=cancel_kb())


@router.message(AdminAddProductStates.waiting_for_title)
async def admin_add_product_title(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    await state.update_data(title=message.text)
    await state.set_state(AdminAddProductStates.waiting_for_description)
    await message.answer('Введите описание товара:', reply_markup=cancel_kb())


@router.message(AdminAddProductStates.waiting_for_description)
async def admin_add_product_description(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    await state.update_data(description=message.text)
    await state.set_state(AdminAddProductStates.waiting_for_price)
    await message.answer('Введите цену товара в рублях:', reply_markup=cancel_kb())


@router.message(AdminAddProductStates.waiting_for_price)
async def admin_add_product_price(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        price = Decimal((message.text or '').replace(',', '.'))
        if price <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, AttributeError):
        await message.answer('Введите корректную цену числом.')
        return

    data = await state.get_data()
    async with db.SessionLocal() as session:
        product = await create_product(
            session,
            data['title'],
            data['description'],
            price,
            data.get('category_id'),
        )
    await state.clear()
    await message.answer(f'✅ Товар создан. ID: {product.id}', reply_markup=admin_menu_kb())


@router.message(AdminAddItemsStates.waiting_for_product_id)
async def admin_add_items_product_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID товара.')
        return
    await state.update_data(product_id=int(message.text))
    await state.set_state(AdminAddItemsStates.waiting_for_items)
    await message.answer('Отправьте позиции товара, каждая с новой строки.', reply_markup=cancel_kb())


@router.message(AdminAddItemsStates.waiting_for_items)
async def admin_add_items_content(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    data = await state.get_data()
    items = (message.text or '').splitlines()
    async with db.SessionLocal() as session:
        count = await add_product_items(session, data['product_id'], items)
    await state.clear()
    await message.answer(f'✅ Загружено позиций: {count}', reply_markup=admin_menu_kb())


@router.message(AdminToggleProductStates.waiting_for_product_id)
async def admin_toggle_product(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID товара.')
        return
    product_id = int(message.text)
    async with db.SessionLocal() as session:
        products = await get_all_products(session)
        target = next((item for item in products if item.id == product_id), None)
        if not target:
            result = False
        else:
            result = await update_product_status(session, product_id, not target.is_active)
    await state.clear()
    await message.answer('✅ Статус товара изменен.' if result else 'Товар не найден.', reply_markup=admin_menu_kb())


@router.message(AdminFileUploadStates.waiting_for_product_id)
async def admin_upload_file_product_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID товара.')
        return
    await state.update_data(product_id=int(message.text))
    await state.set_state(AdminFileUploadStates.waiting_for_document)
    await message.answer('Отправьте .txt файл с позициями, каждая с новой строки.', reply_markup=cancel_kb())


@router.message(AdminFileUploadStates.waiting_for_document, F.document)
async def admin_upload_file_document(message: Message, state: FSMContext, config: Config, bot):
    if not is_admin(message.from_user.id, config):
        return
    document = message.document
    if not document.file_name.lower().endswith('.txt'):
        await message.answer('Поддерживается только .txt файл.')
        return
    file = await bot.get_file(document.file_id)
    file_data = await bot.download_file(file.file_path)
    content = file_data.read().decode('utf-8', errors='ignore')
    items = [line.strip() for line in content.splitlines() if line.strip()]
    data = await state.get_data()
    async with db.SessionLocal() as session:
        count = await add_product_items(session, data['product_id'], items)
    await state.clear()
    await message.answer(f'✅ Из файла загружено позиций: {count}', reply_markup=admin_menu_kb())


@router.message(AdminPromoStates.waiting_for_code)
async def admin_promo_code(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    code = (message.text or '').strip().upper()
    if len(code) < 3:
        await message.answer('Код слишком короткий.')
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoStates.waiting_for_amount)
    await message.answer('Введите сумму бонуса по промокоду:', reply_markup=cancel_kb())


@router.message(AdminPromoStates.waiting_for_amount)
async def admin_promo_amount(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        amount = Decimal((message.text or '').replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, AttributeError):
        await message.answer('Введите корректную сумму.')
        return
    await state.update_data(amount=amount)
    await state.set_state(AdminPromoStates.waiting_for_max_uses)
    await message.answer('Введите максимальное число использований:', reply_markup=cancel_kb())


@router.message(AdminPromoStates.waiting_for_max_uses)
async def admin_promo_max_uses(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите число.')
        return
    max_uses = int(message.text)
    if max_uses <= 0:
        await message.answer('Число должно быть больше 0.')
        return
    data = await state.get_data()
    async with db.SessionLocal() as session:
        promo = await create_promo_code(session, data['code'], data['amount'], max_uses)
    await state.clear()
    await message.answer(
        f'✅ Промокод создан: <code>{promo.code}</code>\nСумма: {format_price(promo.amount)} ₽\nИспользований: {promo.max_uses}',
        reply_markup=admin_menu_kb(),
    )


@router.message(AdminBroadcastStates.waiting_for_text)
async def admin_broadcast(message: Message, state: FSMContext, config: Config, bot):
    if not is_admin(message.from_user.id, config):
        return
    text = (message.text or '').strip()
    if not text:
        await message.answer('Текст не должен быть пустым.')
        return
    async with db.SessionLocal() as session:
        user_ids = await get_all_user_ids(session)
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
    await state.clear()
    await message.answer(f'✅ Рассылка завершена. Отправлено: {sent}, ошибок: {failed}', reply_markup=admin_menu_kb())


@router.message(AdminExportStates.waiting_for_type)
async def admin_export_csv(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    export_type = (message.text or '').strip().lower()
    output = io.StringIO()
    writer = csv.writer(output)

    async with db.SessionLocal() as session:
        if export_type == 'users':
            users = await get_all_users(session)
            writer.writerow(['id', 'username', 'full_name', 'balance', 'is_blocked', 'referred_by', 'created_at'])
            for item in users:
                writer.writerow([item.id, item.username, item.full_name, item.balance, item.is_blocked, item.referred_by, item.created_at])
        elif export_type == 'orders':
            orders = await get_all_orders(session)
            writer.writerow(['id', 'user_id', 'product_id', 'product_title', 'amount', 'created_at'])
            for item in orders:
                writer.writerow([item.id, item.user_id, item.product_id, item.product.title, item.amount, item.created_at])
        elif export_type == 'payments':
            payments = await get_all_payments(session)
            writer.writerow(['id', 'user_id', 'amount', 'method', 'status', 'external_id', 'created_at'])
            for item in payments:
                writer.writerow([item.id, item.user_id, item.amount, item.method, item.status, item.external_id, item.created_at])
        else:
            await message.answer('Введите только: users / orders / payments')
            return

    content = output.getvalue().encode('utf-8')
    file = BufferedInputFile(content, filename=f'{export_type}.csv')
    await state.clear()
    await message.answer_document(file, caption=f'Экспорт {export_type}')
    await message.answer('✅ Экспорт готов.', reply_markup=admin_menu_kb())


@router.message(AdminEditProductStates.waiting_for_product_id)
async def admin_edit_product_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID товара.')
        return
    await state.update_data(product_id=int(message.text))
    await state.set_state(AdminEditProductStates.waiting_for_field)
    await message.answer('Введите поле: title / description / price / discount_percent', reply_markup=cancel_kb())


@router.message(AdminEditProductStates.waiting_for_field)
async def admin_edit_product_field(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    field = (message.text or '').strip()
    if field not in {'title', 'description', 'price', 'discount_percent'}:
        await message.answer('Доступные поля: title / description / price / discount_percent')
        return
    await state.update_data(field=field)
    await state.set_state(AdminEditProductStates.waiting_for_value)
    await message.answer('Введите новое значение:', reply_markup=cancel_kb())


@router.message(AdminEditProductStates.waiting_for_value)
async def admin_edit_product_value(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    data = await state.get_data()
    field = data['field']
    value = message.text
    if field == 'price':
        value = Decimal((message.text or '').replace(',', '.'))
    elif field == 'discount_percent':
        value = int(message.text)
    async with db.SessionLocal() as session:
        result = await update_product_field(session, data['product_id'], field, value)
    await state.clear()
    await message.answer('✅ Товар обновлен.' if result else 'Не удалось обновить товар.', reply_markup=admin_menu_kb())


@router.message(AdminClearStockStates.waiting_for_product_id)
async def admin_clear_stock(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID товара.')
        return
    async with db.SessionLocal() as session:
        count = await clear_unsold_items(session, int(message.text))
    await state.clear()
    await message.answer(f'✅ Удалено непроданных позиций: {count}', reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith('admin:ticket_view:'))
async def admin_ticket_view(callback: CallbackQuery, config: Config):
    if not is_admin(callback.from_user.id, config):
        await callback.answer('Доступ запрещен.', show_alert=True)
        return
    ticket_id = int(callback.data.split(':')[2])
    async with db.SessionLocal() as session:
        ticket = await get_support_ticket(session, ticket_id)
    if not ticket:
        await callback.answer('Тикет не найден.', show_alert=True)
        return
    text = (
        f'Тикет #{ticket.id}\n'
        f'Пользователь: {ticket.user_id}\n'
        f'Статус: {ticket.status}\n\n'
        f'Сообщение:\n{ticket.message_text}\n\n'
        f'Ответ:\n{ticket.admin_reply or "—"}'
    )
    await callback.message.edit_text(text, reply_markup=ticket_view_kb(ticket.id, ticket.status == 'open'))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:ticket_reply:'))
async def admin_ticket_reply_callback(callback: CallbackQuery, state: FSMContext, config: Config):
    if not is_admin(callback.from_user.id, config):
        await callback.answer('Доступ запрещен.', show_alert=True)
        return
    ticket_id = int(callback.data.split(':')[2])
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminTicketReplyStates.waiting_for_reply)
    await callback.message.edit_text(f'Введите ответ для тикета #{ticket_id}:', reply_markup=cancel_kb())
    await callback.answer()


@router.message(AdminTicketReplyStates.waiting_for_ticket_id)
async def admin_ticket_reply_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID тикета.')
        return
    await state.update_data(ticket_id=int(message.text))
    await state.set_state(AdminTicketReplyStates.waiting_for_reply)
    await message.answer('Введите ответ пользователю:', reply_markup=cancel_kb())


@router.message(AdminTicketReplyStates.waiting_for_reply)
async def admin_ticket_reply_text(message: Message, state: FSMContext, config: Config, bot):
    if not is_admin(message.from_user.id, config):
        return
    data = await state.get_data()
    async with db.SessionLocal() as session:
        ticket = await reply_support_ticket(session, data['ticket_id'], message.text or '')
    await state.clear()
    if not ticket:
        await message.answer('Тикет не найден.', reply_markup=admin_menu_kb())
        return
    try:
        await bot.send_message(ticket.user_id, f'💬 Ответ по тикету #{ticket.id}:\n\n{ticket.admin_reply}')
    except Exception:
        pass
    await message.answer('✅ Ответ отправлен пользователю.', reply_markup=admin_menu_kb())


@router.message(AdminBlockUserStates.waiting_for_user_id)
async def admin_block_user_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID пользователя.')
        return
    user_id = int(message.text)
    await state.clear()
    await message.answer('Выберите действие:', reply_markup=block_action_kb(user_id))


@router.message(AdminBalanceStates.waiting_for_user_id)
async def admin_balance_user_id(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    if not (message.text or '').isdigit():
        await message.answer('Введите числовой ID пользователя.')
        return
    await state.update_data(user_id=int(message.text))
    await state.set_state(AdminBalanceStates.waiting_for_amount)
    await message.answer('Введите сумму. Можно отрицательную, например: -100 или 250', reply_markup=cancel_kb())


@router.message(AdminBalanceStates.waiting_for_amount)
async def admin_balance_amount(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        amount = Decimal((message.text or '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        await message.answer('Введите корректную сумму.')
        return
    data = await state.get_data()
    async with db.SessionLocal() as session:
        result = await change_user_balance(session, data['user_id'], amount)
    await state.clear()
    await message.answer('✅ Баланс изменен.' if result else 'Пользователь не найден.', reply_markup=admin_menu_kb())
