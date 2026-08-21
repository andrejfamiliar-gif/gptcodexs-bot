from __future__ import annotations

from typing import TypeVar

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


_T = TypeVar("_T")


LANGUAGES = ("zh", "en", "ru", "vi", "hi")

LANGUAGE_BUTTONS = (
    ("zh", "🇨🇳 中文"),
    ("en", "🇺🇸 English"),
    ("ru", "🇷🇺 Русский"),
    ("vi", "🇻🇳 Tiếng Việt"),
    ("hi", "🇮🇳 हिन्दी"),
)

# The same labels keyed by code, for screens that name the current language
# rather than offering a choice of them.
LANGUAGE_NAMES = dict(LANGUAGE_BUTTONS)


def _pick(labels: dict[str, _T], language: str) -> _T:
    """Look up a per-language label, falling back to English.

    Every keyboard below carries its own small label dict. Adding a language to
    ``LANGUAGES`` without touching all of them would otherwise raise KeyError
    inside a handler, which reaches the buyer as a dead button. Falling back to
    English keeps the menu usable while a translation is still missing.
    """
    value = labels.get(language)
    return labels["en"] if value is None else value


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
    # The buyer types the amount in their own currency, so both the prompt and
    # the "that is not a number" hint have to name that currency and show an
    # example in it. A dollar example under a ₫ prompt is how someone ends up
    # typing 2.50 and being told it is too small.
    "top_up_other": {
        "zh": "请输入充值金额（{currency}）：",
        "en": "Enter a top-up amount in {currency}:",
        "ru": "Введите сумму пополнения в {currency}:",
    },
    "top_up_invalid": {
        "zh": "请输入有效金额，例如 {example}。",
        "en": "Enter a valid amount, for example {example}.",
        "ru": "Введите корректную сумму, например {example}.",
    },
    "top_up_invoice": {
        "zh": "充值账单已创建：{amount}\nCrypto Pay 账单：{usd_amount}\n点击下方按钮完成支付。\n支付成功后余额会自动更新。",
        "en": "Top-up invoice created: {amount}\nCrypto Pay invoice: {usd_amount}\nTap the button below to pay.\nYour balance will update automatically after payment.",
        "ru": "Счёт на пополнение создан: {amount}\nСчёт Crypto Pay: {usd_amount}\nНажмите кнопку ниже для оплаты.\nПосле оплаты баланс обновится автоматически.",
    },
    # Just the question. The two buttons below it are named plainly enough that
    # spelling out what each one does only adds a wall of text over the choice.
    "mpay_method": {
        "zh": "请选择支付方式，金额 {amount}：",
        "en": "Choose how to pay {amount}:",
        "ru": "Выберите способ оплаты на сумму {amount}:",
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
    # The buyer is shown the coin amount, the rate and the address, and nothing
    # else: no request number, no fiat restatement of the amount they just chose,
    # and no hash instructions — verification is one "check payment" tap.
    # ``{payment_id}`` and ``{fiat_amount}`` are still accepted as arguments by
    # ``str.format`` even though no language uses them, so callers stay simple.
    "mpay_instructions": {
        "zh": (
            "币种：<b>{asset}</b>\n"
            "网络：<b>{network}</b>\n"
            "转账金额：<b>{crypto_amount} {asset}</b>\n"
            "汇率：1 {asset} = {rate}（{rate_at} UTC）\n\n"
            "收款地址：\n<code>{address}</code>\n\n"
            "⚠️ 请务必使用 <b>{network}</b> 网络，其他网络的转账无法找回。\n"
            "本页面有效期 {hours} 小时。"
        ),
        "en": (
            "Coin: <b>{asset}</b>\n"
            "Network: <b>{network}</b>\n"
            "Amount to send: <b>{crypto_amount} {asset}</b>\n"
            "Rate: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "Address:\n<code>{address}</code>\n\n"
            "⚠️ Use the <b>{network}</b> network. A transfer on any other network cannot be recovered.\n"
            "This request is valid for {hours} hours."
        ),
        "ru": (
            "Монета: <b>{asset}</b>\n"
            "Сеть: <b>{network}</b>\n"
            "Сумма перевода: <b>{crypto_amount} {asset}</b>\n"
            "Курс: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "Адрес:\n<code>{address}</code>\n\n"
            "⚠️ Переводите только в сети <b>{network}</b>. Перевод в другой сети вернуть нельзя.\n"
            "Заявка действительна {hours} ч."
        ),
        "vi": (
            "Đồng tiền: <b>{asset}</b>\n"
            "Mạng: <b>{network}</b>\n"
            "Số tiền cần chuyển: <b>{crypto_amount} {asset}</b>\n"
            "Tỷ giá: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "Địa chỉ:\n<code>{address}</code>\n\n"
            "⚠️ Chỉ chuyển trên mạng <b>{network}</b>. Chuyển sai mạng sẽ không thể lấy lại.\n"
            "Yêu cầu này có hiệu lực trong {hours} giờ."
        ),
        "hi": (
            "सिक्का: <b>{asset}</b>\n"
            "नेटवर्क: <b>{network}</b>\n"
            "भेजने की राशि: <b>{crypto_amount} {asset}</b>\n"
            "दर: 1 {asset} = {rate} ({rate_at} UTC)\n\n"
            "पता:\n<code>{address}</code>\n\n"
            "⚠️ केवल <b>{network}</b> नेटवर्क पर भेजें। किसी दूसरे नेटवर्क पर भेजी गई राशि वापस नहीं मिल सकती।\n"
            "यह अनुरोध {hours} घंटे तक मान्य है।"
        ),
    },
    # Without a rate the fiat amount is the only figure the bot can state, so it
    # stays — replacing it with a made-up coin amount would be worse.
    "mpay_instructions_no_rate": {
        "zh": (
            "币种：<b>{asset}</b>\n"
            "网络：<b>{network}</b>\n"
            "应付金额：<b>{fiat_amount}</b>\n\n"
            "收款地址：\n<code>{address}</code>\n\n"
            "ℹ️ 机器人暂时无法获取 {asset} 的汇率，因此无法显示精确的币种数量。"
            "请按当前市场价转入等值金额，管理员将按到账时的汇率核对。\n"
            "⚠️ 请务必使用 <b>{network}</b> 网络，其他网络的转账无法找回。\n"
            "本页面有效期 {hours} 小时。"
        ),
        "en": (
            "Coin: <b>{asset}</b>\n"
            "Network: <b>{network}</b>\n"
            "Amount owed: <b>{fiat_amount}</b>\n\n"
            "Address:\n<code>{address}</code>\n\n"
            "ℹ️ The bot has no rate for {asset} right now, so it cannot show an exact coin amount. "
            "Send the equivalent at the current market rate; the admin will check it against the rate at the time it arrives.\n"
            "⚠️ Use the <b>{network}</b> network. A transfer on any other network cannot be recovered.\n"
            "This request is valid for {hours} hours."
        ),
        "ru": (
            "Монета: <b>{asset}</b>\n"
            "Сеть: <b>{network}</b>\n"
            "К оплате: <b>{fiat_amount}</b>\n\n"
            "Адрес:\n<code>{address}</code>\n\n"
            "ℹ️ Бот сейчас не знает курс {asset}, поэтому не может показать точное количество монет. "
            "Переведите эквивалент по текущему рыночному курсу — админ сверит сумму по курсу на момент зачисления.\n"
            "⚠️ Переводите только в сети <b>{network}</b>. Перевод в другой сети вернуть нельзя.\n"
            "Заявка действительна {hours} ч."
        ),
        "vi": (
            "Đồng tiền: <b>{asset}</b>\n"
            "Mạng: <b>{network}</b>\n"
            "Số tiền phải trả: <b>{fiat_amount}</b>\n\n"
            "Địa chỉ:\n<code>{address}</code>\n\n"
            "ℹ️ Bot hiện không có tỷ giá {asset} nên không thể hiển thị số lượng coin chính xác. "
            "Hãy chuyển số tiền tương đương theo giá thị trường hiện tại; quản trị viên sẽ đối chiếu theo tỷ giá lúc nhận được.\n"
            "⚠️ Chỉ chuyển trên mạng <b>{network}</b>. Chuyển sai mạng sẽ không thể lấy lại.\n"
            "Yêu cầu này có hiệu lực trong {hours} giờ."
        ),
        "hi": (
            "सिक्का: <b>{asset}</b>\n"
            "नेटवर्क: <b>{network}</b>\n"
            "देय राशि: <b>{fiat_amount}</b>\n\n"
            "पता:\n<code>{address}</code>\n\n"
            "ℹ️ बॉट के पास अभी {asset} की दर नहीं है, इसलिए वह सटीक सिक्का राशि नहीं दिखा सकता। "
            "वर्तमान बाज़ार दर पर समकक्ष राशि भेजें; राशि मिलने के समय की दर से एडमिन उसे जाँचेगा।\n"
            "⚠️ केवल <b>{network}</b> नेटवर्क पर भेजें। किसी दूसरे नेटवर्क पर भेजी गई राशि वापस नहीं मिल सकती।\n"
            "यह अनुरोध {hours} घंटे तक मान्य है।"
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
        "zh": "付款尚未确认。",
        "en": "The payment is not confirmed yet.",
        "ru": "Оплата ещё не подтверждена.",
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
        "zh": (
            "✅ 付款已收到。\n\n"
            "该商品目前为预订状态，将在 {hours} 小时内自动发货。\n"
            "账号准备好后机器人会立即发送给你，无需再次操作。\n"
            "如有疑问请联系 {support}。"
        ),
        "en": (
            "✅ Payment received.\n\n"
            "This item is on pre-order and will be delivered automatically within {hours} h.\n"
            "The bot sends the account as soon as it is ready — you do not need to do anything.\n"
            "Questions: {support}."
        ),
        "ru": (
            "✅ Оплата принята.\n\n"
            "Товар оформлен как предзаказ, выдача в течение {hours} ч.\n"
            "Бот отправит аккаунт автоматически, как только он будет готов — ничего делать не нужно.\n"
            "Вопросы: {support}."
        ),
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
    "support_ticket_button": {
        "zh": "✉️ 联系客服",
        "en": "✉️ Contact support",
        "ru": "✉️ Написать в поддержку",
    },
    "support_ticket_prompt": {
        "zh": "请详细描述你的问题。发送 /cancel 可取消。",
        "en": "Describe your issue in one message. Send /cancel to cancel.",
        "ru": "Опиши проблему одним сообщением. Для отмены отправь /cancel.",
    },
    "support_ticket_created": {
        "zh": "✅ 工单 #{ticket_id} 已创建。我们会尽快回复。",
        "en": "✅ Ticket #{ticket_id} has been created. We will reply as soon as possible.",
        "ru": "✅ Обращение #{ticket_id} создано. Мы ответим в ближайшее время.",
    },
    "support_ticket_message_sent": {
        "zh": "✅ 消息已添加到工单 #{ticket_id}。",
        "en": "✅ Your message was added to ticket #{ticket_id}.",
        "ru": "✅ Сообщение добавлено в обращение #{ticket_id}.",
    },
    "support_ticket_reply_button": {
        "zh": "💬 回复工单",
        "en": "💬 Reply to ticket",
        "ru": "💬 Ответить по обращению",
    },
    "support_ticket_reply": {
        "zh": "✉️ 工单 #{ticket_id} 的客服回复：\n\n{body}",
        "en": "✉️ Support reply for ticket #{ticket_id}:\n\n{body}",
        "ru": "✉️ Ответ поддержки по обращению #{ticket_id}:\n\n{body}",
    },
    "support_ticket_closed": {
        "zh": "✅ 工单 #{ticket_id} 已关闭。如有新问题，请创建新的工单。",
        "en": "✅ Ticket #{ticket_id} is closed. Create a new ticket if you need more help.",
        "ru": "✅ Обращение #{ticket_id} закрыто. Если понадобится помощь, создай новое обращение.",
    },
    "support_ticket_already_closed": {
        "zh": "工单已关闭。",
        "en": "This ticket is already closed.",
        "ru": "Это обращение уже закрыто.",
    },
    "support_ticket_too_long": {
        "zh": "消息过长，最多 4000 个字符。",
        "en": "The message is too long. Maximum: 4000 characters.",
        "ru": "Сообщение слишком длинное. Максимум — 4000 символов.",
    },
    "settings": {
        "zh": "⚙️ 设置\n\n购买通知：{status}",
        "en": "⚙️ Settings\n\nPurchase notifications: {status}",
        "ru": "⚙️ Настройки\n\nУведомления о покупках: {status}",
    },
    "notifications_on": {
        "zh": "已开启",
        "en": "enabled",
        "ru": "включены",
    },
    "notifications_off": {
        "zh": "已关闭",
        "en": "disabled",
        "ru": "выключены",
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
        "zh": (
            "┌─────────────────┐\n"
            "🛍 <b>有人刚下单了</b>\n"
            "└─────────────────┘\n"
            "📦 商品 · <b>{product}</b>\n"
            "🔢 数量 · <b>{quantity}</b>\n"
            "💵 金额 · <b>{price}</b>\n"
            "👤 买家 · <i>{buyer}</i>\n"
            "└╴ 库存已更新"
        ),
        "en": (
            "┌─────────────────┐\n"
            "🛍 <b>Someone just bought</b>\n"
            "└─────────────────┘\n"
            "📦 Product · <b>{product}</b>\n"
            "🔢 Quantity · <b>{quantity}</b>\n"
            "💵 Total · <b>{price}</b>\n"
            "👤 Buyer · <i>{buyer}</i>\n"
            "└╴ Stock updated"
        ),
        "ru": (
            "┌─────────────────┐\n"
            "🛍 <b>Только что купили</b>\n"
            "└─────────────────┘\n"
            "📦 Товар · <b>{product}</b>\n"
            "🔢 Количество · <b>{quantity}</b>\n"
            "💵 Сумма · <b>{price}</b>\n"
            "👤 Покупатель · <i>{buyer}</i>\n"
            "└╴ Наличие обновлено"
        ),
    },
    "disable_purchase_notifications": {
        "zh": "🔕 关闭购买通知",
        "en": "🔕 Disable purchase notifications",
        "ru": "🔕 Отключить уведомления о покупках",
    },
    # Deliberately does not say which products arrived: the owner asked for a
    # plain "new stock is in" so the broadcast does not double as a price list.
    "stock_replenished": {
        "zh": (
            "╭───────────────╮\n"
            "📦 <b>新货到店</b>\n"
            "╰───────────────╯\n"
            "✨ 刚刚补充了一批新账号。\n"
            "🟢 库存已更新，先到先得。\n\n"
            "打开「商品」看看现在有什么。"
        ),
        "en": (
            "╭───────────────╮\n"
            "📦 <b>Restocked</b>\n"
            "╰───────────────╯\n"
            "✨ A fresh batch of accounts is in.\n"
            "🟢 Stock is updated — first come, first served.\n\n"
            "Open «Products» to see what is available."
        ),
        "ru": (
            "╭───────────────╮\n"
            "📦 <b>Новое поступление</b>\n"
            "╰───────────────╯\n"
            "✨ Загрузили свежую партию аккаунтов.\n"
            "🟢 Наличие обновлено — кто успел, тот забрал.\n\n"
            "Откройте «Товары», чтобы посмотреть."
        ),
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
    # Added with all five languages inline rather than through _VI/_HI: a new
    # string is easier to keep honest when every translation of it sits on one
    # screen.
    "top_up_too_small": {
        "zh": "最低充值金额为 {minimum}。请输入不低于该金额的数字。",
        "en": "The minimum top-up is {minimum}. Enter that amount or more.",
        "ru": "Минимальная сумма пополнения — {minimum}. Введите её или больше.",
        "vi": "Số tiền nạp tối thiểu là {minimum}. Hãy nhập số đó hoặc lớn hơn.",
        "hi": "न्यूनतम राशि {minimum} है। इतनी या इससे अधिक राशि दर्ज करें।",
    },
    "top_up_min_hint": {
        "zh": "最低 {minimum}。",
        "en": "Minimum {minimum}.",
        "ru": "Минимум {minimum}.",
        "vi": "Tối thiểu {minimum}.",
        "hi": "न्यूनतम {minimum}।",
    },
    "top_up_cancelled": {
        "zh": "已取消充值。",
        "en": "Top-up cancelled.",
        "ru": "Пополнение отменено.",
        "vi": "Đã huỷ nạp tiền.",
        "hi": "राशि जोड़ना रद्द कर दिया गया।",
    },
    "cancel_hint": {
        "zh": "输入 /cancel 或点击下方按钮可以退出。",
        "en": "Send /cancel or tap the button below to back out.",
        "ru": "Отправьте /cancel или нажмите кнопку ниже, чтобы выйти.",
        "vi": "Gửi /cancel hoặc nhấn nút bên dưới để thoát.",
        "hi": "बाहर निकलने के लिए /cancel भेजें या नीचे का बटन दबाएँ।",
    },
    "nothing_to_cancel": {
        "zh": "现在没有需要取消的操作。",
        "en": "There is nothing to cancel right now.",
        "ru": "Сейчас нечего отменять.",
        "vi": "Hiện không có gì để huỷ.",
        "hi": "अभी रद्द करने के लिए कुछ नहीं है।",
    },
    "action_cancelled": {
        "zh": "已取消。",
        "en": "Cancelled.",
        "ru": "Отменено.",
        "vi": "Đã huỷ.",
        "hi": "रद्द कर दिया गया।",
    },
    # The referral screen. The percentage is passed in rather than written into
    # the text, so the number a buyer is promised and the number the code pays
    # can never drift apart.
    "referral_card": {
        "zh": (
            "╭───────────────╮\n"
            "👥 <b>邀请返利</b>\n"
            "╰───────────────╯\n"
            "分享你的链接，好友每次购买你都能拿 <b>{percent}%</b>，"
            "直接进入余额，可用于下单或提现给客服。\n\n"
            "🔗 你的链接：\n{link}\n\n"
            "👤 已邀请 · <b>{invited}</b>\n"
            "🧾 已带来订单 · <b>{orders}</b>\n"
            "💰 累计收益 · <b>{earned}</b>\n\n"
            "🎁 活动截止 2026年9月5日：好友累计购买满 $5，"
            "你将额外获得 $1 余额。\n\n"
            "<i>返利在好友付款后立即入账。</i>"
        ),
        "en": (
            "╭───────────────╮\n"
            "👥 <b>Referral programme</b>\n"
            "╰───────────────╯\n"
            "Share your link and you earn <b>{percent}%</b> of everything the "
            "people you invite buy — straight onto your balance, ready to spend "
            "on an order.\n\n"
            "🔗 Your link:\n{link}\n\n"
            "👤 Invited · <b>{invited}</b>\n"
            "🧾 Their paid orders · <b>{orders}</b>\n"
            "💰 Earned so far · <b>{earned}</b>\n\n"
            "🎁 Until September 5, 2026: when an invited friend spends $5 in total, "
            "you receive an extra $1 balance bonus.\n\n"
            "<i>The commission lands the moment their payment goes through.</i>"
        ),
        "ru": (
            "╭───────────────╮\n"
            "👥 <b>Реферальная программа</b>\n"
            "╰───────────────╯\n"
            "Делитесь ссылкой — и получаете <b>{percent}%</b> с каждой покупки "
            "тех, кто пришёл по ней. Деньги сразу падают на баланс, ими можно "
            "оплатить заказ.\n\n"
            "🔗 Ваша ссылка:\n{link}\n\n"
            "👤 Приглашено · <b>{invited}</b>\n"
            "🧾 Их оплаченных заказов · <b>{orders}</b>\n"
            "💰 Заработано · <b>{earned}</b>\n\n"
            "🎁 Акция до 5 сентября 2026: когда приглашённый вами пользователь "
            "купит товаров на $5 суммарно, вы получите ещё $1 на баланс.\n\n"
            "<i>Начисление приходит сразу после их оплаты.</i>"
        ),
        "vi": (
            "╭───────────────╮\n"
            "👥 <b>Chương trình giới thiệu</b>\n"
            "╰───────────────╯\n"
            "Chia sẻ liên kết của bạn và nhận <b>{percent}%</b> mọi đơn hàng của "
            "người bạn mời — cộng thẳng vào số dư, dùng được để đặt hàng.\n\n"
            "🔗 Liên kết của bạn:\n{link}\n\n"
            "👤 Đã mời · <b>{invited}</b>\n"
            "🧾 Đơn đã thanh toán của họ · <b>{orders}</b>\n"
            "💰 Đã nhận · <b>{earned}</b>\n\n"
            "🎁 Khuyến mãi đến ngày 05/09/2026: khi người bạn mời mua tổng cộng $5, "
            "bạn nhận thêm $1 vào số dư.\n\n"
            "<i>Hoa hồng vào ngay khi họ thanh toán xong.</i>"
        ),
        "hi": (
            "╭───────────────╮\n"
            "👥 <b>रेफ़रल प्रोग्राम</b>\n"
            "╰───────────────╯\n"
            "अपना लिंक साझा करें और आपके बुलाए लोगों की हर खरीद पर <b>{percent}%</b> "
            "पाएँ — सीधे आपकी शेष राशि में, ऑर्डर पर खर्च करने के लिए तैयार।\n\n"
            "🔗 आपका लिंक:\n{link}\n\n"
            "👤 आमंत्रित · <b>{invited}</b>\n"
            "🧾 उनके भुगतान किए ऑर्डर · <b>{orders}</b>\n"
            "💰 अब तक कमाया · <b>{earned}</b>\n\n"
            "🎁 5 सितंबर 2026 तक ऑफ़र: आपके आमंत्रित व्यक्ति की कुल खरीद $5 होने पर "
            "आपको बैलेंस में अतिरिक्त $1 मिलेगा।\n\n"
            "<i>उनका भुगतान होते ही कमीशन जुड़ जाता है।</i>"
        ),
    },
    "referral_bonus": {
        "zh": (
            "💰 <b>邀请返利入账</b>\n"
            "你邀请的用户完成了一笔订单。\n"
            "返利 · <b>{bonus}</b>（{percent}%）\n"
            "当前余额 · <b>{balance}</b>"
        ),
        "en": (
            "💰 <b>Referral commission</b>\n"
            "Someone you invited completed an order.\n"
            "Your cut · <b>{bonus}</b> ({percent}%)\n"
            "Balance now · <b>{balance}</b>"
        ),
        "ru": (
            "💰 <b>Реферальное начисление</b>\n"
            "Приглашённый вами человек оплатил заказ.\n"
            "Ваши · <b>{bonus}</b> ({percent}%)\n"
            "Баланс теперь · <b>{balance}</b>"
        ),
        "vi": (
            "💰 <b>Hoa hồng giới thiệu</b>\n"
            "Người bạn mời vừa hoàn tất một đơn hàng.\n"
            "Phần của bạn · <b>{bonus}</b> ({percent}%)\n"
            "Số dư hiện tại · <b>{balance}</b>"
        ),
        "hi": (
            "💰 <b>रेफ़रल कमीशन</b>\n"
            "आपके बुलाए किसी व्यक्ति ने ऑर्डर पूरा किया।\n"
            "आपका हिस्सा · <b>{bonus}</b> ({percent}%)\n"
            "अब शेष राशि · <b>{balance}</b>"
        ),
    },
    "referral_campaign_bonus": {
        "zh": (
            "🎁 <b>邀请活动奖励</b>\n"
            "你邀请的用户累计购买已达到 $5。\n"
            "额外奖励 · <b>{bonus}</b>（$1.00）\n"
            "当前余额 · <b>{balance}</b>"
        ),
        "en": (
            "🎁 <b>Referral campaign reward</b>\n"
            "Someone you invited has spent $5 in total.\n"
            "Extra reward · <b>{bonus}</b> ({bonus_usd})\n"
            "Balance now · <b>{balance}</b>"
        ),
        "ru": (
            "🎁 <b>Бонус по акции</b>\n"
            "Приглашённый вами пользователь купил товаров на $5 суммарно.\n"
            "Дополнительный бонус · <b>{bonus}</b> ({bonus_usd})\n"
            "Баланс теперь · <b>{balance}</b>"
        ),
        "vi": (
            "🎁 <b>Thưởng khuyến mãi giới thiệu</b>\n"
            "Người bạn mời đã mua tổng cộng $5.\n"
            "Thưởng thêm · <b>{bonus}</b> ({bonus_usd})\n"
            "Số dư hiện tại · <b>{balance}</b>"
        ),
        "hi": (
            "🎁 <b>रेफ़रल ऑफ़र बोनस</b>\n"
            "आपके आमंत्रित व्यक्ति ने कुल $5 की खरीदारी की है।\n"
            "अतिरिक्त बोनस · <b>{bonus}</b> ({bonus_usd})\n"
            "अब शेष राशि · <b>{balance}</b>"
        ),
    },
    "settings_card": {
        "zh": (
            "⚙️ <b>设置</b>\n\n"
            "🔔 他人购买通知 · <b>{notifications}</b>\n"
            "🌐 界面语言 · <b>{language}</b>\n\n"
            "<i>点击下方按钮即可修改。</i>"
        ),
        "en": (
            "⚙️ <b>Settings</b>\n\n"
            "🔔 Notifications about other purchases · <b>{notifications}</b>\n"
            "🌐 Interface language · <b>{language}</b>\n\n"
            "<i>Tap a button below to change it.</i>"
        ),
        "ru": (
            "⚙️ <b>Настройки</b>\n\n"
            "🔔 Уведомления о чужих покупках · <b>{notifications}</b>\n"
            "🌐 Язык интерфейса · <b>{language}</b>\n\n"
            "<i>Нажмите кнопку ниже, чтобы изменить.</i>"
        ),
        "vi": (
            "⚙️ <b>Cài đặt</b>\n\n"
            "🔔 Thông báo về đơn của người khác · <b>{notifications}</b>\n"
            "🌐 Ngôn ngữ giao diện · <b>{language}</b>\n\n"
            "<i>Nhấn nút bên dưới để thay đổi.</i>"
        ),
        "hi": (
            "⚙️ <b>सेटिंग्स</b>\n\n"
            "🔔 दूसरों की खरीद की सूचनाएँ · <b>{notifications}</b>\n"
            "🌐 इंटरफ़ेस भाषा · <b>{language}</b>\n\n"
            "<i>बदलने के लिए नीचे का बटन दबाएँ।</i>"
        ),
    },
}


# Vietnamese and Hindi arrived after the table above was already three columns
# wide, so they are kept as flat per-language dicts and merged in below. That
# way a new language touches two places instead of all 74 entries, and the
# completeness check at the bottom fails loudly on a missing key rather than
# silently shipping English to a buyer who picked another language.
_VI: dict[str, str] = {
    "choose_language": "Vui lòng chọn ngôn ngữ:",
    "language_saved": "Đã đổi ngôn ngữ.",
    "welcome": "Chào mừng! Hãy chọn sản phẩm hoặc mở menu.",
    "unknown_command": "Vui lòng dùng một trong các nút menu.",
    "choose_pro_plan": "Chọn gói Pro:",
    "choose_plus_plan": "Chọn loại tài khoản Plus:",
    "balance": "💰 Số dư: {balance}\n\nBạn có thể nạp tiền qua Crypto Pay.",
    "top_up": "💳 Chọn số tiền nạp:",
    "top_up_other": "Nhập số tiền nạp bằng {currency}:",
    "top_up_invalid": "Hãy nhập số tiền hợp lệ, ví dụ {example}.",
    "top_up_invoice": (
        "Đã tạo hoá đơn nạp tiền: {amount}\n"
        "Hoá đơn Crypto Pay: {usd_amount}\n"
        "Nhấn nút bên dưới để thanh toán.\n"
        "Số dư sẽ được cập nhật tự động sau khi thanh toán."
    ),
    "mpay_method": "Chọn cách thanh toán {amount}:",
    "mpay_choose_asset": "Chọn đồng tiền (số tiền: {amount}):",
    "mpay_choose_network": (
        "{asset} hoạt động trên nhiều mạng. Hãy chọn đúng mạng mà ví của bạn dùng:\n\n"
        "⚠️ Chuyển sai mạng thì không thể lấy lại tiền."
    ),
    "mpay_ask_hash": (
        "Hãy gửi mã giao dịch (tx hash) của lần chuyển này.\n"
        "Bạn có thể tìm nó trong lịch sử ví hoặc trên trình duyệt blockchain."
    ),
    "mpay_hash_invalid": (
        "Đó không giống một mã giao dịch. Hãy gửi đầy đủ mã như ví của bạn hiển thị "
        "(16–120 ký tự, không có dấu cách)."
    ),
    "mpay_hash_aborted": (
        "Đã ngừng chờ mã giao dịch. Yêu cầu thanh toán của bạn vẫn còn mở — nếu bạn đã "
        "chuyển tiền, hãy quay lại tin nhắn thanh toán và nhấn nút kiểm tra thanh toán một lần nữa."
    ),
    "mpay_hash_duplicate": (
        "Mã giao dịch này đã được gửi trước đó. Nếu đây thực sự là một lần chuyển mới, "
        "hãy liên hệ {support}."
    ),
    "mpay_submitted": (
        "✅ Đã nhận yêu cầu #{payment_id}.\n"
        "Quản trị viên sẽ kiểm tra giao dịch trên blockchain; số dư của bạn sẽ được cập nhật "
        "sau khi xác nhận.\n"
        "Nếu quá lâu, hãy liên hệ {support}."
    ),
    "mpay_confirmed": (
        "✅ Đã xác nhận chuyển khoản #{payment_id}.\n"
        "Đã cộng: {amount}\n"
        "Số dư: {balance}"
    ),
    "mpay_rejected": (
        "❌ Chuyển khoản #{payment_id} không được xác nhận.\n"
        "Quản trị viên không tìm thấy nó trên blockchain, hoặc số tiền không khớp với yêu cầu. "
        "Hãy liên hệ {support}."
    ),
    "mpay_cancelled": (
        "Đã huỷ yêu cầu #{payment_id}. Nếu bạn đã chuyển tiền, hãy liên hệ {support}."
    ),
    "mpay_unavailable": (
        "Hiện không thể thanh toán bằng cryptocurrency. Hãy dùng Crypto Pay hoặc liên hệ {support}."
    ),
    "mpay_stale": "Nút này không còn hiệu lực. Hãy bắt đầu nạp tiền lại.",
    "mpay_open_exists": (
        "Bạn đã có một yêu cầu đang mở #{payment_id}. Hãy hoàn tất hoặc huỷ nó trước."
    ),
    "mpay_admin_new": (
        "🆕 Chuyển khoản crypto đang chờ xác nhận #{payment_id}\n\n"
        "Người dùng: {user}\n"
        "Đồng tiền / mạng: {asset} / {network}\n"
        "Yêu cầu: {fiat_amount}\n"
        "Dự kiến: {crypto_amount}\n"
        "Địa chỉ: <code>{address}</code>\n"
        "Mã giao dịch: <code>{tx_hash}</code>\n\n"
        "Hãy kiểm tra mã giao dịch, số tiền và mạng trên trình duyệt blockchain trước khi xác nhận."
    ),
    "mpay_admin_confirmed": "✅ #{payment_id} đã xác nhận, {amount} đã được cộng cho {user}.",
    "mpay_admin_rejected": "❌ #{payment_id} bị từ chối, không cộng gì cả.",
    "mpay_admin_already": "#{payment_id} đã được một quản trị viên khác xử lý.",
    "mpay_admin_none_pending": "Không có chuyển khoản crypto nào đang chờ xác nhận.",
    "product_invoice": (
        "Sản phẩm: {product}\n"
        "Giá niêm yết: {amount}\n"
        "Hoá đơn Crypto Pay: {usd_amount}\n\n"
        "Nhấn nút bên dưới để thanh toán bằng crypto."
    ),
    "pay": "💳 Thanh toán",
    "pay_balance": "💰 Trả bằng số dư",
    "balance_insufficient": "Số dư không đủ. Vui lòng nạp tiền trước.",
    "check_payment": "🔄 Kiểm tra thanh toán",
    "payment_pending": "Thanh toán chưa được xác nhận.",
    "payment_expired": "Hoá đơn đã hết hạn. Vui lòng tạo đơn hàng mới.",
    "payment_confirmed": "Đã xác nhận thanh toán. Sản phẩm của bạn sẽ được giao trong vài giây.",
    "top_up_confirmed": "Đã xác nhận nạp tiền. Số dư của bạn sẽ được cập nhật trong vài giây.",
    "product_out_of_stock": "Sản phẩm này tạm thời đã hết.",
    "stock": (
        "🔄 Tình trạng còn hàng:\n\n"
        "ChatGPT Plus NW: {plus_nw}\n"
        "ChatGPT Plus FW: {plus_fw}\n"
        "GPT Pro/5x NW: {pro5_nw}\n"
        "GPT Pro/20x NW: {pro20_nw}"
    ),
    "stock_list": "🔄 Tình trạng còn hàng:\n\n{items}",
    "queue": (
        "🕒 Xếp hàng\n\n"
        "Bạn có thể đặt trước một tài khoản. Khi có hàng trở lại, hệ thống sẽ tự động giao cho bạn."
    ),
    "queue_choose_quantity": "Chọn số lượng:",
    "queue_invoice": (
        "🕒 Đơn đặt trước\n"
        "Sản phẩm: {product}\n"
        "Số lượng: {quantity}\n"
        "Giá: {amount}\n"
        "Hoá đơn Crypto Pay: {usd_amount}\n\n"
        "Nhấn nút bên dưới để thanh toán. Khi có hàng trở lại, hệ thống sẽ tự động giao cho bạn."
    ),
    "queue_added": (
        "✅ Đã thêm vào danh sách chờ: {product}\n"
        "Chúng tôi sẽ tự động thông báo khi có hàng."
    ),
    "queue_already": "Bạn đã ở trong danh sách chờ cho: {product}.",
    "queue_available": "🎉 Có hàng trở lại: {product}\nBạn có thể mua ngay.",
    "no_stock_after_payment": (
        "✅ Đã nhận thanh toán.\n\n"
        "Sản phẩm này là đặt trước và sẽ được giao tự động trong {hours} giờ.\n"
        "Bot sẽ gửi tài khoản ngay khi sẵn sàng — bạn không cần làm gì thêm.\n"
        "Thắc mắc: {support}."
    ),
    "delivery_account": (
        "✅ Đơn hàng hoàn tất\n"
        "Sản phẩm: {product}\n\n"
        "Sản phẩm số của bạn:\n<pre>{payload}</pre>\n\n"
        "Không chia sẻ thông tin này với bất kỳ ai."
    ),
    "delivery_balance": "✅ Nạp tiền hoàn tất\nĐã thêm: {amount}\nSố dư hiện tại: {balance}",
    "invite": "账号GPT Plus/Pro顶级品质\n\n🔗 Mời bạn bè vào bot:\n{link}",
    "help": (
        "📖 Trợ giúp\n\n"
        "Hỗ trợ: {support}\n"
        "Dùng các nút bên dưới để xem Điều khoản bán hàng và Chính sách bảo mật."
    ),
    "support_ticket_button": "✉️ Liên hệ hỗ trợ",
    "support_ticket_prompt": "Mô tả vấn đề trong một tin nhắn. Gửi /cancel để huỷ.",
    "support_ticket_created": "✅ Đã tạo yêu cầu #{ticket_id}. Chúng tôi sẽ phản hồi sớm nhất có thể.",
    "support_ticket_message_sent": "✅ Đã thêm tin nhắn vào yêu cầu #{ticket_id}.",
    "support_ticket_reply_button": "💬 Trả lời yêu cầu",
    "support_ticket_reply": "✉️ Phản hồi hỗ trợ cho yêu cầu #{ticket_id}:\n\n{body}",
    "support_ticket_closed": "✅ Yêu cầu #{ticket_id} đã đóng. Nếu cần hỗ trợ thêm, hãy tạo yêu cầu mới.",
    "support_ticket_already_closed": "Yêu cầu này đã được đóng.",
    "support_ticket_too_long": "Tin nhắn quá dài. Tối đa 4000 ký tự.",
    "settings": "⚙️ Cài đặt\n\nThông báo mua hàng: {status}",
    "notifications_on": "đang bật",
    "notifications_off": "đang tắt",
    "enable_notifications": "🔔 Bật thông báo mua hàng",
    "disable_notifications": "🔕 Tắt thông báo mua hàng",
    "notifications_updated": "Đã cập nhật cài đặt thông báo mua hàng.",
    "purchase_notification": (
        "┌─────────────────┐\n"
        "🛍 <b>Vừa có người mua</b>\n"
        "└─────────────────┘\n"
        "📦 Sản phẩm · <b>{product}</b>\n"
        "🔢 Số lượng · <b>{quantity}</b>\n"
        "💵 Tổng · <b>{price}</b>\n"
        "👤 Người mua · <i>{buyer}</i>\n"
        "└╴ Tồn kho đã cập nhật"
    ),
    "disable_purchase_notifications": "🔕 Tắt thông báo mua hàng",
    "stock_replenished": (
        "╭───────────────╮\n"
        "📦 <b>Hàng mới về</b>\n"
        "╰───────────────╯\n"
        "✨ Vừa nhập một lô tài khoản mới.\n"
        "🟢 Tồn kho đã cập nhật — ai nhanh người đó được.\n\n"
        "Mở «Sản phẩm» để xem hàng còn."
    ),
    "catalog": "🛍 Sản phẩm",
    "catalog_empty": "Hiện chưa có sản phẩm nào.",
    "catalog_title": "🛍 Chọn một sản phẩm:",
    "payment_error": "Không thể tạo hoá đơn. Hãy thử lại sau hoặc liên hệ {support}.",
    "generic_error": "Có lỗi xảy ra. Vui lòng thử lại sau.",
    "admin_only": "Lệnh này chỉ dành cho quản trị viên.",
    "admin_good_added": "Đã thêm sản phẩm vào kho: {product}, ID {good_id}.",
    "admin_add_usage": (
        "Cách dùng: /add_good <gpt_plus_nw|gpt_plus_fw|pro_5x_nw|pro_20x_nw> <sản phẩm số>."
    ),
    "admin_stock": "Kho:\n{stock}",
    "stock_empty": "Kho trống.",
}

_HI: dict[str, str] = {
    "choose_language": "कृपया भाषा चुनें:",
    "language_saved": "भाषा बदल दी गई।",
    "welcome": "स्वागत है! कोई उत्पाद चुनें या मेन्यू खोलें।",
    "unknown_command": "कृपया मेन्यू के बटनों में से किसी एक का उपयोग करें।",
    "choose_pro_plan": "Pro प्लान चुनें:",
    "choose_plus_plan": "Plus खाते का प्रकार चुनें:",
    "balance": "💰 शेष राशि: {balance}\n\nआप Crypto Pay से पैसे जोड़ सकते हैं।",
    "top_up": "💳 जोड़ने के लिए राशि चुनें:",
    "top_up_other": "{currency} में जोड़ने के लिए राशि दर्ज करें:",
    "top_up_invalid": "मान्य राशि दर्ज करें, उदाहरण के लिए {example}।",
    "top_up_invoice": (
        "राशि जोड़ने का इनवॉइस बन गया: {amount}\n"
        "Crypto Pay इनवॉइस: {usd_amount}\n"
        "भुगतान के लिए नीचे का बटन दबाएँ।\n"
        "भुगतान के बाद आपकी शेष राशि अपने आप अपडेट हो जाएगी।"
    ),
    "mpay_method": "{amount} का भुगतान कैसे करना है, चुनें:",
    "mpay_choose_asset": "सिक्का चुनें (राशि: {amount}):",
    "mpay_choose_network": (
        "{asset} कई नेटवर्क पर चलता है। वही चुनें जो आपका वॉलेट वाकई इस्तेमाल करता है:\n\n"
        "⚠️ गलत नेटवर्क पर भेजी गई राशि वापस नहीं मिल सकती।"
    ),
    "mpay_ask_hash": (
        "इस ट्रांसफ़र का ट्रांज़ैक्शन हैश भेजें।\n"
        "यह आपके वॉलेट के इतिहास या ब्लॉक एक्सप्लोरर में मिलेगा।"
    ),
    "mpay_hash_invalid": (
        "यह ट्रांज़ैक्शन हैश जैसा नहीं लगता। जैसा आपका वॉलेट दिखाता है, पूरा हैश भेजें "
        "(16–120 अक्षर, बिना स्पेस)।"
    ),
    "mpay_hash_aborted": (
        "हैश का इंतज़ार बंद कर दिया गया। आपका भुगतान अनुरोध अभी भी खुला है — अगर आपने पैसे भेज "
        "दिए हैं, तो भुगतान संदेश पर वापस जाकर फिर से भुगतान जाँचने का बटन दबाएँ।"
    ),
    "mpay_hash_duplicate": (
        "यह ट्रांज़ैक्शन हैश पहले ही भेजा जा चुका है। अगर यह सचमुच नया ट्रांसफ़र है, तो "
        "{support} से संपर्क करें।"
    ),
    "mpay_submitted": (
        "✅ अनुरोध #{payment_id} मिल गया।\n"
        "एडमिन ब्लॉक एक्सप्लोरर पर ट्रांज़ैक्शन जाँचेगा; पुष्टि होने पर शेष राशि अपडेट हो जाएगी।\n"
        "अगर बहुत देर लगे तो {support} से संपर्क करें।"
    ),
    "mpay_confirmed": (
        "✅ ट्रांसफ़र #{payment_id} की पुष्टि हो गई।\n"
        "जोड़ा गया: {amount}\n"
        "शेष राशि: {balance}"
    ),
    "mpay_rejected": (
        "❌ ट्रांसफ़र #{payment_id} की पुष्टि नहीं हुई।\n"
        "एडमिन को यह ब्लॉकचेन पर नहीं मिला, या राशि अनुरोध से मेल नहीं खाई। "
        "{support} से संपर्क करें।"
    ),
    "mpay_cancelled": (
        "अनुरोध #{payment_id} रद्द कर दिया गया। अगर आपने पैसे भेज दिए हैं तो {support} से संपर्क करें।"
    ),
    "mpay_unavailable": (
        "अभी cryptocurrency से भुगतान उपलब्ध नहीं है। Crypto Pay का उपयोग करें या "
        "{support} से संपर्क करें।"
    ),
    "mpay_stale": "यह बटन अब मान्य नहीं है। राशि जोड़ना फिर से शुरू करें।",
    "mpay_open_exists": (
        "आपका एक अनुरोध #{payment_id} पहले से खुला है। पहले उसे पूरा करें या रद्द करें।"
    ),
    "mpay_admin_new": (
        "🆕 पुष्टि के लिए प्रतीक्षारत crypto ट्रांसफ़र #{payment_id}\n\n"
        "उपयोगकर्ता: {user}\n"
        "सिक्का / नेटवर्क: {asset} / {network}\n"
        "अनुरोधित: {fiat_amount}\n"
        "अपेक्षित: {crypto_amount}\n"
        "पता: <code>{address}</code>\n"
        "Tx हैश: <code>{tx_hash}</code>\n\n"
        "पुष्टि से पहले हैश, राशि और नेटवर्क ब्लॉक एक्सप्लोरर पर जाँच लें।"
    ),
    "mpay_admin_confirmed": "✅ #{payment_id} की पुष्टि हुई, {user} को {amount} जोड़ा गया।",
    "mpay_admin_rejected": "❌ #{payment_id} अस्वीकृत, कुछ भी नहीं जोड़ा गया।",
    "mpay_admin_already": "#{payment_id} को किसी दूसरे एडमिन ने पहले ही निपटा दिया है।",
    "mpay_admin_none_pending": "पुष्टि के लिए कोई crypto ट्रांसफ़र प्रतीक्षारत नहीं है।",
    "product_invoice": (
        "उत्पाद: {product}\n"
        "प्रदर्शित कीमत: {amount}\n"
        "Crypto Pay इनवॉइस: {usd_amount}\n\n"
        "crypto से भुगतान के लिए नीचे का बटन दबाएँ।"
    ),
    "pay": "💳 भुगतान करें",
    "pay_balance": "💰 शेष राशि से भुगतान करें",
    "balance_insufficient": "शेष राशि पर्याप्त नहीं है। कृपया पहले राशि जोड़ें।",
    "check_payment": "🔄 भुगतान जाँचें",
    "payment_pending": "भुगतान की अभी पुष्टि नहीं हुई है।",
    "payment_expired": "इनवॉइस की अवधि समाप्त हो गई। कृपया नया ऑर्डर बनाएँ।",
    "payment_confirmed": "भुगतान की पुष्टि हो गई। आपका सामान कुछ सेकंड में दे दिया जाएगा।",
    "top_up_confirmed": "राशि जोड़ने की पुष्टि हो गई। आपकी शेष राशि कुछ सेकंड में अपडेट हो जाएगी।",
    "product_out_of_stock": "यह उत्पाद अस्थायी रूप से उपलब्ध नहीं है।",
    "stock": (
        "🔄 उपलब्धता:\n\n"
        "ChatGPT Plus NW: {plus_nw}\n"
        "ChatGPT Plus FW: {plus_fw}\n"
        "GPT Pro/5x NW: {pro5_nw}\n"
        "GPT Pro/20x NW: {pro20_nw}"
    ),
    "stock_list": "🔄 उपलब्धता:\n\n{items}",
    "queue": (
        "🕒 प्रतीक्षा सूची\n\n"
        "आप खाता पहले से बुक कर सकते हैं। जैसे ही स्टॉक आएगा, सिस्टम अपने आप आपको दे देगा।"
    ),
    "queue_choose_quantity": "मात्रा चुनें:",
    "queue_invoice": (
        "🕒 प्रतीक्षा सूची का ऑर्डर\n"
        "उत्पाद: {product}\n"
        "मात्रा: {quantity}\n"
        "कीमत: {amount}\n"
        "Crypto Pay इनवॉइस: {usd_amount}\n\n"
        "भुगतान के लिए नीचे का बटन दबाएँ। स्टॉक आने पर सिस्टम अपने आप आपको दे देगा।"
    ),
    "queue_added": (
        "✅ प्रतीक्षा सूची में जोड़ा गया: {product}\n"
        "उपलब्ध होने पर हम आपको अपने आप सूचित करेंगे।"
    ),
    "queue_already": "आप पहले से ही इसकी प्रतीक्षा सूची में हैं: {product}।",
    "queue_available": "🎉 फिर से उपलब्ध: {product}\nआप अभी खरीद सकते हैं।",
    "no_stock_after_payment": (
        "✅ भुगतान प्राप्त हो गया।\n\n"
        "यह उत्पाद प्री-ऑर्डर पर है और {hours} घंटे के भीतर स्वचालित रूप से डिलीवर होगा।\n"
        "खाता तैयार होते ही बॉट उसे भेज देगा — आपको कुछ नहीं करना है।\n"
        "प्रश्न: {support}।"
    ),
    "delivery_account": (
        "✅ ऑर्डर पूरा हुआ\n"
        "उत्पाद: {product}\n\n"
        "आपका डिजिटल सामान:\n<pre>{payload}</pre>\n\n"
        "यह जानकारी किसी के साथ साझा न करें।"
    ),
    "delivery_balance": "✅ राशि जुड़ गई\nजोड़ा गया: {amount}\nवर्तमान शेष राशि: {balance}",
    "invite": "账号GPT Plus/Pro顶级品质\n\n🔗 दोस्तों को बॉट में बुलाएँ:\n{link}",
    "help": (
        "📖 सहायता\n\n"
        "सहायता: {support}\n"
        "बिक्री की शर्तें और गोपनीयता नीति देखने के लिए नीचे के बटनों का उपयोग करें।"
    ),
    "support_ticket_button": "✉️ सहायता से संपर्क करें",
    "support_ticket_prompt": "अपनी समस्या एक संदेश में लिखें। रद्द करने के लिए /cancel भेजें।",
    "support_ticket_created": "✅ अनुरोध #{ticket_id} बना दिया गया है। हम जल्द से जल्द जवाब देंगे।",
    "support_ticket_message_sent": "✅ आपका संदेश अनुरोध #{ticket_id} में जोड़ दिया गया है।",
    "support_ticket_reply_button": "💬 अनुरोध का जवाब दें",
    "support_ticket_reply": "✉️ अनुरोध #{ticket_id} पर सहायता का जवाब:\n\n{body}",
    "support_ticket_closed": "✅ अनुरोध #{ticket_id} बंद कर दिया गया है। आगे मदद चाहिए तो नया अनुरोध बनाएँ।",
    "support_ticket_already_closed": "यह अनुरोध पहले ही बंद है।",
    "support_ticket_too_long": "संदेश बहुत लंबा है। अधिकतम 4000 अक्षर।",
    "settings": "⚙️ सेटिंग्स\n\nखरीद सूचनाएँ: {status}",
    "notifications_on": "चालू",
    "notifications_off": "बंद",
    "enable_notifications": "🔔 खरीद सूचनाएँ चालू करें",
    "disable_notifications": "🔕 खरीद सूचनाएँ बंद करें",
    "notifications_updated": "खरीद सूचनाओं की सेटिंग अपडेट हो गई।",
    "purchase_notification": (
        "┌─────────────────┐\n"
        "🛍 <b>किसी ने अभी खरीदा</b>\n"
        "└─────────────────┘\n"
        "📦 उत्पाद · <b>{product}</b>\n"
        "🔢 मात्रा · <b>{quantity}</b>\n"
        "💵 कुल · <b>{price}</b>\n"
        "👤 खरीदार · <i>{buyer}</i>\n"
        "└╴ स्टॉक अपडेट हो गया"
    ),
    "disable_purchase_notifications": "🔕 खरीद सूचनाएँ बंद करें",
    "stock_replenished": (
        "╭───────────────╮\n"
        "📦 <b>नया स्टॉक आया</b>\n"
        "╰───────────────╯\n"
        "✨ खातों की नई खेप आ गई है।\n"
        "🟢 स्टॉक अपडेट है — पहले आइए, पहले पाइए।\n\n"
        "उपलब्धता देखने के लिए «उत्पाद» खोलें।"
    ),
    "catalog": "🛍 उत्पाद",
    "catalog_empty": "अभी कोई उत्पाद उपलब्ध नहीं है।",
    "catalog_title": "🛍 कोई उत्पाद चुनें:",
    "payment_error": "इनवॉइस नहीं बन सका। बाद में फिर कोशिश करें या {support} से संपर्क करें।",
    "generic_error": "कुछ गड़बड़ हो गई। कृपया बाद में फिर कोशिश करें।",
    "admin_only": "यह कमांड केवल एडमिन के लिए है।",
    "admin_good_added": "स्टॉक में जोड़ा गया: {product}, ID {good_id}।",
    "admin_add_usage": (
        "उपयोग: /add_good <gpt_plus_nw|gpt_plus_fw|pro_5x_nw|pro_20x_nw> <डिजिटल सामान>।"
    ),
    "admin_stock": "स्टॉक:\n{stock}",
    "stock_empty": "स्टॉक खाली है।",
}

for _code, _table in (("vi", _VI), ("hi", _HI)):
    for _key, _value in _table.items():
        TEXTS[_key][_code] = _value

_missing = {
    code: sorted(key for key, row in TEXTS.items() if code not in row)
    for code in LANGUAGES
}
_missing = {code: keys for code, keys in _missing.items() if keys}
if _missing:
    raise RuntimeError(f"i18n is missing translations: {_missing}")


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
    "vi": {
        "plus": "⚡GPT Plus",
        "pro": "🚀 Pro",
        "balance": "💰Số dư",
        "invite": "🔗Mời bạn",
        "stock": "🔄Kiểm tra hàng",
        "queue": "🕒Xếp hàng",
        "catalog": "🛍Sản phẩm",
        "help": "📖Trợ giúp",
        "settings": "⚙️Cài đặt",
        "language": "🌐Ngôn ngữ",
    },
    "hi": {
        "plus": "⚡GPT Plus",
        "pro": "🚀 Pro",
        "balance": "💰शेष राशि",
        "invite": "🔗आमंत्रित करें",
        "stock": "🔄स्टॉक देखें",
        "queue": "🕒प्रतीक्षा सूची",
        "catalog": "🛍उत्पाद",
        "help": "📖सहायता",
        "settings": "⚙️सेटिंग्स",
        "language": "🌐भाषा",
    },
}


def t(language: str | None, key: str, **kwargs: object) -> str:
    language = language if language in LANGUAGES else "en"
    row = TEXTS[key]
    template = row.get(language) or row["en"]
    return template.format(**kwargs)


def language_keyboard() -> InlineKeyboardMarkup:
    """Two languages per row, so the full name fits next to the flag.

    Five buttons on one row leaves Telegram about a fifth of the width each,
    which truncates "Tiếng Việt" and "Русский" to something the buyer has to
    guess at. Two per row is wide enough for every name we ship.
    """
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"lang:{code}")
        for code, label in LANGUAGE_BUTTONS
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    labels = _pick(
        {
            "zh": {"offer": "📄 销售条款", "privacy": "🔒 隐私政策"},
            "en": {"offer": "📄 Terms of Sale", "privacy": "🔒 Privacy Policy"},
            "ru": {"offer": "📄 Оферта", "privacy": "🔒 Политика конфиденциальности"},
            "vi": {"offer": "📄 Điều khoản bán hàng", "privacy": "🔒 Chính sách bảo mật"},
            "hi": {"offer": "📄 बिक्री की शर्तें", "privacy": "🔒 गोपनीयता नीति"},
        },
        language,
    )
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
        "vi": "💳 Nạp tiền",
        "hi": "💳 राशि जोड़ें",
    }
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_pick(labels, language),
                    callback_data="topup",
                    style=ButtonStyle.SUCCESS,
                )
            ],
        ]
    )


