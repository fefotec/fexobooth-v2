# Erkenntnisse - Fexobooth V2

Lessons Learned und Technologie-Entscheidungen für zukünftige Referenz.

---

## Technologie-Entscheidungen

### EDSDK ist NICHT thread-safe! (Windows COM STA)

| | |
|---|---|
| **Kontext** | Canon EDSDK DLL nutzt Windows COM mit Single-Threaded Apartment. Wenn zwei Threads gleichzeitig EDSDK-Funktionen aufrufen (z.B. UI-Thread `list_cameras()` + Background-Thread `capture_photo()`), entsteht ein Deadlock |
| **Entscheidung** | Alle EDSDK-Aufrufe vom UI-Thread nur wenn `camera_manager.is_initialized == False` (= keine aktive Session). Wenn die Kamera in Benutzung ist, überspringt `_check_camera_status()` den EDSDK-Check komplett |
| **Alternativen** | Thread-Lock um alle EDSDK-Aufrufe (komplexer, fehleranfällig), EDSDK nur von einem Thread (erfordert Message-Queue-Architektur), Kamera-Status ohne EDSDK prüfen (WMI/USB-Enumeration - Overkill) |
| **Begründung** | Pragmatische Lösung: `is_initialized` ist ein zuverlässiger Proxy. Wenn die Kamera initialisiert ist, wissen wir dass sie verbunden ist. Wenn nicht, ist es sicher EDSDK aufzurufen weil kein anderer Thread es nutzt |

### Kiosk-Modus: Taskleiste verstecken + Benachrichtigungen unterdrücken (KEIN permanentes topmost!)

| | |
|---|---|
| **Kontext** | App muss im Kiosk-Modus laufen: Kein Zugang zu Windows für Kunden, keine störenden Windows-Meldungen. Aber eigene App-Dialoge (USB-Sync, Export, Event-Wechsel) müssen im Vordergrund erscheinen |
| **Entscheidung** | Drei-Säulen-Ansatz: (1) Taskleiste via Windows API verstecken (`FindWindowW("Shell_TrayWnd")` + `ShowWindow(SW_HIDE)`), wird alle 5s re-assertet. (2) Windows-Benachrichtigungen via Registry unterdrücken (`NOC_GLOBAL_SETTING_TOASTS_ENABLED=0`). (3) `-topmost=True` nur KURZ beim Fenster-Positionieren, dann sofort wieder entfernt. Notfall-Shortcut Ctrl+Shift+Q zum Beenden |
| **Alternativen** | Permanentes `-topmost=True` (**SCHLECHT** - blockiert ALLE Dialoge inkl. eigener App-Dialoge, macht App unbedienbar!), `WS_EX_APPWINDOW` via `withdraw/deiconify` (Race Condition), Windows Kiosk-Modus / Assigned Access (braucht Enterprise) |
| **Begründung** | Permanentes `-topmost=True` verhindert dass Toplevel-Dialoge (auch eigene!) in den Vordergrund kommen. `transient()` + `grab_set()` reichen nicht gegen ein topmost-Elternfenster. Taskleiste-Verstecken allein ist ausreichend um Windows-Zugang zu verhindern. Benachrichtigungs-Toasts werden über Registry deaktiviert statt durch topmost überlagert |

### Canon DSLR: Dual-Modus Capture (SD-Karte optional, Host-Download als Fallback)

| | |
|---|---|
| **Kontext** | Canon EOS 2000D auf Fotoboxen - manche haben SD-Karte, manche nicht. Bilder müssen in voller DSLR-Auflösung auf dem Tablet landen. Host-Download hing anfangs → Ursache war der EDSDK-Deadlock (UI-Thread + Session-Thread gleichzeitig), NICHT der Host-Download selbst |
| **Entscheidung** | Zwei Modi: (1) MIT SD-Karte: `set_save_to_camera()` + Directory-Polling (zuverlässigster Modus). (2) OHNE SD-Karte: `set_save_to_host()` + Event-Handler (`_on_object_event`) + Queue-basierter Download. System-Test nutzt immer LiveView (braucht keine SD-Karte, schneller) |
| **Alternativen** | Nur Directory-Polling (braucht SD-Karte - nicht akzeptabel für Boxen ohne SD), nur Host-Download (weniger getestet als Directory-Polling), LiveView-Fallback statt echtem Capture (reduzierte Auflösung) |
| **Begründung** | Beide Modi müssen funktionieren. Directory-Polling ist bewährt und zuverlässig. Host-Download ist notwendig für Boxen ohne SD-Karte. Der EDSDK-Deadlock-Fix (kein EDSDK vom UI-Thread wenn Session aktiv) war die eigentliche Lösung für das Hängen. `get_event()` MUSS regelmäßig gepollt werden damit Events auf Windows dispatched werden |

