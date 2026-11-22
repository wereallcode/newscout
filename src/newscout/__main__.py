import argparse
import logging
import threading
from pathlib import Path

from newscout import db, presets
from newscout.ai import state
from newscout.ai.loop import run_ai
from newscout.fetch.loop import run_forever
from newscout.web import create_app

log = logging.getLogger("newscout")


def supervised(loop, path: Path, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            loop(path, stop)
        except Exception:
            log.exception("%s crashed; restarting", loop.__name__)
            stop.wait(5)


def start(loop, path: Path, stop: threading.Event) -> None:
    threading.Thread(target=supervised, args=(loop, path, stop), daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="newscout", description="A self-hosted newsroom for your RSS feeds."
    )
    parser.add_argument("--port", type=int, default=8000)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("web", help="Serve the web app only")
    commands.add_parser("fetch", help="Run the fetcher only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    path = db.default_path()
    presets.install(db.connect(path))
    stop = threading.Event()
    try:
        if args.command == "fetch":
            start(run_ai, path, stop)
            run_forever(path, stop)
            return 0
        if args.command is None:
            # Dev starts paused so a restart never surprises you; "newscout fetch" resumes as it was
            db.fetcher.stop(db.connect(path))
            state.set_running(db.connect(path), False)
            start(run_forever, path, stop)
            start(run_ai, path, stop)
        create_app(path).run(host="127.0.0.1", port=args.port, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
