from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


LANGUAGES = ("zh", "en", "ru")

LANGUAGE_BUTTONS = (
    ("zh", "🇨🇳 中文"),
    ("en", "🇺🇸 English"),
    ("ru", "🇷🇺 Русский"),
)


TEXTS: dict[str, dict[str, str]] = {
    "choose_language": {
        "zh": "请选择语言：",
        "en": "Please choose a language:",
        "ru": "Выберите язык:",
    },
    "language_saved": {
        "zh": "语言已更改。",
        "en": "Language changed.",
        "ru": "Язык изменён.",
    },
    "welcome": {
        "zh": "欢迎！请选择商品或打开菜单。",
        "en": "Welcome! Choose a product or open the menu.",
        "ru": "Добро пожаловать! Выберите товар или раздел меню.",
    },
    "unknown_command": {
        "zh": "请使用菜单中的按钮。",
        "en": "Please use one of the menu buttons.",
        "ru": "Пожалуйста, используйте кнопки меню.",
    },
    "choose_pro_plan": {
        "zh": "请选择 Pro 套餐：",
        "en": "Choose a Pro plan:",
        "ru": "Выберите тариф Pro:",
    },
    "choose_plus_plan": {
        "zh": "请选择 Plus 账号类型：",
        "en": "Choose a Plus account type:",
        "ru": "Выберите тип аккаунта Plus:",
    },
    "balance": {
        "zh": "💰 余额：{balance}\n\n你可以通过 Crypto Pay 充值。",
        "en": "💰 Balance: {balance}\n\nYou can top up using Crypto Pay.",
        "ru": "💰 Баланс: {balance}\n\nПополнить баланс можно через Crypto Pay.",
    },
    "top_up": {
        "zh": "💳 选择充值金额：",
        "en": "💳 Choose a top-up amount:",
        "ru": "💳 Выберите сумму пополнения:",
    },
    "top_up_other": {
        "zh": "请输入充值金额（USD）：",
        "en": "Enter a top-up amount in USD:",
        "ru": "Введите сумму пополнения в USD:",
    },
    "top_up_invalid": {
        "zh": "请输入有效金额，例如 2.50。",
        "en": "Enter a valid amount, for example 2.50.",
        "ru": "Введите корректную сумму, например 2.50.",
    },
    "top_up_invoice": {
        "zh": "充值账单已创建：{amount}\nCrypto Pay 账单：{usd_amount}\n点击下方按钮完成支付。\n支付成功后余额会自动更新。",
        "en": "Top-up invoice created: {amount}\nCrypto Pay invoice: {usd_amount}\nTap the button below to pay.\nYour balance will update automatically after payment.",
        "ru": "Счёт на пополнение создан: {amount}\nСчёт Crypto Pay: {usd_amount}\nНажмите кнопку ниже для оплаты.\nПосле оплаты баланс обновится автоматически.",
    },
    "product_invoice": {
        "zh": "商品：{product}\n显示价格：{amount}\nCrypto Pay 账单：{usd_amount}\n\n点击下方按钮用加密货币支付。",
        "en": "Product: {product}\nDisplayed price: {amount}\nCrypto Pay invoice: {usd_amount}\n\nTap the button below to pay with crypto.",
        "ru": "Товар: {product}\nЦена: {amount}\nСчёт Crypto Pay: {usd_amount}\n\nНажмите кнопку ниже для оплаты криптовалютой.",
    },
    "pay": {
        "zh": "💳 支付",
        "en": "💳 Pay",
        "ru": "💳 Оплатить",
    },
    "pay_balance": {
        "zh": "💰 使用余额支付",
        "en": "💰 Pay with balance",
        "ru": "💰 Оплатить с баланса",
    },
    "balance_insufficient": {
        "zh": "余额不足，请先充值。",
        "en": "Insufficient balance. Please top up first.",
        "ru": "Недостаточно средств на балансе. Сначала пополните его.",
    },
    "check_payment": {
        "zh": "🔄 Проверить оплату",
        "en": "🔄 Check payment",
        "ru": "🔄 Проверить оплату",
    },
    "payment_pending": {
        "zh": "付款尚未确认。完成支付后再次点击检查。",
        "en": "The payment is not confirmed yet. Complete the payment and check again.",
        "ru": "Оплата ещё не подтверждена. Завершите оплату и проверьте ещё раз.",
    },
    "payment_expired": {
        "zh": "账单已过期。请重新创建订单。",
        "en": "The invoice has expired. Please create a new order.",
        "ru": "Счёт истёк. Создайте новый заказ.",
    },
    "payment_confirmed": {
        "zh": "付款已确认，商品将在几秒内发送。",
        "en": "Payment confirmed. Your item will be delivered in a few seconds.",
        "ru": "Оплата подтверждена. Товар будет отправлен в течение нескольких секунд.",
    },
    "top_up_confirmed": {
        "zh": "充值已确认，余额将在几秒内更新。",
        "en": "Top-up confirmed. Your balance will update in a few seconds.",
        "ru": "Пополнение подтверждено. Баланс обновится в течение нескольких секунд.",
    },
    "product_out_of_stock": {
        "zh": "此商品暂时缺货。",
        "en": "This product is temporarily out of stock.",
        "ru": "Этого товара сейчас нет в наличии.",
    },
    "stock": {
        "zh": "🔄 库存情况：\n\nChatGPT Plus NW：{plus_nw}\nChatGPT Plus FW：{plus_fw}\nGPT Pro/5x NW：{pro5_nw}\nGPT Pro/20x NW：{pro20_nw}",
        "en": "🔄 Availability:\n\nChatGPT Plus NW: {plus_nw}\nChatGPT Plus FW: {plus_fw}\nGPT Pro/5x NW: {pro5_nw}\nGPT Pro/20x NW: {pro20_nw}",
        "ru": "🔄 Наличие:\n\nChatGPT Plus NW: {plus_nw}\nChatGPT Plus FW: {plus_fw}\nGPT Pro/5x NW: {pro5_nw}\nGPT Pro/20x NW: {pro20_nw}",
    },
    "queue": {
        "zh": "🕒 排队\n\n您可以提前预订账号。账号重新到货后，系统将自动为您发放。",
        "en": "🕒 Queue\n\nYou can reserve an account in advance. Once it is back in stock, the system will automatically deliver it to you.",
        "ru": "🕒 Очередь\n\nВы можете заранее зарезервировать аккаунт. Когда аккаунт снова появится в наличии, система автоматически выдаст его вам.",
    },
    "queue_choose_quantity": {
        "zh": "请选择数量：",
        "en": "Choose a quantity:",
        "ru": "Выберите количество:",
    },
    "queue_invoice": {
        "zh": "🕒 排队订单\n商品：{product}\n数量：{quantity}\n价格：{amount}\nCrypto Pay 账单：{usd_amount}\n\n点击下方按钮完成付款。账号重新到货后，系统将自动为您发放。",
        "en": "🕒 Queue order\nProduct: {product}\nQuantity: {quantity}\nPrice: {amount}\nCrypto Pay invoice: {usd_amount}\n\nTap the button below to pay. Once the account is back in stock, the system will automatically deliver it to you.",
        "ru": "🕒 Заказ в очереди\nТовар: {product}\nКоличество: {quantity}\nЦена: {amount}\nСчёт Crypto Pay: {usd_amount}\n\nНажмите кнопку ниже для оплаты. Когда аккаунт снова появится в наличии, система автоматически выдаст его вам.",
    },
    "queue_added": {
        "zh": "✅ 已加入等待名单：{product}\n商品到货后我们会自动通知你。",
        "en": "✅ Added to the waitlist: {product}\nWe will notify you automatically when it is available.",
        "ru": "✅ Вы добавлены в очередь: {product}\nМы автоматически уведомим вас, когда товар появится.",
    },
    "queue_already": {
        "zh": "你已经在等待名单中：{product}。",
        "en": "You are already on the waitlist for: {product}.",
        "ru": "Вы уже стоите в очереди на: {product}.",
    },
    "queue_available": {
        "zh": "🎉 商品已到货：{product}\n现在可以购买。",
        "en": "🎉 Back in stock: {product}\nYou can purchase it now.",
        "ru": "🎉 Товар появился в наличии: {product}\nТеперь его можно купить.",
    },
    "no_stock_after_payment": {
        "zh": "付款已收到，但该商品暂时缺货。请联系 {support}，我们会尽快处理订单。",
        "en": "Payment received, but the item is temporarily out of stock. Contact {support} and we will process the order as soon as possible.",
        "ru": "Оплата получена, но товар временно закончился. Напишите {support}, и мы обработаем заказ как можно скорее.",
    },
    "delivery_account": {
        "zh": "✅ 订单已完成\n商品：{product}\n\n你的数字商品：\n<pre>{payload}</pre>\n\n请不要把这些数据发送给其他人。",
        "en": "✅ Order completed\nProduct: {product}\n\nYour digital item:\n<pre>{payload}</pre>\n\nDo not share these details with anyone.",
        "ru": "✅ Заказ выполнен\nТовар: {product}\n\nВаш цифровой товар:\n<pre>{payload}</pre>\n\nНе передавайте эти данные другим людям.",
    },
    "delivery_balance": {
        "zh": "✅ 充值成功\n余额增加：{amount}\n当前余额：{balance}",
        "en": "✅ Top-up completed\nAdded: {amount}\nCurrent balance: {balance}",
        "ru": "✅ Пополнение выполнено\nЗачислено: {amount}\nТекущий баланс: {balance}",
    },
    "invite": {
        "zh": "账号GPT Plus/Pro顶级品质\n\n🔗 邀请朋友使用机器人：\n{link}",
        "en": "账号GPT Plus/Pro顶级品质\n\n🔗 Invite friends to the bot:\n{link}",
        "ru": "账号GPT Plus/Pro顶级品质\n\n🔗 Приглашайте друзей в бота:\n{link}",
    },
    "help": {
        "zh": "📖 帮助\n\n客服：{support}\n请使用下方按钮查看销售条款和隐私政策。",
        "en": "📖 Help\n\nSupport: {support}\nUse the buttons below to view the Terms of Sale and Privacy Policy.",
        "ru": "📖 Помощь\n\nПоддержка: {support}\nИспользуйте кнопки ниже, чтобы открыть оферту и политику конфиденциальности.",
    },
    "payment_error": {
        "zh": "无法创建账单。请稍后再试或联系 {support}。",
        "en": "Could not create the invoice. Try again later or contact {support}.",
        "ru": "Не удалось создать счёт. Попробуйте позже или напишите {support}.",
    },
    "generic_error": {
        "zh": "发生错误，请稍后再试。",
        "en": "Something went wrong. Please try again later.",
        "ru": "Произошла ошибка. Попробуйте позже.",
    },
    "admin_only": {
        "zh": "此命令仅管理员可用。",
        "en": "This command is available to admins only.",
        "ru": "Эта команда доступна только администраторам.",
    },
    "admin_good_added": {
        "zh": "商品已加入库存：{product}，编号 {good_id}。",
        "en": "Item added to stock: {product}, ID {good_id}.",
        "ru": "Товар добавлен на склад: {product}, ID {good_id}.",
    },
    "admin_add_usage": {
        "zh": "用法：/add_good <gpt_plus_nw|gpt_plus_fw|pro_5x_nw|pro_20x_nw> <digital item>。",
        "en": "Usage: /add_good <gpt_plus_nw|gpt_plus_fw|pro_5x_nw|pro_20x_nw> <digital item>.",
        "ru": "Использование: /add_good <gpt_plus_nw|gpt_plus_fw|pro_5x_nw|pro_20x_nw> <цифровой товар>.",
    },
    "admin_stock": {
        "zh": "库存：\n{stock}",
        "en": "Stock:\n{stock}",
        "ru": "Остатки:\n{stock}",
    },
    "stock_empty": {
        "zh": "库存为空。",
        "en": "Stock is empty.",
        "ru": "Склад пуст.",
    },
}


