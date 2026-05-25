from __future__ import annotations

import asyncio
import functools
import html
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, Callable, Awaitable
from dataclasses import dataclass
from urllib.parse import quote_plus
from logging.handlers import RotatingFileHandler

import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from stremio_utils import find_subtitles
from stremio_utils import rename_subtitle_to_match


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads"))).expanduser().resolve()
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "cache_db" / "cache.db"))).expanduser().resolve()
LOG_DIR = BASE_DIR / "logs"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEFAULT_QUALITY = os.getenv("DEFAULT_QUALITY", "1080p").strip().lower() or "1080p"
KEEP_SUBTITLE_COPY = os.getenv("KEEP_SUBTITLE_COPY", "false").strip().lower() in {"1", "true", "yes", "on"}
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS = {
    int(part.strip())
    for part in ALLOWED_USERS_RAW.split(",")
    if part.strip().isdigit()
}

MOVIE_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v"}
VIDEO_LIMIT_BYTES = (2 * 1024**3) - (50 * 1024**2)
TWO_GB_BYTES = 2 * 1024**3
SEARCH_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
STREAM_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
USER_STATE: dict[int, dict[str, Any]] = {}
DOWNLOAD_LOCKS: dict[str, asyncio.Lock] = {}
SUB_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
COMPRESSION_QUEUE: asyncio.Queue | None = None


@dataclass
class CompressionTask:
    video_file: str
    dest_dir: str
    chat_id: int
    status_message_id: int
    download_id: int
    imdb_id: str
    season: int | None
    episode: int | None
    quality: str
    user_id: int
    query: str


TIMEOUT_MESSAGES = {
    "cinemeta": "⏳ Serviço lento, tente novamente em instantes.",
    "torrentio": "⏳ Torrentio não respondeu. Tente novamente.",
}


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / "bot.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            file_handler,
            logging.StreamHandler(),
        ],
    )


logger = logging.getLogger("stremio-bot")


def ensure_environment() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_quality_rank(quality: str | None) -> int:
    quality = (quality or "").lower()
    for index, item in enumerate(["2160p", "4k", "1080p", "720p", "480p", "360p"]):
        if item in quality:
            return index
    return 999


def format_size(value: int | None) -> str:
    if not value:
        return "? GB"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def truncate(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def safe_text(value: Any) -> str:
    return html.escape(str(value))


def extract_quality(text: str) -> str:
    lowered = text.lower()
    if "2160p" in lowered or "4k" in lowered:
        return "2160p"
    if "1080p" in lowered:
        return "1080p"
    if "720p" in lowered:
        return "720p"
    if "480p" in lowered:
        return "480p"
    if "360p" in lowered:
        return "360p"
    return "unknown"


def extract_source(stream: dict[str, Any]) -> str:
    title = stream.get("title", "") or ""
    match = re.search(r"⚙️\s*([^\n]+)", title)
    if match:
        return match.group(1).strip()
    name = stream.get("name", "") or ""
    first_line = name.splitlines()[0].strip() if name else ""
    return first_line or "Torrentio"


def extract_video_size(stream: dict[str, Any]) -> int | None:
    behavior = stream.get("behaviorHints", {}) or {}
    size = behavior.get("videoSize")
    if isinstance(size, int) and size > 0:
        return size
    title = stream.get("title", "") or ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)", title, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "GB":
        return int(value * 1024**3)
    return int(value * 1024**2)


def build_title_label(meta: dict[str, Any]) -> str:
    emoji = "📺" if meta.get("type") == "series" else "🎬"
    parts = [meta.get("name", "Título")]
    year = meta.get("year")
    if year:
        parts.append(str(year))
    director = meta.get("director") or []
    cast = meta.get("cast") or []
    person = director[0] if director else (cast[0] if cast else None)
    if person:
        parts.append(str(person))
    rating = meta.get("imdbRating")
    if rating:
        parts.append(f"⭐{rating}")
    return truncate(f"{emoji} {' • '.join(parts)}", 64)


def build_stream_label(stream: dict[str, Any]) -> str:
    quality = extract_quality(
        f"{stream.get('name', '')} {stream.get('title', '')} {stream.get('behaviorHints', {}).get('filename', '')}"
    )
    size = format_size(extract_video_size(stream))
    source = extract_source(stream)
    return truncate(f"⬇️ {quality} • {size} • {source}", 64)


def parse_allowed_users() -> set[int]:
    return ALLOWED_USERS


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not ALLOWED_USERS:
        return True
    return user.id in ALLOWED_USERS


