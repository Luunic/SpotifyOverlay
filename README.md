# SpotifyOverlay
An minimalistic overlay for spotify
<img width="193" height="198" alt="spotifyOverlayDemo" src="https://github.com/user-attachments/assets/bdcebfd1-0044-4667-bced-b822b0dc1003" />
## Features
This repo provides an minimalistic overlay for spotify.
It can perform actions like Pause, Skip or setVolume

## Setup
 
### 1. Create a Spotify App
For this step you need a Spotify-Premium Account.
Go to https://developer.spotify.com/dashboard and login with your Spotify Account.
Then Create an App in the Dashboard.
Choose a Name and a Description.
For the Redirect URI use Following: http://127.0.0.1:8000/callback
For Api Use select Web API.
Finish Creation!


### 2. Get the Overlay
Option 1: Download the MusicOverlay.exe from executable\
Option 2: Download the sourceCode music_overlay.py from src\ and use the following command on it: `pyinstaller --onefile --windowed --name "MusicOverlay" music_overlay.py`
  After running that command you should find the MusicOverlay.exe in dist\

### 3 Setup the App
Open MusicOverlay.exe
Input your Client-ID and Client-Secret of your Spotify App.
(You can see them in the Spotify dashboard)
Click the Connect Button.

Now you are ready to use the Overlay