### Taskleiste: Crash-Sicherheit durch 3-Schichten-Schutz

| | |
|---|---|
| **Kontext** | `ShowWindow(SW_HIDE)` auf der Windows-Taskleiste ist persistent - bleibt auch nach App-Crash versteckt. Wenn die App abstürzt oder per Force-Kill beendet wird, ist die Taskleiste dauerhaft weg |
| **Entscheidung** | 3-Schichten-Schutz: (1) `atexit.register()` in `app.py` als Safety-Net bei sauberen Python-Exits. (2) `_recover_taskbar()` in `main.py` beim App-Start - stellt Taskleiste wieder her bevor die App das Fenster erstellt. (3) Global Exception Handler stellt Taskleiste bei unbehandelten Exceptions wieder her |
| **Alternativen** | Windows-Service der Taskleiste überwacht (Overkill), Scheduled Task beim Login (unzuverlässig), nur `atexit` (reicht nicht für harte Kills) |
| **Begründung** | `atexit` allein fängt keine SIGKILL/Stromausfälle ab. Die Recovery beim nächsten Start ist die zuverlässigste Lösung - selbst nach hartem Crash wird die Taskleiste beim nächsten Programmstart sofort wiederhergestellt, bevor die App sie erneut versteckt |

### OTA-Update: GitHub Releases statt Source-Archiv

| | |
|---|---|
| **Kontext** | 200 Produktions-Tablets laufen als PyInstaller-EXE (kein Python/Git installiert). Source-Download via `archive/refs/heads/main.zip` nutzlos, weil Tablets die EXE brauchen |
| **Entscheidung** | GitHub Releases API (`/repos/.../releases/latest`) + ZIP-Asset mit fertigem Build. In-App Button im Service-Menü + standalone BAT-Datei als Fallback |
| **Alternativen** | Auto-Updater mit Polling (braucht dauerhaft Internet), Inno Setup Installer erneut ausführen (braucht Admin-Rechte + User-Interaktion), eigener Update-Server (Overkill) |
| **Begründung** | Tablets sind meist offline (Hotspot-Modus). Update nur wenn manuell Internet angeschlossen. GitHub Releases ist kostenlos, versioniert, und die API ist stabil. BAT-Script als Fallback wenn App nicht startet |

### USB-Stick Erkennung: 3 Typen + Fallback

| | |
|---|---|
| **Kontext** | Verschiedene USB-Sticks können eingesteckt werden: Event-Sticks (Buchung), Backup-Sticks, oder fremde Sticks |
| **Entscheidung** | Label-basierte Erkennung: "fexobox" = Event, "FEXOSAFE" = Backup, alles andere = unbekannt → Export anbieten |
| **Alternativen** | Nur bekannte Sticks akzeptieren (kein Notfall-Export möglich) |
| **Begründung** | Wenn ein Kunden-Stick kaputt geht, muss es eine Möglichkeit geben, Bilder auf einen beliebigen USB-Stick zu exportieren. Erkennung über `GetDriveTypeW` (DRIVE_REMOVABLE) + `GetVolumeInformationW` (Label) |

### USB-Sync: Niemals automatisch, immer fragen

| | |
|---|---|
| **Kontext** | Bilder werden bei jedem Foto auf USB kopiert. Wenn der Kunde den Stick kurz abzieht und wieder einsteckt, fehlen evtl. Bilder auf USB |
| **Entscheidung** | Kein Auto-Sync. Bestätigungsdialog mit Fortschritt und Abbrechen-Button. Bei neuem Event (anderer Stick) wird NICHT kopiert |
| **Alternativen** | Auto-Sync bei jedem Einstecken (kopiert ungefragt, auch bei neuem Event), kein Sync (Bilder fehlen auf USB) |
| **Begründung** | User muss Kontrolle haben. Bei neuem Event dürfen alte Bilder nicht auf den neuen Stick. Nur bei gleichem Event ist Sync sinnvoll. Abbrechen-Option wichtig weil Kopieren auf schwacher Hardware lange dauern kann |

