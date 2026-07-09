"""Single application bootstrap entrypoint.

Every front door into this system — the FastAPI app, the Typer CLI, the
Streamlit dashboard, the pipeline orchestrator — calls `bootstrap_app()`
exactly once to get a fully-wired `Container`. This guarantees:

1. Configuration is loaded and validated (bad YAML fails loudly, here,
   before anything else runs).
2. Logging is configured before any other module logs anything.
3. Required data directories exist.
4. The database schema exists.
5. Every consumer resolves shared infrastructure from the same container
   instance, rather than re-constructing engines/settings independently.

Run directly (`python -m fitnova.bootstrap`) as a smoke test: it should
print a confirmation with zero errors if the scaffold is wired correctly.
"""

from __future__ import annotations

from fitnova.core.container import Container
from fitnova.core.logging_config import configure_logging, get_logger
from fitnova.db.init_db import init_db

logger = get_logger(__name__)


def bootstrap_app() -> Container:
    """Wire configuration, logging, filesystem, and the database. Returns
    the DI container so callers can resolve further dependencies."""
    container = Container()
    settings = container.settings()

    configure_logging(settings)
    logger.info("Bootstrapping FitNova (env=%s)", settings.app_env)

    for directory in (
        settings.resolved_data_dir(),
        settings.resolved_audio_inbox_dir(),
        settings.resolved_processed_audio_dir(),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory exists: %s", directory)

    weights = container.weights_config()
    issue_rules = container.issue_rules_config()
    logger.info(
        "Loaded business config: scoring_version=%s, %d issue types defined",
        weights.scoring_version,
        len(issue_rules.issue_types),
    )

    engine = container.engine()
    init_db(engine)

    logger.info("Bootstrap complete")
    return container


if __name__ == "__main__":
    bootstrap_app()
    print("FitNova bootstrap OK — settings, logging, config, and database are wired.")
