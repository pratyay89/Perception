import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        # Colours are switched on automatically where the terminal supports them
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()
