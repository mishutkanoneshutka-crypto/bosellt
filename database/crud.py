from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import CartItem, Category, Order, Payment, Product, ProductItem, PromoCode, PromoCodeUsage, SupportTicket, User


async def get_or_create_user(session: AsyncSession, user_id: int, username: str | None, full_name: str) -> User:
    user = await session.get(User, user_id)
    if user:
        user.username = username
        user.full_name = full_name
        await session.commit()
        return user

    user = User(id=user_id, username=username, full_name=full_name)
    session.add(user)
    await session.commit()
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def set_user_blocked(session: AsyncSession, user_id: int, blocked: bool) -> bool:
    user = await session.get(User, user_id)
    if not user:
        return False
    user.is_blocked = blocked
    await session.commit()
    return True


async def change_user_balance(session: AsyncSession, user_id: int, amount: Decimal) -> bool:
    user = await session.get(User, user_id)
    if not user:
        return False
    user.balance = max(Decimal('0.00'), Decimal(user.balance) + amount)
    await session.commit()
    return True


async def get_stats(session: AsyncSession) -> dict:
    users_count = int((await session.execute(select(func.count(User.id)))).scalar() or 0)
    products_count = int((await session.execute(select(func.count(Product.id)))).scalar() or 0)
    orders_count = int((await session.execute(select(func.count(Order.id)))).scalar() or 0)
    paid_sum = Decimal((await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == 'paid'))).scalar() or 0)
    return {
        'users_count': users_count,
        'products_count': products_count,
        'orders_count': orders_count,
        'paid_sum': paid_sum,
    }


async def create_category(session: AsyncSession, title: str) -> Category:
    category = Category(title=title.strip())
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def get_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(select(Category).order_by(Category.title.asc()))
    return list(result.scalars().all())


async def create_product(session: AsyncSession, title: str, description: str, price: Decimal, category_id: int | None = None) -> Product:
    product = Product(title=title, description=description, price=price, category_id=category_id)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def update_product_field(session: AsyncSession, product_id: int, field: str, value) -> bool:
    product = await session.get(Product, product_id)
    if not product or field not in {'title', 'description', 'price', 'discount_percent'}:
        return False
    setattr(product, field, value)
    await session.commit()
    return True


async def clear_unsold_items(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(select(ProductItem).where(ProductItem.product_id == product_id, ProductItem.is_sold.is_(False)))
    items = list(result.scalars().all())
    count = len(items)
    for item in items:
        await session.delete(item)
    await session.commit()
    return count


async def update_product_status(session: AsyncSession, product_id: int, is_active: bool) -> bool:
    product = await session.get(Product, product_id)
    if not product:
        return False
    product.is_active = is_active
    await session.commit()
    return True


async def get_active_products(session: AsyncSession, category_id: int | None = None, search: str | None = None) -> list[Product]:
    query = select(Product).where(Product.is_active.is_(True)).options(selectinload(Product.category)).order_by(Product.id.desc())
    if category_id:
        query = query.where(Product.category_id == category_id)
    if search:
        pattern = f'%{search.strip()}%'
        query = query.where(or_(Product.title.ilike(pattern), Product.description.ilike(pattern)))
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_all_products(session: AsyncSession) -> list[Product]:
    result = await session.execute(select(Product).options(selectinload(Product.category)).order_by(Product.id.desc()))
    return list(result.scalars().all())


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.items), selectinload(Product.category))
    )
    return result.scalar_one_or_none()


async def add_product_items(session: AsyncSession, product_id: int, items: list[str]) -> int:
    product = await session.get(Product, product_id)
    if not product:
        return 0
    entities = [ProductItem(product_id=product_id, content=item.strip()) for item in items if item.strip()]
    session.add_all(entities)
    await session.commit()
    return len(entities)


async def get_product_stock(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        select(func.count(ProductItem.id)).where(
            ProductItem.product_id == product_id,
            ProductItem.is_sold.is_(False),
        )
    )
    return int(result.scalar() or 0)


def calculate_discounted_price(price: Decimal, discount_percent: int) -> Decimal:
    if discount_percent <= 0:
        return Decimal(price)
    discount = (Decimal(price) * Decimal(discount_percent)) / Decimal('100')
    return (Decimal(price) - discount).quantize(Decimal('0.01'))


