import logging
import logging.handlers
from pathlib import Path

from config.env import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_LOGGER_PREFIXES = (
    "__main__",
    "main",
    "abstract",
    "classes",
    "cogs",
    "cli_args",
    "config",
    "embeds",
    "services",
    "views",
)
DEFAULT_APP_LOG_FILE = "discord.log"
DEFAULT_DEPENDENCY_LOG_FILE = "discord.deps.log"
DEFAULT_APP_LOG_LEVEL = "INFO"
DEFAULT_LIBRARY_LOG_LEVEL = "WARNING"
DEFAULT_CONSOLE_LOG_LEVEL = "INFO"
DEFAULT_LOG_MAX_BYTES = 32 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5


def _parse_log_level(raw_value: str, default: str) -> int:
    raw_value = str(raw_value or default).strip().upper()
    parsed_level = logging._nameToLevel.get(raw_value)
    if parsed_level is not None:
        return parsed_level
    return logging._nameToLevel.get(default.upper(), logging.INFO)


def _parse_positive_int(raw_value: int, default: int) -> int:
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return default


def _is_project_path(pathname: str) -> bool:
    if not pathname:
        return False

    try:
        resolved_path = Path(pathname).resolve()
    except (OSError, RuntimeError):
        return False

    try:
        relative_path = resolved_path.relative_to(PROJECT_ROOT)
    except ValueError:
        return False

    return ".venv" not in relative_path.parts


def _is_app_record(record: logging.LogRecord) -> bool:
    if _is_project_path(getattr(record, "pathname", "")):
        return True

    logger_name = getattr(record, "name", "") or ""
    return any(
        logger_name == prefix or logger_name.startswith(f"{prefix}.")
        for prefix in APP_LOGGER_PREFIXES
    )


def _record_source(record: logging.LogRecord) -> str:
    if _is_app_record(record):
        return "BOT"
    if record.name == "discord" or record.name.startswith("discord."):
        return "DISCORD"
    return "LIB"


class AppOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _is_app_record(record)


class DependencyOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _is_app_record(record)


class SourceFilter(logging.Filter):
    """Adds a `source` attribute so formatters can highlight library logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.source = _record_source(record)
        return True


class ColourFormatter(logging.Formatter):
    COLOURS = {
        "DISCORD": "\033[36m",  # Cyan
        "BOT": "\033[32m",  # Green
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str, datefmt: str, *, enable_colour: bool) -> None:
        super().__init__(fmt, datefmt, style="{")
        self.enable_colour = enable_colour

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        if not self.enable_colour:
            return formatted

        colour = self.COLOURS.get(getattr(record, "source", ""))
        return f"{colour}{formatted}{self.RESET}" if colour else formatted


def setup_logging() -> None:
    dt_fmt = "%Y-%m-%d %H:%M:%S"
    fmt = "[{asctime}] [{levelname:<8}] [{source:<7}] {name}: {message}"
    app_log_level = _parse_log_level(settings.app_log_level, DEFAULT_APP_LOG_LEVEL)
    library_log_level = _parse_log_level(
        settings.lib_log_level,
        DEFAULT_LIBRARY_LOG_LEVEL,
    )
    console_log_level = _parse_log_level(
        settings.console_log_level,
        DEFAULT_CONSOLE_LOG_LEVEL,
    )
    app_log_filename = str(settings.app_log_file or DEFAULT_APP_LOG_FILE)
    dependency_log_filename = str(
        settings.dependency_log_file or DEFAULT_DEPENDENCY_LOG_FILE
    )
    log_max_bytes = _parse_positive_int(
        settings.log_max_bytes,
        DEFAULT_LOG_MAX_BYTES,
    )
    log_backup_count = _parse_positive_int(
        settings.log_backup_count,
        DEFAULT_LOG_BACKUP_COUNT,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(min(app_log_level, library_log_level, console_log_level))

    # Remove any pre-existing handlers to avoid duplicate logs.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    app_file_handler = logging.handlers.RotatingFileHandler(
        filename=app_log_filename,
        encoding="utf-8",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
    )
    app_file_handler.setLevel(app_log_level)
    app_file_handler.setFormatter(logging.Formatter(fmt, dt_fmt, style="{"))
    app_file_handler.addFilter(SourceFilter())
    app_file_handler.addFilter(AppOnlyFilter())
    root_logger.addHandler(app_file_handler)

    dependency_file_handler = logging.handlers.RotatingFileHandler(
        filename=dependency_log_filename,
        encoding="utf-8",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
    )
    dependency_file_handler.setLevel(library_log_level)
    dependency_file_handler.setFormatter(logging.Formatter(fmt, dt_fmt, style="{"))
    dependency_file_handler.addFilter(SourceFilter())
    dependency_file_handler.addFilter(DependencyOnlyFilter())
    root_logger.addHandler(dependency_file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)
    console_formatter = ColourFormatter(
        fmt,
        dt_fmt,
        enable_colour=getattr(console_handler.stream, "isatty", lambda: False)(),
    )
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(SourceFilter())
    root_logger.addHandler(console_handler)

    minimum_noisy_library_level = max(library_log_level, logging.WARNING)
    noisy_loggers = (
        "asyncio",
        "discord",
        "discord.client",
        "discord.gateway",
        "discord.http",
        "httpcore",
        "httpx",
        "openai",
        "peewee",
        "pymongo",
        "urllib3",
        "yfinance",
    )
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(minimum_noisy_library_level)

