from fastapi import APIRouter, FastAPI
from . import search

router = APIRouter()

router.include_router(search.router)

web_api = FastAPI()
web_api.include_router(router)