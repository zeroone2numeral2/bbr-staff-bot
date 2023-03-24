from .models import User, Chat, UserMessage, ChatAdministrator, Setting
from .base import Base, engine

Base.metadata.create_all(engine)