def require_auth(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        if not is_authorized(update):
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Acesso não autorizado.")
            return None
        return await handler(update, context, *args, **kwargs)

    return wrapper


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    connection = get_db_connection()
    enqueued_compression = False
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                imdb_id TEXT NOT NULL,
                season INTEGER,
                episode INTEGER,
                quality TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                tg_file_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_imdb ON cache (imdb_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_created_at ON cache (created_at)")
        connection.commit()
    finally:
        connection.close()


def db_find_cache_row(
    imdb_id: str,
    season: int | None,
    episode: int | None,
    quality: str,
) -> sqlite3.Row | None:
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM cache
            WHERE imdb_id = ?
              AND quality = ?
              AND COALESCE(season, -1) = COALESCE(?, -1)
              AND COALESCE(episode, -1) = COALESCE(?, -1)
            ORDER BY id DESC
            LIMIT 1
            """,
            (imdb_id, quality, season, episode),
        )
        return cursor.fetchone()
    finally:
        connection.close()


def db_save_cache(
    query: str,
    imdb_id: str,
    season: int | None,
    episode: int | None,
    quality: str,
    file_path: str,
    file_size: int,
    tg_file_id: str | None = None,
) -> None:
    connection = get_db_connection()
    try:
        existing = db_find_cache_row(imdb_id, season, episode, quality)
        if existing:
            connection.execute(
                """
                UPDATE cache
                SET query = ?, file_path = ?, file_size = ?, tg_file_id = ?, created_at = ?
                WHERE id = ?
                """,
                (query, file_path, file_size, tg_file_id, now_iso(), existing["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO cache (query, imdb_id, season, episode, quality, file_path, file_size, tg_file_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (query, imdb_id, season, episode, quality, file_path, file_size, tg_file_id, now_iso()),
            )
        connection.commit()
    finally:
        connection.close()


def db_update_tg_file_id(cache_id: int, tg_file_id: str | None) -> None:
    connection = get_db_connection()
    try:
        connection.execute("UPDATE cache SET tg_file_id = ?, created_at = ? WHERE id = ?", (tg_file_id, now_iso(), cache_id))
        connection.commit()
    finally:
        connection.close()


def db_delete_cache_row(cache_id: int) -> None:
    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM cache WHERE id = ?", (cache_id,))
        connection.commit()
    finally:
        connection.close()


def db_list_recent_cache(limit: int = 20) -> list[sqlite3.Row]:
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM cache
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(cursor.fetchall())
    finally:
        connection.close()


def db_count_cache() -> int:
    connection = get_db_connection()
    try:
        cursor = connection.execute("SELECT COUNT(*) FROM cache")
        return int(cursor.fetchone()[0])
    finally:
        connection.close()


def db_insert_download(user_id: int, query: str, status: str) -> int:
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO downloads (user_id, query, status, started_at, finished_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (user_id, query, status, now_iso()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def db_update_download(download_id: int, status: str) -> None:
    connection = get_db_connection()
    try:
        finished = now_iso() if status in {"done", "failed"} else None
        connection.execute(
            "UPDATE downloads SET status = ?, finished_at = COALESCE(?, finished_at) WHERE id = ?",
            (status, finished, download_id),
        )
        connection.commit()
    finally:
        connection.close()


def db_cleanup_old_cache(days: int) -> int:
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    connection = get_db_connection()
    try:
        cursor = connection.execute("SELECT id, file_path FROM cache WHERE created_at < ?", (threshold,))
        rows = list(cursor.fetchall())
        for row in rows:
            file_path = Path(row["file_path"])
            if file_path.exists():
                try:
                    if file_path.is_file():
                        file_path.unlink()
                    else:
                        shutil.rmtree(file_path, ignore_errors=True)
                except OSError:
                    logger.exception("Falha ao remover arquivo antigo %s", file_path)
            connection.execute("DELETE FROM cache WHERE id = ?", (row["id"],))
        connection.commit()
        return len(rows)
    finally:
        connection.close()


def db_clear_stale_downloads() -> None:
    connection = get_db_connection()
    try:
        connection.execute("UPDATE downloads SET status = 'failed', finished_at = ? WHERE status = 'downloading'", (now_iso(),))
        connection.commit()
    finally:
        connection.close()


def download_lock(key: str) -> asyncio.Lock:
    lock = DOWNLOAD_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        DOWNLOAD_LOCKS[key] = lock
    return lock


def cache_search_results(results: list[dict[str, Any]]) -> str:
    token = token_urlsafe(6)
    SEARCH_CACHE[token] = (datetime.now(timezone.utc).timestamp(), results)
    return token


def cache_stream_results(results: list[dict[str, Any]]) -> str:
    token = token_urlsafe(6)
    STREAM_CACHE[token] = (datetime.now(timezone.utc).timestamp(), results)
    return token


def cache_sub_results(data: dict[str, Any]) -> str:
    token = token_urlsafe(6)
    SUB_CACHE[token] = (datetime.now(timezone.utc).timestamp(), data)
    return token


def get_cached_results(cache: dict[str, tuple[float, list[dict[str, Any]]]], token: str, ttl_seconds: int = 1800) -> list[dict[str, Any]] | None:
    item = cache.get(token)
    if not item:
        return None
    timestamp, results = item
    if datetime.now(timezone.utc).timestamp() - timestamp > ttl_seconds:
        cache.pop(token, None)
        return None
    return results


async def http_get_json(url: str, timeout_seconds: float, retries: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    timeout = httpx.Timeout(timeout_seconds)
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("Falha inesperada na requisição HTTP")


async def search_cinemeta(query: str) -> list[dict[str, Any]]:
    encoded = quote_plus(query)
    urls = [
        f"https://v3-cinemeta.strem.io/catalog/movie/top/search={encoded}.json",
        f"https://v3-cinemeta.strem.io/catalog/series/top/search={encoded}.json",
    ]
    tasks = [http_get_json(url, timeout_seconds=15.0) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    metas: list[dict[str, Any]] = []
    timeout_seen = False
    for result in results:
        if isinstance(result, Exception):
            if isinstance(result, httpx.TimeoutException):
                timeout_seen = True
            logger.warning("Erro na busca Cinemeta: %s", result)
            continue
        metas.extend(result.get("metas", []) or [])
    unique: dict[str, dict[str, Any]] = {}
    for meta in metas:
        key = f"{meta.get('type', '')}:{meta.get('id', '')}"
        unique[key] = meta
    final_results = list(unique.values())
    final_results.sort(key=lambda item: (item.get("type") != "movie", item.get("year", "0"), item.get("name", "")))
    if not final_results and timeout_seen:
        raise httpx.TimeoutException(TIMEOUT_MESSAGES["cinemeta"])
    return final_results


async def fetch_streams(media_type: str, imdb_id: str, season: int | None = None, episode: int | None = None) -> list[dict[str, Any]]:
    if media_type == "series":
        if season is None or episode is None:
            return []
        endpoint = f"https://torrentio.strem.fun/stream/series/{imdb_id}:{season}:{episode}.json"
    else:
        endpoint = f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json"
    result = await http_get_json(endpoint, timeout_seconds=20.0)
    streams = result.get("streams", []) or []
    valid_streams: list[dict[str, Any]] = []
    for stream in streams:
        if stream.get("infoHash") or stream.get("url"):
            valid_streams.append(stream)
    if not valid_streams:
        return []
    preferred = [stream for stream in valid_streams if extract_quality(f"{stream.get('name', '')} {stream.get('title', '')} {stream.get('behaviorHints', {}).get('filename', '')}") == DEFAULT_QUALITY]
    filtered = preferred or valid_streams
    filtered.sort(key=lambda item: (parse_quality_rank(extract_quality(f"{item.get('name', '')} {item.get('title', '')} {item.get('behaviorHints', {}).get('filename', '')}")), -(extract_video_size(item) or 0)))
    return filtered[:10]


async def run_aria2c(
    source: str,
    destination: Path,
    select_file: int | None = None,
) -> None:
    if shutil.which("aria2c") is None:
        raise FileNotFoundError("aria2c não instalado. Rode: sudo apt install aria2")
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        "aria2c",
        "--enable-rpc=false",
        "--seed-time=0",
        "--max-connection-per-server=4",
        "--bt-stop-timeout=300",
        "--file-allocation=none",
        "--continue=true",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--quiet=true",
        "--console-log-level=warn",
        "--summary-interval=0",
        f"--dir={str(destination)}",
    ]
    if select_file is not None:
        command.append(f"--select-file={select_file}")
    command.append(source)
    logger.info("Executando aria2c: %s", " ".join(command[:-1] + ["<source>"]))
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=300)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise TimeoutError("Torrent sem seeders. Tente outro stream.") from exc
    if process.returncode != 0:
        stderr = ""
        if process.stderr:
            stderr = (await process.stderr.read()).decode("utf-8", errors="ignore")
        raise RuntimeError(stderr.strip() or f"aria2c falhou com código {process.returncode}")
    


def locate_video_file(directory: Path) -> Path:
    rar_files = list(directory.rglob("*.rar"))
    if rar_files:
        raise RuntimeError("Torrent veio compactado (.rar). Tente outro stream.")
    video_files = [path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in MOVIE_EXTENSIONS]
    if not video_files:
        raise RuntimeError("Arquivo de vídeo não encontrado após download.")
    return max(video_files, key=lambda item: item.stat().st_size)


def build_magnet(stream: dict[str, Any]) -> str:
    info_hash = stream.get("infoHash")
    if not info_hash:
        return stream.get("url", "")
    dn = quote_plus(stream.get("name", "torrent"))
    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"
    for tracker in stream.get("sources", []) or []:
        if isinstance(tracker, str) and tracker.startswith("tracker:"):
            magnet += f"&tr={quote_plus(tracker.removeprefix('tracker:'))}"
    return magnet


async def compress_video(input_path: Path, target_dir: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg não instalado. Rode: sudo apt install ffmpeg")
    target_dir.mkdir(parents=True, exist_ok=True)
    output = target_dir / (input_path.stem + "_compressed.mp4")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=3600)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise TimeoutError("Compressão excedeu o tempo limite") from exc
    if process.returncode != 0:
        stderr = ""
        if process.stderr:
            stderr = (await process.stderr.read()).decode("utf-8", errors="ignore")
        raise RuntimeError(stderr.strip() or f"ffmpeg falhou com código {process.returncode}")
    return output


async def compression_worker(bot) -> None:
    """Worker que processa compressões enfileiradas sequencialmente."""
    global COMPRESSION_QUEUE
    if COMPRESSION_QUEUE is None:
        COMPRESSION_QUEUE = asyncio.Queue()
    queue = COMPRESSION_QUEUE
    while True:
        task: CompressionTask = await queue.get()
        try:
            # notify user
            try:
                await bot.edit_message_text(chat_id=task.chat_id, message_id=task.status_message_id, text="🛠️ Compressão em andamento...")
            except Exception:
                pass
            try:
                compressed = await compress_video(Path(task.video_file), Path(task.dest_dir))
                compressed_size = compressed.stat().st_size
                if compressed_size <= VIDEO_LIMIT_BYTES:
                    # update cache to point to compressed file
                    db_save_cache(task.query, task.imdb_id, task.season, task.episode, task.quality, str(compressed), compressed_size, None)
                    try:
                        await bot.edit_message_text(chat_id=task.chat_id, message_id=task.status_message_id, text="📤 Enviando vídeo comprimido no Telegram...")
                    except Exception:
                        pass
                    file_id, sent = await maybe_send_video(bot, task.chat_id, compressed, None)
                    if sent and file_id:
                        cache_row = db_find_cache_row(task.imdb_id, task.season, task.episode, task.quality)
                        if cache_row:
                            db_update_tg_file_id(int(cache_row["id"]), file_id)
                    await bot.send_message(chat_id=task.chat_id, text=f"✅ Compressão e envio concluídos: {compressed.name}")
                    db_update_download(task.download_id, "done")
                else:
                    # still too big
                    db_save_cache(task.query, task.imdb_id, task.season, task.episode, task.quality, task.video_file, Path(task.video_file).stat().st_size, None)
                    await bot.send_message(chat_id=task.chat_id, text=("⚠️ Arquivo permanece acima do limite mesmo após compressão. "
                                                                          f"Arquivo salvo em: {task.video_file}"))
                    db_update_download(task.download_id, "done")
            except FileNotFoundError as exc:
                await bot.send_message(chat_id=task.chat_id, text=f"❌ {exc}")
                db_update_download(task.download_id, "failed")
            except Exception:
                logger.exception("Erro na compressão em background")
                await bot.send_message(chat_id=task.chat_id, text="❌ Falha na compressão em background.")
                db_update_download(task.download_id, "failed")
        finally:
            # release locks for this content and user
            try:
                content_lock = download_lock(f"{task.imdb_id}:{task.season or 0}:{task.episode or 0}:{task.quality}")
                if content_lock.locked():
                    try:
                        content_lock.release()
                    except RuntimeError:
                        pass
            except Exception:
                pass
            try:
                user_lock = download_lock(f"user:{task.user_id}")
                if user_lock.locked():
                    try:
                        user_lock.release()
                    except RuntimeError:
                        pass
            except Exception:
                pass
            queue.task_done()


def get_subtitle_files(directory: Path) -> list[Path]:
    files = [p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in {".srt", ".ass"}]
    files.sort(key=lambda p: p.name.lower())
    return files


async def sub_selection_watchdog(token: str, timeout_seconds: int, bot) -> None:
    await asyncio.sleep(timeout_seconds)
    data = get_cached_results(SUB_CACHE, token)
    if not data:
        return
    # proceed without subtitle
    try:
        video_file = Path(data.get("video_file"))
        chat_id = data.get("chat_id")
        download_id = data.get("download_id")
        user_id = data.get("user_id")
        file_id, sent = await maybe_send_video(bot, chat_id, video_file, None)
        if sent and file_id:
            # update DB tg_file_id
            cache_row = db_find_cache_row(data.get("imdb_id", ""), data.get("season"), data.get("episode"), data.get("quality"))
            if cache_row:
                db_update_tg_file_id(int(cache_row["id"]), file_id)
        db_update_download(download_id, "done")
    except Exception:
        logger.exception("Falha ao enviar vídeo após watchdog de legenda")
        db_update_download(download_id, "failed")
    finally:
        # release user lock
        user_lock = download_lock(f"user:{user_id}")
        if user_lock.locked():
            try:
                user_lock.release()
            except RuntimeError:
                pass
        SUB_CACHE.pop(token, None)


async def maybe_send_video(bot, chat_id: int, file_path: Path, tg_file_id: str | None) -> tuple[str | None, bool]:
    try:
        if tg_file_id:
            message = await bot.send_video(
                chat_id=chat_id,
                video=tg_file_id,
                supports_streaming=True,
                write_timeout=600,
                read_timeout=600,
            )
        else:
            with file_path.open("rb") as file_handle:
                message = await bot.send_video(
                    chat_id=chat_id,
                    video=file_handle,
                    supports_streaming=True,
                    write_timeout=600,
                    read_timeout=600,
                )
        file_id = None
        if message.video:
            file_id = message.video.file_id
        return file_id, True
    except BadRequest as exc:
        if tg_file_id and "FILE_REFERENCE_EXPIRED" in str(exc).upper():
            return None, False
        raise


def should_keep_subtitle_copy() -> bool:
    return os.getenv("KEEP_SUBTITLE_COPY", "false").strip().lower() in {"1", "true", "yes", "on"}


async def send_subtitle_document(bot, chat_id: int, video_path: Path, subtitle_path: Path, keep_copy: bool | None = None) -> Path:
    renamed = rename_subtitle_to_match(video_path, subtitle_path)
    try:
        await bot.send_document(chat_id=chat_id, document=renamed)
    finally:
        if keep_copy is None:
            keep_copy = should_keep_subtitle_copy()
        if not keep_copy:
            try:
                Path(renamed).unlink(missing_ok=True)
            except Exception:
                logger.exception("Falha ao remover legenda temporária %s", renamed)
    return Path(renamed)


def build_search_keyboard(token: str, metas: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for index, meta in enumerate(metas[:10]):
        rows.append([InlineKeyboardButton(build_title_label(meta), callback_data=f"sel|{token}|{index}")])
    return InlineKeyboardMarkup(rows)


def build_season_keyboard(imdb_id: str, seasons: int = 10) -> InlineKeyboardMarkup:
    buttons = []
    row: list[InlineKeyboardButton] = []
    for season in range(1, seasons + 1):
        row.append(InlineKeyboardButton(f"Temporada {season}", callback_data=f"sea|{imdb_id}|{season}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("↩️ Voltar", callback_data="back|search")])
    return InlineKeyboardMarkup(buttons)


def build_episode_keyboard(imdb_id: str, season: int, episodes: int = 24) -> InlineKeyboardMarkup:
    buttons = []
    row: list[InlineKeyboardButton] = []
    for episode in range(1, episodes + 1):
        row.append(InlineKeyboardButton(str(episode), callback_data=f"epi|{imdb_id}|{season}|{episode}"))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("↩️ Voltar", callback_data=f"back|season|{imdb_id}")])
    return InlineKeyboardMarkup(buttons)


def build_stream_keyboard(token: str, streams: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for index, stream in enumerate(streams[:10]):
        rows.append([InlineKeyboardButton(build_stream_label(stream), callback_data=f"dl|{token}|{index}")])
    rows.append([InlineKeyboardButton("↩️ Nova busca", callback_data="back|search")])
    return InlineKeyboardMarkup(rows)


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    message = update.effective_message
    if not message:
        return
    query = query.strip()
    if not query:
        await message.reply_text("Use /buscar <título> ou envie o nome do filme/série em texto livre.")
        return
    try:
        metas = await search_cinemeta(query)
    except httpx.TimeoutException:
        await message.reply_text(TIMEOUT_MESSAGES["cinemeta"])
        return
    except Exception as exc:
        logger.exception("Falha na busca Cinemeta")
        await message.reply_text(f"❌ Erro na busca: {exc}")
        return
    if not metas:
        await message.reply_text("😕 Nenhum resultado. Tente buscar em inglês.")
        return
    token = cache_search_results(metas)
    USER_STATE.setdefault(message.chat_id, {})["search_token"] = token
    await message.reply_text(
        "Selecione um resultado:",
        reply_markup=build_search_keyboard(token, metas),
    )


async def send_stream_options(
    query: Update,
    context: ContextTypes.DEFAULT_TYPE,
    meta: dict[str, Any],
    season: int | None = None,
    episode: int | None = None,
) -> None:
    message = query.effective_message
    if not message:
        return
    try:
        streams = await fetch_streams(meta.get("type", "movie"), meta.get("id", ""), season=season, episode=episode)
    except httpx.TimeoutException:
        await message.reply_text(TIMEOUT_MESSAGES["torrentio"])
        return
    except Exception as exc:
        logger.exception("Falha ao buscar streams")
        await message.reply_text(f"❌ Erro ao buscar streams: {exc}")
        return
    if not streams:
        await message.reply_text("😕 Sem streams disponíveis agora. Tente mais tarde.")
        return
    token = cache_stream_results(streams)
    USER_STATE.setdefault(message.chat_id, {})["stream_token"] = token
    label = build_title_label(meta)
    if season is not None and episode is not None:
        label = f"{label} - S{season:02d}E{episode:02d}"
    await message.reply_text(
        f"Streams para {label}",
        reply_markup=build_stream_keyboard(token, streams),
    )


async def send_cached_video(context: ContextTypes.DEFAULT_TYPE, message, row: sqlite3.Row) -> None:
    chat_id = message.chat_id
    file_path = Path(row["file_path"])
    if not file_path.exists():
        db_delete_cache_row(int(row["id"]))
        await message.reply_text("⚠️ Cache local inválido. Baixando novamente.")
        return
    if int(row["file_size"]) > VIDEO_LIMIT_BYTES:
        await message.reply_text(
            "⚠️ Arquivo acima do limite da Bot API. Envie manualmente a partir do caminho local:\n"
            f"{file_path}"
        )
        return
    file_id = row["tg_file_id"]
    try:
        new_file_id, sent = await maybe_send_video(context.bot, chat_id, file_path, file_id)
        if not sent and file_id:
            db_update_tg_file_id(int(row["id"]), None)
            new_file_id, sent = await maybe_send_video(context.bot, chat_id, file_path, None)
        if sent and new_file_id and new_file_id != file_id:
            db_update_tg_file_id(int(row["id"]), new_file_id)
        return
    except BadRequest:
        if file_id:
            db_update_tg_file_id(int(row["id"]), None)
            new_file_id, sent = await maybe_send_video(context.bot, chat_id, file_path, None)
            if sent and new_file_id:
                db_update_tg_file_id(int(row["id"]), new_file_id)
            return
        raise


async def download_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    meta: dict[str, Any],
    stream: dict[str, Any],
    season: int | None = None,
    episode: int | None = None,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    imdb_id = str(meta.get("id", ""))
    quality = extract_quality(
        f"{stream.get('name', '')} {stream.get('title', '')} {stream.get('behaviorHints', {}).get('filename', '')}"
    )
    cache_row = db_find_cache_row(imdb_id, season, episode, quality)
    if cache_row:
        await send_cached_video(context, message, cache_row)
        return
    # enforce single active download per user
    user_lock_key = f"user:{user.id}"
    user_lock = download_lock(user_lock_key)
    if user_lock.locked():
        await message.reply_text("⏳ Você já tem um download em andamento. Aguarde terminar antes de iniciar outro.")
        return
    await user_lock.acquire()
    release_user_lock = True
    content_key = f"{imdb_id}:{season or 0}:{episode or 0}:{quality}"
    lock = download_lock(content_key)
    if lock.locked():
        await message.reply_text("⏳ Este conteúdo já está sendo baixado. Você será notificado quando terminar.")
    await lock.acquire()
    download_id = db_insert_download(user.id, meta.get("name", imdb_id), "downloading")
    try:
        status_message = await message.reply_text("⬇️ Baixando, aguarde...")
        dest_dir = DOWNLOAD_DIR / re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{imdb_id}_{season or 'movie'}_{episode or 'full'}_{quality}")
        source = build_magnet(stream)
        select_file = None
        if meta.get("type") == "series" and stream.get("fileIdx") is not None:
            try:
                select_file = int(stream.get("fileIdx")) + 1
            except (TypeError, ValueError):
                select_file = None
        await run_aria2c(source, dest_dir, select_file=select_file)
        video_file = locate_video_file(dest_dir)
        file_size = video_file.stat().st_size
        # se o arquivo estiver maior que 2 GB, enfileirar compressão automática e não bloquear o handler
        if file_size > TWO_GB_BYTES:
            # salvar cache provisório apontando para o arquivo original
            db_save_cache(meta.get("name", imdb_id), imdb_id, season, episode, quality, str(video_file), file_size, None)
            # prepare compression task
            global COMPRESSION_QUEUE
            if COMPRESSION_QUEUE is None:
                COMPRESSION_QUEUE = asyncio.Queue()
            task = CompressionTask(
                video_file=str(video_file),
                dest_dir=str(dest_dir),
                chat_id=message.chat_id,
                status_message_id=status_message.message_id,
                download_id=download_id,
                imdb_id=imdb_id,
                season=season,
                episode=episode,
                quality=quality,
                user_id=user.id,
                query=meta.get("name", imdb_id),
            )
            await COMPRESSION_QUEUE.put(task)
            enqueued_compression = True
            release_user_lock = False
            await status_message.edit_text("🛠️ Arquivo grande; compressão enfileirada. Você será notificado quando terminar.")
            return
        db_save_cache(meta.get("name", imdb_id), imdb_id, season, episode, quality, str(video_file), file_size, None)
        # detect subtitle files (prioritize pt-br/pt)
        subtitle_files = find_subtitles(dest_dir)
        if subtitle_files:
            # check environment preference for automatic subtitle selection
            pref = os.getenv("SUB_LANG", "pt-br,pt") or "pt-br,pt"
            preferred = [p.strip().lower() for p in pref.split(",") if p.strip()]
            chosen_idx = None
            for lang in preferred:
                for idx, info in enumerate(subtitle_files):
                    if info.get("lang") == lang:
                        chosen_idx = idx
                        break
                if chosen_idx is not None:
                    break
            if chosen_idx is not None:
                # automatic send preferred subtitle (rename to match video)
                sub_info = subtitle_files[chosen_idx]
                sub_path = Path(sub_info.get("path"))
                try:
                    renamed = await send_subtitle_document(context.bot, message.chat_id, video_file, sub_path)
                    await status_message.edit_text(f"📎 Enviando legenda preferida: {renamed.name}")
                except Exception:
                    logger.exception("Falha ao enviar legenda preferida")
                # continue to send video afterwards
            else:
                token = cache_sub_results({
                    "video_file": str(video_file),
                    "subtitle_files": subtitle_files,
                    "chat_id": message.chat_id,
                    "download_id": download_id,
                    "imdb_id": imdb_id,
                    "season": season,
                    "episode": episode,
                    "quality": quality,
                    "user_id": user.id,
                })
                # build keyboard with language hint
                rows = []
                for idx, info in enumerate(subtitle_files[:10]):
                    label = f"{info.get('name')} • {info.get('lang')}"
                    rows.append([InlineKeyboardButton(label, callback_data=f"sub|{token}|{idx}")])
                rows.append([InlineKeyboardButton("⛔ Sem legenda", callback_data=f"sub|{token}|-1")])
                await status_message.edit_text(
                    "📝 Legendas encontradas. Escolha qual legenda enviar junto (ou 'Sem legenda').",
                    reply_markup=InlineKeyboardMarkup(rows),
                )
                # keep user lock until selection finished by callback or watchdog
                release_user_lock = False
                # start watchdog to auto-continue after 10 minutes
                asyncio.create_task(sub_selection_watchdog(token, 600, context.bot))
                return
            # continue normally when automatic subtitle sent
        await status_message.edit_text("📤 Enviando vídeo no Telegram...")
        file_id, sent = await maybe_send_video(context.bot, message.chat_id, video_file, None)
        if not sent:
            await status_message.edit_text("⚠️ Reenviando após expiração do file_id...")
            file_id, sent = await maybe_send_video(context.bot, message.chat_id, video_file, None)
        if sent and file_id:
            cache_row = db_find_cache_row(imdb_id, season, episode, quality)
            if cache_row:
                db_update_tg_file_id(int(cache_row["id"]), file_id)
        if sent:
            await status_message.edit_text(f"✅ Enviado com sucesso: {video_file.name}")
        db_update_download(download_id, "done")
    except FileNotFoundError as exc:
        db_update_download(download_id, "failed")
        await message.reply_text(f"❌ {exc}")
    except TimeoutError as exc:
        db_update_download(download_id, "failed")
        await message.reply_text(f"⚠️ {exc}")
    except OSError:
        db_update_download(download_id, "failed")
        await message.reply_text("💾 Disco cheio! Libere espaço e tente novamente.")
        logger.exception("Erro de sistema ao baixar/enviar conteúdo")
    except RuntimeError as exc:
        db_update_download(download_id, "failed")
        await message.reply_text(f"❌ {exc}")
    except TelegramError as exc:
        db_update_download(download_id, "failed")
        logger.exception("Falha no envio para Telegram")
        await message.reply_text(f"❌ Falha no envio. Arquivo salvo em: {dest_dir}")
        raise exc
    finally:
        if not enqueued_compression and lock.locked():
            lock.release()
        if release_user_lock and user_lock.locked():
            user_lock.release()
@require_auth
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    text = (
        "Stremio Bot ativo.\n\n"
        "Comandos disponíveis:\n"
        "• /buscar <título>\n"
        "• /cache\n"
        "• /status\n"
        "• /limpar [dias]\n\n"
        "Você também pode enviar o título em texto livre."
    )
    await message.reply_text(text)


@require_auth
async def handle_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    await perform_search(update, context, query)


@require_auth
async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return
    if message.text.startswith("/"):
        return
    await perform_search(update, context, message.text)


@require_auth
async def handle_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    rows = db_list_recent_cache(20)
    if not rows:
        await message.reply_text("Cache vazio.")
        return
    lines = ["Últimos itens no cache:"]
    for row in rows:
        season = row["season"] if row["season"] is not None else "-"
        episode = row["episode"] if row["episode"] is not None else "-"
        file_state = "tg_file_id" if row["tg_file_id"] else "arquivo local"
        lines.append(
            f"• {row['query']} | {row['quality']} | S{season}E{episode} | {format_size(row['file_size'])} | {file_state}"
        )
    await message.reply_text("\n".join(lines))


@require_auth
async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    disk = shutil.disk_usage(DOWNLOAD_DIR)
    text = (
        f"Espaço em disco:\n"
        f"• Livre: {format_size(disk.free)}\n"
        f"• Usado: {format_size(disk.used)}\n"
        f"• Total: {format_size(disk.total)}\n\n"
        f"Itens no cache: {db_count_cache()}"
    )
    await message.reply_text(text)


@require_auth
async def handle_clean_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    days = 30
    if context.args:
        try:
            days = max(1, int(context.args[0]))
        except ValueError:
            pass
    removed = db_cleanup_old_cache(days)
    await message.reply_text(f"🧹 Limpeza concluída. {removed} item(ns) removido(s) com mais de {days} dia(s).")


@require_auth
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        await query.answer()
    except BadRequest:
        return
    parts = query.data.split("|")
    if not parts:
        return
    action = parts[0]
    chat_state = USER_STATE.setdefault(query.message.chat_id if query.message else 0, {})
    try:
        if action == "sel" and len(parts) == 3:
            token, index_raw = parts[1], parts[2]
            metas = get_cached_results(SEARCH_CACHE, token)
            if metas is None:
                await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                return
            meta = metas[int(index_raw)]
            chat_state["selected_meta"] = meta
            if meta.get("type") == "series":
                await query.message.edit_text(
                    f"{build_title_label(meta)}\nSelecione a temporada:",
                    reply_markup=build_season_keyboard(str(meta.get("id", ""))),
                )
                return
            await query.message.edit_text(
                f"{build_title_label(meta)}\nBuscando streams...",
            )
            await send_stream_options(update, context, meta)
            return
        if action == "sea" and len(parts) == 3:
            imdb_id, season_raw = parts[1], parts[2]
            meta = chat_state.get("selected_meta")
            if not meta:
                await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                return
            season = int(season_raw)
            chat_state["selected_season"] = season
            await query.message.edit_text(
                f"{build_title_label(meta)}\nTemporada {season}: escolha o episódio.",
                reply_markup=build_episode_keyboard(imdb_id, season),
            )
            return
        if action == "epi" and len(parts) == 4:
            imdb_id, season_raw, episode_raw = parts[1], parts[2], parts[3]
            meta = chat_state.get("selected_meta")
            if not meta:
                await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                return
            season = int(season_raw)
            episode = int(episode_raw)
            chat_state["selected_season"] = season
            chat_state["selected_episode"] = episode
            await query.message.edit_text(
                f"{build_title_label(meta)}\nBuscando streams da T{season:02d}E{episode:02d}...",
            )
            await send_stream_options(update, context, meta, season=season, episode=episode)
            return
        if action == "dl" and len(parts) == 3:
            token, index_raw = parts[1], parts[2]
            streams = get_cached_results(STREAM_CACHE, token)
            if streams is None:
                await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                return
            meta = chat_state.get("selected_meta")
            if not meta:
                await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                return
            stream = streams[int(index_raw)]
            season = chat_state.get("selected_season")
            episode = chat_state.get("selected_episode")
            await download_and_send(update, context, meta, stream, season=season, episode=episode)
            return
        if action == "sub" and len(parts) == 3:
            token = parts[1]
            try:
                idx = int(parts[2])
            except (TypeError, ValueError):
                await query.message.reply_text("❌ Opção inválida.")
                return
            data = get_cached_results(SUB_CACHE, token)
            if data is None:
                await query.message.reply_text("❌ Erro interno. A seleção expirou.")
                return
            chat_id = data.get("chat_id")
            download_id = data.get("download_id")
            user_id = data.get("user_id")
            video_path = Path(data.get("video_file"))
            subtitle_files = data.get("subtitle_files", [])
            try:
                if idx >= 0 and idx < len(subtitle_files):
                    sub_info = subtitle_files[idx]
                    sub_path = Path(sub_info.get("path"))
                    await query.message.reply_text(f"📎 Enviando legenda: {sub_path.name} ({sub_info.get('lang')})")
                    try:
                        renamed = await send_subtitle_document(context.bot, chat_id, video_path, sub_path)
                        logger.info("Legenda enviada: %s", renamed)
                    except Exception:
                        logger.exception("Erro ao enviar legenda via callback")
                await query.message.edit_text("📤 Enviando vídeo no Telegram...")
                file_id, sent = await maybe_send_video(context.bot, chat_id, video_path, None)
                if sent and file_id:
                    cache_row = db_find_cache_row(data.get("imdb_id", ""), data.get("season"), data.get("episode"), data.get("quality"))
                    if cache_row:
                        db_update_tg_file_id(int(cache_row["id"]), file_id)
                db_update_download(download_id, "done")
            except BadRequest:
                db_update_download(download_id, "failed")
                await query.message.reply_text(f"❌ Falha no envio. Arquivo salvo em: {video_path}")
            except Exception:
                logger.exception("Erro ao enviar vídeo/legenda via callback")
                db_update_download(download_id, "failed")
                await query.message.reply_text("❌ Falha no envio.")
            finally:
                # release user lock
                user_lock = download_lock(f"user:{user_id}")
                if user_lock.locked():
                    try:
                        user_lock.release()
                    except RuntimeError:
                        pass
                SUB_CACHE.pop(token, None)
            return
        if action == "back" and len(parts) >= 2:
            target = parts[1]
            if target == "search":
                await query.message.edit_text("Envie um título para buscar.")
                return
            if target == "season" and len(parts) == 3:
                meta = chat_state.get("selected_meta")
                if not meta:
                    await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
                    return
                await query.message.edit_text(
                    f"{build_title_label(meta)}\nSelecione a temporada:",
                    reply_markup=build_season_keyboard(parts[2]),
                )
                return
    except IndexError:
        await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
    except (ValueError, json.JSONDecodeError):
        await query.message.reply_text("❌ Erro interno. Tente a busca novamente.")
    except BadRequest as exc:
        if "query is too old" in str(exc).lower():
            return
        raise


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Erro não tratado", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("❌ Erro interno. Tente novamente.")


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN não configurado no ambiente.")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("buscar", handle_search_command))
    application.add_handler(CommandHandler("cache", handle_cache_command))
    application.add_handler(CommandHandler("status", handle_status_command))
    application.add_handler(CommandHandler("limpar", handle_clean_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))
    application.add_error_handler(error_handler)
    # iniciar worker de compressão em background
    global COMPRESSION_QUEUE
    COMPRESSION_QUEUE = asyncio.Queue()
    try:
        application.create_task(compression_worker(application.bot))
    except Exception:
        # em alguns contextos a criação da task pode ser adiada
        pass
    return application


def main() -> None:
    load_dotenv()
    setup_logging()
    ensure_environment()
    init_db()
    db_clear_stale_downloads()
    logger.info("Iniciando bot com %d usuário(s) autorizado(s)", len(parse_allowed_users()))
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()