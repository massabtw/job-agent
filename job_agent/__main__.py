import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError

from .approval import approve_jobs, reviewed_job
from .browser.gupy import apply_gupy
from .browser.indeed import apply_indeed
from .browser.inspector import detect_blockers, extract_gupy_job, extract_indeed_job
from .browser.search import search_gupy, search_indeed
from .browser.session import create_browser_context
from .connectors import browser_channel, load_jobs, validate_destination
from .discovery import discover, fetch
from .evaluation import evaluate
from .models import Profile
from .profile_validation import profile_blockers
from .runner import run
from .storage import Store

ROOT = Path(__file__).resolve().parents[1]


def guarded_apply(page, url, profile, store, batch_id, auto_submit=True, expected_key=None):
    channel = browser_channel(url)
    reservation = {}

    def before_submit(job):
        if evaluate(job, profile).status != "READY" or profile_blockers(profile):
            return "NEEDS_REVIEW"
        destination_channel, destination = validate_destination(job)
        if destination_channel != channel or destination != str(job.url):
            return "NEEDS_REVIEW"
        key = store.register(job)
        if expected_key and key != expected_key:
            return "NEEDS_REVIEW"
        prior = store.application_status(key)
        if prior:
            return "DUPLICATE" if prior == "SUBMITTED" else "NEEDS_REVIEW"
        store.enqueue(key, channel, destination)
        with store.connection:
            store.connection.execute(
                "UPDATE queue SET state='READY' WHERE key=? AND state='NEEDS_REVIEW' "
                "AND destination=? AND channel=?", (key, destination, channel)
            )
        token = store.reserve(key, batch_id)
        if not token:
            return "LIMIT_REACHED"
        reservation.update(key=key, token=token)
        store.transition(key, token, "SUBMITTING")
        return None

    # Canonical previously registered URLs are checked before any form interaction.
    row = store.connection.execute("SELECT key FROM jobs WHERE json_extract(payload,'$.url')=?",
                                   (url,)).fetchone()
    if row and store.application_status(row["key"]):
        return "NEEDS_REVIEW", None, "Candidatura anterior registrada; não repetir."
    try:
        connector = apply_gupy if channel == "gupy" else apply_indeed
        options = {}
        if store.connection.execute("SELECT 1 FROM approvals LIMIT 1").fetchone():
            options["review_job"] = lambda fresh: reviewed_job(store, fresh, profile)
        status, job, evidence = connector(page, url, profile, auto_submit=auto_submit,
                                          before_submit=before_submit, **options)
    except (PlaywrightError, OSError, ValueError, AssertionError) as error:
        if not reservation:
            raise
        status, job, evidence = "SUBMISSION_UNCERTAIN", None, f"Tentativa interrompida: {error}"
    if reservation:
        final = status if status in {"SUBMITTED", "SUBMISSION_UNCERTAIN"} else "SUBMISSION_UNCERTAIN"
        store.transition(reservation["key"], reservation["token"], final, evidence)
        status = final
    elif status in {"SUBMITTED", "SUBMISSION_UNCERTAIN"}:
        raise ValueError("Conector tentou registrar envio sem reserva.")
    if job:
        key = store.register(job)
        if status == "NEEDS_REVIEW":
            dest_channel, destination = validate_destination(job)
            store.enqueue(key, dest_channel, destination)
        if status in {"NEEDS_REVIEW", "DISCARDED", "BLOCKED_CAPTCHA", "ERROR"}:
            with store.connection:
                store.connection.execute(
                    "UPDATE queue SET state='NEEDS_REVIEW', evidence=? WHERE key=? "
                    "AND state IN ('READY','NEEDS_REVIEW')", (evidence, key)
                )
    return status, job, evidence


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Job Agent: triagem factual e automação de candidaturas.")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "history.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("queue")
    approve = commands.add_parser("approve", help="Autorizar envio de vagas revisadas por 24 horas.")
    approve.add_argument("--jobs", type=Path, required=True)
    approve.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    approve.add_argument("--evidence", required=True)
    approve.add_argument("--authorize-submit", action="store_true", required=True)
    review = commands.add_parser("review", help="Consultar pendências e registrar notas sem aprovação.")
    review.add_argument("--key")
    review.add_argument("--note")
    reconcile = commands.add_parser("reconcile", help="Confirmar manualmente envio incerto com evidência.")
    reconcile.add_argument("--key", required=True)
    reconcile.add_argument("--evidence", required=True)

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
    cmd_search.add_argument("--limit", type=int, choices=range(1, 101), default=10)
    cmd_search.add_argument("--headless", action="store_true", default=False)

    # Browser automation: inspect
    cmd_inspect = commands.add_parser("inspect")
    cmd_inspect.add_argument("--url", required=True)
    cmd_inspect.add_argument("--output", type=Path)
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
    cmd_proc.add_argument("--limit", type=int, choices=range(1, 6), default=5)
    cmd_proc.add_argument("--headless", action="store_true", default=False)

    # Browser automation: login session
    cmd_login = commands.add_parser("login")
    cmd_login.add_argument("--url", default="https://portal.gupy.io")

    # Browser automation: autopilot end-to-end
    cmd_auto = commands.add_parser("autopilot")
    cmd_auto.add_argument("--profile", type=Path, default=ROOT / "profile.json")
    cmd_auto.add_argument("--queries", nargs="+", default=[".net junior", "c# junior", "backend junior", "desenvolvedor .net"])
    cmd_auto.add_argument("--platforms", nargs="+", choices=["gupy", "indeed"], default=["gupy", "indeed"])
    cmd_auto.add_argument("--limit", type=int, choices=range(1, 101), default=10)
    cmd_auto.add_argument("--max-applies", type=int, choices=range(1, 6), default=5)
    cmd_auto.add_argument("--headless", action="store_true", default=False)
    cmd_auto.add_argument("--no-submit", action="store_true", default=False)
    cmd_auto.add_argument("--output", type=Path, default=ROOT / "data" / "autopilot-report.json")


    args = parser.parse_args()
    store = Store(args.db.resolve())

    try:
        if args.command == "login":
            print("Abrindo navegador com sessao persistente em data/browser_session...")
            print("Faca login nas suas contas do Gupy e Indeed.")
            print("Quando concluir, pressione [ENTER] neste terminal ou avise o agente no chat.")
            with create_browser_context(headless=False) as ctx:
                page_gupy = ctx.new_page()
                page_gupy.goto("https://portal.gupy.io")
                page_indeed = ctx.new_page()
                page_indeed.goto("https://br.indeed.com")
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
            channel = browser_channel(args.url)
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
                if channel == "gupy":
                    job = extract_gupy_job(page, args.url)
                else:
                    job = extract_indeed_job(page, args.url)
                eval_result = evaluate(job, profile)
                blockers = detect_blockers(page)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps([job.model_dump(mode="json")],
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({
                "job": job.model_dump(mode="json"),
                "evaluation": eval_result.model_dump(mode="json"),
                "blockers": blockers,
            }, ensure_ascii=False, indent=2))
            return 0

        if args.command == "auto-apply":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            auto_submit = not args.no_submit
            batch_id = str(uuid4())
            store.create_batch(batch_id, 1)
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                status, job, evidence = guarded_apply(
                    page, args.url, profile, store, batch_id, auto_submit=auto_submit
                )
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
            eligible = [item for item in queue_items if item["state"] == "READY"][:args.limit]
            batch_id = str(uuid4())
            store.create_batch(batch_id, args.limit)
            processed_results = []
            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                for item in eligible:
                    dest = item["destination"]
                    status, job, evidence = guarded_apply(
                        page, dest, profile, store, batch_id, expected_key=item["key"]
                    )
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
            store.save_report({"mode": "process_queue", "items": processed_results})
            return 0

        if args.command == "autopilot":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            queries = args.queries or [".net junior", "c# junior", "backend junior", "desenvolvedor .net"]
            print("=== Piloto Automático Iniciado ===")
            print(f"Buscando vagas para: {profile.identity.get('full_name', 'Candidato')}")
            print(f"Termos: {', '.join(queries)}")
            all_found = []
            applied = []
            discarded = []
            needs_review = []
            errors = []
            batch_id = str(uuid4())
            store.create_batch(batch_id, args.max_applies)

            with create_browser_context(headless=args.headless) as ctx:
                page = ctx.new_page()
                for q in queries:
                    if "gupy" in args.platforms:
                        print(f"Buscando na Gupy: '{q}'...")
                        try:
                            g_res = search_gupy(page, q, limit=args.limit)
                            all_found.extend(g_res)
                            print(f"  -> Encontradas {len(g_res)} vagas na Gupy.")
                        except (PlaywrightError, OSError, ValueError) as err:
                            errors.append(f"Erro Gupy '{q}': {err}")
                    if "indeed" in args.platforms:
                        print(f"Buscando no Indeed: '{q}'...")
                        try:
                            i_res = search_indeed(page, q, limit=args.limit)
                            all_found.extend(i_res)
                            print(f"  -> Encontradas {len(i_res)} vagas no Indeed.")
                        except (PlaywrightError, OSError, ValueError) as err:
                            errors.append(f"Erro Indeed '{q}': {err}")

                unique_jobs = {}
                for item in all_found:
                    unique_jobs[item["url"]] = item

                print(f"\nTotal de vagas únicas localizadas: {len(unique_jobs)}")
                print("Iniciando triagem factual e candidatura assistida...\n")

                for url, item in unique_jobs.items():
                    attempts = store.connection.execute(
                        "SELECT COUNT(*) FROM queue WHERE batch_id=?", (batch_id,)
                    ).fetchone()[0]
                    if attempts >= args.max_applies:
                        print(f"Limite máximo de {args.max_applies} candidaturas do lote atingido.")
                        break

                    job_title = item.get("title", url)
                    print(f"-> Analisando: {job_title}")
                    try:
                        status, job, evidence = guarded_apply(
                            page, url, profile, store, batch_id, auto_submit=not args.no_submit
                        )

                        print(f"   Resultado: [{status}] - {evidence[:120]}")
                        if status == "SUBMITTED":
                            applied.append({
                                "url": url,
                                "title": job.title if job else job_title,
                                "company": job.company if job else "",
                                "evidence": evidence,
                            })
                        elif status == "DISCARDED":
                            discarded.append({
                                "url": url,
                                "title": job.title if job else job_title,
                                "company": job.company if job else "",
                                "evidence": evidence,
                            })
                        else:
                            needs_review.append({
                                "url": url,
                                "status": status,
                                "title": job.title if job else job_title,
                                "company": job.company if job else "",
                                "evidence": evidence,
                            })
                    except (PlaywrightError, OSError, ValueError) as err:
                        print(f"   Erro ao processar: {err}")
                        errors.append({"url": url, "error": str(err)})

            summary = {
                "queries": queries,
                "total_found": len(all_found),
                "unique": len(unique_jobs),
                "applied_count": len(applied),
                "applied": applied,
                "discarded_count": len(discarded),
                "discarded": discarded,
                "needs_review_count": len(needs_review),
                "needs_review": needs_review,
                "errors": errors,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nRelatório completo salvo em: {args.output}")
            print(json.dumps({
                "candidaturas_enviadas": len(applied),
                "descartadas": len(discarded),
                "pendentes_revisao": len(needs_review),
                "erros": len(errors),
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

        if args.command == "approve":
            profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8-sig"))
            keys = approve_jobs(store, load_jobs(args.jobs), profile, args.evidence)
            print(json.dumps({"approved": keys, "state": "READY", "valid_hours": 24},
                             ensure_ascii=False, indent=2))
            return 0

        if args.command == "review":
            if args.note is not None:
                if not args.key:
                    raise ValueError("Nota de revisão exige --key.")
                store.add_review_note(args.key, args.note)
            result = store.review_detail(args.key) if args.key else store.pending_reviews()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "reconcile":
            store.reconcile(args.key, args.evidence)
            print(json.dumps(store.review_detail(args.key), ensure_ascii=False, indent=2))
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
    except (TypeError, ValueError, OSError, ValidationError, sqlite3.Error,
            httpx.HTTPError, PlaywrightError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Execução encerrada.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())