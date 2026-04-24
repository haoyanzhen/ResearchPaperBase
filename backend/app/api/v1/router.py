from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.config import router as config_router
from app.api.v1.construction import router as construction_router
from app.api.v1.dialogues import router as dialogues_router
from app.api.v1.projects import recommendations_router, router as projects_router
from app.api.v1.review import router as review_router
from app.api.v1.tasks import router as tasks_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(config_router)
router.include_router(projects_router)
router.include_router(recommendations_router)
router.include_router(tasks_router)
router.include_router(construction_router)
router.include_router(review_router)
router.include_router(dialogues_router)
router.include_router(admin_router)
