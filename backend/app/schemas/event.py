from pydantic import BaseModel


class EventFeedItem(BaseModel):
    title: str
    source: str
    timestamp: str
    sentiment: str
    summary: str


class EventFeedResponse(BaseModel):
    items: list[EventFeedItem]
