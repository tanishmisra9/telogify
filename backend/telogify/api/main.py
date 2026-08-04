"""FastAPI app."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from telogify.api.routes import router

app = FastAPI(title="Telogify")

# ponytail: open CORS for dev (Vite on :5173). Restrict to the deployed origin in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
