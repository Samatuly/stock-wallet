from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_quote_service
from app.models import JournalEntry
from app.schemas import JournalCreate, JournalOut
from app.services.quote_provider import QuoteService

router = APIRouter(prefix="/journal", tags=["journal"])


def _with_current(rows: list[JournalEntry], quotes: QuoteService) -> list[JournalOut]:
    current = quotes.get_quotes([(r.ticker, r.market) for r in rows])
    result = []
    for r in rows:
        out = JournalOut.model_validate(r)
        q = current.get(r.ticker)
        if q is not None:
            out.current_price = q.price
            if r.price_at_entry:
                out.change_percent = round((q.price - r.price_at_entry) / r.price_at_entry * 100, 2)
        result.append(out)
    return result


@router.get("", response_model=list[JournalOut])
def list_entries(
    ticker: str | None = Query(None),
    db: Session = Depends(get_db),
    quotes: QuoteService = Depends(get_quote_service),
):
    stmt = select(JournalEntry).order_by(JournalEntry.created_at.desc())
    if ticker:
        stmt = stmt.where(JournalEntry.ticker == ticker.strip().upper())
    return _with_current(list(db.scalars(stmt).all()), quotes)


@router.post("", response_model=JournalOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    data: JournalCreate,
    db: Session = Depends(get_db),
    quotes: QuoteService = Depends(get_quote_service),
):
    quote = quotes.get_quote(data.ticker, data.market)  # None — запись всё равно сохраняется
    entry = JournalEntry(
        **data.model_dump(),
        price_at_entry=quote.price if quote else None,
        currency=quote.currency if quote else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _with_current([entry], quotes)[0]


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
