import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from .connectors import load_jobs
from .discovery import discover, fetch
from .models import Profile
from .profile_validation import profile_blockers
from .runner import run
from .storage import Store

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Job Agent: triagem factual, sem envios reais.")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "history.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("queue")
    online = commands.add_parser("discover")
    online.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    online.add_argument("--output", type=Path, default=ROOT / "data" / "discovered.json")
    online.add_argument("--report", type=Path, default=ROOT / "data" / "discovery-report.json")
    check = commands.add_parser("check-profile")
    check.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    for name in ("run", "watch"):
        command = commands.add_parser(name)
        command.add_argument("--profile", type=Path, default=ROOT / "profile.json")
        if name == "run":
            command.add_argument("--jobs", type=Path, required=True)
        command.add_argument("--report", type=Path, default=ROOT / "data" / "report.json")
        command.add_argument("--limit", type=int, choices=range(1, 6), default=5)
        if name == "watch":
            command.add_argument("--inbox", type=Path, default=ROOT / "data" / "inbox")
            command.add_argument("--interval", type=int, default=60)
    history = commands.add_parser("record-history")
    history.add_argument("--key", required=True)
    history.add_argument("--status", choices=["SUBMITTED", "SUBMISSION_UNCERTAIN"], required=True)
    history.add_argument("--evidence", required=True)
    args = parser.parse_args()
    store = Store(args.db.resolve())
    try:
        if args.command == "discover":
            payload, cached = fetch(ROOT / "data" / "remotive-cache.sqlite3")
            jobs, errors = discover(payload)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps([j.model_dump(mode="json") for j in jobs],
                                             ensure_ascii=False, indent=2), encoding="utf-8")
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            report = run(jobs, profile, store)
            report["discovery"] = {"source": "Remotive", "from_cache": cached,
                                   "received": len(payload["jobs"]), "selected": len(jobs),
                                   "errors": errors, "delay_hours": 24}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"discovery": report["discovery"], "discarded": report["discarded"],
                              "needs_review": report["needs_review"], "submitted": 0,
                              "report": str(args.report)}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "queue":
            print(json.dumps(store.queue_items(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "check-profile":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            blockers = profile_blockers(profile)
            print(json.dumps({"valid": not blockers, "blockers": blockers}, ensure_ascii=False,
                             indent=2))
            return 1 if blockers else 0
        if args.command == "record-history":
            store.record_external(args.key, args.status, args.evidence)
            print("Histórico externo registrado; nenhuma candidatura foi enviada pelo agente.")
            return 0
        if args.command == "watch" and args.interval < 10:
            raise ValueError("Intervalo mínimo: dez segundos.")

        def execute(path: Path):
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            report = run(load_jobs(path), profile, store, args.limit)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.report.with_suffix(".tmp")
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(args.report)
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

        if args.command == "run":
            execute(args.jobs.resolve())
        else:
            args.inbox.mkdir(parents=True, exist_ok=True)
            processed = {}
            print("Observando arquivos JSON locais; Ctrl+C para encerrar.", flush=True)
            while True:
                for path in sorted(args.inbox.glob("*.json")):
                    stamp = (path.stat().st_mtime_ns, path.stat().st_size)
                    if processed.get(path) != stamp:
                        try:
                            execute(path)
                        except (TypeError, ValueError, OSError, ValidationError) as error:
                            print(f"Falha em {path}: {error}", file=sys.stderr)
                        processed[path] = stamp
                time.sleep(args.interval)
        return 0
    except (TypeError, ValueError, OSError, ValidationError, sqlite3.Error, httpx.HTTPError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Execução encerrada.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())