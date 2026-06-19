from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        existing = {column["name"] for column in inspect(engine).get_columns("lead")}
        with engine.begin() as connection:
            if "company_website" not in existing:
                connection.execute(text("ALTER TABLE lead ADD COLUMN company_website VARCHAR(300)"))
            if "linkedin_url" not in existing:
                connection.execute(text("ALTER TABLE lead ADD COLUMN linkedin_url VARCHAR(300)"))
        enrichment_columns = {column["name"] for column in inspect(engine).get_columns("leadenrichment")}
        with engine.begin() as connection:
            if "role_validation" not in enrichment_columns:
                connection.execute(text("ALTER TABLE leadenrichment ADD COLUMN role_validation VARCHAR(200) DEFAULT 'Não validado publicamente'"))
            if "professional_presence" not in enrichment_columns:
                connection.execute(text("ALTER TABLE leadenrichment ADD COLUMN professional_presence VARCHAR(300) DEFAULT 'Não localizada'"))
            if "qualification_score" not in enrichment_columns:
                connection.execute(text("ALTER TABLE leadenrichment ADD COLUMN qualification_score INTEGER DEFAULT 0"))
            if "research_sources" not in enrichment_columns:
                connection.execute(text("ALTER TABLE leadenrichment ADD COLUMN research_sources VARCHAR(1000)"))
        meeting_columns = {column["name"] for column in inspect(engine).get_columns("meeting")}
        with engine.begin() as connection:
            if "meeting_url" not in meeting_columns:
                connection.execute(text("ALTER TABLE meeting ADD COLUMN meeting_url VARCHAR(500)"))
            if "admin_note" not in meeting_columns:
                connection.execute(text("ALTER TABLE meeting ADD COLUMN admin_note VARCHAR(500)"))
            if "notified_at" not in meeting_columns:
                connection.execute(text("ALTER TABLE meeting ADD COLUMN notified_at DATETIME"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
