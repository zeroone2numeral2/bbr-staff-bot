from .models import User, Chat, UserMessage, ChatAdministrator
from .base import Base, engine

Base.metadata.create_all(engine)