### Galerie-Server: Immer lokaler Pfad, nie USB

| | |
|---|---|
| **Kontext** | Bilder existieren an zwei Orten: Lokal (C:\FexoBooth\BILDER) und USB (F:\BILDER). USB ist Backup und darf nicht gelöscht werden |
| **Entscheidung** | Galerie liest immer vom lokalen Pfad. Löschen betrifft nur lokale Festplatte. No-cache Headers auf allen Gallery-Responses |
| **Alternativen** | USB-Pfad bevorzugen (Löschen wirkt nicht in Galerie), USB auch löschen (zerstört Backup) |
| **Begründung** | Lokaler Pfad = "Arbeitskopie", USB = "Backup". Galerie zeigt die Arbeitskopie. Wenn die gelöscht wird, ist die Galerie sofort leer. USB-Bilder bleiben sicher erhalten |

### Event-Wechsel: Pending-Dialog-Queue statt sofortigem Laden

| | |
|---|---|
| **Kontext** | Neuer USB-Stick kann jederzeit eingesteckt werden - auch während aktiver Foto-Session |
| **Entscheidung** | Pending-Dialog-Queue: Dialoge werden in `_pending_event_change` / `_pending_fexosafe_drive` gespeichert und erst beim Rückkehr zum StartScreen angezeigt |
| **Alternativen** | Sofort Dialog zeigen (unterbricht User-Session), Komplett im Hintergrund wechseln (User merkt nichts) |
| **Begründung** | Session nicht unterbrechen, User soll bewusst entscheiden. Event-Wechsel hat Priorität über FEXOSAFE-Dialog |

### Dual-USB-System: fexobox + FEXOSAFE

| | |
|---|---|
| **Kontext** | Bilder vom alten Event dürfen nicht auf den neuen Event-Stick, aber müssen gesichert werden |
| **Entscheidung** | Separater Sicherungs-Stick mit Volume-Label "FEXOSAFE" |
| **Alternativen** | Gleicher Stick mit Template-Erkennung (fragil), Netzwerk-Backup (offline nicht möglich) |
| **Begründung** | Klare Trennung: "fexobox" = Event-Stick, "FEXOSAFE" = Sicherungs-Stick. Erkennung über Volume-Label ist eindeutig und robust |

### Tkinter Toplevel-Dialoge: Niemals innerhalb destroy()-Callback erstellen

| | |
|---|---|
| **Kontext** | Service-PIN (6588) Eingabe im AdminDialog führte zum App-Freeze |
| **Entscheidung** | Dialog setzt nur ein Flag (`_open_service = True`) und zerstört sich via `self.destroy()`. Der aufrufende Code (nach `wait_window()`) prüft das Flag und erstellt den neuen Dialog |
| **Alternativen** | ServiceDialog direkt in `_open_service_menu()` erstellen (verursacht Freeze), `withdraw()` statt `destroy()` (Zombie-Window) |
| **Begründung** | Wenn Toplevel A sich `destroy()`t und Toplevel B innerhalb desselben Callbacks erstellt, kann B hinter dem Hauptfenster landen. Mit `grab_set()` wird dann das Hauptfenster blockiert → Freeze. Neuen Dialog immer NACH `wait_window()` im aufrufenden Code erstellen |

### Canon SELPHY Fehlererkennung: EnumWindows statt Spooler-API

| | |
|---|---|
| **Kontext** | Canon SELPHY CP1000 meldet Papier-/Kassettenfehler NICHT über win32print PRINTER_STATUS Flags |
| **Entscheidung** | Fehlererkennung über `EnumWindows` API: Canon-Treiber zeigt eigene Dialog-Fenster (Titel "Canon SELPHY CP1000 ..."), deren Child-Controls (Static Labels) den Fehlertext enthalten |
| **Alternativen** | win32print Spooler-Flags (Canon setzt diese nicht), EnumJobs pStatus (Canon befüllt das Feld nicht zuverlässig) |
| **Begründung** | Der Canon-Treiber nutzt seinen eigenen Dialog statt des Windows-Spooler-Mechanismus. EnumWindows + EnumChildWindows ist die einzige zuverlässige Methode, den Fehlertext abzugreifen |