MENU_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "plus": "⚡GPT Plus",
        "pro": "🚀 Pro",
        "balance": "💰余额",
        "invite": "🔗邀请",
        "stock": "🔄检查库存",
        "queue": "🕒排队",
        "help": "📖帮助",
        "language": "🌐语言",
    },
    "en": {
        "plus": "⚡GPT Plus",
        "pro": "🚀 Pro",
        "balance": "💰Balance",
        "invite": "🔗Invite",
        "stock": "🔄Check stock",
        "queue": "🕒Queue",
        "help": "📖Help",
        "language": "🌐Language",
    },
    "ru": {
        "plus": "⚡GPT Plus",
        "pro": "🚀Pro",
        "balance": "💰Баланс",
        "invite": "🔗Пригласить",
        "stock": "🔄Проверить наличие",
        "queue": "🕒Очередь",
        "help": "📖Помощь",
        "language": "🌐Язык",
    },
}


def t(language: str | None, key: str, **kwargs: object) -> str:
    language = language if language in LANGUAGES else "en"
    template = TEXTS[key][language]
    return template.format(**kwargs)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"lang:{code}") for code, label in LANGUAGE_BUTTONS]
        ]
    )


def main_keyboard(language: str) -> ReplyKeyboardMarkup:
    labels = MENU_LABELS[language if language in LANGUAGES else "en"]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=labels["plus"]), KeyboardButton(text=labels["pro"])],
            [KeyboardButton(text=labels["balance"]), KeyboardButton(text=labels["invite"])],
            [KeyboardButton(text=labels["stock"]), KeyboardButton(text=labels["queue"])],
            [KeyboardButton(text=labels["help"]), KeyboardButton(text=labels["language"])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def help_keyboard(
    language: str,
    support_url: str,
    offer_url: str,
    privacy_url: str,
) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {
        "zh": {"offer": "📄 销售条款", "privacy": "🔒 隐私政策"},
        "en": {"offer": "📄 Terms of Sale", "privacy": "🔒 Privacy Policy"},
        "ru": {"offer": "📄 Оферта", "privacy": "🔒 Политика конфиденциальности"},
    }[language]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="@admingpt", url=support_url)],
            [InlineKeyboardButton(text=labels["offer"], url=offer_url)],
            [InlineKeyboardButton(text=labels["privacy"], url=privacy_url)],
        ]
    )


