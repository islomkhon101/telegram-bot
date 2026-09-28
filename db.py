import aiosqlite
from datetime import datetime, date, timedelta

DB_PATH = "flight_bot.sqlite3"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    telegram_full_name TEXT,
    full_name TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    first_seen TEXT NOT NULL,
    approved_at TEXT,
    approved_by INTEGER
);

CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER NOT NULL,
    source_chat_id INTEGER,
    source_chat_type TEXT,
    flight_date TEXT NOT NULL,
    flight_no TEXT NOT NULL,
    airline TEXT NOT NULL,
    operation TEXT NOT NULL,
    route TEXT NOT NULL,
    stay_days INTEGER NOT NULL DEFAULT 0,
    crew_hotel TEXT,
    pax_hotel TEXT,
    crew_count INTEGER NOT NULL DEFAULT 0,
    pax_count INTEGER NOT NULL DEFAULT 0,
    transfer INTEGER NOT NULL DEFAULT 0,
    transfer_provider TEXT,
    catering INTEGER NOT NULL DEFAULT 0,
    restaurant TEXT,
    extra_purchase INTEGER NOT NULL DEFAULT 0,
    extra_purchase_text TEXT,
    served_display TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flight_staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id INTEGER NOT NULL,
    employee_tg_id INTEGER,
    manual_name TEXT,
    FOREIGN KEY(flight_id) REFERENCES flights(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flight_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id INTEGER NOT NULL,
    file_id TEXT NOT NULL,
    file_unique_id TEXT,
    FOREIGN KEY(flight_id) REFERENCES flights(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_flights_date ON flights(flight_date);
"""

async def _ensure_column(db, table, column, sql_type):
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in await cur.fetchall()}
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # First create tables that do not exist.
        await db.executescript(SCHEMA)

        # Then migrate old v1 tables by adding columns that may be missing.
        emp_cols = {
            "telegram_full_name":"TEXT", "full_name":"TEXT", "phone":"TEXT",
            "status":"TEXT NOT NULL DEFAULT 'pending'", "approved_at":"TEXT", "approved_by":"INTEGER"
        }
        flight_cols = {
            "source_chat_id":"INTEGER","source_chat_type":"TEXT","crew_hotel":"TEXT",
            "pax_hotel":"TEXT","transfer_provider":"TEXT","served_display":"TEXT"
        }
        for c, t in emp_cols.items():
            await _ensure_column(db, "employees", c, t)
        for c, t in flight_cols.items():
            await _ensure_column(db, "flights", c, t)

        # Indexes that depend on migrated columns must be created last.
        await db.execute("CREATE INDEX IF NOT EXISTS idx_emp_status ON employees(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_flights_date ON flights(flight_date)")
        await db.commit()

async def ensure_employee(tg_id, username, telegram_full_name):
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO employees(tg_id,username,telegram_full_name,first_seen,status)
            VALUES(?,?,?,?, 'pending')
            ON CONFLICT(tg_id) DO UPDATE SET username=excluded.username,
                telegram_full_name=excluded.telegram_full_name
        """,(tg_id,username,telegram_full_name,now))
        await db.commit()

async def get_employee(tg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute("SELECT * FROM employees WHERE tg_id=?",(tg_id,))
        return await cur.fetchone()

async def set_registration(tg_id, full_name, phone):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET full_name=?, phone=? WHERE tg_id=?",(full_name,phone,tg_id))
        await db.commit()

async def set_status(tg_id,status,approved_by=None):
    stamp=datetime.now().isoformat(timespec="seconds") if status=="approved" else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET status=?, approved_at=?, approved_by=? WHERE tg_id=?",
                         (status,stamp,approved_by,tg_id))
        await db.commit()

async def list_employees(status=None, exclude_tg_id=None):
    q="SELECT * FROM employees WHERE 1=1"; p=[]
    if status:
        q+=" AND status=?"; p.append(status)
    if exclude_tg_id is not None:
        q+=" AND tg_id<>?"; p.append(exclude_tg_id)
    q+=" ORDER BY COALESCE(full_name,telegram_full_name,username)"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute(q,p); return await cur.fetchall()

async def duplicate_flight_exists(flight_date, flight_no):
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute("SELECT 1 FROM flights WHERE flight_date=? AND UPPER(flight_no)=UPPER(?) LIMIT 1",
                             (flight_date,flight_no.strip()))
        return await cur.fetchone() is not None

async def save_flight(data, created_by, staff_ids, manual_names, photos, source_chat_id, source_chat_type):
    print("SAVE_FLIGHT START", data .get("flight_no"), created_by, staff_ids, flush = True)
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute("""
        INSERT INTO flights(
          created_by,source_chat_id,source_chat_type,flight_date,flight_no,airline,operation,route,
          stay_days,crew_hotel,pax_hotel,crew_count,pax_count,transfer,transfer_provider,catering,
          restaurant,extra_purchase,extra_purchase_text,served_display,comment,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
          created_by,source_chat_id,source_chat_type,data["flight_date"],data["flight_no"],data["airline"],
          data["operation"],data["route"],int(data["stay_days"]),data.get("crew_hotel"),data.get("pax_hotel"),
          int(data["crew_count"]),int(data["pax_count"]),1 if data.get("transfer") else 0,
          data.get("transfer_provider"),1 if data.get("catering") else 0,data.get("restaurant"),
          1 if data.get("extra_purchase") else 0,data.get("extra_purchase_text"),data.get("staff_display"),
          data.get("comment"),datetime.now().isoformat(timespec="seconds")
        ))
        fid=cur.lastrowid
        for tid in sorted(set(int(x) for x in staff_ids)):
            await db.execute("INSERT INTO flight_staff(flight_id,employee_tg_id,manual_name) VALUES(?,?,NULL)",(fid,tid))
        for name in sorted(set(n.strip() for n in manual_names if n.strip())):
            await db.execute("INSERT INTO flight_staff(flight_id,employee_tg_id,manual_name) VALUES(?,NULL,?)",(fid,name))
        for p in photos:
            await db.execute("INSERT INTO flight_photos(flight_id,file_id,file_unique_id) VALUES(?,?,?)",
                             (fid,p["file_id"],p.get("file_unique_id")))
        await db.commit()
        print("SAVE_FLIGHT OK", fid, flush=True)        
        return fid

async def get_flight(fid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute("SELECT * FROM flights WHERE id=?",(fid,))
        return await cur.fetchone()

async def get_photos(fid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute("SELECT * FROM flight_photos WHERE flight_id=? ORDER BY id",(fid,))
        return await cur.fetchall()

async def get_flights(start_date,end_date,employee_tg_id=None):
    print("GET_FLIGHTS", start_date, end_date, employee_tg_id, flush=True    
    q="SELECT * FROM flights WHERE flight_date BETWEEN ? AND ?"; p=[start_date,end_date]
    if employee_tg_id is not None:
        q+=" AND EXISTS(SELECT 1 FROM flight_staff fs WHERE fs.flight_id=flights.id AND fs.employee_tg_id=?)"
        p.append(employee_tg_id)
    q+=" ORDER BY flight_date DESC,id DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute(q,p); return await cur.fetchall()

async def delete_flight(fid):
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute("DELETE FROM flights WHERE id=?",(fid,))
        await db.commit(); return cur.rowcount>0

async def workload(start_date,end_date):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        cur=await db.execute("""
        SELECT e.tg_id,
        COALESCE(e.full_name,e.telegram_full_name,e.username,CAST(e.tg_id AS TEXT)) name,
        COUNT(DISTINCT CASE WHEN f.flight_date BETWEEN ? AND ? THEN fs.flight_id END) flights_count
        FROM employees e
        LEFT JOIN flight_staff fs ON fs.employee_tg_id=e.tg_id
        LEFT JOIN flights f ON f.id=fs.flight_id
        WHERE e.status='approved'
        GROUP BY e.tg_id,name ORDER BY name
        """,(start_date,end_date))
        return await cur.fetchall()

def date_range(kind):
    t=date.today()
    if kind=="today": return t.isoformat(),t.isoformat()
    if kind=="yesterday":
        d=t-timedelta(days=1); return d.isoformat(),d.isoformat()
    if kind=="week":
        s=t-timedelta(days=t.weekday()); return s.isoformat(),t.isoformat()
    if kind=="month": return t.replace(day=1).isoformat(),t.isoformat()
    raise ValueError(kind)
