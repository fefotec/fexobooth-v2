"""Canon DSLR Camera Manager (EDSDK)

High-level Kamera-Manager für Canon DSLRs via EDSDK.
Implementiert das CameraManager Interface für fexobooth.
"""

import cv2
import numpy as np
import time
import io
import itertools
import threading
from queue import Queue, Empty
from typing import Optional, List, Dict, Any
from PIL import Image, ExifTags
from ctypes import c_void_p

from .base import CameraManager
from src.utils.logging import get_logger, is_developer_mode

logger = get_logger(__name__)

# EDSDK Import (nur auf Windows)
try:
    from . import edsdk
    EDSDK_AVAILABLE = True
except Exception as e:
    EDSDK_AVAILABLE = False
    logger.warning(f"EDSDK nicht verfügbar: {e}")


_CANON_SESSION_IDS = itertools.count(1)


class CanonCameraManager(CameraManager):
    """Verwaltet Canon DSLR Kameras via EDSDK
    
    Unterstützt:
    - Live View Streaming
    - Foto-Capture in voller Auflösung
    - Kamera-Einstellungen (TODO)
    """
    
    def __init__(self):
        self._session_id = next(_CANON_SESSION_IDS)
        self._capture_ids = itertools.count(1)
        self._aktueller_capture_id: Optional[str] = None
        self._capture_gestartet: float = 0.0
        self._letztes_event: float = 0.0
        self._is_initialized = False
        self._initializing = False  # True während initialize() läuft (Deadlock-Schutz)
        self._session_open = False
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
        self._capture_accepting: bool = False
        self._captured_image: Optional[Image.Image] = None
        self._use_host_download: bool = False  # True = kein SD, Bild via Event-Handler empfangen
        self._host_storage_ready: bool = False  # von Kamera bestaetigter Host-Speicher
        self._event_handler_registered: bool = False  # True = Object-Event-Handler registriert
        # True = Session muss vor dem nächsten Capture vollständig neu aufbauen
        # (Shutdown, CARD_NG oder gedrosselter Sofort-Reconnect).
        self._camera_shutdown: bool = False

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

        self._diag(
            "MANAGER-CREATED",
            initialized=False,
            host=False,
            handler=False,
        )

    def _diag(self, event: str, **werte) -> None:
        """Korrelierte DSLR-Diagnose nur im dynamisch aktiven Dev-Modus."""
        if not is_developer_mode():
            return
        details = " ".join(f"{key}={value}" for key, value in werte.items())
        logger.debug(
            "CANON-DIAG "
            f"event={event} session={self._session_id} "
            f"thread={threading.current_thread().name}/{threading.current_thread().ident} "
            f"{details}".rstrip()
        )
    
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
        """Abgesicherter Einstieg; ein Fehler darf den Init-Status nie verklemmen."""
        self._initializing = True
        self._host_storage_ready = False
        try:
            return self._initialize_canon(camera_index, width, height)
        except Exception as e:
            logger.exception(f"Canon-Initialisierung unerwartet abgebrochen: {e}")
            if self._camera_ref:
                try:
                    edsdk.dispose_camera(
                        self._camera_ref, session_open=self._session_open
                    )
                except Exception as cleanup_error:
                    logger.error(
                        "Canon-Handle nach Init-Exception nicht freigegeben: "
                        f"{cleanup_error}"
                    )
            self._camera_ref = None
            self._camera_info = None
            self._session_open = False
            self._is_initialized = False
            self._use_host_download = False
            self._host_storage_ready = False
            self._event_handler_registered = False
            return False
        finally:
            self._initializing = False

    def _initialize_canon(self, camera_index: int, width: int, height: int) -> bool:
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
            self._initializing = True
        
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
        
        # Der Wrapper routet jetzt ausnahmslos selbst auf den Owner-Thread.
        logger.debug("Kamera-Liste abrufen...")
        cameras = edsdk.get_camera_list() or []
        logger.info(f"Gefundene Kameras: {len(cameras)}")
        
        if not cameras:
            logger.error("Keine Canon Kamera gefunden")
            self._initializing = False
            return False
        
        for i, cam in enumerate(cameras):
            logger.debug(f"  [{i}] {cam.get('name', 'Unknown')} @ {cam.get('port', '?')}")
        
        if camera_index >= len(cameras):
            logger.error(f"Kamera-Index {camera_index} ungültig (nur {len(cameras)} Kameras)")
            for cam in cameras:
                edsdk.release(cam.get("ref"))
            self._initializing = False
            return False
        
        # Kamera auswählen
        self._camera_info = cameras[camera_index]
        self._camera_ref = self._camera_info["ref"]
        self._session_open = False

        # Nicht ausgewaehlte Handles stammen ebenfalls vom EDSDK und muessen
        # im Owner freigegeben werden.
        for i, cam in enumerate(cameras):
            if i != camera_index:
                edsdk.release(cam.get("ref"))
        
        logger.info(f"Verbinde mit: {self._camera_info['name']}")

        # Canon registriert Object-/State-Handler im offiziellen Sample vor
        # OpenSession. Entscheidend ist: derselbe Owner-Thread fuer alles.
        logger.info("Registriere Canon Object- und State-Handler im Owner")
        object_ok = edsdk.set_object_event_handler(
            self._camera_ref, self._on_object_event
        )
        state_ok = edsdk.set_state_event_handler(
            self._camera_ref, self._on_state_event
        )
        if object_ok is not True or state_ok is not True:
            logger.error(
                "Canon-Handler nicht vollstaendig registriert: "
                f"object={object_ok!r}, state={state_ok!r}"
            )
            edsdk.dispose_camera(self._camera_ref, session_open=False)
            self._camera_ref = None
            self._camera_info = None
            self._initializing = False
            return False

        self._event_handler_registered = True

        # Session oeffnen (mit genau einem kontrollierten Busy-Retry).
        logger.debug("Öffne Kamera-Session...")
        if not edsdk.open_session(self._camera_ref):
            logger.error("Session konnte nicht geöffnet werden")
            edsdk.dispose_camera(self._camera_ref, session_open=False)
            self._camera_ref = None
            self._camera_info = None
            self._event_handler_registered = False
            self._initializing = False
            return False
        
        logger.info("Session erfolgreich geöffnet")
        self._session_open = True

        # Die Live-Flotte arbeitet ohne Speicherkarte. Host-Transfer ist kein
        # Fallback, sondern der verbindliche Produktionsweg.
        self._use_host_download = True
        if not edsdk.set_save_to_host(self._camera_ref):
            logger.error("Host-Speicher konnte nicht vollständig bereitgemeldet werden")
            edsdk.dispose_camera(self._camera_ref, session_open=True)
            self._camera_ref = None
            self._camera_info = None
            self._session_open = False
            self._use_host_download = False
            self._host_storage_ready = False
            self._event_handler_registered = False
            self._initializing = False
            return False
        self._host_storage_ready = True
        logger.info("Speicherung: direkter Host-Transfer ohne Speicherkarte")

        # Bildqualität auf JPG Large Fine setzen (kein RAW!) - nicht kritisch wenn fehlschlägt
        try:
            if not edsdk.set_image_quality_jpg(self._camera_ref):
                logger.warning("Bildqualität konnte nicht auf JPG gesetzt werden - bitte manuell prüfen!")
        except Exception as e:
            logger.warning(f"set_image_quality_jpg Exception (ignoriert): {e}")

        self._is_initialized = True
        self._initializing = False
        logger.info(f"✅ Canon Kamera initialisiert: {self._camera_info['name']}")
        self._diag(
            "INITIALIZED",
            initialized=True,
            host=self._use_host_download,
            host_ready=self._host_storage_ready,
            object_handler=self._event_handler_registered,
            state_handler=True,
        )

        # Kamera-Einstellungen loggen (für Debugging)
        edsdk.log_camera_settings(self._camera_ref)
        
        return True
    
    def release(self):
        """Gibt Kamera-Ressourcen frei"""
        self._diag(
            "RELEASE-START",
            initialized=self._is_initialized,
            live_view=self._live_view_active,
        )
        if self._live_view_active:
            self.stop_live_view()

        if self._camera_ref:
            edsdk.dispose_camera(
                self._camera_ref, session_open=self._session_open
            )

        self._camera_ref = None
        self._camera_info = None
        self._is_initialized = False
        self._initializing = False
        self._session_open = False
        self._use_host_download = False
        self._host_storage_ready = False
        self._event_handler_registered = False
        self._camera_shutdown = False
        self._last_frame = None

        logger.info("Canon Kamera freigegeben")
        self._diag("RELEASE-END", initialized=False, live_view=False)
    
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
            logger.debug(f"get_live_view_image Exception: {e}")
            jpeg_data = None

        if jpeg_data is None:
            # EDSDK-Fehler werden im Wrapper in `letzter_fehler` abgelegt und
            # kommen als regulaeres None zurueck. Deshalb muss auch dieser
            # Normalpfad gezaehlt werden, nicht nur eine Python-Exception.
            if not hasattr(self, '_evf_error_count'):
                self._evf_error_count = 0
            self._evf_error_count += 1
            fehler = getattr(edsdk, "letzter_fehler", 0)
            name = edsdk.ERROR_NAMES.get(fehler, "UNBEKANNT")
            if self._evf_error_count <= 3 or self._evf_error_count % 100 == 0:
                logger.debug(
                    f"get_live_view_image Fehler #{self._evf_error_count}: "
                    f"{name} ({hex(fehler)})"
                )
            self._diag(
                "LIVEVIEW-NONE",
                count=self._evf_error_count,
                error=name,
                code=hex(fehler),
                owner=edsdk.owner_snapshot() if is_developer_mode() else "-",
            )

            if edsdk.ist_verbindung_tot(fehler):
                logger.error(
                    "Live-View-Verbindung verloren: "
                    f"{name} ({hex(fehler)}) — vollstaendige Neu-Enumeration"
                )
                self._live_view_active = False
                self._verbindung_neu_aufbauen(
                    f"Live-View-Download scheiterte mit {name}"
                )
                return _notnagel("Kameraverbindung verloren")

            # Bei vielen Fehlern: Live-View neu starten
            if self._evf_error_count % 30 == 0:
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
        """Kompatibilitaets-Hook fuer app.py; der Owner pumpt selbst.

        Absichtlich kein EDSDK-Aufruf aus dem Tk-Thread. Der zentrale
        `edsdk-kamera`-Thread verarbeitet Windows-Nachrichten und EdsGetEvent.
        """
        if not self._is_initialized or not EDSDK_AVAILABLE:
            return
        if self._reconnect_laeuft:
            return
        self._pump_laeufe += 1

    def _log_kamera_zustand_kurz(self) -> None:
        """Dev-Snapshot der relevanten Kamera-Werte direkt vor dem Auslösen."""
        if not is_developer_mode() or not self._camera_ref:
            return

        try:
            prop_ids = (
                edsdk.kEdsPropID_BatteryLevel,
                edsdk.kEdsPropID_AEMode,
                edsdk.kEdsPropID_AFMode,
                edsdk.kEdsPropID_Tv,
                edsdk.kEdsPropID_Av,
                edsdk.kEdsPropID_ISOSpeed,
                edsdk.kEdsPropID_WhiteBalance,
                edsdk.kEdsPropID_ExposureCompensation,
                edsdk.kEdsPropID_MeteringMode,
                edsdk.kEdsPropID_Evf_ViewType,
            )
            snapshot = edsdk.get_property_snapshot(self._camera_ref, prop_ids)
            hole = snapshot.get
            akku = hole(edsdk.kEdsPropID_BatteryLevel)
            aemode = hole(edsdk.kEdsPropID_AEMode)
            afmode = hole(edsdk.kEdsPropID_AFMode)
            tv = hole(edsdk.kEdsPropID_Tv)
            av = hole(edsdk.kEdsPropID_Av)
            iso = hole(edsdk.kEdsPropID_ISOSpeed)
            wb = hole(edsdk.kEdsPropID_WhiteBalance)
            exposure_comp = hole(edsdk.kEdsPropID_ExposureCompensation)
            metering = hole(edsdk.kEdsPropID_MeteringMode)
            evf_view_type = hole(edsdk.kEdsPropID_Evf_ViewType)

            akku_text = {
                0: "LEER", 1: "sehr schwach", 2: "schwach",
                4: "ok", 0x7fffffff: "Netzstrom",
            }.get(akku, str(akku))
            af_text = {
                0: "One-Shot AF", 1: "AI Servo", 2: "AI Focus", 3: "manuell (MF)",
            }.get(afmode, str(afmode))
            ae_text = edsdk.AE_MODE_NAMEN.get(
                aemode, f"0x{aemode:x}" if aemode is not None else "?"
            )
            tv_text = ("legt die Kamera beim Auslösen fest" if tv == 0
                       else edsdk.TV_NAMEN.get(tv, f"0x{tv:x}" if tv is not None else "?"))
            av_text = ("legt die Kamera beim Auslösen fest" if av == 0
                       else edsdk.AV_NAMEN.get(av, f"0x{av:x}" if av is not None else "?"))
            iso_text = edsdk.ISO_NAMEN.get(iso, f"0x{iso:x}" if iso is not None else "?")
            wb_text = edsdk.WB_NAMEN.get(wb, str(wb))
            exposure_comp_text = edsdk.EXPOSURE_COMP_NAMEN.get(
                exposure_comp,
                edsdk.EXPOSURE_COMP_NAMEN.get(
                    exposure_comp & 0xFF, f"0x{exposure_comp:08x}"
                ) if exposure_comp is not None else "?",
            )
            metering_text = edsdk.METERING_MODE_NAMEN.get(
                metering, f"0x{metering:x}" if metering is not None else "?"
            )
            evf_text = edsdk.EVF_VIEW_TYPE_NAMEN.get(
                evf_view_type,
                f"0x{evf_view_type:x}" if evf_view_type is not None else "?",
            )

            logger.info(
                f"[3/5] Kamera-Zustand: Modus={ae_text}, Zeit={tv_text}, Blende={av_text}, "
                f"ISO={iso_text}, Weißabgleich={wb_text}, Fokus={af_text}, Akku={akku_text}"
            )
            self._diag(
                "EXPOSURE-PROPS",
                capture=self._aktueller_capture_id or "-",
                ae=ae_text.replace(" ", "_"),
                tv=tv_text.replace(" ", "_"),
                av=av_text.replace(" ", "_"),
                iso=iso_text,
                exposure_comp=exposure_comp_text.replace(" ", "_"),
                metering=metering_text.replace(" ", "_"),
                wb=wb_text.replace(" ", "_"),
                evf_view_type=evf_text.replace(" ", "_"),
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
            if wb in (0, 23):
                logger.info(
                    "[3/5] Hinweis: Weißabgleich steht auf Automatik. Der rechnet pro Foto neu — "
                    "in derselben Collage können die Bilder unterschiedlich farbig werden."
                )
            if aemode in (9, 15, 22, 23, 24, 25):
                # Ein Automatikmodus ist die BEWUSSTE Wahl für die Mietflotte:
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

    def _log_foto_belichtung(self, image: Image.Image) -> None:
        """Loggt EXIF und eine kleine Helligkeitsprobe ausschließlich im Dev-Mode."""
        if not is_developer_mode():
            return

        try:
            exif = image.getexif()
            exif_ifd = {}
            try:
                exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            except Exception:
                # Manche JPEGs legen die Werte direkt in IFD0 ab oder haben
                # gar keinen EXIF-Unterbaum. Beides ist fuer den Capture okay.
                pass

            def exif_wert(tag: int):
                wert = exif_ifd.get(tag)
                return exif.get(tag) if wert is None else wert

            def zahl(wert):
                if wert is None:
                    return "-"
                if isinstance(wert, (list, tuple)):
                    wert = wert[0] if wert else None
                try:
                    return f"{float(wert):.6g}"
                except (TypeError, ValueError, ZeroDivisionError):
                    return str(wert).replace(" ", "_")

            exposure_programme = {
                0: "undefiniert", 1: "manuell", 2: "Programmautomatik",
                3: "Zeitautomatik", 4: "Blendenautomatik", 5: "kreativ",
                6: "Action", 7: "Portrait", 8: "Landschaft",
            }
            exif_metering = {
                0: "unbekannt", 1: "Mittelwert", 2: "mittenbetont",
                3: "Spot", 4: "Multi-Spot", 5: "Mehrfeld", 6: "selektiv",
                255: "sonstige",
            }
            exif_wb = {0: "auto", 1: "manuell"}

            exposure_time = exif_wert(0x829A)
            f_number = exif_wert(0x829D)
            iso = exif_wert(0x8827)
            if iso is None:
                iso = exif_wert(0x8833)
            exposure_bias = exif_wert(0x9204)
            exposure_program = exif_wert(0x8822)
            metering = exif_wert(0x9207)
            flash = exif_wert(0x9209)
            white_balance = exif_wert(0xA403)

            max_kante = max(image.size)
            faktor = min(1.0, 256.0 / max_kante) if max_kante else 1.0
            ziel = (
                max(1, round(image.size[0] * faktor)),
                max(1, round(image.size[1] * faktor)),
            )
            thumb = image.resize(ziel, Image.Resampling.BOX).convert("RGB")
            luma_hist = thumb.convert("L").histogram()
            pixel = sum(luma_hist)

            def perzentil(prozent: int):
                ziel_anzahl = max(1, (pixel * prozent + 99) // 100)
                kumuliert = 0
                for helligkeit, anzahl in enumerate(luma_hist):
                    kumuliert += anzahl
                    if kumuliert >= ziel_anzahl:
                        return helligkeit
                return 255

            luma_mean = (
                sum(wert * anzahl for wert, anzahl in enumerate(luma_hist)) / pixel
                if pixel else 0.0
            )
            rgb_hist = thumb.histogram()
            nearwhite = sum(luma_hist[250:]) * 100.0 / pixel if pixel else 0.0
            shadows = sum(luma_hist[:16]) * 100.0 / pixel if pixel else 0.0
            kanal_clipping = [
                sum(rgb_hist[offset + 250:offset + 256]) * 100.0 / pixel
                if pixel else 0.0
                for offset in (0, 256, 512)
            ]

            self._diag(
                "EXPOSURE-JPEG",
                capture=self._aktueller_capture_id or "-",
                exif_tv_s=zahl(exposure_time),
                exif_f=zahl(f_number),
                exif_iso=zahl(iso),
                exif_bias_ev=zahl(exposure_bias),
                exif_program=exposure_programme.get(
                    exposure_program, str(exposure_program)
                ).replace(" ", "_"),
                exif_metering=exif_metering.get(
                    metering, str(metering)
                ).replace(" ", "_"),
                exif_flash=(f"0x{flash:x}" if isinstance(flash, int) else str(flash)),
                exif_wb=exif_wb.get(white_balance, str(white_balance)),
                luma_mean=f"{luma_mean:.1f}",
                p50=perzentil(50),
                p95=perzentil(95),
                p99=perzentil(99),
                nearwhite_pct=f"{nearwhite:.2f}",
                shadow_pct=f"{shadows:.2f}",
                r250_pct=f"{kanal_clipping[0]:.2f}",
                g250_pct=f"{kanal_clipping[1]:.2f}",
                b250_pct=f"{kanal_clipping[2]:.2f}",
                thumb=f"{ziel[0]}x{ziel[1]}",
            )
        except Exception as e:
            self._diag(
                "EXPOSURE-JPEG-ERROR",
                capture=self._aktueller_capture_id or "-",
                error=type(e).__name__,
            )

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


    def _capture_scharfschalten(self) -> None:
        """Bindet die Host-Queue unmittelbar vor dem Shutter an diesen Capture."""
        verworfen = 0
        while True:
            try:
                self._photo_queue.get_nowait()
                verworfen += 1
            except Empty:
                break
        self._capture_gestartet = time.monotonic()
        self._capture_accepting = True
        logger.info(
            "CANON-CAPTURE ARMED "
            f"capture={self._aktueller_capture_id or '-'} "
            f"discarded_queue_items={verworfen}"
        )

    def _on_object_event(self, event_type: int, obj_ref: c_void_p) -> bool:
        """Verarbeitet einen bereits aus dem nativen Callback ausgekoppelten Event.

        Diese Methode laeuft als normaler Auftrag im Canon-Owner. Der native
        Callback ist zu diesem Zeitpunkt bereits zur EDSDK.dll zurueckgekehrt.
        """
        self._events_gesehen += 1
        self._letztes_event = time.monotonic()
        event_name = edsdk.OBJECT_EVENT_NAMEN.get(
            event_type, f"0x{event_type:08x}"
        )
        seit_capture_ms = (
            (self._letztes_event - self._capture_gestartet) * 1000
            if self._capture_gestartet else -1
        )

        logger.info(
            "CANON-CAPTURE EVENT "
            f"capture={self._aktueller_capture_id or '-'} "
            f"event=0x{event_type:08x} name={event_name} "
            f"since_shutter_ms={seit_capture_ms:.1f} count={self._events_gesehen}"
        )

        if event_type in (
            edsdk.kEdsObjectEvent_DirItemRequestTransfer,
            edsdk.kEdsObjectEvent_DirItemRequestTransferDT,
        ):
            capture_id = self._aktueller_capture_id
            if not self._capture_accepting or not capture_id:
                logger.warning(
                    "CANON-CAPTURE STALE-EVENT-REJECTED "
                    f"event=0x{event_type:08x} capture={capture_id or '-'}"
                )
                # False veranlasst den Low-Level-Dispatcher zu Cancel+Release.
                return False

            download_start = time.monotonic()
            try:
                image_data = edsdk.download_image_to_memory(obj_ref)
                if image_data:
                    self._photo_queue.put((capture_id, image_data))
                    logger.info(
                        "CANON-CAPTURE DOWNLOAD-QUEUED "
                        f"capture={capture_id} "
                        f"bytes={len(image_data)} "
                        f"download_ms={(time.monotonic() - download_start) * 1000:.1f}"
                    )
                else:
                    logger.error(
                        "CANON-CAPTURE DOWNLOAD-FAILED "
                        f"capture={self._aktueller_capture_id or '-'}"
                    )
            except Exception as e:
                logger.exception(f"CANON-CAPTURE Download-Exception: {e}")

            # Auch ein fehlgeschlagener Download wurde im Wrapper per Cancel
            # abgeschlossen. True bedeutet hier: Transfer wurde behandelt.
            return True

        return False

    def _on_state_event(self, event_type: int, event_data: int) -> None:
        """Separater Canon-State-Handler; 0x301 gehoert nicht zu Object-Events."""
        event_name = edsdk.STATE_EVENT_NAMEN.get(
            event_type, f"0x{event_type:08x}"
        )
        seit_capture_ms = (
            (time.monotonic() - self._capture_gestartet) * 1000
            if self._capture_gestartet else -1
        )
        daten_name = edsdk.ERROR_NAMES.get(event_data, "-")
        logger.info(
            "CANON-STATE EVENT "
            f"capture={self._aktueller_capture_id or '-'} "
            f"event=0x{event_type:08x} name={event_name} "
            f"data=0x{event_data:08x} data_name={daten_name} "
            f"since_shutter_ms={seit_capture_ms:.1f}"
        )
        if event_type == edsdk.kEdsStateEvent_Shutdown:
            logger.error("CANON-STATE Kamera-Shutdown erkannt")
            self._camera_shutdown = True
            self._host_storage_ready = False
        elif (
            event_type == edsdk.kEdsStateEvent_CaptureError
            and event_data == edsdk.EDS_ERR_TAKE_PICTURE_CARD_NG
        ):
            logger.error(
                "CANON-STATE CARD_NG erkannt: Host-Bereitschaft wird verworfen"
            )
            self._host_storage_ready = False
            self._camera_shutdown = True

    def _recover_from_shutdown(self) -> bool:
        """Verwirft alte Referenzen und enumeriert die Kamera vollstaendig neu."""
        logger.warning("=== KAMERA RECOVERY: vollstaendige Neu-Enumeration ===")
        self._camera_shutdown = False
        camera_index = 0
        if self._camera_info:
            camera_index = int(self._camera_info.get("index", 0))
        try:
            self.release()
        except Exception as e:
            logger.warning(f"Recovery: release fehlgeschlagen: {e}")
            return False
        time.sleep(0.5)
        erfolg = self.initialize(camera_index=camera_index)
        logger.warning(
            f"=== KAMERA RECOVERY {'erfolgreich' if erfolg else 'FEHLGESCHLAGEN'} ==="
        )
        return erfolg

    def capture_photo(self, timeout: float = 10.0) -> Optional[Image.Image]:
        """Nimmt genau ein Foto in voller DSLR-Aufloesung auf.

        Produktionsweg ist der direkte Host-Transfer ohne Speicherkarte.

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

        # Recovery nach Shutdown oder verworfenem Host-/Verbindungszustand.
        if self._camera_shutdown:
            logger.warning("capture_photo: Kamera war im Shutdown - versuche Recovery...")
            if not self._recover_from_shutdown():
                logger.error("capture_photo: Recovery fehlgeschlagen!")
                return None

        if self._use_host_download and not (
            self._session_open
            and self._event_handler_registered
            and self._host_storage_ready
        ):
            logger.error(
                "CANON-HOST SHUTTER-BLOCKED: Host-Speicher ist nicht vollständig bereit "
                f"session={self._session_open} handler={self._event_handler_registered} "
                f"host_ready={self._host_storage_ready}"
            )
            self._diag(
                "SHUTTER-BLOCKED",
                reason="host_not_ready",
                session_open=self._session_open,
                handler=self._event_handler_registered,
                host_ready=self._host_storage_ready,
            )
            return None

        capture_start = time.monotonic()
        self._aktueller_capture_id = (
            f"{self._session_id}.{next(self._capture_ids)}"
        )
        self._capture_gestartet = 0.0
        self._capture_accepting = False
        self._diag(
            "CAPTURE-START",
            capture=self._aktueller_capture_id,
            host=self._use_host_download,
            live_view=self._live_view_active,
            events=self._events_gesehen,
        )

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

            # Beim Diagnose-/Notweg ueber Karte muss die Ausgangszahl VOR dem
            # Ausloesen stehen. Nach dem Trigger ist das neue Bild oft schon
            # in der vermeintlichen Baseline enthalten.
            karten_baseline = None
            if not self._use_host_download:
                karten_baseline = edsdk.get_card_image_count(self._camera_ref)
                logger.info(
                    f"[2/5] Karten-Baseline vor Ausloesung: {karten_baseline}"
                )

            # SCHRITT 3: Foto auslösen
            # 2.4.46: Kurz-Diagnose direkt vor dem Auslösen. Wenn wieder kein
            # Bild kommt, steht damit im Log, in welchem Zustand die Kamera war
            # — Akku, Wahlrad, Fokus-Art. Alle drei können ein Auslösen
            # verhindern, ohne dass die Software etwas falsch macht.
            self._log_kamera_zustand_kurz()

            logger.info(
                f"[3/5] Löse Kamera genau einmal aus "
                f"(Capture {self._aktueller_capture_id})..."
            )
            if not edsdk.take_picture(
                self._camera_ref,
                self._live_view_active,
                before_shutter=self._capture_scharfschalten,
            ):
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

                if fehler == getattr(
                    edsdk, "EDS_ERR_TAKE_PICTURE_CARD_NG", 0x00008D07
                ):
                    self._host_storage_ready = False
                    self._camera_shutdown = True
                    logger.error(
                        "   >>> Canon meldet CARD_NG trotz Host-Transfer. "
                        "Host-Bereitschaft verworfen; vor dem nächsten Foto "
                        "wird die Session vollständig neu aufgebaut."
                    )

                if edsdk.ist_verbindung_tot(fehler):
                    self._host_storage_ready = False
                    # Falls der sofortige Neuaufbau gerade gedrosselt oder
                    # bereits belegt ist, muss der nächste Benutzer-Capture
                    # trotzdem erneut durch die vollständige Recovery laufen.
                    self._camera_shutdown = True
                    self._verbindung_neu_aufbauen(f"Auslösen scheiterte mit {name}")

                return self._fallback_to_live_view(live_view_was_active)

            logger.info(
                "[3/5] ✓ Kamera ausgelöst! "
                f"command_ms={(time.monotonic() - self._capture_gestartet) * 1000:.1f}"
            )

            # SCHRITT 4: Auf Bild warten (je nach Modus)
            image_data = None

            if self._use_host_download:
                # Nur warten. Event-Poll, Windows-Message-Pump und Download
                # gehoeren dem Owner-Thread und duerfen hier nicht stattfinden.
                events_vorher = self._events_gesehen
                logger.info(f"[4/5] Warte auf Host-Download (max {timeout}s)...")
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        queue_item = self._photo_queue.get(
                            timeout=min(0.25, max(0.01, deadline - time.monotonic()))
                        )
                        if not (
                            isinstance(queue_item, tuple)
                            and len(queue_item) == 2
                        ):
                            logger.error(
                                "CANON-CAPTURE ungueltiger Queue-Eintrag verworfen"
                            )
                            continue
                        queue_capture_id, kandidat = queue_item
                        if queue_capture_id != self._aktueller_capture_id:
                            logger.warning(
                                "CANON-CAPTURE fremdes Queue-Bild verworfen "
                                f"expected={self._aktueller_capture_id} "
                                f"received={queue_capture_id}"
                            )
                            continue
                        image_data = kandidat
                        if image_data:
                            self._capture_accepting = False
                            logger.info(
                                f"[4/5] ✓ Bild via Host-Download: "
                                f"{len(image_data)} bytes, "
                                f"shutter_to_queue_ms="
                                f"{(time.monotonic() - self._capture_gestartet) * 1000:.1f}"
                            )
                            break
                    except Empty:
                        continue

                if image_data is None:
                    neu = self._events_gesehen - events_vorher
                    logger.error(
                        "CANON-CAPTURE TIMEOUT "
                        f"capture={self._aktueller_capture_id} timeout_s={timeout} "
                        f"new_events={neu} total_events={self._events_gesehen} "
                        f"owner={edsdk.owner_snapshot(fail_if_busy=True)}"
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
                    self._camera_ref,
                    timeout=karten_timeout,
                    baseline=karten_baseline,
                )

            if image_data is None:
                logger.error("[4/5] ✗ Kein Bild empfangen!")
                return self._fallback_to_live_view(live_view_was_active)

            logger.info(f"[4/5] ✓ Bild empfangen: {len(image_data)} bytes")

            # SCHRITT 5: Bild dekodieren + LiveView starten
            logger.info("[5/5] Dekodiere Bild...")
            decode_start = time.monotonic()
            try:
                image = Image.open(io.BytesIO(image_data))
                image.load()
                self._log_foto_belichtung(image)
                logger.info(
                    f"[5/5] ✓ Bild dekodiert: {image.size[0]}x{image.size[1]} "
                    f"({image.mode}), decode_ms="
                    f"{(time.monotonic() - decode_start) * 1000:.1f}"
                )
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
                f"=== ECHTES DSLR-FOTO: capture={self._aktueller_capture_id} "
                f"{image.size[0]}x{image.size[1]} "
                f"total_ms={(time.monotonic() - capture_start) * 1000:.1f} === "
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
        finally:
            self._diag(
                "CAPTURE-END",
                capture=self._aktueller_capture_id,
                total_ms=f"{(time.monotonic() - capture_start) * 1000:.1f}",
                events=self._events_gesehen,
                real=self._fotos_echt,
                fallback=self._fotos_notloesung,
                empty=self._fotos_leer,
            )
            self._capture_accepting = False
            self._aktueller_capture_id = None
            self._capture_gestartet = 0.0

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
        """Sperrt den alten Direktshutter ohne Queue-/Host-Vertrag.

        Ein Canon-Foto darf nur über :meth:`capture_photo` laufen. Dort sind
        Host-Readiness, Capture-ID, Transfer-Queue und genau ein Shutter als
        eine Einheit abgesichert. Die Methode bleibt nur als fehlertoleranter
        Kompatibilitaetsstub bestehen.
        """
        logger.error(
            "Canon take_picture() ohne Downloadvertrag ist gesperrt; "
            "capture_photo() verwenden"
        )
        return False
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized
    
    @property
    def camera_name(self) -> str:
        if self._camera_info:
            return self._camera_info.get("name", "Unknown Canon Camera")
        return "Not connected"