def balance_keyboard(language: str) -> InlineKeyboardMarkup:
    labels = {
        "zh": "💳 充值",
        "en": "💳 Top up",
        "ru": "💳 Пополнить",
    }
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=labels[language], callback_data="topup")],
        ]
    )


def top_up_keyboard(language: str, amount_labels: dict[int, str] | None = None) -> InlineKeyboardMarkup:
    labels = {
        "zh": "充值 {amount}",
        "en": "Top up {amount}",
        "ru": "Пополнить {amount}",
    }
    other_labels = {"zh": "其他", "en": "Other", "ru": "Другая сумма"}
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=labels[language].format(
                        amount=(amount_labels or {}).get(amount, f"${amount:.2f}")
                    ),
                    callback_data=f"topup:{amount * 100}",
                )
                for amount in (2, 5)
            ],
            [
                InlineKeyboardButton(
                    text=labels[language].format(
                        amount=(amount_labels or {}).get(10, "$10.00")
                    ),
                    callback_data="topup:1000",
                ),
                InlineKeyboardButton(
                    text=other_labels[language],
                    callback_data="topup:other",
                )
            ],
        ]
    )


def _with_price(label: str, product_key: str, prices: dict[str, str] | None) -> str:
    if prices and product_key in prices:
        return f"{label} · {prices[product_key]}"
    return label


