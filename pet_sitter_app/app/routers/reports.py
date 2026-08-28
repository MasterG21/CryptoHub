from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

TARGET_MODELS = {
    models.ReportTargetType.message: models.Message,
    models.ReportTargetType.review: models.Review,
    models.ReportTargetType.user: models.User,
}


@router.post("", response_model=schemas.ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: schemas.ReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    target_model = TARGET_MODELS[payload.target_type]
    target = db.query(target_model).filter(target_model.id == payload.target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"{payload.target_type.value} not found")

    report = models.Report(
        reporter_id=current_user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/me", response_model=list[schemas.ReportOut])
def list_my_reports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Report)
        .filter(models.Report.reporter_id == current_user.id)
        .order_by(models.Report.created_at.desc())
        .all()
    )
