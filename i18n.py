from __future__ import annotations

from aiogram.enums import ButtonStyle
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
    "mpay_method": {
        "zh": "请选择支付方式，金额 {amount}：\n\n• Crypto Pay — 自动入账，速度最快。\n• 加密货币转账 — 直接转到我们的钱包，管理员核对后入账。",
        "en": "Choose how to pay {amount}:\n\n• Crypto Pay — credited automatically, fastest.\n• Crypto transfer — send straight to our wallet; an admin verifies it and then credits you.",
        "ru": "Выберите способ оплаты на сумму {amount}:\n\n• Crypto Pay — зачисление автоматическое, это быстрее всего.\n• Перевод криптовалютой — напрямую на наш кошелёк, админ сверяет перевод и зачисляет.",
    },
    "mpay_choose_asset": {
        "zh": "请选择币种（金额 {amount}）：",
        "en": "Choose a coin (amount: {amount}):",
        "ru": "Выберите монету (сумма: {amount}):",
    },
    "mpay_choose_network": {
        "zh": "{asset} 支持多个网络。请选择您钱包实际使用的网络：\n\n⚠️ 网络选错，资金将无法找回。",
        "en": "{asset} works on several networks. Pick the one your wallet actually uses:\n\n⚠️ Send on the wrong network and the funds cannot be recovered.",
        "ru": "{asset} работает в нескольких сетях. Выберите ту, которой реально пользуется ваш кошелёк:\n\n⚠️ Перевод в неверной сети вернуть невозможно.",
    },
    "mpay_instructions": {
        "zh": (
            "💸 转账明细 #{payment_id}\n\n"
            "币种：<b>{asset}</b>\n"
            "网络：<b>{network}</b>\n"
            "转账金额：<b>{crypto_amount} {asset}</b>\n"
            "折合：{fiat_amount}\n"
            "汇率：1 {asset} = {rate}（{rate_at} UTC）\n\n"
            "收款地址：\n<code>{address}</code>\n\n"
            "⚠️ 请务必使用 <b>{network}</b> 网络，其他网络的转账无法找回。\n"
            "转账完成后请发送交易哈希（tx hash），管理员核对链上记录后为您入账。\n"
            "本页面有效期 {hours} 小时。"
        ),
        "en": (
            "💸 Transfer details #{payment_id}\n\n"
            "Coin: <b>{asset}</b>\n"
            "Network: <b>{network}</b>\n"
            "Amount to send: <b>{crypto_amount} {asset}</b>\n"
            "Equivalent: {fiat_amount}\n"
            "Rate: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "Address:\n<code>{address}</code>\n\n"
            "⚠️ Use the <b>{network}</b> network. A transfer on any other network cannot be recovered.\n"
            "Send the transaction hash once the transfer is done; an admin checks it on-chain and credits you.\n"
            "This request is valid for {hours} hours."
        ),
        "ru": (
            "💸 Реквизиты перевода #{payment_id}\n\n"
            "Монета: <b>{asset}</b>\n"
            "Сеть: <b>{network}</b>\n"
            "Сумма перевода: <b>{crypto_amount} {asset}</b>\n"
            "Это примерно {fiat_amount}\n"
            "Курс: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "Адрес:\n<code>{address}</code>\n\n"
            "⚠️ Переводите только в сети <b>{network}</b>. Перевод в другой сети вернуть нельзя.\n"
            "После перевода отправьте хеш транзакции — админ сверит его в блокчейне и зачислит сумму.\n"
            "Реквизиты действительны {hours} ч."
        ),
    },
    "mpay_instructions_no_rate": {
        "zh": (
            "💸 转账明细 #{payment_id}\n\n"
            "币种：<b>{asset}</b>\n"
            "网络：<b>{network}</b>\n"
            "应付金额：<b>{fiat_amount}</b>\n\n"
            "收款地址：\n<code>{address}</code>\n\n"
            "ℹ️ 机器人暂时无法获取 {asset} 的汇率，因此无法显示精确的币种数量。"
            "请按当前市场价转入等值金额，管理员将按到账时的汇率核对。\n"
            "⚠️ 请务必使用 <b>{network}</b> 网络，其他网络的转账无法找回。\n"
            "转账完成后请发送交易哈希（tx hash）。\n"
            "本页面有效期 {hours} 小时。"
        ),
        "en": (
            "💸 Transfer details #{payment_id}\n\n"
            "Coin: <b>{asset}</b>\n"
            "Network: <b>{network}</b>\n"
            "Amount owed: <b>{fiat_amount}</b>\n\n"
            "Address:\n<code>{address}</code>\n\n"
            "ℹ️ The bot has no rate for {asset} right now, so it cannot show an exact coin amount. "
            "Send the equivalent at the current market rate; the admin will check it against the rate at the time it arrives.\n"
            "⚠️ Use the <b>{network}</b> network. A transfer on any other network cannot be recovered.\n"
            "Send the transaction hash once the transfer is done.\n"
            "This request is valid for {hours} hours."
        ),
        "ru": (
            "💸 Реквизиты перевода #{payment_id}\n\n"
            "Монета: <b>{asset}</b>\n"
            "Сеть: <b>{network}</b>\n"
            "К оплате: <b>{fiat_amount}</b>\n\n"
            "Адрес:\n<code>{address}</code>\n\n"
            "ℹ️ Бот сейчас не знает курс {asset}, поэтому не может показать точное количество монет. "
            "Переведите эквивалент по текущему рыночному курсу — админ сверит сумму по курсу на момент зачисления.\n"
            "⚠️ Переводите только в сети <b>{network}</b>. Перевод в другой сети вернуть нельзя.\n"
            "После перевода отправьте хеш транзакции.\n"
            "Реквизиты действительны {hours} ч."
        ),
    },
    "mpay_ask_hash": {
        "zh": "请发送这笔转账的交易哈希（tx hash）。\n可在钱包的交易记录或区块浏览器中找到。",
        "en": "Send the transaction hash for this transfer.\nYou will find it in your wallet history or on a block explorer.",
        "ru": "Отправьте хеш транзакции по этому переводу.\nОн есть в истории кошелька или в блокчейн-обозревателе.",
    },
    "mpay_hash_invalid": {
        "zh": "这看起来不像交易哈希。请发送钱包中显示的完整哈希（16–120 个字符，不含空格）。",
        "en": "That does not look like a transaction hash. Send the full hash as your wallet shows it (16–120 characters, no spaces).",
        "ru": "Это не похоже на хеш транзакции. Отправьте полный хеш, как его показывает кошелёк (16–120 символов, без пробелов).",
    },
    "mpay_hash_aborted": {
        "zh": "已停止输入哈希。您的付款申请仍然有效——如已完成转账，请回到付款消息并再次点击「我已转账，提交哈希」。",
        "en": "Stopped waiting for the hash. Your payment request is still open — if you have already transferred, go back to the payment message and tap \"I have sent it — submit hash\" again.",
        "ru": "Ввод хеша отменён. Заявка на оплату всё ещё активна — если перевод уже сделан, вернитесь к сообщению с оплатой и снова нажмите «Я отправил».",
    },
    "mpay_hash_duplicate": {
        "zh": "该交易哈希已被提交过。如果您确认这是新的转账，请联系 {support}。",
        "en": "That transaction hash has already been submitted. If this really is a new transfer, contact {support}.",
        "ru": "Этот хеш уже отправляли. Если это действительно новый перевод, напишите {support}.",
    },
    "mpay_submitted": {
        "zh": "✅ 已收到申请 #{payment_id}。\n管理员会在区块浏览器上核对该交易，确认后余额将自动更新。\n如长时间未处理，请联系 {support}。",
        "en": "✅ Request #{payment_id} received.\nAn admin will verify the transaction on a block explorer; your balance updates once it is confirmed.\nIf it takes too long, contact {support}.",
        "ru": "✅ Заявка #{payment_id} принята.\nАдмин сверит транзакцию в блокчейн-обозревателе, после подтверждения баланс обновится.\nЕсли долго нет ответа — напишите {support}.",
    },
    "mpay_confirmed": {
        "zh": "✅ 转账 #{payment_id} 已确认。\n已入账：{amount}\n当前余额：{balance}",
        "en": "✅ Transfer #{payment_id} confirmed.\nCredited: {amount}\nBalance: {balance}",
        "ru": "✅ Перевод #{payment_id} подтверждён.\nЗачислено: {amount}\nБаланс: {balance}",
    },
    "mpay_rejected": {
        "zh": "❌ 转账 #{payment_id} 未获确认。\n管理员在链上未找到这笔转账，或金额与申请不符。请联系 {support}。",
        "en": "❌ Transfer #{payment_id} was not confirmed.\nThe admin could not find it on-chain, or the amount did not match the request. Contact {support}.",
        "ru": "❌ Перевод #{payment_id} не подтверждён.\nАдмин не нашёл его в блокчейне либо сумма не совпала с заявкой. Напишите {support}.",
    },
    "mpay_cancelled": {
        "zh": "申请 #{payment_id} 已取消。如果您已经转账，请联系 {support}。",
        "en": "Request #{payment_id} cancelled. If you already sent the transfer, contact {support}.",
        "ru": "Заявка #{payment_id} отменена. Если перевод вы всё-таки сделали — напишите {support}.",
    },
    "mpay_unavailable": {
        "zh": "目前无法使用加密货币转账。请使用 Crypto Pay，或联系 {support}。",
        "en": "Crypto transfer is unavailable right now. Use Crypto Pay or contact {support}.",
        "ru": "Перевод криптовалютой сейчас недоступен. Используйте Crypto Pay или напишите {support}.",
    },
    "mpay_stale": {
        "zh": "该按钮已失效，请重新开始充值。",
        "en": "That button is no longer valid. Start the top-up again.",
        "ru": "Кнопка устарела. Начните пополнение заново.",
    },
    "mpay_open_exists": {
        "zh": "您已有一笔待处理的申请 #{payment_id}。请先完成或取消它。",
        "en": "You already have an open request #{payment_id}. Finish or cancel it first.",
        "ru": "У вас уже есть открытая заявка #{payment_id}. Сначала завершите или отмените её.",
    },
    "mpay_admin_new": {
        "zh": (
            "🆕 待确认的加密货币转账 #{payment_id}\n\n"
            "用户：{user}\n"
            "币种/网络：{asset} / {network}\n"
            "申请金额：{fiat_amount}\n"
            "应收：{crypto_amount}\n"
            "地址：<code>{address}</code>\n"
            "交易哈希：<code>{tx_hash}</code>\n\n"
            "确认前请在区块浏览器上核对哈希、金额和网络。"
        ),
        "en": (
            "🆕 Crypto transfer awaiting confirmation #{payment_id}\n\n"
            "User: {user}\n"
            "Coin / network: {asset} / {network}\n"
            "Requested: {fiat_amount}\n"
            "Expected: {crypto_amount}\n"
            "Address: <code>{address}</code>\n"
            "Tx hash: <code>{tx_hash}</code>\n\n"
            "Check the hash, the amount and the network on a block explorer before confirming."
        ),
        "ru": (
            "🆕 Перевод криптой на подтверждение #{payment_id}\n\n"
            "Пользователь: {user}\n"
            "Монета / сеть: {asset} / {network}\n"
            "Заявлено: {fiat_amount}\n"
            "Ожидается: {crypto_amount}\n"
            "Адрес: <code>{address}</code>\n"
            "Хеш: <code>{tx_hash}</code>\n\n"
            "Перед подтверждением сверьте хеш, сумму и сеть в блокчейн-обозревателе."
        ),
    },
    "mpay_admin_confirmed": {
        "zh": "✅ #{payment_id} 已确认，已为用户 {user} 入账 {amount}。",
        "en": "✅ #{payment_id} confirmed, {amount} credited to {user}.",
        "ru": "✅ #{payment_id} подтверждён, {amount} зачислено пользователю {user}.",
    },
    "mpay_admin_rejected": {
        "zh": "❌ #{payment_id} 已拒绝，未入账。",
        "en": "❌ #{payment_id} rejected, nothing was credited.",
        "ru": "❌ #{payment_id} отклонён, ничего не зачислено.",
    },
    "mpay_admin_already": {
        "zh": "#{payment_id} 已被其他管理员处理。",
        "en": "#{payment_id} was already handled by another admin.",
        "ru": "#{payment_id} уже обработал другой админ.",
    },
    "mpay_admin_none_pending": {
        "zh": "没有待确认的加密货币转账。",
        "en": "No crypto transfers are awaiting confirmation.",
        "ru": "Нет переводов криптой на подтверждение.",
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
    "stock_list": {
        "zh": "🔄 库存情况：\n\n{items}",
        "en": "🔄 Availability:\n\n{items}",
        "ru": "🔄 Наличие:\n\n{items}",
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
    "settings": {
        "zh": "⚙️ 设置\n\n购买通知：{status}",
        "en": "⚙️ Settings\n\nPurchase notifications: {status}",
        "ru": "⚙️ Настройки\n\nУведомления о покупках: {status}",
    },
    "notifications_on": {
        "zh": " включены",
        "en": " enabled",
        "ru": " включены",
    },
    "notifications_off": {
        "zh": " выключены",
        "en": " disabled",
        "ru": " выключены",
    },
    "enable_notifications": {
        "zh": "🔔 开启购买通知",
        "en": "🔔 Enable purchase notifications",
        "ru": "🔔 Включить уведомления о покупках",
    },
    "disable_notifications": {
        "zh": "🔕 关闭购买通知",
        "en": "🔕 Disable purchase notifications",
        "ru": "🔕 Отключить уведомления о покупках",
    },
    "notifications_updated": {
        "zh": "购买通知设置已更新。",
        "en": "Purchase notification settings updated.",
        "ru": "Настройки уведомлений о покупках обновлены.",
    },
    "purchase_notification": {
        "zh": "🛍 新订单\n商品：{product}\n数量：{quantity}\n价格：{price}\n买家：{buyer}",
        "en": "🛍 New purchase\nProduct: {product}\nQuantity: {quantity}\nPrice: {price}\nBuyer: {buyer}",
        "ru": "🛍 Новая покупка\nТовар: {product}\nКоличество: {quantity}\nЦена: {price}\nПокупатель: {buyer}",
    },
    "disable_purchase_notifications": {
        "zh": "🔕 关闭购买通知",
        "en": "🔕 Disable purchase notifications",
        "ru": "🔕 Отключить уведомления о покупках",
    },
    "stock_replenished": {
        "zh": "📦 库存已补充\n已添加新的账号。",
        "en": "📦 Stock replenished\nNew accounts have been added.",
        "ru": "📦 Склад пополнен\nДобавлены новые аккаунты.",
    },
    "catalog": {
        "zh": "🛍 商品",
        "en": "🛍 Products",
        "ru": "🛍 Товары",
    },
    "catalog_empty": {
        "zh": "暂无商品。",
        "en": "No products are available yet.",
        "ru": "Товаров пока нет.",
    },
    "catalog_title": {
        "zh": "🛍 选择商品：",
        "en": "🛍 Choose a product:",
        "ru": "🛍 Выберите товар:",
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
        "catalog": "🛍商品",
        "help": "📖帮助",
        "settings": "⚙️设置",
        "language": "🌐语言",
    },
    "en": {
        "plus": "⚡GPT Plus",
        "pro": "🚀 Pro",
        "balance": "💰Balance",
        "invite": "🔗Invite",
        "stock": "🔄Check stock",
        "queue": "🕒Queue",
        "catalog": "🛍Products",
        "help": "📖Help",
        "settings": "⚙️Settings",
        "language": "🌐Language",
    },
    "ru": {
        "plus": "⚡GPT Plus",
        "pro": "🚀Pro",
        "balance": "💰Баланс",
        "invite": "🔗Пригласить",
        "stock": "🔄Проверить наличие",
        "queue": "🕒Очередь",
        "catalog": "🛍Товары",
        "help": "📖Помощь",
        "settings": "⚙️Настройки",
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
            [KeyboardButton(text=labels["catalog"]), KeyboardButton(text=labels["help"])],
            [KeyboardButton(text=labels["settings"]), KeyboardButton(text=labels["language"])],
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
            [
                InlineKeyboardButton(
                    text=labels[language],
                    callback_data="topup",
                    style=ButtonStyle.SUCCESS,
                )
            ],
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


def _with_price(
    label: str,
    product_key: str,
    prices: dict[str, str] | None,
    stock: dict[str, int] | None = None,
) -> str:
    marker = ""
    if stock is not None:
        marker = "🟢 " if stock.get(product_key, 0) > 0 else "🔴 "
    if prices and product_key in prices:
        return f"{marker}{label} · {prices[product_key]}"
    return f"{marker}{label}"


def _stock_style(product_key: str, stock: dict[str, int] | None) -> str | None:
    """Colour a product button green when it is buyable, red when it is not.

    Returns ``None`` when stock is unknown, so the button keeps the default
    look rather than claiming a state we cannot back up. The 🟢/🔴 marker in
    the label carries the same information for clients too old to render
    ``style``.
    """
    if stock is None:
        return None
    return ButtonStyle.SUCCESS if stock.get(product_key, 0) > 0 else ButtonStyle.DANGER


def plus_keyboard(
    language: str,
    prices: dict[str, str] | None = None,
    stock: dict[str, int] | None = None,
) -> InlineKeyboardMarkup:
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
                    text=_with_price(labels["nw"], "gpt_plus_nw", prices, stock),
                    callback_data="product:gpt_plus_nw",
                    style=_stock_style("gpt_plus_nw", stock),
                ),
                InlineKeyboardButton(
                    text=_with_price(labels["fw"], "gpt_plus_fw", prices, stock),
                    callback_data="product:gpt_plus_fw",
                    style=_stock_style("gpt_plus_fw", stock),
                ),
            ]
        ]
    )


