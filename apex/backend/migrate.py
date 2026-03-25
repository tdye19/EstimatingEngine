"""Run: python -m apex.backend.migrate"""
from alembic.config import Config
from alembic import command


def run_migrations():
    alembic_cfg = Config("apex/backend/alembic.ini")
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    run_migrations()
