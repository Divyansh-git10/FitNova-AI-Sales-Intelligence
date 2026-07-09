"""Application-wide dependency injection container.

Every consumer of infrastructure (the API, the CLI, the dashboard, tests)
resolves its dependencies through a `Container` instance rather than
constructing `Settings`, an `Engine`, or a config object directly. This is
what lets tests substitute an in-memory SQLite engine or a stub LLM client
without monkeypatching module globals, and it's the single place that knows
how all the pieces wire together.

Phase 2 wires: settings, business config (weights/issue-rules), and
database infrastructure. Phase 4/5 extend this container with the
repository layer, the LLM client, and pipeline services — consumers should
never construct those directly either, once they exist.
"""

from __future__ import annotations

from dependency_injector import containers, providers

from fitnova.core.config import IssueRulesConfig, ScoringWeightsConfig, Settings, get_settings
from fitnova.db.session import build_engine, build_session_factory


def _load_weights(settings: Settings) -> ScoringWeightsConfig:
    return settings.load_weights()


def _load_issue_rules(settings: Settings) -> IssueRulesConfig:
    return settings.load_issue_rules()


class Container(containers.DeclarativeContainer):
    """Composition root. See module docstring."""

    settings = providers.Singleton(get_settings)

    weights_config = providers.Singleton(_load_weights, settings=settings)
    issue_rules_config = providers.Singleton(_load_issue_rules, settings=settings)

    engine = providers.Singleton(build_engine, settings=settings)
    session_factory = providers.Singleton(build_session_factory, engine=engine)