async def buy_product(session: AsyncSession, user_id: int, product_id: int) -> tuple[bool, str, Order | None]:
    user = await session.get(User, user_id)
    product = await session.get(Product, product_id)

    if not user:
        return False, 'Пользователь не найден.', None
    if user.is_blocked:
        return False, 'Ваш аккаунт заблокирован.', None
    if not product or not product.is_active:
        return False, 'Товар недоступен.', None

    result = await session.execute(
        select(ProductItem)
        .where(ProductItem.product_id == product_id, ProductItem.is_sold.is_(False))
        .limit(1)
    )
    item = result.scalar_one_or_none()
    if not item:
        return False, 'Товар закончился.', None

    final_price = calculate_discounted_price(Decimal(product.price), int(product.discount_percent))
    if Decimal(user.balance) < final_price:
        return False, 'Недостаточно средств.', None

    user.balance = Decimal(user.balance) - final_price
    item.is_sold = True
    item.sold_at = datetime.utcnow()

    order = Order(
        user_id=user_id,
        product_id=product_id,
        product_item_id=item.id,
        amount=final_price,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    result = await session.execute(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.product), selectinload(Order.product_item))
    )
    return True, 'Покупка успешно завершена.', result.scalar_one()


async def add_to_cart(session: AsyncSession, user_id: int, product_id: int) -> bool:
    product = await session.get(Product, product_id)
    if not product or not product.is_active:
        return False
    result = await session.execute(select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id))
    cart_item = result.scalar_one_or_none()
    if cart_item:
        cart_item.quantity += 1
    else:
        session.add(CartItem(user_id=user_id, product_id=product_id, quantity=1))
    await session.commit()
    return True


async def get_cart_items(session: AsyncSession, user_id: int) -> list[CartItem]:
    result = await session.execute(select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.id.asc()))
    return list(result.scalars().all())


async def update_cart_quantity(session: AsyncSession, cart_item_id: int, user_id: int, quantity: int) -> bool:
    item = await session.get(CartItem, cart_item_id)
    if not item or item.user_id != user_id:
        return False
    if quantity <= 0:
        await session.delete(item)
    else:
        item.quantity = quantity
    await session.commit()
    return True


async def remove_cart_item(session: AsyncSession, cart_item_id: int, user_id: int) -> bool:
    item = await session.get(CartItem, cart_item_id)
    if not item or item.user_id != user_id:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def clear_cart(session: AsyncSession, user_id: int) -> None:
    result = await session.execute(select(CartItem).where(CartItem.user_id == user_id))
    items = list(result.scalars().all())
    for item in items:
        await session.delete(item)
    await session.commit()


async def buy_cart(session: AsyncSession, user_id: int) -> tuple[bool, str, list[Order]]:
    cart_items = await get_cart_items(session, user_id)
    if not cart_items:
        return False, 'Корзина пуста.', []

    orders: list[Order] = []
    for cart_item in cart_items:
        for _ in range(cart_item.quantity):
            success, text, order = await buy_product(session, user_id, cart_item.product_id)
            if not success:
                return False, text, orders
            if order:
                orders.append(order)
    await clear_cart(session, user_id)
    return True, 'Покупка корзины завершена.', orders


async def get_user_orders(session: AsyncSession, user_id: int) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .options(selectinload(Order.product), selectinload(Order.product_item))
    )
    return list(result.scalars().all())


async def get_order(session: AsyncSession, order_id: int, user_id: int | None = None) -> Order | None:
    query = select(Order).where(Order.id == order_id).options(selectinload(Order.product), selectinload(Order.product_item))
    if user_id is not None:
        query = query.where(Order.user_id == user_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_payment(session: AsyncSession, user_id: int, amount: Decimal, method: str, external_id: str | None = None) -> Payment:
    payment = Payment(user_id=user_id, amount=amount, method=method, external_id=external_id)
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_payment_by_external_id(session: AsyncSession, external_id: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.external_id == external_id))
    return result.scalar_one_or_none()


async def get_user_payments(session: AsyncSession, user_id: int) -> list[Payment]:
    result = await session.execute(select(Payment).where(Payment.user_id == user_id).order_by(Payment.id.desc()))
    return list(result.scalars().all())


