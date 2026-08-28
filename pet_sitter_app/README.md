# PawConnect

A web app connecting pet owners with pet sitters: sitters list their services, rates, and the
pet types they accept; owners search and send booking requests; both sides message about a
booking and owners leave a review once it's completed.

FastAPI backend (REST API + SQLite via SQLAlchemy) with a small dependency-free HTML/JS frontend
served by the same app.

## Features

- Email/password auth (JWT) with two roles: pet owner and pet sitter
- Sitters manage a profile: bio, hourly rate, years of experience, services offered
  (dog walking, boarding, drop-in visits, daycare, house sitting), and accepted pet types
- Owners manage a list of pets and search/filter sitters by city, service, pet type, and max rate
- Booking request workflow: `pending → accepted/declined`, then `accepted → completed/cancelled`,
  with role-appropriate transitions enforced by the API
- Per-booking messaging thread between the owner and sitter
- Owners leave a 1-5 star review with a comment once a booking is `completed`; sitter profiles
  show the average rating and review count

## Setup

```bash
cd pet_sitter_app
pip install -r requirements-dev.txt   # includes runtime deps + pytest/httpx for tests
```

## Run

```bash
python run.py
```

Then open http://localhost:8000 in a browser. The API is mounted under `/api/*`; interactive docs
are available at http://localhost:8000/docs.

By default data is stored in a local `pet_sitter.db` SQLite file (gitignored). Override with the
`PET_SITTER_DB_URL` environment variable, and set `PET_SITTER_SECRET_KEY` to a stable secret in
any environment where you need JWTs to survive a restart (otherwise a random key is generated per
process).

## Tests

```bash
python -m pytest tests/
```

Tests exercise the full API (auth, sitter profiles/search, the booking lifecycle, messaging, and
reviews) against an isolated in-memory-style SQLite database per test — no network required.

## Project layout

```
pet_sitter_app/
  app/
    main.py          FastAPI app, mounts the API routers and the static frontend
    models.py        SQLAlchemy models (User, SitterProfile, Pet, Booking, Message, Review)
    schemas.py        Pydantic request/response schemas
    security.py       Password hashing (PBKDF2) and JWT issuing/verification
    deps.py            Auth dependencies (current user, role checks)
    routers/           auth, sitters, pets, bookings, reviews
  frontend/           Static single-page app (no build step) consuming the API
  tests/              pytest suite using FastAPI's TestClient
```
