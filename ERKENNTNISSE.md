# Erkenntnisse - Fexobooth V2

Lessons Learned und Technologie-Entscheidungen für zukünftige Referenz.

---

## Technologie-Entscheidungen

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

## Performance-Erkenntnisse

- **Max. 25 FPS für Video** - Mehr schafft die Hardware nicht flüssig
- **Keine 60fps GUI-Updates** - after() mit mindestens 50ms Intervall
- **Bilder nicht im RAM halten** - Sofort auf Disk schreiben, nur bei Bedarf laden
- **Flask ist OK** - Verbraucht nur ~20-30 MB RAM im Idle
- **LANCZOS-Resize cachen** - Overlay-Resize auf App-Level statt Screen-Level, überlebt Screen-Wechsel
- **Kamera nicht freigeben bei Zwischen-Videos** - Kamera bleibt warm, spart ~1.5s Reopening
