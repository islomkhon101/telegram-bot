import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
ALLOWED_GROUP_ID = int(os.getenv("ALLOWED_GROUP_ID", "0") or 0)

AIRLINES = [
    "JETEX", "RUSJET", "FCG", "SOLARIS",
    "UVT", "RUSAERO", "SICHUAN AIRLINES", "SCAT AIRLINES",
]

RESTAURANTS = ["HANZADE", "PLATAN", "OASIS"]
