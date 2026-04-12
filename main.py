"""flow-st8 - Lightweight local voice transcription for Windows."""

import logging
import sys

from config import load_config
from app import FlowSt8App


def _setup_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr so pt-BR and Unicode never crash logging."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, Exception):
            pass


def main() -> None:
    _setup_utf8_stdio()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("flow-st8")

    log.info("Loading configuration...")
    config = load_config()

    log.info("Starting flow-st8 (model=%s, hotkey=%s, vad=%s)",
             config.model.name, config.hotkey.key, config.vad.enabled)

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