### Video-Wiedergabe: VLC mit DXVA2 Hardware-Beschleunigung

| | |
|---|---|
| **Kontext** | Video-Wiedergabe auf schwacher Hardware (Atom CPU) |
| **Entscheidung** | VLC (python-vlc) mit DXVA2 Hardware-Beschleunigung |
| **Alternativen** | MSMF/OpenCV (UI-Freeze, eingeschränkte Codec-Unterstützung), FFmpeg (zusätzliche Dependency) |
| **Begründung** | VLC nutzt GPU-Beschleunigung (DXVA2), kein UI-Freeze, breite Codec-Unterstützung |

### GUI-Framework: CustomTkinter

| | |
|---|---|
| **Kontext** | Leichtgewichtiges GUI für schwache Hardware |
| **Entscheidung** | CustomTkinter |
| **Alternativen** | PyQt (zu schwer), Kivy (zu schwer), Standard Tkinter (hässlich) |
| **Begründung** | Modern aussehend, leichtgewichtig, einfache API |

### Galerie-Server: Flask

| | |
|---|---|
| **Kontext** | Lokaler Webserver für QR-Code Galerie |
| **Entscheidung** | Flask |
| **Alternativen** | FastAPI (overkill), http.server (zu primitiv) |
| **Begründung** | Leichtgewichtig (~20-30 MB RAM), einfach, bewährt |

### Persistenz: JSON-Cache statt Datenbank

| | |
|---|---|
| **Kontext** | Buchungsdaten und Settings speichern |
| **Entscheidung** | JSON-Dateien in .booking_cache/ |
| **Alternativen** | SQLite (overkill), Registry (Windows-spezifisch, unflexibel) |
| **Begründung** | Einfach, lesbar, portabel, keine zusätzliche Dependency |

---

## Lessons Learned

### Video: OpenCV Default-Backend kann H.264 nicht decodieren

| | |
|---|---|
| **Problem** | Video zeigt schwarzen Bildschirm auf Miix 310 |
| **Ursache** | OpenCV Default-Backend kann H.264/MP4 nicht decodieren |
| **Lösung** | MSMF-Backend explizit setzen: `cv2.VideoCapture(path, cv2.CAP_MSMF)` |
| **Merke** | Auf schwacher Windows-Hardware immer MSMF für Video nutzen |

### Video: Frame-Lesen blockiert Main-Thread

| | |
|---|---|
| **Problem** | UI friert während Video-Wiedergabe ein |
| **Ursache** | `cap.read()` blockiert den Main-Thread |
| **Lösung** | Threading mit Frame-Queue (Producer-Consumer Pattern) |
| **Merke** | Auf schwacher Hardware immer Video-Decoding in separaten Thread |

### Hotspot: NetworkOperatorTetheringManager braucht Internet

| | |
|---|---|
| **Problem** | Hotspot-Script schlägt fehl ohne Internetverbindung |
| **Ursache** | Windows NetworkOperatorTetheringManager braucht aktive Internetverbindung |
| **Lösung** | Fallback auf netsh hostednetwork |
| **Merke** | Für Offline-Betrieb mehrere Fallback-Methoden implementieren |

### USB: Singleton-Pattern für shared State

| | |
|---|---|
| **Problem** | Pending-Files Counter aktualisiert sich nicht live |
| **Ursache** | Verschiedene Module hatten eigene USBManager-Instanzen |
| **Lösung** | `get_shared_usb_manager()` Singleton-Funktion |
| **Merke** | Bei shared State immer Singleton oder DI nutzen |

### Persistenz: Cache für USB-Daten

| | |
|---|---|
| **Problem** | Template und Buchung nach Neustart oder USB-Abzug weg |
| **Ursache** | Daten wurden nur vom USB gelesen, nicht gecached |
| **Lösung** | Lokaler Cache in .booking_cache/ |
| **Merke** | USB-Daten immer lokal cachen für Offline-Betrieb |

---

### Event-Wechsel: reset_session() löscht gerade geladenes Template

