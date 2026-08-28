from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role

router = APIRouter(prefix="/api/sitters", tags=["sitters"])


def _stats(db: Session, sitter_user_id: int):
    avg_rating, count = (
        db.query(func.avg(models.Review.rating), func.count(models.Review.id))
        .filter(models.Review.sitter_id == sitter_user_id)
        .one()
    )
    return (round(avg_rating, 2) if avg_rating is not None else None, count or 0)


@router.get("", response_model=List[schemas.SitterProfileOut])
def list_sitters(
    city: Optional[str] = None,
    service: Optional[models.ServiceType] = None,
    pet_type: Optional[str] = None,
    max_rate: Optional[float] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.SitterProfile)
    if city:
        query = query.filter(models.SitterProfile.city.ilike(f"%{city}%"))
    if max_rate is not None:
        query = query.filter(models.SitterProfile.hourly_rate <= max_rate)
    if service:
        query = query.filter(models.SitterProfile.services.contains(service.value))
    if pet_type:
        query = query.filter(models.SitterProfile.accepted_pet_types.ilike(f"%{pet_type.lower()}%"))

    profiles = query.all()
    return [
        schemas.SitterProfileOut.from_orm_with_stats(p, *_stats(db, p.user_id))
        for p in profiles
    ]


@router.get("/{sitter_user_id}", response_model=schemas.SitterProfileOut)
def get_sitter(sitter_user_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.SitterProfile).filter(models.SitterProfile.user_id == sitter_user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Sitter not found")
    return schemas.SitterProfileOut.from_orm_with_stats(profile, *_stats(db, sitter_user_id))


@router.put("/me", response_model=schemas.SitterProfileOut)
def update_my_profile(
    payload: schemas.SitterProfileIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.sitter)),
):
    profile = db.query(models.SitterProfile).filter(models.SitterProfile.user_id == current_user.id).first()
    if not profile:
        profile = models.SitterProfile(user_id=current_user.id)
        db.add(profile)

    profile.bio = payload.bio
    profile.hourly_rate = payload.hourly_rate
    profile.years_experience = payload.years_experience
    profile.services = ",".join(s.value for s in payload.services)
    profile.accepted_pet_types = ",".join(p.strip().lower() for p in payload.accepted_pet_types if p.strip())
    profile.city = payload.city
    db.commit()
    db.refresh(profile)
    return schemas.SitterProfileOut.from_orm_with_stats(profile, *_stats(db, current_user.id))


@router.get("/{sitter_user_id}/reviews", response_model=List[schemas.ReviewOut])
def sitter_reviews(sitter_user_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Review)
        .filter(models.Review.sitter_id == sitter_user_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
