"""Canon DSLR Camera Manager (EDSDK)

High-level Kamera-Manager für Canon DSLRs via EDSDK.
Implementiert das CameraManager Interface für fexobooth.
"""

import cv2
import numpy as np
import time
import io
import threading
from queue import Queue, Empty
from typing import Optional, List, Dict, Any
from PIL import Image
from ctypes import c_void_p

from .base import CameraManager
from src.utils.logging import get_logger

logger = get_logger(__name__)

# EDSDK Import (nur auf Windows)
try:
    from . import edsdk
    EDSDK_AVAILABLE = True
except Exception as e:
    EDSDK_AVAILABLE = False
    logger.warning(f"EDSDK nicht verfügbar: {e}")


class CanonCameraManager(CameraManager):
    """Verwaltet Canon DSLR Kameras via EDSDK
    
    Unterstützt:
    - Live View Streaming
    - Foto-Capture in voller Auflösung
    - Kamera-Einstellungen (TODO)
    """
    
    def __init__(self):
        self._is_initialized = False
        self._initializing = False  # True während initialize() läuft (Deadlock-Schutz)
        self._camera_ref: Optional[c_void_p] = None
        self._camera_info: Optional[Dict] = None
        self._live_view_active = False

        # Frame Cache
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_cache_duration: float = 0.033  # ~30fps

        # Capture State & Mode
        self._photo_queue: Queue = Queue()
        self._capture_in_progress: bool = False
        self._captured_image: Optional[Image.Image] = None
        self._use_host_download: bool = False  # True = kein SD, Bild via Event-Handler empfangen
        self._event_handler_registered: bool = False  # True = Object-Event-Handler registriert
        self._camera_shutdown: bool = False  # True wenn 0x301 Shutdown-Event empfangen

        # ------------------------------------------------------------------
        # 2.4.46 — Schutz gegen die zwei Box-Fehlerbilder vom 21.08.2026
        # ------------------------------------------------------------------
        # (A) "Endlosschleife": Reißt die USB-Verbindung ab, schlug jeder
        #     start_live_view() 3x mit je 0,5s Pause fehl — also 1,5s Blockade
        #     pro Vorschaubild, ~40x pro Minute, 29 Minuten am Stück. Windows
        #     meldete die App irgendwann als "reagiert nicht" (AppHang).
        #     Gegenmittel: Nach einer verlorenen Runde ist Live-View für ein
        #     paar Sekunden gesperrt und kehrt sofort zurück, statt zu warten.
        self._lv_fehler_serie: int = 0        # verlorene start_live_view-Runden am Stück
        self._lv_gesperrt_bis: float = 0.0    # bis dahin gar nicht erst versuchen
        self._lv_sperre_sekunden: float = 5.0

        # (B) "Immer dasselbe Bild in der Collage": get_frame() gab bei toter
        #     Kamera stillschweigend das letzte gelungene Vorschaubild zurück.
        #     Die Notlösung hielt das für ein frisches Foto — und legte damit
        #     3x exakt dasselbe Standbild in die Collage.
        #     Gegenmittel: Fingerabdruck jedes ausgelieferten Notbildes; ein
        #     Wiederholungstäter wird abgelehnt.
        self._letzter_fallback_fp: Optional[str] = None

        # (C) Wiederherstellung: Bisher gab es sie nur für das Shutdown-Ereignis
        #     0x301. Die real auftretenden Codes (DEVICE_BUSY, COMM_DISCONNECTED)
        #     lösten sie nie aus — die App fand nie zurück.
        self._reconnect_laeuft: bool = False
        self._letzter_reconnect: float = 0.0
        self._reconnect_abstand: float = 10.0  # frühestens alle 10s neu aufbauen

        # (D) Zähler für die Dev-Mode-Auswertung. Ohne die war im Box-Log nicht
        #     zu sehen, dass 133 von 133 "Fotos" in Wahrheit Notlösungen waren.
        self._events_gesehen: int = 0      # wie oft der Kamera-Rückkanal gefeuert hat
        self._pump_laeufe: int = 0         # wie oft Events abgeholt wurden
        self._fotos_echt: int = 0          # echte DSLR-Aufnahmen
        self._fotos_notloesung: int = 0    # Vorschaubild statt Foto
        self._fotos_leer: int = 0          # gar kein Bild

        # (E) 2.4.54: Wurde schon einmal geprüft, ob die Karte als Notnagel
        #     einspringen muss? Verhindert, dass bei jedem Foto erneut
        #     umgestellt wird.
        self._karte_als_notnagel_geprueft: bool = False
    
    @staticmethod
    def is_available() -> bool:
        """Prüft ob EDSDK verfügbar ist"""
        return EDSDK_AVAILABLE
    
    @staticmethod
    def list_cameras() -> List[Dict[str, Any]]:
        """Listet verfügbare Canon Kameras"""
        if not EDSDK_AVAILABLE:
            return []
        
        return edsdk.get_camera_list()
    
    def initialize(self, camera_index: int = 0, width: int = 0, height: int = 0) -> bool:
        """Initialisiert die Kamera
        
        Args:
            camera_index: Index der Kamera (0 = erste Canon Kamera)
            width/height: Werden bei Canon ignoriert (Live View hat feste Auflösung)
        """
        logger.info(f"=== Canon Kamera initialisieren (index={camera_index}) ===")

        # Deadlock-Schutz: Flag setzen BEVOR EDSDK-Aufrufe beginnen
        # Verhindert dass _check_camera_status() im UI-Thread gleichzeitig EDSDK aufruft
        self._initializing = True

        # Wenn bereits initialisiert, erst aufräumen
        if self._is_initialized:
            logger.info("Bereits initialisiert, führe Cleanup durch...")
            self.release()
        
        if not EDSDK_AVAILABLE:
            logger.error("EDSDK nicht verfügbar")
            self._initializing = False
            return False
        
        # SDK initialisieren
        logger.debug("SDK initialisieren...")
        if not edsdk.initialize():
            logger.error("SDK-Initialisierung fehlgeschlagen")
            self._initializing = False
            return False
        
        # Kamera-Liste holen — im Kamera-Faden (2.4.57).
        # Die Kamera-Referenz, die hier entsteht, gehoert dem Faden, der sie
        # erzeugt hat. Wird sie anderswo erzeugt als die Sitzung geoeffnet
        # wird, haengen spaetere Aufrufe.
        logger.debug("Kamera-Liste abrufen...")
        cameras = edsdk.im_kamera_faden(edsdk.get_camera_list)
        logger.info(f"Gefundene Kameras: {len(cameras)}")
        
        if not cameras:
            logger.error("Keine Canon Kamera gefunden")
            self._initializing = False
            return False
        
        for i, cam in enumerate(cameras):
            logger.debug(f"  [{i}] {cam.get('name', 'Unknown')} @ {cam.get('port', '?')}")
        
        if camera_index >= len(cameras):
            logger.error(f"Kamera-Index {camera_index} ungültig (nur {len(cameras)} Kameras)")
            self._initializing = False
            return False
        
        # Kamera auswählen
        self._camera_info = cameras[camera_index]
        self._camera_ref = self._camera_info["ref"]
        
        logger.info(f"Verbinde mit: {self._camera_info['name']}")
        
        # Session öffnen (mit Retry-Logik in edsdk.open_session)
        logger.debug("Öffne Kamera-Session...")
        if not edsdk.im_kamera_faden(edsdk.open_session, self._camera_ref):
            logger.error("Session konnte nicht geöffnet werden")
            self._camera_ref = None
            self._camera_info = None
            self._initializing = False
            return False
        
        logger.info("Session erfolgreich geöffnet")
        
        # ------------------------------------------------------------------
        # Speicherung: Kamera-Zwischenspeicher hat Vorrang (2.4.56)
        # ------------------------------------------------------------------
        #
        # WICHTIG ZUR EINORDNUNG: Die Fotos landen in BEIDEN Faellen auf der
        # PC-Festplatte (C:exobooth\BILDER). Der Unterschied ist nur der
        # Transportweg aus der Kamera heraus:
        #
        #   Weg A (Karte):  Kamera legt das Bild auf ihre Karte, die Box holt
        #                   es sofort ab und speichert es auf dem PC.
        #   Weg B (direkt): Die Kamera schickt das Bild ohne Zwischenschritt.
        #
        # Weg B ist eleganter — aber er braucht einen "Rueckkanal", und dessen
        # Einrichtung (`EdsSetObjectEventHandler`) HAENGT auf dieser Hardware
        # dauerhaft. Box-Log vom 24.08.2026:
        #
        #     11:10:30  Rueckkanal-Registrierung nach 4s nicht abgeschlossen
        #     11:10:30  EDSDK Fehler 0x81 (DEVICE_BUSY)      <- Kamera blockiert
        #     11:12:47  Rueckkanal-Registrierung nach 4s ... <- naechster Versuch
        #     11:13:07  Rueckkanal-Registrierung nach 4s ...
        #
        # Jeder Versuch hinterlaesst einen haengenden Aufruf, der die Kamera
        # besetzt haelt. Danach kam weder Live-View noch ein Foto — und mit
        # jedem weiteren Versuch wurde es schlechter.
        #
        # Deshalb: Steckt eine Karte, wird sie als Zwischenspeicher genutzt und
        # der Rueckkanal gar nicht erst angefasst. Das Ergebnis fuer den Kunden
        # ist dasselbe, nur ohne die Blockade.
        self._use_host_download = False
        logger.debug("Konfiguriere Speicherung...")

        karte_da = False
        if edsdk.set_save_to_camera(self._camera_ref):
            volume = edsdk.get_first_volume(self._camera_ref)
            if volume:
                karte_da = True
                edsdk.EDSDK_DLL.EdsRelease(volume)

        if karte_da:
            logger.info(
                "Speicherung: über den Kamera-Zwischenspeicher — die Box holt "
                "jedes Foto sofort ab und legt es auf der PC-Festplatte ab"
            )
        else:
            # Ohne Karte bleibt nur der Direktweg. Der braucht den Rueckkanal,
            # und der kann haengen — deshalb nur hier, wo es keine Alternative
            # gibt, und mit klarer Ansage im Log.
            self._use_host_download = True
            logger.warning(
                "Keine Speicherkarte in der Kamera — nur der Direktweg bleibt. "
                "Dessen Einrichtung kann auf dieser Hardware hängen; eine Karte "
                "in der Kamera ist der zuverlässigere Weg (die Fotos landen "
                "trotzdem auf der PC-Festplatte)."
            )

            if edsdk.set_save_to_host(self._camera_ref):
                logger.info("Kamera liefert Fotos direkt an den Rechner")

            rueckkanal = edsdk.set_object_event_handler(
                self._camera_ref, self._on_object_event
            )
            self._event_handler_registered = rueckkanal is not False
            if rueckkanal is True:
                logger.info("Rückkanal steht")
            elif rueckkanal is None:
                logger.warning("Rückkanal nicht bestätigt — Fotos kommen evtl. nicht an")
            else:
                logger.error("Rückkanal abgelehnt — so kann kein Foto ankommen")

        # Bildqualität auf JPG Large Fine setzen (kein RAW!) - nicht kritisch wenn fehlschlägt
        try:
            if not edsdk.set_image_quality_jpg(self._camera_ref):
                logger.warning("Bildqualität konnte nicht auf JPG gesetzt werden - bitte manuell prüfen!")
        except Exception as e:
            logger.warning(f"set_image_quality_jpg Exception (ignoriert): {e}")

        self._is_initialized = True
        self._initializing = False
        logger.info(f"✅ Canon Kamera initialisiert: {self._camera_info['name']}")

        # Kamera-Einstellungen loggen (für Debugging)
        edsdk.log_camera_settings(self._camera_ref)
        
        return True
    
    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        if self._live_view_active:
            self.stop_live_view()

        if self._camera_ref and self._is_initialized:
            edsdk.close_session(self._camera_ref)
            edsdk.EDSDK_DLL.EdsRelease(self._camera_ref)

        self._camera_ref = None
        self._camera_info = None
        self._is_initialized = False
        self._initializing = False
        self._use_host_download = False
        self._event_handler_registered = False
        self._camera_shutdown = False
        self._last_frame = None

        logger.info("Canon Kamera freigegeben")
    
    def start_live_view(self) -> bool:
        """Startet Live View mit Retry-Logik

        2.4.46: Zwei Änderungen gegen die Endlosschleife vom 21.08.2026.

        1. SPERRE NACH VERLORENER RUNDE. Vorher kostete jeder Aufruf bei toter
           Kamera 1,5 Sekunden (3 Versuche à 0,5s Pause) — und der Vorschau-
           Arbeiter ruft das mehrmals pro Sekunde. Ergebnis auf Box 245: 1.611
           Fehlversuche in 29 Minuten, die App reagierte am Ende nicht mehr.
           Jetzt gilt nach einer verlorenen Runde eine Ruhepause, in der sofort
           False zurückkommt — ohne die Box zu blockieren.

        2. VERBINDUNGSABBRUCH ERKENNEN. Meldet die Kamera DEVICE_BUSY oder
           COMM_DISCONNECTED, ist die Session hinüber; weiterprobieren bringt
           nichts. Dann wird ein Neuaufbau angestoßen statt endlos zu klopfen.
        """
        logger.debug("start_live_view aufgerufen...")

        if not self._is_initialized or not self._camera_ref:
            logger.warning("start_live_view: Kamera nicht initialisiert")
            return False

        if self._live_view_active:
            logger.debug("Live View bereits aktiv")
            return True

        # Ruhepause nach einer verlorenen Runde: sofort zurück, nicht blockieren
        jetzt = time.monotonic()
        if jetzt < self._lv_gesperrt_bis:
            logger.debug(
                f"start_live_view: Ruhepause noch {self._lv_gesperrt_bis - jetzt:.1f}s "
                f"(Serie: {self._lv_fehler_serie} verlorene Runden)"
            )
            return False

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if edsdk.start_live_view(self._camera_ref):
                    self._live_view_active = True
                    # Warten bis Live View bereit ist
                    time.sleep(0.8)
                    if self._lv_fehler_serie:
                        logger.info(
                            f"Live View gestartet (Versuch {attempt + 1}) — "
                            f"Kamera hat sich nach {self._lv_fehler_serie} verlorenen Runden gefangen"
                        )
                    else:
                        logger.info(f"Live View gestartet (Versuch {attempt + 1})")
                    self._lv_fehler_serie = 0
                    self._lv_gesperrt_bis = 0.0
                    return True

                # Fehlgeschlagen — sagt der Fehlercode, dass die Verbindung tot ist?
                fehler = getattr(edsdk, "letzter_fehler", 0)
                if edsdk.ist_verbindung_tot(fehler):
                    name = edsdk.ERROR_NAMES.get(fehler, "UNBEKANNT")
                    logger.error(
                        f"start_live_view: Verbindung zur Kamera ist weg ({name}) — "
                        f"weitere Versuche sind zwecklos, baue neu auf"
                    )
                    break

                logger.warning(f"start_live_view Versuch {attempt + 1} fehlgeschlagen")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"start_live_view Exception (Versuch {attempt + 1}): {e}")
                time.sleep(0.5)

        # Runde verloren
        self._lv_fehler_serie += 1
        self._lv_gesperrt_bis = time.monotonic() + self._lv_sperre_sekunden

        # Nur die erste Runde und danach jede 20. laut melden — sonst läuft das
        # Log wieder mit tausenden identischen Zeilen voll.
        if self._lv_fehler_serie == 1 or self._lv_fehler_serie % 20 == 0:
            logger.error(
                f"Live View konnte nach 3 Versuchen nicht gestartet werden "
                f"(verlorene Runde #{self._lv_fehler_serie}, "
                f"Ruhepause {self._lv_sperre_sekunden:.0f}s)"
            )

        # Ab der zweiten verlorenen Runde: Verbindung neu aufbauen (gedrosselt)
        if self._lv_fehler_serie >= 2:
            self._verbindung_neu_aufbauen("Live View startet nicht mehr")

        return False
    
    def stop_live_view(self):
        """Stoppt Live View"""
        if self._camera_ref and self._live_view_active:
            edsdk.stop_live_view(self._camera_ref)
            self._live_view_active = False
            logger.info("Live View gestoppt")
    
    def get_frame(self, use_cache: bool = True, allow_stale: bool = True) -> Optional[np.ndarray]:
        """Holt ein Frame vom Live View

        Args:
            use_cache: Kurzzeit-Cache (~30fps) nutzen
            allow_stale: Darf im Notfall das zuletzt gelungene Bild zurückkommen?

                2.4.46 — DAS war die Ursache für "immer dasselbe Bild in der
                Collage". Diese Methode gab bei toter Kamera stillschweigend
                `self._last_frame` zurück: ein Vorschaubild, das Minuten alt
                sein konnte. Für die laufende Vorschau auf dem Schirm ist das
                richtig (ein eingefrorenes Bild ist besser als ein schwarzer
                Bildschirm) — für eine Foto-Aufnahme ist es fatal, weil drei
                Fotos hintereinander byte-identisch werden.

                Deshalb: Die Vorschau ruft weiter mit allow_stale=True auf,
                die Foto-Notlösung mit allow_stale=False und bekommt dann
                lieber gar nichts als ein altes Bild.

        Returns:
            OpenCV BGR Frame oder None
        """
        if not self._is_initialized:
            logger.debug("get_frame: nicht initialisiert")
            return None

        def _notnagel(grund: str) -> Optional[np.ndarray]:
            """Letztes gelungenes Bild — nur wenn ausdrücklich erlaubt."""
            if not allow_stale:
                logger.debug(f"get_frame: kein frisches Bild ({grund}), Altbild ist gesperrt")
                return None
            if self._last_frame is None:
                return None
            alter = time.time() - self._last_frame_time
            logger.debug(f"get_frame: liefere Altbild ({grund}, {alter:.1f}s alt)")
            return self._last_frame

        # Live View starten falls nicht aktiv
        if not self._live_view_active:
            logger.debug("get_frame: starte Live View...")
            if not self.start_live_view():
                # Nur die erste Runde meldet laut (start_live_view drosselt schon)
                if self._lv_fehler_serie <= 1:
                    logger.warning("get_frame: Live View konnte nicht gestartet werden")
                return _notnagel("Live View startet nicht")

        current_time = time.time()

        # Cache nutzen
        if use_cache and self._last_frame is not None:
            if current_time - self._last_frame_time < self._frame_cache_duration:
                return self._last_frame.copy()

        # Live View Frame holen (JPEG bytes)
        try:
            jpeg_data = edsdk.get_live_view_image(self._camera_ref)
        except Exception as e:
            # Nicht bei jedem Frame loggen - nur gelegentlich
            if not hasattr(self, '_evf_error_count'):
                self._evf_error_count = 0
            self._evf_error_count += 1
            if self._evf_error_count <= 3 or self._evf_error_count % 100 == 0:
                logger.debug(f"get_live_view_image Fehler #{self._evf_error_count}: {e}")
            jpeg_data = None
        
        if jpeg_data is None:
            # Bei vielen Fehlern: Live-View neu starten
            if hasattr(self, '_evf_error_count') and self._evf_error_count > 0 and self._evf_error_count % 30 == 0:
                logger.warning(f"Viele Live-View Fehler ({self._evf_error_count}), versuche Neustart...")
                self._live_view_active = False
                self.start_live_view()
            return _notnagel("Vorschaubild kam nicht an")

        # Erfolg - Fehler-Counter zurücksetzen
        if hasattr(self, '_evf_error_count'):
            self._evf_error_count = 0
        
        try:
            # JPEG zu numpy array
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                self._last_frame = frame
                self._last_frame_time = current_time
                return frame
                
        except Exception as e:
            logger.error(f"Fehler beim Dekodieren des Frames: {e}")

        return _notnagel("Bild ließ sich nicht dekodieren")

    # ------------------------------------------------------------------
    # 2.4.46 — Verbindungs-Neuaufbau und Event-Abholung
    # ------------------------------------------------------------------

    def _verbindung_neu_aufbauen(self, grund: str) -> bool:
        """Baut die Kamera-Verbindung komplett neu auf.

        Bisher gab es eine Wiederherstellung NUR für das Shutdown-Ereignis
        0x301 (`_recover_from_shutdown`). Die auf den Boxen real auftretenden
        Fälle — DEVICE_BUSY und COMM_DISCONNECTED — haben sie nie ausgelöst.
        Deshalb fand die App nie zurück und lief bis zum Abschuss durch Windows
        im Kreis.

        Gedrosselt: höchstens alle `_reconnect_abstand` Sekunden, damit daraus
        nicht die nächste Endlosschleife wird.
        """
        if self._reconnect_laeuft:
            return False

        jetzt = time.monotonic()
        wartezeit = self._reconnect_abstand - (jetzt - self._letzter_reconnect)
        if wartezeit > 0:
            logger.debug(f"Neuaufbau übersprungen (noch {wartezeit:.0f}s Sperre)")
            return False

        self._reconnect_laeuft = True
        self._letzter_reconnect = jetzt
        logger.warning(f"=== KAMERA-VERBINDUNG WIRD NEU AUFGEBAUT (Grund: {grund}) ===")

        try:
            self._live_view_active = False
            self._last_frame = None          # Altbild verwerfen, sonst geistert es weiter
            self._letzter_fallback_fp = None

            erfolg = self._recover_from_shutdown()

            if erfolg:
                self._lv_fehler_serie = 0
                self._lv_gesperrt_bis = 0.0
                logger.warning("=== Neuaufbau erfolgreich — Kamera ist wieder da ===")
            else:
                # Harter Weg: komplette Neuinitialisierung
                logger.warning("Neuaufbau über Session fehlgeschlagen — versuche Vollstart")
                try:
                    self.release()
                except Exception as e:
                    logger.debug(f"release() beim Neuaufbau: {e}")
                erfolg = self.initialize()
                logger.warning(
                    f"=== Vollstart {'erfolgreich' if erfolg else 'FEHLGESCHLAGEN'} ==="
                )

            return erfolg
        except Exception as e:
            logger.error(f"Neuaufbau Exception: {e}")
            return False
        finally:
            self._reconnect_laeuft = False

    def pump_events(self) -> None:
        """Holt wartende Kamera-Ereignisse ab. MUSS regelmäßig laufen!

        2.4.46 — DAS ist der Grund, warum keine Fotos ankamen.

        Das EDSDK stellt Ereignisse ("Bild fertig, hol es ab") über die Windows-
        Nachrichtenschlange zu, und zwar an den Programmteil, der die Kamera
        geöffnet hat — bei uns der Haupt-Programmfaden mit der Bedienoberfläche.
        Abgeholt werden sie nur, wenn `EdsGetEvent()` **aus genau diesem Faden**
        aufgerufen wird.

        Bisher passierte das nur in der Warteschleife der Foto-Aufnahme — und
        die läuft seit dem Umbau auf Hintergrund-Aufnahme in einem NEBEN-Faden.
        Die Ereignisse blieben deshalb ungelesen im Haupt-Faden liegen. Beweis
        aus den Box-Logs vom 21.08.2026: über 200 Auslösungen, aber KEIN
        einziges `>>> OBJECT EVENT` — der Rückkanal hat kein einziges Mal
        gefeuert.

        Wird von app.py im Takt der Bedienoberfläche aufgerufen (nur bei Canon).
        """
        if not self._is_initialized or not EDSDK_AVAILABLE:
            return
        if self._reconnect_laeuft:
            return

        try:
            edsdk.get_event()
            self._pump_laeufe += 1
        except Exception as e:
            logger.debug(f"pump_events Fehler: {e}")

    def _log_kamera_zustand_kurz(self) -> None:
        """Einzeiler mit dem Kamera-Zustand direkt vor dem Auslösen.

        2.4.46 — Bewusst EINE Zeile (nicht der große Block aus
        log_camera_settings), damit das Log bei 100 Fotos pro Abend lesbar
        bleibt. Enthält genau die Werte, die ein Nicht-Auslösen erklären:
        Akku leer, Wahlrad auf Video, Autofokus findet nichts.
        """
        if not self._camera_ref:
            return

        try:
            hole = lambda pid: edsdk.get_property_uint(self._camera_ref, pid)
            akku = hole(edsdk.kEdsPropID_BatteryLevel)
            aemode = hole(edsdk.kEdsPropID_AEMode)
            afmode = hole(edsdk.kEdsPropID_AFMode)
            tv = hole(edsdk.kEdsPropID_Tv)
            av = hole(edsdk.kEdsPropID_Av)
            iso = hole(edsdk.kEdsPropID_ISOSpeed)
            wb = hole(edsdk.kEdsPropID_WhiteBalance)

            akku_text = {
                0: "LEER", 1: "sehr schwach", 2: "schwach",
                4: "ok", 0x7fffffff: "Netzstrom",
            }.get(akku, str(akku))
            af_text = {
                0: "One-Shot AF", 1: "AI Servo", 2: "AI Focus", 3: "manuell (MF)",
            }.get(afmode, str(afmode))
            ae_text = {
                0: "P", 1: "Tv", 2: "Av", 3: "M", 8: "Vollautomatik",
                9: "Auto ohne Blitz", 0x17: "Szeneautomatik",
            }.get(aemode, f"0x{aemode:x}" if aemode is not None else "?")
            tv_text = ("legt die Kamera beim Auslösen fest" if tv == 0
                       else edsdk.TV_NAMEN.get(tv, f"0x{tv:x}" if tv is not None else "?"))
            av_text = ("legt die Kamera beim Auslösen fest" if av == 0
                       else edsdk.AV_NAMEN.get(av, f"0x{av:x}" if av is not None else "?"))
            iso_text = edsdk.ISO_NAMEN.get(iso, f"0x{iso:x}" if iso is not None else "?")
            wb_text = edsdk.WB_NAMEN.get(wb, str(wb))

            logger.info(
                f"[3/5] Kamera-Zustand: Modus={ae_text}, Zeit={tv_text}, Blende={av_text}, "
                f"ISO={iso_text}, Weißabgleich={wb_text}, Fokus={af_text}, Akku={akku_text}"
            )

            if akku in (0, 1):
                logger.warning("[3/5] ACHTUNG: Kamera-Akku fast leer — sie löst bald nicht mehr aus!")

            # 2.4.46: Die drei Einstellungen, die in einer Fotobox regelmäßig
            # für schlechte oder fehlende Fotos sorgen — mit Klartext-Hinweis,
            # damit man im Box-Log nicht raten muss.
            # 0x00 heisst "kein Wert" — nicht "sehr lange Zeit". In den
            # Vollautomatik-Modi legt die Kamera Zeit und Blende erst beim
            # Ausloesen fest und meldet vorher 0. Ohne diese Ausnahme warnte
            # das Log bei JEDEM Foto vor Verwacklung (Box-Log 21.08.2026).
            if tv is not None and 0 < tv <= 0x63:  # 1/40s und länger
                logger.warning(
                    f"[3/5] ACHTUNG: Belichtungszeit {tv_text} ist für eine Fotobox zu lang. "
                    f"Gäste bewegen sich — die Fotos werden verwackelt. "
                    f"Die Box arbeitet ohne Blitz, deshalb wählt die Automatik bei dunkler "
                    f"Location lange Zeiten. Abhilfe wäre Modus Tv mit fester Zeit (1/100s) "
                    f"und ISO-Automatik: Zeit bleibt kurz, die Kamera regelt trotzdem nach."
                )
            if afmode in (0, 1, 2):
                # Der Autofokus MUSS in der Mietbox aktiv bleiben: Gäste stehen
                # unterschiedlich weit weg und bewegen sich. Ein fester Fokus
                # wäre hier keine Lösung, sondern ein neues Problem.
                logger.debug(f"[3/5] Autofokus aktiv ({af_text}) — für die Mietbox richtig so.")
            if wb == 0:
                logger.info(
                    "[3/5] Hinweis: Weißabgleich steht auf Automatik. Der rechnet pro Foto neu — "
                    "in derselben Collage können die Bilder unterschiedlich farbig werden."
                )
            if aemode in (8, 9, 0x17):
                # "Auto ohne Blitz" (9) ist die BEWUSSTE Wahl für die Mietflotte:
                # ohne Blitz muss die Kamera bei dunkler werdender Location selbst
                # nachregeln, und der Kunde darf nichts einstellen müssen.
                # Hier steht deshalb nur, was das für die Bildwirkung bedeutet —
                # keine Empfehlung, das Wahlrad zu verstellen.
                logger.info(
                    f"[3/5] Modus {ae_text}: Die Kamera regelt Zeit, ISO und Weißabgleich "
                    f"selbst nach (so gewollt, weil die Box ohne Blitz arbeitet). "
                    f"Nebenwirkung: Fotos einer Collage können sich in Helligkeit und "
                    f"Farbe unterscheiden."
                )
        except Exception as e:
            logger.debug(f"Kamera-Zustand nicht auslesbar: {e}")

    @staticmethod
    def _bild_fingerabdruck(frame: np.ndarray) -> str:
        """Kurzer Fingerabdruck eines Bildes — erkennt Doppelbilder sicher.

        Nur damit im Log sofort sichtbar ist, wenn zweimal dasselbe Bild
        ausgeliefert wird. Bewusst billig gerechnet (die Boxen sind schwach):
        Prüfsumme über die rohen Bilddaten.
        """
        try:
            import hashlib
            return hashlib.md5(frame.tobytes()).hexdigest()[:12]
        except Exception:
            return "?"


    def _on_object_event(self, event_type: int, obj_ref: c_void_p) -> int:
        """Callback für EDSDK Object Events (Host-Download Modus)

        Wird aufgerufen wenn die Kamera ein Bild bereit hat zum Download.
        Das Bild wird in den Speicher geladen und in die Photo-Queue gelegt.

        Canon EOS 2000D sendet 0x00000208 statt 0x00000108 (DirItemRequestTransfer)
        bei Host-Download. Daher werden mehrere Event-Typen als Download-Trigger behandelt.
        """
        event_names = {
            0x00000100: "DirItemCreated",
            0x00000101: "DirItemRemoved",
            0x00000102: "DirItemInfoChanged",
            0x00000108: "DirItemRequestTransfer",
            0x00000208: "DirItemRequestTransfer_Alt",
            0x00000301: "StateEvent_Shutdown",
            0x00000302: "StateEvent_JobStatusChanged",
        }
        event_name = event_names.get(event_type, f"0x{event_type:08x}")

        # 2.4.46: Jedes Ereignis zählen. In den Box-Logs vom 21.08.2026 stand
        # dieser Zähler faktisch auf 0 — kein einziges Ereignis kam an. Genau
        # daran erkennt man beim nächsten Test sofort, ob der Rückkanal lebt.
        self._events_gesehen += 1

        # Nur relevante Events loggen (nicht die vielen DirItemRemoved/InfoChanged)
        if event_type not in (0x00000101, 0x00000102):
            logger.info(
                f">>> OBJECT EVENT: {event_name} (0x{event_type:08x}) "
                f"[Ereignis Nr. {self._events_gesehen}]"
            )

        # Download-Trigger: 0x00000108 (Standard) ODER 0x00000208 (Canon EOS 2000D)
        if event_type in (0x00000108, 0x00000208):
            logger.info(f">>> Transfer-Event erkannt: {event_name} - starte Download...")
            try:
                image_data = edsdk.download_image_to_memory(obj_ref)
                if image_data:
                    self._photo_queue.put(image_data)
                    logger.info(f">>> Bild empfangen: {len(image_data)} bytes ({len(image_data)/1024/1024:.1f} MB)")
                else:
                    logger.error(">>> Download fehlgeschlagen (keine Daten)")
            except Exception as e:
                logger.error(f">>> Download Exception: {e}")

            # Objekt freigeben
            try:
                if edsdk.EDSDK_DLL:
                    edsdk.EDSDK_DLL.EdsRelease(obj_ref)
            except Exception:
                pass

        # DirItemCreated: Ebenfalls Download versuchen (Fallback für andere Kamera-Modelle)
        elif event_type == 0x00000100:
            logger.info(f">>> DirItemCreated - versuche Download...")
            try:
                image_data = edsdk.download_image_to_memory(obj_ref)
                if image_data:
                    self._photo_queue.put(image_data)
                    logger.info(f">>> Bild via DirItemCreated: {len(image_data)} bytes ({len(image_data)/1024/1024:.1f} MB)")
            except Exception as e:
                # DirItemCreated ist nicht immer ein Bild - Fehler ignorieren
                logger.debug(f">>> DirItemCreated Download nicht möglich: {e}")

            try:
                if edsdk.EDSDK_DLL:
                    edsdk.EDSDK_DLL.EdsRelease(obj_ref)
            except Exception:
                pass

        # Kamera-Shutdown erkennen (0x301): Kamera braucht Re-Initialisierung
        elif event_type == 0x00000301:
            logger.error(">>> KAMERA SHUTDOWN erkannt (0x301)! Markiere für Re-Initialisierung.")
            self._camera_shutdown = True

        return 0  # EDS_ERR_OK

    def _recover_from_shutdown(self) -> bool:
        """Versucht die Kamera nach einem 0x301 Shutdown wiederherzustellen.

        Schließt die aktuelle Session und öffnet sie neu.
        Returns True wenn Recovery erfolgreich.
        """
        logger.warning("=== KAMERA RECOVERY nach Shutdown ===")
        self._camera_shutdown = False

        if not self._camera_ref:
            logger.error("Recovery: Kein Kamera-Ref vorhanden")
            return False

        # Session schließen und neu öffnen
        try:
            edsdk.close_session(self._camera_ref)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Recovery: close_session Fehler (ignoriert): {e}")

        if not edsdk.open_session(self._camera_ref):
            logger.error("Recovery: open_session fehlgeschlagen!")
            self._is_initialized = False
            return False

        logger.info("Recovery: Session neu geöffnet")

        # Host-Download neu konfigurieren
        if self._use_host_download:
            edsdk.set_save_to_host(self._camera_ref)
            if edsdk.set_object_event_handler(self._camera_ref, self._on_object_event):
                self._event_handler_registered = True
                logger.info("Recovery: Event-Handler neu registriert")
            else:
                logger.error("Recovery: Event-Handler Registrierung fehlgeschlagen!")
                self._event_handler_registered = False
        else:
            edsdk.set_save_to_camera(self._camera_ref)

        logger.info("=== KAMERA RECOVERY erfolgreich ===")
        return True

    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Nimmt ein Foto in voller DSLR-Auflösung auf

        Zwei Modi je nach SD-Karten-Verfügbarkeit:
        - MIT SD-Karte: Directory-Polling (Bild auf SD -> Download)
        - OHNE SD-Karte: Host-Download (Bild direkt via USB zum Tablet)

        Args:
            timeout: Maximale Wartezeit in Sekunden

        Returns:
            PIL Image in voller DSLR-Auflösung oder None bei Fehler
        """
        mode_text = "Host-Download" if self._use_host_download else "Directory-Polling"
        logger.info("=" * 60)
        logger.info(f"=== CAPTURE_PHOTO ({mode_text}) ===")
        logger.info("=" * 60)

        if not self._is_initialized or not self._camera_ref:
            logger.error("capture_photo: Kamera nicht initialisiert!")
            return None

        # Recovery nach Kamera-Shutdown (0x301)
        if self._camera_shutdown:
            logger.warning("capture_photo: Kamera war im Shutdown - versuche Recovery...")
            if not self._recover_from_shutdown():
                logger.error("capture_photo: Recovery fehlgeschlagen!")
                return None

        live_view_was_active = self._live_view_active

        try:
            # SCHRITT 1: Live-View BLEIBT AN.
            #
            # 2.4.52 — Bisher wurde er hier abgeschaltet und nach der Aufnahme
            # wieder gestartet. Das kostete gemessen 1,5 s pro Foto
            # (0,7 s Abschalten + 0,8 s Neustart) und war der zweite Punkt, an
            # dem die Box von Canons eigenem Beispiel abwich — dort wird der
            # Ausloeser einfach gesendet, ohne den Live-View anzufassen.
            #
            # Christian am 24.08.2026: "dslr-booth laeuft ja auch auf der
            # gleichen hardware und das problemlos fluessig mit dslr". Genau
            # dieses Abschalten und Wiederanwerfen ist der sichtbare
            # Unterschied: Waehrend der Live-View aus ist, steht auf dem Schirm
            # ein eingefrorenes Bild, das der Gast fuer sein Foto haelt.
            #
            # Zusaetzlich bleibt so das Vorschaubild fuer die Notloesung
            # verfuegbar, ohne dass der Live-View erst wieder hochlaufen muss.
            if self._live_view_active:
                logger.info("[1/5] Live-View bleibt an (wie in Canons Referenz)")
            else:
                logger.info("[1/5] Live-View war nicht aktiv")

            # SCHRITT 2: Queue leeren (Host-Download)
            if self._use_host_download:
                if not self._event_handler_registered:
                    logger.error("[2/5] ✗ Event-Handler nicht registriert! Fallback auf LiveView.")
                    return self._fallback_to_live_view(live_view_was_active)
                logger.info("[2/5] Event-Handler aktiv, leere Photo-Queue...")
                while not self._photo_queue.empty():
                    try:
                        self._photo_queue.get_nowait()
                    except Empty:
                        break
            else:
                logger.info("[2/5] Directory-Polling Modus (SD-Karte)")

            # SCHRITT 3: Foto auslösen
            # 2.4.46: Kurz-Diagnose direkt vor dem Auslösen. Wenn wieder kein
            # Bild kommt, steht damit im Log, in welchem Zustand die Kamera war
            # — Akku, Wahlrad, Fokus-Art. Alle drei können ein Auslösen
            # verhindern, ohne dass die Software etwas falsch macht.
            self._log_kamera_zustand_kurz()

            # 2.4.53: Vor JEDER Aufnahme melden, dass am Rechner Platz ist.
            # Ohne diese Meldung bewegt die Kamera im Direktbetrieb zwar den
            # Spiegel, legt das Bild aber nirgends ab — genau das Bild, das
            # Christian am 24.08.2026 beschrieb ("die kamera hat doch fotos
            # gemacht", aber nichts kam an). Die Meldung ist flüchtig und muss
            # deshalb wiederholt werden, nicht nur einmal beim Verbinden.
            if self._use_host_download:
                if not edsdk.melde_freien_speicher(self._camera_ref):
                    logger.warning(
                        "[3/5] Speicherplatz-Meldung an die Kamera fehlgeschlagen — "
                        "sie könnte die Aufnahme verweigern"
                    )

            logger.info("[3/5] Löse Kamera aus...")
            if not edsdk.take_picture(self._camera_ref, self._live_view_active):
                fehler = getattr(edsdk, "letzter_fehler", 0)
                name = edsdk.ERROR_NAMES.get(fehler, "UNBEKANNT")
                logger.error(f"[3/5] ✗ Auslösen fehlgeschlagen! Kamera meldet: {name} ({hex(fehler)})")

                # 2.4.46: Klartext statt Rätselraten. Die häufigsten Fälle mit
                # konkreter Handlungsanweisung fürs Box-Protokoll.
                if fehler == 0x00008D01:
                    logger.error(
                        "   >>> Die Kamera konnte nicht scharfstellen und hat deshalb nicht "
                        "ausgelöst (AF_NG). In der Mietbox ist der Autofokus gewollt, also "
                        "liegt es am Motiv: zu dunkel, zu kontrastarm oder zu nah. "
                        "Prüfen: Box-Beleuchtung an? AF-Hilfslicht der Kamera aktiv?"
                    )
                elif fehler == 0x00000081:
                    logger.error(
                        "   >>> Die Kamera ist belegt (DEVICE_BUSY). Meist hängt die "
                        "vorherige Session oder das USB-Kabel wackelt."
                    )
                elif edsdk.ist_verbindung_tot(fehler):
                    logger.error("   >>> Verbindung zur Kamera ist weg — baue neu auf.")

                if edsdk.ist_verbindung_tot(fehler):
                    self._verbindung_neu_aufbauen(f"Auslösen scheiterte mit {name}")

                return self._fallback_to_live_view(live_view_was_active)

            logger.info("[3/5] ✓ Kamera ausgelöst!")

            # SCHRITT 4: Auf Bild warten (je nach Modus)
            image_data = None

            if self._use_host_download:
                # HOST-MODUS: Bild kommt über Event-Handler in _photo_queue
                #
                # 2.4.46: Zusätzlich werden hier Windows-Nachrichten abgearbeitet.
                # Diese Schleife läuft seit dem Umbau auf Hintergrund-Aufnahme in
                # einem Neben-Faden; `EdsGetEvent()` allein reicht dort nicht, weil
                # das EDSDK seine Ereignisse über die Nachrichtenschlange zustellt.
                # Die eigentliche Abholung macht app.py im Haupt-Faden
                # (siehe pump_events) — das hier ist der Gürtel zum Hosenträger.
                events_vorher = self._events_gesehen

                # 2.4.46 — WARTEZEIT AN DIE WIRKLICHKEIT ANPASSEN.
                #
                # Christian am 21.08.2026: "das ist alles viel zu träge und
                # dauert ewig". Gemessen im Box-Log: 12,7 Sekunden pro Foto.
                # Davon waren 10 Sekunden reines Warten auf ein Bild, das gar
                # nicht kommen konnte — der Rückkanal der Kamera war nicht
                # eingerichtet.
                #
                # Zwei Fälle:
                #  - Rückkanal nachweislich nicht da  -> 1,5 s (nur pro forma)
                #  - Rückkanal da, aber noch nie ein Bild gebracht -> 4 s
                # Sobald einmal ein Bild angekommen ist, gilt wieder die volle
                # Wartezeit: Dann ist der Weg belegt und ein langsamer Download
                # darf nicht abgeschnitten werden.
                if not self._event_handler_registered:
                    timeout = min(timeout, 1.5)
                    logger.warning(
                        f"[4/5] Rückkanal der Kamera ist nicht eingerichtet — warte nur "
                        f"{timeout}s statt 10s. Ein echtes DSLR-Foto ist so nicht möglich; "
                        f"eine SD-Karte in der Kamera würde das lösen."
                    )
                elif self._events_gesehen == 0:
                    timeout = min(timeout, 4.0)
                    logger.info(
                        f"[4/5] Bisher kam noch nie ein Kamera-Ereignis an — warte "
                        f"verkürzt {timeout}s statt 10s, damit die Box nicht stockt."
                    )

                logger.info(f"[4/5] Warte auf Host-Download (max {timeout}s)...")
                start_time = time.time()
                while time.time() - start_time < timeout:
                    # Events pollen (WICHTIG - ohne das kommen keine Events auf Windows!)
                    edsdk.get_event()
                    edsdk.pump_windows_messages()
                    try:
                        image_data = self._photo_queue.get(timeout=0.1)
                        if image_data:
                            logger.info(f"[4/5] ✓ Bild via Host-Download: {len(image_data)} bytes")
                            break
                        else:
                            logger.warning("[4/5] None aus Queue - Download fehlgeschlagen")
                            image_data = None
                    except Empty:
                        continue

                if image_data is None:
                    # 2.4.54 — SELBSTHEILUNG: Kam auf dem Direktweg noch NIE ein
                    # Ereignis an, funktioniert er auf dieser Box nicht. Dann
                    # einmalig auf die Karte umstellen, statt bei jedem Foto
                    # erneut ins Leere zu laufen. Der Direktweg bleibt die
                    # erste Wahl — aber eine Box, die gar keine Fotos liefert,
                    # ist schlimmer als eine, die den langsameren Weg nimmt.
                    if self._events_gesehen == 0 and not self._karte_als_notnagel_geprueft:
                        self._karte_als_notnagel_geprueft = True
                        volume = edsdk.get_first_volume(self._camera_ref)
                        if volume:
                            edsdk.EDSDK_DLL.EdsRelease(volume)
                            logger.error(
                                "Auf dem Direktweg kam noch nie ein Ereignis an — "
                                "stelle dauerhaft auf die Speicherkarte um. "
                                "Das ist der langsamere Weg, liefert aber Fotos."
                            )
                            if edsdk.set_save_to_camera(self._camera_ref):
                                self._use_host_download = False
                        else:
                            logger.error(
                                "Direktweg liefert nichts und es steckt keine Karte "
                                "in der Kamera. So kann kein Foto entstehen — "
                                "USB-Verbindung und Kamera-Einstellungen prüfen."
                            )

                    # Diagnose fürs nächste Box-Log: Hat der Rückkanal überhaupt
                    # gefeuert? "0 Ereignisse" heißt: Kamera hat nie ausgelöst
                    # bzw. das Ereignis kam nie an. "Ereignisse, aber kein Bild"
                    # heißt: ausgelöst, aber der Download scheiterte.
                    neu = self._events_gesehen - events_vorher
                    logger.error(
                        f"[4/5] DIAGNOSE: In der Wartezeit kamen {neu} Kamera-Ereignisse an "
                        f"(insgesamt {self._events_gesehen} seit Start, "
                        f"{self._pump_laeufe} Abholungen). "
                        + ("KEIN Ereignis -> Kamera hat nicht ausgelöst oder der Rückkanal ist tot."
                           if neu == 0 else
                           "Ereignisse kamen an, aber kein Bild -> Download scheiterte.")
                    )
            else:
                # SD-MODUS: Directory-Polling
                #
                # 2.4.51: Wartezeit von 10 s auf 6 s. Eine EOS 2000D schreibt
                # ein JPEG in ein bis zwei Sekunden auf die Karte. Ist nach
                # sechs Sekunden nichts da, kommt auch nichts mehr — dann hat
                # die Kamera nicht ausgeloest, und weiteres Warten kostet den
                # Gast nur Zeit vor einem eingefrorenen Bild.
                karten_timeout = min(timeout, 6.0)
                logger.info(f"[4/5] Warte auf Bild von der Karte (max {karten_timeout}s)...")
                image_data = edsdk.wait_for_new_image(
                    self._camera_ref, timeout=karten_timeout
                )

            if image_data is None:
                logger.error("[4/5] ✗ Kein Bild empfangen!")
                return self._fallback_to_live_view(live_view_was_active)

            logger.info(f"[4/5] ✓ Bild empfangen: {len(image_data)} bytes")

            # SCHRITT 5: Bild dekodieren + LiveView starten
            logger.info("[5/5] Dekodiere Bild...")
            try:
                image = Image.open(io.BytesIO(image_data))
                image.load()
                logger.info(f"[5/5] ✓ Bild dekodiert: {image.size[0]}x{image.size[1]} ({image.mode})")
            except Exception as e:
                logger.error(f"[5/5] ✗ Fehler beim Dekodieren: {e}")
                return self._fallback_to_live_view(live_view_was_active)

            # 2.4.52: Kein Neustart mehr noetig — der Live-View lief die ganze
            # Zeit durch. Nur fuer den Fall, dass die Kamera ihn bei der
            # Aufnahme von sich aus beendet hat, wird er nachgezogen.
            if live_view_was_active and not self._live_view_active:
                logger.info("Live-View wurde von der Kamera beendet — starte neu")
                self.start_live_view()

            self._fotos_echt += 1
            self._letzter_fallback_fp = None  # echtes Foto -> Doppelbild-Sperre zurücksetzen
            logger.info("=" * 60)
            logger.info(
                f"=== ECHTES DSLR-FOTO: {image.size[0]}x{image.size[1]} === "
                f"Bilanz: {self._fotos_echt} echt / {self._fotos_notloesung} Notlösung / "
                f"{self._fotos_leer} leer"
            )
            logger.info("=" * 60)
            return image

        except Exception as e:
            logger.error(f"capture_photo Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._fallback_to_live_view(live_view_was_active)

    def _fallback_to_live_view(self, restart_live_view: bool) -> Optional[Image.Image]:
        """Notlösung: Vorschaubild statt DSLR-Foto, wenn die Aufnahme scheitert.

        Nach LiveView-Start braucht die Canon EOS 2000D ~1-2s bis gültige Frames
        kommen (OBJECT_NOTREADY in den ersten Versuchen). Daher Retry-Logik.

        2.4.46 — ZWEI ÄNDERUNGEN, die das Doppelbild verhindern:

        1. `allow_stale=False`: Vorher holte die Schleife hier ein Bild über
           get_frame(use_cache=False). Der Parameter schaltete aber nur den
           30fps-Zwischenspeicher ab — bei toter Kamera kam trotzdem das
           letzte gelungene Vorschaubild zurück. Die Schleife war damit sofort
           "erfolgreich" und brach nach dem ERSTEN Versuch ab. Genau so landete
           dreimal dasselbe Standbild in der Collage.

        2. Fingerabdruck-Sperre: Selbst wenn doch ein altes Bild durchrutscht,
           wird ein Bild abgelehnt, das mit dem zuletzt gelieferten Notbild
           identisch ist. Lieber ein leerer Collagen-Platz als dreimal dasselbe
           Gesicht — session.py behandelt "kein Foto" bereits sauber.
        """
        logger.warning("=== NOTLÖSUNG: Vorschaubild statt DSLR-Foto ===")

        # Live-View starten wenn nicht aktiv
        if not self._live_view_active:
            logger.info("Starte Live-View für die Notlösung...")
            self.start_live_view()

        # Mehrere Versuche - Kamera braucht nach LiveView-Start etwas Zeit.
        # allow_stale=False sorgt dafür, dass diese Schleife wirklich wartet,
        # statt sich sofort mit einem Altbild zufriedenzugeben.
        frame = None
        for attempt in range(10):
            frame = self.get_frame(use_cache=False, allow_stale=False)
            if frame is not None:
                if attempt:
                    logger.info(f"Notlösung: frisches Vorschaubild nach {attempt + 1} Versuchen")
                break
            time.sleep(0.3)

        if frame is None:
            self._fotos_leer += 1
            logger.error(
                "Notlösung gescheitert: Die Kamera liefert gar kein Bild mehr. "
                "Dieser Collagen-Platz bleibt leer (besser als ein Doppelbild)."
            )
            self._verbindung_neu_aufbauen("Kamera liefert überhaupt kein Bild mehr")
            return None

        # Doppelbild-Sperre: identisches Bild wie beim letzten Mal?
        fp = self._bild_fingerabdruck(frame)
        if fp != "?" and fp == self._letzter_fallback_fp:
            self._fotos_leer += 1
            logger.error(
                f"Notlösung abgelehnt: Bild ist identisch mit dem letzten "
                f"(Fingerabdruck {fp}) — die Kamera ist eingefroren. "
                f"Platz bleibt leer statt Doppelbild in der Collage."
            )
            self._verbindung_neu_aufbauen("Vorschau eingefroren (identische Bilder)")
            return None

        self._letzter_fallback_fp = fp
        self._fotos_notloesung += 1

        # OpenCV BGR zu PIL RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)

        logger.warning(
            f"Notlösung geliefert: {image.size[0]}x{image.size[1]} (Vorschau-Auflösung, "
            f"kein echtes DSLR-Foto!) Fingerabdruck={fp} | "
            f"Bilanz: {self._fotos_echt} echt / {self._fotos_notloesung} Notlösung / "
            f"{self._fotos_leer} leer"
        )
        return image
    
    def get_high_res_frame(self, width: int = 0, height: int = 0) -> Optional[np.ndarray]:
        """Holt ein hochauflösendes Foto (volle Kamera-Auflösung)
        
        Bei Canon: Nutzt capture_photo() für echte DSLR-Qualität.
        Gibt numpy array zurück für Kompatibilität mit Webcam-Interface.
        """
        image = self.capture_photo()
        if image is None:
            return None
        
        # PIL Image zu numpy array (BGR für OpenCV)
        rgb = np.array(image)
        if len(rgb.shape) == 3 and rgb.shape[2] == 3:
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            return bgr
        return rgb
    
    def take_picture(self) -> bool:
        """Löst die Kamera aus (ohne auf Bild zu warten)
        
        Für manuelles Auslösen. Nutze capture_photo() wenn du das Bild brauchst.
        
        Returns:
            True wenn erfolgreich ausgelöst
        """
        if not self._is_initialized or not self._camera_ref:
            return False
        
        return edsdk.take_picture(self._camera_ref)
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    @property
    def camera_name(self) -> str:
        if self._camera_info:
            return self._camera_info.get("name", "Unknown Canon Camera")
        return "Not connected"
