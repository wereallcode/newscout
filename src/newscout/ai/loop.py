import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from newscout import db
from newscout.ai import instructions, state
from newscout.ai.deepseek import DeepSeekJudge
from newscout.ai.pipeline import process

PAUSE_AFTER_ERROR = timedelta(minutes=1)

log = logging.getLogger(__name__)


# Its own loop, so a slow AI never holds up fetching.
def run_ai(path: Path, stop: threading.Event, poll: float = 2.0) -> None:
    conn = db.connect(path)
    paused_until = datetime.min.replace(tzinfo=UTC)
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            key = state.key(conn)
            if key and state.running(conn) and now >= paused_until:
                try:
                    process(conn, DeepSeekJudge(key), instructions.load(conn))
                    state.report(conn, None)
                except Exception as error:
                    log.exception("AI failed; trying again in a minute")
                    state.report(conn, str(error))
                    paused_until = now + PAUSE_AFTER_ERROR
            stop.wait(poll)
    finally:
        conn.close()
