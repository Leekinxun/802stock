from pydantic import BaseModel


class MetricCard(BaseModel):
    label: str
    value: str
    hint: str
    tone: str = 'neutral'
