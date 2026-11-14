from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scene_tracker.core.settings import Settings


def session_factory(settings: Settings):
    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)
