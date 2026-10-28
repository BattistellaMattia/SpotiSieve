"""SpotiSieve - filter a Spotify playlist export by musical genre.

No Spotify API key is needed to filter a playlist:
  * the playlist comes from a CSV file (e.g. exported with Exportify),
  * genres come from the CSV itself or, when missing, from MusicBrainz (free, no key).

A Spotify login is needed ONLY if you want the one-click "Import to Spotify" button.
Without it you can still copy the track links or save the result as a CSV.
"""
import base64
import csv
import hashlib
import json
import re
import secrets
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox


def get_app_dir() -> Path:
    """Return the folder containing the .exe (when compiled) or the .py script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# Local files are always saved right next to the executable
APP_DIR = get_app_dir()
SETTINGS_FILE_PATH = APP_DIR / "settings.json"
CACHE_FILE_PATH = APP_DIR / ".cache"              # Spotify login token (optional login)
GENRE_CACHE_FILE_PATH = APP_DIR / "genre_cache.json"

# ------------------------------------------------------------------
# Optional Spotify login (only used by the "Import to Spotify" button)
# ------------------------------------------------------------------
# A public Client ID is NOT a secret (PKCE login needs no Client Secret).
# If you own a Spotify Developer app, paste its Client ID here (or in the
# in-app settings) to enable one-click login. Leave empty to disable it.
BUNDLED_CLIENT_ID = ""
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "playlist-modify-private playlist-modify-public"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# ------------------------------------------------------------------
# Genre lookup (MusicBrainz: free, no API key, max 1 request/second)
# ------------------------------------------------------------------
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/artist/"
USER_AGENT = "SpotiSieve/2.0 ( https://github.com/BattistellaMattia/SpotiSieve )"
MB_MIN_INTERVAL = 1.1  # seconds between requests, as requested by MusicBrainz

EXPORTIFY_URL = "https://watsonbox.github.io/exportify/"

# 24 musical genres arranged in 3 rows of 8 columns
GENRES_LIST = [
    "pop", "hip hop", "rap", "trap", "rock", "indie", "r&b", "electronic",
    "edm", "house", "techno", "dance", "metal", "punk", "alternative", "soul",
    "jazz", "blues", "classical", "reggaeton", "latin", "funk", "country", "lo-fi"
]

# Alternative spellings that should count as the same genre
GENRE_SYNONYMS = {
    "hip hop": ("hip hop", "hiphop"),
    "r&b": ("r&b", "rnb", "rhythm and blues"),
    "electronic": ("electronic", "electronica"),
    "edm": ("edm", "electronic dance music"),
    "lo-fi": ("lo-fi", "lofi"),
}

# Spotify color theme palette
COLOR_SPOTIFY_GREEN = "#1DB954"
COLOR_SPOTIFY_HOVER = "#1ed760"
COLOR_BTN_OFF = "#2b2b2b"
COLOR_BTN_OFF_HOVER = "#3d3d3d"
COLOR_REMOVE = "#e22134"
COLOR_REMOVE_HOVER = "#ff4b5c"


# ==================================================================
# PURE HELPERS (no GUI, easy to test)
# ==================================================================
def normalize_text(text: str) -> str:
    """Lowercase and turn separators into spaces ('Hip-Hop' -> 'hip hop')."""
    text = re.sub(r"[-_/]+", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def fold_name(text: str) -> str:
    """Accent-insensitive, punctuation-insensitive key used to compare artist names."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def genre_matches(selected: str, tag: str) -> bool:
    """True if the selected genre appears as a whole word/phrase inside the tag.

    'pop' matches 'dance pop' and 'k-pop' but 'rap' does not match 'trap'.
    """
    tag_norm = normalize_text(tag)
    for term in GENRE_SYNONYMS.get(selected, (selected,)):
        term_norm = re.escape(normalize_text(term))
        if re.search(rf"(?<![a-z0-9&]){term_norm}(?![a-z0-9&])", tag_norm):
            return True
    return False


def track_matches(selected_genres, track_genres) -> bool:
    return any(genre_matches(sel, tag) for sel in selected_genres for tag in track_genres)


def parse_track_uri(value: str):
    """Return a normalized 'spotify:track:<id>' from a URI, a link or a bare ID (else None)."""
    value = (value or "").strip()
    match = (
        re.search(r"spotify:track:([A-Za-z0-9]{22})", value)
        or re.search(r"open\.spotify\.com/(?:intl-[a-z]+/)?track/([A-Za-z0-9]{22})", value)
        or re.fullmatch(r"([A-Za-z0-9]{22})", value)
    )
    return f"spotify:track:{match.group(1)}" if match else None


