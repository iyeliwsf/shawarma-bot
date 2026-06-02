import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8969505121:AAFYXK-DRUV7RcWUgBuG2YKNt5c5SDulDac"
OWNER_ID  = 1067385281
SHEET_ID  = "1kz1sZSwZDSPQc33jkcQxNIdXmElhcjjBlDng_q0BflA"
TZ        = ZoneInfo("Europe/Istanbul")

CASHIERS = {
    OWNER_ID: "Мурад (тест)",
    # 111111111: "Ильхам",
    # 222222222: "Сальма",
    # 333333333: "Милена",
}
COURIERS = {
    # 444444444: "Энгин",
    # 555555555: "Самет",
}
COURIER_NAMES = ["Энгин", "Самет", "Третий"]

def get_sheet(sheet_name):
    import json
    creds_json = os.environ.get("GOOGLE_CREDS")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"])
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=sheet_name, rows=500, cols=35)

def ensure_headers():
    ws = get_sheet("БОТ_Касса")
    if not ws.cell(1,1).value:
        ws.append_row(["Дата","Кассир","Нал.offline","Нал.курьер","Kuvveyt","Ziraat","IBAN","Yemeksepeti","Trendyol","Yemek нал.","Migros","Getir","ИТОГО","Расход карта","Карта комм.","Расход нал.","Нал. комм.",f"{COURIER_NAMES[0]} часы",f"{COURIER_NAMES[0]} сумма",f"{COURIER_NAMES[1]} часы",f"{COURIER_NAMES[1]} сумма",f"{COURIER_NAMES[2]} часы",f"{COURIER_NAMES[2]} сумма","Курьеры комм.","Аванс кто","Аванс сумма","Заметки"])
    ws2 = get_sheet("БОТ_Авансы")
    if not ws2.cell(1,1).value:
        ws2.append_row(["Дата","Кто просит","На кого","Сумма","Статус"])

def save_cashier(d):
    ensure_headers()
    ws = get_sheet("БОТ_Касса")
    total = sum(d.get(k,0) for k in ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"])
    ws.append_row([d.get("date"),d.get("cashier"),d.get("cash_offline",0),d.get("cash_courier",0),d.get("card_kuvveyt",0),d.get("card_ziraat",0),d.get("iban",0),d.get("yemeksepeti",0),d.get("trendyol",0),d.get("yemek_cash",0),d.get("migros",0),d.get("getir",0),total,d.get("card_expense",0),d.get("card_comment",""),d.get("cash_expense",0),d.get("cash_comment",""),d.get("c1_hours",""),d.get("c1_sum",0),d.get("c2_hours",""),d.get("c2_sum",0),d.get("c3_hours",""),d.get("c3_sum",0),d.get("courier_comment",""),d.get("adv_name",""),d.get("adv_sum",0),d.get("extra","")],value_input_option="USER_ENTERED")
    return total

def save_advance(date, requester, who, amount):
    ensure_headers()
    get_sheet("БОТ_Авансы").append_row([date,requester,who,amount,"Одобрено"],value_input_option="USER_ENTERED")

def get_name(uid):
    if uid in CASHIERS: return CASHIERS[uid]
    if uid in COURIERS: return COURIERS[uid]
    return "Неизвестный"

def is_cashier(uid): return uid in CASHIERS or uid == OWNER_ID
def num_kb(): return ReplyKeyboardMarkup([["0"]], resize_keyboard=True, one_time_keyboard=True)
def skip_kb(): return ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True, one_time_keyboard=True)
def parse_num(t):
    try: return float(t.replace(",",".").strip())
    except: return 0.0

async def msg(u, text, kb=None):
    await u.message.reply_text(text, reply_markup=kb or ReplyKeyboardRemove(), parse_mode="Markdown")

