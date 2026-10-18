from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns(bind) -> None:
    """Добавляет колонки, появившиеся после создания таблиц.

    Base.metadata.create_all создаёт недостающие ТАБЛИЦЫ, но не добавляет новые
    колонки в уже существующие. Для личной базы SQLite проще сделать это здесь,
    чем заставлять каждый раз вручную запускать миграцию. Безопасно вызывать много раз.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(bind)
    if "forecasts" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("forecasts")}
        if "actual_price" not in columns:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE forecasts ADD COLUMN actual_price FLOAT"))
