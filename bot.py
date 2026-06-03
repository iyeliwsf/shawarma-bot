import os, json, logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
STAFF_BOT_TOKEN = "8969505121:AAFYXK-DRUV7RcWUgBuG2YKNt5c5SDulDac"
OWNER_BOT_TOKEN = "8958494523:AAEo8lnjuPk27qVKi4TNcPNaFK5oOYQMdd4"
OWNER_ID        = 1067385281
TZ              = ZoneInfo("Europe/Istanbul")
KM_RATE         = 5  # ₺ за км

# Заполни реальными Telegram ID после регистрации
CASHIERS = {
    OWNER_ID: "Мурад",
    # 111111111: "Ильхам",
    # 222222222: "Сальма",
    # 333333333: "Милена",
    # 444444444: "Раджаб",
}
COURIERS = {
    OWNER_ID: "Мурад",
    # 555555555: "Энгин",
    # 666666666: "Самет",
}
CASHIER_NAMES = ["Ильхам", "Сальма", "Милена", "Раджаб"]
COURIER_NAMES = ["Энгин", "Самет", "Курьер 3"]

# ─── STATES ───────────────────────────────────────────────────────────────────
(
    S_SHIFT_OPENER, S_SHIFT_TYPE, S_CASH_START,
    S_CASH_OFFLINE, S_CASH_COURIER,
    S_CARD_KUV, S_CARD_ZIR, S_IBAN,
    S_YEMEK, S_TREND, S_YEMEK_CASH, S_MIGROS, S_GETIR,
    S_EXPENSES, S_EXPENSE_AMOUNT, S_EXPENSE_TYPE, S_EXPENSE_COMMENT, S_EXPENSE_MORE,
    S_C1_KM, S_C2_KM, S_C3_KM,
    S_ADVANCES, S_ADV_NAME, S_ADV_AMOUNT, S_ADV_MORE,
    S_EXTRA, S_CONFIRM,
) = range(27)

ADV_WHO, ADV_AMT, ADV_CONF = range(100, 103)

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def kb_num():
    return ReplyKeyboardMarkup([["0"], ["◀️ Назад"]], resize_keyboard=True)

def kb_skip():
    return ReplyKeyboardMarkup([["Пропустить"], ["◀️ Назад"]], resize_keyboard=True)

def kb_yesno():
    return ReplyKeyboardMarkup([["✅ Да, добавить ещё"], ["➡️ Продолжить"], ["◀️ Назад"]], resize_keyboard=True)

