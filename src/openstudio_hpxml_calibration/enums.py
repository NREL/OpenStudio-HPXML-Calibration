from enum import Enum


class Granularity(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class Format(str, Enum):
    CSV = "csv"
    JSON = "json"
    MSGPACK = "msgpack"
    CSV_DVIEW = "csv_dview"
