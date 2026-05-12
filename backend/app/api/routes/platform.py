from fastapi import APIRouter

from app.schemas.dashboard import PlatformStatus
from app.services.repo_inventory import scan_legacy_repo_status

router = APIRouter()


@router.get('/status', response_model=PlatformStatus)
def platform_status() -> PlatformStatus:
    return scan_legacy_repo_status()