def plus_keyboard(language: str, prices: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {
        "zh": {"nw": "⚡ Plus NW", "fw": "⚡ Plus FW"},
        "en": {"nw": "⚡ Plus NW", "fw": "⚡ Plus FW"},
        "ru": {"nw": "⚡ Plus NW", "fw": "⚡ Plus FW"},
    }[language]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_with_price(labels["nw"], "gpt_plus_nw", prices),
                    callback_data="product:gpt_plus_nw",
                ),
                InlineKeyboardButton(
                    text=_with_price(labels["fw"], "gpt_plus_fw", prices),
                    callback_data="product:gpt_plus_fw",
                ),
            ]
        ]
    )


def pro_keyboard(language: str, prices: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {
        "zh": {"5": "🚀 Pro 5x NW", "20": "🚀 Pro 20x NW"},
        "en": {"5": "🚀 Pro 5x NW", "20": "🚀 Pro 20x NW"},
        "ru": {"5": "🚀 Pro 5x NW", "20": "🚀 Pro 20x NW"},
    }[language]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_with_price(labels["5"], "pro_5x_nw", prices),
                    callback_data="product:pro_5x_nw",
                ),
                InlineKeyboardButton(
                    text=_with_price(labels["20"], "pro_20x_nw", prices),
                    callback_data="product:pro_20x_nw",
                ),
            ]
        ]
    )


