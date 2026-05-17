import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from api.webhooks import twilio, telnyx, flutterwave
from api.routes import admin
from database.connection import engine, Base
from utils.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    yield
    logger.info("Shutting down...")


app = FastAPI(title="PrimeDigits API", lifespan=lifespan)

app.include_router(twilio.router)
app.include_router(telnyx.router)
app.include_router(flutterwave.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return PlainTextResponse("PrimeDigits API is running.")
