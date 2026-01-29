"""Admin-Dialog"""

import customtkinter as ctk
from typing import Dict, Any, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


class AdminDialog(ctk.CTkToplevel):
    """Admin-Einstellungen Dialog"""
    
    def __init__(self, parent, config: Dict[str, Any]):
        super().__init__(parent)
        
        self.title("Admin-Einstellungen")
        self.geometry("600x500")
        self.config_data = config.copy()
        self.result: Optional[Dict[str, Any]] = None
        
        # Modal machen
        self.transient(parent)
        self.grab_set()
        
        # PIN-Abfrage zuerst
        self._show_pin_dialog()
    
    def _show_pin_dialog(self):
        """Zeigt PIN-Eingabe"""
        self.pin_frame = ctk.CTkFrame(self)
        self.pin_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            self.pin_frame,
            text="Admin-PIN eingeben:",
            font=ctk.CTkFont(size=20)
        ).pack(pady=20)
        
        self.pin_entry = ctk.CTkEntry(
            self.pin_frame,
            show="*",
            width=200,
            height=50,
            font=ctk.CTkFont(size=24)
        )
        self.pin_entry.pack(pady=10)
        self.pin_entry.bind("<Return>", lambda e: self._check_pin())
        
        ctk.CTkButton(
            self.pin_frame,
            text="OK",
            width=100,
            command=self._check_pin
        ).pack(pady=20)
        
        self.pin_entry.focus()
    
    def _check_pin(self):
        """Prüft die PIN"""
        entered = self.pin_entry.get()
        correct = self.config_data.get("admin_pin", "3198")
        
        if entered == correct:
            self.pin_frame.destroy()
            self._show_settings()
        else:
            self.pin_entry.delete(0, "end")
            ctk.CTkLabel(
                self.pin_frame,
                text="Falsche PIN!",
                text_color="red"
            ).pack()
    
    def _show_settings(self):
        """Zeigt Einstellungen"""
        # Tabview für Kategorien
        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Tabs erstellen
        general_tab = tabview.add("Allgemein")
        templates_tab = tabview.add("Templates")
        print_tab = tabview.add("Druck")
        
        # --- Allgemein ---
        self._create_general_settings(general_tab)
        
        # --- Templates ---
        self._create_template_settings(templates_tab)
        
        # --- Druck ---
        self._create_print_settings(print_tab)
        
        # Speichern/Abbrechen
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=100,
            command=self.destroy
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="Speichern",
            width=100,
            fg_color="#27ae60",
            command=self._save
        ).pack(side="right", padx=5)
    
    def _create_general_settings(self, parent):
        """Allgemeine Einstellungen"""
        # Countdown
        ctk.CTkLabel(parent, text="Countdown (Sek):").pack(anchor="w", padx=10, pady=(10, 0))
        self.countdown_var = ctk.IntVar(value=self.config_data.get("countdown_time", 5))
        ctk.CTkSlider(
            parent,
            from_=1,
            to=10,
            variable=self.countdown_var,
            number_of_steps=9
        ).pack(fill="x", padx=10)
        
        # Kamera-Index
        ctk.CTkLabel(parent, text="Kamera-Index:").pack(anchor="w", padx=10, pady=(10, 0))
        self.camera_var = ctk.IntVar(value=self.config_data.get("camera_index", 0))
        ctk.CTkOptionMenu(
            parent,
            values=["0", "1", "2", "3", "4"],
            variable=self.camera_var
        ).pack(anchor="w", padx=10)
        
        # Neue PIN
        ctk.CTkLabel(parent, text="Neue Admin-PIN:").pack(anchor="w", padx=10, pady=(10, 0))
        self.new_pin_entry = ctk.CTkEntry(parent, placeholder_text="4-stellig")
        self.new_pin_entry.pack(anchor="w", padx=10)
    
    def _create_template_settings(self, parent):
        """Template-Einstellungen"""
        # Template 1
        self.t1_enabled = ctk.CTkCheckBox(
            parent,
            text="Template 1 aktiv"
        )
        self.t1_enabled.pack(anchor="w", padx=10, pady=10)
        if self.config_data.get("template1_enabled"):
            self.t1_enabled.select()
        
        ctk.CTkLabel(parent, text="Template 1 Pfad:").pack(anchor="w", padx=10)
        self.t1_path = ctk.CTkEntry(parent, width=400)
        self.t1_path.insert(0, self.config_data.get("template_paths", {}).get("template1", ""))
        self.t1_path.pack(anchor="w", padx=10)
        
        # Template 2
        self.t2_enabled = ctk.CTkCheckBox(
            parent,
            text="Template 2 aktiv"
        )
        self.t2_enabled.pack(anchor="w", padx=10, pady=(20, 10))
        if self.config_data.get("template2_enabled"):
            self.t2_enabled.select()
        
        ctk.CTkLabel(parent, text="Template 2 Pfad:").pack(anchor="w", padx=10)
        self.t2_path = ctk.CTkEntry(parent, width=400)
        self.t2_path.insert(0, self.config_data.get("template_paths", {}).get("template2", ""))
        self.t2_path.pack(anchor="w", padx=10)
    
    def _create_print_settings(self, parent):
        """Druck-Einstellungen"""
        adjustment = self.config_data.get("print_adjustment", {})
        
        # Offset X
        ctk.CTkLabel(parent, text="Offset X:").pack(anchor="w", padx=10, pady=(10, 0))
        self.offset_x_var = ctk.IntVar(value=adjustment.get("offset_x", 0))
        ctk.CTkSlider(
            parent,
            from_=-100,
            to=100,
            variable=self.offset_x_var
        ).pack(fill="x", padx=10)
        
        # Offset Y
        ctk.CTkLabel(parent, text="Offset Y:").pack(anchor="w", padx=10, pady=(10, 0))
        self.offset_y_var = ctk.IntVar(value=adjustment.get("offset_y", 0))
        ctk.CTkSlider(
            parent,
            from_=-100,
            to=100,
            variable=self.offset_y_var
        ).pack(fill="x", padx=10)
        
        # Zoom
        ctk.CTkLabel(parent, text="Zoom (%):").pack(anchor="w", padx=10, pady=(10, 0))
        self.zoom_var = ctk.IntVar(value=adjustment.get("zoom", 100))
        ctk.CTkSlider(
            parent,
            from_=50,
            to=150,
            variable=self.zoom_var
        ).pack(fill="x", padx=10)
        
        # Max Prints
        ctk.CTkLabel(parent, text="Max. Drucke pro Session:").pack(anchor="w", padx=10, pady=(10, 0))
        self.max_prints_var = ctk.IntVar(value=self.config_data.get("max_prints_per_session", 1))
        ctk.CTkOptionMenu(
            parent,
            values=["1", "2", "3", "5", "10"],
            variable=self.max_prints_var
        ).pack(anchor="w", padx=10)
    
    def _save(self):
        """Speichert die Einstellungen"""
        # Werte übernehmen
        self.config_data["countdown_time"] = self.countdown_var.get()
        self.config_data["camera_index"] = int(self.camera_var.get())
        
        if self.new_pin_entry.get():
            self.config_data["admin_pin"] = self.new_pin_entry.get()
        
        self.config_data["template1_enabled"] = bool(self.t1_enabled.get())
        self.config_data["template2_enabled"] = bool(self.t2_enabled.get())
        self.config_data["template_paths"]["template1"] = self.t1_path.get()
        self.config_data["template_paths"]["template2"] = self.t2_path.get()
        
        self.config_data["print_adjustment"] = {
            "offset_x": self.offset_x_var.get(),
            "offset_y": self.offset_y_var.get(),
            "zoom": self.zoom_var.get()
        }
        self.config_data["max_prints_per_session"] = int(self.max_prints_var.get())
        
        self.result = self.config_data
        logger.info("Admin-Einstellungen gespeichert")
        self.destroy()
