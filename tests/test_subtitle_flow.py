import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Ensure project root available for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Stub dotenv so importing bot works even when python-dotenv is absent in the test env.
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

telegram_stub = types.ModuleType("telegram")
telegram_stub.InlineKeyboardButton = object
telegram_stub.InlineKeyboardMarkup = object
telegram_stub.Update = object

telegram_constants_stub = types.ModuleType("telegram.constants")
telegram_constants_stub.ParseMode = object

telegram_error_stub = types.ModuleType("telegram.error")
telegram_error_stub.BadRequest = Exception
telegram_error_stub.TelegramError = Exception

telegram_ext_stub = types.ModuleType("telegram.ext")
telegram_ext_stub.Application = type("Application", (), {"builder": staticmethod(lambda: type("Builder", (), {"token": staticmethod(lambda *args, **kwargs: type("App", (), {"build": staticmethod(lambda: None)})())})())})
telegram_ext_stub.CallbackQueryHandler = object
telegram_ext_stub.CommandHandler = object
telegram_ext_stub.ContextTypes = type("ContextTypes", (), {"DEFAULT_TYPE": object()})
telegram_ext_stub.MessageHandler = object
telegram_ext_stub.filters = types.SimpleNamespace(TEXT=object(), COMMAND=object())

sys.modules.setdefault("telegram", telegram_stub)
sys.modules.setdefault("telegram.constants", telegram_constants_stub)
sys.modules.setdefault("telegram.error", telegram_error_stub)
sys.modules.setdefault("telegram.ext", telegram_ext_stub)

from bot import send_subtitle_document


def test_send_subtitle_document_removes_copy(tmp_path: Path, monkeypatch):
    video = tmp_path / "Movie.Name.mkv"
    video.write_text("video")
    subtitle = tmp_path / "movie.pt.srt"
    subtitle.write_text("subtitle")
    bot_mock = AsyncMock()
    bot_mock.send_document = AsyncMock(return_value=None)

    monkeypatch.setenv("KEEP_SUBTITLE_COPY", "false")

    renamed = asyncio.run(send_subtitle_document(bot_mock, 123, video, subtitle))

    bot_mock.send_document.assert_awaited_once()
    sent_kwargs = bot_mock.send_document.await_args.kwargs
    assert sent_kwargs["chat_id"] == 123
    assert Path(sent_kwargs["document"]).name.startswith("Movie.Name")
    assert renamed.exists() is False


def test_send_subtitle_document_keeps_copy_when_enabled(tmp_path: Path, monkeypatch):
    video = tmp_path / "Movie.Name.mkv"
    video.write_text("video")
    subtitle = tmp_path / "movie.pt.srt"
    subtitle.write_text("subtitle")
    bot_mock = AsyncMock()
    bot_mock.send_document = AsyncMock(return_value=None)

    monkeypatch.setenv("KEEP_SUBTITLE_COPY", "true")

    renamed = asyncio.run(send_subtitle_document(bot_mock, 123, video, subtitle))

    bot_mock.send_document.assert_awaited_once()
    assert renamed.exists() is True
