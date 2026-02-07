# twitch_chat_monitor/channel_selector.py
"""
GUI dialog for selecting which live channels to monitor.
Replaces console-based input() for the public build.
"""

import tkinter as tk
from tkinter import ttk


class ChannelSelectorDialog:
    def __init__(self, live_channels, follower_counts, live_data):
        """
        live_channels: list of channel names that are live
        follower_counts: dict of {channel: follower_count}
        live_data: dict of {channel: {game, viewers, etc}}
        """
        self.live_channels = live_channels
        self.follower_counts = follower_counts
        self.live_data = live_data
        self.selected_channels = set()
        self.result = None

        self.root = tk.Tk()
        self.root.title("FameForecastTextView - Select Channels")
        self.root.geometry("500x600")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(True, True)

        self._build_ui()

    def _build_ui(self):
        # Title
        title = tk.Label(self.root, text="Select Channels",
                        font=("Segoe UI", 16, "bold"), fg="#9147ff", bg="#1e1e1e")
        title.pack(pady=(20, 5))

        subtitle = tk.Label(self.root,
                           text=f"{len(self.live_channels)} channels are live",
                           font=("Segoe UI", 10), fg="#888", bg="#1e1e1e")
        subtitle.pack(pady=(0, 15))

        # Quick select buttons
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(fill='x', padx=20, pady=(0, 10))

        ttk.Button(btn_frame, text="Select All",
                  command=self._select_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Select None",
                  command=self._select_none).pack(side='left', padx=5)

        # Scrollable channel list
        list_frame = tk.Frame(self.root, bg="#2b2b2b")
        list_frame.pack(fill='both', expand=True, padx=20, pady=10)

        # Canvas for scrolling
        canvas = tk.Canvas(list_frame, bg="#2b2b2b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#2b2b2b")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Channel checkboxes
        self.check_vars = {}

        # Sort by followers (low to high)
        sorted_channels = sorted(self.live_channels,
                                key=lambda ch: self.follower_counts.get(ch.lower(), 0))

        for channel in sorted_channels:
            var = tk.BooleanVar(value=False)
            self.check_vars[channel] = var

            followers = self.follower_counts.get(channel.lower(), 0)
            game = self.live_data.get(channel.lower(), {}).get('game', 'Unknown')

            frame = tk.Frame(self.scrollable_frame, bg="#2b2b2b")
            frame.pack(fill='x', pady=2, padx=5)

            cb = tk.Checkbutton(frame, variable=var, bg="#2b2b2b",
                               activebackground="#2b2b2b", selectcolor="#4a4a4a",
                               fg="white", activeforeground="white",
                               highlightthickness=0, bd=0)
            cb.pack(side='left')

            # Channel name
            name_label = tk.Label(frame, text=channel,
                                 font=("Segoe UI", 11, "bold"),
                                 fg="white", bg="#2b2b2b", width=20, anchor='w')
            name_label.pack(side='left')

            # Follower count
            followers_str = f"{followers:,}"
            followers_label = tk.Label(frame, text=followers_str,
                                       font=("Segoe UI", 9),
                                       fg="#888", bg="#2b2b2b", width=12, anchor='e')
            followers_label.pack(side='left')

            # Game (truncated)
            game_display = game[:25] + "..." if len(game) > 25 else game
            game_label = tk.Label(frame, text=game_display,
                                 font=("Segoe UI", 9),
                                 fg="#666", bg="#2b2b2b", anchor='w')
            game_label.pack(side='left', padx=(10, 0))

        # Start button
        self.btn_start = ttk.Button(self.root, text="Let's Go",
                                    command=self._on_start)
        self.btn_start.pack(pady=20)

        # Footer
        footer = tk.Label(self.root,
                         text="Tip: You can join more channels later when they go live",
                         font=("Segoe UI", 8), fg="#666", bg="#1e1e1e")
        footer.pack(side='bottom', pady=10)

    def _select_all(self):
        for var in self.check_vars.values():
            var.set(True)

    def _select_none(self):
        for var in self.check_vars.values():
            var.set(False)

    def _on_start(self):
        self.selected_channels = {ch for ch, var in self.check_vars.items() if var.get()}
        self.result = self.selected_channels
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result if self.result is not None else set()


class NoLiveChannelsDialog:
    """Dialog shown when no channels are live"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FameForecastTextView")
        self.root.geometry("400x200")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)

        tk.Label(self.root, text="No Channels Live",
                font=("Segoe UI", 16, "bold"), fg="#9147ff", bg="#1e1e1e").pack(pady=(40, 10))

        tk.Label(self.root, text="None of your followed channels are currently streaming.",
                font=("Segoe UI", 10), fg="#888", bg="#1e1e1e").pack(pady=5)

        tk.Label(self.root, text="We'll notify you when they go live.",
                font=("Segoe UI", 10), fg="#888", bg="#1e1e1e").pack(pady=5)

        ttk.Button(self.root, text="Continue", command=self.root.destroy).pack(pady=20)

    def run(self):
        self.root.mainloop()


class LoadingDialog:
    """Simple loading dialog"""
    def __init__(self, message="Loading..."):
        self.root = tk.Tk()
        self.root.title("FameForecastTextView")
        self.root.geometry("300x100")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)  # No window decorations

        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 300) // 2
        y = (self.root.winfo_screenheight() - 100) // 2
        self.root.geometry(f"300x100+{x}+{y}")

        self.label = tk.Label(self.root, text=message,
                             font=("Segoe UI", 12), fg="white", bg="#1e1e1e")
        self.label.pack(expand=True)

    def update_message(self, message):
        self.label.config(text=message)
        self.root.update()

    def close(self):
        self.root.destroy()


def select_channels(live_channels, follower_counts, live_data):
    """
    Show channel selection dialog and return selected channels.
    Returns a set of channel names.
    """
    if not live_channels:
        dialog = NoLiveChannelsDialog()
        dialog.run()
        return set()

    dialog = ChannelSelectorDialog(live_channels, follower_counts, live_data)
    return dialog.run()
