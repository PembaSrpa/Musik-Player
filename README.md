# Music Player

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Usage

- Place `.mp3`, `.flac`, `.wav`, `.m4a`, `.ogg`, `.aac` files in `/music`
- Track list populates incrementally on startup (1000+ tracks load without blocking UI)
- Double-click a track to play
- Last played track, position, volume, shuffle, and repeat are restored on next launch
- Shuffle and repeat (off / all / one) toggle via buttons in the controls bar
- Minimize via yellow dot; close via red dot (saves state before exit)

## State file

Saved to `~/.config/musicplayer/state.json`

## Package to .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name musicplayer main.py
```