async def create_promo_code(session: AsyncSession, code: str, amount: Decimal, max_uses: int) -> PromoCode:
    promo = PromoCode(code=code.strip().upper(), amount=amount, max_uses=max_uses)
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def get_promo_code(session: AsyncSession, code: str) -> PromoCode | None:
    result = await session.execute(select(PromoCode).where(PromoCode.code == code.strip().upper()))
    return result.scalar_one_or_none()


async def apply_promo_code(session: AsyncSession, user_id: int, code: str) -> tuple[bool, str, Decimal | None]:
    promo = await get_promo_code(session, code)
    if not promo or not promo.is_active:
        return False, 'Промокод не найден или неактивен.', None
    if promo.uses_count >= promo.max_uses:
        return False, 'Лимит использований промокода исчерпан.', None

    usage_check = await session.execute(
        select(PromoCodeUsage).where(PromoCodeUsage.promo_code_id == promo.id, PromoCodeUsage.user_id == user_id)
    )
    if usage_check.scalar_one_or_none():
        return False, 'Вы уже использовали этот промокод.', None

    user = await session.get(User, user_id)
    if not user:
        return False, 'Пользователь не найден.', None

    user.balance = Decimal(user.balance) + Decimal(promo.amount)
    promo.uses_count += 1
    session.add(PromoCodeUsage(promo_code_id=promo.id, user_id=user_id))
    if promo.uses_count >= promo.max_uses:
        promo.is_active = False
    await session.commit()
    return True, 'Промокод успешно активирован.', Decimal(promo.amount)


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.id).where(User.is_blocked.is_(False)))
    return list(result.scalars().all())


async def set_referrer(session: AsyncSession, user_id: int, referrer_id: int) -> bool:
    if user_id == referrer_id:
        return False
    user = await session.get(User, user_id)
    referrer = await session.get(User, referrer_id)
    if not user or not referrer or user.referred_by:
        return False
    user.referred_by = referrer_id
    await session.commit()
    return True


async def reward_referrer_for_payment(session: AsyncSession, payment_id: int, percent: Decimal = Decimal('5.00')) -> None:
    payment = await session.get(Payment, payment_id)
    if not payment or payment.status != 'paid':
        return
    user = await session.get(User, payment.user_id)
    if not user or not user.referred_by:
        return
    referrer = await session.get(User, user.referred_by)
    if not referrer:
        return
    bonus = (Decimal(payment.amount) * percent) / Decimal('100')
    referrer.balance = Decimal(referrer.balance) + bonus.quantize(Decimal('0.01'))
    await session.commit()


async def create_support_ticket(session: AsyncSession, user_id: int, message_text: str) -> SupportTicket:
    ticket = SupportTicket(user_id=user_id, message_text=message_text)
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def reply_support_ticket(session: AsyncSession, ticket_id: int, reply_text: str) -> SupportTicket | None:
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket:
        return None
    ticket.admin_reply = reply_text
    ticket.status = 'closed'
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_support_tickets(session: AsyncSession, status: str | None = None) -> list[SupportTicket]:
    query = select(SupportTicket).order_by(SupportTicket.id.desc())
    if status:
        query = query.where(SupportTicket.status == status)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_support_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket | None:
    return await session.get(SupportTicket, ticket_id)


async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.id.asc()))
    return list(result.scalars().all())


async def get_all_orders(session: AsyncSession) -> list[Order]:
    result = await session.execute(
        select(Order).order_by(Order.id.asc()).options(selectinload(Order.product), selectinload(Order.user))
    )
    return list(result.scalars().all())


async def get_all_payments(session: AsyncSession) -> list[Payment]:
    result = await session.execute(select(Payment).order_by(Payment.id.asc()))
    return list(result.scalars().all())


async def mark_payment_paid(session: AsyncSession, payment_id: int) -> Payment | None:
    payment = await session.get(Payment, payment_id)
    if not payment or payment.status == 'paid':
        return payment
    payment.status = 'paid'
    user = await session.get(User, payment.user_id)
    if user:
        user.balance = Decimal(user.balance) + Decimal(payment.amount)
    await session.commit()
    await reward_referrer_for_payment(session, payment.id)
    return payment
