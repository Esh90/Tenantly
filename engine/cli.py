"""Single CLI entry point: `uv run python -m engine.cli <command>`."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def recon() -> None:
    """Verify pack facts against CORPUS_ATLAS.md and write DATASET_NOTES.md."""
    from engine.notes import write_dataset_notes

    failed = write_dataset_notes()
    typer.echo(f"recon done; {failed} claim(s) differ from the atlas (see DATASET_NOTES.md)")


@app.command()
def corpus() -> None:
    """Load, mask, classify and sectionize the corpus -> artifacts/corpus/*.jsonl."""
    from engine.corpus.build import write

    docs, sections = write()
    typer.echo(f"corpus: {docs} documents, {sections} sections")


@app.command()
def facts() -> None:
    """Derive building facts for all addresses -> artifacts/eval/facts_report.json."""
    from engine import config
    from engine.facts.derive import derive_all, facts_report
    from engine.io import atomic_write_json

    report = facts_report(derive_all())
    atomic_write_json(config.ARTIFACTS / "eval" / "facts_report.json", report)
    typer.echo(
        f"facts: {report['addresses']} addresses, {report['record_conflicts']} record conflicts, "
        f"{report['zip_suspect']} suspect ZIPs, {report['missing_year_built']} missing year built"
    )


@app.command()
def geo() -> None:
    """Download TIGER boundaries and write artifacts/geo/*."""
    import logging

    from engine.geo.boundaries import build

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    report = build()
    typer.echo(f"geo: {len(report['cities'])} cities, {len(report['counties'])} counties")


@app.command()
def resolve() -> None:
    """Facts + geocode + point-in-polygon -> artifacts/addresses.resolved.json."""
    import logging

    from engine.geo.resolve import write

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    r = write()
    typer.echo(
        f"resolve: {r['addresses']} addresses; batch {r['matched_batch']}, oneline "
        f"{r['matched_oneline']}, nominatim {r['matched_nominatim']}, unmatched {r['unmatched']}; "
        f"mailing mismatches {r['mailing_mismatches']}; census disagreements "
        f"{r['census_disagreements']}"
    )


@app.command()
def compile(
    explain: bool = typer.Option(False, "--explain", help="Plan and estimate cost; spend nothing"),
    only: str = typer.Option("", help="Comma-separated doc ids, for a partial run"),
) -> None:
    """Run the Law Compiler DAG -> artifacts/rules.compiled.json."""
    import logging

    from engine.compile import dag
    from engine.compile.llm import LLM

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    docs = [d for d in only.split(",") if d] or None
    llm = LLM()
    if explain:
        typer.echo(dag.dump_plan(dag.explain_plan(llm, docs)))
        return
    rules, relations, findings, oqs, extra = dag.compile_all(llm, docs)
    rs = dag.write_artifacts(rules, relations, findings, oqs, extra)
    typer.echo(
        f"compiled {len(rs.rules)} rules, {len(rs.relations)} relations, {len(rs.findings)} findings, "
        f"{len(rs.open_questions)} open questions; data_version {rs.data_version}; "
        f"spent ${llm.ledger.total:.3f} of ${llm.ledger.cap:.2f}"
    )


@app.command()
def lookups() -> None:
    """Engine at the default date for all 500 addresses; prints the result distribution."""
    from collections import Counter

    from engine.export import build

    doc = build.build_lookups(build.load_ruleset(), build.load_records())
    c = Counter(e["result"] for v in doc["lookups"].values() for e in v)
    typer.echo(f"lookups: {len(doc['lookups'])} addresses; results {dict(sorted(c.items()))}")


@app.command()
def changes() -> None:
    """Typed change tests T1-T5 -> artifacts/changes/*.json and out/changes.json."""
    from engine.export import build

    sub = build.write_changes(build.load_ruleset(), build.load_records())
    for tid, v in sub.items():
        typer.echo(
            f"{tid}: affected {len(v['affected_address_ids'])}, conflict flags {len(v['conflict_flag_address_ids'])}"
        )


@app.command()
def export() -> None:
    """Write out/rules.json, lookups.json, changes.json (validated against the official schema)."""
    from engine.export import build

    typer.echo(str(build.export_all(build.load_ruleset(), build.load_records())))


@app.command()
def snapshot() -> None:
    """Write the static snapshot to artifacts/web/."""
    from engine.export import build

    typer.echo(str(build.build_snapshot()))


@app.command()
def score() -> None:
    """Self-score against the silver key (eval/selfscore.py) -> artifacts/eval/selfscore.json."""
    import importlib

    typer.echo(importlib.import_module("eval.selfscore").main())


@app.command()
def serve(port: int = 8000, reload: bool = False) -> None:
    """Run the API locally."""
    import uvicorn

    uvicorn.run("engine.api.main:app", host="0.0.0.0", port=port, reload=reload)  # noqa: S104


@app.command("deploy-api")
def deploy_api() -> None:
    """Build build/space and push it to the Hugging Face Space; poll /v1/health."""
    import logging

    from engine.deploy import deploy

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    typer.echo(f"deployed: {deploy()}")


if __name__ == "__main__":
    app()