| | |
|---|---|
| **Problem** | System-Test meldet "Keine Template-Boxen geladen", obwohl Template auf USB funktioniert |
| **Ursache** | `_execute_event_change()` lud Template in Schritt 6 (`self.template_boxes = boxes`), aber `reset_session()` in Schritt 9 setzte `self.template_boxes = []` zurück. System-Test in Schritt 12 fand leere Boxes |
| **Lösung** | `reset_session()` VOR Template-Laden verschieben (Schritt 4 statt 9) |
| **Merke** | Bei mehrstufigen Initialisierungen: Daten die im späteren Schritt gebraucht werden NICHT in einem Zwischenschritt überschreiben. Reihenfolge: Erst aufräumen, dann neu befüllen |

### Doppelter Screen-Wechsel bei Video-Callbacks

| | |
|---|---|
| **Problem** | Session-Screen wird 2x erstellt/zerstört nach jedem Zwischen-Video |
| **Ursache** | `_on_video_end()` ruft sowohl `on_complete()` (Callback navigiert) als auch `show_screen()` auf |
| **Lösung** | `show_screen()` nur aufrufen wenn KEIN Callback vorhanden, sonst übernimmt Callback |
| **Merke** | Bei Callback-Pattern: Callback ODER eigene Navigation, nie beides |

### VLC-Cleanup blockiert Kamera-Initialisierung

| | |
|---|---|
| **Problem** | ~400ms Verzögerung nach Video weil VLC und Kamera gleichzeitig DXVA2 nutzen |
| **Ursache** | VLC-Cleanup lief asynchron (fire-and-forget Thread) |
| **Lösung** | `thread.join(timeout=1.0)` - VLC muss DXVA2 freigeben bevor Kamera startet |
| **Merke** | Hardware-Ressourcen immer synchron freigeben bevor nächster Consumer startet |

### Template-ZIP Caching

| | |
|---|---|
| **Problem** | Gleiche ZIP-Datei wurde 3x entpackt beim App-Start |
| **Ursache** | Kein Modul-Level-Cache in TemplateLoader |
| **Lösung** | `_template_cache` Dictionary mit (Pfad, mtime) als Key |
| **Merke** | Teure I/O-Operationen (ZIP, Bilddateien) immer cachen |

### Service-Menü: Separater PIN statt eigener Screen

| | |
|---|---|
| **Problem** | Internes Wartungsmenü soll über anderen PIN aufrufbar sein |
| **Ursache** | Admin-PIN-Dialog ist bereits vorhanden und zentral angebunden |
| **Lösung** | Bestehenden PIN-Dialog erweitert: Service-PIN wird VOR dem Admin-PIN geprüft, öffnet eigenen Dialog |
| **Merke** | Bestehende Infrastruktur erweitern statt duplizieren. App-Referenz am Root-Widget für Dialog-übergreifenden Zugriff |

### CTkImage: dark_image Parameter nötig im Dark Mode

| | |
|---|---|
| **Problem** | Logo wird in der Top-Bar nicht angezeigt, obwohl Pfad korrekt und Datei existiert |
| **Ursache** | `CTkImage(light_image=...)` zeigt nichts im Dark Mode - CustomTkinter nutzt `dark_image` wenn Appearance Mode dark ist |
| **Lösung** | `CTkImage(light_image=img, dark_image=img, size=...)` - beide Parameter setzen |
| **Merke** | CustomTkinter CTkImage braucht IMMER beide Image-Parameter, sonst wird je nach Mode nichts angezeigt |

---

### VLC: Erste Instance-Erstellung dauert ~57s auf schwacher Hardware

| | |
|---|---|
| **Problem** | Erstes Video nach App-Start friert 57 Sekunden ein |
| **Ursache** | VLC lädt beim ersten `_vlc.Instance()` den gesamten Plugin-Cache (~200 Plugins) |
| **Lösung** | Warmup im Hintergrund-Thread direkt beim App-Start. Subtile Ladeanimation falls Video vor Warmup-Ende gestartet wird |
| **Merke** | Teure Initialisierungen immer vorziehen (Warmup-Pattern). 2. VLC-Instance ist sofort (91ms vs 57s) |

### Hotspot-Steuerung blockiert Hauptthread

