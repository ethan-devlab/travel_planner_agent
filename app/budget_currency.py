# coding=utf-8
import re


BUDGET_CURRENCY_CODES = (
    "TWD",
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "CAD",
    "CHF",
    "CNY",
    "SEK",
    "NZD",
    "HKD",
    "SGD",
    "KRW",
    "INR",
    "MXN",
    "MYR",
    "RUB",
    "ZAR",
    "BRL",
    "TRY",
)

BUDGET_CURRENCY_CHOICES = tuple((code, code) for code in BUDGET_CURRENCY_CODES)

BUDGET_CURRENCY_SYMBOLS = {
    "TWD": "NT$",
    "USD": "US$",
    "EUR": "EUR ",
    "GBP": "GBP ",
    "JPY": "JPY ",
    "AUD": "AUD ",
    "CAD": "CAD ",
    "CHF": "CHF ",
    "CNY": "CNY ",
    "SEK": "SEK ",
    "NZD": "NZD ",
    "HKD": "HK$",
    "SGD": "SGD ",
    "KRW": "KRW ",
    "INR": "INR ",
    "MXN": "MXN ",
    "MYR": "MYR ",
    "RUB": "RUB ",
    "ZAR": "ZAR ",
    "BRL": "BRL ",
    "TRY": "TRY ",
}

LOCATION_CURRENCY_HINTS = (
    ("台灣", "TWD"),
    ("臺灣", "TWD"),
    ("taiwan", "TWD"),
    ("台北", "TWD"),
    ("臺北", "TWD"),
    ("新北", "TWD"),
    ("台中", "TWD"),
    ("臺中", "TWD"),
    ("台南", "TWD"),
    ("臺南", "TWD"),
    ("高雄", "TWD"),
    ("香港", "HKD"),
    ("hong kong", "HKD"),
    ("日本", "JPY"),
    ("japan", "JPY"),
    ("東京", "JPY"),
    ("tokyo", "JPY"),
    ("大阪", "JPY"),
    ("osaka", "JPY"),
    ("京都", "JPY"),
    ("kyoto", "JPY"),
    ("韓國", "KRW"),
    ("南韓", "KRW"),
    ("korea", "KRW"),
    ("seoul", "KRW"),
    ("中國", "CNY"),
    ("china", "CNY"),
    ("新加坡", "SGD"),
    ("singapore", "SGD"),
    ("英國", "GBP"),
    ("united kingdom", "GBP"),
    ("london", "GBP"),
    ("美國", "USD"),
    ("united states", "USD"),
    ("usa", "USD"),
    ("加拿大", "CAD"),
    ("canada", "CAD"),
    ("澳洲", "AUD"),
    ("australia", "AUD"),
    ("紐西蘭", "NZD"),
    ("new zealand", "NZD"),
    ("瑞士", "CHF"),
    ("switzerland", "CHF"),
    ("瑞典", "SEK"),
    ("sweden", "SEK"),
    ("印度", "INR"),
    ("india", "INR"),
    ("墨西哥", "MXN"),
    ("mexico", "MXN"),
    ("馬來西亞", "MYR"),
    ("malaysia", "MYR"),
    ("俄羅斯", "RUB"),
    ("russia", "RUB"),
    ("南非", "ZAR"),
    ("south africa", "ZAR"),
    ("巴西", "BRL"),
    ("brazil", "BRL"),
    ("土耳其", "TRY"),
    ("turkey", "TRY"),
    ("法國", "EUR"),
    ("france", "EUR"),
    ("德國", "EUR"),
    ("germany", "EUR"),
    ("義大利", "EUR"),
    ("italy", "EUR"),
    ("西班牙", "EUR"),
    ("spain", "EUR"),
    ("荷蘭", "EUR"),
    ("netherlands", "EUR"),
)


def infer_budget_currency(location_text, fallback="TWD"):
    normalized = re.sub(r"\s+", " ", str(location_text or "").strip()).casefold()
    if not normalized:
        return fallback

    for hint, currency_code in LOCATION_CURRENCY_HINTS:
        if hint.casefold() in normalized:
            return currency_code
    return fallback


def resolve_budget_currency(location_text, submitted_currency, fallback="TWD"):
    normalized_currency = str(submitted_currency or "").strip().upper()
    if normalized_currency and normalized_currency != "AUTO" and normalized_currency in BUDGET_CURRENCY_CODES:
        return normalized_currency
    return infer_budget_currency(location_text, fallback=fallback)


def format_budget(amount, currency_code):
    symbol = BUDGET_CURRENCY_SYMBOLS.get(currency_code or "TWD", f"{currency_code or 'TWD'} ")
    return f"{symbol}{amount}"