(C_CASH_OFFLINE,C_CASH_COURIER,C_CARD_KUV,C_CARD_ZIR,C_IBAN,C_YEMEK,C_TREND,C_YEMEK_CASH,C_MIGROS,C_GETIR,C_CARD_EXP,C_CARD_COMM,C_CASH_EXP,C_CASH_COMM,C_C1_HOURS,C_C1_SUM,C_C2_HOURS,C_C2_SUM,C_C3_HOURS,C_C3_SUM,C_COURIER_COMM,C_ADV_NAME,C_ADV_SUM,C_EXTRA,C_CONFIRM)=range(25)
ADV_WHO,ADV_AMT,ADV_CONFIRM=range(100,103)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    buttons = []
    if is_cashier(uid): buttons.append([InlineKeyboardButton("📋 Отчёт кассира",callback_data="cashier")])
    buttons.append([InlineKeyboardButton("💰 Запросить аванс",callback_data="advance")])
    if uid == OWNER_ID: buttons.append([InlineKeyboardButton("📊 Сводка за сегодня",callback_data="summary")])
    await update.message.reply_text(f"👋 Привет, *{get_name(uid)}*!\n🕐 {now}\n\nЧто делаем?",reply_markup=InlineKeyboardMarkup(buttons),parse_mode="Markdown")

async def cashier_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    ctx.user_data.clear()
    ctx.user_data["cashier"]=get_name(q.from_user.id)
    ctx.user_data["date"]=datetime.now(TZ).strftime("%d.%m.%Y")
    await q.message.reply_text("📋 *Отчёт за смену*\n\n*1️⃣ Наличные offline (₺):*",parse_mode="Markdown",reply_markup=num_kb())
    return C_CASH_OFFLINE

async def c_cash_offline(u,ctx):
    ctx.user_data["cash_offline"]=parse_num(u.message.text)
    await msg(u,"*2️⃣ Наличные курьер (₺):*",num_kb()); return C_CASH_COURIER
async def c_cash_courier(u,ctx):
    ctx.user_data["cash_courier"]=parse_num(u.message.text)
    await msg(u,"*3️⃣ Карта Kuvveyt (₺):*",num_kb()); return C_CARD_KUV
async def c_card_kuv(u,ctx):
    ctx.user_data["card_kuvveyt"]=parse_num(u.message.text)
    await msg(u,"*4️⃣ Карта Ziraat (₺):*",num_kb()); return C_CARD_ZIR
async def c_card_zir(u,ctx):
    ctx.user_data["card_ziraat"]=parse_num(u.message.text)
    await msg(u,"*5️⃣ IBAN (₺):*",num_kb()); return C_IBAN
async def c_iban(u,ctx):
    ctx.user_data["iban"]=parse_num(u.message.text)
    await msg(u,"*6️⃣ Yemeksepeti (₺):*",num_kb()); return C_YEMEK
async def c_yemek(u,ctx):
    ctx.user_data["yemeksepeti"]=parse_num(u.message.text)
    await msg(u,"*7️⃣ Trendyol (₺):*",num_kb()); return C_TREND
async def c_trend(u,ctx):
    ctx.user_data["trendyol"]=parse_num(u.message.text)
    await msg(u,"*8️⃣ Yemeksepeti наличка (₺):*",num_kb()); return C_YEMEK_CASH
async def c_yemek_cash(u,ctx):
    ctx.user_data["yemek_cash"]=parse_num(u.message.text)
    await msg(u,"*9️⃣ Migros (₺):*",num_kb()); return C_MIGROS
async def c_migros(u,ctx):
    ctx.user_data["migros"]=parse_num(u.message.text)
    await msg(u,"*🔟 Getir Yemek (₺):*",num_kb()); return C_GETIR
async def c_getir(u,ctx):
    ctx.user_data["getir"]=parse_num(u.message.text)
    await msg(u,"*💳 Расход картой (₺):*\n(0 если не было)",num_kb()); return C_CARD_EXP
async def c_card_exp(u,ctx):
    ctx.user_data["card_expense"]=parse_num(u.message.text)
    if ctx.user_data["card_expense"]>0:
        await msg(u,"📝 Комментарий к расходу картой:"); return C_CARD_COMM
    ctx.user_data["card_comment"]=""
    await msg(u,"*💵 Расход наличных из кассы (₺):*\n(0 если не было)",num_kb()); return C_CASH_EXP
async def c_card_comm(u,ctx):
    ctx.user_data["card_comment"]=u.message.text
    await msg(u,"*💵 Расход наличных из кассы (₺):*",num_kb()); return C_CASH_EXP
async def c_cash_exp(u,ctx):
    ctx.user_data["cash_expense"]=parse_num(u.message.text)
    if ctx.user_data["cash_expense"]>0:
        await msg(u,"📝 Комментарий к расходу наличных:"); return C_CASH_COMM
    ctx.user_data["cash_comment"]=""
    await msg(u,f"*🚗 {COURIER_NAMES[0]} — часы:*\n(12:00-00:00 или Пропустить)",skip_kb()); return C_C1_HOURS