| | |
|---|---|
| **Problem** | App friert ~6.3s ein beim Start weil Hotspot gestartet/gestoppt wird |
| **Ursache** | PowerShell-Aufruf für Windows Mobile Hotspot API ist synchron und langsam |
| **Lösung** | Start und Stop in daemon-Threads auslagern |
| **Merke** | Alle externen Prozessaufrufe (subprocess) in Hintergrund-Threads |

### overrideredirect(True) macht App zum Hintergrund-Prozess

| | |
|---|---|
| **Problem** | App erscheint im Windows Taskmanager als "Hintergrund-Prozess" statt "App" |
| **Ursache** | `overrideredirect(True)` entfernt das Fenster aus der Windows-Shell-Verwaltung (kein Taskbar-Eintrag) |
| **Lösung** | `overrideredirect(True)` beibehalten (deckt auf Miix 310 korrekt den ganzen Screen ab), PLUS Windows API `SetWindowLongW` mit `WS_EX_APPWINDOW` Flag setzen (erzwingt Taskbar-Eintrag) |
| **Merke** | `attributes("-fullscreen", True)` deckt auf manchen Tablets NICHT den ganzen Bildschirm ab! `overrideredirect(True)` + `WS_EX_APPWINDOW` via ctypes ist der sichere Weg |

### Foto-Zähler Off-by-One bei letztem Foto

| | |
|---|---|
| **Problem** | "Foto 5 von 4" wird beim letzten Foto einer 4er Collage angezeigt |
| **Ursache** | `_capture_photo` erhöht `current_photo_index` NACH dem Foto und ruft dann `_update_progress` auf. Beim 4. Foto: Index 3→4, Anzeige 4+1=5 |
| **Lösung** | `min(current_photo_index + 1, total_photos)` in `_update_progress` |
| **Merke** | Bei Zähler-Anzeigen immer auf Off-by-One achten, besonders wenn Index nach dem letzten Element hochgezählt wird |

### Flash-Bild intermittierend nicht sichtbar

| | |
|---|---|
| **Problem** | Auslösebild fehlt sporadisch beim 2. Foto einer Collage |
| **Ursache** | Flash wird nur per Flag (`show_flash=True`) gesetzt und erst beim nächsten `_update_live_view`-Tick (bis zu 50ms später) angezeigt. Auf langsamer Hardware kann der Tick verpasst werden |
| **Lösung** | `_display_flash()` direkt in `_take_photo()` aufrufen (sofortige Anzeige), zusätzlich zum Flag für die Loop |
| **Merke** | Zeitkritische visuelle Feedback-Elemente sofort anzeigen, nicht auf den nächsten Timer-Tick warten |

## Performance-Erkenntnisse

