"""
nAI Core Source Routes
Manage NAS folders that are indexed in place (admin), and list visible sources (users)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from ..config import Settings, get_config
from ..models.schemas import (
    ScanResult,
    ShareCandidateInfo,
    ShareDiscovery,
    SourceCreate,
    SourceInfo,
    SourceUpdate,
    User,
)
from ..nas import get_nas_adapter
from ..security import get_scope, require_admin, require_auth
from ..services.access import AccessScope
from ..services.sources import SourceError, SourceService, get_source_service
from ..utils.logging import get_logger

router = APIRouter(prefix="/sources", tags=["Sources"])
logger = get_logger(__name__)


@router.get("", response_model=list[SourceInfo])
def list_sources(
    user: User = Depends(require_auth),
    scope: AccessScope = Depends(get_scope),
    service: SourceService = Depends(get_source_service),
) -> list[SourceInfo]:
    """Sources you can search. Paths and scan details are only shown to admins."""
    if user.is_admin:
        return service.list_sources()
    return [
        s.model_copy(update={"exclude_patterns": [], "allowed_groups": [], "last_error": None})
        for s in service.list_sources(include_paths=False)
        if scope.allows(s.id)
    ]


@router.get("/discover", response_model=ShareDiscovery, dependencies=[Depends(require_admin)])
def discover_shares(
    settings: Settings = Depends(get_config),
    service: SourceService = Depends(get_source_service),
) -> ShareDiscovery:
    """Folders under the allowed roots that could be added as sources (from the NAS adapter)."""
    adapter = get_nas_adapter(settings)
    existing = [s.path for s in service.list_sources() if s.path]
    shares = adapter.discover_shares(settings.sources_allowed_roots, existing)
    return ShareDiscovery(
        platform=adapter.name,
        platform_name=adapter.display_name,
        capabilities=vars(adapter.capabilities),
        status=adapter.platform_status(),
        shares=[ShareCandidateInfo(**vars(s)) for s in shares],
    )


@router.post("", response_model=SourceInfo, status_code=201, dependencies=[Depends(require_admin)])
def create_source(
    data: SourceCreate,
    background: BackgroundTasks,
    service: SourceService = Depends(get_source_service),
) -> SourceInfo:
    """Add a folder. It is scanned right away in the background."""
    try:
        source = service.create(data)
    except SourceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if source.enabled:
        background.add_task(_scan_quietly, service, source.id)
    return source


def _scan_quietly(service: SourceService, source_id: int) -> None:
    try:
        service.scan(source_id)
    except Exception as e:
        logger.warning(f"Background scan of source {source_id} failed: {e}")


@router.patch("/{source_id}", response_model=SourceInfo, dependencies=[Depends(require_admin)])
def update_source(
    source_id: int, data: SourceUpdate, service: SourceService = Depends(get_source_service)
) -> SourceInfo:
    try:
        source = service.update(source_id, data)
    except SourceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/{source_id}", dependencies=[Depends(require_admin)])
def delete_source(source_id: int, service: SourceService = Depends(get_source_service)) -> dict:
    """Remove a source from nAI (its index entries). Files on disk are not touched."""
    if not service.delete(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True}


@router.post("/{source_id}/scan", dependencies=[Depends(require_admin)])
async def scan_source(
    source_id: int,
    background: BackgroundTasks,
    wait: bool = Query(False, description="Wait for the scan to finish and return its result"),
    service: SourceService = Depends(get_source_service),
) -> ScanResult | dict:
    """Rescan a source now (incremental: only changed files are re-indexed)."""
    if service.get(source_id) is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if service.is_scanning(source_id):
        raise HTTPException(status_code=409, detail="A scan of this source is already running")
    if not wait:
        background.add_task(_scan_quietly, service, source_id)
        return {"started": True}
    try:
        return await run_in_threadpool(service.scan, source_id)
    except SourceError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