def uri_to_link(uri: str) -> str:
    return "https://open.spotify.com/track/" + uri.split(":")[-1]


# Accepted CSV column names (lowercase). Covers Exportify and similar exporters.
CSV_COLUMNS = {
    "uri": ("track uri", "spotify uri", "uri", "spotify id", "track id", "track link", "link", "url"),
    "title": ("track name", "track title", "title", "name", "track", "song"),
    "album": ("album name", "album"),
    "artists": ("artist name(s)", "artist names", "artist name", "artists", "artist"),
    "genres": ("genres", "genre", "artist genres", "artist genre"),
}


def parse_playlist_csv(path):
    """Read a playlist CSV and return a list of track dictionaries."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"File not found:\n{path}")

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("The CSV file is empty.")

        headers = {h.strip().lower(): h for h in reader.fieldnames if h}

        def find(kind):
            for candidate in CSV_COLUMNS[kind]:
                if candidate in headers:
                    return headers[candidate]
            return None

        col_uri, col_title = find("uri"), find("title")
        col_album, col_artists, col_genres = find("album"), find("artists"), find("genres")
        if not col_title or not col_artists:
            raise ValueError(
                "Could not find the track title and artist columns.\n"
                "Export the playlist with Exportify (it includes 'Track Name' and 'Artist Name(s)')."
            )

        tracks, seen = [], set()
        for index, row in enumerate(reader):
            title = (row.get(col_title) or "").strip()
            artists = [a.strip() for a in (row.get(col_artists) or "").split(";") if a.strip()]
            if not title or not artists:
                continue

            spotify_uri = parse_track_uri(row.get(col_uri) or "") if col_uri else None
            key = spotify_uri or f"row:{index}"
            dedupe_key = spotify_uri or (title.lower(), artists[0].lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            raw_genres = (row.get(col_genres) or "") if col_genres else ""
            csv_genres = [g.strip().lower() for g in re.split(r"[,;]", raw_genres) if g.strip()]

            tracks.append({
                "uri": key,
                "spotify_uri": spotify_uri,
                "title": title,
                "album": (row.get(col_album) or "").strip() if col_album else "",
                "artists": artists,
                "csv_genres": csv_genres,
            })
    return tracks


# ------------------------------------------------------------------
# MusicBrainz genre lookup
# ------------------------------------------------------------------
class GenreServiceError(Exception):
    """Raised when the genre service cannot be reached."""


def extract_tags(artist: dict, limit: int = 15):
    """Collect genre/tag names from a MusicBrainz artist object, best voted first."""
    items = list(artist.get("genres", [])) + list(artist.get("tags", []))
    items = [i for i in items if i.get("name") and i.get("count", 1) > 0]
    items.sort(key=lambda i: i.get("count", 0), reverse=True)
    names = []
    for item in items:
        name = item["name"].lower()
        if name not in names:
            names.append(name)
    return names[:limit]


def pick_best_artist(name: str, candidates):
    """Return the first candidate whose name matches exactly (ignoring accents/punctuation)."""
    wanted = fold_name(name)
    for candidate in candidates:
        if fold_name(candidate.get("name", "")) == wanted:
            return candidate
    return None


def fetch_musicbrainz_genres(name: str):
    """Query MusicBrainz for one artist and return its genre tags."""
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    params = urllib.parse.urlencode({"query": f'artist:"{escaped}"', "fmt": "json", "limit": 5})
    request = urllib.request.Request(
        f"{MUSICBRAINZ_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as err:
            if err.code in (429, 503) and attempt == 0:
                time.sleep(3)  # polite retry when rate-limited
                continue
            raise GenreServiceError(f"MusicBrainz returned HTTP {err.code}.") from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise GenreServiceError(f"Cannot reach MusicBrainz: {err}") from err

    best = pick_best_artist(name, data.get("artists", []))
    return extract_tags(best) if best else []


class GenreLookup:
    """Artist -> genres lookup with a persistent local cache and request throttling."""

    def __init__(self, cache_path, fetcher=fetch_musicbrainz_genres,
                 min_interval=MB_MIN_INTERVAL, sleep=time.sleep, clock=time.monotonic):
        self.cache_path = Path(cache_path)
        self.fetcher = fetcher
        self.min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last_request = None
        self._unsaved = 0
        self.cache = self._load()

    def _load(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _key(name):
        return name.strip().lower()

    def has(self, name) -> bool:
        return self._key(name) in self.cache

    def get(self, name):
        key = self._key(name)
        if key in self.cache:
            return self.cache[key]

        if self._last_request is not None:
            wait = self.min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        try:
            genres = self.fetcher(name)
        finally:
            self._last_request = self._clock()

        self.cache[key] = genres
        self._unsaved += 1
        if self._unsaved >= 25:
            self.save()
        return genres

    def save(self):
        try:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
            self._unsaved = 0
        except OSError:
            pass


# ------------------------------------------------------------------
# Optional Spotify login (PKCE: no Client Secret required)
# ------------------------------------------------------------------
class SpotifyAPIError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Spotify API error {status}: {body}")
        self.status = status


def _post_form(url, data):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        raise SpotifyAPIError(err.code, err.read().decode(errors="replace")) from err


def _save_token(cache_path, token):
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    Path(cache_path).write_text(json.dumps(token), encoding="utf-8")


def spotify_login(client_id, redirect_uri, cache_path, timeout=180, open_browser=webbrowser.open):
    """Return a valid access token, reusing/refreshing the saved one or asking the user to log in."""
    cache_path = Path(cache_path)

    # 1. Reuse or refresh the saved token
    try:
        saved = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if saved and saved.get("client_id") == client_id:
        if saved.get("expires_at", 0) - 60 > time.time():
            return saved["access_token"]
        if saved.get("refresh_token"):
            try:
                fresh = _post_form(SPOTIFY_TOKEN_URL, {
                    "grant_type": "refresh_token",
                    "refresh_token": saved["refresh_token"],
                    "client_id": client_id,
                })
                fresh.setdefault("refresh_token", saved["refresh_token"])
                fresh["client_id"] = client_id
                _save_token(cache_path, fresh)
                return fresh["access_token"]
            except SpotifyAPIError:
                pass  # fall through to a new login

    # 2. New login in the browser (Authorization Code with PKCE)
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in ("127.0.0.1", "localhost") or not parsed.port:
        raise ValueError("The Redirect URI must look like http://127.0.0.1:8888/callback")

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if urllib.parse.urlparse(self.path).path != (parsed.path or "/"):
                self.send_response(404)
                self.end_headers()
                return
            result["code"] = (query.get("code") or [None])[0]
            result["error"] = (query.get("error") or [None])[0]
            result["state"] = (query.get("state") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;background:#121212;color:#fff;"
                b"text-align:center;padding-top:80px'><h2>SpotiSieve</h2>"
                b"<p>Login completed. You can close this tab and go back to the app.</p></body></html>"
            )

        def log_message(self, *args):
            pass  # keep the console quiet

    server = HTTPServer((parsed.hostname, parsed.port), CallbackHandler)
    server.timeout = 1
    try:
        open_browser(SPOTIFY_AUTH_URL + "?" + urllib.parse.urlencode({
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPE,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }))
        deadline = time.time() + timeout
        while "code" not in result and "error" not in result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if result.get("error") or not result.get("code"):
        raise RuntimeError(f"Spotify login failed or timed out ({result.get('error') or 'no answer'}).")
    if result.get("state") != state:
        raise RuntimeError("Spotify login rejected: state mismatch.")

    token = _post_form(SPOTIFY_TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    token["client_id"] = client_id
    _save_token(cache_path, token)
    return token["access_token"]


def spotify_api(method, path, token, payload=None):
    """Small JSON helper for the Spotify Web API (retries once on rate limiting)."""
    body = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(2):
        request = urllib.request.Request(
            SPOTIFY_API_URL + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt == 0:
                time.sleep(min(int(err.headers.get("Retry-After", "2")), 30) + 1)
                continue
            raise SpotifyAPIError(err.code, err.read().decode(errors="replace")) from err
    return {}


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    SETTINGS_FILE_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


# ==================================================================
# GUI
# ==================================================================
class SettingsWindow(ctk.CTkToplevel):
    """Modal window for the OPTIONAL Spotify login (needed only for the direct import)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title("Spotify Login (optional)")
        self.geometry("540x400")
        self.resizable(False, False)

        # Keep modal window on top of the main application
        self.transient(parent)
        self.grab_set()
        self.focus()

        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkFrame(self, corner_radius=10)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="Spotify Login (optional)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(12, 4))

        ctk.CTkLabel(
            container,
            text=(
                "You do NOT need this to filter playlists, copy links or save a CSV.\n"
                "It is only needed for the one-click 'Import to Spotify' button.\n"
                "Paste the Client ID of a Spotify Developer app (no Client Secret needed)."
            ),
            font=ctk.CTkFont(size=12),
            text_color="#b3b3b3",
            justify="left"
        ).pack(anchor="w", padx=15, pady=(0, 12))

        ctk.CTkLabel(
            container, text="Client ID:", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15)
        self.client_id_entry = ctk.CTkEntry(
            container, placeholder_text="Paste your Spotify Client ID here", height=34
        )
        self.client_id_entry.pack(fill="x", padx=15, pady=(2, 10))
        self.client_id_entry.insert(0, self.parent.client_id)

        ctk.CTkLabel(
            container, text="Redirect URI:", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15)
        self.redirect_uri_entry = ctk.CTkEntry(container, height=34)
        self.redirect_uri_entry.pack(fill="x", padx=15, pady=(2, 15))
        self.redirect_uri_entry.insert(0, self.parent.redirect_uri)

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(5, 10))

        ctk.CTkButton(
            btn_frame, text="Log out", fg_color=COLOR_BTN_OFF, hover_color=COLOR_BTN_OFF_HOVER,
            width=90, height=36, command=self._logout
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="Cancel", fg_color=COLOR_BTN_OFF, hover_color=COLOR_BTN_OFF_HOVER,
            width=100, height=36, command=self.destroy
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Save", fg_color=COLOR_SPOTIFY_GREEN, hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000", font=ctk.CTkFont(size=13, weight="bold"),
            width=120, height=36, command=self._save
        ).pack(side="right")

    def _logout(self):
        self.parent.logout()
        messagebox.showinfo("Logged out", "The saved Spotify login was removed.", parent=self)

    def _save(self):
        new_id = self.client_id_entry.get().strip()
        new_uri = self.redirect_uri_entry.get().strip() or DEFAULT_REDIRECT_URI
        try:
            self.parent.update_settings(new_id, new_uri)
        except OSError as err:
            messagebox.showerror("Save Error", f"Failed to save settings:\n{err}", parent=self)
            return
        self.destroy()


class SpotifyGenreExtractorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SpotiSieve - Spotify Playlist Genre Extractor")
        self.geometry("1120x880")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        # Optional login settings (settings.json, never needed for filtering)
        settings = load_settings()
        self.client_id = (settings.get("client_id") or BUNDLED_CLIENT_ID).strip()
        self.redirect_uri = (settings.get("redirect_uri") or DEFAULT_REDIRECT_URI).strip()

        # Application state
        self.selected_genres = set()
        self.genre_buttons = {}
        self.filtered_tracks = []  # List of track dictionaries
        self.track_rows = {}       # Maps uri -> {"frame": widget, "search_blob": str}
        self.settings_win = None
        self.genre_lookup = GenreLookup(GENRE_CACHE_FILE_PATH)
        self.cancel_event = threading.Event()
        self.running = False

        self._build_ui()

    def _build_ui(self):
        # --- 1. CSV FILE SECTION & LOGIN SETTINGS BUTTON ---
        top_frame = ctk.CTkFrame(self, corner_radius=10)
        top_frame.pack(fill="x", padx=20, pady=(15, 10))

        header_bar = ctk.CTkFrame(top_frame, fg_color="transparent")
        header_bar.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            header_bar,
            text="1. Load your playlist CSV (no Spotify account or API key needed):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        self.settings_btn = ctk.CTkButton(
            header_bar,
            text="⚙️ Spotify Login (optional)",
            width=200,
            height=30,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            border_width=1,
            border_color="#404040",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.open_settings_window
        )
        self.settings_btn.pack(side="right")

        file_row = ctk.CTkFrame(top_frame, fg_color="transparent")
        file_row.pack(fill="x", padx=15, pady=(0, 12))

        self.exportify_btn = ctk.CTkButton(
            file_row,
            text="🌐 Get your CSV on Exportify",
            width=230,
            height=38,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            border_width=1,
            border_color="#404040",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.open_exportify
        )
        self.exportify_btn.pack(side="right", padx=(8, 0))

        self.browse_btn = ctk.CTkButton(
            file_row,
            text="Browse CSV…",
            width=130,
            height=38,
            fg_color=COLOR_SPOTIFY_GREEN,
            hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.browse_csv
        )
        self.browse_btn.pack(side="right", padx=(8, 0))

        self.path_entry = ctk.CTkEntry(
            file_row,
            placeholder_text="Path of the playlist CSV file (e.g. exported with Exportify)",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.path_entry.pack(side="left", fill="x", expand=True)

        # --- 2. GENRE MATRIX SECTION (3 rows x 8 columns) ---
        genre_frame = ctk.CTkFrame(self, corner_radius=10)
        genre_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(
            genre_frame,
            text="2. Select Musical Genres to Extract (click to highlight/deselect):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        grid_container = ctk.CTkFrame(genre_frame, fg_color="transparent")
        grid_container.pack(fill="x", padx=10, pady=(0, 12))

        for i in range(8):
            grid_container.grid_columnconfigure(i, weight=1)

        for idx, genre in enumerate(GENRES_LIST):
            row = idx // 8
            col = idx % 8
            btn = ctk.CTkButton(
                grid_container,
                text=genre.upper(),
                fg_color=COLOR_BTN_OFF,
                hover_color=COLOR_BTN_OFF_HOVER,
                text_color="#ffffff",
                border_width=1,
                border_color="#404040",
                height=36,
                corner_radius=8,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda g=genre: self.toggle_genre(g)
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            self.genre_buttons[genre] = btn

        # --- 3. LARGE START BUTTON, PROGRESS & STATUS BAR ---
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=8)

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="START TRACK EXTRACTION",
            height=50,
            corner_radius=10,
            fg_color=COLOR_SPOTIFY_GREEN,
            hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.on_start_clicked
        )
        self.start_btn.pack(fill="x")

        self.progress = ctk.CTkProgressBar(action_frame, height=8, progress_color=COLOR_SPOTIFY_GREEN)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(8, 0))

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="Ready. Load a playlist CSV, select genres, and click Start.",
            font=ctk.CTkFont(size=13),
            text_color="#b3b3b3"
        )
        self.status_label.pack(pady=(6, 0))

        # --- 4. TRACK PREVIEW AREA WITH SEARCH BAR & REMOVAL ('✕') ---
        preview_frame = ctk.CTkFrame(self, corner_radius=10)
        preview_frame.pack(fill="both", expand=True, padx=20, pady=5)

        header_preview = ctk.CTkFrame(preview_frame, fg_color="transparent")
        header_preview.pack(fill="x", padx=15, pady=(10, 6))

        self.tracks_count_label = ctk.CTkLabel(
            header_preview,
            text="3. Extracted Tracks (0): review list or click '✕' to remove",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.tracks_count_label.pack(side="left")

        # Live Search Bar on the right side of the preview header
        search_container = ctk.CTkFrame(header_preview, fg_color="transparent")
        search_container.pack(side="right")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)

        self.search_entry = ctk.CTkEntry(
            search_container,
            textvariable=self.search_var,
            placeholder_text="🔍 Search title, artist, feat, or album...",
            width=300,
            height=32,
            font=ctk.CTkFont(size=12)
        )
        self.search_entry.pack(side="left", padx=(0, 6))

        self.clear_search_btn = ctk.CTkButton(
            search_container,
            text="Clear",
            width=60,
            height=32,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            font=ctk.CTkFont(size=12),
            command=self.clear_search
        )
        self.clear_search_btn.pack(side="left")

        self.tracks_scroll = ctk.CTkScrollableFrame(preview_frame, corner_radius=8)
        self.tracks_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 12))

        # --- 5. EXPORT SECTION (copy links / save CSV / optional direct import) ---
        bottom_frame = ctk.CTkFrame(self, corner_radius=10)
        bottom_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkLabel(
            bottom_frame,
            text="Playlist Name:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(15, 10), pady=12)

        self.import_btn = ctk.CTkButton(
            bottom_frame,
            text="IMPORT TO SPOTIFY (login)",
            height=38,
            width=210,
            fg_color=COLOR_SPOTIFY_GREEN,
            hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self.start_import_thread
        )
        self.import_btn.pack(side="right", padx=(0, 15), pady=12)

        self.csv_btn = ctk.CTkButton(
            bottom_frame,
            text="SAVE CSV",
            height=38,
            width=110,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            border_width=1,
            border_color="#404040",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self.save_csv
        )
        self.csv_btn.pack(side="right", padx=(0, 8), pady=12)

        self.copy_btn = ctk.CTkButton(
            bottom_frame,
            text="COPY SPOTIFY LINKS",
            height=38,
            width=170,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            border_width=1,
            border_color="#404040",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self.copy_links
        )
        self.copy_btn.pack(side="right", padx=(0, 8), pady=12)

        self.playlist_name_entry = ctk.CTkEntry(
            bottom_frame,
            placeholder_text="e.g., Extracted Rock & Indie Mix",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.playlist_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 15), pady=12)

        self.output_buttons = [self.copy_btn, self.csv_btn, self.import_btn]

    # ==========================================
    # OPTIONAL LOGIN SETTINGS
    # ==========================================
    def open_settings_window(self):
        if self.settings_win is None or not self.settings_win.winfo_exists():
            self.settings_win = SettingsWindow(self)
        else:
            self.settings_win.focus()

    def update_settings(self, client_id, redirect_uri):
        """Save the optional login settings and forget any previous login."""
        save_settings({"client_id": client_id, "redirect_uri": redirect_uri})
        self.client_id = client_id.strip() or BUNDLED_CLIENT_ID
        self.redirect_uri = redirect_uri
        self.logout()
        self._update_status("Spotify login settings saved.")

    def logout(self):
        if CACHE_FILE_PATH.exists():
            try:
                CACHE_FILE_PATH.unlink()
            except OSError:
                pass

    # ==========================================
    # UI LOGIC, GENRE TOGGLE & LIVE SEARCH
    # ==========================================
    def toggle_genre(self, genre):
        """Toggle highlight state for the clicked genre button."""
        btn = self.genre_buttons[genre]
        if genre in self.selected_genres:
            self.selected_genres.remove(genre)
            btn.configure(
                fg_color=COLOR_BTN_OFF,
                hover_color=COLOR_BTN_OFF_HOVER,
                text_color="#ffffff",
                border_color="#404040"
            )
        else:
            self.selected_genres.add(genre)
            btn.configure(
                fg_color=COLOR_SPOTIFY_GREEN,
                hover_color=COLOR_SPOTIFY_HOVER,
                text_color="#000000",
                border_color=COLOR_SPOTIFY_GREEN
            )

    def open_exportify(self):
        """Open the Exportify website (where the playlist CSV is exported) in the default browser."""
        if not webbrowser.open(EXPORTIFY_URL):
            messagebox.showinfo(
                "Open this page",
                f"Could not open the browser automatically.\nOpen this address manually:\n\n{EXPORTIFY_URL}"
            )

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select the playlist CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def clear_search(self):
        """Reset the search bar and show all extracted tracks."""
        self.search_var.set("")
        self.focus()

    def _on_search_changed(self, *args):
        """Filter visible track rows in real time based on the search query."""
        query = self.search_var.get().strip().lower()
        visible_count = 0

        for track_data in self.filtered_tracks:
            uri = track_data["uri"]
            row_info = self.track_rows.get(uri)
            if not row_info:
                continue

            frame = row_info["frame"]
            if not query or query in row_info["search_blob"]:
                frame.pack(fill="x", padx=5, pady=3)
                visible_count += 1
            else:
                frame.pack_forget()

        self._update_counter_label(visible_count=visible_count, is_filtering=bool(query))

    # ==========================================
    # PHASE 1: TRACK EXTRACTION & FILTERING
    # ==========================================
    def on_start_clicked(self):
        if self.running:
            self.cancel_event.set()
            self._update_status("Cancelling... (progress is saved)")
            return
        self.start_extraction_thread()

    def start_extraction_thread(self):
        path = self.path_entry.get().strip().strip('"')
        if not path:
            messagebox.showwarning("Missing CSV", "Please load a playlist CSV file first.")
            return
        if not self.selected_genres:
            messagebox.showwarning("No Genres Selected", "Please select at least one musical genre.")
            return

        self.cancel_event.clear()
        self._set_running(True)
        self._set_outputs(False)
        self.search_var.set("")
        self._clear_preview_list()

        thread = threading.Thread(
            target=self._extract_tracks_worker,
            args=(path, set(self.selected_genres)),
            daemon=True
        )
        thread.start()

    def _extract_tracks_worker(self, path, selected_genres):
        try:
            self._update_status("Reading the CSV file...")
            tracks = parse_playlist_csv(path)
            if not tracks:
                self._update_status("No valid tracks found in this file.")
                return

            # Artists whose genres are not already provided by the CSV
            artists = {}
            for track in tracks:
                if track["csv_genres"]:
                    continue
                for name in track["artists"]:
                    artists.setdefault(name.strip().lower(), name)

            to_fetch = sum(1 for name in artists.values() if not self.genre_lookup.has(name))
            if to_fetch:
                minutes = max(1, round(to_fetch * MB_MIN_INTERVAL / 60))
                self._update_status(
                    f"Looking up genres for {to_fetch} artists on MusicBrainz (about {minutes} min, "
                    f"results are saved for next time)..."
                )

            artist_genres = {}
            total = max(len(artists), 1)
            for done, (key, name) in enumerate(artists.items(), start=1):
                if self.cancel_event.is_set():
                    self._update_status("Cancelled. Progress is saved: start again to continue.")
                    return
                artist_genres[key] = self.genre_lookup.get(name)
                self._set_progress(done / total)
                if to_fetch and done % 5 == 0:
                    self._update_status(f"Genre lookup: {done}/{total} artists...")
            self._set_progress(1)

            # Filter tracks matching the selected genres
            matched = []
            for track in tracks:
                genres = list(track["csv_genres"])
                if not genres:
                    for name in track["artists"]:
                        genres.extend(artist_genres.get(name.strip().lower(), []))

                if not track_matches(selected_genres, genres):
                    continue

                feat = f" (feat. {', '.join(track['artists'][1:])})" if len(track["artists"]) > 1 else ""
                matched.append({
                    "uri": track["uri"],
                    "spotify_uri": track["spotify_uri"],
                    "title": track["title"],
                    "album": track["album"] or "Unknown Album",
                    "author": track["artists"][0],
                    "artists": track["artists"],
                    "feat": feat,
                    "genres": ", ".join(genres[:6]),
                })

            self.after(0, self._populate_preview_list, matched, len(tracks))

        except (ValueError, GenreServiceError) as err:
            message = str(err)
            self.after(0, lambda: messagebox.showerror("Extraction Error", message))
            self._update_status("Error during track extraction.")
        except Exception as err:  # unexpected problem: show it instead of failing silently
            message = f"An unexpected error occurred:\n{err}"
            self.after(0, lambda: messagebox.showerror("Unexpected Error", message))
            self._update_status("Error during track extraction.")
        finally:
            self.genre_lookup.save()
            self.after(0, lambda: self._set_running(False))

    def _populate_preview_list(self, matched_tracks, total_scanned):
        self.filtered_tracks = matched_tracks
        for track_data in self.filtered_tracks:
            self._create_track_row(track_data)

        self._update_counter_label()
        self._update_status(
            f"Extraction complete: {len(matched_tracks)} matching tracks found out of {total_scanned} scanned."
        )
        self._set_outputs(bool(self.filtered_tracks))

    def _create_track_row(self, track_data):
        uri = track_data["uri"]
        row_frame = ctk.CTkFrame(self.tracks_scroll, fg_color="#232323", corner_radius=6)
        row_frame.pack(fill="x", padx=5, pady=3)

        info_text = (
            f"🎵 {track_data['title']}   |   "
            f"🎤 {track_data['author']}{track_data['feat']}   |   "
            f"💿 {track_data['album']}"
        )

        lbl = ctk.CTkLabel(
            row_frame,
            text=info_text,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13)
        )
        lbl.pack(side="left", fill="x", expand=True, padx=12, pady=6)

        remove_btn = ctk.CTkButton(
            row_frame,
            text="✕",
            width=32,
            height=28,
            fg_color=COLOR_REMOVE,
            hover_color=COLOR_REMOVE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda u=uri: self.remove_track(u)
        )
        remove_btn.pack(side="right", padx=8, pady=5)

        # Precompute lowercase search string for instant filtering
        search_blob = (
            f"{track_data['title']} {track_data['author']} "
            f"{track_data['feat']} {track_data['album']}"
        ).lower()

        self.track_rows[uri] = {
            "frame": row_frame,
            "search_blob": search_blob
        }

    def remove_track(self, uri):
        """Remove the track from the export list and destroy its UI row."""
        self.filtered_tracks = [t for t in self.filtered_tracks if t["uri"] != uri]
        if uri in self.track_rows:
            self.track_rows[uri]["frame"].destroy()
            del self.track_rows[uri]

        # Recalculate counter keeping any active search filter in mind
        self._on_search_changed()

        if not self.filtered_tracks:
            self._set_outputs(False)

    def _clear_preview_list(self):
        for widget in self.tracks_scroll.winfo_children():
            widget.destroy()
        self.filtered_tracks.clear()
        self.track_rows.clear()
        self._update_counter_label()

    def _update_counter_label(self, visible_count=None, is_filtering=False):
        total = len(self.filtered_tracks)
        if is_filtering and visible_count is not None:
            self.tracks_count_label.configure(
                text=f"3. Extracted Tracks ({total} total, showing {visible_count}): click '✕' to remove"
            )
        else:
            self.tracks_count_label.configure(
                text=f"3. Extracted Tracks ({total}): review list or click '✕' to remove"
            )

    # ==========================================
    # PHASE 2: EXPORT (no login needed) 
    # ==========================================
    def _importable_uris(self):
        return [t["spotify_uri"] for t in self.filtered_tracks if t.get("spotify_uri")]

    def copy_links(self):
        uris = self._importable_uris()
        if not uris:
            messagebox.showwarning(
                "No Spotify links",
                "The CSV has no Spotify track URIs, so links cannot be created.\n"
                "Use 'Save CSV' instead, or export the playlist with Exportify."
            )
            return

        self.clipboard_clear()
        self.clipboard_append("\n".join(uri_to_link(u) for u in uris))
        self.update()  # keep the clipboard content after the window loses focus

        skipped = len(self.filtered_tracks) - len(uris)
        extra = f"\n({skipped} tracks without a Spotify link were skipped.)" if skipped else ""
        messagebox.showinfo(
            "Links copied",
            f"{len(uris)} track links copied to the clipboard.\n\n"
            "In the Spotify desktop app: create a new playlist, click in its track list "
            f"and press Ctrl+V.{extra}"
        )

    def save_csv(self):
        suggested = (self.playlist_name_entry.get().strip() or "spotisieve_playlist") + ".csv"
        path = filedialog.asksaveasfilename(
            title="Save the filtered playlist",
            defaultextension=".csv",
            initialfile=suggested,
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Track URI", "Track Name", "Artist Name(s)", "Album Name", "Genres"])
                for t in self.filtered_tracks:
                    writer.writerow([
                        t.get("spotify_uri") or "", t["title"], ";".join(t["artists"]),
                        t["album"], t.get("genres", "")
                    ])
            self._update_status(f"Saved {len(self.filtered_tracks)} tracks to {Path(path).name}.")
        except OSError as err:
            messagebox.showerror("Save Error", f"Could not save the file:\n{err}")

    # ==========================================
    # PHASE 3 (OPTIONAL): DIRECT IMPORT WITH SPOTIFY LOGIN
    # ==========================================
    def start_import_thread(self):
        if not self.client_id:
            messagebox.showinfo(
                "Login not configured",
                "Direct import needs a Spotify Client ID (see 'Spotify Login (optional)').\n\n"
                "No problem: you can use 'Copy Spotify Links' and paste them into a new playlist, "
                "or 'Save CSV'."
            )
            self.open_settings_window()
            return

        playlist_name = self.playlist_name_entry.get().strip()
        if not playlist_name:
            messagebox.showwarning("Missing Name", "Please enter a name for the new playlist before importing.")
            return
        uris = self._importable_uris()
        if not uris:
            messagebox.showwarning("Empty List", "There are no tracks with a Spotify link to import.")
            return

        self._set_outputs(False)
        self.start_btn.configure(state="disabled")
        genres_str = ", ".join(sorted(self.selected_genres))
        thread = threading.Thread(
            target=self._import_playlist_worker,
            args=(playlist_name, uris, genres_str),
            daemon=True
        )
        thread.start()

    def _import_playlist_worker(self, playlist_name, uris, genres_str):
        try:
            self._update_status("Waiting for Spotify login in your browser (3 minutes max)...")
            token = spotify_login(self.client_id, self.redirect_uri, CACHE_FILE_PATH)

            self._update_status("Creating new playlist in your Spotify account...")
            playlist = spotify_api("POST", "/me/playlists", token, {
                "name": playlist_name,
                "public": False,
                "description": f"Generated by SpotiSieve - Filtered genres: {genres_str}",
            })
            playlist_id = playlist["id"]

            # Add tracks in batches of 100 (Spotify API limit per request)
            for i in range(0, len(uris), 100):
                spotify_api("POST", f"/playlists/{playlist_id}/items", token, {"uris": uris[i:i + 100]})
                self._update_status(f"Importing tracks: {min(i + 100, len(uris))}/{len(uris)}...")

            self._update_status(f"Playlist '{playlist_name}' successfully created on Spotify!")
            self.after(0, lambda: messagebox.showinfo(
                "Import Complete",
                f"Playlist '{playlist_name}' ({len(uris)} tracks) is now in your Spotify library!"
            ))
        except SpotifyAPIError as err:
            hint = ""
            if err.status in (401, 403):
                hint = ("\n\nIn Spotify Development Mode only users added by the app owner can log in. "
                        "Use 'Copy Spotify Links' as an alternative.")
            message = f"{err}{hint}"
            self.after(0, lambda: messagebox.showerror("Import Error", message))
            self._update_status("Error while importing playlist.")
        except Exception as err:
            message = f"Failed to create playlist:\n{err}"
            self.after(0, lambda: messagebox.showerror("Import Error", message))
            self._update_status("Error while importing playlist.")
        finally:
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self._set_outputs(bool(self.filtered_tracks)))

    # ==========================================
    # SMALL UI HELPERS (safe to call from worker threads)
    # ==========================================
    def _update_status(self, message):
        self.after(0, lambda: self.status_label.configure(text=message))

    def _set_progress(self, value):
        self.after(0, lambda: self.progress.set(value))

    def _set_running(self, running):
        self.running = running
        if running:
            self.progress.set(0)
            self.start_btn.configure(
                text="CANCEL", fg_color=COLOR_REMOVE, hover_color=COLOR_REMOVE_HOVER, text_color="#ffffff"
            )
        else:
            self.start_btn.configure(
                text="START TRACK EXTRACTION", fg_color=COLOR_SPOTIFY_GREEN,
                hover_color=COLOR_SPOTIFY_HOVER, text_color="#000000"
            )

    def _set_outputs(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in self.output_buttons:
            button.configure(state=state)


if __name__ == "__main__":
    app = SpotifyGenreExtractorApp()
    app.mainloop()