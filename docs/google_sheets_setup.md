# Connect Tallyable to a Google Sheet (Windows)

This takes about 15 minutes and is free. You will make a "robot" Google account (a **service account**), give it access to one test spreadsheet, and point Tallyable at that spreadsheet.

**Use fake data only.** Make a new, empty test sheet. Don't connect the club's real sheets.

**Use your personal Gmail.** School accounts (like UC Davis) often block the key download in step 3.

## 1. Make a Google Cloud project
1. Go to https://console.cloud.google.com and sign in.
2. At the top, click the project picker, then **New project**. Name it `tallyable` and click **Create**. You don't need billing for this.
3. Make sure `tallyable` is selected in the project picker.

## 2. Turn on the Sheets and Drive APIs
1. Search the top bar for **Google Sheets API**, open it, and click **Enable**.
2. Do the same for **Google Drive API**.

## 3. Create the service account and its key
1. Search for **Service accounts** and open it (under IAM & Admin).
2. Click **Create service account**. Name it `tallyable-bot`, click **Create and continue**, skip the optional role and user steps, and click **Done**.
3. Click the new account, open the **Keys** tab, and choose **Add key**, then **Create new key**, then **JSON**, then **Create**. A `.json` file downloads.
4. Move that file into your Tallyable folder and rename it to `service_account.json`. Git already ignores this name, so it won't be committed.

The key file works like a password. Never commit it, email it, or paste it in chat. If it leaks, delete the key on the Keys tab and make a new one.

## 4. Make a test sheet and share it with the bot
1. Go to https://sheets.new and name the sheet `Tallyable TEST (fake data)`.
2. Open `service_account.json` in VS Code and copy the `client_email` value. It looks like `tallyable-bot@tallyable-123456.iam.gserviceaccount.com`.
3. In the sheet, click **Share**, paste that email, choose **Editor**, uncheck "Notify people", and click **Share**.
4. Copy the sheet ID from the address bar. It's the long part between `/d/` and `/edit`:
   `https://docs.google.com/spreadsheets/d/`**`1AbC...xyz`**`/edit`

## 5. Tell Tallyable about it
Add these two lines to `.env` in the Tallyable folder:
```
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
TALLYABLE_SHEET_ID=1AbC...xyz
```

## 6. Try it
```
pip install -r requirements.txt
python -m streamlit run app.py
```
Draft the fake event, approve a few receipts, then go to **3. Summary**, type some fake income, and click **Push to Google Sheets**. The sheet gets four tabs:

| Tab | What it is | Edit it? |
| --- | --- | --- |
| Transactions | One row per approved line item. This is the record the tool trusts. | Only to fix mistakes |
| Events | One row per event, with income by source | Only to fix mistakes |
| Balance Sheet | Your sideways layout, one block per event | No, it's rebuilt on every push |
| Ledger | Date, description, assets, liabilities, running totals, balance | No, it's rebuilt on every push |

Clicking Push again won't double-count anything. Receipts that are already posted are skipped.

## If it fails
- **"Could not open the Google Sheet" / SpreadsheetNotFound:** the sheet ID is wrong, or you didn't share the sheet with the `client_email`.
- **403 / PERMISSION_DENIED:** one of the two APIs in step 2 isn't enabled, or the bot only has Viewer access.
- **FileNotFoundError:** `service_account.json` isn't in the Tallyable folder, or the name in `.env` doesn't match.
- If the Summary screen says "Push to local CSV", the two `.env` lines are missing.