async def c_cash_comm(u,ctx):
    ctx.user_data["cash_comment"]=u.message.text
    await msg(u,f"*🚗 {COURIER_NAMES[0]} — часы:*",skip_kb()); return C_C1_HOURS
async def c_c1_hours(u,ctx):
    t=u.message.text; ctx.user_data["c1_hours"]="" if t=="Пропустить" else t
    await msg(u,f"*💵 {COURIER_NAMES[0]} — сумма (₺):*",num_kb()); return C_C1_SUM
async def c_c1_sum(u,ctx):
    ctx.user_data["c1_sum"]=parse_num(u.message.text)
    await msg(u,f"*🚗 {COURIER_NAMES[1]} — часы:*",skip_kb()); return C_C2_HOURS
async def c_c2_hours(u,ctx):
    t=u.message.text; ctx.user_data["c2_hours"]="" if t=="Пропустить" else t
    await msg(u,f"*💵 {COURIER_NAMES[1]} — сумма (₺):*",num_kb()); return C_C2_SUM
async def c_c2_sum(u,ctx):
    ctx.user_data["c2_sum"]=parse_num(u.message.text)
    await msg(u,f"*🚗 {COURIER_NAMES[2]} — часы:*",skip_kb()); return C_C3_HOURS
async def c_c3_hours(u,ctx):
    t=u.message.text; ctx.user_data["c3_hours"]="" if t=="Пропустить" else t
    await msg(u,f"*💵 {COURIER_NAMES[2]} — сумма (₺):*",num_kb()); return C_C3_SUM
async def c_c3_sum(u,ctx):
    ctx.user_data["c3_sum"]=parse_num(u.message.text)
    await msg(u,"📝 Расходы курьеров (бензин и т.д.):\n(или Пропустить)",skip_kb()); return C_COURIER_COMM
async def c_courier_comm(u,ctx):
    t=u.message.text; ctx.user_data["courier_comment"]="" if t=="Пропустить" else t
    await msg(u,"💰 Аванс: кто брал сегодня?\n(имя или Пропустить)",skip_kb()); return C_ADV_NAME
async def c_adv_name(u,ctx):
    t=u.message.text
    if t=="Пропустить":
        ctx.user_data["adv_name"]=""; ctx.user_data["adv_sum"]=0
        await msg(u,"📌 Доп. заметки:\n(или Пропустить)",skip_kb()); return C_EXTRA
    ctx.user_data["adv_name"]=t
    await msg(u,f"💵 Сколько взял {t} (₺)?",num_kb()); return C_ADV_SUM
async def c_adv_sum(u,ctx):
    ctx.user_data["adv_sum"]=parse_num(u.message.text)
    await msg(u,"📌 Доп. заметки:\n(или Пропустить)",skip_kb()); return C_EXTRA
async def c_extra(u,ctx):
    t=u.message.text; ctx.user_data["extra"]="" if t=="Пропустить" else t
    return await show_confirm(u,ctx)

async def show_confirm(u,ctx):
    d=ctx.user_data
    total=sum(d.get(k,0) for k in ["cash_offline","cash_courier","card_kuvveyt","card_ziraat","iban","yemeksepeti","trendyol","yemek_cash","migros","getir"])
    text=(f"✅ *Проверь отчёт — {d['date']}*\nКассир: {d['cashier']}\n\n"
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
          f"  ━━━━━━━━━━━━━\n"
          f"  *ИТОГО: `{total:,.0f}` ₺*\n\n"
          f"*Расходы:*\n"
          f"  Карта: `{d.get('card_expense',0):,.0f}` ₺ {d.get('card_comment','')}\n"
          f"  Нал.: `{d.get('cash_expense',0):,.0f}` ₺ {d.get('cash_comment','')}\n\n"
          f"*Курьеры:*\n"
          f"  {COURIER_NAMES[0]}: {d.get('c1_hours','-')} → `{d.get('c1_sum',0):,.0f}` ₺\n"
          f"  {COURIER_NAMES[1]}: {d.get('c2_hours','-')} → `{d.get('c2_sum',0):,.0f}` ₺\n"
          f"  {COURIER_NAMES[2]}: {d.get('c3_hours','-')} → `{d.get('c3_sum',0):,.0f}` ₺\n")
    if d.get("adv_name"): text+=f"\n*Аванс:* {d['adv_name']} — `{d.get('adv_sum',0):,.0f}` ₺\n"
    if d.get("extra"): text+=f"*Заметки:* {d['extra']}\n"
    text+="\nВсё верно?"
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Отправить",callback_data="confirm_yes"),InlineKeyboardButton("🔄 Заново",callback_data="cashier")]])
    await u.message.reply_text(text,parse_mode="Markdown",reply_markup=kb)
    return C_CONFIRM

