# Google Drive Integration Setup

This guide walks you through configuring Jason Studio to upload customer
photo zip files to Google Drive, so you can share download links instead of
hosting files locally.

Two authentication modes are supported:

- **OAuth2 (recommended)** — for personal Gmail accounts. You authorize once
  in the browser; a refresh token is saved for subsequent uploads.
- **Service account** — for Google Workspace organizations using Shared Drives.

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click **Select a project** (top bar) then **New Project**.
3. Name it (e.g. `jasonstudio`) and click **Create**.
4. Make sure the new project is selected in the top bar.

## 2. Enable the Google Drive API

1. In the left sidebar, go to **APIs & Services > Library**.
2. Search for **Google Drive API**.
3. Click on it and press **Enable**.

## 3. Create OAuth2 credentials (recommended)

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. If prompted, configure the **OAuth consent screen** first:
   - Choose **External** user type.
   - Fill in the app name (e.g. `Jason Studio`) and your email.
   - Add yourself as a test user (your Gmail address).
   - Save and go back to creating credentials.
4. For **Application type**, choose **Desktop app**.
5. Name it (e.g. `jasonstudio-desktop`) and click **Create**.
6. Click **Download JSON** and save it somewhere safe (e.g.
   `~/.config/jasonstudio/client_secrets.json`).
   **Do not commit this file to git.**

## 4. Create a Google Drive folder

1. In your Google Drive, create a folder (e.g. `JasonStudio Downloads`).
2. Open the folder and copy its ID from the URL:
   `https://drive.google.com/drive/folders/FOLDER_ID_HERE`

## 5. Configure Django settings

Add these variables to your `.env` file:

```
GOOGLE_DRIVE_CLIENT_SECRETS_FILE=~/.config/jasonstudio/client_secrets.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

Optionally set a custom token storage path (defaults to the same directory
as the client secrets file):

```
GOOGLE_DRIVE_TOKEN_FILE=~/.config/jasonstudio/google-drive-token.json
```

## 6. Authorize (first run)

1. Start the dev server: `uv run --dev python -m django runserver --settings=jasonstudio.settings.debug`
2. Navigate to an order with photos.
3. Click **Upload to Google Drive**.
4. A browser window opens — log in with your Google account and grant
   Drive access.
5. The token is saved automatically. Subsequent uploads will not require
   browser authorization.

## 7. Verify

After authorization, the upload should complete and you'll see a success
message with a Google Drive download link. The link is also stored in
the order notes.

## How it works

- The app creates a zip of the customer's digital delivery photos.
- It uploads the zip to your Google Drive folder via the Drive API.
- It sets the file permissions to "anyone with the link can view".
- The resulting Google Drive download link is stored in the order notes
  and displayed in a success message.
- The link can then be included in emails to the customer.

## Costs

The Google Drive API is free for the volumes a photography studio would use.
No billing account is required unless you exceed the free-tier quotas
(which are very generous for file uploads). Storage uses your personal
Google Drive quota (15 GB free).

---

## Alternative: Service account (Google Workspace only)

Service accounts have no Drive storage quota of their own. They only work
with **Shared Drives**, which require a Google Workspace subscription.

### Setup

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > Service Account**.
3. Give it a name (e.g. `jasonstudio-drive`) and click **Create and Continue**.
4. Skip the optional role/access steps — click **Done**.
5. On the Credentials page, click the service account you just created.
6. Go to the **Keys** tab.
7. Click **Add Key > Create new key > JSON** and click **Create**.
8. Save the `.json` file somewhere safe (e.g.
   `~/.config/jasonstudio/google-drive-credentials.json`).
   **Do not commit this file to git.**
9. Create a **Shared Drive** in Google Workspace and add the service
   account email as a Contributor.

### .env configuration

```
GOOGLE_DRIVE_CREDENTIALS_FILE=~/.config/jasonstudio/google-drive-credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_shared_drive_folder_id_here
```

Do **not** set `GOOGLE_DRIVE_CLIENT_SECRETS_FILE` — if both are present,
OAuth2 takes precedence.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Google Drive is not configured" | Check that `GOOGLE_DRIVE_CLIENT_SECRETS_FILE` (or `GOOGLE_DRIVE_CREDENTIALS_FILE`) and `GOOGLE_DRIVE_FOLDER_ID` are set, and that the credentials file exists at the specified path. |
| Browser auth window doesn't open | Make sure you're running on a machine with a browser. The OAuth2 flow opens `localhost` to complete authorization. |
| "403 storageQuotaExceeded" with service account | Service accounts have no personal Drive quota. Use OAuth2 instead, or switch to a Shared Drive with Google Workspace. |
| "403 Forbidden" on upload | For OAuth2: ensure the folder belongs to the authorized Google account. For service account: re-share the Shared Drive with the service account email as Contributor. |
| Token expired / invalid | Delete the token file (see `GOOGLE_DRIVE_TOKEN_FILE`) and re-authorize by clicking Upload to Google Drive again. |
