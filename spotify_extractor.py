import os
import re
import sys
import threading
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv, set_key


def get_app_dir() -> Path:
    """Return the folder containing the .exe (when compiled) or the .py script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# Always save .env and .cache right next to the executable
APP_DIR = get_app_dir()
ENV_FILE_PATH = APP_DIR / ".env"
CACHE_FILE_PATH = APP_DIR / ".cache"

load_dotenv(dotenv_path=ENV_FILE_PATH)

# Default Spotify OAuth configuration
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "playlist-read-private playlist-modify-public playlist-modify-private"

# 24 musical genres arranged in 3 rows of 8 columns
GENRES_LIST = [
    "pop", "hip hop", "rap", "trap", "rock", "indie", "r&b", "electronic",
    "edm", "house", "techno", "dance", "metal", "punk", "alternative", "soul",
    "jazz", "blues", "classical", "reggaeton", "latin", "funk", "country", "lo-fi"
]

# Spotify color theme palette
COLOR_SPOTIFY_GREEN = "#1DB954"
COLOR_SPOTIFY_HOVER = "#1ed760"
COLOR_BTN_OFF = "#2b2b2b"
COLOR_BTN_OFF_HOVER = "#3d3d3d"
COLOR_REMOVE = "#e22134"
COLOR_REMOVE_HOVER = "#ff4b5c"


class SettingsWindow(ctk.CTkToplevel):
    """Modal window to input and save Spotify API credentials into the local .env file."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title("Spotify API Settings")
        self.geometry("520x360")
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
            text="Spotify API Credentials Setup",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(12, 4))

        ctk.CTkLabel(
            container,
            text="Your keys are stored exclusively on your computer inside the local '.env' file.",
            font=ctk.CTkFont(size=12),
            text_color="#b3b3b3"
        ).pack(anchor="w", padx=15, pady=(0, 12))

        # --- Client ID ---
        ctk.CTkLabel(
            container,
            text="Client ID:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15)

        self.client_id_entry = ctk.CTkEntry(
            container,
            placeholder_text="Paste your Spotify Client ID here",
            height=34
        )
        self.client_id_entry.pack(fill="x", padx=15, pady=(2, 10))
        self.client_id_entry.insert(0, self.parent.client_id)

        # --- Client Secret ---
        secret_header = ctk.CTkFrame(container, fg_color="transparent")
        secret_header.pack(fill="x", padx=15)

        ctk.CTkLabel(
            secret_header,
            text="Client Secret:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        self.show_secret_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            secret_header,
            text="Show",
            variable=self.show_secret_var,
            command=self._toggle_secret_visibility,
            checkbox_width=18,
            checkbox_height=18,
            font=ctk.CTkFont(size=12)
        ).pack(side="right")

        self.client_secret_entry = ctk.CTkEntry(
            container,
            placeholder_text="Paste your Spotify Client Secret here",
            height=34,
            show="•"
        )
        self.client_secret_entry.pack(fill="x", padx=15, pady=(2, 10))
        self.client_secret_entry.insert(0, self.parent.client_secret)

        # --- Redirect URI ---
        ctk.CTkLabel(
            container,
            text="Redirect URI:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15)

        self.redirect_uri_entry = ctk.CTkEntry(
            container,
            height=34
        )
        self.redirect_uri_entry.pack(fill="x", padx=15, pady=(2, 15))
        self.redirect_uri_entry.insert(0, self.parent.redirect_uri)

        # --- Save / Cancel Buttons ---
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(5, 10))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            width=110,
            height=36,
            command=self.destroy
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="Save to .env",
            fg_color=COLOR_SPOTIFY_GREEN,
            hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=160,
            height=36,
            command=self._save_credentials
        ).pack(side="right")

    def _toggle_secret_visibility(self):
        if self.show_secret_var.get():
            self.client_secret_entry.configure(show="")
        else:
            self.client_secret_entry.configure(show="•")

    def _save_credentials(self):
        new_id = self.client_id_entry.get().strip()
        new_secret = self.client_secret_entry.get().strip()
        new_uri = self.redirect_uri_entry.get().strip() or DEFAULT_REDIRECT_URI

        if not new_id or not new_secret:
            messagebox.showwarning(
                "Missing Fields",
                "Please enter both your Client ID and Client Secret.",
                parent=self
            )
            return

        try:
            # Create the .env file if it does not exist yet
            if not ENV_FILE_PATH.exists():
                ENV_FILE_PATH.touch()

            # Write or update keys in the local .env file
            set_key(str(ENV_FILE_PATH), "SPOTIPY_CLIENT_ID", new_id)
            set_key(str(ENV_FILE_PATH), "SPOTIPY_CLIENT_SECRET", new_secret)
            set_key(str(ENV_FILE_PATH), "SPOTIPY_REDIRECT_URI", new_uri)

            # Update in-memory credentials on the main application
            self.parent.update_credentials(new_id, new_secret, new_uri)

            messagebox.showinfo(
                "Settings Saved",
                "API credentials successfully saved to '.env'!",
                parent=self
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save the .env file:\n{e}",
                parent=self
            )


class SpotifyGenreExtractorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SpotiSieve - Spotify Playlist Genre Extractor")
        self.geometry("1120x840")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        # Load credentials from environment variables (.env)
        self.client_id = self._clean_env_val(os.getenv("SPOTIPY_CLIENT_ID", ""))
        self.client_secret = self._clean_env_val(os.getenv("SPOTIPY_CLIENT_SECRET", ""))
        self.redirect_uri = self._clean_env_val(
            os.getenv("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
        )

        # Application state
        self.selected_genres = set()
        self.genre_buttons = {}
        self.filtered_tracks = []  # List of track dictionaries
        self.track_rows = {}       # Maps uri -> {"frame": widget, "search_blob": str}
        self.sp = None
        self.settings_win = None

        self._build_ui()

    @staticmethod
    def _clean_env_val(val):
        """Ignore placeholder values coming from .env.example."""
        if not val or "inserisci_qui" in val.lower() or "your_personal" in val.lower():
            return ""
        return val.strip()

    def _build_ui(self):
        # --- 1. PLAYLIST URL SECTION & API SETTINGS BUTTON ---
        top_frame = ctk.CTkFrame(self, corner_radius=10)
        top_frame.pack(fill="x", padx=20, pady=(15, 10))

        header_bar = ctk.CTkFrame(top_frame, fg_color="transparent")
        header_bar.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            header_bar,
            text="1. Enter Public Spotify Playlist Link or ID:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        self.settings_btn = ctk.CTkButton(
            header_bar,
            text="⚙️ API Settings",
            width=150,
            height=30,
            fg_color=COLOR_BTN_OFF,
            hover_color=COLOR_BTN_OFF_HOVER,
            border_width=1,
            border_color="#404040",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.open_settings_window
        )
        self.settings_btn.pack(side="right")

        self.url_entry = ctk.CTkEntry(
            top_frame,
            placeholder_text="https://open.spotify.com/playlist/...",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(fill="x", padx=15, pady=(0, 12))

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

        # --- 3. LARGE START BUTTON & STATUS BAR ---
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
            command=self.start_extraction_thread
        )
        self.start_btn.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="Ready. Paste a playlist link, select genres, and click Start.",
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

        # --- 5. PLAYLIST CREATION & IMPORT SECTION ---
        bottom_frame = ctk.CTkFrame(self, corner_radius=10)
        bottom_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkLabel(
            bottom_frame,
            text="New Playlist Name:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(15, 10), pady=12)

        self.playlist_name_entry = ctk.CTkEntry(
            bottom_frame,
            placeholder_text="e.g., Extracted Rock & Indie Mix",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.playlist_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 15), pady=12)

        self.import_btn = ctk.CTkButton(
            bottom_frame,
            text="IMPORT TO SPOTIFY",
            height=38,
            width=220,
            fg_color=COLOR_SPOTIFY_GREEN,
            hover_color=COLOR_SPOTIFY_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
            command=self.start_import_thread
        )
        self.import_btn.pack(side="right", padx=(0, 15), pady=12)

    # ==========================================
    # SETTINGS WINDOW & CREDENTIAL MANAGEMENT
    # ==========================================
    def open_settings_window(self):
        if self.settings_win is None or not self.settings_win.winfo_exists():
            self.settings_win = SettingsWindow(self)
        else:
            self.settings_win.focus()

    def update_credentials(self, client_id, client_secret, redirect_uri):
        """Update active credentials and clear any previous OAuth token cache."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.sp = None

        if CACHE_FILE_PATH.exists():
            try:
                CACHE_FILE_PATH.unlink()
            except OSError:
                pass

        self._update_status("API credentials updated and saved to '.env'.")

    def has_valid_credentials(self):
        return bool(self.client_id and self.client_secret)

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

    def authenticate_spotify(self):
        """Initialize the Spotipy client using OAuth."""
        if self.sp is None:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=SCOPE,
                cache_path=str(CACHE_FILE_PATH)
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)

    @staticmethod
    def extract_playlist_id(url_or_id):
        """Extract the Spotify playlist ID from a URL or return the raw ID."""
        match = re.search(r"playlist/([a-zA-Z0-9]+)", url_or_id)
        if match:
            return match.group(1)
        return url_or_id.strip()

    # ==========================================
    # PHASE 1: TRACK EXTRACTION & FILTERING
    # ==========================================
    def start_extraction_thread(self):
        if not self.has_valid_credentials():
            messagebox.showinfo(
                "API Setup Required",
                "Please enter your Spotify Client ID and Client Secret in the API Settings window before starting."
            )
            self.open_settings_window()
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a Spotify playlist link or ID.")
            return
        if not self.selected_genres:
            messagebox.showwarning("No Genres Selected", "Please select at least one musical genre.")
            return

        self.start_btn.configure(state="disabled")
        self.import_btn.configure(state="disabled")
        self.search_var.set("")
        self._clear_preview_list()

        thread = threading.Thread(target=self._extract_tracks_worker, args=(url,), daemon=True)
        thread.start()

    def _extract_tracks_worker(self, url):
        try:
            self._update_status("Authenticating with Spotify...")
            self.authenticate_spotify()

            playlist_id = self.extract_playlist_id(url)
            self._update_status("Fetching playlist tracks (this may take a few seconds for 100+ hour playlists)...")

            # 1. Fetch all tracks handling pagination in batches of 100
            raw_tracks = []
            results = self.sp.playlist_items(
                playlist_id,
                additional_types=("track",),
                limit=100
            )

            while results:
                for item in results.get("items", []):
                    track = item.get("track")
                    # Skip local files or unavailable tracks
                    if track and track.get("id") and track.get("type") == "track":
                        raw_tracks.append(track)

                self._update_status(f"Downloading tracks... ({len(raw_tracks)} read)")
                if results.get("next"):
                    results = self.sp.next(results)
                else:
                    break

            if not raw_tracks:
                self._update_status("No valid tracks found in this playlist.")
                self._reenable_start()
                return

            # 2. Collect unique artist IDs and request genres in batches of 50
            unique_artist_ids = list({
                artist["id"]
                for track in raw_tracks
                for artist in track.get("artists", [])
                if artist.get("id")
            })

            self._update_status(f"Analyzing genres for {len(unique_artist_ids)} unique artists...")
            artist_genres_map = {}

            for i in range(0, len(unique_artist_ids), 50):
                batch_ids = unique_artist_ids[i:i + 50]
                artists_data = self.sp.artists(batch_ids).get("artists", [])
                for artist_obj in artists_data:
                    if artist_obj and artist_obj.get("id"):
                        artist_genres_map[artist_obj["id"]] = [
                            g.lower() for g in artist_obj.get("genres", [])
                        ]

            # 3. Filter tracks matching the selected genres
            matched_tracks = []
            seen_uris = set()

            for track in raw_tracks:
                uri = track["uri"]
                if uri in seen_uris:
                    continue

                artists = track.get("artists", [])
                if not artists:
                    continue

                # Combine genres from all artists credited on the track
                track_genres = set()
                for a in artists:
                    a_id = a.get("id")
                    if a_id in artist_genres_map:
                        track_genres.update(artist_genres_map[a_id])

                # Substring match to capture sub-genres (e.g., "pop" matches "dance pop")
                is_match = any(
                    sel_genre in sp_genre
                    for sel_genre in self.selected_genres
                    for sp_genre in track_genres
                )

                if is_match:
                    seen_uris.add(uri)
                    main_artist = artists[0]["name"]
                    feat_artists = [a["name"] for a in artists[1:]]
                    feat_str = f" (feat. {', '.join(feat_artists)})" if feat_artists else ""

                    matched_tracks.append({
                        "uri": uri,
                        "title": track.get("name", "Unknown Title"),
                        "album": track.get("album", {}).get("name", "Unknown Album"),
                        "author": main_artist,
                        "feat": feat_str
                    })

            # 4. Populate UI on the main thread
            self.after(0, self._populate_preview_list, matched_tracks, len(raw_tracks))

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Spotify API Error", f"An error occurred:\n{e}"))
            self._update_status("Error during track extraction.")
            self._reenable_start()

    def _populate_preview_list(self, matched_tracks, total_scanned):
        self.filtered_tracks = matched_tracks
        for track_data in self.filtered_tracks:
            self._create_track_row(track_data)

        self._update_counter_label()
        self._update_status(
            f"Extraction complete: {len(matched_tracks)} matching tracks found out of {total_scanned} scanned."
        )
        self.start_btn.configure(state="normal")
        if self.filtered_tracks:
            self.import_btn.configure(state="normal")

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
            self.import_btn.configure(state="disabled")

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
    # PHASE 2: PLAYLIST CREATION & IMPORT
    # ==========================================
    def start_import_thread(self):
        playlist_name = self.playlist_name_entry.get().strip()
        if not playlist_name:
            messagebox.showwarning("Missing Name", "Please enter a name for the new playlist before importing.")
            return
        if not self.filtered_tracks:
            messagebox.showwarning("Empty List", "There are no tracks left to import.")
            return

        self.import_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")

        thread = threading.Thread(
            target=self._import_playlist_worker,
            args=(playlist_name,),
            daemon=True
        )
        thread.start()

    def _import_playlist_worker(self, playlist_name):
        try:
            self._update_status("Creating new playlist in your Spotify account...")
            user_id = self.sp.current_user()["id"]
            genres_str = ", ".join(sorted(self.selected_genres))

            new_playlist = self.sp.user_playlist_create(
                user=user_id,
                name=playlist_name,
                public=False,
                description=f"Generated by SpotiSieve — Filtered genres: {genres_str}"
            )
            new_playlist_id = new_playlist["id"]

            # Add tracks in batches of 100 (Spotify API limit per request)
            uris = [t["uri"] for t in self.filtered_tracks]
            for i in range(0, len(uris), 100):
                batch = uris[i:i + 100]
                self.sp.playlist_add_items(new_playlist_id, batch)
                self._update_status(f"Importing tracks: {min(i + 100, len(uris))}/{len(uris)}...")

            self._update_status(f"Playlist '{playlist_name}' successfully created on Spotify!")
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Import Complete",
                    f"Playlist '{playlist_name}' ({len(uris)} tracks) is now available in your Spotify library!"
                )
            )
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Import Error", f"Failed to create playlist:\n{e}"))
            self._update_status("Error while importing playlist.")
        finally:
            self._reenable_start()
            self.after(0, lambda: self.import_btn.configure(state="normal"))

    def _update_status(self, message):
        self.after(0, lambda: self.status_label.configure(text=message))

    def _reenable_start(self):
        self.after(0, lambda: self.start_btn.configure(state="normal"))


if __name__ == "__main__":
    app = SpotifyGenreExtractorApp()
    app.mainloop()