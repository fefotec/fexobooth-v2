"""Performance Overlay für Developer Mode

Zeigt CPU- und RAM-Auslastung in der oberen rechten Ecke an.
Nur aktiv wenn developer_mode = True in config.
"""

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.ui.theme import COLORS, FONTS
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.app import PhotoboothApp

logger = get_logger(__name__)


class PerformanceOverlay:
    """Zeigt CPU/RAM Nutzung als Overlay an"""
    
    def __init__(self, app: "PhotoboothApp"):
        self.app = app
        self.enabled = app.config.get("developer_mode", False)
        self._label = None
        self._update_job = None
        
        if self.enabled:
            self._create_overlay()
            self._start_updates()
            logger.info("🛠️ Performance Overlay aktiviert")
    
    def _create_overlay(self):
        """Erstellt das Overlay-Label"""
        # Overlay-Frame in der Top-Bar (ganz rechts, vor Admin-Button)
        self._label = ctk.CTkLabel(
            self.app.top_bar,
            text="CPU: --% | RAM: --MB",
            font=("Consolas", 11),
            text_color="#00ff00",  # Matrix-Grün
            fg_color="#000000",
            corner_radius=4,
            padx=8,
            pady=3
        )
        # Ganz rechts packen (vor dem Admin-Button falls möglich)
        self._label.pack(side="right", padx=5, pady=10)
    
    def _start_updates(self):
        """Startet periodische Updates"""
        self._update_stats()
    
    def _update_stats(self):
        """Aktualisiert die Performance-Statistiken"""
        if not self.enabled or not self._label:
            return
        
        try:
            import psutil
            
            # CPU (über kurzes Intervall, nicht-blockierend)
            cpu_percent = psutil.cpu_percent(interval=None)
            
            # RAM
            memory = psutil.virtual_memory()
            ram_used_mb = memory.used / (1024 * 1024)
            ram_total_mb = memory.total / (1024 * 1024)
            ram_percent = memory.percent
            
            # Prozess-spezifisch
            process = psutil.Process()
            process_ram_mb = process.memory_info().rss / (1024 * 1024)
            
            # Farbe je nach Auslastung
            if cpu_percent > 80 or ram_percent > 85:
                color = "#ff4444"  # Rot - kritisch
            elif cpu_percent > 60 or ram_percent > 70:
                color = "#ffaa00"  # Orange - Warnung
            else:
                color = "#00ff00"  # Grün - OK
            
            text = f"CPU: {cpu_percent:4.1f}% | RAM: {process_ram_mb:4.0f}MB ({ram_percent:.0f}%)"
            
            self._label.configure(text=text, text_color=color)
            
        except ImportError:
            # psutil nicht installiert
            self._label.configure(text="psutil fehlt!", text_color="#ff4444")
            logger.warning("psutil nicht installiert - Performance Overlay deaktiviert")
            self.enabled = False
            return
        except Exception as e:
            logger.debug(f"Performance Update Fehler: {e}")
        
        # Nächstes Update in 2 Sekunden
        if self.enabled:
            self._update_job = self.app.root.after(2000, self._update_stats)
    
    def destroy(self):
        """Räumt auf"""
        if self._update_job:
            try:
                self.app.root.after_cancel(self._update_job)
            except:
                pass
        if self._label:
            try:
                self._label.destroy()
            except:
                pass