- **Max. 25 FPS für Video** - Mehr schafft die Hardware nicht flüssig
- **Keine 60fps GUI-Updates** - after() mit mindestens 50ms Intervall
- **Bilder nicht im RAM halten** - Sofort auf Disk schreiben, nur bei Bedarf laden
- **Flask ist OK** - Verbraucht nur ~20-30 MB RAM im Idle
- **LANCZOS-Resize cachen** - Overlay-Resize auf App-Level statt Screen-Level, überlebt Screen-Wechsel
- **Kamera nicht freigeben bei Zwischen-Videos** - Kamera bleibt warm, spart ~1.5s Reopening
- **Template-Preview im Session-Screen entfernen** - Vollbild-LiveView statt Template-Overlay spart ~200 Zeilen Code und mehrere PIL-Operationen pro Frame
- **BILINEAR statt LANCZOS für kleine Previews** - Filter-Mini-Previews brauchen keine High-Quality-Interpolation, BILINEAR reicht und ist spürbar schneller
- **Container-Größe Fallback** - `winfo_width()` gibt 0/1 zurück wenn Widget noch nicht gelayoutet wurde. Immer Fallback auf Screensize haben
- **Windows Icon-Cache** - `ie4uinit.exe` existiert nicht auf allen Geräten (z.B. Lenovo Miix 310). Icon-Cache-Dateien per PowerShell löschen UND `SHChangeNotify(SHCNE_ASSOCCHANGED)` aufrufen um den Explorer sofort zu benachrichtigen. In Inno Setup am besten direkt im Pascal-Script per `external 'SHChangeNotify@shell32.dll stdcall'`
- **ICO Multi-Size** - Windows Desktop-Icons brauchen 256x256 Auflösung. Eine ICO mit nur 16x16 wird verpixelt dargestellt. Immer alle Größen (16, 24, 32, 48, 64, 128, 256) einpacken
- **CTkImage dark_image** - CustomTkinter CTkImage braucht IMMER `dark_image` Parameter gesetzt, auch wenn identisch mit `light_image`. Ohne wird im Dark Mode NICHTS angezeigt. Betrifft ALLE Stellen wo CTkImage erzeugt wird (Flash, Preview, Final)
- **PIL paste() mit RGBA-Maske** - `Image.paste(img, pos, img)` mit RGBA-Maske funktioniert nur zuverlässig für Bilder die tatsächlich Transparenz haben (PNG). Für JPEG→RGBA-Konvertierung (Alpha=255 überall) kann die Maske Probleme machen. Besser: Bildmodus prüfen und nur für echte RGBA-Bilder die Maske verwenden, für RGB direkt ohne Maske pasten
- **CustomTkinter Overlays** - `place()` Widgets mit `fg_color="transparent"` zeigen die Hintergrundfarbe des Parent-Widgets, NICHT das darunter liegende Widget (kein echtes Alpha in tkinter). Für saubere UI: `pack()`-Layout verwenden, damit Elemente nicht überlappen. Overlays über Bildern erzeugen immer sichtbare Rechtecke
- **Booking-Settings vs. Config-Persistenz** - Booking-Settings aus settings.json werden via `apply_settings_to_config()` in die App-Config übernommen. Feature-Checks (z.B. Galerie aktiv?) müssen NUR die Config prüfen, nicht zusätzlich die Booking-Settings direkt. Sonst können Admin-Änderungen nicht greifen, weil die Booking-Settings die Config-Änderung "umgehen"
- **Gallery-Server Pfad ≠ Lokaler Bilder-Pfad** - Der Gallery-Server kann auf den USB-BILDER-Ordner zeigen, nicht auf den lokalen. Beim Löschen von Bildern muss auch der Gallery-Pfad berücksichtigt werden, sonst bleiben Bilder im Live-Server sichtbar
- **PyInstaller 6.x _internal-Ordner** - Neuere PyInstaller-Versionen legen Daten-Assets in `_internal/` ab, nicht im Root des Dist-Ordners. Desktop-Shortcuts und andere externe Referenzen auf Assets müssen den korrekten Pfad verwenden. Im Installer die ICO-Datei separat kopieren
- **Windows Mobile Hotspot braucht Internet** - `NetworkOperatorTetheringManager.GetInternetConnectionProfile()` gibt null zurück ohne Internetverbindung. Stattdessen `GetConnectionProfiles()` nutzen und ALLE Profile durchprobieren. Als Offline-Fallback: `netsh wlan hostednetwork` (braucht kein Internet, nutzt WiFi-Adapter direkt als SoftAP). Wichtig: WiFi-Adapter muss AKTIV bleiben, nur keine Verbindung zu einem Netzwerk haben
- **Flash-Bild muss gecacht werden** - `_display_flash()` lädt bei jedem Foto das JPEG neu (~120ms auf Atom CPU). Zusammen mit dem blockierenden `get_high_res_frame()` bleibt kaum Zeit für die GUI den Flash tatsächlich zu malen. Lösung: Flash-PIL-Image einmalig beim Session-Start cachen, und `update_idletasks()` nach dem Setzen aufrufen um den Redraw zu erzwingen
- **subprocess text=True Encoding** - `subprocess.run(..., text=True)` nutzt `locale.getpreferredencoding()` (cp1252 auf dt. Windows). PowerShell-Output mit Sonderzeichen (Umlaute, Unicode) kann `UnicodeDecodeError` auslösen. Fix: `text=True` weglassen und stattdessen `result.stdout.decode("utf-8", errors="replace")` verwenden
- **overrideredirect(True) nach Dialog** - Auf Windows wird `overrideredirect(True)` nicht immer sofort übernommen. Die App muss `withdraw()` + `deiconify()` aufrufen (in `_set_appwindow()`). Admin-Dialog darf Fullscreen-Restore NICHT selbst machen, sondern die App übernimmt das nach `wait_window()` mit `_enter_fullscreen()`
