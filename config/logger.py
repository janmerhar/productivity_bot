import logging
import logging.handlers


class SourceFilter(logging.Filter):
    """Adds a `source` attribute so formatters can highlight library logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.source = (
            "DISCORD"
            if record.name == "discord" or record.name.startswith("discord.")
            else "BOT"
        )
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

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove any pre-existing handlers to avoid duplicate logs.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        filename="discord.log",
        encoding="utf-8",
        maxBytes=32 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, dt_fmt, style="{"))
    file_handler.addFilter(SourceFilter())
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = ColourFormatter(
        fmt,
        dt_fmt,
        enable_colour=getattr(console_handler.stream, "isatty", lambda: False)(),
    )
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(SourceFilter())
    root_logger.addHandler(console_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.DEBUG)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

