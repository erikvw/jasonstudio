# Google Drive Integration Setup

This guide walks you through configuring Jason Studio to upload customer
photo zip files to Google Drive, so you can share download links instead of
hosting files locally.

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click **Select a project** (top bar) then **New Project**.
3. Name it (e.g. `jasonstudio`) and click **Create**.
4. Make sure the new project is selected in the top bar.

## 2. Enable the Google Drive API

1. In the left sidebar, go to **APIs & Services > Library**.
2. Search for **Google Drive API**.
3. Click on it and press **Enable**.

## 3. Create a service account

A service account is a special Google account your app uses to authenticate
without requiring a user login.

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > Service Account**.
3. Give it a name (e.g. `jasonstudio-drive`) and click **Create and Continue**.
4. Skip the optional role/access steps — click **Done**.
5. On the Credentials page, click the service account you just created.
6. Go to the **Keys** tab.
7. Click **Add Key > Create new key > JSON** and click **Create**.
8. A `.json` file will download. Save it somewhere safe (e.g.
   `~/.config/jasonstudio/google-drive-credentials.json`).
   **Do not commit this file to git.**

## 4. Create and share a Google Drive folder

1. In your personal Google Drive, create a folder (e.g. `JasonStudio Downloads`).
2. Right-click the folder and choose **Share**.
3. Paste the service account email address (it looks like
   `jasonstudio-drive@your-project.iam.gserviceaccount.com` — find it on
   the service account details page in GCP console).
4. Give it **Editor** access and click **Send**.
5. Open the folder and copy its ID from the URL:
   `https://drive.google.com/drive/folders/FOLDER_ID_HERE`

## 5. Configure Django settings

Add these two variables to your `.env` file:

```
GOOGLE_DRIVE_CREDENTIALS_FILE=/path/to/google-drive-credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

Or set them as environment variables.

## 6. Verify

1. Start the dev server: `uv run --dev python -m django runserver --settings=jasonstudio.settings.debug`
2. Navigate to an order with photos.
3. In the **Downloads** card, you should see an **Upload to Google Drive** button.
4. Click it — the zip file will be uploaded and a shareable link will be
   stored in the order notes and shown as a success message.

## How it works

- The app creates a zip of the customer's digital delivery photos.
- It uploads the zip to the shared Google Drive folder via the Drive API.
- It sets the file permissions to "anyone with the link can view".
- The resulting Google Drive download link is stored in the order notes
  and displayed in a success message.
- The link can then be included in emails to the customer.

## Costs

The Google Drive API is free for the volumes a photography studio would use.
No billing account is required unless you exceed the free-tier quotas
(which are very generous for file uploads).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Google Drive is not configured" | Check that both `GOOGLE_DRIVE_CREDENTIALS_FILE` and `GOOGLE_DRIVE_FOLDER_ID` are set, and that the credentials file exists at the specified path. |
| "403 Forbidden" on upload | The service account doesn't have access to the folder. Re-share the folder with the service account email as an Editor. |
| "File not found" for credentials | The path in `GOOGLE_DRIVE_CREDENTIALS_FILE` is wrong or the file was moved. Use an absolute path. |
