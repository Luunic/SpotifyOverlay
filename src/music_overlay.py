"""
Music Player Overlay – PyQt6 + Spotipy
========================================
On first launch a setup dialog appears for Spotify credentials.
On Windows, credentials are stored in the Windows Credential Manager (no
plaintext on disk). On other platforms a plain JSON fallback is used.
"""

import sys, os, json

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QSlider, QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QRectF, QPointF, QThread, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QPainterPath,
    QLinearGradient, QBrush, QPen, QMouseEvent, QPolygonF
)

# ══════════════════════════════════════════════════════════
#  Color constants
# ══════════════════════════════════════════════════════════

C_BG    = QColor("#02111B")
C_CHAR  = QColor("#3F4045")
C_PLUM  = QColor("#30292F")
C_STEEL = QColor("#5D737E")
C_WHITE = QColor("#FCFCFC")
C_DIM   = QColor("#6A8090")

REDIRECT_URI = "http://127.0.0.1:8000/callback"
CONFIG_DIR   = os.path.join(os.path.expanduser("~"), ".musicoverlay")
CACHE_FILE   = os.path.join(CONFIG_DIR, "spotify_cache")
CRED_TARGET  = "MusicOverlay_Spotify"   # key name in Windows Credential Manager
_JSON_FILE   = os.path.join(CONFIG_DIR, "config.json")  # fallback for non-Windows


# ══════════════════════════════════════════════════════════
#  Credential storage
#  Windows  → Credential Manager (no plaintext on disk)
#  Other OS → ~/.musicoverlay/config.json
# ══════════════════════════════════════════════════════════

def _wincred_available() -> bool:
    return sys.platform == "win32"

def load_config() -> dict | None:
    """Load stored credentials. Returns None if not found."""
    return _wincred_load() if _wincred_available() else _json_load()

def save_config(client_id: str, client_secret: str):
    """Save credentials securely."""
    if _wincred_available():
        _wincred_save(client_id, client_secret)
    else:
        _json_save(client_id, client_secret)

# ── Windows Credential Manager ────────────────────────────

def _wincred_save(client_id: str, client_secret: str):
    """Store both credentials as a single blob in Windows Credential Manager."""
    import ctypes, ctypes.wintypes

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags",              ctypes.wintypes.DWORD),
            ("Type",               ctypes.wintypes.DWORD),
            ("TargetName",         ctypes.wintypes.LPWSTR),
            ("Comment",            ctypes.wintypes.LPWSTR),
            ("LastWritten",        ctypes.c_int64),
            ("CredentialBlobSize", ctypes.wintypes.DWORD),
            ("CredentialBlob",     ctypes.POINTER(ctypes.c_byte)),
            ("Persist",            ctypes.wintypes.DWORD),
            ("AttributeCount",     ctypes.wintypes.DWORD),
            ("Attributes",         ctypes.c_void_p),
            ("TargetAlias",        ctypes.wintypes.LPWSTR),
            ("UserName",           ctypes.wintypes.LPWSTR),
        ]

    # Pack both values separated by "|" into UTF-16-LE blob
    blob       = f"{client_id}|{client_secret}".encode("utf-16-le")
    blob_array = (ctypes.c_byte * len(blob))(*blob)

    cred = _CREDENTIAL()
    cred.Flags              = 0
    cred.Type               = 1            # CRED_TYPE_GENERIC
    cred.TargetName         = CRED_TARGET
    cred.Comment            = "Spotify credentials for MusicOverlay"
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob     = blob_array
    cred.Persist            = 2            # CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount     = 0
    cred.Attributes         = None
    cred.TargetAlias        = None
    cred.UserName           = "musicoverlay"

    if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise RuntimeError(f"CredWriteW failed (error {ctypes.GetLastError()})")