def queue_keyboard(language: str, prices: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {
        "zh": {
            "plus_nw": "ChatGPT Plus NW",
            "plus_fw": "ChatGPT Plus FW",
            "pro5_nw": "GPT Pro/5x NW",
            "pro20_nw": "GPT Pro/20x NW",
        },
        "en": {
            "plus_nw": "ChatGPT Plus NW",
            "plus_fw": "ChatGPT Plus FW",
            "pro5_nw": "GPT Pro/5x NW",
            "pro20_nw": "GPT Pro/20x NW",
        },
        "ru": {
            "plus_nw": "ChatGPT Plus NW",
            "plus_fw": "ChatGPT Plus FW",
            "pro5_nw": "GPT Pro/5x NW",
            "pro20_nw": "GPT Pro/20x NW",
        },
    }[language]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_with_price(labels["plus_nw"], "gpt_plus_nw", prices),
                    callback_data="queue:gpt_plus_nw",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["plus_fw"], "gpt_plus_fw", prices),
                    callback_data="queue:gpt_plus_fw",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["pro5_nw"], "pro_5x_nw", prices),
                    callback_data="queue:pro_5x_nw",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["pro20_nw"], "pro_20x_nw", prices),
                    callback_data="queue:pro_20x_nw",
                )
            ],
        ]
    )


def queue_purchase_keyboard(language: str, product_key: str) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "pay"), callback_data=f"buy:{product_key}")],
        ]
    )


def queue_quantity_keyboard(language: str, product_key: str) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {"zh": "数量 {quantity}", "en": "Quantity {quantity}", "ru": "Количество {quantity}"}
    quantities = (1, 2, 3, 5)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=labels[language].format(quantity=quantity),
                    callback_data=f"queue_qty:{product_key}:{quantity}",
                )
                for quantity in quantities[:2]
            ],
            [
                InlineKeyboardButton(
                    text=labels[language].format(quantity=quantity),
                    callback_data=f"queue_qty:{product_key}:{quantity}",
                )
                for quantity in quantities[2:]
            ],
        ]
    )


def queue_payment_keyboard(
    language: str,
    invoice_url: str,
    order_id: int | None = None,
    show_balance_payment: bool = False,
) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    rows = [[InlineKeyboardButton(text=t(language, "pay"), url=invoice_url)]]
    if order_id is not None:
        if show_balance_payment:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=t(language, "pay_balance"),
                        callback_data=f"balance_pay:{order_id}",
                    )
                ]
            )
        rows.append(
            [InlineKeyboardButton(text=t(language, "check_payment"), callback_data=f"check:{order_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_button_keyboard(language: str, product_key: str) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    labels = {"zh": "🕒 加入排队", "en": "🕒 Join queue", "ru": "🕒 В очередь"}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=labels[language], callback_data=f"queue:{product_key}")],
        ]
    )


def payment_keyboard(
    language: str,
    invoice_url: str,
    order_id: int,
    product_key: str | None = None,
    show_balance_payment: bool = False,
) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    rows = [
        [InlineKeyboardButton(text=t(language, "pay"), url=invoice_url)],
    ]
    if show_balance_payment:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(language, "pay_balance"),
                    callback_data=f"balance_pay:{order_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=t(language, "check_payment"), callback_data=f"check:{order_id}")]
    )
    if product_key is not None:
        buy_many_labels = {
            "zh": "🛒 购买多个",
            "en": "🛒 Buy several",
            "ru": "🛒 Купить несколько",
        }
        rows.append(
            [
                InlineKeyboardButton(
                    text=buy_many_labels[language],
                    callback_data=f"buy_many:{product_key}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def action_for_text(language: str, message_text: str) -> str | None:
    labels = MENU_LABELS[language if language in LANGUAGES else "en"]
    for action, label in labels.items():
        if label == message_text:
            return action
    return None