# The floor for a top-up, in USD cents. Below this the Crypto Pay invoice costs
# more in network fees than it carries, so the buyer is told the minimum up
# front rather than being bounced after typing a figure.
MIN_TOPUP_CENTS = 130

# Preset top-up buttons, in USD cents. The first one is the minimum, so the
# cheapest allowed top-up is reachable in a single tap.
TOPUP_PRESETS_CENTS = (MIN_TOPUP_CENTS, 200, 500, 1000)


def top_up_keyboard(language: str, amount_labels: dict[int, str] | None = None) -> InlineKeyboardMarkup:
    labels = {
        "zh": "充值 {amount}",
        "en": "Top up {amount}",
        "ru": "Пополнить {amount}",
        "vi": "Nạp {amount}",
        "hi": "{amount} जोड़ें",
    }
    other_labels = {
        "zh": "✏️ 其他",
        "en": "✏️ Other",
        "ru": "✏️ Другая сумма",
        "vi": "✏️ Số khác",
        "hi": "✏️ अन्य राशि",
    }
    cancel_labels = {
        "zh": "✖️ 取消",
        "en": "✖️ Cancel",
        "ru": "✖️ Отмена",
        "vi": "✖️ Huỷ",
        "hi": "✖️ रद्द करें",
    }
    language = language if language in LANGUAGES else "en"
    template = _pick(labels, language)

    # The caller supplies the labels already converted into the buyer's own
    # currency, keyed by USD cents; the USD fallback only shows up if it forgot.
    def preset(cents: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=template.format(
                amount=(amount_labels or {}).get(cents, f"${cents / 100:.2f}")
            ),
            callback_data=f"topup:{cents}",
        )

    presets = [preset(cents) for cents in TOPUP_PRESETS_CENTS]
    rows = [presets[index : index + 2] for index in range(0, len(presets), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text=_pick(other_labels, language),
                callback_data="topup:other",
            ),
            InlineKeyboardButton(
                text=_pick(cancel_labels, language),
                callback_data="topup:cancel",
                style=ButtonStyle.DANGER,
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard(language: str, callback_data: str = "topup:cancel") -> InlineKeyboardMarkup:
    """A single way out of a prompt that is waiting for typed input.

    Without it the buyer who opened "other amount" by mistake has no way back:
    every message they send is read as an amount, so the bot keeps asking.
    """
    labels = {
        "zh": "✖️ 取消",
        "en": "✖️ Cancel",
        "ru": "✖️ Отмена",
        "vi": "✖️ Huỷ",
        "hi": "✖️ रद्द करें",
    }
    language = language if language in LANGUAGES else "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_pick(labels, language),
                    callback_data=callback_data,
                    style=ButtonStyle.DANGER,
                )
            ]
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
    # Product names, so they read the same in every language.
    labels = {"nw": "⚡ Plus NW", "fw": "⚡ Plus FW"}
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
    # Product names, so they read the same in every language.
    labels = {"5": "🚀 Pro 5x NW", "20": "🚀 Pro 20x NW"}
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
    # Product names, so they read the same in every language.
    labels = {
        "plus_nw": "ChatGPT Plus NW",
        "plus_fw": "ChatGPT Plus FW",
        "pro5_nw": "GPT Pro/5x NW",
        "pro20_nw": "GPT Pro/20x NW",
    }
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
    labels = {
        "zh": "数量 {quantity}",
        "en": "Quantity {quantity}",
        "ru": "Количество {quantity}",
        "vi": "Số lượng {quantity}",
        "hi": "मात्रा {quantity}",
    }
    template = _pick(labels, language)
    quantities = (1, 2, 3, 5)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=template.format(quantity=quantity),
                    callback_data=f"queue_qty:{product_key}:{quantity}",
                )
                for quantity in quantities[:2]
            ],
            [
                InlineKeyboardButton(
                    text=template.format(quantity=quantity),
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
    labels = {
        "zh": "🕒 加入排队",
        "en": "🕒 Join queue",
        "ru": "🕒 В очередь",
        "vi": "🕒 Vào danh sách chờ",
        "hi": "🕒 प्रतीक्षा सूची में",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_pick(labels, language),
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
            "vi": "🛒 Mua nhiều",
            "hi": "🛒 कई खरीदें",
        }
        rows.append(
            [
                InlineKeyboardButton(
                    text=_pick(buy_many_labels, language),
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
    # Left untranslated on purpose: the owner wants the same wording in every
    # language, the way the coin tickers are the same everywhere. Neither label
    # explains itself here — the two names go out bare.
    auto = "⚡ Crypto Pay"
    manual = "🪙 Cryptocurrency"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=auto,
                    callback_data=f"cpay:{amount_cents}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=manual,
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
    back = {
        "zh": "◀️ 返回",
        "en": "◀️ Back",
        "ru": "◀️ Назад",
        "vi": "◀️ Quay lại",
        "hi": "◀️ वापस",
    }
    rows.append(
        [InlineKeyboardButton(text=_pick(back, language), callback_data=f"topup:{amount_cents}")]
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
    back = {
        "zh": "◀️ 返回",
        "en": "◀️ Back",
        "ru": "◀️ Назад",
        "vi": "◀️ Quay lại",
        "hi": "◀️ वापस",
    }
    rows.append(
        [InlineKeyboardButton(text=_pick(back, language), callback_data=f"mpay:assets:{amount_cents}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mpay_pending_keyboard(language: str, payment_id: int) -> InlineKeyboardMarkup:
    """Buttons under a transfer request.

    The primary button reads "check payment" and routes to ``mpay:check:``,
    which hands the request to the admins without asking the buyer for a
    transaction hash. ``mpay:hash:`` still exists for buyers who want to supply
    one, but nothing in the UI demands it any more.
    """
    language = language if language in LANGUAGES else "en"
    check = {
        "zh": "🔄 检查支付",
        "en": "🔄 Check payment",
        "ru": "🔄 Проверить оплату",
        "vi": "🔄 Kiểm tra thanh toán",
        "hi": "🔄 भुगतान जाँचें",
    }
    cancel = {
        "zh": "✖️ 取消",
        "en": "✖️ Cancel",
        "ru": "✖️ Отменить",
        "vi": "✖️ Huỷ",
        "hi": "✖️ रद्द करें",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_pick(check, language),
                    callback_data=f"mpay:check:{payment_id}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_pick(cancel, language),
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
