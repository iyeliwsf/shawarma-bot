import os, json, logging, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STAFF_BOT_TOKEN = "8969505121:AAFYXK-DRUV7RcWUgBuG2YKNt5c5SDulDac"
OWNER_BOT_TOKEN = "8958494523:AAEo8lnjuPk27qVKi4TNcPNaFK5oOYQMdd4"
OWNER_ID        = 1067385281
TZ              = ZoneInfo("Europe/Istanbul")
KM_RATE         = 5

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

# States
(
    ST_OPENER, ST_SHIFT, ST_CASH_START,
    ST_IN1, ST_IN2, ST_IN3, ST_IN4, ST_IN5,
    ST_IN6, ST_IN7, ST_IN8, ST_IN9, ST_IN10,
    ST_EXP_TYPE, ST_EXP_AMT, ST_EXP_CMT, ST_EXP_MORE,
    ST_C1, ST_C2, ST_C3,
    ST_ADV_NAME, ST_ADV_AMT, ST_ADV_MORE,
    ST_EXTRA, ST_CONFIRM,
) = range(25)

ADV_WHO, ADV_AMT, ADV_CONF = range(100, 103)

def kb(*rows_extra, back=True):
    rows = list(rows_extra)
    if back: rows.append(["◀️ Назад"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)

def kb_num(): return kb(["0"])
def kb_skip(): return kb(["Пропустить"])
def kb_more(): return kb(["✅ Добавить ещё"], ["➡️ Продолжить"])
def kb_names(names): return kb(*[[n] for n in names])
def kb_expense_type(): return kb(["💳 Карта", "💵 Наличные"])

def get_name(uid):
    if uid in CASHIERS: return CASHIERS[uid]
    if uid in COURIERS: return COURIERS[uid]
    return "Неизвестный"

def now_str(): return datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
def today_str(): return datetime.now(TZ).strftime("%d.%m.%Y")
def parse_num(t):
    try: return float(t.replace(",",".").strip())
    except: return 0.0

def is_back(t): return t == "◀️ Назад"
def is_skip(t): return t in ("Пропустить", "0")

async def rmsg(u, text, keyboard=None):
    await u.message.reply_text(text, reply_markup=keyboard or ReplyKeyboardRemove(), parse_mode="Markdown")

async def notify_owner(ctx, text, reply_markup=None):
    try:
        owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
        async with owner_app:
            await owner_app.bot.send_message(OWNER_ID, text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Owner notify error: {e}")

# /start staff
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    btns = []
    if uid in CASHIERS or uid == OWNER_ID:
        btns.append([InlineKeyboardButton("📋 Отчёт кассира", callback_data="cashier")])
    if uid in COURIERS or uid == OWNER_ID:
        btns.append([InlineKeyboardButton("🚗 Отчёт курьера", callback_data="courier")])
    btns.append([InlineKeyboardButton("💰 Запросить аванс", callback_data="advance")])
    await update.message.reply_text(
        f"👋 Привет, *{get_name(uid)}*!\n🕐 {now_str()}\n\nЧто делаем?",
        reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown"
    )

# Cashier conv
async def cashier_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data.clear()
    ctx.user_data.update({"date": today_str(), "cashier": get_name(q.from_user.id),
                          "uid": q.from_user.id, "expenses": [], "advances": []})
    await q.message.reply_text("📋 *Отчёт за смену*\n\n👤 Кто открыл кассу?",
                                reply_markup=kb_names(CASHIER_NAMES), parse_mode="Markdown")
    return ST_OPENER

async def st_opener(u, ctx):
    if is_back(u.message.text): await start(u, ctx); return ConversationHandler.END
    ctx.user_data["opener"] = u.message.text
    await rmsg(u, "🕐 Напиши смену:\n(например: *12:00-18:00* или *Ильхам до 21:00, Сальма до 00:00*)", kb_skip())
    return ST_SHIFT

async def st_shift(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "👤 Кто открыл кассу?", kb_names(CASHIER_NAMES)); return ST_OPENER
    ctx.user_data["shift"] = u.message.text if not is_skip(u.message.text) else ""
    await rmsg(u, "💵 *Остаток в кассе на начало смены (₺):*", kb_num())
    return ST_CASH_START

async def st_cash_start(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "🕐 Смена:", kb_skip()); return ST_SHIFT
    ctx.user_data["cash_start"] = parse_num(u.message.text)
    await rmsg(u, "*1️⃣ Наличные offline (₺):*", kb_num())
    return ST_IN1

async def st_in1(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "💵 Остаток в кассе на начало:", kb_num()); return ST_CASH_START
    ctx.user_data["cash_offline"] = parse_num(u.message.text)
    await rmsg(u, "*2️⃣ Наличные курьер (₺):*", kb_num()); return ST_IN2

async def st_in2(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*1️⃣ Наличные offline:*", kb_num()); return ST_IN1
    ctx.user_data["cash_courier"] = parse_num(u.message.text)
    await rmsg(u, "*3️⃣ Карта Kuvveyt (₺):*", kb_num()); return ST_IN3

async def st_in3(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*2️⃣ Наличные курьер:*", kb_num()); return ST_IN2
    ctx.user_data["card_kuvveyt"] = parse_num(u.message.text)
    await rmsg(u, "*4️⃣ Карта Ziraat (₺):*", kb_num()); return ST_IN4

async def st_in4(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*3️⃣ Карта Kuvveyt:*", kb_num()); return ST_IN3
    ctx.user_data["card_ziraat"] = parse_num(u.message.text)
    await rmsg(u, "*5️⃣ IBAN (₺):*", kb_num()); return ST_IN5

async def st_in5(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*4️⃣ Карта Ziraat:*", kb_num()); return ST_IN4
    ctx.user_data["iban"] = parse_num(u.message.text)
    await rmsg(u, "*6️⃣ Yemeksepeti (₺):*", kb_num()); return ST_IN6

async def st_in6(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*5️⃣ IBAN:*", kb_num()); return ST_IN5
    ctx.user_data["yemeksepeti"] = parse_num(u.message.text)
    await rmsg(u, "*7️⃣ Trendyol (₺):*", kb_num()); return ST_IN7

async def st_in7(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*6️⃣ Yemeksepeti:*", kb_num()); return ST_IN6
    ctx.user_data["trendyol"] = parse_num(u.message.text)
    await rmsg(u, "*8️⃣ Yemeksepeti наличка (₺):*", kb_num()); return ST_IN8

async def st_in8(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*7️⃣ Trendyol:*", kb_num()); return ST_IN7
    ctx.user_data["yemek_cash"] = parse_num(u.message.text)
    await rmsg(u, "*9️⃣ Migros (₺):*", kb_num()); return ST_IN9

async def st_in9(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*8️⃣ Yemeksepeti наличка:*", kb_num()); return ST_IN8
    ctx.user_data["migros"] = parse_num(u.message.text)
    await rmsg(u, "*🔟 Getir Yemek (₺):*", kb_num()); return ST_IN10

async def st_in10(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*9️⃣ Migros:*", kb_num()); return ST_IN9
    ctx.user_data["getir"] = parse_num(u.message.text)
    n = len(ctx.user_data["expenses"]) + 1
    await rmsg(u, f"💸 *Расход #{n}* — тип оплаты:\n(0 если расходов не было)", kb_expense_type())
    return ST_EXP_TYPE

async def st_exp_type(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "*🔟 Getir Yemek:*", kb_num()); return ST_IN10
    if is_skip(u.message.text):
        await rmsg(u, f"🚗 *{COURIER_NAMES[0]}* — км за смену:\n(0 если не работал)", kb_num())
        return ST_C1
    ctx.user_data["_exp_type"] = u.message.text
    await rmsg(u, "💰 Сумма расхода (₺):", kb_num())
    return ST_EXP_AMT

async def st_exp_amt(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "💸 Тип оплаты:", kb_expense_type()); return ST_EXP_TYPE
    ctx.user_data["_exp_amt"] = parse_num(u.message.text)
    await rmsg(u, "📝 Комментарий к расходу\n(что купили/оплатили):")
    return ST_EXP_CMT

async def st_exp_cmt(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "💰 Сумма расхода:", kb_num()); return ST_EXP_AMT
    ctx.user_data["expenses"].append({
        "type": ctx.user_data.get("_exp_type",""),
        "amount": ctx.user_data.get("_exp_amt",0),
        "comment": u.message.text
    })
    await rmsg(u, f"Расход добавлен ✅\nДобавить ещё?", kb_more())
    return ST_EXP_MORE

async def st_exp_more(u, ctx):
    if u.message.text == "✅ Добавить ещё":
        n = len(ctx.user_data["expenses"]) + 1
        await rmsg(u, f"💸 *Расход #{n}* — тип:", kb_expense_type())
        return ST_EXP_TYPE
    await rmsg(u, f"🚗 *{COURIER_NAMES[0]}* — км за смену:\n(0 если не работал)", kb_num())
    return ST_C1

async def st_c1(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "Добавить ещё расход?", kb_more()); return ST_EXP_MORE
    km = parse_num(u.message.text)
    ctx.user_data["c1_km"] = km; ctx.user_data["c1_sum"] = km * KM_RATE
    await rmsg(u, f"🚗 *{COURIER_NAMES[1]}* — км:\n(0 если не работал)", kb_num()); return ST_C2

async def st_c2(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, f"🚗 *{COURIER_NAMES[0]}* — км:", kb_num()); return ST_C1
    km = parse_num(u.message.text)
    ctx.user_data["c2_km"] = km; ctx.user_data["c2_sum"] = km * KM_RATE
    await rmsg(u, f"🚗 *{COURIER_NAMES[2]}* — км:\n(0 если не работал)", kb_num()); return ST_C3

async def st_c3(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, f"🚗 *{COURIER_NAMES[1]}* — км:", kb_num()); return ST_C2
    km = parse_num(u.message.text)
    ctx.user_data["c3_km"] = km; ctx.user_data["c3_sum"] = km * KM_RATE
    await rmsg(u, f"💰 *Аванс* — кто брал?\n(или Пропустить)", kb_names(CASHIER_NAMES + ["Пропустить"]))
    return ST_ADV_NAME

async def st_adv_name(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, f"🚗 *{COURIER_NAMES[2]}* — км:", kb_num()); return ST_C3
    if is_skip(u.message.text):
        await rmsg(u, "📌 Доп. заметки:\n(или Пропустить)", kb_skip()); return ST_EXTRA
    ctx.user_data["_adv_name"] = u.message.text
    await rmsg(u, f"💵 Сколько взял {u.message.text} (₺)?", kb_num()); return ST_ADV_AMT

async def st_adv_amt(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "💰 Кто брал аванс?", kb_names(CASHIER_NAMES + ["Пропустить"])); return ST_ADV_NAME
    ctx.user_data["advances"].append({
        "name": ctx.user_data.get("_adv_name",""),
        "amount": parse_num(u.message.text)
    })
    await rmsg(u, "Аванс добавлен ✅\nДобавить ещё?", kb_more()); return ST_ADV_MORE

async def st_adv_more(u, ctx):
    if u.message.text == "✅ Добавить ещё":
        await rmsg(u, "💰 Кто следующий?", kb_names(CASHIER_NAMES + ["Пропустить"])); return ST_ADV_NAME
    await rmsg(u, "📌 Доп. заметки:\n(или Пропустить)", kb_skip()); return ST_EXTRA

async def st_extra(u, ctx):
    if is_back(u.message.text):
        await rmsg(u, "Добавить ещё аванс?", kb_more()); return ST_ADV_MORE
    ctx.user_data["extra"] = "" if is_skip(u.message.text) else u.message.text
    return await show_confirm(u, ctx)

async def show_confirm(u, ctx):
    d = ctx.user_data
    inc_keys = ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"]
    total_inc = sum(d.get(k,0) for k in inc_keys)
    total_exp = sum(e["amount"] for e in d.get("expenses",[]))
    total_adv = sum(a["amount"] for a in d.get("advances",[]))
    cash_start = d.get("cash_start",0)
    cash_in = d.get("cash_offline",0) + d.get("cash_courier",0) + d.get("yemek_cash",0)
    cash_out = sum(e["amount"] for e in d.get("expenses",[]) if "Наличные" in e.get("type",""))
    cash_end = cash_start + cash_in - cash_out - total_adv

    txt = (f"✅ *Проверь отчёт — {d['date']}*\n"
           f"👤 {d.get('opener','?')} | {d.get('shift','')}\n"
           f"💵 Касса начало: `{cash_start:,.0f}` ₺\n\n"
           f"*Поступления:*\n"
           f"  Нал.offline: `{d.get('cash_offline',0):,.0f}` ₺\n"
           f"  Нал.курьер: `{d.get('cash_courier',0):,.0f}` ₺\n"
           f"  Kuvveyt: `{d.get('card_kuvveyt',0):,.0f}` ₺\n"
           f"  Ziraat: `{d.get('card_ziraat',0):,.0f}` ₺\n"
           f"  IBAN: `{d.get('iban',0):,.0f}` ₺\n"
           f"  Yemeksepeti: `{d.get('yemeksepeti',0):,.0f}` ₺\n"
           f"  Trendyol: `{d.get('trendyol',0):,.0f}` ₺\n"
           f"  Yemek нал.: `{d.get('yemek_cash',0):,.0f}` ₺\n"
           f"  Migros: `{d.get('migros',0):,.0f}` ₺\n"
           f"  Getir: `{d.get('getir',0):,.0f}` ₺\n"
           f"  ━━━━━━━━━\n"
           f"  *ИТОГО: `{total_inc:,.0f}` ₺*\n\n")
    if d.get("expenses"):
        txt += "*Расходы:*\n"
        for e in d["expenses"]:
            txt += f"  {e['type']}: `{e['amount']:,.0f}` ₺ — {e['comment']}\n"
        txt += f"  Итого: `{total_exp:,.0f}` ₺\n\n"
    c1,c2,c3 = d.get('c1_km',0), d.get('c2_km',0), d.get('c3_km',0)
    if c1+c2+c3 > 0:
        txt += f"*Курьеры:*\n"
        if c1: txt += f"  {COURIER_NAMES[0]}: {c1} км → `{d.get('c1_sum',0):,.0f}` ₺\n"
        if c2: txt += f"  {COURIER_NAMES[1]}: {c2} км → `{d.get('c2_sum',0):,.0f}` ₺\n"
        if c3: txt += f"  {COURIER_NAMES[2]}: {c3} км → `{d.get('c3_sum',0):,.0f}` ₺\n"
        txt += "\n"
    if d.get("advances"):
        txt += "*Авансы:*\n"
        for a in d["advances"]:
            txt += f"  {a['name']}: `{a['amount']:,.0f}` ₺\n"
        txt += f"  Итого: `{total_adv:,.0f}` ₺\n\n"
    txt += f"💰 *Касса конец смены: `{cash_end:,.0f}` ₺*\n"
    if d.get("extra"): txt += f"\n📌 {d['extra']}\n"
    txt += "\nВсё верно?"
    kb_confirm = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Отправить", callback_data="do_confirm"),
        InlineKeyboardButton("🔄 Заново", callback_data="cashier")
    ]])
    await u.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb_confirm)
    return ST_CONFIRM

async def do_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data != "do_confirm": return ConversationHandler.END
    d = ctx.user_data
    inc_keys = ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"]
    total_inc = sum(d.get(k,0) for k in inc_keys)
    total_adv = sum(a["amount"] for a in d.get("advances",[]))
    cash_start = d.get("cash_start",0)
    cash_in = d.get("cash_offline",0)+d.get("cash_courier",0)+d.get("yemek_cash",0)
    cash_out = sum(e["amount"] for e in d.get("expenses",[]) if "Наличные" in e.get("type",""))
    cash_end = cash_start + cash_in - cash_out - total_adv

    await q.message.reply_text(
        f"✅ *Отчёт отправлен!*\nВыручка: *{total_inc:,.0f} ₺*\nКасса: *{cash_end:,.0f} ₺*",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

    owner_txt = (f"📊 *Новый отчёт!*\n"
                 f"📅 {d['date']} | {d.get('opener','')} | {d.get('shift','')}\n"
                 f"💰 Выручка: *{total_inc:,.0f} ₺*\n"
                 f"💵 Касса: {cash_start:,.0f} → *{cash_end:,.0f} ₺*\n")
    if d.get("expenses"):
        owner_txt += "💸 Расходы:\n"
        for e in d["expenses"]:
            owner_txt += f"  {e['type']}: {e['amount']:,.0f}₺ — {e['comment']}\n"
    if d.get("advances"):
        owner_txt += "💰 Авансы: " + ", ".join(f"{a['name']} {a['amount']:,.0f}₺" for a in d["advances"]) + "\n"
    c1,c2,c3 = d.get('c1_km',0),d.get('c2_km',0),d.get('c3_km',0)
    if c1+c2+c3>0:
        owner_txt += f"🚗 Курьеры: {COURIER_NAMES[0]}={c1}км, {COURIER_NAMES[1]}={c2}км, {COURIER_NAMES[2]}={c3}км\n"
    if d.get("extra"): owner_txt += f"📌 {d['extra']}\n"

    await notify_owner(ctx, owner_txt)
    return ConversationHandler.END

# Advance
async def advance_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data.clear()
    await q.message.reply_text("💰 *Запрос аванса*\n\nНа чьё имя?",
                                reply_markup=kb_names(CASHIER_NAMES), parse_mode="Markdown")
    return ADV_WHO

async def adv_who(u, ctx):
    ctx.user_data["adv_who"] = u.message.text
    await rmsg(u, f"💵 Сколько нужно {u.message.text} (₺)?", kb_num()); return ADV_AMT

async def adv_amt(u, ctx):
    ctx.user_data["adv_amt"] = parse_num(u.message.text)
    who, amt = ctx.user_data["adv_who"], ctx.user_data["adv_amt"]
    await u.message.reply_text(
        f"💰 *Запрос:* {who} — *{amt:,.0f} ₺*\nОтправить владельцу?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Отправить", callback_data="adv_send"),
            InlineKeyboardButton("❌ Отмена", callback_data="adv_cancel")
        ]])
    ); return ADV_CONF

async def adv_conf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "adv_send":
        who, amt = ctx.user_data["adv_who"], ctx.user_data["adv_amt"]
        requester = get_name(q.from_user.id)
        uid = q.from_user.id
        kb_owner = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Одобрить", callback_data=f"ok_{who}_{int(amt)}_{uid}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{who}_{uid}")
        ]])
        await notify_owner(ctx, f"💰 *Запрос аванса!*\nПросит: {requester}\nКому: {who}\nСумма: *{amt:,.0f} ₺*", kb_owner)
        await q.message.reply_text("✅ Запрос отправлен владельцу! Ожидай.", reply_markup=ReplyKeyboardRemove())
    else:
        await q.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отменено. /start — начать заново.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Owner bot
async def owner_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 *Мурад, привет!*\n🕐 {now_str()}\n\n"
        "Сюда приходят все отчёты и запросы авансов.\n"
        "Ничего делать не нужно — просто читай и одобряй кнопками.",
        parse_mode="Markdown"
    )