def _wincred_load() -> dict | None:
    """Read credentials from Windows Credential Manager."""
    import ctypes, ctypes.wintypes

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags",              ctypes.wintypes.DWORD),
            ("Type",               ctypes.wintypes.DWORD),
            ("TargetName",         ctypes.wintypes.LPWSTR),
            ("Comment",            ctypes.wintypes.LPWSTR),
            ("LastWritten",        ctypes.c_int64),
            ("CredentialBlobSize", ctypes.wintypes.DWORD),
            ("CredentialBlob",     ctypes.POINTER(ctypes.c_byte)),
            ("Persist",            ctypes.wintypes.DWORD),
            ("AttributeCount",     ctypes.wintypes.DWORD),
            ("Attributes",         ctypes.c_void_p),
            ("TargetAlias",        ctypes.wintypes.LPWSTR),
            ("UserName",           ctypes.wintypes.LPWSTR),
        ]

    advapi = ctypes.windll.advapi32
    p_cred = ctypes.POINTER(_CREDENTIAL)()
    if not advapi.CredReadW(CRED_TARGET, 1, 0, ctypes.byref(p_cred)):
        return None  # entry not found
    try:
        cred = p_cred.contents
        blob = bytes(cred.CredentialBlob[:cred.CredentialBlobSize])
        text = blob.decode("utf-16-le")
        parts = text.split("|", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return {"client_id": parts[0], "client_secret": parts[1]}
    except Exception as e:
        print(f"[Creds] wincred read error: {e}")
    finally:
        advapi.CredFree(p_cred)
    return None

# ── JSON fallback (macOS / Linux) ────────────────────────

def _json_save(client_id: str, client_secret: str):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(_JSON_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f)

def _json_load() -> dict | None:
    if not os.path.exists(_JSON_FILE):
        return None
    try:
        with open(_JSON_FILE, "r") as f:
            data = json.load(f)
        if data.get("client_id") and data.get("client_secret"):
            return data
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════
#  Spotify init & API wrapper
# ══════════════════════════════════════════════════════════

Sp = None

def init_spotify(client_id: str, client_secret: str) -> bool:
    """Initialize Spotipy with the given credentials. Returns True on success."""
    global Sp
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        os.makedirs(CONFIG_DIR, exist_ok=True)
        Sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=REDIRECT_URI,
            scope="user-read-playback-state user-modify-playback-state",
            cache_path=CACHE_FILE,
            open_browser=True,
        ))
        # Test connection
        Sp.current_playback()
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"[Spotify] init error: {e}")
        Sp = None
        return False


class MusicAPI:

    @staticmethod
    def get_current_track() -> dict:
        """
        Fetch the currently playing track from Spotify.
        Returns a dict: title, artist, cover_url, volume (0–1), is_playing.
        """
        if Sp is None:
            return {"title": "Not connected", "artist": "", "cover_url": None,
                    "volume": 0.5, "is_playing": False}
        try:
            pb = Sp.current_playback()
            if pb is None:
                return {"title": "Nothing playing", "artist": "", "cover_url": None,
                        "volume": 0.5, "is_playing": False}
            item    = pb.get("item") or {}
            device  = pb.get("device") or {}
            title   = item.get("name", "Unknown")
            artists = item.get("artists") or []
            artist  = ", ".join(a["name"] for a in artists)
            # Smallest image (last in list) for fast loading
            images    = (item.get("album") or {}).get("images") or []
            cover_url = images[-1].get("url") if images else None
            return {
                "title":      title,
                "artist":     artist,
                "cover_url":  cover_url,
                "volume":     (device.get("volume_percent") or 0) / 100.0,
                "is_playing": pb.get("is_playing", False),
            }
        except Exception as e:
            print(f"[Spotify] get_current_track: {e}")
            return {"title": "Error", "artist": str(e)[:30], "cover_url": None,
                    "volume": 0.5, "is_playing": False}

    @staticmethod
    def play_pause():
        """Toggle playback – pauses if playing, resumes if paused."""
        if Sp is None: return
        try:
            pb = Sp.current_playback()
            Sp.pause_playback() if (pb and pb.get("is_playing")) else Sp.start_playback()
        except Exception as e:
            print(f"[Spotify] play_pause: {e}")

    @staticmethod
    def next_track():
        """Skip to the next track."""
        if Sp is None: return
        try: Sp.next_track()
        except Exception as e: print(f"[Spotify] next_track: {e}")

    @staticmethod
    def previous_track():
        """Go back to the previous track."""
        if Sp is None: return
        try: Sp.previous_track()
        except Exception as e: print(f"[Spotify] previous_track: {e}")

    @staticmethod
    def set_volume(value: float):
        """Set playback volume. value is in range 0.0–1.0."""
        if Sp is None: return
        try: Sp.volume(int(value * 100))
        except Exception as e: print(f"[Spotify] set_volume: {e}")


