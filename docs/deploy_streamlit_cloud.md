# Put Tallyable online (Streamlit Community Cloud)

This gives you a link like `https://tallyable.streamlit.app` to show in interviews. It's free and takes about 10 minutes. Nothing goes online until you click Deploy yourself.

## Before you start
- **Set a password.** The app can spend your API credit, so never deploy it without `APP_PASSWORD`.
- **Use fake data only.** The repo is public, and the demo should only ever show the fake event.
- **Don't commit secrets.** Keys go in the Secrets box (step 3), never in a file you commit. Git already ignores `.env`, `service_account.json`, and `.streamlit/secrets.toml`.
- **Local files don't last online.** On the cloud, `output/` (the local CSV, the run log, and reimbursements) is wiped whenever the app restarts. Connect Google Sheets ([guide](google_sheets_setup.md)) if you want pushes to stick around.

## 1. Sign in
Go to https://share.streamlit.io and sign in with your GitHub account (`bokchoi-kc0420`). Allow it to see your repositories when asked.

## 2. Create the app
1. Click **Create app**, and choose to deploy from a GitHub repo.
2. Repository: `bokchoi-kc0420/Tallyable`. Branch: `main`. Main file path: `app.py`.
3. Pick a custom URL if you want, like `tallyable`.
4. Open **Advanced settings** and choose Python **3.12**.

## 3. Add the secrets
In Advanced settings, there's a **Secrets** box. Open [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example), copy it into the box, and fill it in:
- `APP_PASSWORD`: required. Make it long.
- `ANTHROPIC_API_KEY`: optional. If you leave it out, the demo uses the stub, which costs $0 and is a fine default for a public demo.
- `TALLYABLE_SHEET_ID` and the `[gcp_service_account]` block: optional. Copy each field from your `service_account.json`. Keep the `\n` characters in `private_key` exactly as they are.

You can change secrets later in the app's **Settings > Secrets**. The app restarts with the new values.

## 4. Deploy
Click **Deploy**. The first build takes a few minutes while it installs `requirements.txt`. When it finishes, open the link, enter the password, and run through the fake event.

## If something goes wrong
- **Build fails:** open **Manage app** (bottom right of the app page) to see the log. The last red lines usually name the problem.
- **"Demo mode" banner:** `ANTHROPIC_API_KEY` is missing or misspelled in Secrets. That is fine for a public demo; the stand-in still works.
- **Sheets error on Summary:** the sheet isn't shared with the service account's `client_email`, or a field in `[gcp_service_account]` was copied wrong.
- **The app is asleep:** free apps sleep when nobody visits for a while. Click the wake-up button and wait about a minute.

To turn it off, go to the app's menu at share.streamlit.io and choose **Delete**.
