"""FastAPI app."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from telogify.api.routes import router
from telogify.config import require_signup_secrets, settings

# Refuses to boot in production without the signup secrets, rather than serving a signup form
# with no bot defense and no working unsubscribe tokens.
require_signup_secrets()

app = FastAPI(title="Telogify")

# Was allow_origins=["*"], which shipped to production with a note to fix it. Now that POSTing
# here sends real email, the wildcard is no longer defensible: scoped to the frontend origin
# plus the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Vercel mints a new hostname per deployment, so a preview cannot be listed ahead of time.
    # Unset in production; see config.cors_origin_regex for why it must stay project-scoped.
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
