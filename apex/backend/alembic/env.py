import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so apex.backend.* imports work whether
# alembic is invoked from apex/backend/ or from the project root.
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))  # apex/backend/alembic/
_backend = os.path.dirname(_here)  # apex/backend/
_repo_root = os.path.dirname(os.path.dirname(_backend))  # project root
for _p in (_repo_root, _backend):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Import Base (defined in database.py) and ALL models so autogenerate sees
# every table.
# ---------------------------------------------------------------------------
from apex.backend.db.database import DATABASE_URL, Base  # noqa: E402
from apex.backend.models import (  # noqa: F401, E402
    agent_run_log,
    audit_log,
    bid_comparison,
    change_order,
    document,
    equipment_rate,
    estimate,
    estimate_library,
    gap_report,
    labor_estimate,
    material_price,
    organization,
    productivity_history,
    project,
    project_actual,
    spec_section,
    takeoff_item,
    token_usage,
    upload_chunk,
    upload_session,
    user,
)
from apex.backend.models.decision_models import (  # noqa: F401, E402
    ActivityAlias,
    BidOutcome,
    CanonicalActivity,
    ComparableProject,
    CostBreakdownBucket,
    EscalationInput,
    EstimateLine,
    EstimatorOverride,
    FieldActual,
    HistoricalRateObservation,
    RiskItem,
)
from apex.backend.models.document_association import DocumentAssociation, DocumentGroup  # noqa: F401, E402
from apex.backend.models.field_actuals import FieldActualsLineItem, FieldActualsProject  # noqa: F401, E402
from apex.backend.models.historical_line_item import HistoricalLineItem  # noqa: F401, E402
from apex.backend.models.intelligence_report import IntelligenceReportModel  # noqa: F401, E402
from apex.backend.models.takeoff_v2 import TakeoffItemV2  # noqa: F401, E402
from apex.backend.services.library.bid_intelligence.models import BIEstimate  # noqa: F401, E402
from apex.backend.services.library.productivity_brain.models import PBLineItem, PBProject  # noqa: F401, E402

# ---------------------------------------------------------------------------
# Alembic Config
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from the same source database.py uses so they stay
# consistent.  The value in alembic.ini acts as a fallback only.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to real DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
