"""Hosted start-up only. Streamlit's Google sign-in reads .streamlit/secrets.toml, but Doppler hands
the app env vars, so this writes the [auth] section from them before the app starts (see Procfile).
Locally it never runs and there is no sign-in."""
import json
import os
from pathlib import Path

ENV = {"redirect_uri": "AUTH_REDIRECT_URI", "cookie_secret": "AUTH_COOKIE_SECRET",
       "client_id": "GOOGLE_CLIENT_ID", "client_secret": "GOOGLE_CLIENT_SECRET"}
lines = ["[auth]", *(f"{key} = {json.dumps(os.environ[var])}" for key, var in ENV.items()),
         'server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"']
(Path(__file__).parent.parent / ".streamlit" / "secrets.toml").write_text("\n".join(lines) + "\n")
