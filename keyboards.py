from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import AIRLINES, RESTAURANTS

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить рейс"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📥 Скачать отчёт в Excel")],
            [KeyboardButton(text="🗑 Удалить рейс"), KeyboardButton(text="👥 Управление сотрудниками")],
        ],
        resize_keyboard=True
    )

def employee_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить рейс")],
            [KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True
    )

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def nav_row():
    return [
        InlineKeyboardButton(text="◀️ Назад", callback_data="nav:back"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="nav:cancel"),
    ]

def date_kb():
    return ikb([
        [InlineKeyboardButton(text="🌙 Вчера", callback_data="date:yesterday")],
        [InlineKeyboardButton(text="☀️ Сегодня", callback_data="date:today")],
        [InlineKeyboardButton(text="✈️ Завтра", callback_data="date:tomorrow")],
        [InlineKeyboardButton(text="🗓 Выбрать другую дату", callback_data="date:custom")],
        nav_row(),
    ])

def airline_kb():
    rows = [[InlineKeyboardButton(text=f"✈️ {x}", callback_data=f"air:{i}")] for i, x in enumerate(AIRLINES)]
    rows += [
        [InlineKeyboardButton(text="➕ Другая авиакомпания", callback_data="air:custom")],
        nav_row()
    ]
    return ikb(rows)

def operation_kb():
    return ikb([
        [InlineKeyboardButton(text="🛬 Прилёт", callback_data="op:arrival"),
         InlineKeyboardButton(text="🛫 Вылет", callback_data="op:departure")],
        nav_row()
    ])

def stay_kb():
    return ikb([
        [InlineKeyboardButton(text="✈️ 0 дней", callback_data="stay:0")],
        [InlineKeyboardButton(text="🌙 1 день", callback_data="stay:1")],
        [InlineKeyboardButton(text="🏨 2 дня", callback_data="stay:2")],
        [InlineKeyboardButton(text="➕ Другое", callback_data="stay:custom")],
        nav_row()
    ])

def yes_no_kb(prefix):
    return ikb([
        [InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:no")],
        nav_row()
    ])

def skip_text_kb(prefix, label="⏭ Не размещались"):
    return ikb([
        [InlineKeyboardButton(text=label, callback_data=f"{prefix}:skip")],
        nav_row()
    ])

def restaurant_kb():
    rows = [[InlineKeyboardButton(text=f"🍽 {x}", callback_data=f"rest:{i}")] for i, x in enumerate(RESTAURANTS)]
    rows += [
        [InlineKeyboardButton(text="➕ Другой ресторан", callback_data="rest:custom")],
        nav_row()
    ]
    return ikb(rows)

def served_mode_kb():
    return ikb([
        [InlineKeyboardButton(text="🙋 Я", callback_data="served:self")],
        [InlineKeyboardButton(text="👤 Другой сотрудник", callback_data="served:other")],
        [InlineKeyboardButton(text="👥 Вместе", callback_data="served:together")],
        nav_row()
    ])

def employee_single_kb(rows):
    kb = InlineKeyboardBuilder()
    for r in rows:
        label = r["full_name"] or r["telegram_full_name"] or r["username"] or str(r["tg_id"])
        kb.button(text=f"👤 {label}", callback_data=f"empone:{r['tg_id']}")
    kb.button(text="➕ Добавить вручную", callback_data="empone:manual")
    kb.button(text="◀️ Назад", callback_data="nav:back")
    kb.button(text="❌ Отменить", callback_data="nav:cancel")
    kb.adjust(1)
    return kb.as_markup()

def employee_multi_kb(rows, selected):
    kb = InlineKeyboardBuilder()
    for r in rows:
        tid = int(r["tg_id"])
        label = r["full_name"] or r["telegram_full_name"] or r["username"] or str(tid)
        mark = "✅ " if tid in selected else ""
        kb.button(text=f"{mark}👤 {label}", callback_data=f"empmulti:{tid}")
    kb.button(text="➕ Добавить вручную", callback_data="empmulti:manual")
    kb.button(text="✅ Готово", callback_data="empmulti:done")
    kb.button(text="◀️ Назад", callback_data="nav:back")
    kb.button(text="❌ Отменить", callback_data="nav:cancel")
    kb.adjust(1)
    return kb.as_markup()

def comment_kb():
    return ikb([
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="comment:skip")],
        nav_row()
    ])

def photo_choice_kb():
    return ikb([
        [InlineKeyboardButton(text="📷 Добавить фото", callback_data="photo:add")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="photo:skip")],
        nav_row()
    ])

def photo_done_kb():
    return ikb([
        [InlineKeyboardButton(text="✅ Готово", callback_data="photo:done")],
        nav_row()
    ])

def confirm_kb():
    return ikb([
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="confirm:save")],
        [InlineKeyboardButton(text="✏️ Исправить", callback_data="confirm:edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="nav:cancel")],
    ])

def cancel_confirm_kb():
    return ikb([
        [InlineKeyboardButton(text="✅ Да, отменить", callback_data="cancel:yes")],
        [InlineKeyboardButton(text="↩️ Продолжить заполнение", callback_data="cancel:no")],
    ])

def stats_period_kb(prefix="stats"):
    return ikb([
        [InlineKeyboardButton(text="🌙 Вчера", callback_data=f"{prefix}:yesterday"),
         InlineKeyboardButton(text="☀️ Сегодня", callback_data=f"{prefix}:today")],
        [InlineKeyboardButton(text="📅 Эта неделя", callback_data=f"{prefix}:week"),
         InlineKeyboardButton(text="🗓 Этот месяц", callback_data=f"{prefix}:month")],
        [InlineKeyboardButton(text="📆 Выбрать период", callback_data=f"{prefix}:custom")],
    ])

def flights_list_kb(flights):
    rows=[]
    for f in flights[:40]:
        rows.append([InlineKeyboardButton(
            text=f"✈️ {f['airline']} · {f['flight_no']} · {f['flight_date']}",
            callback_data=f"flightview:{f['id']}"
        )])
    return ikb(rows)

def flight_actions_kb(fid, admin):
    rows=[]
    if admin:
        rows.append([InlineKeyboardButton(text="🗑 Удалить рейс", callback_data=f"flightdel:{fid}")])
    return ikb(rows) if rows else None

def approval_kb(tg_id):
    return ikb([
        [InlineKeyboardButton(text="✅ Добавить сотрудника", callback_data=f"approve:{tg_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{tg_id}")],
    ])

def employees_manage_kb(rows):
    kb=InlineKeyboardBuilder()
    for r in rows:
        label=r["full_name"] or r["telegram_full_name"] or r["username"] or str(r["tg_id"])
        icon={"approved":"✅","pending":"⏳","blocked":"🚫","rejected":"❌"}.get(r["status"],"•")
        kb.button(text=f"{icon} {label}", callback_data=f"employee:{r['tg_id']}")
    kb.adjust(1)
    return kb.as_markup()

def employee_action_kb(tg_id,status):
    rows=[]
    if status=="approved":
        rows.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"block:{tg_id}")])
    else:
        rows.append([InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"approve:{tg_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="employees:back")])
    return ikb(rows)
