import asyncio
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, ReplyKeyboardRemove

from config import BOT_TOKEN, ADMIN_ID, ALLOWED_GROUP_ID, AIRLINES, RESTAURANTS
from states import RegistrationForm, FlightForm, StatsForm, DeleteForm
from db import (
    init_db, ensure_employee, get_employee, set_registration, set_status, list_employees,
    duplicate_flight_exists, save_flight, get_flight, get_photos, get_flights,
    delete_flight, workload, date_range
)
from keyboards import (
    admin_menu, employee_menu, phone_kb, date_kb, airline_kb, operation_kb, stay_kb,
    yes_no_kb, skip_text_kb, restaurant_kb, served_mode_kb, employee_single_kb,
    employee_multi_kb, comment_kb, photo_choice_kb, photo_done_kb, confirm_kb,
    cancel_confirm_kb, stats_period_kb, flights_list_kb, flight_actions_kb,
    approval_kb, employees_manage_kb, employee_action_kb, ikb, nav_row
)
from report import build_excel

router=Router()
ADMIN_FILE=Path(".admin_id")

def current_admin_id():
    if ADMIN_ID:
        return ADMIN_ID
    if ADMIN_FILE.exists():
        try:
            return int(ADMIN_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
    return 0

def claim_admin_if_needed(uid):
    if ADMIN_ID:
        return uid==ADMIN_ID
    existing=current_admin_id()
    if existing:
        return uid==existing
    ADMIN_FILE.write_text(str(uid),encoding="utf-8")
    return True

def is_admin(uid):
    return uid==current_admin_id()

def menu_for(uid):
    return admin_menu() if is_admin(uid) else employee_menu()

def parse_date_text(text):
    for fmt in ("%d.%m.%Y","%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(),fmt).date()
        except ValueError:
            pass
    return None

def allowed_chat(message):
    if message.chat.type==ChatType.PRIVATE:
        return True
    return not ALLOWED_GROUP_ID or message.chat.id==ALLOWED_GROUP_ID

async def has_access(uid):
    if is_admin(uid):
        return True
    e=await get_employee(uid)
    return bool(e and e["status"]=="approved")

async def require_access(message):
    if not allowed_chat(message):
        await message.answer("🔒 Этот бот не настроен для работы в данной группе.")
        return False
    if await has_access(message.from_user.id):
        return True
    e=await get_employee(message.from_user.id)
    if e and e["status"]=="pending":
        await message.answer("⏳ Ваша заявка ожидает подтверждения администратора.")
    elif e and e["status"] in ("blocked","rejected"):
        await message.answer("🚫 Доступ не предоставлен. Обратитесь к администратору.")
    else:
        await message.answer("🔒 Сначала откройте бота в личном чате и отправьте /start.")
    return False

def card(data, *, saved=False, flight_id=None, photo_count=None):
    yn=lambda x:"Да" if x else "Нет"
    lines=["✅ <b>Рейс сохранён</b>" if saved else "📋 <b>Карточка рейса</b>"]
    if flight_id is not None:
        lines.append(f"🆔 ID: <b>{flight_id}</b>")
    lines += [
        f"📅 Дата: {escape(str(data.get('flight_date','')))}",
        f"✈️ Рейс: {escape(str(data.get('flight_no','')))}",
        f"🏢 Авиакомпания: {escape(str(data.get('airline','')))}",
        f"{'🛬' if data.get('operation')=='Прилёт' else '🛫'} Операция: {escape(str(data.get('operation','')))}",
        f"🗺 Маршрут: {escape(str(data.get('route','')))}",
        f"🕒 Пребывание: {data.get('stay_days',0)} дн.",
    ]
    if int(data.get("stay_days",0) or 0)>0:
        lines += [
            f"🏨 Гостиница экипажа: {escape(str(data.get('crew_hotel') or 'Не размещались'))}",
            f"🧳 Гостиница пассажиров: {escape(str(data.get('pax_hotel') or 'Не размещались'))}",
        ]
    lines += [
        f"👨‍✈️ Экипаж: {data.get('crew_count',0)}",
        f"👥 Пассажиры: {data.get('pax_count',0)}",
        f"🚐 Трансфер: {yn(data.get('transfer'))}",
    ]
    if data.get("transfer"):
        lines.append(f"🚘 Кем организован: {escape(str(data.get('transfer_provider') or '—'))}")
    lines.append(f"🍽 Питание: {yn(data.get('catering'))}")
    if data.get("catering"):
        lines.append(f"🍴 Ресторан: {escape(str(data.get('restaurant') or '—'))}")
    lines.append(f"🛍 Доп. покупки: {yn(data.get('extra_purchase'))}")
    if data.get("extra_purchase"):
        lines.append(f"📦 Что куплено: {escape(str(data.get('extra_purchase_text') or '—'))}")
    lines += [
        f"👤 Обслуживали: {escape(str(data.get('staff_display') or data.get('served_display') or '—'))}",
        f"💬 Комментарий: {escape(str(data.get('comment') or '—'))}",
    ]
    count = len(data.get("photos",[])) if photo_count is None else photo_count
    lines.append(f"📸 Фото: {count}")
    return "\n".join(lines)

async def track(state, message):
    d=await state.get_data()
    ids=list(d.get("_msg_ids",[]))
    ids.append(message.message_id)
    await state.update_data(_msg_ids=ids)

async def ask(message,state,text,reply_markup=None):
    m=await message.answer(text,reply_markup=reply_markup)
    await track(state,m)
    return m

async def track_user(state,message):
    await track(state,message)

async def cleanup(bot,chat_id,ids):
    for mid in sorted(set(ids),reverse=True):
        try:
            await bot.delete_message(chat_id,mid)
        except Exception:
            pass

async def move(state,next_state):
    d=await state.get_data()
    hist=list(d.get("_history",[]))
    cur=await state.get_state()
    if cur:
        hist.append(cur)
    await state.update_data(_history=hist)
    await state.set_state(next_state)

def text_nav(prefix=""):
    return ikb([nav_row()])

async def render_state(message,state,state_name):
    mapping={
        FlightForm.date.state:("📅 <b>Выберите дату рейса</b>",date_kb()),
        FlightForm.flight_no.state:("✈️ <b>Введите номер рейса</b>",text_nav()),
        FlightForm.airline.state:("🏢 <b>Выберите авиакомпанию</b>",airline_kb()),
        FlightForm.operation.state:("🛬🛫 <b>Прилёт или вылет?</b>",operation_kb()),
        FlightForm.route.state:("🗺 <b>Введите маршрут</b>\nНапример: <code>SKD → IST</code>",text_nav()),
        FlightForm.stay_days.state:("🕒 <b>Длительность пребывания</b>",stay_kb()),
        FlightForm.crew_hotel.state:("🏨 <b>В какой гостинице разместился экипаж?</b>",skip_text_kb("crewhotel")),
        FlightForm.pax_hotel.state:("🧳 <b>В какой гостинице разместились пассажиры?</b>",skip_text_kb("paxhotel")),
        FlightForm.crew_count.state:("👨‍✈️ <b>Сколько членов экипажа?</b>",text_nav()),
        FlightForm.pax_count.state:("👥 <b>Сколько пассажиров?</b>",text_nav()),
        FlightForm.transfer.state:("🚐 <b>Был ли организован трансфер?</b>",yes_no_kb("transfer")),
        FlightForm.transfer_provider.state:("🚘 <b>Кем был организован трансфер?</b>",text_nav()),
        FlightForm.catering.state:("🍽 <b>Было ли организовано питание?</b>",yes_no_kb("catering")),
        FlightForm.restaurant.state:("🍴 <b>Выберите ресторан</b>",restaurant_kb()),
        FlightForm.extra_purchase.state:("🛍 <b>Было ли что-то приобретено дополнительно, помимо питания?</b>",yes_no_kb("extra")),
        FlightForm.extra_purchase_text.state:("📦 <b>Укажите, что именно было приобретено или доставлено</b>",text_nav()),
        FlightForm.served_mode.state:("👤 <b>Кто обслуживал рейс?</b>",served_mode_kb()),
        FlightForm.comment.state:("💬 <b>Добавьте комментарий к рейсу</b> или пропустите.",comment_kb()),
        FlightForm.photo_choice.state:("📸 <b>Хотите прикрепить фотографии борта или важных деталей рейса?</b>",photo_choice_kb()),
    }
    text,kb=mapping.get(state_name,("◀️ Вернулись на предыдущий шаг. Введите ответ заново.",text_nav()))
    await ask(message,state,text,kb)

@router.message(CommandStart())
async def start(message:Message,state:FSMContext,bot:Bot):
    await state.clear()
    await ensure_employee(message.from_user.id,message.from_user.username,message.from_user.full_name)
    if claim_admin_if_needed(message.from_user.id):
        await set_registration(message.from_user.id,message.from_user.full_name,"")
        await set_status(message.from_user.id,"approved",message.from_user.id)
        await message.answer("✅ Вы назначены администратором.\n\nВыберите действие:",reply_markup=admin_menu())
        return
    e=await get_employee(message.from_user.id)
    if e and e["status"]=="approved":
        await message.answer("👋 Добро пожаловать. Выберите действие:",reply_markup=employee_menu())
        return
    if e and e["status"]=="pending" and e["full_name"] and e["phone"]:
        await message.answer("⏳ Ваша заявка уже отправлена администратору.")
        return
    if e and e["status"] in ("blocked","rejected"):
        await message.answer("🚫 Доступ не предоставлен. Обратитесь к администратору.")
        return
    if message.chat.type!=ChatType.PRIVATE:
        await message.answer("🔒 Регистрацию нужно пройти в личном чате с ботом.")
        return
    await state.set_state(RegistrationForm.full_name)
    await message.answer("👋 Добро пожаловать!\n\n👤 Введите ваше имя и фамилию:",reply_markup=ReplyKeyboardRemove())

@router.message(RegistrationForm.full_name)
async def reg_name(message:Message,state:FSMContext):
    name=(message.text or "").strip()
    if len(name)<3:
        await message.answer("Введите имя и фамилию полностью.")
        return
    await state.update_data(reg_name=name)
    await state.set_state(RegistrationForm.phone)
    await message.answer("📱 Отправьте номер телефона кнопкой ниже или введите вручную:",reply_markup=phone_kb())

@router.message(RegistrationForm.phone)
async def reg_phone(message:Message,state:FSMContext,bot:Bot):
    phone=message.contact.phone_number if message.contact else (message.text or "").strip()
    if len(phone)<5:
        await message.answer("Введите корректный номер телефона.")
        return
    d=await state.get_data()
    await set_registration(message.from_user.id,d["reg_name"],phone)
    await state.clear()
    await message.answer("⏳ Заявка отправлена администратору. Ожидайте подтверждения.",reply_markup=ReplyKeyboardRemove())
    e=await get_employee(message.from_user.id)
    aid=current_admin_id()
    if aid:
        uname=f"@{e['username']}" if e["username"] else "—"
        await bot.send_message(aid,
            "👤 <b>Новый сотрудник запрашивает доступ</b>\n"
            f"Имя: {escape(e['full_name'] or '')}\nТелефон: {escape(e['phone'] or '')}\n"
            f"Telegram: {escape(uname)}\nID: <code>{e['tg_id']}</code>",
            reply_markup=approval_kb(e["tg_id"]))

@router.callback_query(F.data.startswith("approve:"))
async def approve(cb:CallbackQuery,bot:Bot):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа",show_alert=True); return
    uid=int(cb.data.split(":")[1])
    await set_status(uid,"approved",cb.from_user.id)
    try:
        await bot.send_message(uid,"✅ Доступ разрешён.",reply_markup=employee_menu())
    except Exception: pass
    try: await cb.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await cb.answer("Доступ разрешён")

@router.callback_query(F.data.startswith("reject:"))
async def reject(cb:CallbackQuery,bot:Bot):
    if not is_admin(cb.from_user.id): return
    uid=int(cb.data.split(":")[1])
    await set_status(uid,"rejected",cb.from_user.id)
    try: await bot.send_message(uid,"❌ Доступ не предоставлен. Обратитесь к администратору.")
    except Exception: pass
    try: await cb.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await cb.answer("Отклонено")

@router.message(F.text=="👥 Управление сотрудниками")
async def manage(message:Message):
    if not is_admin(message.from_user.id): return
    rows=await list_employees()
    await message.answer("👥 <b>Сотрудники</b>",reply_markup=employees_manage_kb(rows))

@router.callback_query(F.data.startswith("employee:"))
async def employee_view(cb:CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid=int(cb.data.split(":")[1]); e=await get_employee(uid)
    if not e: await cb.answer("Не найден"); return
    name=e["full_name"] or e["telegram_full_name"] or e["username"] or str(uid)
    await cb.message.edit_text(
        f"👤 <b>{escape(name)}</b>\n📱 {escape(e['phone'] or '—')}\nСтатус: <b>{escape(e['status'])}</b>\nID: <code>{uid}</code>",
        reply_markup=employee_action_kb(uid,e["status"]))
    await cb.answer()

@router.callback_query(F.data.startswith("block:"))
async def block(cb:CallbackQuery,bot:Bot):
    if not is_admin(cb.from_user.id): return
    uid=int(cb.data.split(":")[1])
    await set_status(uid,"blocked",cb.from_user.id)
    try: await bot.send_message(uid,"🚫 Ваш доступ заблокирован администратором.")
    except Exception: pass
    rows=await list_employees()
    await cb.message.edit_text("👥 <b>Сотрудники</b>",reply_markup=employees_manage_kb(rows))
    await cb.answer("Заблокирован")

@router.callback_query(F.data=="employees:back")
async def employees_back(cb:CallbackQuery):
    if not is_admin(cb.from_user.id): return
    rows=await list_employees()
    await cb.message.edit_text("👥 <b>Сотрудники</b>",reply_markup=employees_manage_kb(rows))
    await cb.answer()

@router.message(F.text=="➕ Добавить рейс")
async def add_flight(message:Message,state:FSMContext):
    if not await require_access(message): return
    await state.clear()
    await state.update_data(_msg_ids=[message.message_id],_history=[],photos=[],staff_ids=[],manual_staff=[])
    await state.set_state(FlightForm.date)
    await ask(message,state,"📅 <b>Выберите дату рейса</b>",date_kb())

@router.callback_query(F.data=="nav:cancel")
async def nav_cancel(cb:CallbackQuery,state:FSMContext):
    if not await state.get_state():
        await cb.answer(); return
    await state.update_data(_return_state=await state.get_state())
    await state.set_state(FlightForm.cancel_confirm)
    await ask(cb.message,state,"⚠️ <b>Отменить добавление рейса?</b>\nВсе введённые данные будут удалены.",cancel_confirm_kb())
    await cb.answer()

@router.callback_query(FlightForm.cancel_confirm,F.data=="cancel:no")
async def cancel_no(cb:CallbackQuery,state:FSMContext):
    d=await state.get_data()
    if d.get("_return_state"): await state.set_state(d["_return_state"])
    try: await cb.message.delete()
    except Exception: pass
    await cb.answer()

@router.callback_query(FlightForm.cancel_confirm,F.data=="cancel:yes")
async def cancel_yes(cb:CallbackQuery,state:FSMContext,bot:Bot):
    d=await state.get_data(); ids=d.get("_msg_ids",[]); cid=cb.message.chat.id; uid=cb.from_user.id
    await state.clear()
    await cleanup(bot,cid,ids+[cb.message.message_id])
    await bot.send_message(cid,"❌ Заполнение отменено.",reply_markup=menu_for(uid))
    await cb.answer()

@router.callback_query(F.data=="nav:back")
async def nav_back(cb:CallbackQuery,state:FSMContext):
    d=await state.get_data(); hist=list(d.get("_history",[]))
    if not hist:
        await state.clear()
        await cb.message.answer("↩️ Главное меню.",reply_markup=menu_for(cb.from_user.id))
        await cb.answer(); return
    prev=hist.pop()
    await state.update_data(_history=hist)
    await state.set_state(prev)
    await render_state(cb.message,state,prev)
    await cb.answer()

@router.callback_query(FlightForm.date,F.data.startswith("date:"))
async def date_step(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]; today=date.today()
    if v=="custom":
        await move(state,FlightForm.custom_date)
        await ask(cb.message,state,"🗓 <b>Введите дату в формате ДД.ММ.ГГГГ</b>",text_nav())
    else:
        selected={"yesterday":today-timedelta(days=1),"today":today,"tomorrow":today+timedelta(days=1)}[v]
        await state.update_data(flight_date=selected.isoformat())
        await move(state,FlightForm.flight_no)
        await ask(cb.message,state,"✈️ <b>Введите номер рейса</b>",text_nav())
    await cb.answer()

@router.message(FlightForm.custom_date)
async def custom_date(message:Message,state:FSMContext):
    await track_user(state,message)
    d=parse_date_text(message.text or "")
    if not d:
        await ask(message,state,"⚠️ Введите дату, например 28.09.2026",text_nav()); return
    await state.update_data(flight_date=d.isoformat()); await move(state,FlightForm.flight_no)
    await ask(message,state,"✈️ <b>Введите номер рейса</b>",text_nav())

@router.message(FlightForm.flight_no)
async def flight_no(message:Message,state:FSMContext):
    await track_user(state,message)
    no=(message.text or "").strip().upper()
    if len(no)<2:
        await ask(message,state,"⚠️ Введите корректный номер рейса.",text_nav()); return
    d=await state.get_data()
    if await duplicate_flight_exists(d["flight_date"],no):
        await ask(message,state,"⚠️ Такой рейс уже есть на эту дату. Проверьте, не дублируете ли запись.",text_nav())
    await state.update_data(flight_no=no); await move(state,FlightForm.airline)
    await ask(message,state,"🏢 <b>Выберите авиакомпанию</b>",airline_kb())

@router.callback_query(FlightForm.airline,F.data.startswith("air:"))
async def airline(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]
    if v=="custom":
        await move(state,FlightForm.custom_airline)
        await ask(cb.message,state,"✍️ <b>Введите название авиакомпании</b>",text_nav())
    else:
        await state.update_data(airline=AIRLINES[int(v)]); await move(state,FlightForm.operation)
        await ask(cb.message,state,"🛬🛫 <b>Прилёт или вылет?</b>",operation_kb())
    await cb.answer()

@router.message(FlightForm.custom_airline)
async def custom_airline(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(airline=(message.text or "").strip()); await move(state,FlightForm.operation)
    await ask(message,state,"🛬🛫 <b>Прилёт или вылет?</b>",operation_kb())

@router.callback_query(FlightForm.operation,F.data.startswith("op:"))
async def operation(cb:CallbackQuery,state:FSMContext):
    await state.update_data(operation="Прилёт" if cb.data.endswith("arrival") else "Вылет")
    await move(state,FlightForm.route)
    await ask(cb.message,state,"🗺 <b>Введите маршрут</b>\nНапример: <code>SKD → IST</code>",text_nav())
    await cb.answer()

@router.message(FlightForm.route)
async def route(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(route=(message.text or "").strip()); await move(state,FlightForm.stay_days)
    await ask(message,state,"🕒 <b>Длительность пребывания</b>",stay_kb())

@router.callback_query(FlightForm.stay_days,F.data.startswith("stay:"))
async def stay(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]
    if v=="custom":
        await move(state,FlightForm.custom_stay_days)
        await ask(cb.message,state,"📅 <b>Укажите количество дней пребывания</b>",text_nav())
    else:
        days=int(v); await state.update_data(stay_days=days)
        if days>0:
            await move(state,FlightForm.crew_hotel)
            await ask(cb.message,state,"🏨 <b>В какой гостинице разместился экипаж?</b>",skip_text_kb("crewhotel"))
        else:
            await state.update_data(crew_hotel=None,pax_hotel=None); await move(state,FlightForm.crew_count)
            await ask(cb.message,state,"👨‍✈️ <b>Сколько членов экипажа?</b>",text_nav())
    await cb.answer()

@router.message(FlightForm.custom_stay_days)
async def custom_stay(message:Message,state:FSMContext):
    await track_user(state,message)
    try:
        days=int((message.text or "").strip())
        if not 0<=days<=365: raise ValueError
    except ValueError:
        await ask(message,state,"⚠️ Введите целое число от 0 до 365.",text_nav()); return
    await state.update_data(stay_days=days)
    if days>0:
        await move(state,FlightForm.crew_hotel)
        await ask(message,state,"🏨 <b>В какой гостинице разместился экипаж?</b>",skip_text_kb("crewhotel"))
    else:
        await state.update_data(crew_hotel=None,pax_hotel=None); await move(state,FlightForm.crew_count)
        await ask(message,state,"👨‍✈️ <b>Сколько членов экипажа?</b>",text_nav())

@router.callback_query(FlightForm.crew_hotel,F.data=="crewhotel:skip")
async def crew_hotel_skip(cb:CallbackQuery,state:FSMContext):
    await state.update_data(crew_hotel=None); await move(state,FlightForm.pax_hotel)
    await ask(cb.message,state,"🧳 <b>В какой гостинице разместились пассажиры?</b>",skip_text_kb("paxhotel"))
    await cb.answer()

@router.message(FlightForm.crew_hotel)
async def crew_hotel(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(crew_hotel=(message.text or "").strip()); await move(state,FlightForm.pax_hotel)
    await ask(message,state,"🧳 <b>В какой гостинице разместились пассажиры?</b>",skip_text_kb("paxhotel"))

@router.callback_query(FlightForm.pax_hotel,F.data=="paxhotel:skip")
async def pax_hotel_skip(cb:CallbackQuery,state:FSMContext):
    await state.update_data(pax_hotel=None); await move(state,FlightForm.crew_count)
    await ask(cb.message,state,"👨‍✈️ <b>Сколько членов экипажа?</b>",text_nav()); await cb.answer()

@router.message(FlightForm.pax_hotel)
async def pax_hotel(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(pax_hotel=(message.text or "").strip()); await move(state,FlightForm.crew_count)
    await ask(message,state,"👨‍✈️ <b>Сколько членов экипажа?</b>",text_nav())

async def read_nonneg(message,state,key):
    await track_user(state,message)
    try:
        v=int((message.text or "").strip())
        if v<0: raise ValueError
    except ValueError:
        await ask(message,state,"⚠️ Введите целое число 0 или больше.",text_nav()); return None
    await state.update_data(**{key:v}); return v

@router.message(FlightForm.crew_count)
async def crew_count(message:Message,state:FSMContext):
    if await read_nonneg(message,state,"crew_count") is None: return
    await move(state,FlightForm.pax_count)
    await ask(message,state,"👥 <b>Сколько пассажиров?</b>",text_nav())

@router.message(FlightForm.pax_count)
async def pax_count(message:Message,state:FSMContext):
    if await read_nonneg(message,state,"pax_count") is None: return
    await move(state,FlightForm.transfer)
    await ask(message,state,"🚐 <b>Был ли организован трансфер?</b>",yes_no_kb("transfer"))

@router.callback_query(FlightForm.transfer,F.data.startswith("transfer:"))
async def transfer(cb:CallbackQuery,state:FSMContext):
    yes=cb.data.endswith("yes"); await state.update_data(transfer=yes)
    if yes:
        await move(state,FlightForm.transfer_provider)
        await ask(cb.message,state,"🚘 <b>Кем был организован трансфер?</b>",text_nav())
    else:
        await state.update_data(transfer_provider=None); await move(state,FlightForm.catering)
        await ask(cb.message,state,"🍽 <b>Было ли организовано питание?</b>",yes_no_kb("catering"))
    await cb.answer()

@router.message(FlightForm.transfer_provider)
async def transfer_provider(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(transfer_provider=(message.text or "").strip()); await move(state,FlightForm.catering)
    await ask(message,state,"🍽 <b>Было ли организовано питание?</b>",yes_no_kb("catering"))

@router.callback_query(FlightForm.catering,F.data.startswith("catering:"))
async def catering(cb:CallbackQuery,state:FSMContext):
    yes=cb.data.endswith("yes"); await state.update_data(catering=yes)
    if yes:
        await move(state,FlightForm.restaurant)
        await ask(cb.message,state,"🍴 <b>Выберите ресторан</b>",restaurant_kb())
    else:
        await state.update_data(restaurant=None); await move(state,FlightForm.extra_purchase)
        await ask(cb.message,state,"🛍 <b>Было ли что-то приобретено дополнительно, помимо питания?</b>",yes_no_kb("extra"))
    await cb.answer()

@router.callback_query(FlightForm.restaurant,F.data.startswith("rest:"))
async def restaurant(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]
    if v=="custom":
        await move(state,FlightForm.custom_restaurant)
        await ask(cb.message,state,"✍️ <b>Введите название ресторана</b>",text_nav())
    else:
        await state.update_data(restaurant=RESTAURANTS[int(v)]); await move(state,FlightForm.extra_purchase)
        await ask(cb.message,state,"🛍 <b>Было ли что-то приобретено дополнительно, помимо питания?</b>",yes_no_kb("extra"))
    await cb.answer()

@router.message(FlightForm.custom_restaurant)
async def custom_restaurant(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(restaurant=(message.text or "").strip()); await move(state,FlightForm.extra_purchase)
    await ask(message,state,"🛍 <b>Было ли что-то приобретено дополнительно, помимо питания?</b>",yes_no_kb("extra"))


@router.callback_query(FlightForm.extra_purchase,F.data.startswith("extra:"))
async def extra_purchase(cb:CallbackQuery,state:FSMContext):
    yes=cb.data.endswith("yes"); await state.update_data(extra_purchase=yes)
    if yes:
        await move(state,FlightForm.extra_purchase_text)
        await ask(cb.message,state,"📦 <b>Укажите, что именно было приобретено или доставлено</b>",text_nav())
    else:
        await state.update_data(extra_purchase_text=None); await move(state,FlightForm.served_mode)
        await ask(cb.message,state,"👤 <b>Кто обслуживал рейс?</b>",served_mode_kb())
    await cb.answer()

@router.message(FlightForm.extra_purchase_text)
async def extra_purchase_text(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(extra_purchase_text=(message.text or "").strip())
    await move(state,FlightForm.served_mode)
    await ask(message,state,"👤 <b>Кто обслуживал рейс?</b>",served_mode_kb())

async def staff_display(state,user_id,user_name):
    d=await state.get_data()
    ids=set(int(x) for x in d.get("staff_ids",[]))
    manual=list(d.get("manual_staff",[]))
    rows=await list_employees(status="approved")
    byid={int(r["tg_id"]):(r["full_name"] or r["telegram_full_name"] or r["username"] or str(r["tg_id"])) for r in rows}
    names=[]
    for tid in ids:
        names.append(byid.get(tid,user_name if tid==user_id else str(tid)))
    names+=manual
    return ", ".join(dict.fromkeys(names))

@router.callback_query(FlightForm.served_mode,F.data.startswith("served:"))
async def served_mode(cb:CallbackQuery,state:FSMContext):
    mode=cb.data.split(":")[1]; uid=cb.from_user.id
    if mode=="self":
        await state.update_data(staff_ids=[uid],manual_staff=[])
        await state.update_data(staff_display=await staff_display(state,uid,cb.from_user.full_name))
        await move(state,FlightForm.comment)
        await ask(cb.message,state,"💬 <b>Добавьте комментарий к рейсу</b> или пропустите.",comment_kb())
    elif mode=="other":
        rows=await list_employees(status="approved",exclude_tg_id=uid)
        await move(state,FlightForm.served_other)
        await ask(cb.message,state,"👤 <b>Выберите сотрудника</b>",employee_single_kb(rows))
    else:
        rows=await list_employees(status="approved",exclude_tg_id=uid)
        await state.update_data(staff_ids=[uid],manual_staff=[])
        await move(state,FlightForm.served_together)
        await ask(cb.message,state,"👥 <b>Выберите сотрудников</b>\nВы уже добавлены.",employee_multi_kb(rows,{uid}))
    await cb.answer()

@router.callback_query(FlightForm.served_other,F.data.startswith("empone:"))
async def served_other(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]
    if v=="manual":
        await move(state,FlightForm.served_other_manual)
        await ask(cb.message,state,"✍️ <b>Введите имя сотрудника вручную</b>",text_nav())
    else:
        await state.update_data(staff_ids=[int(v)],manual_staff=[])
        await state.update_data(staff_display=await staff_display(state,cb.from_user.id,cb.from_user.full_name))
        await move(state,FlightForm.comment)
        await ask(cb.message,state,"💬 <b>Добавьте комментарий к рейсу</b> или пропустите.",comment_kb())
    await cb.answer()

@router.message(FlightForm.served_other_manual)
async def served_other_manual(message:Message,state:FSMContext):
    await track_user(state,message)
    name=(message.text or "").strip()
    await state.update_data(staff_ids=[],manual_staff=[name],staff_display=name)
    await move(state,FlightForm.comment)
    await ask(message,state,"💬 <b>Добавьте комментарий к рейсу</b> или пропустите.",comment_kb())

@router.callback_query(FlightForm.served_together,F.data.startswith("empmulti:"))
async def served_together(cb:CallbackQuery,state:FSMContext):
    v=cb.data.split(":")[1]; d=await state.get_data()
    selected=set(int(x) for x in d.get("staff_ids",[cb.from_user.id]))
    if v=="done":
        await state.update_data(staff_display=await staff_display(state,cb.from_user.id,cb.from_user.full_name))
        await move(state,FlightForm.comment)
        await ask(cb.message,state,"💬 <b>Добавьте комментарий к рейсу</b> или пропустите.",comment_kb())
    elif v=="manual":
        await move(state,FlightForm.served_together_manual)
        await ask(cb.message,state,"✍️ <b>Введите имя сотрудника, которого нужно добавить вручную</b>",text_nav())
    else:
        tid=int(v)
        if tid in selected: selected.remove(tid)
        else: selected.add(tid)
        selected.add(cb.from_user.id)
        await state.update_data(staff_ids=list(selected))
        rows=await list_employees(status="approved",exclude_tg_id=cb.from_user.id)
        await cb.message.edit_reply_markup(reply_markup=employee_multi_kb(rows,selected))
    await cb.answer()

@router.message(FlightForm.served_together_manual)
async def served_together_manual(message:Message,state:FSMContext):
    await track_user(state,message)
    d=await state.get_data()
    manual=list(d.get("manual_staff",[])); manual.append((message.text or "").strip())
    await state.update_data(manual_staff=manual)
    rows=await list_employees(status="approved",exclude_tg_id=message.from_user.id)
    selected=set(int(x) for x in d.get("staff_ids",[message.from_user.id]))
    await state.set_state(FlightForm.served_together)
    await ask(message,state,"✅ Имя добавлено. Можно выбрать ещё сотрудников или нажать «Готово».",
              employee_multi_kb(rows,selected))

@router.callback_query(FlightForm.comment,F.data=="comment:skip")
async def comment_skip(cb:CallbackQuery,state:FSMContext):
    await state.update_data(comment=None); await move(state,FlightForm.photo_choice)
    await ask(cb.message,state,"📸 <b>Хотите прикрепить фотографии борта или важных деталей рейса?</b>",photo_choice_kb())
    await cb.answer()

@router.message(FlightForm.comment)
async def comment_text(message:Message,state:FSMContext):
    await track_user(state,message)
    await state.update_data(comment=(message.text or "").strip()); await move(state,FlightForm.photo_choice)
    await ask(message,state,"📸 <b>Хотите прикрепить фотографии борта или важных деталей рейса?</b>",photo_choice_kb())

@router.callback_query(FlightForm.photo_choice,F.data.startswith("photo:"))
async def photo_choice(cb:CallbackQuery,state:FSMContext):
    if cb.data.endswith("skip"):
        d=await state.get_data(); await state.set_state(FlightForm.confirm)
        await ask(cb.message,state,card(d),confirm_kb())
    else:
        await move(state,FlightForm.photos)
        await ask(cb.message,state,
                  "📎 Отправьте одну или несколько фотографий борта, салона, багажа или других важных деталей.\n"
                  "Когда закончите, нажмите <b>✅ Готово</b>.",
                  photo_done_kb())
    await cb.answer()

@router.message(FlightForm.photos,F.photo)
async def photo_receive(message:Message,state:FSMContext):
    await track_user(state,message)
    d=await state.get_data(); photos=list(d.get("photos",[]))
    ph=message.photo[-1]
    photos.append({"file_id":ph.file_id,"file_unique_id":ph.file_unique_id})
    await state.update_data(photos=photos)
    await ask(message,state,f"📸 Фото добавлено. Всего: <b>{len(photos)}</b>",photo_done_kb())

@router.callback_query(FlightForm.photos,F.data=="photo:done")
async def photo_done(cb:CallbackQuery,state:FSMContext):
    d=await state.get_data(); await state.set_state(FlightForm.confirm)
    await ask(cb.message,state,card(d),confirm_kb()); await cb.answer()

@router.callback_query(FlightForm.confirm,F.data=="confirm:edit")
async def confirm_edit(cb:CallbackQuery,state:FSMContext):
    await state.update_data(_history=[])
    await state.set_state(FlightForm.date)
    await ask(cb.message,state,"✏️ Начнём исправление с первого пункта.\n\n📅 <b>Выберите дату рейса</b>",date_kb())
    await cb.answer()

@router.callback_query(FlightForm.confirm,F.data=="confirm:save")
async def confirm_save(cb:CallbackQuery,state:FSMContext,bot:Bot):
    d=await state.get_data()
    fid=await save_flight(
        d,cb.from_user.id,d.get("staff_ids",[]),d.get("manual_staff",[]),d.get("photos",[]),
        cb.message.chat.id,str(cb.message.chat.type)
    )
    final=card(d,saved=True,flight_id=fid)
    ids=d.get("_msg_ids",[]); cid=cb.message.chat.id; uid=cb.from_user.id
    await state.clear()
    await cleanup(bot,cid,ids+[cb.message.message_id])
    await bot.send_message(cid,final,reply_markup=menu_for(uid))
    await cb.answer("Сохранено")

@router.message(F.text=="📊 Статистика")
async def stats_menu(message:Message,state:FSMContext):
    if not await require_access(message): return
    await state.update_data(report_mode="stats")
    await message.answer("📊 <b>Выберите период</b>",reply_markup=stats_period_kb("stats"))

@router.message(F.text=="📥 Скачать отчёт в Excel")
async def excel_menu(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(report_mode="excel")
    await message.answer("📥 <b>Выберите период для Excel</b>",reply_markup=stats_period_kb("excel"))

async def show_stats(message,start_date,end_date,user_id=None):
    if user_id is None:
        user_id = message.from_user.id
    personal=not is_admin(user_id)
    flights=await get_flights(start_date,end_date,user_id if personal else None)
    lines=[
        "📊 <b>Статистика</b>",
        f"📅 {start_date} — {end_date}",
        f"✈️ Всего рейсов: <b>{len(flights)}</b>",
        f"🛬 Прилётов: {sum(1 for f in flights if f['operation']=='Прилёт')}",
        f"🛫 Вылетов: {sum(1 for f in flights if f['operation']=='Вылет')}",
    ]
    if is_admin(message.from_user.id):
        w=await workload(start_date,end_date)
        lines+=["","👥 <b>По сотрудникам</b>"]
        for r in w:
            icon="✅" if int(r["flights_count"]) else "—"
            lines.append(f"{icon} {escape(r['name'])}: {r['flights_count']}")
    await message.answer("\n".join(lines))
    if flights:
        await message.answer("📋 <b>Рейсы за период</b>\nНажмите на рейс для подробного просмотра.",
                             reply_markup=flights_list_kb(flights))

async def send_excel(message,start_date,end_date):
    out=Path("reports")/f"flights_{start_date}_{end_date}.xlsx"
    path,count=await build_excel(start_date,end_date,str(out))
    await message.answer_document(FSInputFile(path),caption=f"📥 Excel: {start_date} — {end_date}\n✈️ Рейсов: {count}")

@router.callback_query(F.data.startswith("stats:"))
async def stats_choice(cb:CallbackQuery,state:FSMContext):
    kind=cb.data.split(":")[1]
    if kind=="custom":
        await state.update_data(report_mode="stats")
        await state.set_state(StatsForm.start_date)
        await cb.message.answer("📆 Введите начальную дату в формате ДД.ММ.ГГГГ")
    else:
        s,e=date_range(kind); await show_stats(cb.message,s,e,cb.from_user.id)
    await cb.answer()

@router.callback_query(F.data.startswith("excel:"))
async def excel_choice(cb:CallbackQuery,state:FSMContext):
    if not is_admin(cb.from_user.id): return
    kind=cb.data.split(":")[1]
    if kind=="custom":
        await state.update_data(report_mode="excel")
        await state.set_state(StatsForm.start_date)
        await cb.message.answer("📆 Введите начальную дату в формате ДД.ММ.ГГГГ")
    else:
        s,e=date_range(kind); await send_excel(cb.message,s,e)
    await cb.answer()

@router.message(StatsForm.start_date)
async def period_start(message:Message,state:FSMContext):
    d=parse_date_text(message.text or "")
    if not d:
        await message.answer("⚠️ Введите дату в формате ДД.ММ.ГГГГ"); return
    await state.update_data(period_start=d.isoformat())
    await state.set_state(StatsForm.end_date)
    await message.answer("📆 Введите конечную дату периода")

@router.message(StatsForm.end_date)
async def period_end(message:Message,state:FSMContext):
    d=parse_date_text(message.text or "")
    if not d:
        await message.answer("⚠️ Введите дату в формате ДД.ММ.ГГГГ"); return
    data=await state.get_data(); s=data["period_start"]; e=d.isoformat(); mode=data.get("report_mode","stats")
    if e<s:
        await message.answer("⚠️ Конечная дата не может быть раньше начальной."); return
    await state.clear()
    if mode=="excel" and is_admin(message.from_user.id):
        await send_excel(message,s,e)
    else:
        await show_stats(message,s,e)

@router.callback_query(F.data.startswith("flightview:"))
async def flight_view(cb:CallbackQuery,bot:Bot):
    fid=int(cb.data.split(":")[1]); fl=await get_flight(fid)
    if not fl:
        await cb.answer("Рейс не найден",show_alert=True); return
    photos=await get_photos(fid); data=dict(fl)
    await cb.message.answer(card(data,flight_id=fid,photo_count=len(photos)),
                            reply_markup=flight_actions_kb(fid,is_admin(cb.from_user.id)))
    for p in photos:
        try: await bot.send_photo(cb.message.chat.id,p["file_id"])
        except Exception: pass
    await cb.answer()

@router.callback_query(F.data.startswith("flightdel:"))
async def flight_del(cb:CallbackQuery):
    if not is_admin(cb.from_user.id): return
    fid=int(cb.data.split(":")[1]); ok=await delete_flight(fid)
    await cb.message.edit_text("✅ Рейс удалён." if ok else "⚠️ Рейс не найден.")
    await cb.answer()

@router.message(F.text=="🗑 Удалить рейс")
async def delete_menu(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(DeleteForm.flight_id)
    await message.answer("🗑 Введите ID рейса, который нужно удалить.")

@router.message(DeleteForm.flight_id)
async def delete_by_id(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    try: fid=int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Введите числовой ID."); return
    ok=await delete_flight(fid); await state.clear()
    await message.answer("✅ Рейс удалён." if ok else "⚠️ Рейс с таким ID не найден.",reply_markup=admin_menu())

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Проверьте файл .env")
    await init_db()
    bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp=Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
