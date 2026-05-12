from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=128)
    sector: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)


class WatchlistItem(WatchlistCreate):
    id: int
    created_at: str
    updated_at: str


class WatchlistResponse(BaseModel):
    items: list[WatchlistItem]
