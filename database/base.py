from contextlib import contextmanager
from typing import cast

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm import scoped_session

engine = create_engine("sqlite:///bot.db")
SessionClass = sessionmaker(bind=engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionClass()
    try:
        yield session
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(connection=None) -> Session:
    """get a new db session"""

    session = scoped_session(sessionmaker(bind=engine))
    return cast(Session, session)


Base = declarative_base()
