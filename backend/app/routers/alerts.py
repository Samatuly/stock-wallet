from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_quote_service
from app.models import PriceAlert, utcnow
from app.schemas import AlertCreate, AlertOut
from app.services.quote_provider import QuoteService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def is_triggered(direction: str, target: float, price: float) -> bool:
    return price >= target if direction == "above" else price <= target


@router.get("", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db), quotes: QuoteService = Depends(get_quote_service)):
    rows = list(db.scalars(select(PriceAlert).order_by(PriceAlert.active.desc(), PriceAlert.created_at.desc())).all())
    current = quotes.get_quotes([(r.ticker, r.market) for r in rows if r.active])
    result = []
    for r in rows:
        out = AlertOut.model_validate(r)
        q = current.get(r.ticker)
        out.current_price = q.price if q else None
        result.append(out)
    return result


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    alert = PriceAlert(**data.model_dump())
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


# Статический путь /check объявлен до /{alert_id}, чтобы не быть принятым за id.
@router.post("/check", response_model=list[AlertOut])
def check_alerts(db: Session = Depends(get_db), quotes: QuoteService = Depends(get_quote_service)):
    """Сверяет активные алерты с текущими ценами и возвращает сработавшие сейчас.

    Фонового процесса нет: проверка идёт, пока приложение открыто в браузере
    (оно вызывает этот адрес при загрузке и каждые несколько минут).
    """
    active = list(db.scalars(select(PriceAlert).where(PriceAlert.active.is_(True))).all())
    current = quotes.get_quotes([(a.ticker, a.market) for a in active])
    fired = []
    for a in active:
        q = current.get(a.ticker)
        if q is None or not is_triggered(a.direction, a.target_price, q.price):
            continue
        a.active = False
        a.triggered_at = utcnow()
        a.triggered_price = q.price
        fired.append(a)
    if fired:
        db.commit()
    result = []
    for a in fired:
        out = AlertOut.model_validate(a)
        out.current_price = a.triggered_price
        result.append(out)
    return result


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(PriceAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Алерт не найден")
    db.delete(alert)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
