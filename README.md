# SpotiSieve — Spotify Playlist Genre Extractor

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![Spotify API](https://img.shields.io/badge/Spotify_Web_API-1DB954?style=for-the-badge&logo=spotify&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-2b2b2b?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**SpotiSieve** is a fast, modern desktop application built with Python and CustomTkinter that lets you filter massive Spotify playlists (even 100+ hours / 2,000+ tracks) by musical genres, review and clean up the extracted tracklist, and import the result directly into your Spotify account as a brand-new playlist.

### Key Features
* **No Rate-Limit Bottlenecks:** Scans huge playlists (1,500–2,000+ songs) in seconds using smart pagination (100 tracks/batch) and artist batching (50 artists/request).
* **3x8 Interactive Genre Matrix:** Select and combine up to 24 musical genres simultaneously via light-up toggle buttons (automatically matches Spotify sub-genres like *italian trap*, *dance pop*, *melodic techno*, etc.).
* **Staging & Manual Cleanup (`✕`):** Preview all matched tracks with **Title**, **Main Artist**, **Featured Artists (`feat.`)**, and **Album** before creating the playlist. Remove any unwanted track with a single click.
* **1-Click Spotify Import:** Choose a custom name and export the filtered list directly to your personal Spotify library.

### Why Do You Need Your Own Spotify API Keys?
To protect user privacy and avoid global Spotify API rate limits, **this repository does not include pre-configured API keys**. Every user runs the app with their own free personal Spotify Developer credentials stored locally in a `.env` file (which is automatically ignored by Git). Obtaining your keys takes less than 2 minutes and is 100% free.

### Step 1: Get Your Free Spotify API Keys
1. Log in to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) using your Spotify account.
2. Click **Create app**.
3. Fill in the details:
   * **App name:** `SpotiSieve` (or any name you like)
   * **App description:** `Personal genre playlist filter`
   * **Redirect URI:** `http://127.0.0.1:8888/callback` *(Must match this exact URL!)*
4. Check the **Web API** box, accept the terms, and click **Save**.
5. Open your new app's **Settings** and copy your **Client ID** and **Client Secret**.

### Step 2: Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/SpotiSieve.git](https://github.com/YOUR_USERNAME/SpotiSieve.git)
   cd SpotiSieve
   ```

2. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(This installs `spotipy` for API communication, `customtkinter` for the GUI, and `python-dotenv` to keep your personal API keys private).*

3. **Configure your personal API keys:**
   * Duplicate the `.env.example` file and rename the copy to `.env`.
   * Open `.env` with any text editor and paste your personal keys:
     ```env
     SPOTIPY_CLIENT_ID="your_personal_client_id_here"
     SPOTIPY_CLIENT_SECRET="your_personal_client_secret_here"
     SPOTIPY_REDIRECT_URI="[http://127.0.0.1:8888/callback](http://127.0.0.1:8888/callback)"
     ```

4. **Run the application:**
   ```bash
   python spotify_extractor.py
   ```
   *Note: On the first run, your browser will open asking you to authorize the app on your Spotify account. Click **Agree** to complete the setup.*