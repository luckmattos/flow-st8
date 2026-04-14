"""flow-st8 - Lightweight local voice transcription for Windows."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import APP_DIR, load_config
from app import FlowSt8App
from version import __version__


def _setup_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr so pt-BR and Unicode never crash logging."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, Exception):
            pass


def _setup_logging() -> None:
    """Log to stderr and to a rotating file for startup diagnostics."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(sys.stderr),
        RotatingFileHandler(
            APP_DIR / "flow-st8.log",
            maxBytes=512_000,
            backupCount=2,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def main() -> None:
    _setup_utf8_stdio()
    _setup_logging()
    log = logging.getLogger("flow-st8")

    log.info("Loading configuration...")
    config = load_config()

    import autostart
    autostart.sync(config.startup.autostart)

    log.info(
        "Starting flow-st8 v%s (model=%s, hotkey=%s, vad=%s, autostart=%s)",
        __version__,
        config.model.name,
        config.hotkey.key,
        config.vad.enabled,
        config.startup.autostart,
    )

    app = FlowSt8App(config)
    app.start()

    try:
        # Tray.run() blocks the main thread (required by Windows)
        app.tray.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
