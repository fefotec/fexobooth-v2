# Fexobooth V2 - Projektsteuerung

## Projekt-Info

| Feld | Wert |
|------|------|
| **Name** | Fexobooth V2 |
| **Beschreibung** | Photobooth-Software für fexobox Mietgeräte |
| **Stack** | Python 3.10+, CustomTkinter, OpenCV, Pillow, Flask, PyInstaller |
| **Ziel-Hardware** | Lenovo Miix 310 (1280×800, 4GB RAM, Offline-Betrieb) |
| **Arbeitsumgebung erstellt** | 2026-02-05 |

---

## ⚠️ Laufende Baustelle: DSLR (Canon)

**Wer an der Canon-/DSLR-Unterstuetzung arbeitet, liest ZUERST
[DSLR-STAND.md](DSLR-STAND.md).** Dort steht der vollstaendige Stand vom
24.08.2026: was funktioniert, was nicht, die acht bereits behobenen Ursachen,
die Werkzeuge und die Fallstricke.

Zwei Punkte daraus sind so wichtig, dass sie hier stehen:

1. **Die DSLR-Boxen haben in der Regel KEINE Speicherkarte.** Der Direktweg
   (`SaveTo = Host`) ist der einzige Weg, der in der Flotte funktioniert.
   Ein Rueckfall auf den Kartenweg ist keine Loesung.
2. **Vor jedem DSLR-Build:** `python tests/alle_tests.py` — braucht keine
   Kamera und faengt die Fehlerklasse ab, die im August 2026 fuenfmal die
   Ursache war.

---

## Projektabgrenzung

Dieses Repo ist die **interne FexoBooth V2 / Live-Flotten-Software**. Es ist nicht der
Consumer-Fork und gehört bei normalen V2-Aufgaben nicht zu Backend-, Web-, Portal-,
Checkout- oder Lizenzierungsarbeiten.

Wenn Christian von `fexobooth-v2`, interner V2, Tablet-Logs, Nikon, Canon, Drucker,
Hotspot, Kundenmenü oder Live-Flotte spricht:
- nur dieses Repo bearbeiten, außer ein anderes Repo wird ausdrücklich genannt,
- keine Consumer-/Backend-/Web-Repos als Pflichtkontext einbeziehen,
- keinen Consumer-Folgeprompt ausgeben,
- am Ende nur kurz V2-Dateien, Checks und echte Hardware-/Tablet-Blocker nennen.

---

## Pflichtanweisungen

### Bei jedem relevanten Prompt:

1. **Dokumentation lesen** - Lies die relevanten Projektdateien:
   - `ROADMAP.md` - Anforderungen und Ziele
   - `FORTSCHRITT.md` - Was wurde bereits gemacht?
   - `ERKENNTNISSE.md` - Lessons Learned und Tech-Entscheidungen
   - `TODO.md` - Offene Aufgaben

2. **Dokumentation pflegen** - Aktualisiere selbstständig ohne Aufforderung:
   - `FORTSCHRITT.md` - Nach jeder abgeschlossenen Änderung
   - `ERKENNTNISSE.md` - Bei neuen Erkenntnissen oder Tech-Entscheidungen
   - `TODO.md` - Aufgaben hinzufügen/abhaken
   - `CHANGELOG.md` - Für Release-relevante Änderungen
   - `support/HOTLINE_PROMPT_FELIX.md` - Steuert die Telefon-KI „Felix". **Muss bei jeder Änderung an Status-Anzeigen (`src/app.py` Top-Bar), Drucker-Fehlertexten (`src/ui/dialogs/printer_error.py`) oder am Kunden-Menü PIN 2015 (`src/ui/screens/admin.py`) geprüft und angepasst werden.** Sonst gibt Felix dem Kunden falsche Anweisungen.

