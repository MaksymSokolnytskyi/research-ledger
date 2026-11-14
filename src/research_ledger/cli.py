"""The ``ledger`` command."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import sys
from pathlib import Path

from research_ledger import __version__
from research_ledger.config import CONFIG_NAME, find_vault


def _utf8() -> None:
    """Windows consoles default to a legacy code page that mangles Cyrillic."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def cmd_init(args: argparse.Namespace) -> int:
    from research_ledger.scaffold import apply, plan

    root = Path(args.path).resolve()
    files, notes = plan(
        root,
        name=args.name or root.name,
        language=args.language,
        existing=True if args.existing else None,
        with_notes=True if args.with_notes else None,
        docs=tuple(args.docs or ()),
        obsidian_settings=True if args.obsidian else None,
    )
    for f in files:
        print(f"  create {f.path.relative_to(root)}  ({f.reason})")
    for note in notes:
        print(f"  note   {note}")
    if args.dry_run:
        return 0
    apply(files)
    vault = find_vault(root)
    if any(n.startswith("Existing project") for n in notes):  # adopt current state
        from research_ledger.audit import run_audit, save_adopted
        from research_ledger.ratchet import record_pass

        result = run_audit(vault)
        record_pass(vault, result.metrics, adopt=True)
        save_adopted(vault, result)
        print("  baseline adopted from the current state")
    print(f"ledger ready at {root}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from research_ledger.audit import load_adopted, run_audit, save_adopted
    from research_ledger.generate import write_health
    from research_ledger.ratchet import compare, record_pass, stalled

    vault = find_vault(Path(args.path))
    result = run_audit(vault)
    metrics = result.metrics
    ratchet = compare(vault, metrics)
    if args.json:
        print(
            json.dumps(
                {
                    "metrics": metrics,
                    "regressions": [c.model_dump() for c in ratchet.regressions],
                }
            )
        )
    else:
        width = max(len(k) for k in metrics)
        for key, value in metrics.items():
            mark = ""
            for c in ratchet.changes:
                if c.metric == key:
                    mark = "  WORSE" if c.worse else ("  better" if c.better else "")
            print(f"{key:<{width}}  {value:>10}{mark}")
        if not ratchet.had_baseline:
            print("no baseline yet: this pass becomes it")
        for metric in stalled(vault):
            print(f"stalled: {metric} has not improved in 10 passes")
    if not args.check:
        record_pass(vault, metrics, adopt=args.adopt)
        if args.adopt:
            save_adopted(vault, result)
        page = write_health(result, ratchet, load_adopted(vault))
        if not args.json:
            print(f"wrote {page.relative_to(vault.root)}")
    return 1 if ratchet.regressions and not args.adopt else 0


def cmd_context(args: argparse.Namespace) -> int:
    from research_ledger.context import build_context

    vault = find_vault(Path(args.path))
    pack = build_context(vault, args.task, args.budget)
    print(pack.render() or "nothing in the ledger matches this task")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    from research_ledger.records import Record, write_record

    vault = find_vault(Path(args.path))
    body = sys.stdin.read() if args.body == "-" else (args.body or "")
    path = write_record(
        vault,
        Record(
            kind=args.kind,
            title=args.title,
            body=body,
            agent=args.agent or vault.config.agents[0],
            sources=tuple(args.source or ()),
            refs=tuple(args.ref or ()),
        ),
    )
    print(path.relative_to(vault.root))
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    from research_ledger.failures import capture

    vault = find_vault(Path(args.path))
    error = sys.stdin.read() if args.error == "-" else args.error
    result = capture(vault, args.tool, args.command, error, agent=args.agent or "main")
    if result is None:
        print("not recorded: capture is off in ledger.toml or the command is ignored")
        return 0
    print(f"{'repeat of' if result.repeat else 'new failure'} {result.record_id}")
    for lesson in result.lessons:
        print(f"  lesson: {lesson}")
    return 0


def cmd_lesson(args: argparse.Namespace) -> int:
    from research_ledger.failures import add_lesson

    vault = find_vault(Path(args.path))
    try:
        print(add_lesson(vault, args.failure_id, args.text, agent=args.agent or "main"))
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2
    return 0


def cmd_failures(args: argparse.Namespace) -> int:
    from research_ledger.failures import known_failures, load_failures

    vault = find_vault(Path(args.path))
    if args.command:
        for k in known_failures(vault, args.command, limit=20):
            print(f"{k.failure_id}  x{k.times}  {k.title}")
            for lesson in k.lessons:
                print(f"    lesson: {lesson}")
        return 0
    index = load_failures(vault)
    for sig, rec in index.failures.items():
        times = index.count(sig)
        lessons = index.lessons_for(sig)
        print(f"{rec.id}  x{times}  {'lesson' if lessons else 'NO LESSON'}  {rec.title}")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from research_ledger.hooks import main

    main(args.event)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve the vault over HTTP so notes can embed live HTML/JS pages via <iframe>."""
    vault = find_vault(Path(args.path))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(vault.root)
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"serving {vault.root} at http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")
        print(
            f'embed: <iframe src="http://127.0.0.1:{args.port}/demo/page.html"></iframe>'
        )
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    from research_ledger.feedback import main_feedback

    vault = find_vault(Path(args.path))
    message = sys.stdin.read() if args.message == "-" else (args.message or "")
    return main_feedback(vault, args.kind, message, args.submit)


def cmd_stats(args: argparse.Namespace) -> int:
    from research_ledger.usage import summary

    stats = summary(find_vault(Path(args.path)))
    if not stats:
        print("no hook activity recorded yet")
    for event, s in stats.items():
        print(
            f"{event:<14} calls {s['calls']:>5}  spoke {s['spoke']:>5}  "
            f"median {s['median_ms']:>6} ms  p95 {s['p95_ms']:>6} ms  "
            f"errors {s['errors']}  chars added {s['chars_added']}"
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    vault = find_vault(Path(args.path))
    configured = (vault.root / CONFIG_NAME).is_file()
    print(f"research-ledger {__version__}")
    print(f"vault root     {vault.root}")
    print(f"ledger.toml    {'found' if configured else 'missing: run `ledger init`'}")
    state = "exists" if vault.state_dir.exists() else "none yet"
    print(f"state dir      {vault.state_dir} ({state})")
    errors = vault.state_dir / "hook_errors.log"
    if errors.is_file():
        tail = errors.read_text(encoding="utf-8").splitlines()[-3:]
        print("recent hook errors:")
        for line in tail:
            print(f"  {line}")
    return 0 if configured else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ledger", description="Research ledger for Obsidian vaults."
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:  # type: ignore[no-untyped-def]
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--path", default=".", help="vault folder (default: current)")
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "make a folder a ledger (never overwrites)")
    sp.add_argument("dir", nargs="?", default=".", help="folder to initialise")
    sp.add_argument("--name")
    sp.add_argument("--language", choices=["en", "uk"], default="en")
    sp.add_argument(
        "--existing", action="store_true", help="treat as an existing project"
    )
    sp.add_argument("--with-notes", action="store_true", help="add starter notes anyway")
    sp.add_argument(
        "--docs", nargs="+", help="only read these folders: --docs docs notes"
    )
    sp.add_argument(
        "--obsidian", action="store_true", help="add Obsidian settings anyway"
    )
    sp.add_argument("--dry-run", action="store_true")

    sp = add("audit", cmd_audit, "run all checks and the ratchet")
    sp.add_argument("--check", action="store_true", help="write nothing")
    sp.add_argument(
        "--adopt", action="store_true", help="accept current state as baseline"
    )
    sp.add_argument("--json", action="store_true")

    sp = add("context", cmd_context, "context pack for a task")
    sp.add_argument("task")
    sp.add_argument("--budget", type=int, default=None, help="tokens")

    sp = add("record", cmd_record, "write an append-only record")
    sp.add_argument("kind", choices=["run", "decision", "note", "research", "agent_call"])
    sp.add_argument("title")
    sp.add_argument("--body", help="text, or - for stdin")
    sp.add_argument("--source", action="append")
    sp.add_argument("--ref", action="append")
    sp.add_argument("--agent")

    sp = add("capture", cmd_capture, "record a failed command")
    sp.add_argument("--command", required=True)
    sp.add_argument("--error", required=True, help="text, or - for stdin")
    sp.add_argument("--tool", default="Bash")
    sp.add_argument("--agent")

    sp = add("lesson", cmd_lesson, "attach a lesson to a failure")
    sp.add_argument("failure_id")
    sp.add_argument("text")
    sp.add_argument("--agent")

    sp = add("failures", cmd_failures, "list failures, or those of one command")
    sp.add_argument("--command")

    sp = add("hook", cmd_hook, "Claude Code hook entry point (reads JSON on stdin)")
    sp.add_argument(
        "event", choices=["session-start", "user-prompt", "pre-bash", "tool-failure"]
    )

    sp = add("serve", cmd_serve, "serve the vault for embedded HTML/JS pages")
    sp.add_argument("--port", type=int, default=8765)

    sp = add("feedback", cmd_feedback, "bug report or idea with diagnostics attached")
    sp.add_argument("--kind", choices=["bug", "idea", "comment"], default="comment")
    sp.add_argument("--message", "-m", help="text, or - for stdin")
    sp.add_argument("--submit", action="store_true", help="file it with your gh login")

    add("stats", cmd_stats, "what the hooks did on this machine (local only)")
    add("doctor", cmd_doctor, "check the installation and configuration")
    return p


def main(argv: list[str] | None = None) -> int:
    _utf8()
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        args.path = args.dir
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
