from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import BookingStatus, ServiceType, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole
    city: Optional[str] = None
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    city: Optional[str] = None
    phone: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SitterProfileIn(BaseModel):
    bio: str = ""
    hourly_rate: float = Field(ge=0)
    years_experience: int = Field(ge=0, default=0)
    services: List[ServiceType] = []
    accepted_pet_types: List[str] = []
    city: Optional[str] = None


class SitterProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user: UserOut
    bio: str
    hourly_rate: float
    years_experience: int
    services: List[str]
    accepted_pet_types: List[str]
    city: Optional[str] = None
    average_rating: Optional[float] = None
    review_count: int = 0

    @classmethod
    def from_orm_with_stats(cls, profile, average_rating, review_count):
        return cls.model_validate(
            {
                "id": profile.id,
                "user": profile.user,
                "bio": profile.bio,
                "hourly_rate": profile.hourly_rate,
                "years_experience": profile.years_experience,
                "services": [s for s in profile.services.split(",") if s],
                "accepted_pet_types": [p for p in profile.accepted_pet_types.split(",") if p],
                "city": profile.city,
                "average_rating": average_rating,
                "review_count": review_count,
            }
        )


class PetCreate(BaseModel):
    name: str
    species: str
    breed: Optional[str] = None
    notes: str = ""


class PetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    species: str
    breed: Optional[str] = None
    notes: str


class BookingCreate(BaseModel):
    sitter_id: int
    pet_id: Optional[int] = None
    service_type: ServiceType
    start_date: date
    end_date: date
    notes: str = ""


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner: UserOut
    sitter: UserOut
    pet: Optional[PetOut] = None
    service_type: ServiceType
    start_date: date
    end_date: date
    status: BookingStatus
    notes: str
    created_at: datetime


class MessageCreate(BaseModel):
    body: str = Field(min_length=1)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_id: int
    body: str
    created_at: datetime


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    reviewer: UserOut
    rating: int
    comment: str
    created_at: datetime