def kb_names(names):
    rows = [[n] for n in names]
    rows.append(["◀️ Назад"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def kb_shifts():
    return ReplyKeyboardMarkup([["🌅 12:00-18:00", "🌆 18:00-00:00"], ["🌙 00:00-03:00 (пт-вс)"], ["◀️ Назад"]], resize_keyboard=True)

def kb_expense_type():
    return ReplyKeyboardMarkup([["💳 Карта", "💵 Наличные"], ["◀️ Назад"]], resize_keyboard=True)

def remove_kb():
    return ReplyKeyboardRemove()

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_name(uid):
    if uid in CASHIERS: return CASHIERS[uid]
    if uid in COURIERS: return COURIERS[uid]
    return "Неизвестный"

def now_str(): return datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
def today_str(): return datetime.now(TZ).strftime("%d.%m.%Y")

def parse_num(t):
    try: return float(t.replace(",", ".").strip())
    except: return 0.0

async def send_owner(ctx, text):
    """Отправить сообщение владельцу через его бота"""
    try:
        owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
        await owner_app.bot.send_message(OWNER_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Owner notify error: {e}")

async def msg(update, text, kb=None):
    await update.message.reply_text(text, reply_markup=kb or remove_kb(), parse_mode="Markdown")

def is_back(text): return text == "◀️ Назад"
def is_skip(text): return text in ("Пропустить", "0")

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = get_name(uid)
    is_cash = uid in CASHIERS or uid == OWNER_ID
    is_cur  = uid in COURIERS or uid == OWNER_ID
    buttons = []
    if is_cash: buttons.append([InlineKeyboardButton("📋 Отчёт кассира", callback_data="cashier")])
    if is_cur:  buttons.append([InlineKeyboardButton("🚗 Отчёт курьера", callback_data="courier")])
    buttons.append([InlineKeyboardButton("💰 Запросить аванс", callback_data="advance")])
    await update.message.reply_text(
        f"👋 Привет, *{name}*!\n🕐 {now_str()}\n\nЧто делаем?",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
    )

# ─── КАССИР: ОТЧЁТ ────────────────────────────────────────────────────────────
async def cashier_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.clear()
    ctx.user_data["date"] = today_str()
    ctx.user_data["cashier"] = get_name(q.from_user.id)
    ctx.user_data["uid"] = q.from_user.id
    ctx.user_data["expenses"] = []
    ctx.user_data["advances"] = []
    await q.message.reply_text(
        "📋 *Отчёт за смену*\n\n👤 Кто открыл кассу?",
        reply_markup=kb_names(CASHIER_NAMES), parse_mode="Markdown"
    )
    return S_SHIFT_OPENER

async def s_shift_opener(u, ctx):
    if is_back(u.message.text):
        await start_from_msg(u, ctx); return ConversationHandler.END
    ctx.user_data["opener"] = u.message.text
    await msg(u, "🕐 Какая смена?", kb_shifts())
    return S_SHIFT_TYPE

async def s_shift_type(u, ctx):
    if is_back(u.message.text):
        await msg(u, "👤 Кто открыл кассу?", kb_names(CASHIER_NAMES)); return S_SHIFT_OPENER
    ctx.user_data["shift"] = u.message.text
    await msg(u, "💵 *Остаток в кассе на начало смены (₺):*\n(сколько было денег когда открыли)", kb_num())
    return S_CASH_START

async def s_cash_start(u, ctx):
    if is_back(u.message.text):
        await msg(u, "🕐 Какая смена?", kb_shifts()); return S_SHIFT_TYPE
    ctx.user_data["cash_start"] = parse_num(u.message.text)
    await msg(u, "*1️⃣ Наличные offline (₺):*", kb_num())
    return S_CASH_OFFLINE

async def s_cash_offline(u, ctx):
    if is_back(u.message.text):
        await msg(u, "💵 Остаток в кассе на начало:", kb_num()); return S_CASH_START
    ctx.user_data["cash_offline"] = parse_num(u.message.text)
    await msg(u, "*2️⃣ Наличные курьер (₺):*", kb_num())
    return S_CASH_COURIER

async def s_cash_courier(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*1️⃣ Наличные offline (₺):*", kb_num()); return S_CASH_OFFLINE
    ctx.user_data["cash_courier"] = parse_num(u.message.text)
    await msg(u, "*3️⃣ Карта Kuvveyt (₺):*", kb_num())
    return S_CARD_KUV

async def s_card_kuv(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*2️⃣ Наличные курьер (₺):*", kb_num()); return S_CASH_COURIER
    ctx.user_data["card_kuvveyt"] = parse_num(u.message.text)
    await msg(u, "*4️⃣ Карта Ziraat (₺):*", kb_num())
    return S_CARD_ZIR

async def s_card_zir(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*3️⃣ Карта Kuvveyt (₺):*", kb_num()); return S_CARD_KUV
    ctx.user_data["card_ziraat"] = parse_num(u.message.text)
    await msg(u, "*5️⃣ IBAN (₺):*", kb_num())
    return S_IBAN

async def s_iban(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*4️⃣ Карта Ziraat (₺):*", kb_num()); return S_CARD_ZIR
    ctx.user_data["iban"] = parse_num(u.message.text)
    await msg(u, "*6️⃣ Yemeksepeti (₺):*", kb_num())
    return S_YEMEK

async def s_yemek(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*5️⃣ IBAN (₺):*", kb_num()); return S_IBAN
    ctx.user_data["yemeksepeti"] = parse_num(u.message.text)
    await msg(u, "*7️⃣ Trendyol (₺):*", kb_num())
    return S_TREND

async def s_trend(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*6️⃣ Yemeksepeti (₺):*", kb_num()); return S_YEMEK
    ctx.user_data["trendyol"] = parse_num(u.message.text)
    await msg(u, "*8️⃣ Yemeksepeti наличка (₺):*", kb_num())
    return S_YEMEK_CASH

async def s_yemek_cash(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*7️⃣ Trendyol (₺):*", kb_num()); return S_TREND
    ctx.user_data["yemek_cash"] = parse_num(u.message.text)
    await msg(u, "*9️⃣ Migros (₺):*", kb_num())
    return S_MIGROS

async def s_migros(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*8️⃣ Yemeksepeti наличка (₺):*", kb_num()); return S_YEMEK_CASH
    ctx.user_data["migros"] = parse_num(u.message.text)
    await msg(u, "*🔟 Getir Yemek (₺):*", kb_num())
    return S_GETIR

async def s_getir(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*9️⃣ Migros (₺):*", kb_num()); return S_MIGROS
    ctx.user_data["getir"] = parse_num(u.message.text)
    exps = ctx.user_data.get("expenses", [])
    n = len(exps) + 1
    await msg(u, f"💸 *Расход #{n}*\nТип оплаты:", kb_expense_type())
    return S_EXPENSE_TYPE

async def s_expense_type(u, ctx):
    if is_back(u.message.text):
        await msg(u, "*🔟 Getir Yemek (₺):*", kb_num()); return S_GETIR
    ctx.user_data["_exp_type"] = u.message.text
    await msg(u, f"💸 Сумма расхода (₺):\n(0 если не было)", kb_num())
    return S_EXPENSE_AMOUNT

async def s_expense_amount(u, ctx):
    if is_back(u.message.text):
        await msg(u, "Тип оплаты:", kb_expense_type()); return S_EXPENSE_TYPE
    amt = parse_num(u.message.text)
    ctx.user_data["_exp_amount"] = amt
    if amt > 0:
        await msg(u, "📝 Комментарий к расходу:")
        return S_EXPENSE_COMMENT
    # 0 — пропускаем расходы
    ctx.user_data["_exp_type"] = ""
    await ask_couriers(u, ctx)
    return S_C1_KM

async def s_expense_comment(u, ctx):
    if is_back(u.message.text):
        await msg(u, "Сумма расхода (₺):", kb_num()); return S_EXPENSE_AMOUNT
    ctx.user_data["expenses"].append({
        "type": ctx.user_data.get("_exp_type", ""),
        "amount": ctx.user_data.get("_exp_amount", 0),
        "comment": u.message.text
    })
    await msg(u, "Добавить ещё расход?", kb_yesno())
    return S_EXPENSE_MORE

async def s_expense_more(u, ctx):
    if is_back(u.message.text):
        await msg(u, "📝 Комментарий:", None); return S_EXPENSE_COMMENT
    if u.message.text == "✅ Да, добавить ещё":
        n = len(ctx.user_data["expenses"]) + 1
        await msg(u, f"💸 *Расход #{n}*\nТип оплаты:", kb_expense_type())
        return S_EXPENSE_TYPE
    await ask_couriers(u, ctx)
    return S_C1_KM

async def ask_couriers(u, ctx):
    await msg(u, f"🚗 *{COURIER_NAMES[0]}* — сколько км проехал?\n(или 0)", kb_num())

async def s_c1_km(u, ctx):
    if is_back(u.message.text):
        await msg(u, "Добавить ещё расход?", kb_yesno()); return S_EXPENSE_MORE
    km = parse_num(u.message.text)
    ctx.user_data["c1_km"] = km
    ctx.user_data["c1_sum"] = km * KM_RATE
    await msg(u, f"🚗 *{COURIER_NAMES[1]}* — сколько км проехал?\n(или 0)", kb_num())
    return S_C2_KM

async def s_c2_km(u, ctx):
    if is_back(u.message.text):
        await msg(u, f"🚗 *{COURIER_NAMES[0]}* — км:", kb_num()); return S_C1_KM
    km = parse_num(u.message.text)
    ctx.user_data["c2_km"] = km
    ctx.user_data["c2_sum"] = km * KM_RATE
    await msg(u, f"🚗 *{COURIER_NAMES[2]}* — сколько км?\n(или 0)", kb_num())
    return S_C3_KM

async def s_c3_km(u, ctx):
    if is_back(u.message.text):
        await msg(u, f"🚗 *{COURIER_NAMES[1]}* — км:", kb_num()); return S_C2_KM
    km = parse_num(u.message.text)
    ctx.user_data["c3_km"] = km
    ctx.user_data["c3_sum"] = km * KM_RATE
    advs = ctx.user_data.get("advances", [])
    n = len(advs) + 1
    await msg(u, f"💰 *Аванс #{n}* — кто брал?\n(имя или Пропустить)", kb_names(CASHIER_NAMES + ["Пропустить"]))
    return S_ADV_NAME

async def s_adv_name(u, ctx):
    if is_back(u.message.text):
        await msg(u, f"🚗 *{COURIER_NAMES[2]}* — км:", kb_num()); return S_C3_KM
    if is_skip(u.message.text):
        await msg(u, "📌 Доп. заметки:\n(или Пропустить)", kb_skip())
        return S_EXTRA
    ctx.user_data["_adv_name"] = u.message.text
    await msg(u, f"💵 Сколько взял {u.message.text} (₺)?", kb_num())
    return S_ADV_AMOUNT

async def s_adv_amount(u, ctx):
    if is_back(u.message.text):
        await msg(u, "💰 Кто брал аванс?", kb_names(CASHIER_NAMES + ["Пропустить"])); return S_ADV_NAME
    ctx.user_data["advances"].append({
        "name": ctx.user_data.get("_adv_name", ""),
        "amount": parse_num(u.message.text)
    })
    await msg(u, "Добавить ещё аванс?", kb_yesno())
    return S_ADV_MORE

async def s_adv_more(u, ctx):
    if u.message.text == "✅ Да, добавить ещё":
        n = len(ctx.user_data["advances"]) + 1
        await msg(u, f"💰 *Аванс #{n}* — кто брал?", kb_names(CASHIER_NAMES + ["Пропустить"]))
        return S_ADV_NAME
    await msg(u, "📌 Доп. заметки:\n(или Пропустить)", kb_skip())
    return S_EXTRA

async def s_extra(u, ctx):
    if is_back(u.message.text):
        await msg(u, "Добавить ещё аванс?", kb_yesno()); return S_ADV_MORE
    ctx.user_data["extra"] = "" if is_skip(u.message.text) else u.message.text
    return await show_confirm(u, ctx)

async def show_confirm(u, ctx):
    d = ctx.user_data
    # Считаем итоги
    income_keys = ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"]
    total_income = sum(d.get(k,0) for k in income_keys)
    total_exp = sum(e["amount"] for e in d.get("expenses",[]))
    total_adv = sum(a["amount"] for a in d.get("advances",[]))
    total_km_pay = sum([d.get("c1_sum",0), d.get("c2_sum",0), d.get("c3_sum",0)])
    cash_start = d.get("cash_start", 0)
    cash_income = d.get("cash_offline",0) + d.get("cash_courier",0) + d.get("yemek_cash",0)
    cash_expenses = sum(e["amount"] for e in d.get("expenses",[]) if "Наличные" in e.get("type",""))
    cash_end = cash_start + cash_income - cash_expenses - total_adv

    text = (
        f"✅ *Проверь отчёт — {d['date']}*\n"
        f"Кассир: {d.get('opener','?')} | Смена: {d.get('shift','?')}\n"
        f"💵 Касса на старте: `{cash_start:,.0f}` ₺\n\n"
        f"*Поступления:*\n"
        f"  Нал. offline: `{d.get('cash_offline',0):,.0f}` ₺\n"
        f"  Нал. курьер: `{d.get('cash_courier',0):,.0f}` ₺\n"
        f"  Kuvveyt: `{d.get('card_kuvveyt',0):,.0f}` ₺\n"
        f"  Ziraat: `{d.get('card_ziraat',0):,.0f}` ₺\n"
        f"  IBAN: `{d.get('iban',0):,.0f}` ₺\n"
        f"  Yemeksepeti: `{d.get('yemeksepeti',0):,.0f}` ₺\n"
        f"  Trendyol: `{d.get('trendyol',0):,.0f}` ₺\n"
        f"  Yemek нал.: `{d.get('yemek_cash',0):,.0f}` ₺\n"
        f"  Migros: `{d.get('migros',0):,.0f}` ₺\n"
        f"  Getir: `{d.get('getir',0):,.0f}` ₺\n"
        f"  ━━━━━━━━━\n"
        f"  *ИТОГО: `{total_income:,.0f}` ₺*\n\n"
    )
    if d.get("expenses"):
        text += "*Расходы:*\n"
        for e in d["expenses"]:
            text += f"  {e['type']}: `{e['amount']:,.0f}` ₺ — {e['comment']}\n"
        text += f"  Итого расходы: `{total_exp:,.0f}` ₺\n\n"
    text += f"*Курьеры:*\n"
    text += f"  {COURIER_NAMES[0]}: {d.get('c1_km',0)} км → `{d.get('c1_sum',0):,.0f}` ₺\n"
    text += f"  {COURIER_NAMES[1]}: {d.get('c2_km',0)} км → `{d.get('c2_sum',0):,.0f}` ₺\n"
    text += f"  {COURIER_NAMES[2]}: {d.get('c3_km',0)} км → `{d.get('c3_sum',0):,.0f}` ₺\n\n"
    if d.get("advances"):
        text += "*Авансы:*\n"
        for a in d["advances"]:
            text += f"  {a['name']}: `{a['amount']:,.0f}` ₺\n"
        text += f"  Итого авансы: `{total_adv:,.0f}` ₺\n\n"
    text += f"💰 *Касса на конец смены: `{cash_end:,.0f}` ₺*\n"
    if d.get("extra"): text += f"\n📌 {d['extra']}\n"
    text += "\nВсё верно?"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Отправить", callback_data="confirm_report"),
        InlineKeyboardButton("🔄 Заново", callback_data="cashier")
    ]])
    await u.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return S_CONFIRM

async def confirm_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data != "confirm_report":
        return ConversationHandler.END
    d = ctx.user_data
    income_keys = ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"]
    total = sum(d.get(k,0) for k in income_keys)
    total_adv = sum(a["amount"] for a in d.get("advances",[]))
    cash_start = d.get("cash_start",0)
    cash_income = d.get("cash_offline",0)+d.get("cash_courier",0)+d.get("yemek_cash",0)
    cash_expenses = sum(e["amount"] for e in d.get("expenses",[]) if "Наличные" in e.get("type",""))
    cash_end = cash_start + cash_income - cash_expenses - total_adv

    await q.message.reply_text(
        f"✅ *Отчёт отправлен!*\nВыручка: *{total:,.0f} ₺*\nКасса на конец: *{cash_end:,.0f} ₺*",
        parse_mode="Markdown", reply_markup=remove_kb()
    )

    # Отчёт владельцу через его бота
    owner_text = (
        f"📊 *Новый отчёт!*\n"
        f"📅 {d['date']} | {d.get('shift','')}\n"
        f"👤 Открыл: {d.get('opener','')}\n\n"
        f"💰 Выручка: *{total:,.0f} ₺*\n"
        f"💵 Касса: {d.get('cash_start',0):,.0f} → *{cash_end:,.0f} ₺*\n"
    )
    if d.get("expenses"):
        owner_text += f"💸 Расходы: {sum(e['amount'] for e in d['expenses']):,.0f} ₺\n"
    if d.get("advances"):
        owner_text += f"💰 Авансы: {total_adv:,.0f} ₺ ("
        owner_text += ", ".join(f"{a['name']} {a['amount']:,.0f}₺" for a in d["advances"]) + ")\n"
    c1,c2,c3 = d.get('c1_km',0),d.get('c2_km',0),d.get('c3_km',0)
    if c1+c2+c3 > 0:
        owner_text += f"🚗 Км: {COURIER_NAMES[0]}={c1}, {COURIER_NAMES[1]}={c2}, {COURIER_NAMES[2]}={c3}\n"
    if d.get("extra"):
        owner_text += f"📌 {d['extra']}\n"

    try:
        owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
        async with owner_app:
            await owner_app.bot.send_message(OWNER_ID, owner_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Owner notify error: {e}")

    return ConversationHandler.END

# ─── КУРЬЕР: ОТЧЁТ ────────────────────────────────────────────────────────────
async def courier_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.clear()
    ctx.user_data["courier"] = get_name(q.from_user.id)
    ctx.user_data["date"] = today_str()
    await q.message.reply_text(
        "🚗 *Отчёт курьера*\n\nСколько км проехал за смену?",
        parse_mode="Markdown", reply_markup=kb_num()
    )
    return S_C1_KM

# ─── АВАНС ────────────────────────────────────────────────────────────────────
async def advance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.clear()
    await q.message.reply_text(
        "💰 *Запрос аванса*\n\nНа чьё имя?",
        parse_mode="Markdown", reply_markup=kb_names(CASHIER_NAMES)
    )
    return ADV_WHO

async def adv_who(u, ctx):
    ctx.user_data["adv_who"] = u.message.text
    await msg(u, f"💵 Сколько нужно {u.message.text} (₺)?", kb_num())
    return ADV_AMT

async def adv_amt(u, ctx):
    ctx.user_data["adv_amt"] = parse_num(u.message.text)
    who = ctx.user_data["adv_who"]
    amt = ctx.user_data["adv_amt"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Отправить", callback_data="adv_send"),
        InlineKeyboardButton("❌ Отмена", callback_data="adv_cancel")
    ]])
    await u.message.reply_text(
        f"💰 *Запрос аванса:*\nКому: {who}\nСумма: *{amt:,.0f} ₺*\n\nОтправить владельцу?",
        parse_mode="Markdown", reply_markup=kb
    )
    return ADV_CONF

async def adv_conf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "adv_send":
        who = ctx.user_data["adv_who"]
        amt = ctx.user_data["adv_amt"]
        requester = get_name(q.from_user.id)
        uid = q.from_user.id
        # Отправляем владельцу через его бота
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Одобрить", callback_data=f"ok_{who}_{amt}_{uid}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{who}_{uid}")
        ]])
        try:
            owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
            async with owner_app:
                await owner_app.bot.send_message(
                    OWNER_ID,
                    f"💰 *Запрос аванса!*\nПросит: {requester}\nНа кого: {who}\nСумма: *{amt:,.0f} ₺*",
                    parse_mode="Markdown", reply_markup=kb
                )
        except Exception as e:
            logger.error(f"Advance notify error: {e}")
        await q.message.reply_text("✅ Запрос отправлен владельцу!")
    else:
        await q.message.reply_text("Отменено.")
    return ConversationHandler.END

# ─── OWNER BOT ────────────────────────────────────────────────────────────────
async def owner_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привет, *Мурад*!\n🕐 {now_str()}\n\n"
        f"Сюда приходят:\n"
        f"📊 Отчёты от кассиров\n"
        f"💰 Запросы авансов\n"
        f"🔔 Все уведомления",
        parse_mode="Markdown"
    )

async def owner_advance_response(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    action = parts[0]
    who = parts[1]
    if action == "ok":
        amt = float(parts[2])
        uid = int(parts[3])
        await q.message.edit_text(
            f"✅ *Аванс одобрен!*\n{who} — {amt:,.0f} ₺",
            parse_mode="Markdown"
        )
        try:
            await ctx.bot.send_message(uid, f"✅ Аванс для *{who}* на *{amt:,.0f} ₺* — одобрен!", parse_mode="Markdown")
        except: pass
    else:
        uid = int(parts[2])
        await q.message.edit_text(f"❌ Аванс для {who} отклонён.")
        try:
            await ctx.bot.send_message(uid, f"❌ Аванс для *{who}* — отклонён.", parse_mode="Markdown")
        except: pass

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отменено. /start — начать заново.", reply_markup=remove_kb())
    return ConversationHandler.END

async def start_from_msg(update, ctx):
    uid = update.effective_user.id
    name = get_name(uid)
    buttons = [[InlineKeyboardButton("📋 Отчёт кассира", callback_data="cashier")],
               [InlineKeyboardButton("💰 Запросить аванс", callback_data="advance")]]
    await update.message.reply_text(
        f"👋 {name}, главное меню:",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
    )

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    import asyncio

    # Staff bot
    staff_app = Application.builder().token(STAFF_BOT_TOKEN).build()

    cashier_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cashier_start, pattern="^cashier$")],
        states={
            S_SHIFT_OPENER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, s_shift_opener)],
            S_SHIFT_TYPE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, s_shift_type)],
            S_CASH_START:      [MessageHandler(filters.TEXT & ~filters.COMMAND, s_cash_start)],
            S_CASH_OFFLINE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, s_cash_offline)],
            S_CASH_COURIER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, s_cash_courier)],
            S_CARD_KUV:        [MessageHandler(filters.TEXT & ~filters.COMMAND, s_card_kuv)],
            S_CARD_ZIR:        [MessageHandler(filters.TEXT & ~filters.COMMAND, s_card_zir)],
            S_IBAN:            [MessageHandler(filters.TEXT & ~filters.COMMAND, s_iban)],
            S_YEMEK:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_yemek)],
            S_TREND:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_trend)],
            S_YEMEK_CASH:      [MessageHandler(filters.TEXT & ~filters.COMMAND, s_yemek_cash)],
            S_MIGROS:          [MessageHandler(filters.TEXT & ~filters.COMMAND, s_migros)],
            S_GETIR:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_getir)],
            S_EXPENSE_TYPE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, s_expense_type)],
            S_EXPENSE_AMOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, s_expense_amount)],
            S_EXPENSE_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, s_expense_comment)],
            S_EXPENSE_MORE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, s_expense_more)],
            S_C1_KM:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_c1_km)],
            S_C2_KM:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_c2_km)],
            S_C3_KM:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_c3_km)],
            S_ADV_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, s_adv_name)],
            S_ADV_AMOUNT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, s_adv_amount)],
            S_ADV_MORE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, s_adv_more)],
            S_EXTRA:           [MessageHandler(filters.TEXT & ~filters.COMMAND, s_extra)],
            S_CONFIRM:         [CallbackQueryHandler(confirm_report, pattern="^confirm_report$"),
                                CallbackQueryHandler(cashier_start, pattern="^cashier$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    advance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(advance_start, pattern="^advance$")],
        states={
            ADV_WHO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adv_who)],
            ADV_AMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adv_amt)],
            ADV_CONF: [CallbackQueryHandler(adv_conf, pattern="^adv_(send|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    staff_app.add_handler(CommandHandler("start", start))
    staff_app.add_handler(cashier_conv)
    staff_app.add_handler(advance_conv)

    # Owner bot
    owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
    owner_app.add_handler(CommandHandler("start", owner_start))
    owner_app.add_handler(CallbackQueryHandler(owner_advance_response, pattern="^(ok|no)_"))

    # Run both
    async def run_both():
        async with staff_app, owner_app:
            await staff_app.start()
            await owner_app.start()
            await staff_app.updater.start_polling()
            await owner_app.updater.start_polling()
            await asyncio.Event().wait()

    asyncio.run(run_both())

if __name__ == "__main__":
    main()
