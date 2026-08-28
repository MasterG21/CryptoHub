from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/bookings", tags=["reviews"])


@router.post("/{booking_id}/review", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    booking_id: int,
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the pet owner can leave a review")
    if booking.status != models.BookingStatus.completed:
        raise HTTPException(status_code=400, detail="Booking must be completed before it can be reviewed")
    if booking.review is not None:
        raise HTTPException(status_code=400, detail="Booking already reviewed")

    review = models.Review(
        booking_id=booking_id,
        sitter_id=booking.sitter_id,
        reviewer_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
