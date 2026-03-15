import customtkinter as ctk
import webbrowser
import requests
import threading
import time
from typing import Callable
from app.gui import theme

class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master, on_login_success: Callable[[dict], None], on_skip: Callable[[], None]):
        super().__init__(master)
        
        self.title("Syso - Secure Login")
        self.geometry("450x600")
        self.resizable(False, False)
        
        # Center the window
        self.attributes('-topmost', True)
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        self.on_login_success = on_login_success
        self.on_skip = on_skip
        self.backend_url = "http://34.14.201.124:8000"
        self.is_checking = False

        self.configure(fg_color=(theme.LIGHT_PANEL, theme.DARK_PANEL))
        self._build_ui()

    def _build_ui(self):
        # Logo placeholder or Icon
        logo_label = ctk.CTkLabel(
            self, 
            text="👔", 
            font=ctk.CTkFont("Inter", 64)
        )
        logo_label.pack(pady=(60, 10))

        header = ctk.CTkLabel(
            self, 
            text="Welcome to Syso", 
            font=ctk.CTkFont("Inter", 24, "bold"),
            text_color=theme.GREEN_PRIMARY
        )
        header.pack(pady=(10, 5))

        subtext = ctk.CTkLabel(
            self, 
            text="The intelligent caretaker for your system.", 
            font=ctk.CTkFont("Inter", 13),
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED)
        )
        subtext.pack(pady=(0, 40))

        # Login area
        self.login_btn = ctk.CTkButton(
            self,
            text="Sign in with Google",
            font=ctk.CTkFont("Inter", 14, "bold"),
            width=280,
            height=50,
            corner_radius=theme.RADIUS_PILL,
            fg_color="#FFFFFF", # Google style
            text_color="#000000",
            hover_color="#F2F2F2",
            command=self._launch_google_login
        )
        self.login_btn.pack(pady=10)

        # Skip Button
        self.skip_btn = ctk.CTkButton(
            self,
            text="Skip for now",
            font=ctk.CTkFont("Inter", 12),
            width=100,
            height=30,
            fg_color="transparent",
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED),
            hover_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
            command=self._handle_skip
        )
        self.skip_btn.pack(pady=5)

        self.status_label = ctk.CTkLabel(
            self, 
            text="Securely managed by Google OAuth2", 
            font=ctk.CTkFont("Inter", 11),
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED)
        )
        self.status_label.pack(pady=(30, 10))

    def _launch_google_login(self):
        """Opens browser to start Google OAuth flow."""
        self.login_btn.configure(state="disabled", text="Opening Browser...")
        webbrowser.open(f"{self.backend_url}/auth/login")
        
        # Start polling for success
        if not self.is_checking:
            self.is_checking = True
            threading.Thread(target=self._poll_auth_status, daemon=True).start()

    def _poll_auth_status(self):
        """Polls the backend until login is detected."""
        while self.is_checking:
            try:
                response = requests.get(f"{self.backend_url}/auth/status", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("is_logged_in"):
                        self.is_checking = False
                        # Success! Update UI on main thread
                        self.after(0, lambda: self._handle_success(data))
                        break
            except Exception as e:
                pass
            time.sleep(2)

    def _handle_skip(self):
        self.is_checking = False
        self.on_skip()
        self.destroy()

    def _handle_success(self, auth_data: dict):
        self.on_login_success(auth_data)
        self.destroy()
