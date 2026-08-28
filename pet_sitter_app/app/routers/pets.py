from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role

router = APIRouter(prefix="/api/pets", tags=["pets"])


@router.get("", response_model=List[schemas.PetOut])
def list_my_pets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.owner)),
):
    return db.query(models.Pet).filter(models.Pet.owner_id == current_user.id).all()


@router.post("", response_model=schemas.PetOut, status_code=status.HTTP_201_CREATED)
def create_pet(
    payload: schemas.PetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.owner)),
):
    pet = models.Pet(owner_id=current_user.id, **payload.model_dump())
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pet(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.owner)),
):
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id, models.Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    db.delete(pet)
    db.commit()
    return None
