# twitch_chat_monitor/setup_wizard.py
"""
First-run setup wizard for public users.
Guides them through Twitch app creation and OAuth authentication.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import threading
import http.server
import urllib.parse
import requests
import socket

from .user_config import user_config

# App name and OAuth settings
APP_NAME = "FameForecastTextView"
REDIRECT_PORT = 3000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth callback from Twitch"""

    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_GET(self):
        # Parse the authorization code from URL
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response = """
            <html><body style="font-family: Arial; text-align: center; padding: 50px; background: #1e1e1e; color: white;">
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the app.</p>
            </body></html>
            """
            self.wfile.write(response.encode())
        else:
            self.server.auth_code = None
            error = params.get('error', ['Unknown error'])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response = f"""
            <html><body style="font-family: Arial; text-align: center; padding: 50px; background: #1e1e1e; color: white;">
                <h1>Authorization Failed</h1>
                <p>Error: {error}</p>
                <p>Please close this window and try again.</p>
            </body></html>
            """
            self.wfile.write(response.encode())


class SetupWizard:
    def __init__(self, on_complete_callback=None):
        self.on_complete = on_complete_callback
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - First Time Setup")
        self.root.geometry("650x900")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(True, True)  # Allow resizing

        # Variables
        self.client_id_var = tk.StringVar()
        self.client_secret_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.auth_status = tk.StringVar(value="Not authorized")
        self.access_token = None
        self.refresh_token = None

        self._build_ui()

    def _copy_to_clipboard(self, text):
        """Copy text to clipboard and show brief confirmation"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def _create_copyable_field(self, parent, label_text, value):
        """Create a read-only field with a copy button"""
        frame = tk.Frame(parent, bg="#1e1e1e")
        frame.pack(fill='x', pady=5)

        tk.Label(frame, text=label_text, fg="#ccc", bg="#1e1e1e",
                font=("Segoe UI", 9), width=20, anchor='w').pack(side='left')

        entry = tk.Entry(frame, font=("Consolas", 10), width=35, bg="#2b2b2b",
                        fg="white", insertbackground="white", readonlybackground="#2b2b2b",
                        disabledforeground="white")
        entry.insert(0, value)
        entry.config(state='readonly')
        entry.pack(side='left', padx=5)

        btn = ttk.Button(frame, text="Copy", width=6,
                        command=lambda: self._copy_to_clipboard(value))
        btn.pack(side='left')

        return frame

    def _build_ui(self):
        # Title
        title = tk.Label(self.root, text=f"{APP_NAME} Setup",
                        font=("Segoe UI", 20, "bold"), fg="#9147ff", bg="#1e1e1e")
        title.pack(pady=(20, 10))

        subtitle = tk.Label(self.root, text="Multi-stream chat + transcription viewer",
                           font=("Segoe UI", 10), fg="#888", bg="#1e1e1e")
        subtitle.pack(pady=(0, 20))

        # Main container
        container = tk.Frame(self.root, bg="#1e1e1e")
        container.pack(fill='both', expand=True, padx=30)

        # Step 1: Create Twitch App
        self._create_section(container, "Step 1: Create a Twitch Developer App", [
            "1. Click the button below to open Twitch Developer Console",
            "2. Log in with your Twitch account",
            "3. Click 'Register Your Application'",
            "4. Use these values (click Copy buttons):"
        ])

        # Copyable fields for app setup
        self._create_copyable_field(container, "App Name:", APP_NAME)
        self._create_copyable_field(container, "OAuth Redirect URL:", REDIRECT_URI)

        self._create_section(container, "", [
            "5. Set Category to: Chat Bot",
            "6. Click 'Create' then 'Manage' to see your credentials"
        ])

        btn_open_dev = ttk.Button(container, text="Open Twitch Developer Console",
                                  command=lambda: webbrowser.open("https://dev.twitch.tv/console/apps"))
        btn_open_dev.pack(pady=(5, 20))

        # Step 2: Enter Credentials
        self._create_section(container, "Step 2: Enter Your Credentials", [])

        cred_frame = tk.Frame(container, bg="#1e1e1e")
        cred_frame.pack(fill='x', pady=10)

        tk.Label(cred_frame, text="Client ID:", fg="white", bg="#1e1e1e",
                font=("Segoe UI", 10)).grid(row=0, column=0, sticky='w', pady=5)
        client_id_entry = tk.Entry(cred_frame, textvariable=self.client_id_var,
                                   width=50, font=("Consolas", 10))
        client_id_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(cred_frame, text="Client Secret:", fg="white", bg="#1e1e1e",
                font=("Segoe UI", 10)).grid(row=1, column=0, sticky='w', pady=5)
        client_secret_entry = tk.Entry(cred_frame, textvariable=self.client_secret_var,
                                       width=50, font=("Consolas", 10), show="*")
        client_secret_entry.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(cred_frame, text="Your Twitch Username:", fg="white", bg="#1e1e1e",
                font=("Segoe UI", 10)).grid(row=2, column=0, sticky='w', pady=5)
        username_entry = tk.Entry(cred_frame, textvariable=self.username_var,
                                  width=50, font=("Consolas", 10))
        username_entry.grid(row=2, column=1, padx=10, pady=5)

        # Step 3: Authorize
        self._create_section(container, "Step 3: Authorize with Twitch", [
            "Click below to open Twitch and authorize the app."
        ])

        auth_frame = tk.Frame(container, bg="#1e1e1e")
        auth_frame.pack(fill='x', pady=10)

        self.btn_authorize = ttk.Button(auth_frame, text="Authorize with Twitch",
                                        command=self._start_oauth)
        self.btn_authorize.pack(side='left')

        status_label = tk.Label(auth_frame, textvariable=self.auth_status,
                               fg="#f39c12", bg="#1e1e1e", font=("Segoe UI", 10))
        status_label.pack(side='left', padx=20)

        # Save button
        self.btn_save = ttk.Button(container, text="Save & Start App",
                                   command=self._save_and_continue, state='disabled')
        self.btn_save.pack(pady=30)

        # Footer
        footer = tk.Label(self.root, text="Your credentials are stored locally and never shared.",
                         font=("Segoe UI", 8), fg="#666", bg="#1e1e1e")
        footer.pack(side='bottom', pady=10)

    def _create_section(self, parent, title, instructions):
        """Create a section with title and instruction list"""
        title_label = tk.Label(parent, text=title, font=("Segoe UI", 12, "bold"),
                              fg="#9147ff", bg="#1e1e1e", anchor='w')
        title_label.pack(fill='x', pady=(15, 5))

        for instruction in instructions:
            lbl = tk.Label(parent, text=instruction, font=("Segoe UI", 9),
                          fg="#ccc", bg="#1e1e1e", anchor='w', justify='left')
            lbl.pack(fill='x')

    def _start_oauth(self):
        """Start the OAuth flow"""
        client_id = self.client_id_var.get().strip()
        client_secret = self.client_secret_var.get().strip()

        if not client_id or not client_secret:
            messagebox.showerror("Missing Credentials",
                               "Please enter your Client ID and Client Secret first.")
            return

        self.auth_status.set("Waiting for authorization...")
        self.btn_authorize.config(state='disabled')

        # Start OAuth in background thread
        thread = threading.Thread(target=self._oauth_flow, args=(client_id, client_secret))
        thread.daemon = True
        thread.start()

    def _oauth_flow(self, client_id, client_secret):
        """Handle the OAuth flow in background"""
        try:
            # Start local server to receive callback
            server = http.server.HTTPServer(('localhost', REDIRECT_PORT), OAuthCallbackHandler)
            server.auth_code = None
            server.timeout = 120  # 2 minute timeout

            # Build authorization URL
            scopes = "user:read:follows chat:read chat:edit"
            auth_url = (
                f"https://id.twitch.tv/oauth2/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri={REDIRECT_URI}"
                f"&response_type=code"
                f"&scope={scopes.replace(' ', '%20')}"
            )

            # Open browser
            webbrowser.open(auth_url)

            # Wait for callback
            server.handle_request()

            if server.auth_code:
                # Exchange code for token
                token_response = requests.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'code': server.auth_code,
                        'grant_type': 'authorization_code',
                        'redirect_uri': REDIRECT_URI
                    }
                )

                if token_response.status_code == 200:
                    token_data = token_response.json()
                    self.access_token = token_data['access_token']
                    self.refresh_token = token_data.get('refresh_token', '')

                    self.root.after(0, self._on_auth_success)
                else:
                    error = token_response.json().get('message', 'Unknown error')
                    self.root.after(0, lambda: self._on_auth_failure(f"Token exchange failed: {error}"))
            else:
                self.root.after(0, lambda: self._on_auth_failure("Authorization was cancelled or failed"))

        except socket.error as e:
            self.root.after(0, lambda: self._on_auth_failure(f"Could not start callback server: {e}"))
        except Exception as e:
            self.root.after(0, lambda: self._on_auth_failure(str(e)))

    def _on_auth_success(self):
        """Called when OAuth succeeds"""
        self.auth_status.set("Authorized!")
        self.btn_save.config(state='normal')
        # Change status color to green
        for widget in self.root.winfo_children():
            self._update_status_color(widget, "#2ecc71")

    def _update_status_color(self, widget, color):
        """Recursively find and update status label color"""
        try:
            if hasattr(widget, 'cget') and widget.cget('textvariable'):
                # This is a label with textvariable
                pass
        except:
            pass
        for child in widget.winfo_children():
            self._update_status_color(child, color)

    def _on_auth_failure(self, error):
        """Called when OAuth fails"""
        self.auth_status.set("Failed - try again")
        self.btn_authorize.config(state='normal')
        messagebox.showerror("Authorization Failed", error)

    def _save_and_continue(self):
        """Save config and close wizard"""
        username = self.username_var.get().strip()
        if not username:
            messagebox.showerror("Missing Username", "Please enter your Twitch username.")
            return

        # Save to user_config.json
        user_config.update(
            twitch_client_id=self.client_id_var.get().strip(),
            twitch_client_secret=self.client_secret_var.get().strip(),
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            bot_username=username,
            main_username=username,
            setup_complete=True
        )

        # Show completion dialog with FameForecast branding
        self._show_completion_dialog()

    def _show_completion_dialog(self):
        """Show a branded completion dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Setup Complete")
        dialog.geometry("450x280")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        dialog.grab_set()

        # Center on parent
        dialog.transient(self.root)

        tk.Label(dialog, text="You're all set!",
                font=("Segoe UI", 18, "bold"), fg="#2ecc71", bg="#1e1e1e").pack(pady=(25, 10))

        tk.Label(dialog, text="Configuration saved successfully.",
                font=("Segoe UI", 11), fg="#ccc", bg="#1e1e1e").pack(pady=(0, 20))

        # FameForecast branding
        tk.Label(dialog, text="Built by FameForecast",
                font=("Segoe UI", 10, "bold"), fg="#9147ff", bg="#1e1e1e").pack()

        tk.Label(dialog, text="The talent showcase platform for content creators",
                font=("Segoe UI", 9), fg="#888", bg="#1e1e1e").pack(pady=(2, 15))

        # Buttons frame
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(pady=10)

        def open_fameforecast():
            webbrowser.open("https://fameforecast.com")

        def start_app():
            dialog.destroy()
            self.root.destroy()
            if self.on_complete:
                self.on_complete()

        ttk.Button(btn_frame, text="Visit FameForecast.com",
                  command=open_fameforecast).pack(side='left', padx=10)

        start_btn = tk.Button(btn_frame, text="Let's Go!",
                             command=start_app, bg="#9147ff", fg="white",
                             font=("Segoe UI", 10, "bold"), relief='flat',
                             padx=20, pady=5)
        start_btn.pack(side='left', padx=10)

    def run(self):
        """Start the wizard"""
        self.root.mainloop()


def run_setup_wizard(on_complete=None):
    """Convenience function to run the setup wizard"""
    wizard = SetupWizard(on_complete_callback=on_complete)
    wizard.run()


if __name__ == "__main__":
    # Test the wizard standalone
    run_setup_wizard()
