"""Video-Screen für Start/End Videos

Spielt ein Video ab und wechselt dann zum nächsten Screen.
"""

import customtkinter as ctk
import os
import sys
from typing import TYPE_CHECKING, Optional, Callable

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)

# VLC-Import mit Fallback (auch für fehlende DLLs)
VLC_AVAILABLE = False
vlc = None

def _check_vlc():
    """Prüft ob VLC verfügbar ist"""
    global VLC_AVAILABLE, vlc
    try:
        import vlc as _vlc
        vlc = _vlc
        # Test ob VLC wirklich funktioniert (DLLs vorhanden)
        _test_instance = vlc.Instance()
        if _test_instance:
            VLC_AVAILABLE = True
            _test_instance.release()
            logger.info("VLC verfügbar")
    except Exception as e:
        logger.info(f"VLC nicht verfügbar - Videos werden übersprungen: {e}")
        VLC_AVAILABLE = False

# Lazy init - wird beim ersten Video-Abspielen geprüft


class VideoScreen(ctk.CTkFrame):
    """Spielt ein Video ab und wechselt dann zum Ziel-Screen"""
    
    def __init__(self, parent, app: "PhotoboothApp"):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.app = app
        
        self.video_path: Optional[str] = None
        self.next_screen: str = "start"
        self.on_complete: Optional[Callable] = None
        
        self.vlc_instance = None
        self.player = None
        self.is_playing = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        # Video-Container (schwarz)
        self.video_frame = ctk.CTkFrame(
            self,
            fg_color="#000000",
            corner_radius=0
        )
        self.video_frame.pack(fill="both", expand=True)
        
        # Skip-Button (unten rechts, dezent)
        self.skip_btn = ctk.CTkButton(
            self,
            text="Überspringen →",
            font=FONTS["small"],
            width=120,
            height=35,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_light"],
            corner_radius=8,
            command=self._skip_video
        )
        self.skip_btn.place(relx=0.95, rely=0.95, anchor="se")
    
    def play(self, video_path: str, next_screen: str = "start", on_complete: Optional[Callable] = None):
        """Spielt ein Video ab
        
        Args:
            video_path: Pfad zum Video
            next_screen: Screen-Name nach Video-Ende
            on_complete: Callback nach Video-Ende (optional)
        """
        self.video_path = video_path
        self.next_screen = next_screen
        self.on_complete = on_complete
        
        # VLC lazy init
        global VLC_AVAILABLE
        if vlc is None:
            _check_vlc()
        
        if not VLC_AVAILABLE:
            logger.info("VLC nicht verfügbar, überspringe Video")
            self._on_video_end()
            return
        
        if not video_path or not os.path.exists(video_path):
            logger.info(f"Video nicht gefunden: {video_path}")
            self._on_video_end()
            return
        
        try:
            # VLC Instance erstellen
            if sys.platform == "win32":
                self.vlc_instance = vlc.Instance("--no-xlib")
            else:
                self.vlc_instance = vlc.Instance()
            
            self.player = self.vlc_instance.media_player_new()
            media = self.vlc_instance.media_new(video_path)
            self.player.set_media(media)
            
            # Video in unser Frame einbetten
            if sys.platform == "win32":
                self.player.set_hwnd(self.video_frame.winfo_id())
            else:
                self.player.set_xwindow(self.video_frame.winfo_id())
            
            # Event für Video-Ende
            events = self.player.event_manager()
            events.event_attach(vlc.EventType.MediaPlayerEndReached, self._vlc_on_end)
            
            # Video starten
            self.player.play()
            self.is_playing = True
            logger.info(f"Video gestartet: {video_path}")
            
            # Backup-Timer falls Event nicht feuert
            self._check_video_status()
            
        except Exception as e:
            logger.error(f"Video-Fehler: {e}")
            self._on_video_end()
    
    def _vlc_on_end(self, event):
        """VLC Event: Video zu Ende"""
        logger.debug("VLC Event: Video Ende")
        # In main thread ausführen
        self.after(100, self._on_video_end)
    
    def _check_video_status(self):
        """Prüft ob Video noch läuft"""
        if not self.is_playing:
            return
        
        if self.player:
            state = self.player.get_state()
            if state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                self._on_video_end()
                return
        
        # Weiter prüfen
        self.after(500, self._check_video_status)
    
    def _skip_video(self):
        """Video überspringen"""
        logger.info("Video übersprungen")
        self._on_video_end()
    
    def _on_video_end(self):
        """Video ist fertig"""
        if not self.is_playing:
            return
        
        self.is_playing = False
        
        # VLC stoppen und aufräumen
        if self.player:
            try:
                self.player.stop()
            except:
                pass
        
        # Wenn Callback vorhanden: Callback aufrufen, NICHT Screen wechseln
        # (Callback übernimmt die Kontrolle, z.B. bei Zwischen-Videos)
        if self.on_complete:
            logger.info(f"Video fertig, rufe Callback auf")
            self.on_complete()
            return
        
        # Ohne Callback: Zum nächsten Screen wechseln
        logger.info(f"Video fertig, wechsle zu: {self.next_screen}")
        self.app.show_screen(self.next_screen)
    
    def on_hide(self):
        """Screen wird verlassen"""
        self.is_playing = False
        if self.player:
            try:
                self.player.stop()
            except:
                pass
    
    def on_show(self):
        """Screen wird angezeigt"""
        pass  # Video wird über play() gestartet
