import pytest
import tkinter

import spotify_extractor as se
from spotify_extractor import SpotifyGenreExtractorApp, GENRES_LIST

TRACK_A = "37i9dQZF1DXcBWIGoYBM5M"   # 22 characters, like a real Spotify ID
TRACK_B = "4uLU6hMCjMI75M1A2tKUQC"


def write_csv(path, text):
    path.write_text(text, encoding="utf-8-sig")
    return path


def test_parse_track_uri_accepts_uri_link_and_bare_id():
    expected = f"spotify:track:{TRACK_A}"
    assert se.parse_track_uri(f"spotify:track:{TRACK_A}") == expected
    assert se.parse_track_uri(f"https://open.spotify.com/track/{TRACK_A}?si=abc") == expected
    assert se.parse_track_uri(f"  {TRACK_A}  ") == expected
    assert se.parse_track_uri("not a track") is None
    assert se.uri_to_link(expected) == f"https://open.spotify.com/track/{TRACK_A}"


def test_genre_matching_is_word_based():
    assert se.genre_matches("pop", "dance pop")
    assert se.genre_matches("pop", "k-pop")
    assert se.genre_matches("trap", "italian trap")
    assert not se.genre_matches("rap", "trap")        # no false positives inside a word
    assert se.genre_matches("hip hop", "Hip-Hop")
    assert se.genre_matches("r&b", "contemporary r&b")
    assert se.genre_matches("lo-fi", "lofi beats")
    assert se.genre_matches("electronic", "electronica")
    assert not se.genre_matches("rock", "rocksteady")


def test_parse_exportify_csv_with_genres_and_duplicates(tmp_path):
    csv_file = write_csv(tmp_path / "playlist.csv", (
        "Track URI,Track Name,Artist Name(s),Album Name,Genres\n"
        f"spotify:track:{TRACK_A},Song A,Main Artist;Guest,Album A,\"rock, indie rock\"\n"
        f"spotify:track:{TRACK_A},Song A (again),Main Artist,Album A,rock\n"   # duplicate URI
        f"spotify:track:{TRACK_B},Song B,Other Artist,Album B,\n"
    ))
    tracks = se.parse_playlist_csv(csv_file)
    assert [t["title"] for t in tracks] == ["Song A", "Song B"]
    assert tracks[0]["artists"] == ["Main Artist", "Guest"]
    assert tracks[0]["csv_genres"] == ["rock", "indie rock"]
    assert tracks[1]["csv_genres"] == []
    assert tracks[0]["spotify_uri"] == f"spotify:track:{TRACK_A}"


def test_parse_csv_without_uri_column_still_works(tmp_path):
    csv_file = write_csv(tmp_path / "plain.csv", "Title;Artist\nSong;Someone\n")
    tracks = se.parse_playlist_csv(csv_file)
    assert len(tracks) == 1
    assert tracks[0]["spotify_uri"] is None and tracks[0]["uri"].startswith("row:")


def test_parse_csv_rejects_unknown_format(tmp_path):
    csv_file = write_csv(tmp_path / "bad.csv", "foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        se.parse_playlist_csv(csv_file)


def test_musicbrainz_helpers():
    candidates = [
        {"name": "Maneskin Tribute", "score": 100},
        {"name": "Måneskin", "score": 98,
         "tags": [{"name": "Rock", "count": 5}, {"name": "glam rock", "count": 9}, {"name": "bad", "count": 0}]},
    ]
    best = se.pick_best_artist("Maneskin", candidates)
    assert best["name"] == "Måneskin"                 # accent-insensitive exact match
    assert se.extract_tags(best) == ["glam rock", "rock"]
    assert se.pick_best_artist("Nobody", candidates) is None


def test_genre_lookup_uses_cache_and_throttles(tmp_path):
    calls, sleeps, now = [], [], [100.0]

    def fake_fetch(name):
        calls.append(name)
        return ["rock"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    cache_file = tmp_path / "genre_cache.json"
    lookup = se.GenreLookup(cache_file, fetcher=fake_fetch, min_interval=1.0,
                            sleep=fake_sleep, clock=lambda: now[0])
    assert lookup.get("Artist One") == ["rock"]
    assert lookup.get("artist one") == ["rock"]       # served from cache
    assert lookup.get("Artist Two") == ["rock"]
    assert calls == ["Artist One", "Artist Two"]
    assert len(sleeps) == 1                           # second request had to wait
    lookup.save()

    reloaded = se.GenreLookup(cache_file, fetcher=lambda n: pytest.fail("should use cache"))
    assert reloaded.get("Artist Two") == ["rock"]


def test_gui_boot_and_genre_toggle():
    """Smoke test: boot the actual CustomTkinter GUI, toggle a genre, and exit cleanly."""
    try:
        app = SpotifyGenreExtractorApp()
    except tkinter.TclError:
        pytest.skip("No display available for the GUI smoke test")

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


def test_end_to_end_extraction_without_network(tmp_path):
    """Load a CSV in the real GUI, filter by genre using a fake genre service, check the result."""
    try:
        app = SpotifyGenreExtractorApp()
    except tkinter.TclError:
        pytest.skip("No display available for the GUI smoke test")

    csv_file = write_csv(tmp_path / "playlist.csv", (
        "Track URI,Track Name,Artist Name(s),Album Name\n"
        f"spotify:track:{TRACK_A},Rock Song,Rocker,Album A\n"
        f"spotify:track:{TRACK_B},Pop Song,Popper,Album B\n"
    ))
    genres_by_artist = {"Rocker": ["hard rock"], "Popper": ["dance pop"]}
    app.genre_lookup = se.GenreLookup(tmp_path / "cache.json", fetcher=lambda n: genres_by_artist[n],
                                      min_interval=0)
    app.path_entry.insert(0, str(csv_file))
    app.toggle_genre("rock")
    app.start_extraction_thread()

    def check():
        if app.running or not app.filtered_tracks:
            app.after(100, check)
            return
        assert [t["title"] for t in app.filtered_tracks] == ["Rock Song"]
        assert app.copy_btn.cget("state") == "normal"
        app.destroy()

    app.after(100, check)
    app.after(8000, app.destroy)   # safety net so the test can never hang
    app.mainloop()
    assert [t["title"] for t in app.filtered_tracks] == ["Rock Song"]


def test_exportify_button_opens_https_page(monkeypatch):
    """The 'Get your CSV' button must open the Exportify website in the browser."""
    opened = []
    monkeypatch.setattr(se.webbrowser, "open", lambda url: opened.append(url) or True)
    try:
        app = SpotifyGenreExtractorApp()
    except tkinter.TclError:
        pytest.skip("No display available for the GUI smoke test")

    app.exportify_btn.invoke()
    app.destroy()
    assert opened == [se.EXPORTIFY_URL]
    assert se.EXPORTIFY_URL.startswith("https://")