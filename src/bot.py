import os
import asyncio
import importlib
import json
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BOT_NAME = os.getenv("BOT_NAME", "Grace")
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Jakarta")
GLOBAL_RPM_LIMIT = max(1, int(os.getenv("GLOBAL_RPM_LIMIT", "4")))
USER_COOLDOWN_SEC = max(1.0, float(os.getenv("USER_COOLDOWN_SEC", "8")))
MAX_IMAGE_BYTES = max(1, int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024))))
MAX_IMAGES_PER_REQUEST = max(1, int(os.getenv("MAX_IMAGES_PER_REQUEST", "3")))
HISTORY_MAX_TURNS = max(1, int(os.getenv("HISTORY_MAX_TURNS", "6")))
CHANNEL_HISTORY_MESSAGES = max(0, int(os.getenv("CHANNEL_HISTORY_MESSAGES", "6")))
WEATHER_DEFAULT_LOCATION = os.getenv("WEATHER_DEFAULT_LOCATION", "Jakarta")
NEWS_MAX_ITEMS = max(1, min(10, int(os.getenv("NEWS_MAX_ITEMS", "5"))))
NEWS_REGION_LANGUAGE = os.getenv("NEWS_REGION_LANGUAGE", "id")
NEWS_REGION_COUNTRY = os.getenv("NEWS_REGION_COUNTRY", "ID")
DATABASE_URL = os.getenv("DATABASE_URL", "")
HISTORY_BACKEND = os.getenv("HISTORY_BACKEND", "auto").strip().lower()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_STORE_PATH = DATA_DIR / "conversation_history.json"

IDENTITY_TEXT = (
    "Saya adalah Grace, asisten AI DPNP yang dibuat oleh Brann. "
    "Saya siap membantu menjawab pertanyaan dan memberikan penjelasan dengan jelas."
)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
gemini_model: Optional[genai.GenerativeModel] = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(GEMINI_MODEL)

request_timestamps: deque[float] = deque()
last_user_request: dict[int, float] = {}
gemini_lock = asyncio.Lock()
NAME_TRIGGER_PUNCTUATION = ".,:;!?-"


@dataclass
class AIResult:
    text: str
    is_private_warning: bool = False
    is_error: bool = False


@dataclass
class ImagePayload:
    data: bytes
    mime_type: str
    filename: str


conversation_history: dict[str, deque[dict[str, str]]] = {}
history_lock = asyncio.Lock()


def _resolve_history_backend() -> str:
    if HISTORY_BACKEND in {"file", "postgres"}:
        if HISTORY_BACKEND == "postgres" and not DATABASE_URL:
            return "file"
        return HISTORY_BACKEND
    if DATABASE_URL:
        return "postgres"
    return "file"


ACTIVE_HISTORY_BACKEND = _resolve_history_backend()


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_history_store_sync() -> dict[str, deque[dict[str, str]]]:
    _ensure_data_dir()
    if not HISTORY_STORE_PATH.exists():
        return {}

    try:
        with HISTORY_STORE_PATH.open("r", encoding="utf-8") as file:
            raw_data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    histories: dict[str, deque[dict[str, str]]] = {}
    if not isinstance(raw_data, dict):
        return histories

    for key, turns in raw_data.items():
        if not isinstance(key, str) or not isinstance(turns, list):
            continue
        cleaned_turns: list[dict[str, str]] = []
        for turn in turns[-HISTORY_MAX_TURNS:]:
            if not isinstance(turn, dict):
                continue
            user_text = str(turn.get("user", "")).strip()
            bot_text = str(turn.get("bot", "")).strip()
            if not user_text or not bot_text:
                continue
            cleaned_turns.append({"user": user_text, "bot": bot_text})
        if cleaned_turns:
            histories[key] = deque(cleaned_turns, maxlen=HISTORY_MAX_TURNS)
    return histories


def _save_history_store_sync(histories: dict[str, deque[dict[str, str]]]) -> None:
    _ensure_data_dir()
    serializable = {
        key: list(turns)[-HISTORY_MAX_TURNS:]
        for key, turns in histories.items()
        if turns
    }
    with HISTORY_STORE_PATH.open("w", encoding="utf-8") as file:
        json.dump(serializable, file, ensure_ascii=False, indent=2)


def _get_postgres_connection() -> Any:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL belum diisi.")
    try:
        psycopg_module = importlib.import_module("psycopg")
    except ImportError as exc:
        raise RuntimeError("psycopg belum terpasang.") from exc
    return psycopg_module.connect(DATABASE_URL)


