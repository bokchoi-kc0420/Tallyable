"""Hosted start-up only. Streamlit's Google sign-in reads .streamlit/secrets.toml, but the host hands
the app env vars, so this writes the [auth] section from them before the app starts (see Procfile).
Until GOOGLE_CLIENT_ID is set there is no sign-in. Locally it never runs."""
import json
import os
from pathlib import Path

if "GOOGLE_CLIENT_ID" not in os.environ:
    raise SystemExit
ENV = {"cookie_secret": "AUTH_COOKIE_SECRET", "client_id": "GOOGLE_CLIENT_ID", "client_secret": "GOOGLE_CLIENT_SECRET"}
redirect = os.getenv("AUTH_REDIRECT_URI") or os.environ["APP_URL"] + "/oauth2callback"  # APP_URL: DigitalOcean
lines = ["[auth]", f"redirect_uri = {json.dumps(redirect)}",
         *(f"{key} = {json.dumps(os.environ[var])}" for key, var in ENV.items()),
         'server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"']
(Path(__file__).parent.parent / ".streamlit" / "secrets.toml").write_text("\n".join(lines) + "\n")
