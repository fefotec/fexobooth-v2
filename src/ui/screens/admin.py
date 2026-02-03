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

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AdminDialog(ctk.CTkToplevel):
    """Moderner Admin-Einstellungen Dialog"""
    
    def __init__(self, parent, config: Dict[str, Any]):
        super().__init__(parent)
        
        self.title("⚙️ Admin-Einstellungen")
        self.geometry("750x550")
        self.configure(fg_color=COLORS["bg_dark"])
        
        self.config_data = config.copy()
        self.result: Optional[Dict[str, Any]] = None
        self.is_authenticated = False
        self.parent_window = parent
        
        # Modal machen
        self.transient(parent)
        self.grab_set()
        
        # Zentrieren
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 750) // 2
        y = (self.winfo_screenheight() - 550) // 2
        self.geometry(f"+{x}+{y}")
        
        # PIN-Abfrage zuerst
        self._show_pin_dialog()
    
    def _show_pin_dialog(self):
        """Zeigt PIN-Eingabe"""
        self.pin_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.pin_frame.pack(fill="both", expand=True)
        
        # Zentrierter Container
        center = ctk.CTkFrame(self.pin_frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        
        # Icon
        ctk.CTkLabel(
            center,
            text="🔐",
            font=("Segoe UI Emoji", 50)
        ).pack(pady=(0, 15))
        
        # Titel
        ctk.CTkLabel(
            center,
            text="Admin-Zugang",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(0, 20))
        
        # PIN-Eingabe (Auto-Submit bei 4 Zeichen)
        self.pin_entry = ctk.CTkEntry(
            center,
            show="●",
            width=220,
            height=50,
            font=("Segoe UI", 28),
            justify="center",
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            corner_radius=SIZES["corner_radius"]
        )
        self.pin_entry.pack(pady=10)
        self.pin_entry.bind("<Return>", lambda e: self._check_pin())
        self.pin_entry.bind("<KeyRelease>", self._on_pin_key)
        self.pin_entry.focus()
        
        # Fehler-Label
        self.pin_error = ctk.CTkLabel(
            center,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"]
        )
        self.pin_error.pack(pady=5)
        
        # Numpad für Touch
        numpad_frame = ctk.CTkFrame(center, fg_color="transparent")
        numpad_frame.pack(pady=15)
        
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
                    width=60,
                    height=60,
                    font=("Segoe UI", 22),
                    fg_color=COLORS["bg_light"] if num.isdigit() else COLORS["bg_card"],
                    hover_color=COLORS["bg_card"],
                    corner_radius=SIZES["corner_radius_small"],
                    command=lambda n=num: self._numpad_press(n)
                )
                btn.pack(side="left", padx=4, pady=4)
        
        # Abbrechen
        ctk.CTkButton(
            center,
            text="Abbrechen",
            font=FONTS["small"],
            width=120,
            height=35,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self.destroy
        ).pack(pady=(15, 0))
    
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
        """Prüft die PIN"""
        entered = self.pin_entry.get()
        correct = self.config_data.get("admin_pin", "3198")
        
        if entered == correct:
            self.is_authenticated = True
            self.pin_frame.destroy()
            
            # *** WICHTIG: Fullscreen deaktivieren für Admin ***
            try:
                # overrideredirect entfernen damit Fenster normal angezeigt wird
                self.parent_window.overrideredirect(False)
                # Normale Fenstergröße
                self.parent_window.geometry("1024x768")
                logger.info("Fullscreen deaktiviert für Admin-Modus")
            except Exception as e:
                logger.debug(f"Fullscreen-Exit Fehler: {e}")
            
            self._show_settings()
        else:
            self.pin_entry.delete(0, "end")
            self.pin_error.configure(text="❌ Falsche PIN!")
            
            # Shake-Effekt
            x = self.winfo_x()
            for dx in [10, -20, 20, -10, 0]:
                self.geometry(f"+{x + dx}+{self.winfo_y()}")
                self.update()
                self.after(50)
    
    def _show_settings(self):
        """Zeigt Einstellungen"""
        # Hauptcontainer
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Tabview
        tabview = ctk.CTkTabview(
            main,
            fg_color=COLORS["bg_medium"],
            segmented_button_fg_color=COLORS["bg_light"],
            segmented_button_selected_color=COLORS["primary"],
            segmented_button_unselected_color=COLORS["bg_card"],
            height=420
        )
        tabview.pack(fill="both", expand=True)
        
        # Tabs
        self._create_general_tab(tabview.add("Allgemein"))
        self._create_templates_tab(tabview.add("Templates"))
        self._create_print_tab(tabview.add("Druck"))
        self._create_camera_tab(tabview.add("Kamera"))
        
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
        
        # Wert-Anzeige
        value_label = ctk.CTkLabel(
            label_frame,
            text=f"{self.config_data.get(key, min_val)}{suffix}",
            font=FONTS["body_bold"],
            text_color=COLORS["primary"]
        )
        value_label.pack(side="right")
        
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
        
        # Max Drucke
        self.prints_slider = self._create_slider_with_value(
            scroll, "Max. Drucke:", "max_prints_per_session", 0, 10, ""
        )
        
        # Checkboxen
        self._add_checkbox(scroll, "Single-Foto Modus erlauben", "allow_single_mode")
        self._add_checkbox(scroll, "Performance-Modus", "performance_mode")
        self._add_checkbox(scroll, "Vollbild beim Start", "start_fullscreen")
        self._add_checkbox(scroll, "Fertig-Button ausblenden", "hide_finish_button")
        
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
        
        # Offset-Werte mit Anzeige
        adjustment = self.config_data.get("print_adjustment", {})
        
        # Offset X
        self.offset_x_slider = self._create_print_slider(
            preview_frame, "Offset X:", adjustment.get("offset_x", 0), -100, 100, " px"
        )
        
        # Offset Y
        self.offset_y_slider = self._create_print_slider(
            preview_frame, "Offset Y:", adjustment.get("offset_y", 0), -100, 100, " px"
        )
        
        # Zoom
        self.zoom_slider = self._create_print_slider(
            preview_frame, "Zoom:", adjustment.get("zoom", 100), 50, 150, " %"
        )
        
        ctk.CTkLabel(preview_frame, text="").pack(pady=5)  # Spacer
    
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
    
    def _get_available_cameras(self) -> List[str]:
        """Ermittelt verfügbare Kameras mit Namen"""
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
            # Webcams via OpenCV
            try:
                import cv2
                for i in range(5):
                    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    if cap.isOpened():
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cameras.append(f"[{i}] Webcam {i} ({w}x{h})")
                        cap.release()
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
    
    def _cancel(self):
        """Abbrechen - Fullscreen wiederherstellen wenn nötig"""
        if self.config_data.get("start_fullscreen", True):
            try:
                screen_width = self.parent_window.winfo_screenwidth()
                screen_height = self.parent_window.winfo_screenheight()
                self.parent_window.overrideredirect(True)
                self.parent_window.geometry(f"{screen_width}x{screen_height}+0+0")
                self.parent_window.focus_force()
                logger.info("Fullscreen wiederhergestellt")
            except Exception as e:
                logger.debug(f"Fullscreen-Restore Fehler: {e}")
        self.destroy()
    
    def _save(self):
        """Speichert die Einstellungen"""
        logger.info("=== Admin-Einstellungen speichern ===")
        
        # Slider-Werte
        self.config_data["countdown_time"] = int(self.countdown_slider.get())
        self.config_data["single_display_time"] = int(self.single_slider.get())
        self.config_data["final_time"] = int(self.final_slider.get())
        self.config_data["max_prints_per_session"] = int(self.prints_slider.get())
        
        # Checkboxen
        for key in ["allow_single_mode", "performance_mode", "start_fullscreen", "hide_finish_button",
                    "template1_enabled", "template2_enabled", "rotate_180"]:
            var = getattr(self, f"check_{key}", None)
            if var:
                self.config_data[key] = var.get()
                logger.debug(f"  {key} = {var.get()}")
        
        # Template-Pfade - sicherstellen dass Dict existiert
        if "template_paths" not in self.config_data:
            self.config_data["template_paths"] = {}
        
        t1_path = self.t1_path.get().strip()
        t2_path = self.t2_path.get().strip()
        
        self.config_data["template_paths"]["template1"] = t1_path
        self.config_data["template_paths"]["template2"] = t2_path
        self.config_data["logo_path"] = self.logo_path.get().strip()
        
        logger.info(f"Template 1: enabled={self.config_data.get('template1_enabled')}, path='{t1_path}'")
        logger.info(f"Template 2: enabled={self.config_data.get('template2_enabled')}, path='{t2_path}'")
        
        # Drucker
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
        
        # Kamera-Typ (NEU!)
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
        
        # Fullscreen wiederherstellen wenn gewünscht
        if self.config_data.get("start_fullscreen", True):
            try:
                screen_width = self.parent_window.winfo_screenwidth()
                screen_height = self.parent_window.winfo_screenheight()
                self.parent_window.overrideredirect(True)
                self.parent_window.geometry(f"{screen_width}x{screen_height}+0+0")
                self.parent_window.focus_force()
                logger.info("Fullscreen wiederhergestellt")
            except Exception as e:
                logger.debug(f"Fullscreen-Restore Fehler: {e}")
        
        self.destroy()
