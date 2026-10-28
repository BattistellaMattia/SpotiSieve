# SpotiSieve — Spotify Playlist Genre Filter

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-2b2b2b?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**SpotiSieve** is a desktop app (Python + CustomTkinter) that filters huge Spotify playlists by musical genre, lets you review and clean up the result, and gives you a ready-to-use playlist.

**No Spotify account, no API key, no Premium required.** Anyone can use it.

### Key Features
* **Works without any Spotify API:** you load your playlist as a CSV file; genres come from the CSV or from [MusicBrainz](https://musicbrainz.org) (free, no key).
* **3x8 Interactive Genre Matrix:** combine up to 24 genres with light-up toggle buttons. Sub-genres are matched too (*pop* finds *dance pop*, *trap* finds *italian trap*).
* **Staging & Manual Cleanup (`✕`):** preview **Title**, **Main Artist**, **Featured Artists** and **Album**, search in real time and remove unwanted tracks.
* **Three ways to get your new playlist:**
  * **Copy Spotify Links** → paste them into a new playlist in the Spotify desktop app (no login at all).
  * **Save CSV** → keep the filtered list.
  * **Import to Spotify** → one click, with a Spotify login *only if you choose to use it* (optional, see below).
* **Smart cache:** genres already looked up are saved locally, so the next run is instant.

---

## Download (Windows)

**[⬇️ Download SpotiSieve.exe](https://github.com/BattistellaMattia/SpotiSieve/releases/latest/download/SpotiSieve.exe)** — nothing to install or configure, just run it. All versions are on the [Releases page](https://github.com/BattistellaMattia/SpotiSieve/releases).

Windows may show a SmartScreen/Defender warning because the app is not code-signed (common for PyInstaller executables). Click *More info → Run anyway*.

## How to use it

1. **Get your playlist as a CSV.** Click **🌐 Get your CSV on Exportify** in the app (or open [Exportify](https://watsonbox.github.io/exportify/)), log in there and export the playlist. Any CSV with a track title and artist column works; a Spotify track URI/ID column is needed only for *Copy Spotify Links* and *Import*.
2. **Load the CSV** with *Browse CSV…* and **select the genres** you want.
3. Click **START TRACK EXTRACTION**.
   * If the CSV already contains genres they are used directly.
   * Otherwise SpotiSieve looks each artist up on MusicBrainz. The service allows **1 request per second**, so a playlist with 500 different artists takes about 10 minutes the first time (you can cancel and resume: progress is saved).
4. **Review the list**, remove tracks with `✕`, then:
   * click **COPY SPOTIFY LINKS**, create a new playlist in the Spotify desktop app, click inside it and press `Ctrl+V`; or
   * click **SAVE CSV**; or
   * click **IMPORT TO SPOTIFY** (needs the optional login).

> Genre tags from MusicBrainz are community-made: a few artists have none, and those tracks will not match any genre.

## Optional: one-click import with Spotify login

Only the **Import to Spotify** button needs a login. It uses the secure *Authorization Code + PKCE* flow, so **no Client Secret is ever required**.

Spotify's rules for apps in Development Mode (since early 2026): the app owner needs a Premium subscription and each app can authorize at most 5 users. For this reason the app does not ship with a shared Client ID. If you have one:

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) with Redirect URI `http://127.0.0.1:8888/callback`.
2. In SpotiSieve open **⚙️ Spotify Login (optional)**, paste the **Client ID** and save.
3. Add the Spotify accounts that will use it under *User Management* in the dashboard.

Maintainers can also set `BUNDLED_CLIENT_ID` in `spotify_extractor.py` to enable the login for everyone allowed on their app.

Your settings are stored locally in `settings.json` and the login token in `.cache`, next to the app. Both are ignored by Git. Use *Log out* in the settings window to remove the token.

## Run from source

```bash
git clone https://github.com/BattistellaMattia/SpotiSieve.git
cd SpotiSieve
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r requirements.txt
python spotify_extractor.py
```

Run the tests with `pip install pytest` and then `pytest -v` (the GUI test is skipped automatically on machines without a display).

## Releases (automatic)

The executable is built by GitHub Actions, you do not need to build it by hand. To publish a new version:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow in `.github/workflows/release.yml` runs the tests, builds `SpotiSieve.exe` on Windows and attaches it to a new GitHub Release.

To build it locally instead:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name SpotiSieve --collect-all customtkinter spotify_extractor.py
```

## Privacy

* The CSV is read locally and never uploaded.
* Only **artist names** are sent to MusicBrainz, and only for artists whose genres are not already in the CSV.
* No Spotify data is collected by this project.

## License

MIT — see [LICENSE](LICENSE).

*SpotiSieve is not affiliated with Spotify or MusicBrainz.*