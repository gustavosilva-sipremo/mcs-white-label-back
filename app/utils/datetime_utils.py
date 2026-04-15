from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


def now_brasilia() -> datetime:
    return datetime.now(BR_TZ)


def expiration_from_now_brasilia(delta: timedelta) -> datetime:
    return now_brasilia() + delta
