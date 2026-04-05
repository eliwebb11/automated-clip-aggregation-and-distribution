# ClipSlop

A desktop app that automatically fetches top clips from Twitch and Kick and uploads them to YouTube Shorts, TikTok, and X (Twitter).


https://github.com/user-attachments/assets/8649fbd1-a258-4eb8-9ed4-14a530aaac85


---

## What it does

- Fetches top clips from **Twitch** (by game) and **Kick** (by category or specific streamer)
- Displays clips in a dashboard where you can approve or reject them
- Lets you edit the title, description, and tags before uploading
- Uploads approved clips to **YouTube Shorts**, **TikTok**, and **X**
- Optionally runs on a schedule so the whole pipeline runs automatically

---

## Requirements

- Python 3.11+
- Windows (PyWebView uses WinForms)
- Git Bash or any terminal

---

## Installation

```bash
# 1. Extract the zip and open the folder
cd clipslop

# 2. Run the launcher — it sets up everything automatically
run.bat
```

`run.bat` will create a virtual environment, install all dependencies, and launch the app. After the first run you can just double-click `run.bat` to start it.

---

## Running manually

```bash
cd clipslop
source venv/Scripts/activate
python app.py
```

The app opens as a native desktop window. It also runs at `http://localhost:5000` in your browser if you prefer that.

---

## Project structure

```
clipslop/
├── app.py                  # Flask app + all API routes
├── config.py               # Settings loaded from .env
├── database.py             # SQLite models (clips, upload logs, config)
├── downloader.py           # yt-dlp video downloader
├── scheduler.py            # APScheduler auto-pipeline
├── run.bat                 # Launch script (double-click to start)
├── build.bat               # Build ClipSlop.exe with PyInstaller
├── requirements.txt
├── .env.example            # Copy to .env and fill in your keys
├── fetchers/
│   ├── twitch.py           # Twitch Helix API clip fetcher
│   └── kick.py             # Kick v2 API clip fetcher (tls-client)
├── uploaders/
│   ├── youtube.py          # YouTube Data API v3 uploader
│   ├── tiktok.py           # TikTok Content Posting API uploader
│   └── x.py               # X (Twitter) API v2 uploader
├── templates/              # Jinja2 HTML templates
│   └── partials/           # SPA partial templates
└── static/                 # CSS + JS
```

---

## Setting up API keys

Go to **Settings** in the app and fill in your credentials. All keys are saved to a local `.env` file.

### Twitch
1. Go to [dev.twitch.tv](https://dev.twitch.tv) → Create an application
2. Copy the **Client ID** and **Client Secret**
3. Paste into Settings → Twitch section → Save Changes

### Kick
1. Clip fetching using the public Kick API and `tls-client` to bypass Cloudflare.

### YouTube Shorts
1. Go to [Google Cloud Console](https://console.cloud.google.com) → Create a project
2. Enable the **YouTube Data API v3**
3. Create **OAuth 2.0 credentials** → Download as `client_secrets.json`
4. Place `client_secrets.json` in your `clipslop` folder
5. In Settings → YouTube → Click **Connect YouTube** → Log in via browser

### TikTok
1. Go to [developers.tiktok.com](https://developers.tiktok.com) → Create an app
2. Enable the **Content Posting API** with `video.publish` scope
3. In Settings → TikTok → Click **↗ OAuth Login** or paste an access token directly

### X (Twitter)
1. Go to [developer.twitter.com](https://developer.twitter.com) → Create a project and app
2. Set permissions to **Read and Write**
3. Generate **API Key**, **API Secret**, **Access Token**, and **Access Token Secret**
4. Paste all 4 into Settings → X section → Save Changes

---

## Fetching clips

In Settings, configure what to fetch:

**Twitch — Games to track:**
```
eg. Just Chatting, Fortnite, GTA V
```

**Kick — Targets:**
```
eg. just-chatting, slots, @xqc
```
- Plain slugs = category (e.g. `just-chatting`, `slots`)
- `@username` = specific streamer (e.g. `@xqc`)

Then click **⬇ Fetch Clips** on the Dashboard or Clips page.

---

## Upload pipeline

1. **Fetch** — clips are pulled from Twitch/Kick and saved locally
2. **Review** — browse clips on the Clips page, click Approve or Reject
3. **Edit** — on the Queue page, edit the title, description, and tags
4. **Upload** — click the YouTube / TikTok / X buttons per clip, or Upload All

---

## Auto scheduler

In Settings → Auto Scheduler, click **▶ Start** and choose an interval (e.g. every 6 hours). The scheduler will automatically fetch new clips and upload approved ones without any manual input.

Click **⚡ Run Now** to trigger the pipeline immediately.

---

## Building the exe

To build a standalone `ClipSlop.exe`:

```bash
# Option 1 — double-click build.bat in File Explorer

# Option 2 — run from terminal
cmd //c build.bat
```

The exe will appear in `dist/ClipSlop.exe`. Copy it anywhere — it launches the full app as a desktop window with no terminal or browser needed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| App won't start | Make sure venv is activated: `source venv/Scripts/activate` |
| Kick returns 403 | Install tls-client: `pip install tls-client` |
| Twitch returns 400 | Your Client ID or Secret is wrong — check dev.twitch.tv |
| No clips fetched | Check your games/targets are spelled correctly in Settings |
| YouTube upload fails | Make sure `client_secrets.json` is in the project folder and you've completed OAuth |
| Settings not saving | Try navigating directly to `http://localhost:5000/settings` instead of using the sidebar |

---

## Database

Clips are stored in `clips.db` (SQLite) in the project folder. To clear all clips and start fresh, delete `clips.db` and restart the app — it will recreate automatically.

You can inspect the database with [DB Browser for SQLite](https://sqlitebrowser.org/).

---

## License

MIT
