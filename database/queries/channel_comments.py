import datetime
from typing import Optional, List, Any, Tuple

from sqlalchemy import select, false, null, true
from sqlalchemy.orm import Session
from telegram import Message

import utilities
from config import config
from database.models import ChannelComment


def get(session: Session, chat_id: int, message_id: int) -> Optional[ChannelComment]:
    channel_comment: ChannelComment = session.query(ChannelComment).filter(ChannelComment.chat_id == chat_id, ChannelComment.message_id == message_id).one_or_none()

    return channel_comment