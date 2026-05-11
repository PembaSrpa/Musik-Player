import json
import random
from enum import Enum
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4

from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QPixmap


MUSIC_DIR = Path.home() / "Music"
CONFIG_PATH = Path.home() / ".config" / "musicplayer" / "state.json"
SUPPORTED = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"}


class RepeatMode(Enum):
    OFF = 0
    ALL = 1
    ONE = 2


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _extract_cover(path: Path) -> bytes | None:
    try:
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            tags = ID3(path)
            for tag in tags.values():
                if hasattr(tag, "data"):
                    return tag.data
        elif suffix == ".flac":
            audio = FLAC(path)
            if audio.pictures:
                return audio.pictures[0].data
        elif suffix == ".m4a":
            audio = MP4(path)
            covers = audio.tags.get("covr")
            if covers:
                return bytes(covers[0])
    except Exception:
        pass
    return None


def read_metadata(path: Path) -> dict:
    track = {
        "path": str(path),
        "title": path.stem,
        "artist": "Unknown Artist",
        "duration": 0,
    }
    try:
        audio = MutagenFile(path, easy=True)
        if audio:
            track["title"] = (audio.get("title") or [path.stem])[0]
            track["artist"] = (audio.get("artist") or ["Unknown Artist"])[0]
            track["duration"] = int(audio.info.length) if hasattr(audio, "info") else 0
    except Exception:
        pass
    return track


class LibraryLoader(QThread):
    track_ready = pyqtSignal(dict)
    finished_loading = pyqtSignal()

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self):
        if not self._path.exists():
            self.finished_loading.emit()
            return
        files = sorted(
            f for f in self._path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED
        )
        for f in files:
            track = read_metadata(f)
            self.track_ready.emit(track)
        self.finished_loading.emit()


