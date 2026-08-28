import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    owner = "owner"
    sitter = "sitter"


class BookingStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    completed = "completed"


class ServiceType(str, enum.Enum):
    dog_walking = "dog_walking"
    boarding = "boarding"
    drop_in_visit = "drop_in_visit"
    daycare = "daycare"
    house_sitting = "house_sitting"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    city = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sitter_profile = relationship(
        "SitterProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    pets = relationship("Pet", back_populates="owner", cascade="all, delete-orphan")


class SitterProfile(Base):
    __tablename__ = "sitter_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    bio = Column(Text, default="")
    hourly_rate = Column(Float, nullable=False, default=0.0)
    years_experience = Column(Integer, default=0)
    services = Column(String(500), default="")  # comma-separated ServiceType values
    accepted_pet_types = Column(String(500), default="")  # comma-separated species names
    city = Column(String(255), nullable=True)

    user = relationship("User", back_populates="sitter_profile")


class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    species = Column(String(100), nullable=False)
    breed = Column(String(100), nullable=True)
    notes = Column(Text, default="")

    owner = relationship("User", back_populates="pets")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=True)
    service_type = Column(SAEnum(ServiceType), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(SAEnum(BookingStatus), default=BookingStatus.pending, nullable=False)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id])
    sitter = relationship("User", foreign_keys=[sitter_id])
    pet = relationship("Pet")
    messages = relationship("Message", back_populates="booking", cascade="all, delete-orphan")
    review = relationship("Review", back_populates="booking", uselist=False, cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="messages")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_review_booking"),)

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    sitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="review")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
