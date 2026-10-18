from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Position
from app.schemas import ImportError_, ImportRequest, ImportResult, ImportRow, PositionCreate, PositionOut
from app.services.csv_import import parse_csv

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionOut])
def list_positions(db: Session = Depends(get_db)):
    return db.scalars(select(Position).order_by(Position.ticker, Position.buy_date)).all()


@router.post("", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
def create_position(data: PositionCreate, db: Session = Depends(get_db)):
    position = Position(**data.model_dump())
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


@router.post("/import", response_model=ImportResult)
def import_positions(body: ImportRequest, db: Session = Depends(get_db)):
    """Импорт из CSV. С dry_run=true только показывает, что будет добавлено.
    Позиции, которые уже есть (тот же тикер, количество, цена и дата), пропускаются."""
    parsed, errors = parse_csv(body.csv_text)
    existing = {
        (p.ticker, p.quantity, p.buy_price, p.buy_date) for p in db.scalars(select(Position)).all()
    }
    rows, imported = [], 0
    seen = set()
    for line, pos in parsed:
        key = (pos.ticker, pos.quantity, pos.buy_price, pos.buy_date)
        duplicate = key in existing or key in seen
        seen.add(key)
        rows.append(ImportRow(**pos.model_dump(), line=line, duplicate=duplicate))
        if not duplicate and not body.dry_run:
            db.add(Position(**pos.model_dump()))
            imported += 1
    if imported:
        db.commit()
    return ImportResult(
        rows=rows,
        errors=[ImportError_(line=l, message=m) for l, m in errors],
        imported=imported,
        skipped_duplicates=sum(1 for r in rows if r.duplicate),
    )


@router.put("/{position_id}", response_model=PositionOut)
def update_position(position_id: int, data: PositionCreate, db: Session = Depends(get_db)):
    position = db.get(Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    for field, value in data.model_dump().items():
        setattr(position, field, value)
    db.commit()
    db.refresh(position)
    return position


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(position_id: int, db: Session = Depends(get_db)):
    position = db.get(Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    db.delete(position)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