class Player(QObject):
    track_changed = pyqtSignal(dict)
    playback_changed = pyqtSignal(bool)
    position_changed = pyqtSignal(int, int)
    shuffle_changed = pyqtSignal(bool)
    repeat_changed = pyqtSignal(object)
    cover_ready = pyqtSignal(object)
    track_appended = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._media = QMediaPlayer()
        self._audio = QAudioOutput()
        self._media.setAudioOutput(self._audio)
        self._audio.setVolume(0.7)

        self._tracks: list[dict] = []
        self._queue: list[int] = []
        self._queue_pos: int = 0
        self._shuffle: bool = False
        self._repeat: RepeatMode = RepeatMode.OFF
        self._current: dict | None = None
        self._loader: LibraryLoader | None = None

        self._media.positionChanged.connect(self._on_position)
        self._media.playbackStateChanged.connect(self._on_state)
        self._media.mediaStatusChanged.connect(self._on_status)

    def load_library(self):
        self._loader = LibraryLoader(MUSIC_DIR)
        self._loader.track_ready.connect(self._on_track_loaded)
        self._loader.finished_loading.connect(self._on_library_done)
        self._loader.start()

    def _on_track_loaded(self, track: dict):
        self._tracks.append(track)
        self._queue.append(len(self._tracks) - 1)
        self.track_appended.emit(track)

    def _on_library_done(self):
        state = self._load_state()
        if not state:
            return

        vol = state.get("volume", 0.7)
        self._audio.setVolume(vol)

        shuffle = state.get("shuffle", False)
        if shuffle:
            self._shuffle = True
            self._rebuild_queue_preserving(None)

        repeat_val = state.get("repeat", 0)
        self._repeat = RepeatMode(repeat_val)

        idx = state.get("track_index", None)
        pos = state.get("position_ms", 0)

        if idx is not None and 0 <= idx < len(self._tracks):
            try:
                self._queue_pos = self._queue.index(idx)
            except ValueError:
                self._queue_pos = 0
            self._current = self._tracks[self._queue[self._queue_pos]]
            self._media.setSource(QUrl.fromLocalFile(self._current["path"]))
            self._media.pause()
            if pos > 0:
                self._media.setPosition(pos)
            self.track_changed.emit(self._current)
            self._load_cover_async(self._current)

    def _load_cover_async(self, track: dict):
        class CoverLoader(QThread):
            done = pyqtSignal(object)

            def __init__(self, path):
                super().__init__()
                self._path = path

            def run(self):
                data = _extract_cover(Path(self._path))
                if data:
                    px = QPixmap()
                    px.loadFromData(data)
                    self.done.emit(px)
                else:
                    self.done.emit(None)

        loader = CoverLoader(track["path"])
        loader.done.connect(lambda px: self.cover_ready.emit(px))
        loader.done.connect(loader.deleteLater)
        loader.start()
        self._cover_loader = loader

    def _rebuild_queue_preserving(self, current_idx: int | None):
        indices = list(range(len(self._tracks)))
        if self._shuffle:
            random.shuffle(indices)
        self._queue = indices
        if current_idx is not None and current_idx in self._queue:
            self._queue_pos = self._queue.index(current_idx)
        else:
            self._queue_pos = 0

    def play_index(self, index: int):
        if not 0 <= index < len(self._tracks):
            return
        try:
            self._queue_pos = self._queue.index(index)
        except ValueError:
            self._queue_pos = 0
        self._load_current()

    def _load_current(self):
        if not self._queue:
            return
        idx = self._queue[self._queue_pos]
        self._current = self._tracks[idx]
        self._media.setSource(QUrl.fromLocalFile(self._current["path"]))
        self._media.play()
        self.track_changed.emit(self._current)
        self._load_cover_async(self._current)

    def play_pause(self):
        if self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media.pause()
        else:
            if self._media.source().isEmpty() and self._tracks:
                self._load_current()
            else:
                self._media.play()

    def next(self):
        if not self._queue:
            return
        if self._repeat == RepeatMode.ONE:
            self._media.setPosition(0)
            self._media.play()
            return
        next_pos = self._queue_pos + 1
        if next_pos >= len(self._queue):
            if self._repeat == RepeatMode.ALL:
                self._queue_pos = 0
            else:
                return
        else:
            self._queue_pos = next_pos
        self._load_current()

    def prev(self):
        if not self._queue:
            return
        if self._media.position() > 3000:
            self._media.setPosition(0)
            return
        self._queue_pos = (self._queue_pos - 1) % len(self._queue)
        self._load_current()

    def seek(self, ms: int):
        self._media.setPosition(ms)

    def duration(self) -> int:
        return self._media.duration()

    def set_volume(self, value: float):
        self._audio.setVolume(value)

    def volume(self) -> float:
        return self._audio.volume()

    def set_shuffle(self, enabled: bool):
        self._shuffle = enabled
        current_idx = self._queue[self._queue_pos] if self._queue else None
        self._rebuild_queue_preserving(current_idx)
        self.shuffle_changed.emit(enabled)

    def set_repeat(self, mode: RepeatMode):
        self._repeat = mode
        self.repeat_changed.emit(mode)

    def cycle_repeat(self):
        modes = list(RepeatMode)
        next_mode = modes[(self._repeat.value + 1) % len(modes)]
        self.set_repeat(next_mode)

    def is_playing(self) -> bool:
        return self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_shuffle(self) -> bool:
        return self._shuffle

    def repeat_mode(self) -> RepeatMode:
        return self._repeat

    def tracks(self) -> list[dict]:
        return self._tracks

    def current(self) -> dict | None:
        return self._current

    def current_index(self) -> int | None:
        if not self._queue:
            return None
        return self._queue[self._queue_pos]

    def save_state(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "track_index": self.current_index(),
            "position_ms": self._media.position(),
            "volume": self._audio.volume(),
            "shuffle": self._shuffle,
            "repeat": self._repeat.value,
        }
        CONFIG_PATH.write_text(json.dumps(state))

    def _load_state(self) -> dict | None:
        if not CONFIG_PATH.exists():
            return None
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return None

    def _on_position(self, pos: int):
        dur = self._media.duration()
        self.position_changed.emit(pos, dur)

    def _on_state(self, state):
        self.playback_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.next()
