import os
import json
import shutil
import sys
import signal
import subprocess
import threading
import queue
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_TITLE = "FAMILY-SAFE CUTTER // V4"

SUPPORTED_VIDEO_TYPES = (
    "*.mkv *.mp4 *.mov *.m4v *.webm *.avi *.ts"
)


# ============================================================
# COLORS
# ============================================================

BG = "#080C0A"
PANEL = "#0D1410"
PANEL_2 = "#101A14"
BORDER = "#1E3928"

GREEN = "#39FF88"
GREEN_DIM = "#208A4A"
GREEN_DARK = "#123D25"

TEXT = "#D9FFE5"
TEXT_DIM = "#71977E"

RED = "#FF5264"
RED_DARK = "#4D1820"

WHITE = "#FFFFFF"
BLACK = "#000000"


class FamilySafeCutter:

    # ========================================================
    # INIT
    # ========================================================

    def __init__(self, root):

        self.root = root
        self.root.title(APP_TITLE)

        self.root.geometry("1120x850")
        self.root.minsize(900, 680)

        self.input_file = ""
        self.output_file = ""

        self.duration = 0.0

        self.cuts = []

        self.media_info = {}

        self.audio_streams = []
        self.subtitle_streams = []
        self.attachment_streams = []

        self.process = None
        self.worker = None

        self.cancel_requested = False

        self.ui_queue = queue.Queue()

        self.preview_job = None
        self.preview_process = None
        self.preview_image = None

        self.start_time = 0.0
        self.end_time = 0.0

        self.active_handle = "start"

        self.dragging = False

        self.timeline_height = 90

        self.ffmpeg_override = None

        # ----------------------------------------------------
        # EXPORT STATE
        # ----------------------------------------------------

        self.export_started_at = None
        self.export_output_duration = 0.0

        self.export_temp_dir = None

        self.last_ffmpeg_error = ""

        self.build_ui()
        self.check_ffmpeg()

        self.root.after(
            100,
            self.poll_ui_queue
        )

    # ========================================================
    # WINDOWS / SUBPROCESS HELPERS
    # ========================================================

    @staticmethod
    def hidden_startupinfo():

        """
        Prevent Windows console windows from flashing whenever
        FFmpeg / FFprobe is launched.

        This is important for both preview seeking and export.
        """

        if os.name != "nt":
            return None

        startupinfo = subprocess.STARTUPINFO()

        startupinfo.dwFlags |= (
            subprocess.STARTF_USESHOWWINDOW
        )

        startupinfo.wShowWindow = (
            subprocess.SW_HIDE
        )

        return startupinfo

    def subprocess_kwargs(self):

        kwargs = {}

        startupinfo = (
            self.hidden_startupinfo()
        )

        if startupinfo is not None:

            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW
            )

        return kwargs

    # ========================================================
    # FFMPEG
    # ========================================================

    def get_assets_dir(self):
        """
        Returns the assets directory.

        Normal Python execution:

            FamilySafeCutter/
            ├── FamilySafeCutterV4.py
            └── assets/
                ├── ffmpeg.exe
                └── ffprobe.exe

        PyInstaller --onedir:

            FamilySafeCutter/
            ├── FamilySafeCutter.exe
            └── _internal/
                └── assets/
                    ├── ffmpeg.exe
                    └── ffprobe.exe

        PyInstaller --onefile:

            PyInstaller extracts bundled files into
            sys._MEIPASS at runtime.
        """

        # --------------------------------------------
        # PyInstaller
        # --------------------------------------------

        if getattr(sys, "frozen", False):

            bundle_dir = getattr(
                sys,
                "_MEIPASS",
                os.path.dirname(
                    sys.executable
                )
            )

            return os.path.join(
                bundle_dir,
                "assets"
            )

        # --------------------------------------------
        # Normal Python execution
        # --------------------------------------------

        return os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            "assets"
        )

    def find_executable(self, name):

        """
        Find FFmpeg/FFprobe ONLY from the application's
        bundled assets directory.

        The user does not need FFmpeg installed.
        """

        exe_name = (
            name
            if name.lower().endswith(".exe")
            else name + ".exe"
        )

        assets_dir = self.get_assets_dir()

        executable = os.path.join(
            assets_dir,
            exe_name
        )

        if os.path.isfile(executable):

            return executable

        return None

    def find_ffmpeg(self):

        if self.ffmpeg_override:

            if os.path.isfile(
                self.ffmpeg_override
            ):

                return self.ffmpeg_override

        return self.find_executable(
            "ffmpeg"
        )

    def find_ffprobe(self):

        return self.find_executable(
            "ffprobe"
        )

    def check_ffmpeg(self):

        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        if ffmpeg:

            self.ffmpeg_status.set(
                "FFMPEG  ● ONLINE"
            )

        else:

            self.ffmpeg_status.set(
                "FFMPEG  ● MISSING"
            )

        if ffprobe:

            self.ffprobe_status.set(
                "FFPROBE  ● ONLINE"
            )

        else:

            self.ffprobe_status.set(
                "FFPROBE  ● MISSING"
            )

        if ffmpeg and ffprobe:

            self.status_var.set(
                "SYSTEM READY // WAITING FOR INPUT"
            )

        else:

            self.status_var.set(
                "FFMPEG ASSETS MISSING"
            )
        
    

    # ========================================================
    # STYLE
    # ========================================================

    def build_style(self):

        style = ttk.Style()

        try:

            style.theme_use("clam")

        except tk.TclError:

            pass

        style.configure(
            ".",
            background=BG,
            foreground=TEXT,
            font=("Cascadia Mono", 10),
        )

        style.configure(
            "TFrame",
            background=BG,
        )

        style.configure(
            "Panel.TFrame",
            background=PANEL,
        )

        style.configure(
            "TLabel",
            background=BG,
            foreground=TEXT,
        )

        style.configure(
            "Dim.TLabel",
            background=BG,
            foreground=TEXT_DIM,
        )

        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=GREEN,
            font=("Cascadia Mono", 20, "bold"),
        )

        style.configure(
            "Subtitle.TLabel",
            background=BG,
            foreground=TEXT_DIM,
            font=("Cascadia Mono", 9),
        )

        style.configure(
            "Section.TLabelframe",
            background=PANEL,
            foreground=GREEN,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )

        style.configure(
            "Section.TLabelframe.Label",
            background=PANEL,
            foreground=GREEN,
            font=("Cascadia Mono", 10, "bold"),
        )

        style.configure(
            "TButton",
            background=PANEL_2,
            foreground=GREEN,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(12, 7),
            font=("Cascadia Mono", 9, "bold"),
        )

        style.map(
            "TButton",
            background=[
                ("active", GREEN_DARK),
                ("pressed", GREEN_DARK),
            ],
            foreground=[
                ("active", WHITE),
                ("pressed", WHITE),
            ],
        )

        style.configure(
            "Export.TButton",
            background=GREEN_DARK,
            foreground=GREEN,
            padding=(18, 9),
            font=("Cascadia Mono", 10, "bold"),
        )

        style.map(
            "Export.TButton",
            background=[
                ("active", GREEN),
                ("pressed", GREEN),
            ],
            foreground=[
                ("active", BLACK),
                ("pressed", BLACK),
            ],
        )

        style.configure(
            "Danger.TButton",
            background=RED_DARK,
            foreground=RED,
        )

        style.configure(
            "TEntry",
            fieldbackground="#09110C",
            foreground=TEXT,
            insertcolor=GREEN,
            bordercolor=BORDER,
        )

        style.configure(
            "TCombobox",
            fieldbackground="#09110C",
            background=PANEL,
            foreground=TEXT,
            arrowcolor=GREEN,
        )

        style.configure(
            "Horizontal.TProgressbar",
            background=GREEN,
            troughcolor="#142018",
            bordercolor=BORDER,
            lightcolor=GREEN,
            darkcolor=GREEN,
        )

    # ========================================================
    # GUI
    # ========================================================

    def build_ui(self):

        self.build_style()

        self.status_var = tk.StringVar(
            value="SYSTEM INITIALIZING..."
        )

        self.ffmpeg_status = tk.StringVar(
            value="FFMPEG  ● CHECKING"
        )

        self.ffprobe_status = tk.StringVar(
            value="FFPROBE  ● CHECKING"
        )

        self.duration_var = tk.StringVar(
            value="DURATION // --:--:--.---"
        )

        self.current_time_var = tk.StringVar(
            value="00:00:00.000"
        )

        self.start_var = tk.StringVar(
            value="00:00:00.000"
        )

        self.end_var = tk.StringVar(
            value="00:00:00.000"
        )

        self.output_var = tk.StringVar()

        self.quality_var = tk.StringVar(
            value="Very High"
        )

        self.export_info_var = tk.StringVar(
            value="EXPORT IDLE"
        )

        # ----------------------------------------------------
        # ROOT
        # ----------------------------------------------------

        root_frame = ttk.Frame(
            self.root
        )

        root_frame.pack(
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header = ttk.Frame(
            root_frame,
            padding=(18, 14, 18, 8)
        )

        header.pack(
            fill="x"
        )

        ttk.Label(
            header,
            text="FAMILY-SAFE CUTTER",
            style="Title.TLabel"
        ).pack(
            side="left"
        )

        ttk.Label(
            header,
            text=" // V4.0",
            style="Subtitle.TLabel"
        ).pack(
            side="left",
            padx=(5, 0),
            pady=(7, 0)
        )

        # ----------------------------------------------------
        # SCROLLABLE MAIN AREA
        # ----------------------------------------------------

        main_area = ttk.Frame(
            root_frame
        )

        main_area.pack(
            fill="both",
            expand=True
        )

        self.main_canvas = tk.Canvas(
            main_area,
            background=BG,
            highlightthickness=0,
            borderwidth=0,
        )

        self.main_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar = ttk.Scrollbar(
            main_area,
            orient="vertical",
            command=self.main_canvas.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.main_canvas.configure(
            yscrollcommand=scrollbar.set
        )

        content = ttk.Frame(
            self.main_canvas,
            padding=(18, 5, 18, 18)
        )

        self.main_window = (
            self.main_canvas.create_window(
                (0, 0),
                window=content,
                anchor="nw"
            )
        )

        def update_scroll(event=None):

            self.main_canvas.configure(
                scrollregion=self.main_canvas.bbox(
                    "all"
                )
            )

        content.bind(
            "<Configure>",
            update_scroll
        )

        def resize_content(event):

            self.main_canvas.itemconfigure(
                self.main_window,
                width=event.width
            )

        self.main_canvas.bind(
            "<Configure>",
            resize_content
        )

        self.main_canvas.bind_all(
            "<MouseWheel>",
            self.mousewheel
        )

        # ====================================================
        # INPUT
        # ====================================================

        input_frame = ttk.LabelFrame(
            content,
            text="[ 01 // INPUT MEDIA ]",
            style="Section.TLabelframe",
            padding=12
        )

        input_frame.pack(
            fill="x",
            pady=6
        )

        self.input_entry = ttk.Entry(
            input_frame,
            state="readonly"
        )

        self.input_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        ttk.Button(
            input_frame,
            text="BROWSE",
            command=self.choose_input
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # ====================================================
        # PREVIEW
        # ====================================================

        preview_frame = ttk.LabelFrame(
            content,
            text="[ 02 // FRAME PREVIEW ]",
            style="Section.TLabelframe",
            padding=12
        )

        preview_frame.pack(
            fill="x",
            pady=6
        )

        preview_holder = tk.Frame(
            preview_frame,
            bg="#050805",
            height=350,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        preview_holder.pack(
            fill="x"
        )

        preview_holder.pack_propagate(False)

        self.preview_label = tk.Label(
            preview_holder,
            text="NO MEDIA LOADED",
            bg="#050805",
            fg=TEXT_DIM,
            font=("Cascadia Mono", 11)
        )

        self.preview_label.pack(
            fill="both",
            expand=True
        )

        preview_info = ttk.Frame(
            preview_frame
        )

        preview_info.pack(
            fill="x",
            pady=(8, 0)
        )

        ttk.Label(
            preview_info,
            textvariable=self.current_time_var,
            foreground=GREEN,
            font=("Cascadia Mono", 13, "bold")
        ).pack(
            side="left"
        )

        ttk.Label(
            preview_info,
            textvariable=self.duration_var,
            foreground=TEXT_DIM,
            font=("Cascadia Mono", 9)
        ).pack(
            side="right"
        )

        # ====================================================
        # TIMELINE
        # ====================================================

        timeline_frame = ttk.LabelFrame(
            content,
            text="[ 03 // CUT TIMELINE ]",
            style="Section.TLabelframe",
            padding=12
        )

        timeline_frame.pack(
            fill="x",
            pady=6
        )

        self.timeline = tk.Canvas(
            timeline_frame,
            height=90,
            background="#09110C",
            highlightthickness=1,
            highlightbackground=BORDER
        )

        self.timeline.pack(
            fill="x"
        )

        self.timeline.bind(
            "<Configure>",
            self.on_timeline_resize
        )

        self.timeline.bind(
            "<Button-1>",
            self.timeline_mouse_down
        )

        self.timeline.bind(
            "<B1-Motion>",
            self.timeline_mouse_drag
        )

        self.timeline.bind(
            "<ButtonRelease-1>",
            self.timeline_mouse_up
        )

        self.timeline.bind(
            "<Motion>",
            self.timeline_mouse_move
        )

        self.timeline.bind(
            "<Left>",
            lambda e: self.keyboard_move(-0.1)
        )

        self.timeline.bind(
            "<Right>",
            lambda e: self.keyboard_move(0.1)
        )

        self.timeline.bind(
            "<Shift-Left>",
            lambda e: self.keyboard_move(-1.0)
        )

        self.timeline.bind(
            "<Shift-Right>",
            lambda e: self.keyboard_move(1.0)
        )

        # ----------------------------------------------------
        # TIME CONTROLS
        # ----------------------------------------------------

        time_row = ttk.Frame(
            timeline_frame
        )

        time_row.pack(
            fill="x",
            pady=(10, 0)
        )

        ttk.Label(
            time_row,
            text="START"
        ).pack(
            side="left"
        )

        ttk.Label(
            time_row,
            textvariable=self.start_var,
            foreground=GREEN,
            font=("Cascadia Mono", 10, "bold")
        ).pack(
            side="left",
            padx=(7, 25)
        )

        ttk.Label(
            time_row,
            text="END"
        ).pack(
            side="left"
        )

        ttk.Label(
            time_row,
            textvariable=self.end_var,
            foreground=RED,
            font=("Cascadia Mono", 10, "bold")
        ).pack(
            side="left",
            padx=7
        )

        ttk.Button(
            time_row,
            text="+ ADD CUT",
            command=self.add_current_cut
        ).pack(
            side="right"
        )

        ttk.Label(
            timeline_frame,
            text=(
                "Drag handles  //  ← → = 0.1 sec  "
                "//  SHIFT + ← → = 1 sec"
            ),
            foreground=TEXT_DIM
        ).pack(
            anchor="w",
            pady=(8, 0)
        )

        # ====================================================
        # CUT LIST
        # ====================================================

        cuts_frame = ttk.LabelFrame(
            content,
            text="[ 04 // CUTS ]",
            style="Section.TLabelframe",
            padding=12
        )

        cuts_frame.pack(
            fill="x",
            pady=6
        )

        list_container = ttk.Frame(
            cuts_frame
        )

        list_container.pack(
            fill="x"
        )

        self.cut_list = tk.Listbox(
            list_container,
            height=6,
            bg="#080F0B",
            fg=GREEN,
            selectbackground=GREEN_DARK,
            selectforeground=WHITE,
            highlightthickness=1,
            highlightbackground=BORDER,
            relief="flat",
            font=("Cascadia Mono", 10)
        )

        self.cut_list.pack(
            side="left",
            fill="both",
            expand=True
        )

        cut_scroll = ttk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.cut_list.yview
        )

        cut_scroll.pack(
            side="right",
            fill="y"
        )

        self.cut_list.configure(
            yscrollcommand=cut_scroll.set
        )

        cut_buttons = ttk.Frame(
            cuts_frame
        )

        cut_buttons.pack(
            fill="x",
            pady=(8, 0)
        )

        ttk.Button(
            cut_buttons,
            text="REMOVE SELECTED",
            command=self.remove_selected_cut,
            style="Danger.TButton"
        ).pack(
            side="left"
        )

        ttk.Button(
            cut_buttons,
            text="CLEAR ALL",
            command=self.clear_cuts
        ).pack(
            side="left",
            padx=8
        )

        # ====================================================
        # STREAM INFO
        # ====================================================

        info_frame = ttk.LabelFrame(
            content,
            text="[ MEDIA STREAMS ]",
            style="Section.TLabelframe",
            padding=12
        )

        info_frame.pack(
            fill="x",
            pady=6
        )

        self.stream_info_var = tk.StringVar(
            value="NO MEDIA LOADED"
        )

        ttk.Label(
            info_frame,
            textvariable=self.stream_info_var,
            foreground=TEXT_DIM
        ).pack(
            anchor="w"
        )

        # ====================================================
        # OUTPUT
        # ====================================================

        output_frame = ttk.LabelFrame(
            content,
            text="[ 05 // OUTPUT ]",
            style="Section.TLabelframe",
            padding=12
        )

        output_frame.pack(
            fill="x",
            pady=6
        )

        self.output_entry = ttk.Entry(
            output_frame,
            textvariable=self.output_var
        )

        self.output_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        ttk.Button(
            output_frame,
            text="SAVE AS",
            command=self.choose_output
        ).pack(
            side="left",
            padx=(10, 0)
        )

        settings = ttk.Frame(
            output_frame
        )

        settings.pack(
            fill="x",
            pady=(10, 0)
        )

        ttk.Label(
            settings,
            text="ENCODING QUALITY"
        ).pack(
            side="left"
        )

        ttk.Combobox(
            settings,
            textvariable=self.quality_var,
            values=[
                "Very High",
                "High",
                "Balanced"
            ],
            state="readonly",
            width=16
        ).pack(
            side="left",
            padx=10
        )

        # ====================================================
        # EXPORT INFORMATION
        # ====================================================

        export_info_frame = ttk.Frame(
            output_frame
        )

        export_info_frame.pack(
            fill="x",
            pady=(10, 0)
        )

        ttk.Label(
            export_info_frame,
            textvariable=self.export_info_var,
            foreground=TEXT_DIM,
            font=("Cascadia Mono", 9)
        ).pack(
            anchor="w"
        )

        # ====================================================
        # BOTTOM STATUS BAR
        # ====================================================

        bottom = tk.Frame(
            root_frame,
            bg="#050805",
            highlightthickness=1,
            highlightbackground=BORDER
        )

        bottom.pack(
            side="bottom",
            fill="x"
        )

        self.progress = ttk.Progressbar(
            bottom,
            maximum=100,
            style="Horizontal.TProgressbar"
        )

        self.progress.pack(
            fill="x"
        )

        status_row = tk.Frame(
            bottom,
            bg="#050805"
        )

        status_row.pack(
            fill="x",
            padx=12,
            pady=8
        )

        self.status_label = tk.Label(
            status_row,
            textvariable=self.status_var,
            bg="#050805",
            fg=GREEN,
            anchor="w",
            font=("Cascadia Mono", 9)
        )

        self.status_label.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Label(
            status_row,
            textvariable=self.ffmpeg_status,
            bg="#050805",
            fg=GREEN_DIM,
            font=("Cascadia Mono", 8)
        ).pack(
            side="left",
            padx=8
        )

        tk.Label(
            status_row,
            textvariable=self.ffprobe_status,
            bg="#050805",
            fg=GREEN_DIM,
            font=("Cascadia Mono", 8)
        ).pack(
            side="left",
            padx=8
        )

        self.cancel_button = ttk.Button(
            status_row,
            text="CANCEL",
            command=self.cancel_export,
            state="disabled"
        )

        self.cancel_button.pack(
            side="right",
            padx=(8, 0)
        )

        self.export_button = ttk.Button(
            status_row,
            text=">> EXPORT FAMILY-SAFE VIDEO",
            command=self.start_export,
            style="Export.TButton"
        )

        self.export_button.pack(
            side="right"
        )

    # ========================================================
    # MOUSE WHEEL
    # ========================================================

    def mousewheel(self, event):

        try:

            self.main_canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )

        except Exception:

            pass

    # ========================================================
    # INPUT
    # ========================================================

    def choose_input(self):

        path = filedialog.askopenfilename(
            title="Select Video",
            filetypes=[
                (
                    "Common video files",
                    SUPPORTED_VIDEO_TYPES
                ),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        self.input_file = path

        self.input_entry.configure(
            state="normal"
        )

        self.input_entry.delete(
            0,
            tk.END
        )

        self.input_entry.insert(
            0,
            path
        )

        self.input_entry.configure(
            state="readonly"
        )

        base, _ = os.path.splitext(path)

        self.output_file = (
            base + " - Family.mkv"
        )

        self.output_var.set(
            self.output_file
        )

        self.cuts.clear()
        self.refresh_cut_list()

        self.duration = 0.0
        self.start_time = 0.0
        self.end_time = 0.0

        self.preview_label.configure(
            image="",
            text="READING MEDIA..."
        )

        self.status_var.set(
            "PROBING MEDIA STREAMS..."
        )

        self.export_info_var.set(
            "EXPORT IDLE"
        )

        threading.Thread(
            target=self.probe_media,
            daemon=True
        ).start()

    def choose_output(self):

        path = filedialog.asksaveasfilename(
            title="Save Family-Safe Video",
            defaultextension=".mkv",
            filetypes=[
                ("Matroska video", "*.mkv"),
                ("MP4 video", "*.mp4"),
                ("MOV video", "*.mov"),
                ("All files", "*.*")
            ]
        )

        if path:

            self.output_file = path

            self.output_var.set(
                path
            )

    # ========================================================
    # PROBE
    # ========================================================

    def probe_media(self):

        ffprobe = self.find_ffprobe()

        if not ffprobe:

            self.ui_queue.put(
                (
                    "error",
                    "ffprobe.exe was not found."
                )
            )

            return

        command = [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            self.input_file
        ]

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **self.subprocess_kwargs()
            )

            if result.returncode != 0:

                raise RuntimeError(
                    result.stderr.strip()
                    or "ffprobe failed."
                )

            info = json.loads(
                result.stdout
            )

            self.media_info = info

            format_info = info.get(
                "format",
                {}
            )

            duration = float(
                format_info.get(
                    "duration",
                    0
                )
            )

            streams = info.get(
                "streams",
                []
            )

            self.audio_streams = [
                s for s in streams
                if s.get("codec_type") == "audio"
            ]

            self.subtitle_streams = [
                s for s in streams
                if s.get("codec_type") == "subtitle"
            ]

            self.attachment_streams = [
                s for s in streams
                if s.get("codec_type") == "attachment"
            ]

            self.duration = duration

            self.start_time = 0.0
            self.end_time = duration

            self.ui_queue.put(
                (
                    "media_loaded",
                    {
                        "duration": duration,
                        "audio": len(
                            self.audio_streams
                        ),
                        "subtitles": len(
                            self.subtitle_streams
                        ),
                        "attachments": len(
                            self.attachment_streams
                        )
                    }
                )
            )

            self.request_preview(0)

        except Exception as exc:

            self.ui_queue.put(
                (
                    "error",
                    f"Could not read media information:\n\n{exc}"
                )
            )

    # ========================================================
    # TIME
    # ========================================================

    @staticmethod
    def format_time(seconds):

        seconds = max(
            0.0,
            float(seconds)
        )

        hours = int(
            seconds // 3600
        )

        minutes = int(
            (seconds % 3600) // 60
        )

        secs = seconds % 60

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:06.3f}"
        )

    @staticmethod
    def format_duration_short(seconds):

        seconds = max(
            0,
            int(seconds)
        )

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:

            return (
                f"{hours}h "
                f"{minutes:02d}m "
                f"{secs:02d}s"
            )

        if minutes > 0:

            return (
                f"{minutes}m "
                f"{secs:02d}s"
            )

        return f"{secs}s"

    # ========================================================
    # TIMELINE
    # ========================================================

    def on_timeline_resize(self, event=None):

        self.draw_timeline()

    def timeline_x_from_time(self, seconds):

        if self.duration <= 0:
            return 20

        left = 20

        right = max(
            left + 1,
            self.timeline.winfo_width() - 20
        )

        ratio = (
            seconds / self.duration
        )

        return (
            left
            + ratio * (right - left)
        )

    def timeline_time_from_x(self, x):

        left = 20

        right = max(
            left + 1,
            self.timeline.winfo_width() - 20
        )

        x = max(
            left,
            min(right, x)
        )

        ratio = (
            x - left
        ) / (right - left)

        return (
            ratio * self.duration
        )

    def draw_timeline(self):

        self.timeline.delete(
            "all"
        )

        width = max(
            1,
            self.timeline.winfo_width()
        )

        self.timeline.create_rectangle(
            20,
            30,
            width - 20,
            60,
            fill="#152119",
            outline="#31533C"
        )

        if self.duration <= 0:

            self.timeline.create_text(
                width / 2,
                45,
                text="LOAD MEDIA",
                fill=TEXT_DIM,
                font=("Cascadia Mono", 9)
            )

            return

        # ----------------------------------------------------
        # CUTS
        # ----------------------------------------------------

        for start, end in self.cuts:

            x1 = self.timeline_x_from_time(
                start
            )

            x2 = self.timeline_x_from_time(
                end
            )

            self.timeline.create_rectangle(
                x1,
                30,
                x2,
                60,
                fill="#561B24",
                outline=RED
            )

        # ----------------------------------------------------
        # HANDLES
        # ----------------------------------------------------

        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        self.timeline.create_line(
            sx,
            15,
            sx,
            75,
            fill=GREEN,
            width=3
        )

        self.timeline.create_oval(
            sx - 7,
            22,
            sx + 7,
            36,
            fill=GREEN,
            outline=WHITE
        )

        self.timeline.create_line(
            ex,
            15,
            ex,
            75,
            fill=RED,
            width=3
        )

        self.timeline.create_oval(
            ex - 7,
            54,
            ex + 7,
            68,
            fill=RED,
            outline=WHITE
        )

        # ----------------------------------------------------
        # TIME LABELS
        # ----------------------------------------------------

        self.timeline.create_text(
            20,
            10,
            anchor="w",
            text=self.format_time(0),
            fill=TEXT_DIM,
            font=("Cascadia Mono", 8)
        )

        self.timeline.create_text(
            width - 20,
            10,
            anchor="e",
            text=self.format_time(
                self.duration
            ),
            fill=TEXT_DIM,
            font=("Cascadia Mono", 8)
        )

        # ----------------------------------------------------
        # CURRENT MARKER
        # ----------------------------------------------------

        current = (
            self.start_time
            if self.active_handle == "start"
            else self.end_time
        )

        cx = self.timeline_x_from_time(
            current
        )

        self.timeline.create_line(
            cx,
            5,
            cx,
            75,
            fill=WHITE,
            width=1,
            dash=(3, 3)
        )

    def nearest_handle(self, x):

        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        if abs(x - sx) <= 12:
            return "start"

        if abs(x - ex) <= 12:
            return "end"

        return (
            "start"
            if abs(x - sx) <= abs(x - ex)
            else "end"
        )

    def set_handle_from_x(self, x):

        if self.duration <= 0:
            return

        seconds = self.timeline_time_from_x(
            x
        )

        if self.active_handle == "start":

            seconds = min(
                seconds,
                self.end_time - 0.01
            )

            self.start_time = max(
                0,
                seconds
            )

        else:

            seconds = max(
                seconds,
                self.start_time + 0.01
            )

            self.end_time = min(
                self.duration,
                seconds
            )

        self.update_handle_labels()
        self.draw_timeline()

        self.request_preview(
            seconds
        )

    def timeline_mouse_down(self, event):

        if self.duration <= 0:
            return

        self.timeline.focus_set()

        self.active_handle = (
            self.nearest_handle(
                event.x
            )
        )

        self.dragging = True

        self.set_handle_from_x(
            event.x
        )

    def timeline_mouse_drag(self, event):

        if self.dragging:

            self.set_handle_from_x(
                event.x
            )

    def timeline_mouse_up(self, event):

        self.dragging = False

    def timeline_mouse_move(self, event):

        if self.duration <= 0:
            return

        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        if (
            abs(event.x - sx) <= 10
            or abs(event.x - ex) <= 10
        ):

            self.timeline.configure(
                cursor="hand2"
            )

        else:

            self.timeline.configure(
                cursor="arrow"
            )

    def keyboard_move(self, amount):

        if self.duration <= 0:
            return

        if self.active_handle == "start":

            self.start_time = max(
                0,
                min(
                    self.end_time - 0.01,
                    self.start_time + amount
                )
            )

            current = self.start_time

        else:

            self.end_time = min(
                self.duration,
                max(
                    self.start_time + 0.01,
                    self.end_time + amount
                )
            )

            current = self.end_time

        self.update_handle_labels()
        self.draw_timeline()

        self.request_preview(
            current
        )

    def update_handle_labels(self):

        self.start_var.set(
            self.format_time(
                self.start_time
            )
        )

        self.end_var.set(
            self.format_time(
                self.end_time
            )
        )

        current = (
            self.start_time
            if self.active_handle == "start"
            else self.end_time
        )

        self.current_time_var.set(
            self.format_time(
                current
            )
        )

    # ========================================================
    # PREVIEW
    # ========================================================

    def request_preview(self, seconds):

        if not self.input_file:
            return

        if self.preview_job:

            try:

                self.root.after_cancel(
                    self.preview_job
                )

            except Exception:

                pass

        self.preview_job = self.root.after(
            300,
            lambda: self.generate_preview(
                seconds
            )
        )

    def generate_preview(self, seconds):

        self.preview_job = None

        ffmpeg = self.find_ffmpeg()

        if not ffmpeg:
            return

        if self.preview_process:

            try:

                self.preview_process.kill()

            except Exception:

                pass

        temp_dir = os.path.join(
            os.path.dirname(
                self.input_file
            ),
            ".family_safe_preview"
        )

        try:

            os.makedirs(
                temp_dir,
                exist_ok=True
            )

        except Exception:

            return

        preview_path = os.path.join(
            temp_dir,
            "preview.png"
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",

            "-ss",
            f"{seconds:.3f}",

            "-i",
            self.input_file,

            "-frames:v",
            "1",

            "-vf",
            "scale=900:-2",

            "-y",
            preview_path
        ]

        def wait_for_preview():

            try:

                self.preview_process.wait()

                if (
                    self.preview_process.returncode == 0
                    and os.path.exists(
                        preview_path
                    )
                ):

                    self.ui_queue.put(
                        (
                            "preview",
                            preview_path
                        )
                    )

            except Exception:

                pass

        try:

            self.preview_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **self.subprocess_kwargs()
            )

            threading.Thread(
                target=wait_for_preview,
                daemon=True
            ).start()

        except Exception:

            pass

    def show_preview(self, path):

        try:

            image = tk.PhotoImage(
                file=path
            )

            self.preview_image = image

            self.preview_label.configure(
                image=image,
                text=""
            )

        except Exception as exc:

            self.preview_label.configure(
                image="",
                text=f"PREVIEW ERROR\n{exc}"
            )

    # ========================================================
    # CUT MANAGEMENT
    # ========================================================

    def normalize_cuts(self):

        if not self.cuts:
            return []

        sorted_cuts = sorted(
            self.cuts,
            key=lambda x: x[0]
        )

        merged = [
            list(sorted_cuts[0])
        ]

        for start, end in sorted_cuts[1:]:

            previous = merged[-1]

            if start <= previous[1]:

                previous[1] = max(
                    previous[1],
                    end
                )

            else:

                merged.append(
                    [start, end]
                )

        return [
            tuple(item)
            for item in merged
        ]

    def add_current_cut(self):

        if self.duration <= 0:

            messagebox.showerror(
                "NO MEDIA",
                "Load a video first."
            )

            return

        if self.end_time <= self.start_time:

            messagebox.showerror(
                "INVALID RANGE",
                "END must be after START."
            )

            return

        self.cuts.append(
            (
                self.start_time,
                self.end_time
            )
        )

        self.cuts = self.normalize_cuts()

        self.refresh_cut_list()
        self.draw_timeline()

        index = len(self.cuts) - 1

        if index >= 0:

            self.cut_list.selection_clear(
                0,
                tk.END
            )

            self.cut_list.selection_set(
                index
            )

            self.cut_list.see(
                index
            )

        self.status_var.set(
            "CUT ADDED // "
            f"{self.format_time(self.start_time)}"
            " → "
            f"{self.format_time(self.end_time)}"
        )

        next_start = min(
            self.end_time + 0.01,
            self.duration
        )

        self.start_time = next_start
        self.end_time = self.duration

        self.active_handle = "start"

        self.update_handle_labels()
        self.draw_timeline()

    def refresh_cut_list(self):

        self.cut_list.delete(
            0,
            tk.END
        )

        for number, (start, end) in enumerate(
            self.cuts,
            1
        ):

            self.cut_list.insert(
                tk.END,
                (
                    f"[{number:02d}]  "
                    f"{self.format_time(start)}"
                    f"  →  "
                    f"{self.format_time(end)}"
                )
            )

    def remove_selected_cut(self):

        selected = list(
            self.cut_list.curselection()
        )

        if not selected:
            return

        for index in reversed(selected):

            del self.cuts[index]

        self.refresh_cut_list()
        self.draw_timeline()

        self.status_var.set(
            "SELECTED CUT REMOVED"
        )

    def clear_cuts(self):

        if not self.cuts:
            return

        answer = messagebox.askyesno(
            "CLEAR CUTS",
            "Remove all cuts?"
        )

        if not answer:
            return

        self.cuts.clear()

        self.refresh_cut_list()
        self.draw_timeline()

        self.status_var.set(
            "ALL CUTS CLEARED"
        )

    # ========================================================
    # EXPORT CALCULATIONS
    # ========================================================

    def get_crf(self):

        quality = self.quality_var.get()

        if quality == "Very High":
            return "16"

        if quality == "High":
            return "18"

        return "20"

    def calculate_kept_segments(self):

        cuts = self.normalize_cuts()

        kept = []

        cursor = 0.0

        for start, end in cuts:

            if start > cursor:

                kept.append(
                    (
                        cursor,
                        start
                    )
                )

            cursor = max(
                cursor,
                end
            )

        if cursor < self.duration:

            kept.append(
                (
                    cursor,
                    self.duration
                )
            )

        return kept

    def calculate_output_duration(self):

        return sum(
            end - start
            for start, end in self.calculate_kept_segments()
        )

    # ========================================================
    # FILTER COMPLEX
    # ========================================================

    def build_filter_complex(self):

        kept = (
            self.calculate_kept_segments()
        )

        if not kept:

            raise ValueError(
                "The cuts remove the entire video."
            )

        parts = []

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        video_labels = []

        for index, (
            start,
            end
        ) in enumerate(kept):

            label = f"v{index}"

            parts.append(
                (
                    f"[0:v]"
                    f"trim=start={start:.6f}:"
                    f"end={end:.6f},"
                    f"setpts=PTS-STARTPTS"
                    f"[{label}]"
                )
            )

            video_labels.append(
                f"[{label}]"
            )

        parts.append(
            (
                "".join(video_labels)
                + f"concat=n={len(kept)}:"
                  "v=1:a=0[vout]"
            )
        )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        audio_labels = []

        for audio_index, stream in enumerate(
            self.audio_streams
        ):

            stream_index = stream["index"]

            labels = []

            for segment_index, (
                start,
                end
            ) in enumerate(kept):

                label = (
                    f"a{audio_index}_{segment_index}"
                )

                parts.append(
                    (
                        f"[0:{stream_index}]"
                        f"atrim=start={start:.6f}:"
                        f"end={end:.6f},"
                        f"asetpts=PTS-STARTPTS"
                        f"[{label}]"
                    )
                )

                labels.append(
                    f"[{label}]"
                )

            out_label = (
                f"aout{audio_index}"
            )

            parts.append(
                (
                    "".join(labels)
                    + f"concat=n={len(kept)}:"
                      "v=0:a=1"
                    f"[{out_label}]"
                )
            )

            audio_labels.append(
                out_label
            )

        return (
            ";".join(parts),
            audio_labels
        )

    # ========================================================
    # SUBTITLE PREPARATION
    # ========================================================

    def prepare_subtitles(
        self,
        temp_dir
    ):

        """
        Extract and retime every SubRip subtitle stream.

        Returns:

            [
                {
                    "path": retimed_srt_path,
                    "stream": original_stream
                }
            ]
        """

        if not self.subtitle_streams:
            return []

        ffmpeg = self.find_ffmpeg()

        if not ffmpeg:

            raise RuntimeError(
                "FFmpeg not found."
            )

        prepared = []

        for number, stream in enumerate(
            self.subtitle_streams
        ):

            codec = (
                stream.get(
                    "codec_name",
                    ""
                )
                .lower()
            )

            if codec != "subrip":

                self.ui_queue.put(
                    (
                        "status",
                        "Skipping unsupported subtitle "
                        f"format: {codec}"
                    )
                )

                continue

            original_path = os.path.join(
                temp_dir,
                f"subtitle_{number:03d}_original.srt"
            )

            retimed_path = os.path.join(
                temp_dir,
                f"subtitle_{number:03d}_retimed.srt"
            )

            self.ui_queue.put(
                (
                    "status",
                    f"Preparing subtitle "
                    f"{number + 1}/"
                    f"{len(self.subtitle_streams)}..."
                )
            )

            self.extract_subtitle(
                ffmpeg,
                stream,
                original_path
            )

            self.retime_srt(
                original_path,
                retimed_path
            )

            if os.path.isfile(
                retimed_path
            ):

                prepared.append(
                    {
                        "path": retimed_path,
                        "stream": stream
                    }
                )

        return prepared

    # ========================================================
    # EXTRACT SUBTITLE
    # ========================================================

    def extract_subtitle(
        self,
        ffmpeg,
        stream,
        output_path
    ):

        stream_index = stream["index"]

        command = [
            ffmpeg,

            "-hide_banner",
            "-loglevel",
            "error",

            "-i",
            self.input_file,

            "-map",
            f"0:{stream_index}",

            "-c:s",
            "srt",

            "-y",

            output_path
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **self.subprocess_kwargs()
        )

        if result.returncode != 0:

            raise RuntimeError(
                "Could not extract subtitle stream.\n\n"
                + (
                    result.stderr.strip()
                    or "Unknown FFmpeg subtitle error."
                )
            )

        if not os.path.isfile(
            output_path
        ):

            raise RuntimeError(
                "FFmpeg did not create the temporary "
                "subtitle file."
            )

    # ========================================================
    # RETIME SRT
    # ========================================================

    def retime_srt(
        self,
        original_path,
        retimed_path
    ):

        kept = (
            self.calculate_kept_segments()
        )

        with open(
            original_path,
            "r",
            encoding="utf-8-sig",
            errors="replace"
        ) as file:

            text = file.read()

        blocks = text.replace(
            "\r\n",
            "\n"
        ).split(
            "\n\n"
        )

        output_blocks = []

        output_offset = 0.0

        for seg_start, seg_end in kept:

            for block in blocks:

                lines = block.splitlines()

                if len(lines) < 3:
                    continue

                time_line_index = None

                for i, line in enumerate(lines):

                    if "-->" in line:

                        time_line_index = i
                        break

                if time_line_index is None:
                    continue

                time_line = lines[
                    time_line_index
                ]

                try:

                    left, right = (
                        time_line.split(
                            "-->",
                            1
                        )
                    )

                    start = (
                        self.srt_time_to_seconds(
                            left.strip()
                        )
                    )

                    end = (
                        self.srt_time_to_seconds(
                            right.strip()
                        )
                    )

                except Exception:

                    continue

                overlap_start = max(
                    start,
                    seg_start
                )

                overlap_end = min(
                    end,
                    seg_end
                )

                if overlap_start >= overlap_end:
                    continue

                new_start = (
                    output_offset
                    + overlap_start
                    - seg_start
                )

                new_end = (
                    output_offset
                    + overlap_end
                    - seg_start
                )

                new_lines = list(
                    lines
                )

                new_lines[
                    time_line_index
                ] = (
                    self.seconds_to_srt_time(
                        new_start
                    )
                    + " --> "
                    + self.seconds_to_srt_time(
                        new_end
                    )
                )

                output_blocks.append(
                    "\n".join(
                        new_lines
                    )
                )

            output_offset += (
                seg_end - seg_start
            )

        with open(
            retimed_path,
            "w",
            encoding="utf-8"
        ) as file:

            for number, block in enumerate(
                output_blocks,
                1
            ):

                lines = block.splitlines()

                if not lines:
                    continue

                lines[0] = str(
                    number
                )

                file.write(
                    "\n".join(lines)
                )

                file.write(
                    "\n\n"
                )

    # ========================================================
    # SRT TIME
    # ========================================================

    @staticmethod
    def srt_time_to_seconds(value):

        value = value.strip().replace(
            ",",
            "."
        )

        hours, minutes, rest = (
            value.split(":")
        )

        seconds = float(rest)

        return (
            int(hours) * 3600
            + int(minutes) * 60
            + seconds
        )

    @staticmethod
    def seconds_to_srt_time(seconds):

        seconds = max(
            0,
            float(seconds)
        )

        hours = int(
            seconds // 3600
        )

        minutes = int(
            (seconds % 3600) // 60
        )

        whole_seconds = int(
            seconds % 60
        )

        milliseconds = int(
            round(
                (
                    seconds
                    - int(seconds)
                ) * 1000
            )
        )

        if milliseconds >= 1000:

            milliseconds = 0
            whole_seconds += 1

        if whole_seconds >= 60:

            whole_seconds = 0
            minutes += 1

        if minutes >= 60:

            minutes = 0
            hours += 1

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{whole_seconds:02d},"
            f"{milliseconds:03d}"
        )

    # ========================================================
    # START EXPORT
    # ========================================================

    def start_export(self):

        if self.worker and self.worker.is_alive():
            return

        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        if not ffmpeg or not ffprobe:

            messagebox.showerror(
                "FFMPEG / FFPROBE",
                "Both ffmpeg.exe and ffprobe.exe "
                "are required."
            )

            return

        if not self.input_file:

            messagebox.showerror(
                "NO INPUT",
                "Select a video first."
            )

            return

        if not self.cuts:

            messagebox.showerror(
                "NO CUTS",
                "Add at least one cut."
            )

            return

        if not self.output_file:

            messagebox.showerror(
                "NO OUTPUT",
                "Choose an output filename."
            )

            return

        if (
            os.path.abspath(
                self.input_file
            )
            ==
            os.path.abspath(
                self.output_file
            )
        ):

            messagebox.showerror(
                "INVALID OUTPUT",
                "Output must be different from "
                "the source."
            )

            return

        output_dir = os.path.dirname(
            os.path.abspath(
                self.output_file
            )
        )

        if not os.path.isdir(
            output_dir
        ):

            messagebox.showerror(
                "INVALID OUTPUT FOLDER",
                "The output folder does not exist."
            )

            return

        output_duration = (
            self.calculate_output_duration()
        )

        if output_duration <= 0.1:

            messagebox.showerror(
                "INVALID CUTS",
                "The cuts remove the entire video."
            )

            return

        if os.path.exists(
            self.output_file
        ):

            answer = messagebox.askyesno(
                "OVERWRITE?",
                "Output already exists.\n\n"
                "Replace it?"
            )

            if not answer:
                return

        self.cancel_requested = False

        self.last_ffmpeg_error = ""

        self.export_output_duration = (
            output_duration
        )

        self.export_started_at = (
            time.monotonic()
        )

        self.progress["value"] = 0

        self.export_info_var.set(
            (
                "EXPORT PREPARING // "
                f"OUTPUT DURATION "
                f"{self.format_duration_short(output_duration)}"
            )
        )

        self.export_button.configure(
            state="disabled"
        )

        self.cancel_button.configure(
            state="normal"
        )

        self.worker = threading.Thread(
            target=self.export_video,
            daemon=True
        )

        self.worker.start()

    # ========================================================
    # EXPORT IMPLEMENTATION
    # ========================================================

    def export_video(self):

        ffmpeg = self.find_ffmpeg()

        self.export_temp_dir = None

        subtitle_temp_files = []

        try:

            output_dir = os.path.dirname(
                os.path.abspath(
                    self.output_file
                )
            )

            # ------------------------------------------------
            # Temporary directory lives beside output.
            # This avoids weird path handling and keeps
            # temporary export data local to the job.
            # ------------------------------------------------

            temp_dir = tempfile.mkdtemp(
                prefix=".family_safe_v4_",
                dir=output_dir
            )

            self.export_temp_dir = temp_dir

            # ------------------------------------------------
            # Prepare subtitle files BEFORE constructing the
            # final FFmpeg command.
            # ------------------------------------------------

            subtitle_prepared = (
                self.prepare_subtitles(
                    temp_dir
                )
            )

            subtitle_temp_files = [
                item["path"]
                for item in subtitle_prepared
            ]

            (
                filter_complex,
                audio_labels
            ) = self.build_filter_complex()

            # ------------------------------------------------
            # IMPORTANT:
            #
            # ALL INPUTS MUST COME FIRST.
            #
            # FFmpeg requires:
            #
            # ffmpeg [input options] -i INPUT ...
            #        [more input options] -i INPUT2
            #        [output options] OUTPUT
            #
            # In the broken V4 code, -i subtitle.srt appeared
            # after output options such as -map.
            #
            # This version deliberately builds every -i first.
            # ------------------------------------------------

            command = [
                ffmpeg,

                "-hide_banner",

                "-y",

                "-progress",
                "pipe:1",

                "-nostats",

                "-i",
                self.input_file
            ]

            # ------------------------------------------------
            # SUBTITLE INPUTS
            # ------------------------------------------------

            for subtitle_file in subtitle_temp_files:

                command.extend(
                    [
                        "-i",
                        subtitle_file
                    ]
                )

            # ------------------------------------------------
            # FILTER COMPLEX
            # ------------------------------------------------

            command.extend(
                [
                    "-filter_complex",
                    filter_complex,

                    "-map",
                    "[vout]"
                ]
            )

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            for label in audio_labels:

                command.extend(
                    [
                        "-map",
                        f"[{label}]"
                    ]
                )

            # ------------------------------------------------
            # SUBTITLES
            #
            # First media input = 0
            # Subtitle inputs = 1, 2, 3...
            # ------------------------------------------------

            for index in range(
                len(subtitle_temp_files)
            ):

                subtitle_input_index = (
                    1 + index
                )

                command.extend(
                    [
                        "-map",
                        f"{subtitle_input_index}:0"
                    ]
                )

            # ------------------------------------------------
            # ATTACHMENTS
            # ------------------------------------------------

            if self.attachment_streams:

                command.extend(
                    [
                        "-map",
                        "0:t?"
                    ]
                )

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

            command.extend(
                [
                    "-c:v",
                    "libx264",

                    "-preset",
                    "medium",

                    "-crf",
                    self.get_crf()
                ]
            )

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            if audio_labels:

                command.extend(
                    [
                        "-c:a",
                        "aac",

                        "-b:a",
                        "320k"
                    ]
                )

            # ------------------------------------------------
            # SUBTITLES
            # ------------------------------------------------

            if subtitle_temp_files:

                command.extend(
                    [
                        "-c:s",
                        "srt"
                    ]
                )

            # ------------------------------------------------
            # ATTACHMENTS
            # ------------------------------------------------

            if self.attachment_streams:

                command.extend(
                    [
                        "-c:t",
                        "copy"
                    ]
                )

            # ------------------------------------------------
            # METADATA
            # ------------------------------------------------

            command.extend(
                [
                    "-map_metadata",
                    "0",

                    "-map_chapters",
                    "-1",

                    self.output_file
                ]
            )

            self.ui_queue.put(
                (
                    "status",
                    "EXPORTING // ENCODING VIDEO..."
                )
            )

            # ------------------------------------------------
            # START PROCESS
            # ------------------------------------------------

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **self.subprocess_kwargs()
            )

            # ------------------------------------------------
            # STDERR READER
            # ------------------------------------------------

            stderr_thread = threading.Thread(
                target=self.read_stderr,
                daemon=True
            )

            stderr_thread.start()

            total_duration = (
                self.calculate_output_duration()
            )

            # ------------------------------------------------
            # PROGRESS LOOP
            # ------------------------------------------------

            while True:

                if self.cancel_requested:

                    self.terminate_process()

                    raise RuntimeError(
                        "Export cancelled."
                    )

                line = (
                    self.process.stdout.readline()
                )

                if not line:

                    if self.process.poll() is not None:
                        break

                    continue

                line = line.strip()

                if line.startswith(
                    "out_time_ms="
                ):

                    try:

                        value = int(
                            line.split(
                                "=",
                                1
                            )[1]
                        )

                        current = (
                            value / 1_000_000
                        )

                        if current < 0:
                            current = 0

                        if total_duration > 0:

                            percentage = min(
                                100,
                                (
                                    current
                                    / total_duration
                                ) * 100
                            )

                            elapsed = (
                                time.monotonic()
                                - self.export_started_at
                            )

                            remaining = (
                                self.estimate_remaining(
                                    percentage,
                                    elapsed
                                )
                            )

                            self.ui_queue.put(
                                (
                                    "progress",
                                    {
                                        "percentage":
                                            percentage,
                                        "elapsed":
                                            elapsed,
                                        "remaining":
                                            remaining
                                    }
                                )
                            )

                    except (
                        ValueError,
                        ZeroDivisionError
                    ):

                        pass

            return_code = (
                self.process.wait()
            )

            stderr_thread.join(
                timeout=1
            )

            if self.cancel_requested:

                raise RuntimeError(
                    "Export cancelled."
                )

            if return_code != 0:

                error_text = (
                    self.last_ffmpeg_error.strip()
                )

                if not error_text:

                    error_text = (
                        "FFmpeg returned exit code "
                        f"{return_code}."
                    )

                raise RuntimeError(
                    "FFmpeg failed.\n\n"
                    + error_text
                )

            if not os.path.isfile(
                self.output_file
            ):

                raise RuntimeError(
                    "FFmpeg completed but the output "
                    "file was not found."
                )

            self.ui_queue.put(
                (
                    "progress",
                    {
                        "percentage": 100.0,
                        "elapsed": (
                            time.monotonic()
                            - self.export_started_at
                        ),
                        "remaining": 0.0
                    }
                )
            )

            self.ui_queue.put(
                (
                    "success",
                    self.output_file
                )
            )

        except Exception as exc:

            # ------------------------------------------------
            # Delete incomplete output if FFmpeg failed.
            # ------------------------------------------------

            if (
                self.output_file
                and os.path.isfile(
                    self.output_file
                )
            ):

                try:

                    os.remove(
                        self.output_file
                    )

                except Exception:

                    pass

            self.ui_queue.put(
                (
                    "error",
                    str(exc)
                )
            )

        finally:

            self.process = None

            # ------------------------------------------------
            # Clean temporary export directory.
            # ------------------------------------------------

            if self.export_temp_dir:

                try:

                    shutil.rmtree(
                        self.export_temp_dir,
                        ignore_errors=True
                    )

                except Exception:

                    pass

                self.export_temp_dir = None

            self.ui_queue.put(
                (
                    "finished",
                    None
                )
            )

    # ========================================================
    # ESTIMATE
    # ========================================================

    @staticmethod
    def estimate_remaining(
        percentage,
        elapsed
    ):

        if percentage <= 0:
            return None

        if elapsed <= 0:
            return None

        fraction = (
            percentage / 100.0
        )

        total_estimated = (
            elapsed / fraction
        )

        remaining = (
            total_estimated - elapsed
        )

        if remaining < 0:
            remaining = 0

        return remaining

    # ========================================================
    # STDERR
    # ========================================================

    def read_stderr(self):

        process = self.process

        if not process:
            return

        try:

            lines = []

            for line in process.stderr:

                line = line.rstrip()

                if line:

                    lines.append(
                        line
                    )

            if lines:

                # Keep the final useful chunk rather than
                # flooding the GUI with FFmpeg's entire log.

                self.last_ffmpeg_error = "\n".join(
                    lines[-12:]
                )

        except Exception:

            pass

    # ========================================================
    # CANCEL
    # ========================================================

    def cancel_export(self):

        if not self.worker:
            return

        if not self.worker.is_alive():
            return

        answer = messagebox.askyesno(
            "CANCEL EXPORT",
            "Cancel the current export?"
        )

        if answer:

            self.cancel_requested = True

            self.status_var.set(
                "CANCELLING EXPORT..."
            )

            self.export_info_var.set(
                "STOPPING FFMPEG..."
            )

    def terminate_process(self):

        if not self.process:
            return

        try:

            if os.name == "nt":

                self.process.send_signal(
                    signal.CTRL_BREAK_EVENT
                )

            else:

                self.process.terminate()

        except Exception:

            try:

                self.process.kill()

            except Exception:

                pass

    # ========================================================
    # QUEUE
    # ========================================================

    def poll_ui_queue(self):

        try:

            while True:

                message_type, value = (
                    self.ui_queue.get_nowait()
                )

                # --------------------------------------------
                # MEDIA LOADED
                # --------------------------------------------

                if message_type == "media_loaded":

                    duration = value[
                        "duration"
                    ]

                    self.duration_var.set(
                        "DURATION // "
                        + self.format_time(
                            duration
                        )
                    )

                    self.start_time = 0.0
                    self.end_time = duration

                    self.update_handle_labels()
                    self.draw_timeline()

                    self.stream_info_var.set(
                        (
                            f"VIDEO: 1    "
                            f"AUDIO: {value['audio']}    "
                            f"SUBTITLES: "
                            f"{value['subtitles']}    "
                            f"ATTACHMENTS: "
                            f"{value['attachments']}"
                        )
                    )

                    self.status_var.set(
                        "MEDIA LOADED // READY"
                    )

                # --------------------------------------------
                # PREVIEW
                # --------------------------------------------

                elif message_type == "preview":

                    self.show_preview(
                        value
                    )

                # --------------------------------------------
                # PROGRESS
                # --------------------------------------------

                elif message_type == "progress":

                    percentage = float(
                        value["percentage"]
                    )

                    elapsed = float(
                        value.get(
                            "elapsed",
                            0
                        )
                    )

                    remaining = value.get(
                        "remaining"
                    )

                    self.progress[
                        "value"
                    ] = percentage

                    if remaining is not None:

                        remaining_text = (
                            self.format_duration_short(
                                remaining
                            )
                        )

                        elapsed_text = (
                            self.format_duration_short(
                                elapsed
                            )
                        )

                        self.status_var.set(
                            (
                                "EXPORTING // "
                                f"{percentage:.1f}%"
                                " // "
                                f"ETA {remaining_text}"
                            )
                        )

                        self.export_info_var.set(
                            (
                                f"ELAPSED "
                                f"{elapsed_text}"
                                "    //    "
                                f"REMAINING "
                                f"{remaining_text}"
                            )
                        )

                    else:

                        self.status_var.set(
                            (
                                "EXPORTING // "
                                f"{percentage:.1f}%"
                            )
                        )

                # --------------------------------------------
                # STATUS
                # --------------------------------------------

                elif message_type == "status":

                    self.status_var.set(
                        value
                    )

                # --------------------------------------------
                # SUCCESS
                # --------------------------------------------

                elif message_type == "success":

                    self.progress[
                        "value"
                    ] = 100

                    self.status_var.set(
                        "EXPORT COMPLETE // FILE READY"
                    )

                    self.export_info_var.set(
                        "EXPORT COMPLETE // 100%"
                    )

                    messagebox.showinfo(
                        "EXPORT COMPLETE",
                        "Family-safe video created:\n\n"
                        f"{value}"
                    )

                # --------------------------------------------
                # ERROR
                # --------------------------------------------

                elif message_type == "error":

                    self.status_var.set(
                        "ERROR // OPERATION FAILED"
                    )

                    self.export_info_var.set(
                        "EXPORT FAILED"
                    )

                    messagebox.showerror(
                        "ERROR",
                        value
                    )

                # --------------------------------------------
                # FINISHED
                # --------------------------------------------

                elif message_type == "finished":

                    self.export_button.configure(
                        state="normal"
                    )

                    self.cancel_button.configure(
                        state="disabled"
                    )

        except queue.Empty:

            pass

        self.root.after(
            100,
            self.poll_ui_queue
        )


# ============================================================
# MAIN
# ============================================================

def main():

    root = tk.Tk()

    app = FamilySafeCutter(
        root
    )

    def close():

        if (
            app.worker
            and app.worker.is_alive()
        ):

            answer = messagebox.askyesno(
                "EXPORT RUNNING",
                "An export is running.\n\n"
                "Cancel and exit?"
            )

            if not answer:
                return

            app.cancel_requested = True

            app.terminate_process()

        if app.preview_process:

            try:

                app.preview_process.kill()

            except Exception:

                pass

        root.destroy()

    root.protocol(
        "WM_DELETE_WINDOW",
        close
    )

    root.mainloop()


if __name__ == "__main__":
    main()
