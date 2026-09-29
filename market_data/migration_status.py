from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_heads() -> set[str]:
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    return set(ScriptDirectory.from_config(config).get_heads())
