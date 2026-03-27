"""Admin-Dialog - Modern und übersichtlich

Optimiert für Lenovo Miix 310 (1280x800)
- Automatisch Fenstermodus beim Öffnen
- Datei-Dialoge für Template/Logo-Pfade
- Slider mit Wertanzeige
- Drucker-Auswahl
- Kamera-Erkennung
"""

import customtkinter as ctk
from typing import Dict, Any, Optional, List
import os
import threading

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AdminDialog(ctk.CTkToplevel):
    """Moderner Admin-Einstellungen Dialog"""

    def __init__(self, parent, config: Dict[str, Any], kiosk_mode: bool = False):
        super().__init__(parent)

        self.title("⚙️ Admin-Einstellungen")
        self.configure(fg_color="#0a0a10")

        self.config_data = config.copy()
        self.result: Optional[Dict[str, Any]] = None
        self.is_authenticated = False
        self._open_service = False
        self.parent_window = parent
        self._kiosk_mode = kiosk_mode

        # Modal machen
        self.transient(parent)
        self.grab_set()

        # Ctrl+Shift+Q auch im Dialog abfangen (grab_set blockiert Root-Bindings!)
        self.bind("<Control-Shift-Q>", lambda e: self._emergency_quit_from_dialog())
        self.bind("<Control-Shift-q>", lambda e: self._emergency_quit_from_dialog())

        # Vollbild-Overlay für PIN-Dialog (garantiert zentriert)
        self.overrideredirect(True)

        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Ganzen Bildschirm überdecken - Inhalt wird darin zentriert
        self.geometry(f"{screen_w}x{screen_h}+0+0")

        # Dialog in den Vordergrund bringen
        self.lift()
        self.focus_force()

        # Escape zum Schließen (nur im Fenstermodus)
        if not kiosk_mode:
            self.bind("<Escape>", lambda e: self.destroy())

        # PIN-Abfrage zuerst
        self._show_pin_dialog()
    
    def _show_pin_dialog(self):
        """Zeigt PIN-Eingabe als zentriertes Overlay"""
        # Dunkler Fullscreen-Hintergrund (Overlay-Effekt)
        self.pin_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        self.pin_frame.pack(fill="both", expand=True)

        # Klick auf Hintergrund schließt Dialog
        self.pin_frame.bind("<Button-1>", lambda e: self.destroy())

        # Responsive Werte
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        btn_size = min(70, max(50, int(screen_h * 0.08)))
        btn_font_size = max(16, int(btn_size * 0.34))
        btn_pad = max(3, int(btn_size * 0.06))

        # Zentrierte Karte mit eigener Farbe
        card_w = min(380, int(screen_w * 0.75))
        card = ctk.CTkFrame(
            self.pin_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")
        # Klick auf Karte soll NICHT schließen
        card.bind("<Button-1>", lambda e: "break")

        # Schließen-Button oben rechts in der Karte
        close_btn = ctk.CTkButton(
            card,
            text="✕",
            width=32,
            height=32,
            font=("Segoe UI", 16, "bold"),
            fg_color="transparent",
            hover_color=COLORS["error"],
            text_color=COLORS["text_muted"],
            corner_radius=16,
            command=self.destroy
        )
        close_btn.pack(anchor="e", padx=(0, 8), pady=(8, 0))

        # Icon
        icon_size = max(28, min(44, int(screen_h * 0.05)))
        icon_label = ctk.CTkLabel(
            card,
            text="🔐",
            font=("Segoe UI Emoji", icon_size)
        )
        icon_label.pack(pady=(0, 4))

        # Titel
        ctk.CTkLabel(
            card,
            text="Admin-Zugang",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(0, 10))

        # PIN-Eingabe
        entry_h = max(38, min(48, int(screen_h * 0.055)))
        self.pin_entry = ctk.CTkEntry(
            card,
            show="●",
            width=min(220, int(card_w * 0.6)),
            height=entry_h,
            font=("Segoe UI", max(18, int(entry_h * 0.5))),
            justify="center",
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border_light"],
            corner_radius=SIZES["corner_radius"]
        )
        self.pin_entry.pack(pady=(5, 3))
        self.pin_entry.bind("<Return>", lambda e: self._check_pin())
        self.pin_entry.bind("<KeyRelease>", self._on_pin_key)
        self.pin_entry.focus()

        # Fehler-Label
        self.pin_error = ctk.CTkLabel(
            card,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"]
        )
        self.pin_error.pack(pady=2)

        # Numpad für Touch
        numpad_frame = ctk.CTkFrame(card, fg_color="transparent")
        numpad_frame.pack(pady=6)

        buttons = [
            ["1", "2", "3"],
            ["4", "5", "6"],
            ["7", "8", "9"],
            ["⌫", "0", "✓"]
        ]

        for row in buttons:
            row_frame = ctk.CTkFrame(numpad_frame, fg_color="transparent")
            row_frame.pack()

            for num in row:
                btn = ctk.CTkButton(
                    row_frame,
                    text=num,
                    width=btn_size,
                    height=btn_size,
                    font=("Segoe UI", btn_font_size),
                    fg_color=COLORS["bg_light"] if num.isdigit() else COLORS["bg_card"],
                    hover_color=COLORS["bg_card"] if num.isdigit() else COLORS["primary_dark"],
                    corner_radius=SIZES["corner_radius_small"],
                    command=lambda n=num: self._numpad_press(n)
                )
                btn.pack(side="left", padx=btn_pad, pady=btn_pad)

        # Abbrechen-Button
        ctk.CTkButton(
            card,
            text="Abbrechen",
            font=FONTS["small"],
            width=120,
            height=30,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self.destroy
        ).pack(pady=(6, 12))
    
    def _on_pin_key(self, event):
        """Auto-Check bei 4 Zeichen"""
        if len(self.pin_entry.get()) >= 4:
            self.after(100, self._check_pin)
    
    def _numpad_press(self, key: str):
        """Numpad-Taste gedrückt"""
        if key == "⌫":
            current = self.pin_entry.get()
            self.pin_entry.delete(0, "end")
            self.pin_entry.insert(0, current[:-1])
        elif key == "✓":
            self._check_pin()
        else:
            self.pin_entry.insert("end", key)
            # Auto-Check bei 4 Zeichen
            if len(self.pin_entry.get()) >= 4:
                self.after(100, self._check_pin)
    
    def _check_pin(self):
        """Prüft die PIN (Admin, Service, Kunden-Menü)"""
        entered = self.pin_entry.get()
        correct = self.config_data.get("admin_pin", "3198")

        # Kunden-PIN: Öffnet Kunden-Menü
        if entered == "2015":
            self.pin_frame.destroy()
            self._show_customer_menu()
            return

        # Service-PIN: Öffnet Service-Menü statt Admin
        from src.ui.screens.service import SERVICE_PIN
        if entered == SERVICE_PIN:
            self.is_authenticated = True
            self.pin_frame.destroy()
            self._open_service_menu()
            return

        if entered == correct:
            self.is_authenticated = True
            self.pin_frame.destroy()

            if self._kiosk_mode:
                # Im Kiosk-Modus: Settings als Fullscreen-Overlay anzeigen
                self._show_settings()
            else:
                # Im Fenstermodus: Normales Fenster
                self.overrideredirect(False)
                self.title("⚙️ Admin-Einstellungen")
                admin_width = 750
                admin_height = 550
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                x = (screen_w - admin_width) // 2
                y = (screen_h - admin_height) // 2
                self.geometry(f"{admin_width}x{admin_height}+{x}+{y}")
                self._show_settings()
        else:
            self.pin_entry.delete(0, "end")
            self.pin_error.configure(text="❌ Falsche PIN!")

            # Visueller Fehler-Effekt: Eingabefeld rot blinken
            self.pin_entry.configure(border_color=COLORS["error"])
            self.after(600, lambda: self.pin_entry.configure(
                border_color=COLORS["border_light"]
            ))
    
    def _show_customer_menu(self):
        """Zeigt das Kunden-Menü mit Service-Optionen"""
        menu_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        menu_frame.pack(fill="both", expand=True)

        # Zentrierte Karte
        screen_w = self.winfo_screenwidth()
        card_w = min(420, int(screen_w * 0.8))
        card = ctk.CTkFrame(
            menu_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Titel
        ctk.CTkLabel(
            card,
            text="🔧 Service-Menü",
            font=("Segoe UI", 22, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            card,
            text="Bitte wählen Sie eine Option:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 15))

        # Buttons-Container
        btn_container = ctk.CTkFrame(card, fg_color="transparent")
        btn_container.pack(fill="x", padx=25, pady=(0, 10))

        btn_style = {
            "font": ("Segoe UI", 16, "bold"),
            "width": card_w - 60,
            "height": 50,
            "corner_radius": 12,
            "anchor": "w",
        }

        # 1. Template-Auswahl
        ctk.CTkButton(
            btn_container,
            text="  📋  Template wählen",
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            command=lambda: self._customer_template_select(menu_frame),
            **btn_style
        ).pack(pady=4)

        # 2. Live-View Template Overlay ein/aus
        app = self.parent_window._photobooth_app if hasattr(self.parent_window, '_photobooth_app') else None
        overlay_on = self.config_data.get("liveview_template_overlay", True)
        overlay_text = "  👁  Live-View Overlay: EIN" if overlay_on else "  👁  Live-View Overlay: AUS"

        self._overlay_btn = ctk.CTkButton(
            btn_container,
            text=overlay_text,
            fg_color=COLORS["success"] if overlay_on else COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color="#ffffff" if overlay_on else COLORS["text_primary"],
            command=lambda: self._customer_toggle_overlay(),
            **btn_style
        )
        self._overlay_btn.pack(pady=4)

        # 3. Druckstau beheben
        ctk.CTkButton(
            btn_container,
            text="  🖨  Druckstau beheben",
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            command=lambda: self._customer_fix_paper_jam(menu_frame),
            **btn_style
        ).pack(pady=4)

        # 4. Neustart
        ctk.CTkButton(
            btn_container,
            text="  🔄  Windows Neustart",
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["warning"],
            text_color=COLORS["text_primary"],
            command=lambda: self._customer_restart(menu_frame),
            **btn_style
        ).pack(pady=4)

        # Schließen-Button
        ctk.CTkButton(
            card,
            text="Schließen",
            font=FONTS["body"],
            width=120, height=38,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self.destroy
        ).pack(pady=(5, 15))

    def _customer_toggle_overlay(self):
        """Toggle Live-View Template Overlay"""
        current = self.config_data.get("liveview_template_overlay", True)
        new_val = not current
        self.config_data["liveview_template_overlay"] = new_val

        # App-Config auch sofort aktualisieren
        app = self.parent_window._photobooth_app if hasattr(self.parent_window, '_photobooth_app') else None
        if app:
            app.config["liveview_template_overlay"] = new_val
            from src.config.config import save_config
            save_config(app.config)
            logger.info(f"Live-View Overlay {'aktiviert' if new_val else 'deaktiviert'}")

        # Button-Text aktualisieren
        if new_val:
            self._overlay_btn.configure(
                text="  👁  Live-View Overlay: EIN",
                fg_color=COLORS["success"],
                text_color="#ffffff"
            )
        else:
            self._overlay_btn.configure(
                text="  👁  Live-View Overlay: AUS",
                fg_color=COLORS["bg_light"],
                text_color=COLORS["text_primary"]
            )

    def _get_templates_dir(self) -> str:
        """Findet den Pfad zum templates-Ordner (Build + Entwicklung)"""
        import sys
        candidates = []
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, "assets", "templates"))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        candidates.append(os.path.join(project_root, "assets", "templates"))
        for c in candidates:
            if os.path.isdir(c):
                return c
        return ""

    def _get_template_preview(self, zip_path: str, thumb_size=(140, 95)) -> "ctk.CTkImage | None":
        """Extrahiert ein Vorschau-Bild aus einer Template-ZIP"""
        import zipfile
        from PIL import Image
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                png_files = [n for n in zf.namelist() if n.lower().endswith(".png")]
                if not png_files:
                    return None
                # template.png bevorzugen, sonst erstes PNG
                target = next((n for n in png_files if "template" in n.lower()), png_files[0])
                with zf.open(target) as f:
                    img = Image.open(f)
                    img.load()
                    img.thumbnail(thumb_size, Image.Resampling.BILINEAR)
                    return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception as e:
            logger.debug(f"Template-Preview fehlgeschlagen für {zip_path}: {e}")
            return None

    def _customer_template_select(self, parent_frame):
        """Zeigt Template-Auswahl als Touch-Grid ohne Scrollen"""
        parent_frame.destroy()

        select_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        select_frame.pack(fill="both", expand=True)

        # Titel
        ctk.CTkLabel(
            select_frame,
            text="Template wählen",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(12, 8))

        app = self.parent_window._photobooth_app if hasattr(self.parent_window, '_photobooth_app') else None
        current_path = self.config_data.get("template_paths", {}).get("template1", "")
        # Auch aktuellen App-Pfad prüfen
        if app and hasattr(app, 'template_path') and app.template_path:
            current_path = current_path or app.template_path

        # Alle ZIPs sammeln
        templates_dir = self._get_templates_dir()
        all_templates = []  # (name, path, is_current)
        seen_basenames = set()

        # Default-Template.zip aus assets/ (falls vorhanden)
        import sys
        default_candidates = []
        if hasattr(sys, '_MEIPASS'):
            default_candidates.append(os.path.join(sys._MEIPASS, "assets", "Default-Template.zip"))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        default_candidates.append(os.path.join(project_root, "assets", "Default-Template.zip"))
        for c in default_candidates:
            if os.path.isfile(c):
                basename = os.path.basename(c)
                is_current = basename == os.path.basename(current_path) or "Default" in current_path
                all_templates.append(("Standard (4 Fotos)", c, is_current))
                seen_basenames.add(basename)
                break

        if templates_dir:
            try:
                for f in sorted(os.listdir(templates_dir)):
                    if f.lower().endswith(".zip") and "(DEFEKT)" not in f:
                        if f in seen_basenames:
                            continue
                        path = os.path.join(templates_dir, f)
                        display_name = f.replace(".zip", "").replace("-", " ").replace("_", " ")
                        is_current = os.path.basename(path) == os.path.basename(current_path)
                        all_templates.append((display_name, path, is_current))
                        seen_basenames.add(f)
            except OSError:
                pass

        # USB-Stick Template wenn vorhanden (Original vom Stick)
        if app and hasattr(app, '_usb_stick_template') and app._usb_stick_template:
            usb_name = app._usb_stick_template.get("name", "USB-Template")
            usb_path = app._usb_stick_template.get("path", "")
            if usb_path and os.path.isfile(usb_path) and usb_name not in seen_basenames:
                display = usb_name.replace(".zip", "").replace("-", " ").replace("_", " ")
                is_usb_current = os.path.basename(current_path) == usb_name
                all_templates.append((f"USB: {display}", usb_path, is_usb_current))
                seen_basenames.add(usb_name)

        # Preview-Cache
        self._template_previews = []

        # Grid-Layout berechnen (max 4 Spalten, passt sich an)
        count = len(all_templates)
        cols = min(4, count) if count > 0 else 1
        if count <= 3:
            cols = count
        elif count <= 6:
            cols = 3
        else:
            cols = 4

        # Grid-Container
        grid_frame = ctk.CTkFrame(select_frame, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        # Grid-Spalten gleichmäßig verteilen
        for c in range(cols):
            grid_frame.columnconfigure(c, weight=1)

        # Thumbnail-Größe an Anzahl anpassen
        if count <= 4:
            thumb_w, thumb_h = 180, 120
        elif count <= 6:
            thumb_w, thumb_h = 140, 95
        else:
            thumb_w, thumb_h = 110, 75

        def select_template(zip_path, name):
            """Template laden, übernehmen und als aktives Template setzen"""
            if app:
                from src.templates.loader import TemplateLoader
                TemplateLoader.clear_cache()
                overlay, boxes = TemplateLoader.load(zip_path, use_cache=True)
                if boxes:
                    # Aktives Template setzen
                    app.overlay_image = overlay
                    app.template_boxes = boxes
                    app.template_path = zip_path
                    app._cached_scaled_overlay = None

                    # Aktives Template setzen
                    app.cached_usb_template = {
                        "path": zip_path,
                        "name": os.path.basename(zip_path),
                        "overlay": overlay,
                        "boxes": boxes
                    }

                    # Prüfen ob das gewählte Template das USB-Stick-Template ist
                    usb_stick = getattr(app, '_usb_stick_template', None)
                    if usb_stick and usb_stick.get("path") == zip_path:
                        # User wählt USB-Template zurück → Override aufheben
                        app._user_template_override = False
                        logger.info(f"Kunden-Menü: USB-Template '{name}' wiederhergestellt")
                    else:
                        # User wählt anderes Template → Override setzen
                        app._user_template_override = True
                        logger.info(f"Kunden-Menü: Template '{name}' überschreibt USB-Template")

                    # Config speichern damit Template nach Neustart erhalten bleibt
                    if "template_paths" not in self.config_data:
                        self.config_data["template_paths"] = {}
                    self.config_data["template_paths"]["template1"] = zip_path
                    self.config_data["template1_enabled"] = True
                    from src.config.config import save_config
                    save_config(self.config_data)
                    logger.info(f"Kunden-Menü: Template '{name}' gespeichert: {zip_path}")
                else:
                    logger.error(f"Template '{name}' konnte nicht geladen werden")
            self.destroy()

        def _bind_click_recursive(widget, callback):
            """Bindet Click-Event auf Widget UND alle Kind-Widgets (auch CTk-interne Canvas)"""
            widget.bind("<Button-1>", callback)
            for child in widget.winfo_children():
                _bind_click_recursive(child, callback)

        for idx, (name, path, is_current) in enumerate(all_templates):
            row = idx // cols
            col = idx % cols

            # Kachel als CTkButton für zuverlässigen Touch
            tile = ctk.CTkFrame(
                grid_frame,
                fg_color=COLORS["bg_light"] if is_current else COLORS["bg_card"],
                corner_radius=12,
                border_width=3 if is_current else 1,
                border_color=COLORS["primary"] if is_current else COLORS["border"],
            )
            tile.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            grid_frame.rowconfigure(row, weight=1)

            # Preview-Bild
            preview = self._get_template_preview(path, thumb_size=(thumb_w, thumb_h))
            if preview:
                self._template_previews.append(preview)
                img_label = ctk.CTkLabel(tile, text="", image=preview)
                img_label.pack(pady=(8, 4), padx=8)

            # Name
            label_text = f"✓ {name}" if is_current else name
            name_label = ctk.CTkLabel(
                tile,
                text=label_text,
                font=("Segoe UI", 12, "bold"),
                text_color=COLORS["primary"] if is_current else COLORS["text_primary"],
                wraplength=thumb_w + 20,
            )
            name_label.pack(pady=(0, 8), padx=6)

            # Klick auf ALLE Elemente der Kachel (auch interne Canvas-Widgets von CTk)
            click_handler = lambda e, p=path, n=name: select_template(p, n)
            self.after(50, lambda t=tile, h=click_handler: _bind_click_recursive(t, h))

        # Zurück-Button
        ctk.CTkButton(
            select_frame,
            text="← Zurück",
            font=FONTS["body"],
            width=120, height=38,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=lambda: self._customer_back_to_menu(select_frame)
        ).pack(pady=(4, 12))

    def _customer_fix_paper_jam(self, parent_frame):
        """Druckstau beheben - Drucker zurücksetzen"""
        parent_frame.destroy()

        status_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        status_frame.pack(fill="both", expand=True)

        card = ctk.CTkFrame(
            status_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            card,
            text="🖨 Druckstau beheben",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(20, 10))

        status_label = ctk.CTkLabel(
            card,
            text="Drucker wird zurückgesetzt...",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            wraplength=300
        )
        status_label.pack(pady=(0, 20), padx=25)

        def do_fix():
            import subprocess
            try:
                # Druckerwarteschlange leeren
                subprocess.run(["net", "stop", "spooler"], capture_output=True, timeout=10,
                               creationflags=0x08000000)
                subprocess.run(["net", "start", "spooler"], capture_output=True, timeout=10,
                               creationflags=0x08000000)
                self.after(0, lambda: status_label.configure(
                    text="✅ Drucker wurde zurückgesetzt!\n\nBitte Papier prüfen und\nggf. Drucker aus-/einschalten.",
                    text_color=COLORS["success"]
                ))
                logger.info("Kunden-Menü: Druckstau behoben (Spooler neugestartet)")
            except Exception as e:
                self.after(0, lambda: status_label.configure(
                    text=f"❌ Fehler: {e}\n\nBitte Drucker manuell\naus- und einschalten.",
                    text_color=COLORS["error"]
                ))
                logger.error(f"Druckstau-Fix fehlgeschlagen: {e}")

        threading.Thread(target=do_fix, daemon=True).start()

        ctk.CTkButton(
            card,
            text="Schließen",
            font=FONTS["body"],
            width=120, height=38,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self.destroy
        ).pack(pady=(5, 15))

    def _customer_restart(self, parent_frame):
        """Windows Neustart mit Bestätigung und Wartehinweis"""
        parent_frame.destroy()

        confirm_frame = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
        confirm_frame.pack(fill="both", expand=True)

        card = ctk.CTkFrame(
            confirm_frame,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=16
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            card,
            text="🔄 Windows Neustart",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["warning"]
        ).pack(pady=(20, 10))

        self._restart_status = ctk.CTkLabel(
            card,
            text="Der Computer wird neu gestartet.\nDies dauert ca. 1-2 Minuten.",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            justify="center",
            wraplength=300
        )
        self._restart_status.pack(pady=(0, 20), padx=25)

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(0, 15))

        def do_restart():
            import subprocess
            self._restart_status.configure(
                text="⏳ Computer wird neu gestartet...\n\nBitte warten Sie, bis das Gerät\nwieder hochgefahren ist.",
                text_color=COLORS["warning"]
            )
            btn_frame.destroy()
            logger.info("Kunden-Menü: Windows-Neustart ausgelöst")
            subprocess.Popen(
                ["shutdown", "/r", "/f", "/t", "5", "/c", "FexoBooth: Neustart über Kunden-Menü"],
                creationflags=0x08000000
            )

        ctk.CTkButton(
            btn_frame,
            text="Neustart",
            font=("Segoe UI", 16, "bold"),
            width=130, height=45,
            fg_color=COLORS["warning"],
            hover_color="#ff6600",
            corner_radius=12,
            command=do_restart
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            font=("Segoe UI", 16, "bold"),
            width=130, height=45,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            corner_radius=12,
            command=self.destroy
        ).pack(side="left", padx=8)

    def _customer_back_to_menu(self, current_frame):
        """Zurück zum Kunden-Hauptmenü"""
        current_frame.destroy()
        self._show_customer_menu()

    def _open_service_menu(self):
        """Markiert Service-Menü zum Öffnen und schließt den Admin-Dialog.

        Das Service-Menü wird NACH wait_window() in show_admin_dialog() geöffnet,
        damit kein Toplevel innerhalb eines zerstörten Dialogs erstellt wird.
        """
        self._open_service = True
        self.destroy()

    def _minimize_to_taskbar(self):
        """Minimiert den Admin-Dialog (nur im Kiosk-Modus)"""
        # Taskleiste kurz einblenden damit der Nutzer sie sieht
        app = getattr(self.parent_window, '_photobooth_app', None)
        if app:
            app._show_taskbar()
        self.iconify()
        # Wenn wieder hergestellt: Taskleiste wieder verstecken
        def on_deiconify(event=None):
            if app:
                app._hide_taskbar()
        self.bind("<Map>", on_deiconify)

    def _show_settings(self):
        """Zeigt Einstellungen - mit Lazy Loading für schnelleren Start"""
        if self._kiosk_mode:
            # Im Kiosk-Modus: zentriertes Panel mit Rand
            outer = ctk.CTkFrame(self, fg_color="#0a0a10", corner_radius=0)
            outer.pack(fill="both", expand=True)

            # Zentrierter Container mit Padding
            screen_w = self.winfo_screenwidth()
            pad_x = max(20, (screen_w - 780) // 2)

            main = ctk.CTkFrame(
                outer,
                fg_color=COLORS["bg_medium"],
                border_color=COLORS["border"],
                border_width=1,
                corner_radius=16
            )
            main.pack(fill="both", expand=True, padx=pad_x, pady=20)
        else:
            # Im Fenstermodus: wie bisher
            main = ctk.CTkFrame(self, fg_color="transparent")
            main.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Titel im Kiosk-Modus
        if self._kiosk_mode:
            ctk.CTkLabel(
                main,
                text="⚙️ Admin-Einstellungen",
                font=("Segoe UI", 20, "bold"),
                text_color=COLORS["text_primary"]
            ).pack(pady=(10, 5))

        # Tabview
        tab_height = 350 if self._kiosk_mode else 420
        self.tabview = ctk.CTkTabview(
            main,
            fg_color=COLORS["bg_dark"] if self._kiosk_mode else COLORS["bg_medium"],
            segmented_button_fg_color=COLORS["bg_light"],
            segmented_button_selected_color=COLORS["primary"],
            segmented_button_unselected_color=COLORS["bg_card"],
            height=tab_height,
            command=self._on_tab_changed  # Lazy Loading
        )
        self.tabview.pack(fill="both", expand=True, padx=10 if self._kiosk_mode else 0)
        
        # Tab-Namen und ihre Erstellungsfunktionen
        self._tab_creators = {
            "Allgemein": self._create_general_tab,
            "Templates": self._create_templates_tab,
            "Druck": self._create_print_tab,
            "Kamera": self._create_camera_tab,
            "Galerie": self._create_gallery_tab,
            "Videos": self._create_videos_tab,
            "Statistik": self._create_statistics_tab,
        }
        self._tabs_created = set()
        
        # Alle Tabs hinzufügen (leer)
        for tab_name in self._tab_creators.keys():
            self.tabview.add(tab_name)
        
        # Nur ersten Tab sofort erstellen
        self._create_tab_content("Allgemein")
        
        # Button-Leiste
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 0))

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            font=FONTS["small"],
            width=120,
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self._cancel
        ).pack(side="left")

        # Beenden-Button (App komplett schließen)
        ctk.CTkButton(
            btn_frame,
            text="App beenden",
            font=FONTS["small"],
            width=120,
            height=40,
            fg_color="#cc0000",
            hover_color="#990000",
            text_color="#ffffff",
            corner_radius=SIZES["corner_radius"],
            command=self._quit_app
        ).pack(side="left", padx=(15, 0))

        # Minimieren-Button (nur im Kiosk-Modus)
        if self._kiosk_mode:
            ctk.CTkButton(
                btn_frame,
                text="Minimieren",
                font=FONTS["small"],
                width=120,
                height=40,
                fg_color=COLORS["bg_card"],
                hover_color=COLORS["bg_light"],
                text_color=COLORS["text_primary"],
                corner_radius=SIZES["corner_radius"],
                command=self._minimize_to_taskbar
            ).pack(side="left", padx=(15, 0))

        ctk.CTkButton(
            btn_frame,
            text="💾 Speichern",
            font=FONTS["button"],
            width=160,
            height=40,
            fg_color=COLORS["success"],
            hover_color="#00e676",
            corner_radius=SIZES["corner_radius"],
            command=self._save
        ).pack(side="right")
    
    def _on_tab_changed(self):
        """Callback wenn Tab gewechselt wird - Lazy Loading"""
        current_tab = self.tabview.get()
        self._create_tab_content(current_tab)
    
    def _create_tab_content(self, tab_name: str):
        """Erstellt Tab-Inhalt nur wenn noch nicht erstellt"""
        if tab_name in self._tabs_created:
            return  # Schon erstellt
        
        if tab_name in self._tab_creators:
            creator = self._tab_creators[tab_name]
            tab_frame = self.tabview.tab(tab_name)
            creator(tab_frame)
            self._tabs_created.add(tab_name)
            logger.debug(f"Tab '{tab_name}' erstellt (lazy)")
    
    def _create_slider_with_value(self, parent, label: str, key: str, 
                                   min_val: int, max_val: int, suffix: str = "") -> ctk.CTkSlider:
        """Erstellt einen Slider MIT Wertanzeige"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=8)
        
        # Label und Wert in einer Zeile
        label_frame = ctk.CTkFrame(frame, fg_color="transparent")
        label_frame.pack(fill="x")
        
        ctk.CTkLabel(
            label_frame,
            text=label,
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        # Wert-Anzeige (mit Padding rechts damit nicht am Rand klebt)
        value_label = ctk.CTkLabel(
            label_frame,
            text=f"{self.config_data.get(key, min_val)}{suffix}",
            font=FONTS["body_bold"],
            text_color=COLORS["primary"]
        )
        value_label.pack(side="right", padx=(0, 15))
        
        # Slider
        slider = ctk.CTkSlider(
            frame,
            from_=min_val,
            to=max_val,
            number_of_steps=max_val - min_val,
            width=280,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"]
        )
        slider.set(self.config_data.get(key, min_val))
        slider.pack(anchor="w", pady=(5, 0))
        
        # Update-Callback
        def update_value(val):
            value_label.configure(text=f"{int(val)}{suffix}")
        
        slider.configure(command=update_value)
        
        return slider
    
    def _create_general_tab(self, parent):
        """Allgemeine Einstellungen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Flash-Bild (beim Foto-Auslösen)
        ctk.CTkLabel(
            scroll,
            text="📸 Bild beim Foto-Auslösen:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(5, 2))
        
        self.flash_image_path = self._create_file_picker(
            scroll,
            "",
            self.config_data.get("flash_image", ""),
            [("Bilder", "*.png *.jpg *.jpeg *.gif")]
        )
        
        ctk.CTkLabel(
            scroll,
            text="Leer = Standard-Smiley 😊",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(0, 10))
        
        # Countdown
        self.countdown_slider = self._create_slider_with_value(
            scroll, "Countdown:", "countdown_time", 1, 15, " Sek"
        )
        
        # Foto-Anzeige
        self.single_slider = self._create_slider_with_value(
            scroll, "Foto-Anzeige:", "single_display_time", 1, 10, " Sek"
        )
        
        # Auto-Return
        self.final_slider = self._create_slider_with_value(
            scroll, "Auto-Return:", "final_time", 10, 60, " Sek"
        )
        
        # Auslöse-Bild (Flash) Dauer
        self.flash_slider = self._create_slider_with_value(
            scroll, "Auslöse-Bild:", "flash_duration", 100, 1000, " ms"
        )
        
        # Max Drucke
        self.prints_slider = self._create_slider_with_value(
            scroll, "Max. Drucke:", "max_prints_per_session", 0, 10, ""
        )
        
        # Checkboxen
        self._add_checkbox(scroll, "Single-Foto Modus erlauben", "allow_single_mode")
        self._add_checkbox(scroll, "Performance-Modus", "performance_mode")
        self._add_checkbox(scroll, "Vollbild beim Start", "start_fullscreen")
        self._add_checkbox(scroll, "Fertig-Button ausblenden", "hide_finish_button")
        self._add_checkbox(scroll, "Drucken aktivieren", "print_enabled")

        # Neue PIN
        pin_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pin_frame.pack(fill="x", pady=(15, 5))
        
        ctk.CTkLabel(
            pin_frame,
            text="Neue Admin-PIN:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        self.new_pin = ctk.CTkEntry(
            pin_frame,
            placeholder_text="4-stellig",
            width=100,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
        self.new_pin.pack(side="right")
    
    def _create_templates_tab(self, parent):
        """Template-Einstellungen mit Datei-Dialogen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Template 1
        self._add_checkbox(scroll, "Template 1 aktivieren", "template1_enabled")
        self.t1_path = self._create_file_picker(
            scroll, 
            "Template 1 (ZIP):",
            self.config_data.get("template_paths", {}).get("template1", ""),
            [("ZIP-Templates", "*.zip")]
        )
        
        # Template 2
        self._add_checkbox(scroll, "Template 2 aktivieren", "template2_enabled")
        self.t2_path = self._create_file_picker(
            scroll,
            "Template 2 (ZIP):",
            self.config_data.get("template_paths", {}).get("template2", ""),
            [("ZIP-Templates", "*.zip")]
        )
        
        # Logo
        ctk.CTkLabel(
            scroll,
            text="",
            font=FONTS["tiny"]
        ).pack()  # Spacer
        
        self.logo_path = self._create_file_picker(
            scroll,
            "Logo:",
            self.config_data.get("logo_path", ""),
            [("Bilder", "*.png *.jpg *.jpeg")]
        )

    def _create_file_picker(self, parent, label: str, initial_value: str, 
                            filetypes: List[tuple]) -> ctk.CTkEntry:
        """Erstellt ein Eingabefeld mit Datei-Dialog"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        ).pack(anchor="w")
        
        input_frame = ctk.CTkFrame(frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=(2, 0))
        
        entry = ctk.CTkEntry(
            input_frame,
            width=320,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
        entry.insert(0, initial_value)
        entry.pack(side="left")
        
        def browse():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title=f"Wähle {label}",
                filetypes=filetypes + [("Alle Dateien", "*.*")]
            )
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)
        
        ctk.CTkButton(
            input_frame,
            text="📁",
            width=40,
            height=32,
            font=("Segoe UI", 14),
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["primary"],
            command=browse
        ).pack(side="left", padx=(5, 0))
        
        return entry
    
    def _create_print_tab(self, parent):
        """Druck-Einstellungen mit Drucker-Auswahl"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Drucker-Auswahl
        ctk.CTkLabel(
            scroll,
            text="Drucker:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(5, 5))
        
        # Verfügbare Drucker ermitteln
        printers = self._get_available_printers()
        current_printer = self.config_data.get("printer_name", "")
        
        self.printer_dropdown = ctk.CTkOptionMenu(
            scroll,
            values=printers if printers else ["(Kein Drucker gefunden)"],
            width=300,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"]
        )
        if current_printer and current_printer in printers:
            self.printer_dropdown.set(current_printer)
        elif printers:
            self.printer_dropdown.set(printers[0])
        self.printer_dropdown.pack(anchor="w", pady=(0, 15))
        
        # Druck-Vorschau Frame
        preview_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        preview_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            preview_frame,
            text="📄 Druck-Anpassung",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))
        
        # Offset-Werte mit Anzeige und Hinweisen
        adjustment = self.config_data.get("print_adjustment", {})

        # Offset X
        self.offset_x_slider = self._create_print_slider(
            preview_frame, "Offset X:", adjustment.get("offset_x", 0), -100, 100, " px"
        )
        ctk.CTkLabel(
            preview_frame,
            text="← minus = links  |  plus = rechts →",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(padx=15, anchor="w")

        # Offset Y
        self.offset_y_slider = self._create_print_slider(
            preview_frame, "Offset Y:", adjustment.get("offset_y", 0), -100, 100, " px"
        )
        ctk.CTkLabel(
            preview_frame,
            text="↑ minus = hoch  |  plus = runter ↓",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(padx=15, anchor="w")

        # Zoom
        self.zoom_slider = self._create_print_slider(
            preview_frame, "Zoom:", adjustment.get("zoom", 100), 50, 150, " %"
        )
        ctk.CTkLabel(
            preview_frame,
            text="103% empfohlen für randlosen Druck",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(padx=15, anchor="w")

        ctk.CTkLabel(preview_frame, text="").pack(pady=3)  # Spacer

        # Testdruck-Button
        test_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        test_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            test_frame,
            text="🧪 Testdruck",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            test_frame,
            text="Druckt das aktuelle Template mit Platzhalter-Bildern.\nBenötigt keine Fotos.",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 8))

        self._test_print_status = ctk.CTkLabel(
            test_frame, text="", font=FONTS["tiny"], text_color=COLORS["text_muted"]
        )
        self._test_print_status.pack()

        ctk.CTkButton(
            test_frame,
            text="Testdruck starten",
            font=FONTS["button"],
            width=200,
            height=40,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            corner_radius=SIZES["corner_radius"],
            command=self._execute_test_print
        ).pack(pady=(5, 12))

    def _execute_test_print(self):
        """Führt einen Testdruck mit Platzhalter-Bildern aus"""
        self._test_print_status.configure(
            text="Testdruck wird vorbereitet...", text_color=COLORS["info"]
        )
        self.update_idletasks()

        def do_print():
            try:
                from PIL import Image, ImageDraw, ImageFont
                from src.templates.renderer import TemplateRenderer
                from src.templates.loader import TemplateLoader
                import tempfile
                from pathlib import Path

                # Template laden (aktives Template oder Default)
                app = self.parent_window._photobooth_app if hasattr(self.parent_window, '_photobooth_app') else None
                template_path = None
                overlay = None
                boxes = []

                # 1. Aktives Template aus der App
                if app and hasattr(app, 'template_path') and app.template_path:
                    template_path = app.template_path
                # 2. Config-Template
                if not template_path:
                    paths = self.config_data.get("template_paths", {})
                    template_path = paths.get("template1", "")

                if template_path and os.path.isfile(template_path):
                    overlay, boxes = TemplateLoader.load(template_path, use_cache=False)

                if not boxes:
                    # Fallback: Default-Template
                    from src.templates.default import get_default_template_path
                    default_path = get_default_template_path()
                    if default_path:
                        overlay, boxes = TemplateLoader.load(default_path, use_cache=False)

                if not boxes:
                    self.after(0, lambda: self._test_print_status.configure(
                        text="Kein Template gefunden!", text_color=COLORS["error"]
                    ))
                    return

                # Platzhalter-Bilder erzeugen (grau mit "TEST" Text)
                test_photos = []
                colors = ["#4a90d9", "#d94a4a", "#4ad98a", "#d9c74a", "#9b4ad9", "#d97a4a"]
                for i in range(len(boxes)):
                    box = boxes[i]["box"]
                    w = box[2] - box[0]
                    h = box[3] - box[1]
                    img = Image.new("RGB", (w, h), colors[i % len(colors)])
                    draw = ImageDraw.Draw(img)
                    # "TEST" Text zentriert zeichnen
                    text = f"TEST {i+1}"
                    try:
                        font = ImageFont.truetype("segoeui.ttf", max(30, h // 6))
                    except Exception:
                        font = ImageFont.load_default()
                    bbox = draw.textbbox((0, 0), text, font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    draw.text(((w - tw) // 2, (h - th) // 2), text, fill="white", font=font)
                    test_photos.append(img)

                # Template rendern
                renderer = TemplateRenderer()
                result = renderer.render(test_photos, boxes, overlay)

                # Temporär speichern
                temp_path = Path(tempfile.gettempdir()) / "fexobooth_testprint.jpg"
                result_rgb = result.convert("RGB")
                result_rgb.save(str(temp_path), "JPEG", quality=95)

                self.after(0, lambda: self._test_print_status.configure(
                    text="Wird gedruckt...", text_color=COLORS["info"]
                ))

                # GDI-Druck (gleiche Logik wie final.py)
                import win32print
                import win32ui
                from PIL import ImageWin

                # Drucker-Name: aktueller Wert aus Dropdown
                printer_name = self.printer_dropdown.get() if hasattr(self, 'printer_dropdown') else ""
                if printer_name.startswith("⭐ "):
                    printer_name = printer_name[2:].replace(" (Standard)", "")
                if not printer_name:
                    printer_name = win32print.GetDefaultPrinter()

                available = [p[2] for p in win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )]
                if printer_name not in available:
                    self.after(0, lambda: self._test_print_status.configure(
                        text=f"Drucker '{printer_name}' nicht gefunden!",
                        text_color=COLORS["error"]
                    ))
                    return

                adjustment = self.config_data.get("print_adjustment", {})
                offset_x = adjustment.get("offset_x", 0)
                offset_y = adjustment.get("offset_y", 0)
                zoom = adjustment.get("zoom", 100) / 100

                img = Image.open(temp_path)
                base_width = int(1772 * zoom)
                base_height = int(1181 * zoom)

                img_ratio = img.width / img.height
                target_ratio = base_width / base_height
                if img_ratio > target_ratio:
                    new_h = base_height
                    new_w = int(new_h * img_ratio)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - base_width) // 2
                    img = img.crop((left, 0, left + base_width, base_height))
                else:
                    new_w = base_width
                    new_h = int(new_w / img_ratio)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    top = (new_h - base_height) // 2
                    img = img.crop((0, top, base_width, top + base_height))

                # Zoom zentriert
                center_offset_x = -int((1772 * (zoom - 1)) / 2)
                center_offset_y = -int((1181 * (zoom - 1)) / 2)
                draw_x = offset_x + center_offset_x
                draw_y = offset_y + center_offset_y

                hDC = win32ui.CreateDC()
                hDC.CreatePrinterDC(printer_name)
                hDC.StartDoc("Fexobooth Testdruck")
                hDC.StartPage()
                dib = ImageWin.Dib(img)
                dib.draw(hDC.GetHandleOutput(),
                         (draw_x, draw_y, draw_x + base_width, draw_y + base_height))
                hDC.EndPage()
                hDC.EndDoc()
                hDC.DeleteDC()

                # Aufräumen
                try:
                    temp_path.unlink()
                except Exception:
                    pass

                # Lifetime-Zähler hochzählen
                from src.storage.printer_lifetime import get_printer_lifetime
                get_printer_lifetime().increment()

                self.after(0, lambda: self._test_print_status.configure(
                    text=f"Testdruck gesendet an '{printer_name}'",
                    text_color=COLORS["success"]
                ))
                logger.info(f"Testdruck gesendet an '{printer_name}'")

            except ImportError as e:
                self.after(0, lambda: self._test_print_status.configure(
                    text="Druck nur unter Windows verfügbar",
                    text_color=COLORS["warning"]
                ))
            except Exception as e:
                logger.error(f"Testdruck Fehler: {e}")
                import traceback
                logger.error(traceback.format_exc())
                msg = str(e)
                if "1801" in msg:
                    msg = "Drucker nicht erreichbar!"
                elif "offline" in msg.lower():
                    msg = "Drucker ist offline!"
                self.after(0, lambda m=msg: self._test_print_status.configure(
                    text=f"Fehler: {m}", text_color=COLORS["error"]
                ))

        thread = threading.Thread(target=do_print, daemon=True)
        thread.start()

    def _create_print_slider(self, parent, label: str, value: int,
                              min_val: int, max_val: int, suffix: str) -> ctk.CTkSlider:
        """Slider für Druck-Einstellungen mit Wertanzeige"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=15, pady=5)
        
        label_frame = ctk.CTkFrame(frame, fg_color="transparent")
        label_frame.pack(fill="x")
        
        ctk.CTkLabel(
            label_frame,
            text=label,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        value_label = ctk.CTkLabel(
            label_frame,
            text=f"{value}{suffix}",
            font=FONTS["body_bold"],
            text_color=COLORS["primary"]
        )
        value_label.pack(side="right")
        
        slider = ctk.CTkSlider(
            frame,
            from_=min_val,
            to=max_val,
            number_of_steps=max_val - min_val,
            width=250,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["primary"]
        )
        slider.set(value)
        slider.pack(anchor="w", pady=(3, 0))
        
        slider.configure(command=lambda v: value_label.configure(text=f"{int(v)}{suffix}"))
        
        return slider
    
    def _get_available_printers(self) -> List[str]:
        """Ermittelt verfügbare Drucker"""
        printers = []
        try:
            import win32print
            printer_list = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            printers = [p[2] for p in printer_list]
            
            # Standard-Drucker zuerst
            try:
                default = win32print.GetDefaultPrinter()
                if default in printers:
                    printers.remove(default)
                    printers.insert(0, f"⭐ {default} (Standard)")
            except:
                pass
                
        except ImportError:
            printers = ["(win32print nicht verfügbar)"]
        except Exception as e:
            logger.warning(f"Drucker-Liste Fehler: {e}")
            printers = ["(Fehler beim Laden)"]
        
        return printers
    
    def _create_camera_tab(self, parent):
        """Kamera-Einstellungen mit automatischer Erkennung"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Kamera-Typ Auswahl (NEU!)
        ctk.CTkLabel(
            scroll,
            text="Kamera-Typ:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(5, 5))
        
        # Prüfen ob Canon EDSDK verfügbar ist
        try:
            from src.camera import CANON_AVAILABLE
        except:
            CANON_AVAILABLE = False
        
        camera_types = ["webcam"]
        if CANON_AVAILABLE:
            camera_types.append("canon")
        
        current_type = self.config_data.get("camera_type", "webcam")
        
        self.camera_type_dropdown = ctk.CTkOptionMenu(
            scroll,
            values=camera_types,
            width=350,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            command=self._on_camera_type_change
        )
        self.camera_type_dropdown.set(current_type)
        self.camera_type_dropdown.pack(anchor="w", pady=(0, 10))
        
        if not CANON_AVAILABLE:
            ctk.CTkLabel(
                scroll,
                text="⚠️ Canon EDSDK nicht verfügbar (DLLs fehlen?)",
                font=FONTS["tiny"],
                text_color=COLORS["warning"]
            ).pack(anchor="w", pady=(0, 10))
        
        # Kamera-Auswahl
        ctk.CTkLabel(
            scroll,
            text="Kamera:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(5, 5))
        
        # Verfügbare Kameras ermitteln
        cameras = self._get_available_cameras()
        current_index = self.config_data.get("camera_index", 0)
        
        self.camera_dropdown = ctk.CTkOptionMenu(
            scroll,
            values=cameras if cameras else ["(Keine Kamera gefunden)"],
            width=350,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"]
        )
        
        # Aktuelle Kamera setzen
        for cam in cameras:
            if cam.startswith(f"[{current_index}]"):
                self.camera_dropdown.set(cam)
                break
        
        self.camera_dropdown.pack(anchor="w", pady=(0, 10))
        
        # Refresh-Button
        ctk.CTkButton(
            scroll,
            text="🔄 Kameras neu suchen",
            font=FONTS["small"],
            width=150,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["primary"],
            command=self._refresh_cameras
        ).pack(anchor="w", pady=(0, 20))
        
        # Bild um 180° drehen (für kopfüber montierte Kameras)
        self._add_checkbox(scroll, "Bild um 180° drehen", "rotate_180")

        # Template-Overlay im LiveView
        self._add_checkbox(scroll, "Template im LiveView anzeigen", "liveview_template_overlay")
        
        # Auflösung
        cam_settings = self.config_data.get("camera_settings", {})
        
        res_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        res_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            res_frame,
            text="📷 Foto-Auflösung",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 10))
        
        size_frame = ctk.CTkFrame(res_frame, fg_color="transparent")
        size_frame.pack(pady=(0, 10))
        
        ctk.CTkLabel(size_frame, text="Breite:", font=FONTS["small"], 
                     text_color=COLORS["text_muted"]).pack(side="left", padx=(10, 5))
        
        self.photo_width = ctk.CTkEntry(
            size_frame, width=80,
            fg_color=COLORS["bg_light"], border_color=COLORS["border"]
        )
        self.photo_width.insert(0, str(cam_settings.get("single_photo_width", 1920)))
        self.photo_width.pack(side="left")
        
        ctk.CTkLabel(size_frame, text="  Höhe:", font=FONTS["small"],
                     text_color=COLORS["text_muted"]).pack(side="left", padx=(10, 5))
        
        self.photo_height = ctk.CTkEntry(
            size_frame, width=80,
            fg_color=COLORS["bg_light"], border_color=COLORS["border"]
        )
        self.photo_height.insert(0, str(cam_settings.get("single_photo_height", 1080)))
        self.photo_height.pack(side="left")

        # Info-Hinweis zur Auflösung
        ctk.CTkLabel(
            res_frame,
            text="Live-Preview: 640x480 (Performance)\nFotos: Obige Einstellung (Full HD)",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(5, 10))

    def _get_available_cameras(self) -> List[str]:
        """Ermittelt verfügbare Kameras mit echten Gerätenamen"""
        cameras = []

        # Prüfen welcher Kamera-Typ ausgewählt ist
        camera_type = "webcam"
        if hasattr(self, 'camera_type_dropdown'):
            camera_type = self.camera_type_dropdown.get()
        else:
            camera_type = self.config_data.get("camera_type", "webcam")

        if camera_type == "canon":
            # Canon Kameras via EDSDK
            try:
                from src.camera.canon import CanonCameraManager
                canon_cams = CanonCameraManager.list_cameras()
                for cam in canon_cams:
                    cameras.append(f"[{cam['index']}] 📷 {cam['name']}")
                logger.info(f"Canon Kameras gefunden: {len(canon_cams)}")
            except Exception as e:
                logger.warning(f"Canon Kamera-Suche Fehler: {e}")
        else:
            # Webcams via OpenCV + echte Gerätenamen
            try:
                from src.camera.webcam import WebcamManager
                webcams = WebcamManager.list_cameras()
                for cam in webcams:
                    name = cam.get("name", f"Kamera {cam['index']}")
                    w = cam.get("width", 0)
                    h = cam.get("height", 0)
                    cameras.append(f"[{cam['index']}] {name} ({w}x{h})")
                logger.info(f"Webcams gefunden: {len(webcams)}")
            except Exception as e:
                logger.warning(f"Webcam-Suche Fehler: {e}")

        if not cameras:
            cameras = ["[0] Standard-Kamera"]

        return cameras
    
    def _on_camera_type_change(self, choice):
        """Wird aufgerufen wenn Kamera-Typ gewechselt wird"""
        logger.info(f"Kamera-Typ gewechselt: {choice}")
        self._refresh_cameras()
    
    def _refresh_cameras(self):
        """Aktualisiert die Kamera-Liste"""
        cameras = self._get_available_cameras()
        self.camera_dropdown.configure(values=cameras)
        if cameras:
            self.camera_dropdown.set(cameras[0])
    
    def _add_checkbox(self, parent, label: str, key: str):
        """Fügt eine Checkbox hinzu"""
        var = ctk.BooleanVar(value=self.config_data.get(key, False))
        
        cb = ctk.CTkCheckBox(
            parent, text=label, variable=var,
            font=FONTS["small"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            checkbox_width=22,
            checkbox_height=22
        )
        cb.pack(anchor="w", pady=4)
        setattr(self, f"check_{key}", var)
    
    def _create_gallery_tab(self, parent):
        """Galerie/Webserver-Einstellungen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Galerie aktivieren
        self._add_checkbox(scroll, "Galerie aktivieren (QR-Code)", "gallery_enabled")
        
        # Info-Box
        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        info_frame.pack(fill="x", pady=(15, 10))
        
        ctk.CTkLabel(
            info_frame,
            text="📱 So funktioniert's",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))
        
        ctk.CTkLabel(
            info_frame,
            text="Gäste verbinden sich mit dem WLAN-Hotspot\nund scannen den QR-Code auf dem Startbildschirm.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 10))
        
        # Hotspot-Einstellungen
        hotspot_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        hotspot_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            hotspot_frame,
            text="📶 Hotspot-Einstellungen",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 10))
        
        # SSID
        ssid_frame = ctk.CTkFrame(hotspot_frame, fg_color="transparent")
        ssid_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            ssid_frame,
            text="WLAN-Name (SSID):",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        gallery_config = self.config_data.get("gallery", {})
        
        self.gallery_ssid = ctk.CTkEntry(
            ssid_frame,
            width=180,
            fg_color=COLORS["bg_light"],
            border_color=COLORS["border"]
        )
        self.gallery_ssid.insert(0, gallery_config.get("hotspot_ssid", "fexobox-gallery"))
        self.gallery_ssid.pack(side="right")
        
        # Passwort
        pw_frame = ctk.CTkFrame(hotspot_frame, fg_color="transparent")
        pw_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            pw_frame,
            text="WLAN-Passwort:",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        self.gallery_password = ctk.CTkEntry(
            pw_frame,
            width=180,
            fg_color=COLORS["bg_light"],
            border_color=COLORS["border"]
        )
        self.gallery_password.insert(0, gallery_config.get("hotspot_password", "fotobox123"))
        self.gallery_password.pack(side="right")
        
        # Port
        port_frame = ctk.CTkFrame(hotspot_frame, fg_color="transparent")
        port_frame.pack(fill="x", padx=15, pady=(5, 15))
        
        ctk.CTkLabel(
            port_frame,
            text="Webserver-Port:",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        self.gallery_port = ctk.CTkEntry(
            port_frame,
            width=80,
            fg_color=COLORS["bg_light"],
            border_color=COLORS["border"]
        )
        self.gallery_port.insert(0, str(gallery_config.get("port", 8080)))
        self.gallery_port.pack(side="right")
        
        # Hinweis
        ctk.CTkLabel(
            scroll,
            text="⚠️ Hotspot muss einmalig via setup_hotspot.ps1 eingerichtet werden",
            font=FONTS["tiny"],
            text_color=COLORS["warning"]
        ).pack(pady=(10, 0))
    
    def _create_videos_tab(self, parent):
        """Video-Einstellungen für Session-Videos"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Info
        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            info_frame,
            text="🎬 Session-Videos",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))
        
        ctk.CTkLabel(
            info_frame,
            text="Videos werden zwischen den Fotos abgespielt.\nLeer lassen = Video wird übersprungen.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 10))
        
        # Start-Video
        ctk.CTkLabel(
            scroll,
            text="▶️ Start-Video (vor Session):",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 2))
        
        self.video_start_path = self._create_file_picker(
            scroll, "",
            self.config_data.get("video_start", ""),
            [("Videos", "*.mp4 *.avi *.mkv *.mov")]
        )
        
        # Video nach Foto 1
        ctk.CTkLabel(
            scroll,
            text="📷 Video nach Foto 1:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 2))
        
        self.video_after_1_path = self._create_file_picker(
            scroll, "",
            self.config_data.get("video_after_1", ""),
            [("Videos", "*.mp4 *.avi *.mkv *.mov")]
        )
        
        # Video nach Foto 2
        ctk.CTkLabel(
            scroll,
            text="📷 Video nach Foto 2:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 2))
        
        self.video_after_2_path = self._create_file_picker(
            scroll, "",
            self.config_data.get("video_after_2", ""),
            [("Videos", "*.mp4 *.avi *.mkv *.mov")]
        )
        
        # Video nach Foto 3
        ctk.CTkLabel(
            scroll,
            text="📷 Video nach Foto 3:",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 2))
        
        self.video_after_3_path = self._create_file_picker(
            scroll, "",
            self.config_data.get("video_after_3", ""),
            [("Videos", "*.mp4 *.avi *.mkv *.mov")]
        )
        
        # End-Video
        ctk.CTkLabel(
            scroll,
            text="🏁 End-Video (nach Session):",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 2))
        
        self.video_end_path = self._create_file_picker(
            scroll, "",
            self.config_data.get("video_end", ""),
            [("Videos", "*.mp4 *.avi *.mkv *.mov")]
        )
        
        # Hinweis
        ctk.CTkLabel(
            scroll,
            text="💡 Tipp: Kurze Videos (3-5 Sek) in MP4/H.264 für beste Performance",
            font=FONTS["tiny"],
            text_color=COLORS["text_muted"]
        ).pack(pady=(15, 0))
    
    def _create_statistics_tab(self, parent):
        """Statistik-Anzeige und Export"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Aktuelle Statistik laden
        try:
            from src.storage.statistics import statistics_manager
            current = statistics_manager.current
            all_stats = statistics_manager.get_all_stats()
        except Exception as e:
            logger.warning(f"Statistik laden fehlgeschlagen: {e}")
            current = None
            all_stats = []
        
        # Aktuelle Session
        current_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        current_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            current_frame,
            text="📊 Aktuelle Session",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))
        
        if current:
            # Zeitraum formatieren
            time_info = ""
            if current.start_time:
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(current.start_time)
                    time_info = f"\n📅 {start_dt.strftime('%d.%m.%Y')} ab {start_dt.strftime('%H:%M')}"
                    if current.end_time:
                        end_dt = datetime.fromisoformat(current.end_time)
                        time_info = f"\n📅 {start_dt.strftime('%d.%m.%Y')} {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                except:
                    pass
            
            stats_text = (
                f"Buchung: {current.booking_id or 'Keine'}\n"
                f"Fotos: {current.photos_taken}  |  Prints: {current.prints_completed}\n"
                f"Sessions: {current.sessions_count}{time_info}"
            )
        else:
            stats_text = "Keine aktive Session"
        
        self.current_stats_label = ctk.CTkLabel(
            current_frame,
            text=stats_text,
            font=FONTS["small"],
            text_color=COLORS["text_primary"],
            justify="center"
        )
        self.current_stats_label.pack(pady=(0, 10))
        
        # Bisherige Events
        history_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        history_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            history_frame,
            text="📋 Bisherige Events",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))
        
        if all_stats:
            # Letzte 5 anzeigen (mit Datum/Uhrzeit)
            history_text = ""
            for stat in all_stats[-5:]:
                booking = stat.get("booking_id", "?")
                photos = stat.get("photos_taken", 0)
                prints = stat.get("prints_completed", 0)
                
                # Datum und Zeitraum formatieren
                start_time = stat.get("start_time", "")
                end_time = stat.get("end_time", "")
                time_str = ""
                
                if start_time:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(start_time)
                        date_str = start_dt.strftime("%d.%m.")
                        start_str = start_dt.strftime("%H:%M")
                        
                        if end_time:
                            end_dt = datetime.fromisoformat(end_time)
                            end_str = end_dt.strftime("%H:%M")
                            time_str = f" ({date_str} {start_str}-{end_str})"
                        else:
                            time_str = f" ({date_str} {start_str})"
                    except:
                        pass
                
                history_text += f"• {booking}: {photos} Fotos, {prints} Prints{time_str}\n"
            
            ctk.CTkLabel(
                history_frame,
                text=history_text.strip(),
                font=FONTS["tiny"],
                text_color=COLORS["text_primary"],
                justify="left"
            ).pack(padx=15, pady=(0, 10), anchor="w")
        else:
            ctk.CTkLabel(
                history_frame,
                text="Noch keine Events aufgezeichnet",
                font=FONTS["small"],
                text_color=COLORS["text_primary"]
            ).pack(pady=(0, 10))
        
        # Lifetime-Drucker-Zähler
        lifetime_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card"], corner_radius=10)
        lifetime_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            lifetime_frame,
            text="🖨️ Drucker-Lifetime",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(10, 5))

        try:
            from src.storage.printer_lifetime import get_printer_lifetime
            lifetime = get_printer_lifetime()
            lifetime_count = lifetime.total_prints
            last_reset = lifetime.last_reset

            reset_info = ""
            if last_reset:
                try:
                    from datetime import datetime
                    reset_dt = datetime.fromisoformat(last_reset)
                    reset_info = f"\nLetzter Reset: {reset_dt.strftime('%d.%m.%Y %H:%M')}"
                except Exception:
                    pass

            lifetime_text = f"Gesamt-Drucke: {lifetime_count}{reset_info}"
        except Exception as e:
            logger.warning(f"Lifetime-Zähler laden fehlgeschlagen: {e}")
            lifetime_text = "Nicht verfügbar"

        self.lifetime_label = ctk.CTkLabel(
            lifetime_frame,
            text=lifetime_text,
            font=FONTS["small"],
            text_color=COLORS["text_primary"],
            justify="center"
        )
        self.lifetime_label.pack(pady=(0, 5))

        ctk.CTkButton(
            lifetime_frame,
            text="Zähler zurücksetzen (Service-PIN)",
            font=FONTS["tiny"],
            width=200,
            height=28,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_muted"],
            command=self._reset_printer_lifetime
        ).pack(pady=(0, 10))

        # Export-Buttons
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)

        ctk.CTkButton(
            btn_frame,
            text="📤 Als CSV exportieren",
            font=FONTS["small"],
            width=150,
            height=35,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            command=self._export_stats_csv
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="🔄 Aktualisieren",
            font=FONTS["small"],
            width=120,
            height=35,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            command=self._refresh_statistics
        ).pack(side="left")
    
    def _export_stats_csv(self):
        """Exportiert Statistiken als CSV"""
        try:
            from src.storage.statistics import statistics_manager
            from tkinter import filedialog
            
            all_stats = statistics_manager.get_all_stats()
            if not all_stats:
                self._show_message("Keine Statistiken zum Exportieren vorhanden.")
                return
            
            # Datei-Dialog
            path = filedialog.asksaveasfilename(
                title="Statistik exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfilename="fexobooth_statistik.csv"
            )
            
            if not path:
                return
            
            # CSV schreiben
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Buchung", "Start", "Ende", "Fotos", "Prints", "Fehldrucke", "Sessions"])
                
                for stat in all_stats:
                    writer.writerow([
                        stat.get("booking_id", ""),
                        stat.get("start_time", ""),
                        stat.get("end_time", ""),
                        stat.get("photos_taken", 0),
                        stat.get("prints_completed", 0),
                        stat.get("prints_failed", 0),
                        stat.get("sessions_count", 0)
                    ])
            
            self._show_message(f"✅ Exportiert: {path}")
            logger.info(f"Statistik exportiert: {path}")
            
        except Exception as e:
            logger.error(f"Export-Fehler: {e}")
            self._show_message(f"❌ Fehler: {e}")
    
    def _refresh_statistics(self):
        """Aktualisiert die Statistik-Anzeige"""
        try:
            from src.storage.statistics import statistics_manager
            current = statistics_manager.current
            
            if current:
                stats_text = (
                    f"Buchung: {current.booking_id or 'Keine'}\n"
                    f"Fotos: {current.photos_taken}  |  Prints: {current.prints_completed}\n"
                    f"Sessions: {current.sessions_count}"
                )
            else:
                stats_text = "Keine aktive Session"
            
            self.current_stats_label.configure(text=stats_text)
            logger.info("Statistik aktualisiert")
        except Exception as e:
            logger.warning(f"Statistik-Refresh Fehler: {e}")
    
    def _reset_statistics(self):
        """Setzt alle Statistiken zurück (mit Bestätigung)"""
        # Bestätigungs-Dialog
        confirm = ctk.CTkToplevel(self)
        confirm.title("Bestätigung")
        confirm.geometry("300x150")
        confirm.transient(self)
        confirm.grab_set()
        
        # Zentrieren
        confirm.update_idletasks()
        x = (confirm.winfo_screenwidth() - 300) // 2
        y = (confirm.winfo_screenheight() - 150) // 2
        confirm.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(
            confirm,
            text="⚠️ Alle Statistiken löschen?",
            font=FONTS["body_bold"]
        ).pack(pady=(20, 10))
        
        ctk.CTkLabel(
            confirm,
            text="Diese Aktion kann nicht rückgängig\ngemacht werden!",
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        ).pack()
        
        btn_frame = ctk.CTkFrame(confirm, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        def do_reset():
            try:
                from src.storage.statistics import statistics_manager
                statistics_manager.reset_all()
                self._refresh_statistics()
                logger.info("Statistiken zurückgesetzt")
            except Exception as e:
                logger.error(f"Reset-Fehler: {e}")
            confirm.destroy()
        
        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=80,
            fg_color=COLORS["bg_light"],
            command=confirm.destroy
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="Löschen",
            width=80,
            fg_color=COLORS["error"],
            command=do_reset
        ).pack(side="left", padx=5)
    
    def _reset_printer_lifetime(self):
        """Setzt den Drucker-Lifetime-Zähler zurück - erfordert Service-PIN (6588)"""
        from src.ui.screens.service import SERVICE_PIN

        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)

        dialog_w, dialog_h = 340, 420
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - dialog_w) // 2
        y = (screen_h - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        content = ctk.CTkFrame(
            dialog, fg_color=COLORS["bg_medium"],
            border_color=COLORS["warning"], border_width=2, corner_radius=16
        )
        content.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(
            content, text="🖨️ Drucker-Zähler Reset",
            font=FONTS["body_bold"], text_color=COLORS["warning"]
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            content, text="Service-PIN eingeben:",
            font=FONTS["small"], text_color=COLORS["text_secondary"]
        ).pack(pady=(0, 5))

        pin_entry = ctk.CTkEntry(
            content, show="●", width=160, height=38,
            font=("Segoe UI", 18), justify="center",
            fg_color=COLORS["bg_dark"], border_color=COLORS["border_light"],
            corner_radius=SIZES["corner_radius"]
        )
        pin_entry.pack(pady=(0, 3))
        pin_entry.focus()

        error_label = ctk.CTkLabel(
            content, text="", font=FONTS["tiny"], text_color=COLORS["error"]
        )
        error_label.pack()

        def do_reset():
            if pin_entry.get() == SERVICE_PIN:
                try:
                    from src.storage.printer_lifetime import get_printer_lifetime
                    get_printer_lifetime().reset()
                    self.lifetime_label.configure(text="Gesamt-Drucke: 0\nZähler zurückgesetzt!")
                    logger.info("Drucker-Lifetime zurückgesetzt via Service-PIN")
                except Exception as e:
                    logger.error(f"Lifetime-Reset Fehler: {e}")
                dialog.destroy()
            else:
                pin_entry.delete(0, "end")
                error_label.configure(text="Falsche PIN!")
                pin_entry.configure(border_color=COLORS["error"])
                dialog.after(600, lambda: pin_entry.configure(border_color=COLORS["border_light"]))

        def numpad_press(key):
            if key == "⌫":
                current = pin_entry.get()
                pin_entry.delete(0, "end")
                pin_entry.insert(0, current[:-1])
            elif key == "✓":
                do_reset()
            else:
                pin_entry.insert("end", key)
                if len(pin_entry.get()) >= 4:
                    dialog.after(100, do_reset)

        pin_entry.bind("<Return>", lambda e: do_reset())
        pin_entry.bind("<KeyRelease>", lambda e: do_reset() if len(pin_entry.get()) >= 4 else None)

        # Numpad für Touch-Eingabe (wie beim Haupt-PIN-Dialog)
        btn_size = 56
        btn_font_size = 18
        btn_pad = 3

        numpad_frame = ctk.CTkFrame(content, fg_color="transparent")
        numpad_frame.pack(pady=6)

        buttons = [
            ["1", "2", "3"],
            ["4", "5", "6"],
            ["7", "8", "9"],
            ["⌫", "0", "✓"]
        ]

        for row in buttons:
            row_frame = ctk.CTkFrame(numpad_frame, fg_color="transparent")
            row_frame.pack()
            for num in row:
                btn = ctk.CTkButton(
                    row_frame, text=num,
                    width=btn_size, height=btn_size,
                    font=("Segoe UI", btn_font_size),
                    fg_color=COLORS["bg_light"] if num.isdigit() else COLORS["bg_card"],
                    hover_color=COLORS["bg_card"] if num.isdigit() else COLORS["primary_dark"],
                    corner_radius=SIZES["corner_radius_small"],
                    command=lambda n=num: numpad_press(n)
                )
                btn.pack(side="left", padx=btn_pad, pady=btn_pad)

        # Abbrechen-Button
        ctk.CTkButton(
            content, text="Abbrechen",
            font=FONTS["small"], width=120, height=30,
            fg_color="transparent", hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"], command=dialog.destroy
        ).pack(pady=(6, 12))

    def _show_message(self, text: str):
        """Zeigt eine kurze Nachricht"""
        msg = ctk.CTkToplevel(self)
        msg.title("")
        msg.geometry("300x100")
        msg.transient(self)
        msg.overrideredirect(True)
        
        msg.update_idletasks()
        x = (msg.winfo_screenwidth() - 300) // 2
        y = (msg.winfo_screenheight() - 100) // 2
        msg.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(msg, text=text, font=FONTS["body"]).pack(expand=True)
        msg.after(2000, msg.destroy)
    
    def _emergency_quit_from_dialog(self):
        """Ctrl+Shift+Q im Dialog - Dialog schließen und App beenden"""
        self.grab_release()
        self.destroy()
        app = getattr(self.parent_window, '_photobooth_app', None)
        if app:
            app._emergency_quit()

    def _quit_app(self):
        """Beendet die gesamte Anwendung - stellt Taskleiste und Benachrichtigungen wieder her."""
        logger.info("App wird beendet (Admin-Dialog)")
        try:
            app = getattr(self.parent_window, '_photobooth_app', None)
            if app:
                app._show_taskbar()
                app._suppress_notifications(False)
            self.parent_window.destroy()
        except Exception:
            pass

    def _cancel(self):
        """Abbrechen - Fullscreen wird von show_admin_dialog() wiederhergestellt"""
        self.destroy()
    
    def _save(self):
        """Speichert die Einstellungen"""
        logger.info("=== Admin-Einstellungen speichern ===")
        
        # Flash-Bild
        self.config_data["flash_image"] = self.flash_image_path.get().strip()
        
        # Slider-Werte
        self.config_data["countdown_time"] = int(self.countdown_slider.get())
        self.config_data["single_display_time"] = int(self.single_slider.get())
        self.config_data["final_time"] = int(self.final_slider.get())
        self.config_data["flash_duration"] = int(self.flash_slider.get())
        self.config_data["max_prints_per_session"] = int(self.prints_slider.get())
        
        # Checkboxen - alle auslesen und speichern
        checkbox_keys = ["allow_single_mode", "performance_mode", "start_fullscreen", "hide_finish_button",
                         "print_enabled", "template1_enabled", "template2_enabled", "rotate_180", "liveview_template_overlay", "gallery_enabled"]
        logger.info("Checkbox-Werte:")
        for key in checkbox_keys:
            var = getattr(self, f"check_{key}", None)
            if var:
                value = var.get()
                self.config_data[key] = value
                logger.info(f"  {key} = {value}")
        
        # Template-Pfade - nur wenn Tab erstellt wurde (Lazy Loading)
        if hasattr(self, 't1_path'):
            if "template_paths" not in self.config_data:
                self.config_data["template_paths"] = {}
            
            t1_path = self.t1_path.get().strip()
            t2_path = self.t2_path.get().strip()
            
            self.config_data["template_paths"]["template1"] = t1_path
            self.config_data["template_paths"]["template2"] = t2_path
            self.config_data["logo_path"] = self.logo_path.get().strip()

            logger.info(f"Template 1: enabled={self.config_data.get('template1_enabled')}, path='{t1_path}'")
            logger.info(f"Template 2: enabled={self.config_data.get('template2_enabled')}, path='{t2_path}'")
        
        # Galerie-Einstellungen - nur wenn Tab erstellt wurde
        if hasattr(self, 'gallery_ssid'):
            if "gallery" not in self.config_data:
                self.config_data["gallery"] = {}
            
            self.config_data["gallery"]["hotspot_ssid"] = self.gallery_ssid.get().strip()
            self.config_data["gallery"]["hotspot_password"] = self.gallery_password.get().strip()
            try:
                self.config_data["gallery"]["port"] = int(self.gallery_port.get())
            except ValueError:
                self.config_data["gallery"]["port"] = 8080
            
            logger.info(f"Galerie: enabled={self.config_data.get('gallery_enabled')}, "
                        f"ssid={self.config_data['gallery'].get('hotspot_ssid')}, "
                        f"port={self.config_data['gallery'].get('port')}")
        
        # Video-Pfade - nur wenn Tab erstellt wurde
        if hasattr(self, 'video_start_path'):
            self.config_data["video_start"] = self.video_start_path.get().strip()
            self.config_data["video_after_1"] = self.video_after_1_path.get().strip()
            self.config_data["video_after_2"] = self.video_after_2_path.get().strip()
            self.config_data["video_after_3"] = self.video_after_3_path.get().strip()
            self.config_data["video_end"] = self.video_end_path.get().strip()
            
            logger.info(f"Videos: start={bool(self.config_data.get('video_start'))}, "
                        f"after_1={bool(self.config_data.get('video_after_1'))}, "
                        f"after_2={bool(self.config_data.get('video_after_2'))}, "
                        f"after_3={bool(self.config_data.get('video_after_3'))}, "
                        f"end={bool(self.config_data.get('video_end'))}")
        
        # Drucker - nur wenn Tab erstellt wurde
        if hasattr(self, 'printer_dropdown'):
            printer = self.printer_dropdown.get()
            if printer.startswith("⭐ "):
                printer = printer[2:].replace(" (Standard)", "")
            self.config_data["printer_name"] = printer
            
            # Druck-Anpassung
            self.config_data["print_adjustment"] = {
                "offset_x": int(self.offset_x_slider.get()),
                "offset_y": int(self.offset_y_slider.get()),
                "zoom": int(self.zoom_slider.get())
            }
        
        # Kamera - nur wenn Tab erstellt wurde
        if hasattr(self, 'camera_type_dropdown'):
            self.config_data["camera_type"] = self.camera_type_dropdown.get()
            
            # Kamera-Index
            cam_selection = self.camera_dropdown.get()
            # Extrahiere Index aus "[0] Kamera..." oder "[0] 📷 Canon..."
            if cam_selection.startswith("["):
                try:
                    idx = int(cam_selection[1:cam_selection.index("]")])
                    self.config_data["camera_index"] = idx
                except:
                    pass
            
            # camera_settings sicherstellen dass Dict existiert
            if "camera_settings" not in self.config_data:
                self.config_data["camera_settings"] = {}
            
            self.config_data["camera_settings"]["single_photo_width"] = int(self.photo_width.get())
            self.config_data["camera_settings"]["single_photo_height"] = int(self.photo_height.get())
        
        # Neue PIN
        if self.new_pin.get() and len(self.new_pin.get()) == 4:
            self.config_data["admin_pin"] = self.new_pin.get()
        
        self.result = self.config_data
        logger.info("Admin-Einstellungen gespeichert")
        
        # Fullscreen wird von show_admin_dialog() wiederhergestellt
        self.destroy()