3. **Nach jedem neuen Build-Kandidaten: kurze Prüfanweisung ausgeben.** Sobald eine neue
   Versionsnummer gebaut werden kann, bekommt Christian eine **kurze, anfängerfreundliche
   Test-Checkliste** (max. ~6 Punkte): Was auf der Box tun, was dabei rauskommen soll
   (sichtbares Verhalten, kein Log-Jargon), und als letzter Punkt „Dev-Mode-Log an Claude".
   Nur die Punkte aufnehmen, die sich in DIESER Version geändert haben.

4. **Dev-Mode-Logging IMMER mitziehen** - Bei **jeder** Code-Änderung sofort das
   Dev-Mode-Logging erweitern (nicht erst, wenn etwas hakt) und neue Funktionen
   **zuerst im Dev-Mode** (`python src/main.py --dev`) testen.
   - Logger: `from src.utils.logging import get_logger` → `logger = get_logger(__name__)`
   - Logs landen nur im Dev-Mode in `logs/fexobooth_*.log` (Live-Betrieb: 0 Overhead)
   - Logge, **welcher Pfad/Wert wirklich genommen wurde** (das löst Feld-Bugs schnell)
   - **Vollständiger Pflicht-Ablauf:** siehe [ARBEITSWEISE.md](ARBEITSWEISE.md) → Kernprinzip 8

---

## Performance-Richtlinien (WICHTIG!)

Die Software läuft auf schwacher Hardware. **Jede Zeile Code muss ressourcenschonend sein!**

- Keine unnötigen Hintergrund-Tasks
- Bilder effizient verarbeiten (nicht alles im RAM halten)
- GUI-Updates sparsam (kein 60fps Rendering)
- Flask-Server ist okay (~20-30 MB RAM)
- Große Bibliotheken vermeiden wenn möglich
- Video max. 25 FPS

---

## Projekt-Struktur

```
fexobooth-v2/
├── src/
│   ├── app.py              # Hauptanwendung
│   ├── ui/                 # GUI-Komponenten (Screens, Theme)
│   ├── camera/             # Webcam + Canon DSLR Support
│   ├── printer/            # Canon SELPHY Steuerung (Reset, Dialog-Unterdrückung)
│   ├── storage/            # USB, Lokal, Booking, Statistik
│   ├── gallery/            # Flask Webserver + QR-Code
│   ├── templates/          # Template-Loader
│   └── config/             # Konfiguration
├── setup/                  # Setup-Scripts (Hotspot, Tablet)
├── assets/                 # Icons, Templates, Videos
└── BILDER/                 # Ausgabe (Prints, Singles)
```

---

## Mehrsprachigkeit – Geräte-Touchscreen (Pflegepflicht)

Die Touchscreen-Texte des Geräts laufen über `src/i18n.py`. Das `locale`-Feld kommt vom Dashboard via `settings.json` (`NxSettingsJsonService::localeForCountry` in `adminFexobox`) – **beide Seiten** müssen für ein neues Land/eine neue Sprache gepflegt werden. Aktiv: **DE, FR**.

**Bei jedem neuen sichtbaren Gerät-String automatisch (ohne Aufforderung):**
1. In `src/i18n.py` für **alle** Sprachen ergänzen.
2. Im **repo-übergreifenden** Übersetzungs-Inventar vermerken: [`../fexobox-next/docs/MULTILINGUAL-UEBERSETZUNGS-PROMPT.md`](../fexobox-next/docs/MULTILINGUAL-UEBERSETZUNGS-PROMPT.md) → **Abschnitt 0.000** (Fläche „Gerät/Touchscreen") + Detail-Mechanik in **Abschnitt 3.4 L**. So vergisst ein „Übersetze alles auf {Sprache}"-Run das Gerät nicht.

## Verwandte Dokumentation

- [README.md](README.md) - Projekt-Übersicht und Architektur
- [BUILD.md](BUILD.md) - Build & Installation Guide
- [CHANGELOG.md](CHANGELOG.md) - Release-Changelog