# ══════════════════════════════════════════════════════════
#  Close button – painted X circle, reused in both windows
# ══════════════════════════════════════════════════════════

class CloseButton(QPushButton):
    """Small circular button with a painted X. Turns red on hover."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._hovered = self._pressed = False

    def enterEvent(self, e):        self._hovered = True;  self.update()
    def leaveEvent(self, e):        self._hovered = False; self.update()
    def mousePressEvent(self, e):   self._pressed = True;  super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._pressed = False; super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Circle background
        if self._pressed:   bg = QColor(180, 60, 60, 210)
        elif self._hovered: bg = QColor(180, 60, 60, 150)
        else:               bg = QColor(93, 115, 126, 45)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawEllipse(0, 0, w, h)
        # X strokes
        icon_col = C_WHITE if self._hovered else C_DIM
        p.setPen(QPen(icon_col, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        m = 6
        p.drawLine(m, m, w - m, h - m)
        p.drawLine(w - m, m, m, h - m)
        p.end()


# ══════════════════════════════════════════════════════════
#  Setup dialog
# ══════════════════════════════════════════════════════════

SETUP_SS = """
    QWidget#setupWin {
        background-color: #02111B;
        border-radius: 16px;
        border: 1px solid rgba(93,115,126,0.30);
    }
    QLabel#h1 {
        color: #FCFCFC; font-size: 15px; font-weight: 700;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#sub {
        color: #5D737E; font-size: 10px;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#lbl {
        color: #9AAFB8; font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#hint {
        color: #3F5560; font-size: 9px;
        font-family: 'Segoe UI', sans-serif;
    }
    QLineEdit {
        background: rgba(93,115,126,0.12);
        border: 1px solid rgba(93,115,126,0.30);
        border-radius: 8px; color: #FCFCFC;
        font-size: 11px; font-family: 'Segoe UI', sans-serif;
        padding: 6px 10px;
        selection-background-color: #5D737E;
    }
    QLineEdit:focus {
        border: 1px solid #5D737E;
        background: rgba(93,115,126,0.20);
    }
    QPushButton#btnSave {
        background: #5D737E; color: #FCFCFC; border: none;
        border-radius: 9px; font-size: 12px; font-weight: 600;
        font-family: 'Segoe UI', sans-serif; padding: 8px 0;
    }
    QPushButton#btnSave:hover   { background: #6D8E9B; }
    QPushButton#btnSave:pressed { background: #3A5560; }
    QWidget#sep { background: rgba(93,115,126,0.18); }
