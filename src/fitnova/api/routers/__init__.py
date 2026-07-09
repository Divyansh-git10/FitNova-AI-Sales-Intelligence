"""FastAPI routers (Phase 5): calls, org hierarchy (orgs/teams/advisors +
scorecards), executive analytics, issue drill-down + feedback, LLM
observability + pipeline benchmarking + queue/health, and CSV/PDF export.
Each router only calls into `fitnova.db.repository` — no router writes a
raw SQLAlchemy query itself."""
