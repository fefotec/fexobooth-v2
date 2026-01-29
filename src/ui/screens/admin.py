"""Admin-Dialog - Modern und übersichtlich"""

import customtkinter as ctk
from typing import Dict, Any, Optional
import os

from src.ui.theme import COLORS, FONTS, SIZES
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AdminDialog(ctk.CTkToplevel):
    """Moderner Admin-Einstellungen Dialog"""
    
    def __init__(self, parent, config: Dict[str, Any]):
        super().__init__(parent)
        
        self.title("⚙️ Admin-Einstellungen")
        self.geometry("700x600")
        self.configure(fg_color=COLORS["bg_dark"])
        
        self.config_data = config.copy()
        self.result: Optional[Dict[str, Any]] = None
        self.is_authenticated = False
        
        # Modal machen
        self.transient(parent)
        self.grab_set()
        
        # Zentrieren
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 700) // 2
        y = (self.winfo_screenheight() - 600) // 2
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
            font=("Segoe UI Emoji", 60)
        ).pack(pady=(0, 20))
        
        # Titel
        ctk.CTkLabel(
            center,
            text="Admin-Zugang",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        ).pack(pady=(0, 30))
        
        # PIN-Eingabe
        self.pin_entry = ctk.CTkEntry(
            center,
            show="●",
            width=250,
            height=60,
            font=("Segoe UI", 32),
            justify="center",
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            corner_radius=SIZES["corner_radius"]
        )
        self.pin_entry.pack(pady=10)
        self.pin_entry.bind("<Return>", lambda e: self._check_pin())
        self.pin_entry.focus()
        
        # Fehler-Label (versteckt)
        self.pin_error = ctk.CTkLabel(
            center,
            text="",
            font=FONTS["small"],
            text_color=COLORS["error"]
        )
        self.pin_error.pack(pady=5)
        
        # Numpad für Touch
        numpad_frame = ctk.CTkFrame(center, fg_color="transparent")
        numpad_frame.pack(pady=20)
        
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
                    width=70,
                    height=70,
                    font=("Segoe UI", 24),
                    fg_color=COLORS["bg_light"] if num.isdigit() else COLORS["bg_card"],
                    hover_color=COLORS["bg_card"],
                    corner_radius=SIZES["corner_radius_small"],
                    command=lambda n=num: self._numpad_press(n)
                )
                btn.pack(side="left", padx=5, pady=5)
        
        # Abbrechen
        ctk.CTkButton(
            center,
            text="Abbrechen",
            font=FONTS["body"],
            width=150,
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_muted"],
            command=self.destroy
        ).pack(pady=(20, 0))
    
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
    
    def _check_pin(self):
        """Prüft die PIN"""
        entered = self.pin_entry.get()
        correct = self.config_data.get("admin_pin", "3198")
        
        if entered == correct:
            self.is_authenticated = True
            self.pin_frame.destroy()
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
        main.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Tabview
        tabview = ctk.CTkTabview(
            main,
            fg_color=COLORS["bg_medium"],
            segmented_button_fg_color=COLORS["bg_light"],
            segmented_button_selected_color=COLORS["primary"],
            segmented_button_unselected_color=COLORS["bg_card"]
        )
        tabview.pack(fill="both", expand=True)
        
        # Tabs
        self._create_general_tab(tabview.add("Allgemein"))
        self._create_templates_tab(tabview.add("Templates"))
        self._create_print_tab(tabview.add("Druck"))
        self._create_camera_tab(tabview.add("Kamera"))
        
        # Button-Leiste
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(20, 0))
        
        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            font=FONTS["button"],
            width=150,
            height=50,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_card"],
            corner_radius=SIZES["corner_radius"],
            command=self.destroy
        ).pack(side="left")
        
        ctk.CTkButton(
            btn_frame,
            text="💾 Speichern",
            font=FONTS["button"],
            width=200,
            height=50,
            fg_color=COLORS["success"],
            hover_color="#00e676",
            corner_radius=SIZES["corner_radius"],
            command=self._save
        ).pack(side="right")
    
    def _create_general_tab(self, parent):
        """Allgemeine Einstellungen"""
        # Scrollbar für lange Listen
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Countdown
        self._add_setting(
            scroll, "Countdown (Sekunden)",
            "countdown_time", "slider", 1, 15
        )
        
        # Anzeige-Zeit nach Foto
        self._add_setting(
            scroll, "Foto-Anzeige (Sekunden)",
            "single_display_time", "slider", 1, 10
        )
        
        # Auto-Return Zeit
        self._add_setting(
            scroll, "Auto-Return (Sekunden)",
            "final_time", "slider", 10, 60
        )
        
        # Max Drucke
        self._add_setting(
            scroll, "Max. Drucke pro Session",
            "max_prints_per_session", "slider", 0, 10
        )
        
        # Checkboxen
        self._add_checkbox(scroll, "Single-Foto Modus erlauben", "allow_single_mode")
        self._add_checkbox(scroll, "Performance-Modus", "performance_mode")
        self._add_checkbox(scroll, "Vollbild beim Start", "start_fullscreen")
        self._add_checkbox(scroll, "Fertig-Button ausblenden", "hide_finish_button")
        
        # Neue PIN
        ctk.CTkLabel(
            scroll,
            text="Neue Admin-PIN (4-stellig):",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(20, 5))
        
        self.new_pin = ctk.CTkEntry(
            scroll,
            placeholder_text="Leer = keine Änderung",
            width=200,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
        self.new_pin.pack(anchor="w")
    
    def _create_templates_tab(self, parent):
        """Template-Einstellungen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Template 1
        self._add_checkbox(scroll, "Template 1 aktivieren", "template1_enabled")
        
        ctk.CTkLabel(
            scroll, text="Template 1 Pfad (ZIP):",
            font=FONTS["small"], text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(5, 2))
        
        self.t1_path = ctk.CTkEntry(
            scroll, width=400,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.t1_path.insert(0, self.config_data.get("template_paths", {}).get("template1", ""))
        self.t1_path.pack(anchor="w", pady=(0, 15))
        
        # Template 2
        self._add_checkbox(scroll, "Template 2 aktivieren", "template2_enabled")
        
        ctk.CTkLabel(
            scroll, text="Template 2 Pfad (ZIP):",
            font=FONTS["small"], text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(5, 2))
        
        self.t2_path = ctk.CTkEntry(
            scroll, width=400,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.t2_path.insert(0, self.config_data.get("template_paths", {}).get("template2", ""))
        self.t2_path.pack(anchor="w", pady=(0, 15))
        
        # Logo
        ctk.CTkLabel(
            scroll, text="Logo-Pfad:",
            font=FONTS["small"], text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(20, 2))
        
        self.logo_path = ctk.CTkEntry(
            scroll, width=400,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.logo_path.insert(0, self.config_data.get("logo_path", ""))
        self.logo_path.pack(anchor="w")
    
    def _create_print_tab(self, parent):
        """Druck-Einstellungen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        adjustment = self.config_data.get("print_adjustment", {})
        
        # Drucker-Name
        ctk.CTkLabel(
            scroll, text="Drucker (leer = Standard):",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 5))
        
        self.printer_name = ctk.CTkEntry(
            scroll, width=300,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.printer_name.insert(0, self.config_data.get("printer_name", ""))
        self.printer_name.pack(anchor="w", pady=(0, 20))
        
        # Offsets
        ctk.CTkLabel(
            scroll, text="Offset X:",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 5))
        
        self.offset_x = ctk.CTkSlider(
            scroll, from_=-100, to=100, number_of_steps=200, width=300,
            fg_color=COLORS["bg_light"], progress_color=COLORS["primary"]
        )
        self.offset_x.set(adjustment.get("offset_x", 0))
        self.offset_x.pack(anchor="w")
        
        ctk.CTkLabel(
            scroll, text="Offset Y:",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 5))
        
        self.offset_y = ctk.CTkSlider(
            scroll, from_=-100, to=100, number_of_steps=200, width=300,
            fg_color=COLORS["bg_light"], progress_color=COLORS["primary"]
        )
        self.offset_y.set(adjustment.get("offset_y", 0))
        self.offset_y.pack(anchor="w")
        
        ctk.CTkLabel(
            scroll, text="Zoom (%):",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(15, 5))
        
        self.zoom = ctk.CTkSlider(
            scroll, from_=50, to=150, number_of_steps=100, width=300,
            fg_color=COLORS["bg_light"], progress_color=COLORS["primary"]
        )
        self.zoom.set(adjustment.get("zoom", 100))
        self.zoom.pack(anchor="w")
    
    def _create_camera_tab(self, parent):
        """Kamera-Einstellungen"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Kamera-Index
        ctk.CTkLabel(
            scroll, text="Kamera-Index:",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 5))
        
        self.camera_index = ctk.CTkOptionMenu(
            scroll, values=["0", "1", "2", "3", "4"],
            fg_color=COLORS["bg_card"], button_color=COLORS["primary"]
        )
        self.camera_index.set(str(self.config_data.get("camera_index", 0)))
        self.camera_index.pack(anchor="w", pady=(0, 20))
        
        # Auflösung
        cam_settings = self.config_data.get("camera_settings", {})
        
        ctk.CTkLabel(
            scroll, text="Foto-Breite:",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 5))
        
        self.photo_width = ctk.CTkEntry(
            scroll, width=150,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.photo_width.insert(0, str(cam_settings.get("single_photo_width", 1920)))
        self.photo_width.pack(anchor="w")
        
        ctk.CTkLabel(
            scroll, text="Foto-Höhe:",
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(10, 5))
        
        self.photo_height = ctk.CTkEntry(
            scroll, width=150,
            fg_color=COLORS["bg_card"], border_color=COLORS["border"]
        )
        self.photo_height.insert(0, str(cam_settings.get("single_photo_height", 1080)))
        self.photo_height.pack(anchor="w")
    
    def _add_setting(self, parent, label: str, key: str, widget_type: str,
                     min_val: int = 0, max_val: int = 100):
        """Fügt eine Einstellung hinzu"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            frame, text=label,
            font=FONTS["body"], text_color=COLORS["text_secondary"]
        ).pack(anchor="w")
        
        if widget_type == "slider":
            slider = ctk.CTkSlider(
                frame, from_=min_val, to=max_val,
                number_of_steps=max_val - min_val,
                width=300,
                fg_color=COLORS["bg_light"],
                progress_color=COLORS["primary"]
            )
            slider.set(self.config_data.get(key, min_val))
            slider.pack(anchor="w", pady=(5, 0))
            setattr(self, f"setting_{key}", slider)
    
    def _add_checkbox(self, parent, label: str, key: str):
        """Fügt eine Checkbox hinzu"""
        var = ctk.BooleanVar(value=self.config_data.get(key, False))
        
        cb = ctk.CTkCheckBox(
            parent, text=label, variable=var,
            font=FONTS["body"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"]
        )
        cb.pack(anchor="w", pady=5)
        setattr(self, f"check_{key}", var)
    
    def _save(self):
        """Speichert die Einstellungen"""
        # Slider-Werte
        for key in ["countdown_time", "single_display_time", "final_time", "max_prints_per_session"]:
            slider = getattr(self, f"setting_{key}", None)
            if slider:
                self.config_data[key] = int(slider.get())
        
        # Checkboxen
        for key in ["allow_single_mode", "performance_mode", "start_fullscreen", "hide_finish_button",
                    "template1_enabled", "template2_enabled"]:
            var = getattr(self, f"check_{key}", None)
            if var:
                self.config_data[key] = var.get()
        
        # Template-Pfade
        self.config_data["template_paths"]["template1"] = self.t1_path.get()
        self.config_data["template_paths"]["template2"] = self.t2_path.get()
        self.config_data["logo_path"] = self.logo_path.get()
        
        # Druck
        self.config_data["printer_name"] = self.printer_name.get()
        self.config_data["print_adjustment"] = {
            "offset_x": int(self.offset_x.get()),
            "offset_y": int(self.offset_y.get()),
            "zoom": int(self.zoom.get())
        }
        
        # Kamera
        self.config_data["camera_index"] = int(self.camera_index.get())
        self.config_data["camera_settings"]["single_photo_width"] = int(self.photo_width.get())
        self.config_data["camera_settings"]["single_photo_height"] = int(self.photo_height.get())
        
        # Neue PIN
        if self.new_pin.get() and len(self.new_pin.get()) == 4:
            self.config_data["admin_pin"] = self.new_pin.get()
        
        self.result = self.config_data
        logger.info("Admin-Einstellungen gespeichert")
        self.destroy()
