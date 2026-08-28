from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import auth, bookings, pets, reviews, sitters

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PawConnect API",
    description="Connect pet owners with pet sitters: search, booking requests, messaging, and reviews.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sitters.router)
app.include_router(pets.router)
app.include_router(bookings.router)
app.include_router(reviews.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