async def owner_adv_response(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    action = parts[0]
    who = parts[1]
    if action == "ok":
        amt = int(parts[2]); uid = int(parts[3])
        await q.message.edit_text(f"✅ *Аванс одобрен!*\n{who} — {amt:,} ₺", parse_mode="Markdown")
        try: await ctx.bot.send_message(uid, f"✅ Аванс для *{who}* на *{amt:,} ₺* — *одобрен!*", parse_mode="Markdown")
        except: pass
    else:
        uid = int(parts[2])
        await q.message.edit_text(f"❌ Аванс для {who} — отклонён.")
        try: await ctx.bot.send_message(uid, f"❌ Аванс для *{who}* — отклонён владельцем.", parse_mode="Markdown")
        except: pass

def make_cashier_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cashier_cb, pattern="^cashier$")],
        states={
            ST_OPENER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, st_opener)],
            ST_SHIFT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, st_shift)],
            ST_CASH_START:[MessageHandler(filters.TEXT & ~filters.COMMAND, st_cash_start)],
            ST_IN1:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in1)],
            ST_IN2:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in2)],
            ST_IN3:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in3)],
            ST_IN4:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in4)],
            ST_IN5:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in5)],
            ST_IN6:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in6)],
            ST_IN7:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in7)],
            ST_IN8:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in8)],
            ST_IN9:      [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in9)],
            ST_IN10:     [MessageHandler(filters.TEXT & ~filters.COMMAND, st_in10)],
            ST_EXP_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_exp_type)],
            ST_EXP_AMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, st_exp_amt)],
            ST_EXP_CMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, st_exp_cmt)],
            ST_EXP_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_exp_more)],
            ST_C1:       [MessageHandler(filters.TEXT & ~filters.COMMAND, st_c1)],
            ST_C2:       [MessageHandler(filters.TEXT & ~filters.COMMAND, st_c2)],
            ST_C3:       [MessageHandler(filters.TEXT & ~filters.COMMAND, st_c3)],
            ST_ADV_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_adv_name)],
            ST_ADV_AMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, st_adv_amt)],
            ST_ADV_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_adv_more)],
            ST_EXTRA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, st_extra)],
            ST_CONFIRM:  [CallbackQueryHandler(do_confirm, pattern="^do_confirm$"),
                          CallbackQueryHandler(cashier_cb, pattern="^cashier$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

def make_advance_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(advance_cb, pattern="^advance$")],
        states={
            ADV_WHO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adv_who)],
            ADV_AMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adv_amt)],
            ADV_CONF: [CallbackQueryHandler(adv_conf, pattern="^adv_(send|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

def main():
    staff_app = Application.builder().token(STAFF_BOT_TOKEN).build()
    staff_app.add_handler(CommandHandler("start", start))
    staff_app.add_handler(make_cashier_conv())
    staff_app.add_handler(make_advance_conv())

    owner_app = Application.builder().token(OWNER_BOT_TOKEN).build()
    owner_app.add_handler(CommandHandler("start", owner_start))
    owner_app.add_handler(CallbackQueryHandler(owner_adv_response, pattern="^(ok|no)_"))

    async def run():
        async with staff_app, owner_app:
            await staff_app.start()
            await owner_app.start()
            await staff_app.updater.start_polling()
            await owner_app.updater.start_polling()
            await asyncio.Event().wait()

    asyncio.run(run())

if __name__ == "__main__":
    main()