def _init_postgres_history_sync() -> None:
    with _get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    turn_id BIGSERIAL PRIMARY KEY,
                    conversation_key TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    bot_text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_history_key_turn_id
                ON conversation_history (conversation_key, turn_id DESC)
                """
            )
        connection.commit()


def _load_postgres_history_sync() -> dict[str, deque[dict[str, str]]]:
    histories: dict[str, deque[dict[str, str]]] = {}
    with _get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conversation_key, user_text, bot_text
                FROM (
                    SELECT
                        conversation_key,
                        user_text,
                        bot_text,
                        turn_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY conversation_key
                            ORDER BY turn_id DESC
                        ) AS row_num
                    FROM conversation_history
                ) ranked
                WHERE row_num <= %s
                ORDER BY conversation_key, turn_id ASC
                """,
                (HISTORY_MAX_TURNS,),
            )
            for conversation_key, user_text, bot_text in cursor.fetchall():
                turns = histories.setdefault(
                    conversation_key,
                    deque(maxlen=HISTORY_MAX_TURNS),
                )
                turns.append({
                    "user": str(user_text).strip(),
                    "bot": str(bot_text).strip(),
                })
    return histories


def _save_postgres_turn_sync(conversation_key: str, user_text: str, bot_text: str) -> None:
    with _get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_history (conversation_key, user_text, bot_text)
                VALUES (%s, %s, %s)
                """,
                (conversation_key, user_text, bot_text),
            )
            cursor.execute(
                """
                DELETE FROM conversation_history
                WHERE conversation_key = %s
                  AND turn_id NOT IN (
                      SELECT turn_id
                      FROM conversation_history
                      WHERE conversation_key = %s
                      ORDER BY turn_id DESC
                      LIMIT %s
                  )
                """,
                (conversation_key, conversation_key, HISTORY_MAX_TURNS),
            )
        connection.commit()


def _clear_postgres_history_sync(conversation_key: str) -> None:
    with _get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM conversation_history WHERE conversation_key = %s",
                (conversation_key,),
            )
        connection.commit()


def _initialize_history_store_sync() -> dict[str, deque[dict[str, str]]]:
    if ACTIVE_HISTORY_BACKEND == "postgres":
        _init_postgres_history_sync()
        return _load_postgres_history_sync()
    return _load_history_store_sync()


def _build_conversation_key(message: discord.Message) -> str:
    guild_id = message.guild.id if message.guild else "dm"
    channel_id = message.channel.id
    author_id = message.author.id
    return f"{guild_id}:{channel_id}:{author_id}"


def _build_history_context(conversation_key: str) -> str:
    turns = conversation_history.get(conversation_key)
    if not turns:
        return ""

    lines: list[str] = []
    for index, turn in enumerate(turns, start=1):
        user_text = turn.get("user", "").strip()
        bot_text = turn.get("bot", "").strip()
        if not user_text or not bot_text:
            continue
        lines.append(f"{index}. User: {user_text}")
        lines.append(f"{index}. Grace: {bot_text}")
    return "\n".join(lines)


async def _build_recent_channel_context(message: discord.Message) -> str:
    if CHANNEL_HISTORY_MESSAGES <= 0:
        return ""

    if not hasattr(message.channel, "history"):
        return ""

    context_lines: list[str] = []
    try:
        history_messages = [
            item
            async for item in message.channel.history(limit=CHANNEL_HISTORY_MESSAGES, before=message)
        ]
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return ""

    for previous_message in reversed(history_messages):
        content = (previous_message.content or "").strip()
        if not content and previous_message.attachments:
            content = f"[mengirim {len(previous_message.attachments)} attachment]"
        if not content:
            continue

        author_name = previous_message.author.display_name
        if previous_message.author == message.author:
            author_name = "User"
        elif client.user and previous_message.author.id == client.user.id:
            author_name = BOT_NAME
        context_lines.append(f"{author_name}: {content}")

    return "\n".join(context_lines)


async def _store_conversation_turn(conversation_key: str, user_text: str, bot_text: str) -> None:
    normalized_user_text = (user_text or "").strip()
    normalized_bot_text = (bot_text or "").strip()
    if not normalized_user_text or not normalized_bot_text:
        return

    async with history_lock:
        turns = conversation_history.setdefault(
            conversation_key,
            deque(maxlen=HISTORY_MAX_TURNS),
        )
        turns.append({"user": normalized_user_text, "bot": normalized_bot_text})
        snapshot = {key: deque(value, maxlen=HISTORY_MAX_TURNS) for key, value in conversation_history.items()}
    if ACTIVE_HISTORY_BACKEND == "postgres":
        await asyncio.to_thread(
            _save_postgres_turn_sync,
            conversation_key,
            normalized_user_text,
            normalized_bot_text,
        )
        return
    await asyncio.to_thread(_save_history_store_sync, snapshot)


async def _clear_conversation_history(conversation_key: str) -> None:
    async with history_lock:
        conversation_history.pop(conversation_key, None)
        snapshot = {key: deque(value, maxlen=HISTORY_MAX_TURNS) for key, value in conversation_history.items()}
    if ACTIVE_HISTORY_BACKEND == "postgres":
        await asyncio.to_thread(_clear_postgres_history_sync, conversation_key)
        return
    await asyncio.to_thread(_save_history_store_sync, snapshot)


def _weather_code_to_text(code: Optional[int]) -> str:
    weather_map = {
        0: "cerah",
        1: "sebagian cerah",
        2: "berawan",
        3: "mendung",
        45: "berkabut",
        48: "kabut beku",
        51: "gerimis ringan",
        53: "gerimis",
        55: "gerimis lebat",
        56: "gerimis beku ringan",
        57: "gerimis beku lebat",
        61: "hujan ringan",
        63: "hujan sedang",
        65: "hujan lebat",
        66: "hujan beku ringan",
        67: "hujan beku lebat",
        71: "salju ringan",
        73: "salju sedang",
        75: "salju lebat",
        77: "butiran salju",
        80: "hujan lokal ringan",
        81: "hujan lokal",
        82: "hujan lokal lebat",
        85: "salju lokal ringan",
        86: "salju lokal lebat",
        95: "badai petir",
        96: "badai petir dan hujan es ringan",
        99: "badai petir dan hujan es lebat",
    }
    return weather_map.get(code or 0, "kondisi tidak diketahui")


def _http_get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def _http_get_text(url: str) -> str:
    with urlopen(url, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_location_from_weather_prompt(prompt: str) -> tuple[str, bool]:
    cleaned = re.sub(r"\s+", " ", (prompt or "").strip())
    lowered = cleaned.lower()
    patterns = [
        r"(?:cuaca|weather|suhu|prakiraan cuaca)\s+(?:di|untuk|kota|daerah)\s+(.+)$",
        r"(?:bagaimana|gimana)\s+cuaca\s+(?:di|untuk)\s+(.+)$",
        r"(?:cuaca|weather)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        location = cleaned[match.start(1):match.end(1)].strip(" ?!.,")
        if location:
            return location, False
    return WEATHER_DEFAULT_LOCATION, True


def is_weather_question(prompt: str) -> bool:
    p = (prompt or "").lower()
    keywords = [
        "cuaca",
        "weather",
        "suhu",
        "temperatur",
        "prakiraan cuaca",
        "forecast",
    ]
    return any(keyword in p for keyword in keywords)


def is_clear_history_command(prompt: str) -> bool:
    p = (prompt or "").lower().strip()
    commands = [
        "hapus history",
        "hapus riwayat",
        "clear history",
        "reset history",
        "lupakan percakapan",
        "hapus memori",
        "clear memory",
        "reset memory",
    ]
    return any(command in p for command in commands)


def _fetch_weather_sync(location: str) -> dict[str, Any]:
    geocode_url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote_plus(location)}&count=1&language=id&format=json"
    )
    geocode_data = _http_get_json(geocode_url)
    results = geocode_data.get("results") or []
    if not results:
        raise ValueError(f"Lokasi '{location}' tidak ditemukan.")

    best_match = results[0]
    latitude = best_match.get("latitude")
    longitude = best_match.get("longitude")
    if latitude is None or longitude is None:
        raise ValueError(f"Koordinat untuk '{location}' tidak tersedia.")

    weather_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m"
        "&timezone=auto"
    )
    weather_data = _http_get_json(weather_url)
    current = weather_data.get("current") or {}
    return {
        "resolved_name": best_match.get("name") or location,
        "admin1": best_match.get("admin1") or "",
        "country": best_match.get("country") or "",
        "timezone": weather_data.get("timezone") or "setempat",
        "current": current,
    }


async def get_weather_reply(prompt: str) -> AIResult:
    location, used_default = _extract_location_from_weather_prompt(prompt)
    try:
        weather = await asyncio.to_thread(_fetch_weather_sync, location)
    except ValueError as exc:
        return AIResult(str(exc), is_error=True)
    except (HTTPError, URLError, TimeoutError):
        return AIResult(
            "Layanan cuaca sedang tidak bisa diakses. Coba lagi beberapa saat lagi.",
            is_error=True,
        )
    except Exception:
        return AIResult("Gagal mengambil data cuaca saat ini. Coba lagi sebentar ya.", is_error=True)

    current = weather.get("current") or {}
    resolved_name = weather.get("resolved_name", location)
    admin1 = weather.get("admin1", "")
    country = weather.get("country", "")
    location_label = ", ".join(part for part in [resolved_name, admin1, country] if part)
    condition = _weather_code_to_text(current.get("weather_code"))
    intro = (
        f"Saya pakai lokasi default {WEATHER_DEFAULT_LOCATION}. "
        if used_default else ""
    )
    return AIResult(
        (
            f"{intro}Cuaca saat ini di {location_label}: {condition}. "
            f"Suhu {current.get('temperature_2m', '-')}°C, terasa seperti {current.get('apparent_temperature', '-')}°C, "
            f"kelembapan {current.get('relative_humidity_2m', '-')}%, "
            f"angin {current.get('wind_speed_10m', '-')} km/jam, "
            f"presipitasi {current.get('precipitation', '-')} mm. "
            f"Zona waktu lokasi: {weather.get('timezone', 'setempat')}."
        ).strip()
    )


def is_news_question(prompt: str) -> bool:
    p = (prompt or "").lower()
    keywords = [
        "berita",
        "headline",
        "news",
        "kabar terbaru",
        "top stories",
        "berita populer",
        "berita hari ini",
    ]
    return any(keyword in p for keyword in keywords)


def _extract_news_topic(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", (prompt or "").strip())
    lowered = cleaned.lower()
    patterns = [
        r"(?:berita|headline|news|kabar terbaru)\s+(?:tentang|soal|mengenai)\s+(.+)$",
        r"(?:berita|headline|news)\s+(.+)$",
        r"top stories\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        topic = cleaned[match.start(1):match.end(1)].strip(" ?!.,")
        if topic and topic.lower() not in {"hari ini", "terbaru", "populer", "sekarang"}:
            return topic
    return ""


def _build_news_feed_url(topic: str = "") -> str:
    if topic:
        return (
            "https://news.google.com/rss/search"
            f"?q={quote_plus(topic)}&hl={NEWS_REGION_LANGUAGE}&gl={NEWS_REGION_COUNTRY}"
            f"&ceid={NEWS_REGION_COUNTRY}:{NEWS_REGION_LANGUAGE}"
        )
    return (
        "https://news.google.com/rss"
        f"?hl={NEWS_REGION_LANGUAGE}&gl={NEWS_REGION_COUNTRY}&ceid={NEWS_REGION_COUNTRY}:{NEWS_REGION_LANGUAGE}"
    )


def _fetch_popular_news_sync(topic: str = "") -> list[dict[str, str]]:
    raw_xml = _http_get_text(_build_news_feed_url(topic))
    root = ElementTree.fromstring(raw_xml)
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "pub_date": pub_date})
        if len(items) >= NEWS_MAX_ITEMS:
            break
    return items


async def get_news_reply(prompt: str) -> AIResult:
    topic = _extract_news_topic(prompt)
    try:
        items = await asyncio.to_thread(_fetch_popular_news_sync, topic)
    except (HTTPError, URLError, TimeoutError, ElementTree.ParseError):
        return AIResult(
            "Feed berita sedang tidak bisa diakses. Coba lagi beberapa saat lagi.",
            is_error=True,
        )
    except Exception:
        return AIResult("Gagal mengambil berita populer saat ini. Coba lagi sebentar ya.", is_error=True)

    if not items:
        if topic:
            return AIResult(f"Belum ada berita yang ditemukan untuk topik '{topic}'.", is_error=True)
        return AIResult("Belum ada berita populer yang bisa diambil saat ini.", is_error=True)

    heading = f"Berita terbaru untuk topik {topic}:" if topic else "Berita populer saat ini:"
    DISCORD_LIMIT = 1950
    result_lines = [heading]
    current_length = len(heading)

    for index, item in enumerate(items, start=1):
        title_line = f"{index}. {item['title']}"
        # Potong URL supaya tidak meledakkan panjang pesan.
        raw_link = item["link"]
        max_link_len = 100
        link_display = raw_link if len(raw_link) <= max_link_len else raw_link[:max_link_len] + "..."
        link_line = f"   {link_display}"

        entry = f"\n{title_line}\n{link_line}"
        if current_length + len(entry) > DISCORD_LIMIT:
            break
        result_lines.append(title_line)
        result_lines.append(link_line)
        current_length += len(entry)

    return AIResult("\n".join(result_lines))


def _detect_vision_mode(prompt: str) -> str:
    p = (prompt or "").lower()
    ocr_keywords = [
        "ocr",
        "baca teks",
        "extract text",
        "ekstrak teks",
        "salin teks",
        "transkrip",
        "transcribe",
        "copy text",
    ]
    summary_keywords = [
        "ringkas visual",
        "summary visual",
        "ringkasan visual",
        "format poin",
        "bullet",
        "objek utama",
        "apa yang terlihat",
    ]
    if any(k in p for k in ocr_keywords):
        return "ocr"
    if any(k in p for k in summary_keywords):
        return "summary"
    return "default"


def _has_name_trigger(text: str) -> bool:
    bot_name_lower = BOT_NAME.lower()
    lowered = text.lower()
    if not lowered.startswith(bot_name_lower):
        return False
    if len(text) == len(BOT_NAME):
        return False
    return text[len(BOT_NAME)] in NAME_TRIGGER_PUNCTUATION


def should_respond(message: discord.Message, me: discord.ClientUser) -> bool:
    content = (message.content or "").strip()
    if not content:
        return False

    # Trigger saat bot di-mention.
    if me.mentioned_in(message):
        return True

    # Trigger saat user memanggil nama bot di awal pesan dengan tanda baca.
    return _has_name_trigger(content)


def normalize_prompt(message: discord.Message, me: discord.ClientUser) -> str:
    text = (message.content or "").strip()

    # Hapus mention bot kalau ada.
    text = text.replace(f"<@{me.id}>", "").replace(f"<@!{me.id}>", "").strip()

    # Hapus nama bot di awal, misalnya "Grace, ..." atau "Grace. ...".
    if _has_name_trigger(text):
        text = text[len(BOT_NAME):].lstrip(" ,:.-")

    return text.strip()


def is_intro_question(prompt: str) -> bool:
    p = prompt.lower()
    keywords = [
        "siapa kamu",
        "siapa dirimu",
        "kamu siapa",
        "siapa anda",
        "siapa dirimu sebenarnya",
        "nama kamu",
        "namamu siapa",
        "kenalan",
        "perkenalkan",
        "ceritakan tentang dirimu",
        "siapa yang membuatmu",
        "siapa pembuatmu",
        "who are you",
        "introduce yourself",
    ]
    return any(k in p for k in keywords)


def _is_limit_message(text: str) -> bool:
    lowered = text.lower()
    keywords = ["limit gemini", "quota", "rate", "resource_exhausted", "429"]
    return any(k in lowered for k in keywords)


def _get_time_period(hour: int) -> str:
    if 0 <= hour < 4:
        return "dini hari"
    if 4 <= hour < 11:
        return "pagi"
    if 11 <= hour < 15:
        return "siang"
    if 15 <= hour < 18:
        return "sore"
    return "malam"


def _get_now_in_timezone() -> tuple[datetime, str]:
    timezone_name = BOT_TIMEZONE
    try:
        now = datetime.now(ZoneInfo(BOT_TIMEZONE))
    except ZoneInfoNotFoundError:
        now = datetime.now().astimezone()
        timezone_name = str(now.tzinfo) if now.tzinfo else "local"
    return now, timezone_name


def _format_datetime_parts() -> tuple[datetime, str, str, str, str, str]:
    weekdays = [
        "Senin",
        "Selasa",
        "Rabu",
        "Kamis",
        "Jumat",
        "Sabtu",
        "Minggu",
    ]
    months = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]

    now, timezone_name = _get_now_in_timezone()
    weekday = weekdays[now.weekday()]
    month = months[now.month - 1]
    time_period = _get_time_period(now.hour)
    timestamp = now.strftime("%H:%M:%S")
    tz_abbr = now.tzname() or timezone_name
    return now, timezone_name, weekday, month, time_period, f"{timestamp} {tz_abbr}"


def _get_current_datetime_context() -> str:
    now, timezone_name, weekday, month, time_period, timestamp = _format_datetime_parts()
    return (
        f"Waktu saat ini adalah {weekday}, {now.day} {month} {now.year}, "
        f"pukul {timestamp} ({time_period}) di zona waktu {timezone_name}."
    )


def is_datetime_question(prompt: str) -> bool:
    p = prompt.lower()
    keywords = [
        "jam berapa",
        "pukul berapa",
        "waktu sekarang",
        "jam sekarang",
        "tanggal berapa",
        "tanggal sekarang",
        "hari apa",
        "hari ini hari apa",
        "sekarang hari apa",
        "tanggal dan waktu",
        "waktu saat ini",
        "what time",
        "what date",
        "current time",
        "current date",
        "sekarang dini hari",
        "sekarang pagi",
        "sekarang siang",
        "sekarang sore",
        "sekarang malam",
    ]
    return any(k in p for k in keywords)


def build_datetime_reply() -> str:
    now, _, weekday, month, time_period, timestamp = _format_datetime_parts()
    return (
        f"Sekarang hari {weekday}, {now.day} {month} {now.year}, "
        f"pukul {timestamp}. Saat ini masih {time_period}."
    )


async def ask_ai(user_prompt: str, history_context: str = "", channel_context: str = "") -> AIResult:
    if not gemini_model:
        return AIResult(
            "GEMINI_API_KEY belum diset. Isi GEMINI_API_KEY di file .env agar Grace bisa menjawab dengan AI.",
            is_error=True,
        )
    if not GEMINI_API_KEY.startswith("AIza"):
        return AIResult(
            "GEMINI_API_KEY tidak valid. Gunakan API key dari Google AI Studio (biasanya berawalan 'AIza').",
            is_error=True,
        )

    try:
        datetime_context = _get_current_datetime_context()
        system_prompt = (
            "Kamu adalah Grace, asisten AI DPNP yang dibuat oleh Brann. "
            "Jawab dengan ramah, natural, jelas, dan tetap to the point. "
            "Gunakan bahasa Indonesia kecuali user meminta bahasa lain. "
            f"{datetime_context} "
            "Jika tersedia, gunakan riwayat percakapan terbaru untuk menjaga konteks jawaban tetap nyambung, "
            "tetapi prioritaskan pertanyaan user yang paling baru. "
            "Jika user menanyakan tanggal, hari, jam, atau waktu sekarang, gunakan konteks waktu tersebut sebagai acuan utama. "
            f"Jika user menanyakan siapa kamu, identitasmu, atau siapa pembuatmu, jawab secara konsisten dengan kalimat ini: {IDENTITY_TEXT}"
        )
        history_section = f"Riwayat percakapan terbaru:\n{history_context}\n\n" if history_context else ""
        channel_section = (
            f"Pesan sebelumnya di channel yang relevan:\n{channel_context}\n\n"
            if channel_context else ""
        )
        full_prompt = f"{system_prompt}\n\n{history_section}{channel_section}Pertanyaan user: {user_prompt}"
        async with gemini_lock:
            response = await asyncio.to_thread(
                gemini_model.generate_content,
                full_prompt,
                generation_config={"temperature": 0.7},
            )
    except Exception as exc:
        err = str(exc).lower()
        if "api key" in err or "permission" in err or "unauth" in err:
            return AIResult(
                "GEMINI_API_KEY tidak valid atau belum punya izin. Cek key di Google AI Studio.",
                is_error=True,
            )
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        return AIResult("Gagal menghubungi layanan Gemini. Coba lagi sebentar ya.", is_error=True)

    try:
        answer = getattr(response, "text", "") or ""
    except Exception as exc:
        err = str(exc).lower()
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        if "safety" in err or "blocked" in err:
            return AIResult("Jawaban dibatasi oleh safety Gemini. Coba ubah pertanyaannya ya.", is_error=True)
        return AIResult("Gemini mengembalikan respons kosong. Coba lagi dengan pertanyaan yang lebih spesifik.", is_error=True)

    answer = answer.strip()
    if not answer:
        return AIResult("Gemini mengembalikan respons kosong. Coba lagi dengan pertanyaan yang lebih spesifik.", is_error=True)
    if len(answer) > 1900:
        answer = answer[:1900] + "\n\n...[jawaban dipotong karena terlalu panjang]"
    return AIResult(answer)


async def ask_ai_with_images(user_prompt: str, images: list[ImagePayload]) -> AIResult:
    if not gemini_model:
        return AIResult(
            "GEMINI_API_KEY belum diset. Isi GEMINI_API_KEY di file .env agar Grace bisa membaca gambar.",
            is_error=True,
        )
    if not GEMINI_API_KEY.startswith("AIza"):
        return AIResult(
            "GEMINI_API_KEY tidak valid. Gunakan API key dari Google AI Studio (biasanya berawalan 'AIza').",
            is_error=True,
        )

    if not images:
        return AIResult("Tidak ada gambar yang bisa diproses.", is_error=True)

    try:
        datetime_context = _get_current_datetime_context()
        system_prompt = (
            "Kamu adalah Grace, asisten AI DPNP yang dibuat oleh Brann. "
            "Jawab dengan ramah, natural, jelas, dan tetap to the point. "
            "Gunakan bahasa Indonesia kecuali user meminta bahasa lain. "
            f"{datetime_context} "
            "Kamu bisa membaca dan menganalisis gambar dari user. "
            "Jika detail gambar tidak terlihat jelas, jelaskan keterbatasan pengamatan secara jujur. "
            "Jika user menanyakan tanggal, hari, jam, atau waktu sekarang, gunakan konteks waktu tersebut sebagai acuan utama. "
            f"Jika user menanyakan siapa kamu, identitasmu, atau siapa pembuatmu, jawab secara konsisten dengan kalimat ini: {IDENTITY_TEXT}"
        )

        effective_prompt = user_prompt.strip() or "Tolong jelaskan isi gambar ini secara ringkas dan jelas."
        mode = _detect_vision_mode(effective_prompt)
        mode_instruction = ""
        if mode == "ocr":
            mode_instruction = (
                "Mode OCR aktif. Fokus menyalin teks yang terlihat di gambar seakurat mungkin. "
                "Pertahankan urutan baris. Jika ada bagian yang tidak terbaca, tulis [tidak terbaca]."
            )
        elif mode == "summary":
            mode_instruction = (
                "Mode ringkasan visual aktif. Jawab dalam format poin dengan struktur: "
                "1) Objek utama, 2) Teks yang terlihat, 3) Konteks/aktivitas, 4) Ketidakpastian."
            )

        text_part = (
            f"{system_prompt}\n\n"
            f"Instruksi mode: {mode_instruction or 'Mode normal analisis visual.'}\n"
            f"Instruksi user: {effective_prompt}"
        )
        content_parts: list[Any] = [text_part]
        for image in images:
            content_parts.append({"mime_type": image.mime_type, "data": image.data})

        async with gemini_lock:
            response = await asyncio.to_thread(
                gemini_model.generate_content,
                content_parts,
                generation_config={"temperature": 0.6},
            )
    except Exception as exc:
        err = str(exc).lower()
        if "api key" in err or "permission" in err or "unauth" in err:
            return AIResult(
                "GEMINI_API_KEY tidak valid atau belum punya izin. Cek key di Google AI Studio.",
                is_error=True,
            )
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        return AIResult("Gagal memproses gambar di Gemini. Coba lagi sebentar ya.", is_error=True)

    try:
        answer = getattr(response, "text", "") or ""
    except Exception as exc:
        err = str(exc).lower()
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        if "safety" in err or "blocked" in err:
            return AIResult("Analisis gambar dibatasi oleh safety Gemini. Coba gambar lain ya.", is_error=True)
        return AIResult("Gemini mengembalikan respons kosong untuk gambar. Coba lagi dengan instruksi yang lebih spesifik.", is_error=True)

    answer = answer.strip()
    if not answer:
        return AIResult("Gemini mengembalikan respons kosong untuk gambar. Coba lagi dengan instruksi yang lebih spesifik.", is_error=True)
    if len(answer) > 1900:
        answer = answer[:1900] + "\n\n...[jawaban dipotong karena terlalu panjang]"
    return AIResult(answer)


async def _extract_images(message: discord.Message) -> tuple[list[ImagePayload], Optional[str]]:
    async def _collect_from_attachments(
        attachments: list[discord.Attachment],
        images: list[ImagePayload],
    ) -> Optional[str]:
        for attachment in attachments:
            if len(images) >= MAX_IMAGES_PER_REQUEST:
                break
            content_type = (attachment.content_type or "").lower()
            is_image_mime = content_type.startswith("image/")
            is_image_ext = attachment.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif")
            )
            if not (is_image_mime or is_image_ext):
                continue
            if attachment.size and attachment.size > MAX_IMAGE_BYTES:
                return (
                    f"Ukuran gambar `{attachment.filename}` terlalu besar. "
                    f"Maksimal {MAX_IMAGE_BYTES // (1024 * 1024)} MB per gambar."
                )

            try:
                data = await attachment.read()
            except (discord.HTTPException, discord.Forbidden):
                return f"Gagal membaca file gambar `{attachment.filename}`. Coba upload ulang ya."

            mime_type = content_type if is_image_mime else "image/jpeg"
            images.append(
                ImagePayload(
                    data=data,
                    mime_type=mime_type,
                    filename=attachment.filename,
                )
            )
        return None

    images: list[ImagePayload] = []
    current_error = await _collect_from_attachments(message.attachments, images)
    if current_error:
        return [], current_error

    if len(images) >= MAX_IMAGES_PER_REQUEST:
        return images, None

    referenced_message: Optional[discord.Message] = None
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        referenced_message = message.reference.resolved
    elif message.reference and message.reference.message_id and message.channel:
        try:
            fetched = await message.channel.fetch_message(message.reference.message_id)
            if isinstance(fetched, discord.Message):
                referenced_message = fetched
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            referenced_message = None

    if referenced_message and referenced_message.attachments:
        reply_error = await _collect_from_attachments(referenced_message.attachments, images)
        if reply_error:
            return [], reply_error

    return images, None


def _allow_request(user_id: int) -> tuple[bool, Optional[str]]:
    now = time.time()
    cutoff = now - 60
    while request_timestamps and request_timestamps[0] < cutoff:
        request_timestamps.popleft()

    user_last = last_user_request.get(user_id, 0.0)
    if now - user_last < USER_COOLDOWN_SEC:
        wait_sec = int(USER_COOLDOWN_SEC - (now - user_last)) + 1
        return False, f"Grace lagi menunggu cooldown. Coba lagi {wait_sec} detik lagi ya."

    if len(request_timestamps) >= GLOBAL_RPM_LIMIT:
        return False, (
            "Grace sedang membatasi request untuk menghindari limit Gemini. "
            "Coba lagi sebentar ya."
        )

    request_timestamps.append(now)
    last_user_request[user_id] = now
    return True, None


async def _send_private_warning(user: discord.abc.User, text: str) -> None:
    try:
        await user.send(text)
    except (discord.Forbidden, discord.HTTPException):
        # Jika DM user tertutup, jangan kirim warning ke channel publik.
        return


async def _reply_and_store(
    message: discord.Message,
    conversation_key: str,
    user_prompt: str,
    reply_text: str,
) -> None:
    await message.reply(reply_text)
    await _store_conversation_turn(conversation_key, user_prompt, reply_text)


@client.event
async def on_ready() -> None:
    assert client.user is not None
    global conversation_history
    try:
        conversation_history = await asyncio.to_thread(_initialize_history_store_sync)
    except Exception as exc:
        print(f"Gagal menyiapkan storage history backend '{ACTIVE_HISTORY_BACKEND}': {exc}")
        if ACTIVE_HISTORY_BACKEND != "file":
            conversation_history = await asyncio.to_thread(_load_history_store_sync)
        else:
            conversation_history = {}
    print(f"Login sebagai {client.user} ({client.user.id}) | history_backend={ACTIVE_HISTORY_BACKEND}")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    # Jangan merespons pesan broadcast seperti @everyone/@here.
    if message.mention_everyone:
        return

    me = client.user
    if me is None:
        return

    if not should_respond(message, me):
        return

    prompt = normalize_prompt(message, me)
    conversation_key = _build_conversation_key(message)
    images, image_error = await _extract_images(message)
    if image_error:
        await _send_private_warning(message.author, image_error)
        return

    # Jika user hanya memanggil nama bot tanpa pertanyaan.
    if not prompt and not images:
        await _reply_and_store(message, conversation_key, BOT_NAME, IDENTITY_TEXT)
        return

    # Intro wajib ketika user bertanya identitas bot.
    if is_intro_question(prompt):
        await _reply_and_store(message, conversation_key, prompt, IDENTITY_TEXT)
        return

    if prompt and is_clear_history_command(prompt):
        await _clear_conversation_history(conversation_key)
        await message.reply("Riwayat percakapan kamu sudah saya hapus untuk konteks bot ini.")
        return

    if prompt and is_datetime_question(prompt):
        await _reply_and_store(message, conversation_key, prompt, build_datetime_reply())
        return

    if prompt and is_weather_question(prompt):
        weather_result = await get_weather_reply(prompt)
        if weather_result.is_private_warning or weather_result.is_error:
            await _send_private_warning(message.author, weather_result.text)
            return
        await _reply_and_store(message, conversation_key, prompt, weather_result.text)
        return

    if prompt and is_news_question(prompt):
        news_result = await get_news_reply(prompt)
        if news_result.is_private_warning or news_result.is_error:
            await _send_private_warning(message.author, news_result.text)
            return
        await _reply_and_store(message, conversation_key, prompt, news_result.text)
        return

    ok, warning_text = _allow_request(message.author.id)
    if not ok:
        await _send_private_warning(message.author, warning_text or "Grace sedang sibuk. Coba lagi ya.")
        return

    try:
        if images:
            result = await ask_ai_with_images(prompt, images)
        else:
            channel_context = await _build_recent_channel_context(message)
            result = await ask_ai(
                prompt,
                _build_history_context(conversation_key),
                channel_context,
            )
    except Exception as exc:
        print(f"Error saat memproses pertanyaan: {exc}")
        result = AIResult("Maaf, terjadi error saat memproses pertanyaan. Coba lagi sebentar ya.", is_error=True)

    # Proteksi tambahan: jika ada pesan limit dari jalur mana pun, paksa kirim private.
    if isinstance(result, str):
        result = AIResult(result)
    if _is_limit_message(result.text):
        result.is_private_warning = True

    if result.is_private_warning or result.is_error:
        await _send_private_warning(message.author, result.text)
        return

    try:
        stored_prompt = prompt.strip() or "Permintaan analisis gambar"
        if images and prompt.strip():
            stored_prompt = f"{prompt.strip()} [dengan gambar]"
        elif images:
            stored_prompt = "Permintaan analisis gambar"
        await _reply_and_store(message, conversation_key, stored_prompt, result.text)
    except discord.HTTPException:
        await _send_private_warning(
            message.author,
            "Maaf, saya gagal mengirim jawaban ke channel. Coba pertanyaan yang lebih singkat.",
        )


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN belum diisi di file .env")

    client.run(DISCORD_TOKEN)
