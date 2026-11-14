from alembic import context
from sqlalchemy import create_engine

from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.db.models import metadata


def run():
    url = Settings().database_url.get_secret_value()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with create_engine(url).connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()


run()