async def confirm_yes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    try:
        total=save_cashier(ctx.user_data)
        d=ctx.user_data
        await q.message.reply_text(f"✅ *Отчёт сохранён!*\nВыручка: *{total:,.0f} ₺*",parse_mode="Markdown")
        if q.from_user.id!=OWNER_ID:
            await ctx.bot.send_message(OWNER_ID,f"📊 *Новый отчёт!*\nКассир: {d['cashier']}\nДата: {d['date']}\nВыручка: *{total:,.0f} ₺*\nРасход карта: {d.get('card_expense',0):,.0f} ₺\nРасход нал.: {d.get('cash_expense',0):,.0f} ₺",parse_mode="Markdown")
    except Exception as e:
        await q.message.reply_text(f"❌ Ошибка: {e}")
    return ConversationHandler.END

async def advance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    ctx.user_data.clear()
    await q.message.reply_text("💰 *Запрос аванса*\n\nНа чьё имя?",parse_mode="Markdown")
    return ADV_WHO

async def adv_who(u,ctx):
    ctx.user_data["adv_who"]=u.message.text
    await msg(u,f"💵 Сколько нужно {u.message.text} (₺)?",num_kb()); return ADV_AMT

async def adv_amt(u,ctx):
    ctx.user_data["adv_amt"]=parse_num(u.message.text)
    who=ctx.user_data["adv_who"]; amt=ctx.user_data["adv_amt"]
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Отправить запрос",callback_data="adv_confirm"),InlineKeyboardButton("❌ Отмена",callback_data="adv_cancel")]])
    await u.message.reply_text(f"💰 *Запрос:*\nКому: {who}\nСумма: *{amt:,.0f} ₺*\n\nОтправить владельцу?",parse_mode="Markdown",reply_markup=kb)
    return ADV_CONFIRM

async def adv_confirm_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="adv_confirm":
        who=ctx.user_data["adv_who"]; amt=ctx.user_data["adv_amt"]
        requester=get_name(q.from_user.id)
        date=datetime.now(TZ).strftime("%d.%m.%Y")
        uid=q.from_user.id
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Одобрить",callback_data=f"adv_ok_{who}_{amt}_{date}_{uid}"),InlineKeyboardButton("❌ Отклонить",callback_data=f"adv_no_{who}_{uid}")]])
        await ctx.bot.send_message(OWNER_ID,f"💰 *Запрос аванса!*\nПросит: {requester}\nНа кого: {who}\nСумма: *{amt:,.0f} ₺*",parse_mode="Markdown",reply_markup=kb)
        await q.message.reply_text("✅ Запрос отправлен! Ожидай ответа.")
    else:
        await q.message.reply_text("Отменено.")
    return ConversationHandler.END

