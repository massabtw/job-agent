import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from .browser.gupy import apply_gupy
from .browser.indeed import apply_indeed
from .browser.inspector import detect_blockers, extract_gupy_job, extract_indeed_job
from .browser.search import search_gupy, search_indeed
from .browser.session import create_browser_context
from .connectors import load_jobs
from .discovery import discover, fetch
from .evaluation import evaluate
from .models import Profile
from .profile_validation import profile_blockers
from .runner import run
from .storage import Store

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Job Agent: triagem factual e automação de candidaturas.")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "history.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("queue")

    # Remotive discovery
    online = commands.add_parser("discover")
    online.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    online.add_argument("--output", type=Path, default=ROOT / "data" / "discovered.json")
    online.add_argument("--report", type=Path, default=ROOT / "data" / "discovery-report.json")

    # Profile validation
    check = commands.add_parser("check-profile")
    check.add_argument("--profile", type=Path, default=ROOT / "profile.json")

    # Batch run & file watcher
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

    # History tracking
    history = commands.add_parser("record-history")
    history.add_argument("--key", required=True)
    history.add_argument("--status", choices=["SUBMITTED", "SUBMISSION_UNCERTAIN"], required=True)
    history.add_argument("--evidence", required=True)

    # Browser automation: search
    cmd_search = commands.add_parser("search")
    cmd_search.add_argument("--platform", choices=["gupy", "indeed"], required=True)
    cmd_search.add_argument("--query", required=True)
    cmd_search.add_argument("--limit", type=int, default=10)
    cmd_search.add_argument("--headless", action="store_true", default=False)

    # Browser automation: inspect
    cmd_inspect = commands.add_parser("inspect")
    cmd_inspect.add_argument("--url", required=True)
    cmd_inspect.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    cmd_inspect.add_argument("--headless", action="store_true", default=False)

    # Browser automation: auto-apply
    cmd_apply = commands.add_parser("auto-apply")
    cmd_apply.add_argument("--url", required=True)
    cmd_apply.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    cmd_apply.add_argument("--headless", action="store_true", default=False)
    cmd_apply.add_argument("--no-submit", action="store_true", default=False)

    # Browser automation: process-queue
    cmd_proc = commands.add_parser("process-queue")
    cmd_proc.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    cmd_proc.add_argument("--limit", type=int, default=5)
    cmd_proc.add_argument("--headless", action="store_true", default=False)

    # Browser automation: login session
    cmd_login = commands.add_parser("login")
    cmd_login.add_argument("--url", default="https://portal.gupy.io")

    args = parser.parse_args()
    store = Store(args.db.resolve())

    try:
        if args.command == "login":
            print("Abrindo navegador com sessao persistente em data/browser_session...")
            print("Faca login nas suas contas do Gupy e Indeed.")
            print("Quando concluir, pressione [ENTER] neste terminal para salvar a sessao.")
            with create_browser_context(headless=False) as ctx:
                page = ctx.new_page()
                page.goto(args.url)
                input("Pressione [ENTER] para concluir o salvamento da sessao...")
            print("Sessao salva com sucesso!")
            return 0
        if args.command == "search":
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                if args.platform == "gupy":
                    results = search_gupy(page, args.query, args.limit)
                else:
                    results = search_indeed(page, args.query, args.limit)
            print(json.dumps({
                "platform": args.platform,
                "query": args.query,
                "found": len(results),
                "results": results,
            }, ensure_ascii=False, indent=2))
            return 0

        if args.command == "inspect":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
                if "gupy.io" in args.url:
                    job = extract_gupy_job(page, args.url)
                else:
                    job = extract_indeed_job(page, args.url)
                eval_result = evaluate(job, profile)
                blockers = detect_blockers(page)
            print(json.dumps({
                "job": job.model_dump(mode="json"),
                "evaluation": eval_result.model_dump(mode="json"),
                "blockers": blockers,
            }, ensure_ascii=False, indent=2))
            return 0

        if args.command == "auto-apply":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            auto_submit = not args.no_submit
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                if "gupy.io" in args.url:
                    status, job, evidence = apply_gupy(page, args.url, profile, auto_submit=auto_submit)
                else:
                    status, job, evidence = apply_indeed(page, args.url, profile, auto_submit=auto_submit)
                if job:
                    key = store.register(job)
                    if status in {"SUBMITTED", "SUBMISSION_UNCERTAIN"}:
                        store.record_external(key, status, evidence)
            print(json.dumps({
                "url": args.url,
                "status": status,
                "job": job.model_dump(mode="json") if job else None,
                "evidence": evidence,
            }, ensure_ascii=False, indent=2))
            return 0 if status in {"SUBMITTED", "NEEDS_REVIEW", "DISCARDED"} else 1

        if args.command == "process-queue":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            queue_items = store.queue_items()
            eligible = [item for item in queue_items if item["state"] in {"READY", "NEEDS_REVIEW"}][:args.limit]
            processed_results = []
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                for item in eligible:
                    dest = item["destination"]
                    if "gupy.io" in dest:
                        status, job, evidence = apply_gupy(page, dest, profile, auto_submit=True)
                    else:
                        status, job, evidence = apply_indeed(page, dest, profile, auto_submit=True)
                    processed_results.append({
                        "key": item["key"],
                        "destination": dest,
                        "status": status,
                        "evidence": evidence,
                    })
            print(json.dumps({
                "processed": len(processed_results),
                "results": processed_results,
            }, ensure_ascii=False, indent=2))
            return 0

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