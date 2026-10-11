"""Loopback-only Prompt 17 ASGI harness for the certified disposable database.

It composes the real FastAPI routers and Phase 11 coordinator, while routing
artifact lookup to the disposable Prompt 16 root. Do not deploy this module.
"""

from __future__ import annotations

from pathlib import Path

from app.dependencies import get_database_path
from app import main as main_module
from app.routers import potential_customer_search as search_router

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "output" / "lookalike_stage16_2_measurements"
DATABASE = SCRATCH / "certification.db"
if not DATABASE.is_file():
    raise RuntimeError("Prompt 17 requires the disposable certified database.")

app = main_module.app
app.dependency_overrides[get_database_path] = lambda: DATABASE
main_module.PROJECT_ROOT = SCRATCH
search_router.PROJECT_ROOT = SCRATCH

_preflight = search_router.exact_similarity_preflight
_detail = search_router.results_service.get_result_detail
_export = search_router.export_service.stream_phase11_result_export_csv


def _scratch_preflight(database_path, **kwargs):
    return _preflight(database_path, project_root=SCRATCH, **kwargs)


def _scratch_detail(database_path, search_run_id, **kwargs):
    return _detail(database_path, search_run_id, project_root=SCRATCH, **kwargs)


def _scratch_export(database_path, **kwargs):
    return _export(database_path, project_root=SCRATCH, **kwargs)


search_router.exact_similarity_preflight = _scratch_preflight
search_router.results_service.get_result_detail = _scratch_detail
search_router.export_service.stream_phase11_result_export_csv = _scratch_export
