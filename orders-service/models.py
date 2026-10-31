
from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone

from database import Base


class OrderDB(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, index=True)
    space_id = Column(Integer, nullable=False)
    space_name = Column(String, nullable=False)
    user_email = Column(String, nullable=False)
    hours = Column(Integer, nullable=False)
    price_per_hour = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
