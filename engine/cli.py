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