def pro_keyboard(
    language: str,
    prices: dict[str, str] | None = None,
    stock: dict[str, int] | None = None,
) -> InlineKeyboardMarkup:
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
                    text=_with_price(labels["5"], "pro_5x_nw", prices, stock),
                    callback_data="product:pro_5x_nw",
                    style=_stock_style("pro_5x_nw", stock),
                ),
                InlineKeyboardButton(
                    text=_with_price(labels["20"], "pro_20x_nw", prices, stock),
                    callback_data="product:pro_20x_nw",
                    style=_stock_style("pro_20x_nw", stock),
                ),
            ]
        ]
    )


def queue_keyboard(
    language: str,
    prices: dict[str, str] | None = None,
    stock: dict[str, int] | None = None,
) -> InlineKeyboardMarkup:
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
                    text=_with_price(labels["plus_nw"], "gpt_plus_nw", prices, stock),
                    callback_data="queue:gpt_plus_nw",
                    style=_stock_style("gpt_plus_nw", stock),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["plus_fw"], "gpt_plus_fw", prices, stock),
                    callback_data="queue:gpt_plus_fw",
                    style=_stock_style("gpt_plus_fw", stock),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["pro5_nw"], "pro_5x_nw", prices, stock),
                    callback_data="queue:pro_5x_nw",
                    style=_stock_style("pro_5x_nw", stock),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_with_price(labels["pro20_nw"], "pro_20x_nw", prices, stock),
                    callback_data="queue:pro_20x_nw",
                    style=_stock_style("pro_20x_nw", stock),
                )
            ],
        ]
    )


