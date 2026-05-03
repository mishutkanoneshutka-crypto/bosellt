from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_for_query = State()


class PromoStates(StatesGroup):
    waiting_for_code = State()


class SupportStates(StatesGroup):
    waiting_for_message = State()


class AdminTicketReplyStates(StatesGroup):
    waiting_for_ticket_id = State()
    waiting_for_reply = State()


class TopUpStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_method = State()


class AdminAddCategoryStates(StatesGroup):
    waiting_for_title = State()


class AdminAddProductStates(StatesGroup):
    waiting_for_category_id = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()


class AdminAddItemsStates(StatesGroup):
    waiting_for_product_id = State()
    waiting_for_items = State()


class AdminToggleProductStates(StatesGroup):
    waiting_for_product_id = State()


class AdminBlockUserStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_action = State()


class AdminBalanceStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()


class AdminPromoStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_amount = State()
    waiting_for_max_uses = State()


class AdminBroadcastStates(StatesGroup):
    waiting_for_text = State()


class AdminFileUploadStates(StatesGroup):
    waiting_for_product_id = State()
    waiting_for_document = State()


class AdminExportStates(StatesGroup):
    waiting_for_type = State()


class AdminEditProductStates(StatesGroup):
    waiting_for_product_id = State()
    waiting_for_field = State()
    waiting_for_value = State()


class AdminClearStockStates(StatesGroup):
    waiting_for_product_id = State()
