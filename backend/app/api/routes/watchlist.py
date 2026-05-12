from fastapi import APIRouter, HTTPException

from app.schemas.watchlist import WatchlistCreate, WatchlistItem, WatchlistResponse
from app.services.local_store import get_local_store

router = APIRouter()


@router.get('', response_model=WatchlistResponse)
def list_watchlist() -> WatchlistResponse:
    return WatchlistResponse(items=get_local_store().list_watchlist())


@router.post('', response_model=WatchlistItem, status_code=201)
def create_watchlist_item(payload: WatchlistCreate) -> WatchlistItem:
    return get_local_store().add_watchlist_item(payload)


@router.delete('/{item_id}', status_code=204)
def delete_watchlist_item(item_id: int) -> None:
    deleted = get_local_store().delete_watchlist_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='watchlist item not found')
