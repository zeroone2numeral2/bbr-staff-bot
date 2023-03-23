from .models import User, StaffChat, UserMessage, ChatAdministrator
from .base import Base, engine

Base.metadata.create_all(engine)
