from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

ALLOWED_TRANSITIONS = {
    models.BookingStatus.pending: {
        models.BookingStatus.accepted,
        models.BookingStatus.declined,
        models.BookingStatus.cancelled,
    },
    models.BookingStatus.accepted: {models.BookingStatus.completed, models.BookingStatus.cancelled},
}

SITTER_ONLY_TRANSITIONS = {
    models.BookingStatus.accepted,
    models.BookingStatus.declined,
    models.BookingStatus.completed,
}


def _get_booking_for_user(db: Session, booking_id: int, user: models.User) -> models.Booking:
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if user.id not in (booking.owner_id, booking.sitter_id):
        raise HTTPException(status_code=403, detail="Not part of this booking")
    return booking


@router.post("", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != models.UserRole.owner:
        raise HTTPException(status_code=403, detail="Only pet owners can request bookings")

    sitter = (
        db.query(models.User)
        .filter(models.User.id == payload.sitter_id, models.User.role == models.UserRole.sitter)
        .first()
    )
    if not sitter:
        raise HTTPException(status_code=404, detail="Sitter not found")

    if payload.pet_id is not None:
        pet = (
            db.query(models.Pet)
            .filter(models.Pet.id == payload.pet_id, models.Pet.owner_id == current_user.id)
            .first()
        )
        if not pet:
            raise HTTPException(status_code=404, detail="Pet not found")

    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    booking = models.Booking(
        owner_id=current_user.id,
        sitter_id=payload.sitter_id,
        pet_id=payload.pet_id,
        service_type=payload.service_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        notes=payload.notes,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("", response_model=List[schemas.BookingOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Booking)
        .filter(or_(models.Booking.owner_id == current_user.id, models.Booking.sitter_id == current_user.id))
        .order_by(models.Booking.created_at.desc())
        .all()
    )


@router.get("/{booking_id}", response_model=schemas.BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_booking_for_user(db, booking_id, current_user)


@router.patch("/{booking_id}", response_model=schemas.BookingOut)
def update_booking_status(
    booking_id: int,
    payload: schemas.BookingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    booking = _get_booking_for_user(db, booking_id, current_user)
    new_status = payload.status
    allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400, detail=f"Cannot move booking from {booking.status.value} to {new_status.value}"
        )
    if new_status in SITTER_ONLY_TRANSITIONS and current_user.id != booking.sitter_id:
        raise HTTPException(status_code=403, detail="Only the sitter can perform this transition")

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/{booking_id}/messages", response_model=List[schemas.MessageOut])
def list_messages(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_booking_for_user(db, booking_id, current_user)
    return (
        db.query(models.Message)
        .filter(models.Message.booking_id == booking_id)
        .order_by(models.Message.created_at)
        .all()
    )


@router.post("/{booking_id}/messages", response_model=schemas.MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    booking_id: int,
    payload: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_booking_for_user(db, booking_id, current_user)
    message = models.Message(booking_id=booking_id, sender_id=current_user.id, body=payload.body)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
