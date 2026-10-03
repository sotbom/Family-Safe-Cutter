import os
import json
import shutil
import signal
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_TITLE = "Family-Safe Video Cutter V2.1"

SUPPORTED_VIDEO_TYPES = (
    "*.mkv *.mp4 *.mov *.m4v *.webm *.avi *.ts"
)


class FamilySafeCutter:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x820")
        self.root.minsize(850, 600)

        self.input_file = ""
        self.output_file = ""

        self.duration = 0.0
        self.cuts = []

        self.media_info = {}
        self.video_streams = []
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

        self.timeline_width = 900
        self.timeline_height = 90

        self.start_time = 0.0
        self.end_time = 0.0

        self.active_handle = "start"
        self.dragging = False

        self.ffmpeg_override = None
        self.ffprobe_override = None

        self.build_ui()
        self.check_ffmpeg()

        self.root.after(100, self.poll_ui_queue)

    # =========================================================
    # FFmpeg / FFprobe
    # =========================================================

    def find_executable(self, name):

        if name == "ffmpeg" and self.ffmpeg_override:
            if os.path.isfile(self.ffmpeg_override):
                return self.ffmpeg_override

        if name == "ffprobe" and self.ffprobe_override:
            if os.path.isfile(self.ffprobe_override):
                return self.ffprobe_override

        exe = shutil.which(name)

        if exe:
            return exe

        candidates = []

        if name == "ffmpeg":
            candidates = [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            ]

        elif name == "ffprobe":
            candidates = [
                r"C:\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
                r"C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe",
            ]

        for path in candidates:
            if os.path.isfile(path):
                return path

        return None

    def find_ffmpeg(self):
        return self.find_executable("ffmpeg")

    def find_ffprobe(self):
        return self.find_executable("ffprobe")

    def check_ffmpeg(self):

        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        if ffmpeg:
            self.ffmpeg_status.set("FFmpeg: detected")
        else:
            self.ffmpeg_status.set("FFmpeg: NOT FOUND")

        if ffprobe:
            self.ffprobe_status.set("FFprobe: detected")
        else:
            self.ffprobe_status.set("FFprobe: NOT FOUND")

        if ffmpeg and ffprobe:
            self.status_var.set("Ready.")

    def choose_ffmpeg(self):

        path = filedialog.askopenfilename(
            title="Select ffmpeg.exe",
            filetypes=[
                ("FFmpeg executable", "ffmpeg.exe"),
                ("Executable", "*.exe"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.ffmpeg_override = path
            self.ffmpeg_status.set("FFmpeg: selected")
            self.status_var.set("FFmpeg selected.")

    # =========================================================
    # GUI
    # =========================================================

    def build_ui(self):

        style = ttk.Style()

        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        self.status_var = tk.StringVar(value="Ready.")
        self.ffmpeg_status = tk.StringVar(
            value="FFmpeg: checking..."
        )
        self.ffprobe_status = tk.StringVar(
            value="FFprobe: checking..."
        )

        self.duration_var = tk.StringVar(
            value="Duration: —"
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

        self.cut_count_var = tk.StringVar(
            value="0 cuts"
        )

        # =====================================================
        # SCROLLABLE MAIN AREA
        # =====================================================

        main_area = ttk.Frame(self.root)

        main_area.pack(
            fill="both",
            expand=True
        )

        self.main_canvas = tk.Canvas(
            main_area,
            highlightthickness=0,
            borderwidth=0
        )

        self.main_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.main_scrollbar = ttk.Scrollbar(
            main_area,
            orient="vertical",
            command=self.main_canvas.yview
        )

        self.main_scrollbar.pack(
            side="right",
            fill="y"
        )

        self.main_canvas.configure(
            yscrollcommand=self.main_scrollbar.set
        )

        content = ttk.Frame(
            self.main_canvas,
            padding=15
        )

        self.main_canvas_window = (
            self.main_canvas.create_window(
                (0, 0),
                window=content,
                anchor="nw"
            )
        )

        def update_scroll_region(event=None):
            self.main_canvas.configure(
                scrollregion=self.main_canvas.bbox("all")
            )

        content.bind(
            "<Configure>",
            update_scroll_region
        )

        def resize_content(event):
            self.main_canvas.itemconfigure(
                self.main_canvas_window,
                width=event.width
            )

        self.main_canvas.bind(
            "<Configure>",
            resize_content
        )

        # Mouse wheel
        self.main_canvas.bind_all(
            "<MouseWheel>",
            lambda event: self.main_canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )
        )

        self.main_canvas.bind_all(
            "<Button-4>",
            lambda event: self.main_canvas.yview_scroll(
                -3,
                "units"
            )
        )

        self.main_canvas.bind_all(
            "<Button-5>",
            lambda event: self.main_canvas.yview_scroll(
                3,
                "units"
            )
        )

        # =====================================================
        # INPUT
        # =====================================================

        input_frame = ttk.LabelFrame(
            content,
            text="1. Input Video",
            padding=10
        )

        input_frame.pack(
            fill="x",
            pady=(0, 8)
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
            text="Browse...",
            command=self.choose_input
        ).pack(
            side="left",
            padx=(8, 0)
        )

        # =====================================================
        # PREVIEW
        # =====================================================

        preview_frame = ttk.LabelFrame(
            content,
            text="2. Frame Preview",
            padding=10
        )

        preview_frame.pack(
            fill="x",
            pady=8
        )

        self.preview_label = ttk.Label(
            preview_frame,
            text="Select a video to begin.",
            anchor="center"
        )

        self.preview_label.pack(
            fill="x"
        )

        ttk.Label(
            preview_frame,
            textvariable=self.current_time_var,
            font=("Consolas", 12)
        ).pack(
            pady=(8, 0)
        )

        ttk.Label(
            preview_frame,
            textvariable=self.duration_var
        ).pack(
            pady=(2, 0)
        )

        # =====================================================
        # TIMELINE
        # =====================================================

        timeline_frame = ttk.LabelFrame(
            content,
            text="3. Cut Timeline",
            padding=10
        )

        timeline_frame.pack(
            fill="x",
            pady=8
        )

        self.timeline = tk.Canvas(
            timeline_frame,
            height=90,
            background="#202020",
            highlightthickness=1,
            highlightbackground="#555555"
        )

        self.timeline.pack(
            fill="x",
            expand=True
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

        self.timeline.bind(
            "<Button-2>",
            lambda e: self.timeline.focus_set()
        )

        # -----------------------------------------------------
        # Timeline controls
        # -----------------------------------------------------

        controls = ttk.Frame(
            timeline_frame
        )

        controls.pack(
            fill="x",
            pady=(10, 0)
        )

        ttk.Label(
            controls,
            text="Start:"
        ).pack(
            side="left"
        )

        ttk.Label(
            controls,
            textvariable=self.start_var,
            font=("Consolas", 10)
        ).pack(
            side="left",
            padx=(5, 15)
        )

        ttk.Label(
            controls,
            text="End:"
        ).pack(
            side="left"
        )

        ttk.Label(
            controls,
            textvariable=self.end_var,
            font=("Consolas", 10)
        ).pack(
            side="left",
            padx=(5, 15)
        )

        # Set start / end buttons
        ttk.Button(
            controls,
            text="Set Start Here",
            command=self.set_start_here
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            controls,
            text="Set End Here",
            command=self.set_end_here
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            controls,
            text="Reset Handles",
            command=self.reset_handles
        ).pack(
            side="left",
            padx=3
        )

        # Add cut
        self.add_cut_button = ttk.Button(
            controls,
            text="＋  ADD CUT",
            command=self.add_current_cut
        )

        self.add_cut_button.pack(
            side="right",
            padx=(10, 0)
        )

        ttk.Label(
            timeline_frame,
            text=(
                "Drag the green/red handles. "
                "← / → = 0.1 sec    "
                "Shift+← / → = 1 sec"
            )
        ).pack(
            anchor="w",
            pady=(8, 0)
        )

        # =====================================================
        # CUTS
        # =====================================================

        cuts_frame = ttk.LabelFrame(
            content,
            text="4. Cuts",
            padding=10
        )

        cuts_frame.pack(
            fill="x",
            pady=8
        )

        cuts_header = ttk.Frame(
            cuts_frame
        )

        cuts_header.pack(
            fill="x",
            pady=(0, 6)
        )

        ttk.Label(
            cuts_header,
            text="Scenes that will be removed:"
        ).pack(
            side="left"
        )

        ttk.Label(
            cuts_header,
            textvariable=self.cut_count_var,
            font=("Segoe UI", 10, "bold")
        ).pack(
            side="right"
        )

        list_container = ttk.Frame(
            cuts_frame
        )

        list_container.pack(
            fill="x"
        )

        self.cut_list = tk.Listbox(
            list_container,
            font=("Consolas", 10),
            height=7,
            selectmode=tk.EXTENDED
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
            text="Remove Selected",
            command=self.remove_selected_cut
        ).pack(
            side="left"
        )

        ttk.Button(
            cut_buttons,
            text="Clear All",
            command=self.clear_cuts
        ).pack(
            side="left",
            padx=8
        )

        # =====================================================
        # STREAM INFO
        # =====================================================

        info_frame = ttk.LabelFrame(
            content,
            text="Detected Streams",
            padding=8
        )

        info_frame.pack(
            fill="x",
            pady=8
        )

        self.stream_info_var = tk.StringVar(
            value="No media loaded."
        )

        ttk.Label(
            info_frame,
            textvariable=self.stream_info_var
        ).pack(
            anchor="w"
        )

        # =====================================================
        # OUTPUT
        # =====================================================

        output_frame = ttk.LabelFrame(
            content,
            text="5. Output",
            padding=10
        )

        output_frame.pack(
            fill="x",
            pady=8
        )

        ttk.Entry(
            output_frame,
            textvariable=self.output_var
        ).pack(
            side="left",
            fill="x",
            expand=True
        )

        ttk.Button(
            output_frame,
            text="Save As...",
            command=self.choose_output
        ).pack(
            side="left",
            padx=(8, 0)
        )

        settings = ttk.Frame(
            output_frame
        )

        settings.pack(
            fill="x",
            pady=(8, 0)
        )

        ttk.Label(
            settings,
            text="Quality:"
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
            width=15
        ).pack(
            side="left",
            padx=8
        )

        ttk.Label(
            settings,
            text="Default output: MKV"
        ).pack(
            side="left",
            padx=15
        )

        # =====================================================
        # BOTTOM FIXED ACTION BAR
        # =====================================================

        bottom_bar = ttk.Frame(
            self.root,
            padding=(12, 7),
            relief="raised"
        )

        bottom_bar.pack(
            side="bottom",
            fill="x"
        )

        self.progress = ttk.Progressbar(
            bottom_bar,
            maximum=100
        )

        self.progress.pack(
            fill="x",
            pady=(0, 6)
        )

        status_row = ttk.Frame(
            bottom_bar
        )

        status_row.pack(
            fill="x"
        )

        ttk.Label(
            status_row,
            textvariable=self.status_var
        ).pack(
            side="left",
            fill="x",
            expand=True
        )

        ttk.Label(
            status_row,
            textvariable=self.ffmpeg_status
        ).pack(
            side="left",
            padx=8
        )

        ttk.Label(
            status_row,
            textvariable=self.ffprobe_status
        ).pack(
            side="left",
            padx=8
        )

        self.cancel_button = ttk.Button(
            status_row,
            text="Cancel",
            command=self.cancel_export,
            state="disabled"
        )

        self.cancel_button.pack(
            side="right",
            padx=(8, 0)
        )

        self.export_button = ttk.Button(
            status_row,
            text="EXPORT FAMILY-SAFE VIDEO",
            command=self.start_export
        )

        self.export_button.pack(
            side="right"
        )

    # =========================================================
    # File selection
    # =========================================================

    def choose_input(self):

        path = filedialog.askopenfilename(
            title="Select Movie or Episode",
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
            text="Reading video..."
        )

        self.status_var.set(
            "Reading media information..."
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
            self.output_var.set(path)

    # =========================================================
    # Media probing
    # =========================================================

    def probe_media(self):

        ffprobe = self.find_ffprobe()

        if not ffprobe:
            self.ui_queue.put(
                (
                    "error",
                    "ffprobe.exe was not found.\n\n"
                    "FFprobe normally comes with FFmpeg."
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
                errors="replace"
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

            self.video_streams = [
                s for s in streams
                if s.get("codec_type") == "video"
            ]

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
            self.active_handle = "start"

            self.ui_queue.put(
                (
                    "media_loaded",
                    {
                        "duration": duration,
                        "video": len(
                            self.video_streams
                        ),
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

    # =========================================================
    # Timestamp helpers
    # =========================================================

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

    # =========================================================
    # Timeline
    # =========================================================

    def on_timeline_resize(self, event=None):

        self.timeline_width = max(
            1,
            self.timeline.winfo_width()
        )

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

        return ratio * self.duration

    def draw_timeline(self):

        self.timeline.delete("all")

        width = max(
            1,
            self.timeline.winfo_width()
        )

        height = self.timeline_height

        self.timeline.create_rectangle(
            20,
            30,
            width - 20,
            60,
            fill="#353535",
            outline="#666666"
        )

        if self.duration <= 0:

            self.timeline.create_text(
                width / 2,
                45,
                text="Load a video",
                fill="white"
            )

            return

        # Existing cuts
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
                fill="#8b2525",
                outline="#ff5555"
            )

        # Current selected range
        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        self.timeline.create_rectangle(
            sx,
            30,
            ex,
            60,
            fill="#304f35",
            outline="#5cff8a"
        )

        # Start handle
        self.timeline.create_line(
            sx,
            15,
            sx,
            75,
            fill="#35d06f",
            width=3
        )

        self.timeline.create_oval(
            sx - 7,
            23,
            sx + 7,
            37,
            fill="#35d06f",
            outline="white"
        )

        # End handle
        self.timeline.create_line(
            ex,
            15,
            ex,
            75,
            fill="#ff5555",
            width=3
        )

        self.timeline.create_oval(
            ex - 7,
            53,
            ex + 7,
            67,
            fill="#ff5555",
            outline="white"
        )

        # Start label
        self.timeline.create_text(
            20,
            10,
            anchor="w",
            text=self.format_time(0),
            fill="#bbbbbb",
            font=("Consolas", 8)
        )

        # End label
        self.timeline.create_text(
            width - 20,
            10,
            anchor="e",
            text=self.format_time(
                self.duration
            ),
            fill="#bbbbbb",
            font=("Consolas", 8)
        )

    def nearest_handle(self, x):

        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        if abs(x - sx) <= 14:
            return "start"

        if abs(x - ex) <= 14:
            return "end"

        if abs(x - sx) <= abs(x - ex):
            return "start"

        return "end"

    def set_handle_from_x(self, x):

        if self.duration <= 0:
            return

        seconds = self.timeline_time_from_x(x)

        if self.active_handle == "start":

            seconds = min(
                seconds,
                self.end_time - 0.01
            )

            self.start_time = max(
                0.0,
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
            self.nearest_handle(event.x)
        )

        self.dragging = True

        self.set_handle_from_x(
            event.x
        )

    def timeline_mouse_drag(self, event):

        if not self.dragging:
            return

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
            abs(event.x - sx) <= 12
            or abs(event.x - ex) <= 12
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
            return "break"

        if self.active_handle == "start":

            self.start_time = max(
                0.0,
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
        self.request_preview(current)

        return "break"

    # =========================================================
    # Handle buttons
    # =========================================================

    def set_start_here(self):

        if self.duration <= 0:
            return

        current = (
            self.start_time
            if self.active_handle == "start"
            else self.end_time
        )

        self.start_time = max(
            0.0,
            min(
                current,
                self.end_time - 0.01
            )
        )

        self.active_handle = "start"

        self.update_handle_labels()
        self.draw_timeline()

    def set_end_here(self):

        if self.duration <= 0:
            return

        current = (
            self.start_time
            if self.active_handle == "start"
            else self.end_time
        )

        self.end_time = min(
            self.duration,
            max(
                current,
                self.start_time + 0.01
            )
        )

        self.active_handle = "end"

        self.update_handle_labels()
        self.draw_timeline()

    def reset_handles(self):

        if self.duration <= 0:
            return

        self.start_time = 0.0
        self.end_time = self.duration
        self.active_handle = "start"

        self.update_handle_labels()
        self.draw_timeline()

        self.request_preview(0)

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

    # =========================================================
    # Preview
    # =========================================================

    def request_preview(self, seconds):

        if not self.input_file:
            return

        if self.preview_job is not None:

            try:
                self.root.after_cancel(
                    self.preview_job
                )
            except Exception:
                pass

        self.preview_job = self.root.after(
            250,
            lambda: self.generate_preview(seconds)
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

            self.preview_process = None

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
            "scale=720:-2",
            "-y",
            preview_path
        ]

        try:

            self.preview_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

        except Exception:
            return

        process_reference = self.preview_process

        def wait_for_preview():

            try:

                process_reference.wait()

                if (
                    process_reference.returncode == 0
                    and os.path.exists(preview_path)
                ):

                    self.ui_queue.put(
                        (
                            "preview",
                            preview_path
                        )
                    )

            except Exception:
                pass

        threading.Thread(
            target=wait_for_preview,
            daemon=True
        ).start()

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
                text=(
                    "Preview unavailable:\n"
                    f"{exc}"
                )
            )

    # =========================================================
    # Cuts
    # =========================================================

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

            if start <= previous[1] + 0.01:

                previous[1] = max(
                    previous[1],
                    end
                )

            else:

                merged.append(
                    [start, end]
                )

        return [
            tuple(x)
            for x in merged
        ]

    def add_current_cut(self):

        if self.duration <= 0:

            messagebox.showerror(
                "No Video",
                "Select a video first."
            )

            return

        if self.end_time <= self.start_time:

            messagebox.showerror(
                "Invalid Range",
                "END must be after START."
            )

            return

        new_cut = (
            self.start_time,
            self.end_time
        )

        self.cuts.append(
            new_cut
        )

        self.cuts = self.normalize_cuts()

        self.refresh_cut_list()

        # Reset the timeline to make adding
        # another cut easy.
        next_start = min(
            self.end_time + 0.01,
            self.duration
        )

        if next_start >= self.duration:

            self.start_time = 0.0
            self.end_time = self.duration

        else:

            self.start_time = next_start
            self.end_time = self.duration

        self.active_handle = "start"

        self.update_handle_labels()
        self.draw_timeline()

        # Select the last cut.
        if self.cuts:

            index = len(self.cuts) - 1

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
            "Cut added successfully."
        )

    def refresh_cut_list(self):

        self.cut_list.delete(
            0,
            tk.END
        )

        for number, (start, end) in enumerate(
            self.cuts,
            start=1
        ):

            duration = end - start

            self.cut_list.insert(
                tk.END,
                (
                    f"{number:02d}.  "
                    f"{self.format_time(start)}"
                    f"  →  "
                    f"{self.format_time(end)}"
                    f"   "
                    f"({duration:.3f}s)"
                )
            )

        count = len(self.cuts)

        if count == 1:
            self.cut_count_var.set(
                "1 cut"
            )
        else:
            self.cut_count_var.set(
                f"{count} cuts"
            )

    def remove_selected_cut(self):

        selected = list(
            self.cut_list.curselection()
        )

        if not selected:
            return

        for index in reversed(
            selected
        ):
            del self.cuts[index]

        self.refresh_cut_list()
        self.draw_timeline()

        self.status_var.set(
            "Selected cut(s) removed."
        )

    def clear_cuts(self):

        if not self.cuts:
            return

        answer = messagebox.askyesno(
            "Clear Cuts?",
            "Remove all cuts?"
        )

        if not answer:
            return

        self.cuts.clear()

        self.refresh_cut_list()
        self.draw_timeline()

        self.status_var.set(
            "All cuts cleared."
        )

    # =========================================================
    # Export calculations
    # =========================================================

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
            for start, end
            in self.calculate_kept_segments()
        )

    def build_filter_complex(self):

        kept = (
            self.calculate_kept_segments()
        )

        if not kept:

            raise ValueError(
                "The cuts remove the entire video."
            )

        parts = []

        # -----------------------------------------------------
        # VIDEO
        # -----------------------------------------------------

        video_labels = []

        for i, (start, end) in enumerate(
            kept
        ):

            label = f"v{i}"

            parts.append(
                (
                    f"[0:v:0]"
                    f"trim=start={start:.6f}:end={end:.6f},"
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
                + f"concat=n={len(kept)}:v=1:a=0[vout]"
            )
        )

        # -----------------------------------------------------
        # AUDIO
        # -----------------------------------------------------

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
                        f"atrim=start={start:.6f}:end={end:.6f},"
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
                    + f"concat=n={len(kept)}:v=0:a=1"
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

    # =========================================================
    # Export
    # =========================================================

    def start_export(self):

        if self.worker and self.worker.is_alive():
            return

        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        if not ffmpeg or not ffprobe:

            messagebox.showerror(
                "FFmpeg/FFprobe Missing",
                "Both ffmpeg.exe and ffprobe.exe are required."
            )

            return

        if not self.input_file:

            messagebox.showerror(
                "No Input",
                "Select a video first."
            )

            return

        if not self.cuts:

            messagebox.showerror(
                "No Cuts",
                "Add at least one cut first."
            )

            return

        if not self.output_file:

            messagebox.showerror(
                "No Output",
                "Choose an output filename."
            )

            return

        if os.path.abspath(
            self.input_file
        ) == os.path.abspath(
            self.output_file
        ):

            messagebox.showerror(
                "Invalid Output",
                "The output must be different from the original."
            )

            return

        if os.path.exists(
            self.output_file
        ):

            answer = messagebox.askyesno(
                "Overwrite?",
                "The output file already exists.\n\n"
                "Replace it?"
            )

            if not answer:
                return

        # Subtitle warning
        if self.subtitle_streams:

            answer = messagebox.askyesno(
                "Subtitle Notice",
                (
                    f"This video contains "
                    f"{len(self.subtitle_streams)} subtitle stream(s).\n\n"
                    "V2.1 will KEEP the subtitle streams in the "
                    "output MKV instead of deleting them.\n\n"
                    "Important: their timestamps are currently "
                    "copied as-is. Therefore subtitles appearing "
                    "after a removed scene may be out of sync.\n\n"
                    "Continue?"
                )
            )

            if not answer:
                return

        self.cancel_requested = False
        self.progress["value"] = 0

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

    def export_video(self):

        ffmpeg = self.find_ffmpeg()

        temp_output = (
            self.output_file
            + ".working.mkv"
        )

        try:

            (
                filter_complex,
                audio_labels
            ) = self.build_filter_complex()

            # -------------------------------------------------
            # INPUT
            # -------------------------------------------------

            command = [
                ffmpeg,
                "-hide_banner",
                "-y",

                "-i",
                self.input_file,

                "-filter_complex",
                filter_complex,

                # Edited video
                "-map",
                "[vout]"
            ]

            # -------------------------------------------------
            # EDITED AUDIO
            # -------------------------------------------------

            for label in audio_labels:

                command.extend(
                    [
                        "-map",
                        f"[{label}]"
                    ]
                )

            # -------------------------------------------------
            # SUBTITLES
            #
            # THIS IS THE IMPORTANT FIX FROM V2.
            #
            # The old exporter never mapped subtitles,
            # therefore they disappeared when manual -map
            # options were used.
            # -------------------------------------------------

            if self.subtitle_streams:

                command.extend(
                    [
                        "-map",
                        "0:s?"
                    ]
                )

            # -------------------------------------------------
            # ATTACHMENTS / FONTS
            # -------------------------------------------------

            if self.attachment_streams:

                command.extend(
                    [
                        "-map",
                        "0:t?"
                    ]
                )

            # -------------------------------------------------
            # VIDEO ENCODING
            # -------------------------------------------------

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

            # -------------------------------------------------
            # AUDIO ENCODING
            # -------------------------------------------------

            if audio_labels:

                command.extend(
                    [
                        "-c:a",
                        "aac",

                        "-b:a",
                        "320k"
                    ]
                )

            # -------------------------------------------------
            # SUBTITLE COPY
            # -------------------------------------------------

            if self.subtitle_streams:

                command.extend(
                    [
                        "-c:s",
                        "copy"
                    ]
                )

            # -------------------------------------------------
            # ATTACHMENT COPY
            # -------------------------------------------------

            if self.attachment_streams:

                command.extend(
                    [
                        "-c:t",
                        "copy"
                    ]
                )

            # -------------------------------------------------
            # METADATA
            # -------------------------------------------------

            command.extend(
                [
                    "-map_metadata",
                    "0",

                    # Chapters are intentionally not copied
                    # because their timestamps would become
                    # invalid after scene removal.
                    "-map_chapters",
                    "-1",

                    # Progress information
                    "-progress",
                    "pipe:1",

                    "-nostats",

                    # Write to temporary file first
                    temp_output
                ]
            )

            self.ui_queue.put(
                (
                    "status",
                    "Starting FFmpeg export..."
                )
            )

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            threading.Thread(
                target=self.read_stderr,
                daemon=True
            ).start()

            total_duration = (
                self.calculate_output_duration()
            )

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

                        if total_duration > 0:

                            percentage = min(
                                100.0,
                                (
                                    current
                                    / total_duration
                                ) * 100.0
                            )

                            self.ui_queue.put(
                                (
                                    "progress",
                                    percentage
                                )
                            )

                    except ValueError:
                        pass

            return_code = (
                self.process.wait()
            )

            if self.cancel_requested:

                raise RuntimeError(
                    "Export cancelled."
                )

            if return_code != 0:

                raise RuntimeError(
                    "FFmpeg failed.\n\n"
                    "The source or output file may be "
                    "unsupported, locked, or inaccessible."
                )

            if not os.path.isfile(
                temp_output
            ):

                raise RuntimeError(
                    "FFmpeg completed but the temporary "
                    "output file was not found."
                )

            # -------------------------------------------------
            # Move completed file into final location
            # -------------------------------------------------

            if os.path.exists(
                self.output_file
            ):

                try:
                    os.remove(
                        self.output_file
                    )
                except Exception:
                    pass

            os.replace(
                temp_output,
                self.output_file
            )

            self.ui_queue.put(
                (
                    "progress",
                    100.0
                )
            )

            self.ui_queue.put(
                (
                    "success",
                    self.output_file
                )
            )

        except Exception as exc:

            try:

                if os.path.exists(
                    temp_output
                ):

                    os.remove(
                        temp_output
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

            self.ui_queue.put(
                (
                    "finished",
                    None
                )
            )

    def read_stderr(self):

        process = self.process

        if not process:
            return

        try:

            for line in process.stderr:

                if self.cancel_requested:
                    break

        except Exception:
            pass

    # =========================================================
    # Cancellation
    # =========================================================

    def cancel_export(self):

        if not self.worker:
            return

        if not self.worker.is_alive():
            return

        answer = messagebox.askyesno(
            "Cancel Export?",
            "Cancel the current export?"
        )

        if answer:

            self.cancel_requested = True

            self.status_var.set(
                "Cancelling..."
            )

    def terminate_process(self):

        if not self.process:
            return

        try:

            if os.name == "nt":

                try:

                    self.process.send_signal(
                        signal.CTRL_BREAK_EVENT
                    )

                except Exception:

                    self.process.terminate()

            else:

                self.process.terminate()

        except Exception:

            try:
                self.process.kill()
            except Exception:
                pass

    # =========================================================
    # Queue / UI updates
    # =========================================================

    def poll_ui_queue(self):

        try:

            while True:

                message_type, value = (
                    self.ui_queue.get_nowait()
                )

                if message_type == "media_loaded":

                    duration = value["duration"]

                    self.duration_var.set(
                        "Duration: "
                        + self.format_time(
                            duration
                        )
                    )

                    self.start_time = 0.0
                    self.end_time = duration
                    self.active_handle = "start"

                    self.update_handle_labels()
                    self.draw_timeline()

                    self.stream_info_var.set(
                        (
                            f"Video: {value['video']}    "
                            f"Audio: {value['audio']}    "
                            f"Subtitles: {value['subtitles']}    "
                            f"Attachments: {value['attachments']}"
                        )
                    )

                    self.status_var.set(
                        "Video loaded. Add your cuts."
                    )

                elif message_type == "preview":

                    self.show_preview(
                        value
                    )

                elif message_type == "progress":

                    percentage = float(value)

                    self.progress["value"] = (
                        percentage
                    )

                    self.status_var.set(
                        f"Exporting... "
                        f"{percentage:.1f}%"
                    )

                elif message_type == "status":

                    self.status_var.set(
                        value
                    )

                elif message_type == "success":

                    self.progress["value"] = 100

                    self.status_var.set(
                        "Export complete."
                    )

                    messagebox.showinfo(
                        "Export Complete",
                        (
                            "Family-safe video created:\n\n"
                            f"{value}"
                        )
                    )

                elif message_type == "error":

                    self.status_var.set(
                        "Error."
                    )

                    messagebox.showerror(
                        "Error",
                        value
                    )

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
                "Export Running",
                (
                    "An export is currently running.\n\n"
                    "Cancel it and exit?"
                )
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
