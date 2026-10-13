
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / "backend" / ".env"
load_dotenv(ENV_PATH)


class Base(DeclarativeBase):
    pass


class ReviewSessionRecord(Base):
    __tablename__ = "review_sessions"

    analysis_id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    contract_filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    policy_filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    items: Mapped[list] = mapped_column(
        JSON, nullable=False
    )
    analysis_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ReviewDecisionRecord(Base):
    __tablename__ = "review_decisions"

    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "item_id",
            name="uq_review_decision_item",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "review_sessions.analysis_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    item_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    if database_url.startswith("postgresql+psycopg2://"):
        return database_url.replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            1,
        )

    return database_url


def get_session_factory():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        local_database = PROJECT_ROOT / "data" / "reviews.db"
        local_database.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{local_database.as_posix()}"
    else:
        database_url = normalize_database_url(database_url)

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    # Create tables that do not already exist.
    Base.metadata.create_all(engine)

    # Add the analysis_result column to existing installations.
    if "analysis_result" not in {
        column["name"]
        for column in inspect(engine).get_columns("review_sessions")
    }:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE review_sessions "
                "ADD COLUMN analysis_result JSON"
            )

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def create_review_session(
    analysis_id: str,
    contract_filename: str,
    policy_filename: str,
    items: list[dict],
    analysis_result: dict | None = None,
) -> dict:
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        record = ReviewSessionRecord(
            analysis_id=analysis_id,
            contract_filename=contract_filename,
            policy_filename=policy_filename,
            items=items,
            analysis_result=analysis_result,
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "analysis_id": record.analysis_id,
            "contract_filename": record.contract_filename,
            "policy_filename": record.policy_filename,
            "items": record.items,
            "analysis_result": record.analysis_result,
            "created_at": record.created_at,
        }


def list_review_sessions(limit: int = 20) -> list[dict]:
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        records = db.scalars(
            select(ReviewSessionRecord)
            .order_by(
                ReviewSessionRecord.created_at.desc()
            )
            .limit(limit)
        ).all()

        return [
            {
                "analysis_id": record.analysis_id,
                "contract_filename": record.contract_filename,
                "policy_filename": record.policy_filename,
                "created_at": record.created_at,
            }
            for record in records
        ]


def get_review_session(
    analysis_id: str,
) -> dict | None:
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        record = db.get(
            ReviewSessionRecord,
            analysis_id,
        )

        if record is None:
            return None

        decisions = db.scalars(
            select(ReviewDecisionRecord).where(
                ReviewDecisionRecord.analysis_id
                == analysis_id
            )
        ).all()

        # Restore the stored analysis response.
        result = dict(record.analysis_result or {})

        # Database session metadata and reviewer decisions
        # are authoritative.
        result.update({
            "analysis_id": record.analysis_id,
            "contract_filename": record.contract_filename,
            "policy_filename": record.policy_filename,
            "created_at": record.created_at,
            "items": record.items,
            "decisions": [
                {
                    "item_id": item.item_id,
                    "decision": item.decision,
                    "comment": item.comment,
                    "updated_at": item.updated_at,
                }
                for item in decisions
            ],
        })

        return result


def save_review_decision(
    analysis_id: str,
    item_id: str,
    decision: str,
    comment: str | None = None,
) -> dict | None:
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        review = db.get(
            ReviewSessionRecord,
            analysis_id,
        )

        if review is None:
            return None

        item_exists = any(
            item.get("item_id") == item_id
            for item in review.items
        )

        if not item_exists:
            return None

        record = db.scalars(
            select(ReviewDecisionRecord).where(
                ReviewDecisionRecord.analysis_id
                == analysis_id,
                ReviewDecisionRecord.item_id == item_id,
            )
        ).first()

        if record is None:
            record = ReviewDecisionRecord(
                analysis_id=analysis_id,
                item_id=item_id,
                decision=decision,
                comment=comment,
            )
            db.add(record)
        else:
            record.decision = decision
            record.comment = comment
            record.updated_at = datetime.now(
                timezone.utc
            )

        db.commit()
        db.refresh(record)

        return {
            "analysis_id": record.analysis_id,
            "item_id": record.item_id,
            "decision": record.decision,
            "comment": record.comment,
            "updated_at": record.updated_at,
        }