"""

class SetupDialog(QWidget):
    """
    Credential setup window – shown on first launch or via the settings gear.
    Emits `done` when login succeeds.
    """
    done = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.97)
        self._drag_pos = QPoint()
        self._build_ui()

        # Center on primary screen
        self.adjustSize()
        geo = QApplication.primaryScreen().geometry()
        self.move(geo.center().x() - self.width() // 2,
                  geo.center().y() - self.height() // 2)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        win = QWidget()
        win.setObjectName("setupWin")
        outer.addWidget(win)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8); shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        win.setGraphicsEffect(shadow)

        lay = QVBoxLayout(win)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(0)

        # Close button – parented to `win` so it sits inside the rounded border.
        # We position it in resizeEvent so it always hugs the inner top-right corner.
        self.btn_close = CloseButton(win)
        self.btn_close.clicked.connect(self.close)

        # Title row
        h1  = QLabel("Spotify verbinden");  h1.setObjectName("h1")
        sub = QLabel("Gib deine App-Credentials vom Spotify Developer Dashboard ein")
        sub.setObjectName("sub"); sub.setWordWrap(True)
        lay.addWidget(h1); lay.addSpacing(4); lay.addWidget(sub); lay.addSpacing(16)

        sep = QWidget(); sep.setObjectName("sep"); sep.setFixedHeight(1)
        lay.addWidget(sep); lay.addSpacing(16)

        # Client ID
        lbl_id = QLabel("Client ID"); lbl_id.setObjectName("lbl")
        self.inp_id = QLineEdit()
        self.inp_id.setPlaceholderText("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        lay.addWidget(lbl_id); lay.addSpacing(4); lay.addWidget(self.inp_id)
        lay.addSpacing(12)

        # Client Secret
        lbl_sec = QLabel("Client Secret"); lbl_sec.setObjectName("lbl")
        self.inp_sec = QLineEdit()
        self.inp_sec.setPlaceholderText("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        self.inp_sec.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(lbl_sec); lay.addSpacing(4); lay.addWidget(self.inp_sec)
        lay.addSpacing(6)

        hint = QLabel(f"Redirect URI in your Spotify app: {REDIRECT_URI}")
        hint.setObjectName("hint"); hint.setWordWrap(True)
        lay.addWidget(hint); lay.addSpacing(18)

        self.btn_save = QPushButton("Verbinden & starten")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)
        lay.addWidget(self.btn_save)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("hint")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        lay.addSpacing(6); lay.addWidget(self.lbl_status)

        self.setStyleSheet(SETUP_SS)
        self.setFixedWidth(320)

    def resizeEvent(self, e):
        """Pin close button to inner top-right corner of the dialog card."""
        super().resizeEvent(e)
        # outer margin = 10, inner right padding = 22 → position 10+22-18-4 = 10
        inner_right  = self.width() - 10    # right edge of win widget
        btn_right    = inner_right - 10     # 10 px from inner right edge
        btn_top      = 10 + 10              # outer margin + 10 px from inner top
        self.btn_close.move(btn_right - self.btn_close.width(), btn_top)

    def _on_save(self):
        cid = self.inp_id.text().strip()
        sec = self.inp_sec.text().strip()
        if not cid or not sec:
            self.lbl_status.setText("Please fill in both fields.")
            self.lbl_status.setStyleSheet("color: #E07070; font-size: 9px;")
            return
        self.btn_save.setText("Connecting…")
        self.btn_save.setEnabled(False)
        self.lbl_status.setText("")
        QApplication.processEvents()

        if init_spotify(cid, sec):
            save_config(cid, sec)
            self.done.emit()
            self.close()
        else:
            self.btn_save.setText("Verbinden & starten")
            self.btn_save.setEnabled(True)
            self.lbl_status.setText(
                "Connection failed. Check your credentials and make sure\n"
                f"{REDIRECT_URI} is registered in your Spotify app."
            )
            self.lbl_status.setStyleSheet("color: #E07070; font-size: 9px;")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)


# ══════════════════════════════════════════════════════════
#  Playback control buttons (all drawn via QPainter)
# ══════════════════════════════════════════════════════════

class IconButton(QPushButton):
    """Base for playback buttons – handles hover/press state and background painting."""
    def __init__(self, size=28, primary=False, parent=None):
        super().__init__(parent)
        self._primary = primary
        self._hovered = self._pressed = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

    def enterEvent(self, e):        self._hovered = True;  self.update()
    def leaveEvent(self, e):        self._hovered = False; self.update()
    def mousePressEvent(self, e):   self._pressed = True;  super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._pressed = False; super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._primary:
            bg = QColor("#3A5560") if self._pressed else (QColor("#6D8E9B") if self._hovered else QColor("#5D737E"))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(bg))
            p.drawEllipse(0, 0, w, h)
            icon_col = C_WHITE
        else:
            bg = QColor(93,115,126,55) if self._pressed else (QColor(93,115,126,28) if self._hovered else QColor(0,0,0,0))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(bg))
            p.drawRoundedRect(0, 0, w, h, w//2, h//2)
            icon_col = C_WHITE if self._hovered else C_DIM
        self._draw_icon(p, QRect(0, 0, w, h), icon_col)
        p.end()

    def _draw_icon(self, painter, rect, color): pass


class PlayPauseButton(IconButton):
    def __init__(self, parent=None):
        super().__init__(size=36, primary=True, parent=parent)
        self.playing = True

    def _draw_icon(self, p, rect, color):
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(color))
        cx, cy = rect.center().x(), rect.center().y()
        if self.playing:
            # Two bars = pause
            p.drawRoundedRect(cx-6, cy-6, 4, 13, 2, 2)
            p.drawRoundedRect(cx+4, cy-6, 4, 13, 2, 2)
        else:
            # Triangle = play
            p.drawPolygon(QPolygonF([QPointF(cx-4,cy-8), QPointF(cx-4,cy+8), QPointF(cx+9,cy)]))


class PrevButton(IconButton):
    def __init__(self, parent=None): super().__init__(size=28, parent=parent)
    def _draw_icon(self, p, rect, color):
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(color))
        cx, cy = rect.center().x(), rect.center().y()
        p.drawRoundedRect(cx-7, cy-6, 3, 12, 1, 1)
        p.drawPolygon(QPolygonF([QPointF(cx+6,cy-6), QPointF(cx+6,cy+6), QPointF(cx-4,cy)]))


class NextButton(IconButton):
    def __init__(self, parent=None): super().__init__(size=28, parent=parent)
    def _draw_icon(self, p, rect, color):
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(color))
        cx, cy = rect.center().x(), rect.center().y()
        p.drawRoundedRect(cx+4, cy-6, 3, 12, 1, 1)
        p.drawPolygon(QPolygonF([QPointF(cx-6,cy-6), QPointF(cx-6,cy+6), QPointF(cx+4,cy)]))


class VolumeIcon(QWidget):
    """Painted speaker icon placed left of the volume slider."""
    def __init__(self, size=15, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._s = size

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s, cy = self._s, self._s // 2
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(C_DIM))
        p.drawPolygon(QPolygonF([QPointF(1,cy-3), QPointF(5,cy-3), QPointF(8,cy-6),
                                  QPointF(8,cy+6), QPointF(5,cy+3), QPointF(1,cy+3)]))
        p.setPen(QPen(C_DIM, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(9, cy-3, 3, 6, -90*16, 180*16)
        p.drawArc(10, cy-5, 5, 10, -90*16, 180*16)
        p.end()


# ══════════════════════════════════════════════════════════
#  Album cover widget
# ══════════════════════════════════════════════════════════

class CoverLabel(QWidget):
    """Rounded album art with a gradient placeholder when no cover is loaded."""
    def __init__(self, size=60, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._pixmap = None

    def set_cover(self, pixmap):
        self._pixmap = pixmap.scaled(
            self._size, self._size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        ) if (pixmap and not pixmap.isNull()) else None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, s, s), 10, 10)
        p.setClipPath(path)
        if self._pixmap:
            p.drawPixmap(0, 0, self._pixmap)
        else:
            grad = QLinearGradient(0, 0, s, s)
            grad.setColorAt(0, QColor("#2A3540")); grad.setColorAt(1, QColor("#30292F"))
            p.fillPath(path, QBrush(grad))
            p.setPen(C_STEEL)
            p.setFont(QFont("Segoe UI", int(s * 0.3)))
            p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "♪")
        p.end()


# ══════════════════════════════════════════════════════════
#  Main overlay window
# ══════════════════════════════════════════════════════════

class MusicOverlay(QWidget):

    POLL_MS = 3000  # Spotify polling interval in ms

    def __init__(self):
        super().__init__()
        self._drag_pos   = QPoint()
        self._is_playing = True
        self._opacity    = 0.93
        self._last_cover = None  # tracks last cover URL to avoid re-downloading

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self._opacity)
        self.move(16, 16)

        self._build_ui()
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.POLL_MS)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.container = QWidget()
        self.container.setObjectName("container")
        outer.addWidget(self.container)

        # Minimal shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8); shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(shadow)

        main = QVBoxLayout(self.container)
        main.setContentsMargins(14, 13, 14, 12)
        main.setSpacing(10)

        # ── Top row: cover + info + X button ─────────────
        # The X is placed as an absolute widget over the container in resizeEvent.
        self.btn_close = CloseButton(self.container)
        self.btn_close.clicked.connect(QApplication.instance().quit)

        row1 = QHBoxLayout(); row1.setSpacing(12)
        self.cover = CoverLabel(60)
        row1.addWidget(self.cover)

        info = QVBoxLayout(); info.setSpacing(3)
        self.lbl_title  = QLabel("Loading…"); self.lbl_title.setObjectName("lblTitle")
        self.lbl_artist = QLabel("");          self.lbl_artist.setObjectName("lblArtist")
        # Ignored horizontal so text doesn't push the layout wider than the window
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addStretch(); info.addWidget(self.lbl_title)
        info.addWidget(self.lbl_artist); info.addStretch()
        row1.addLayout(info, 1)
        main.addLayout(row1)

        # ── Separator ─────────────────────────────────────
        sep = QWidget(); sep.setFixedHeight(1); sep.setObjectName("sep")
        main.addWidget(sep)

        # ── Playback controls ─────────────────────────────
        row2 = QHBoxLayout(); row2.setSpacing(0); row2.addStretch()
        self.btn_prev = PrevButton()
        self.btn_play = PlayPauseButton()
        self.btn_next = NextButton()
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_play.clicked.connect(self._on_play_pause)
        self.btn_next.clicked.connect(self._on_next)
        row2.addWidget(self.btn_prev); row2.addSpacing(8)
        row2.addWidget(self.btn_play); row2.addSpacing(8)
        row2.addWidget(self.btn_next); row2.addStretch()
        main.addLayout(row2)

        # ── Volume slider ─────────────────────────────────
        row3 = QHBoxLayout(); row3.setSpacing(8)
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100); self.slider_vol.setValue(60)
        self.slider_vol.setObjectName("volSlider")
        self.slider_vol.valueChanged.connect(self._on_volume_change)
        row3.addWidget(VolumeIcon(15))
        row3.addWidget(self.slider_vol, 1)
        main.addLayout(row3)

        # ── Bottom row: settings gear only ───────────────
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("btnGear")
        self.btn_settings.setFixedSize(18, 18)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setFlat(True)
        self.btn_settings.clicked.connect(self._open_settings)

        gear_row = QHBoxLayout()
        gear_row.addWidget(self.btn_settings)
        gear_row.addStretch()
        main.addLayout(gear_row)

        self._apply_ss()
        self.adjustSize()

    def resizeEvent(self, e):
        """Pin the X button to the inner top-right corner of the container."""
        super().resizeEvent(e)
        m  = 6   # outer layout margin
        pad = 8  # gap from inner border
        x  = self.container.width() - self.btn_close.width() - pad
        y  = pad
        self.btn_close.move(x, y)

    def _apply_ss(self):
        self.container.setStyleSheet("""
            QWidget#container {
                background-color: #02111B;
                border-radius: 18px;
                border: 1px solid rgba(93,115,126,0.22);
            }
            QLabel#lblTitle {
                color: #FCFCFC; font-size: 13px; font-weight: 700;
                font-family: 'Segoe UI', sans-serif; letter-spacing: 0.1px;
            }
            QLabel#lblArtist {
                color: #5D737E; font-size: 10px;
                font-family: 'Segoe UI', sans-serif; letter-spacing: 0.4px;
            }
            QWidget#sep { background: rgba(93,115,126,0.18); }
            QPushButton#btnGear {
                color: rgba(93,115,126,0.4); font-size: 11px;
                background: transparent; border: none;
            }
            QPushButton#btnGear:hover { color: #5D737E; }
            QSlider#volSlider { height: 16px; }
            QSlider#volSlider::groove:horizontal {
                height: 3px; background: #3F4045; border-radius: 2px;
            }
            QSlider#volSlider::sub-page:horizontal {
                background: #5D737E; border-radius: 2px; height: 3px;
            }
            QSlider#volSlider::handle:horizontal {
                background: #FCFCFC; width: 10px; height: 10px;
                margin: -4px 0; border-radius: 5px;
            }
            QSlider#volSlider::handle:horizontal:hover {
                background: #5D737E; width: 12px; height: 12px;
                margin: -5px 0; border-radius: 6px;
            }
        """)

    # ── Playback slots ─────────────────────────────────────

    def _on_play_pause(self):
        MusicAPI.play_pause()
        self._is_playing = not self._is_playing
        self.btn_play.playing = self._is_playing
        self.btn_play.update()

    def _on_next(self):
        MusicAPI.next_track()
        QTimer.singleShot(400, self._refresh)

    def _on_prev(self):
        MusicAPI.previous_track()
        QTimer.singleShot(400, self._refresh)

    def _on_volume_change(self, value):
        MusicAPI.set_volume(value / 100.0)

    def _open_settings(self):
        """Open the credential setup dialog."""
        self._setup = SetupDialog()
        self._setup.done.connect(self._refresh)
        self._setup.show()

    def _refresh(self):
        """Poll Spotify and update all UI elements."""
        try:
            track = MusicAPI.get_current_track()
        except Exception as e:
            print(f"[Overlay] refresh error: {e}")
            return

        title = track.get("title", "Unknown")
        if len(title) > 24: title = title[:22] + "…"
        self.lbl_title.setText(title)
        self.lbl_artist.setText(track.get("artist", ""))

        self._is_playing = track.get("is_playing", True)
        self.btn_play.playing = self._is_playing
        self.btn_play.update()

        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(int(track.get("volume", 0.5) * 100))
        self.slider_vol.blockSignals(False)

        # Only re-download cover when the URL changes
        cover_url = track.get("cover_url")
        if cover_url and cover_url != self._last_cover:
            self._last_cover = cover_url
            self._load_cover(cover_url)
        elif not cover_url:
            self._last_cover = None
            self.cover.set_cover(None)

    def _load_cover(self, source: str):
        """Load album art from a URL or local file path."""
        try:
            if source.startswith("http"):
                from urllib.request import urlretrieve
                import tempfile
                tmp = tempfile.mktemp(suffix=".jpg")
                urlretrieve(source, tmp)
                px = QPixmap(tmp)
                os.unlink(tmp)
            else:
                px = QPixmap(source)
            if not px.isNull():
                self.cover.set_cover(px)
        except Exception as e:
            print(f"[Overlay] cover load error: {e}")
            self.cover.set_cover(None)

    # ── Drag to move ───────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        """Double-click toggles between 93% and 38% opacity."""
        self._opacity = 0.38 if self._opacity > 0.5 else 0.93
        self.setWindowOpacity(self._opacity)


# ══════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════

def _launch_overlay(app):
    overlay = MusicOverlay()
    overlay.show()
    app._overlay = overlay  # keep reference alive

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()

    if config:
        # Credentials found – connect directly
        if init_spotify(config["client_id"], config["client_secret"]):
            _launch_overlay(app)
        else:
            # Token may have expired – show setup again
            setup = SetupDialog()
            setup.done.connect(lambda: _launch_overlay(app))
            setup.show()
    else:
        # First launch – show setup dialog
        setup = SetupDialog()
        setup.done.connect(lambda: _launch_overlay(app))
        setup.show()

    sys.exit(app.exec())