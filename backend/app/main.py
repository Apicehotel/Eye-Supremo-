from .database import Base, engine
from .routers.api import router
from .routers.invoice_builder import router as invoice_builder_router
from .routers.warehouse import router as warehouse_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title="RandFatture API", version="1.2.0", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(invoice_builder_router)
app.include_router(warehouse_router)