def catalog_keyboard(
    language: str,
    items: list[tuple[str, str, str, int]],
) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    rows: list[list[InlineKeyboardButton]] = []
    for product_key, label, price, stock_count in items:
        marker = "🟢" if stock_count > 0 else "🔴"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {label} · {price}",
                    callback_data=f"product:{product_key}",
                    style=ButtonStyle.SUCCESS if stock_count > 0 else ButtonStyle.DANGER,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(language: str, purchase_notifications: bool) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    action = "off" if purchase_notifications else "on"
    label_key = "disable_notifications" if purchase_notifications else "enable_notifications"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, label_key),
                    callback_data=f"purchase_notify:{action}",
                    # Red when the tap turns something off, green when it turns
                    # it on, so the colour describes the effect rather than the
                    # current state.
                    style=ButtonStyle.DANGER if purchase_notifications else ButtonStyle.SUCCESS,
                )
            ],
        ]
    )


def purchase_notification_keyboard(language: str) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "disable_purchase_notifications"),
                    callback_data="purchase_notify:off",
                    style=ButtonStyle.DANGER,
                )
            ]
        ]
    )


def queue_purchase_keyboard(language: str, product_key: str) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "pay"),
                    callback_data=f"buy:{product_key}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
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
    rows = [
        [
            InlineKeyboardButton(
                text=t(language, "pay"),
                url=invoice_url,
                style=ButtonStyle.SUCCESS,
            )
        ]
    ]
    if order_id is not None:
        if show_balance_payment:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=t(language, "pay_balance"),
                        callback_data=f"balance_pay:{order_id}",
                        style=ButtonStyle.PRIMARY,
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
            [
                InlineKeyboardButton(
                    text=labels[language],
                    callback_data=f"queue:{product_key}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
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
        [
            InlineKeyboardButton(
                text=t(language, "pay"),
                url=invoice_url,
                style=ButtonStyle.SUCCESS,
            )
        ],
    ]
    if show_balance_payment:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(language, "pay_balance"),
                    callback_data=f"balance_pay:{order_id}",
                    style=ButtonStyle.PRIMARY,
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


def payment_method_keyboard(language: str, amount_cents: int) -> InlineKeyboardMarkup:
    """Crypto Pay versus a direct transfer to one of our wallets.

    Crypto Pay is listed first and coloured, because it credits automatically —
    the manual route costs the buyer a wait for an admin.
    """
    language = language if language in LANGUAGES else "en"
    auto = {
        "zh": "⚡ Crypto Pay（自动）",
        "en": "⚡ Crypto Pay (automatic)",
        "ru": "⚡ Crypto Pay (автоматически)",
    }
    manual = {
        "zh": "🪙 加密货币转账",
        "en": "🪙 Crypto transfer",
        "ru": "🪙 Перевод криптовалютой",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=auto[language],
                    callback_data=f"cpay:{amount_cents}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=manual[language],
                    callback_data=f"mpay:assets:{amount_cents}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )


def mpay_asset_keyboard(
    language: str,
    assets: list[str],
    amount_cents: int,
) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for asset in assets:
        row.append(
            InlineKeyboardButton(
                text=asset,
                callback_data=f"mpay:asset:{asset}:{amount_cents}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    back = {"zh": "◀️ 返回", "en": "◀️ Back", "ru": "◀️ Назад"}
    rows.append(
        [InlineKeyboardButton(text=back[language], callback_data=f"topup:{amount_cents}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mpay_network_keyboard(
    language: str,
    asset: str,
    options: list[tuple[int, str]],
    amount_cents: int,
) -> InlineKeyboardMarkup:
    """One row per network. The index points into ``settings.crypto_wallets``."""
    language = language if language in LANGUAGES else "en"
    rows = [
        [
            InlineKeyboardButton(
                text=network,
                callback_data=f"mpay:w:{index}:{asset}:{amount_cents}",
            )
        ]
        for index, network in options
    ]
    back = {"zh": "◀️ 返回", "en": "◀️ Back", "ru": "◀️ Назад"}
    rows.append(
        [InlineKeyboardButton(text=back[language], callback_data=f"mpay:assets:{amount_cents}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mpay_pending_keyboard(language: str, payment_id: int) -> InlineKeyboardMarkup:
    language = language if language in LANGUAGES else "en"
    sent = {
        "zh": "✅ 我已转账，提交哈希",
        "en": "✅ I have sent it — submit hash",
        "ru": "✅ Перевёл — отправить хеш",
    }
    cancel = {"zh": "✖️ 取消", "en": "✖️ Cancel", "ru": "✖️ Отменить"}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=sent[language],
                    callback_data=f"mpay:hash:{payment_id}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=cancel[language],
                    callback_data=f"mpay:cancel:{payment_id}",
                    style=ButtonStyle.DANGER,
                )
            ],
        ]
    )


def mpay_admin_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """Admin-facing, so English only — same convention as the other admin UI."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm",
                    callback_data=f"mpay:ok:{payment_id}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"mpay:rej:{payment_id}",
                    style=ButtonStyle.DANGER,
                ),
            ]
        ]
    )


def action_for_text(language: str, message_text: str) -> str | None:
    labels = MENU_LABELS[language if language in LANGUAGES else "en"]
    for action, label in labels.items():
        if label == message_text:
            return action
    return None
