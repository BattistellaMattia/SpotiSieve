import pytest
from spotify_extractor import SpotifyGenreExtractorApp, GENRES_LIST


def test_playlist_id_extraction():
    """Verify Spotify URL parsing and raw ID handling."""
    url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc12345"
    assert SpotifyGenreExtractorApp.extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"
    assert SpotifyGenreExtractorApp.extract_playlist_id("  37i9dQZF1DXcBWIGoYBM5M  ") == "37i9dQZF1DXcBWIGoYBM5M"


def test_env_placeholder_sanitization():
    """Ensure placeholder values from .env.example are rejected."""
    assert SpotifyGenreExtractorApp._clean_env_val("your_personal_client_id_here") == ""
    assert SpotifyGenreExtractorApp._clean_env_val("inserisci_qui_il_tuo_client_id") == ""
    assert SpotifyGenreExtractorApp._clean_env_val("  valid_client_id_123  ") == "valid_client_id_123"


def test_gui_boot_and_genre_toggle():
    """Smoke test: boot the actual CustomTkinter GUI, toggle a genre, and exit cleanly."""
    app = SpotifyGenreExtractorApp()

    # Verify all 24 genre buttons rendered properly
    assert len(app.genre_buttons) == len(GENRES_LIST) == 24

    # Simulate clicking 'rock' on and off
    app.toggle_genre("rock")
    assert "rock" in app.selected_genres
    app.toggle_genre("rock")
    assert "rock" not in app.selected_genres

    # Schedule automatic window destruction after 300ms and run the event loop
    app.after(300, app.destroy)
    app.mainloop()