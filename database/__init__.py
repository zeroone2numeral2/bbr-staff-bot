from .base import Base, engine

Base.metadata.create_all(engine)