async def adv_owner_response(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    parts=q.data.split("_")
    if parts[1]=="ok":
        who=parts[2]; amt=float(parts[3]); date=parts[4]; uid=int(parts[5])
        save_advance(date,get_name(q.from_user.id),who,amt)
        await q.message.edit_text(f"✅ *Аванс одобрен!*\n{who} — {amt:,.0f} ₺\nСохранено в таблицу.",parse_mode="Markdown")
        try: await ctx.bot.send_message(uid,f"✅ Аванс для *{who}* на *{amt:,.0f} ₺* — одобрен!",parse_mode="Markdown")
        except: pass
    else:
        who=parts[2]; uid=int(parts[3])
        await q.message.edit_text(f"❌ Аванс для {who} отклонён.")
        try: await ctx.bot.send_message(uid,f"❌ Аванс для *{who}* — отклонён владельцем.",parse_mode="Markdown")
        except: pass

async def summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    try:
        ws=get_sheet("БОТ_Касса")
        rows=ws.get_all_values()
        today=datetime.now(TZ).strftime("%d.%m.%Y")
        today_rows=[r for r in rows[1:] if r and r[0]==today]
        if not today_rows:
            await q.message.reply_text(f"📊 За {today} отчётов ещё нет."); return
        total_rev=sum(float(r[12]) for r in today_rows if len(r)>12 and r[12])
        total_crd=sum(float(r[13]) for r in today_rows if len(r)>13 and r[13])
        total_csh=sum(float(r[15]) for r in today_rows if len(r)>15 and r[15])
        await q.message.reply_text(
            f"📊 *Сводка за {today}*\n\n"
            f"Отчётов: {len(today_rows)}\n"
            f"Выручка грязная: *{total_rev:,.0f} ₺*\n"
            f"Расход карта: {total_crd:,.0f} ₺\n"
            f"Расход нал.: {total_csh:,.0f} ₺\n"
            f"Примерно чистая: *{total_rev-total_crd-total_csh:,.0f} ₺*",
            parse_mode="Markdown")
    except Exception as e:
        await q.message.reply_text(f"Ошибка: {e}")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отменено. /start — начать заново.")
    return ConversationHandler.END

def main():
    app=Application.builder().token(BOT_TOKEN).build()
    cashier_conv=ConversationHandler(
        entry_points=[CallbackQueryHandler(cashier_start,pattern="^cashier$")],
        states={
            C_CASH_OFFLINE:[MessageHandler(filters.TEXT&~filters.COMMAND,c_cash_offline)],
            C_CASH_COURIER:[MessageHandler(filters.TEXT&~filters.COMMAND,c_cash_courier)],
            C_CARD_KUV:[MessageHandler(filters.TEXT&~filters.COMMAND,c_card_kuv)],
            C_CARD_ZIR:[MessageHandler(filters.TEXT&~filters.COMMAND,c_card_zir)],
            C_IBAN:[MessageHandler(filters.TEXT&~filters.COMMAND,c_iban)],
            C_YEMEK:[MessageHandler(filters.TEXT&~filters.COMMAND,c_yemek)],
            C_TREND:[MessageHandler(filters.TEXT&~filters.COMMAND,c_trend)],
            C_YEMEK_CASH:[MessageHandler(filters.TEXT&~filters.COMMAND,c_yemek_cash)],
            C_MIGROS:[MessageHandler(filters.TEXT&~filters.COMMAND,c_migros)],
            C_GETIR:[MessageHandler(filters.TEXT&~filters.COMMAND,c_getir)],
            C_CARD_EXP:[MessageHandler(filters.TEXT&~filters.COMMAND,c_card_exp)],
            C_CARD_COMM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_card_comm)],
            C_CASH_EXP:[MessageHandler(filters.TEXT&~filters.COMMAND,c_cash_exp)],
            C_CASH_COMM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_cash_comm)],
            C_C1_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c1_hours)],
            C_C1_SUM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c1_sum)],
            C_C2_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c2_hours)],
            C_C2_SUM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c2_sum)],
            C_C3_HOURS:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c3_hours)],
            C_C3_SUM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_c3_sum)],
            C_COURIER_COMM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_courier_comm)],
            C_ADV_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,c_adv_name)],
            C_ADV_SUM:[MessageHandler(filters.TEXT&~filters.COMMAND,c_adv_sum)],
            C_EXTRA:[MessageHandler(filters.TEXT&~filters.COMMAND,c_extra)],
            C_CONFIRM:[CallbackQueryHandler(confirm_yes,pattern="^confirm_yes$"),CallbackQueryHandler(cashier_start,pattern="^cashier$")],
        },
        fallbacks=[CommandHandler("cancel",cancel)],
        allow_reentry=True,
    )
    advance_conv=ConversationHandler(
        entry_points=[CallbackQueryHandler(advance_start,pattern="^advance$")],
        states={
            ADV_WHO:[MessageHandler(filters.TEXT&~filters.COMMAND,adv_who)],
            ADV_AMT:[MessageHandler(filters.TEXT&~filters.COMMAND,adv_amt)],
            ADV_CONFIRM:[CallbackQueryHandler(adv_confirm_handler,pattern="^adv_(confirm|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel",cancel)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start",start))
    app.add_handler(cashier_conv)
    app.add_handler(advance_conv)
    app.add_handler(CallbackQueryHandler(summary,pattern="^summary$"))
    app.add_handler(CallbackQueryHandler(adv_owner_response,pattern="^adv_(ok|no)_"))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__=="__main__":
    main()
