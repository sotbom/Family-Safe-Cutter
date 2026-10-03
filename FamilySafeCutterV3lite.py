import os
import re
import json
import shutil
import signal
import subprocess
import threading
import queue
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_TITLE = "Family-Safe Video Cutter V3"

SUPPORTED_VIDEO_TYPES = (
    "*.mkv *.mp4 *.mov *.m4v *.webm *.avi *.ts"
)


class FamilySafeCutter:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x820")
        self.root.minsize(900, 650)

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

        self.export_temp_dir = None

        self.build_ui()
        self.check_ffmpeg()

        self.root.after(100, self.poll_ui_queue)

    # =========================================================
    # FFmpeg / FFprobe
    # =========================================================

    def find_executable(self, name):
        override = (
            self.ffmpeg_override
            if name == "ffmpeg"
            else self.ffprobe_override
        )

        if override and os.path.isfile(override):
            return override

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

    def choose_ffprobe(self):
        path = filedialog.askopenfilename(
            title="Select ffprobe.exe",
            filetypes=[
                ("FFprobe executable", "ffprobe.exe"),
                ("Executable", "*.exe"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.ffprobe_override = path
            self.ffprobe_status.set("FFprobe: selected")
            self.status_var.set("FFprobe selected.")

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

        # =====================================================
        # MAIN SCROLLABLE AREA
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

        def mousewheel(event):
            if event.delta:
                self.main_canvas.yview_scroll(
                    int(-event.delta / 120),
                    "units"
                )

        self.main_canvas.bind_all(
            "<MouseWheel>",
            mousewheel
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
            padx=(5, 20)
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
            padx=5
        )

        ttk.Button(
            controls,
            text="＋  ADD CUT",
            command=self.add_current_cut
        ).pack(
            side="right",
            padx=(10, 0)
        )

        ttk.Label(
            timeline_frame,
            text=(
                "Drag the green/red handles, click the timeline, "
                "or use ← / → for 0.1 sec and Shift+← / → for 1 sec."
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

        list_container = ttk.Frame(
            cuts_frame
        )

        list_container.pack(
            fill="x",
            expand=True
        )

        self.cut_list = tk.Listbox(
            list_container,
            font=("Consolas", 10),
            height=6
        )

        self.cut_list.pack(
            side="left",
            fill="both",
            expand=True
        )

        scroll = ttk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.cut_list.yview
        )

        scroll.pack(
            side="right",
            fill="y"
        )

        self.cut_list.configure(
            yscrollcommand=scroll.set
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
        # MEDIA INFORMATION
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
            textvariable=self.stream_info_var,
            wraplength=900
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

        # =====================================================
        # BOTTOM BAR
        # =====================================================

        bottom_bar = ttk.Frame(
            self.root,
            padding=(15, 8),
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
            pady=(0, 5)
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
            padx=10
        )

        ttk.Label(
            status_row,
            textvariable=self.ffprobe_status
        ).pack(
            side="left",
            padx=10
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

    # =====================================================
    # File selection
    # =====================================================

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

    # =====================================================
    # Probe
    # =====================================================

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

            self.duration = float(
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

            self.start_time = 0.0
            self.end_time = self.duration

            self.ui_queue.put(
                (
                    "media_loaded",
                    {
                        "duration": self.duration,
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

    # =====================================================
    # Timestamp helpers
    # =====================================================

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

    # =====================================================
    # Timeline
    # =====================================================

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

        return (
            ratio * self.duration
        )

    def draw_timeline(self):
        self.timeline.delete("all")

        width = max(
            1,
            self.timeline.winfo_width()
        )

        if self.duration <= 0:
            self.timeline.create_text(
                width / 2,
                45,
                text="Load a video",
                fill="white"
            )
            return

        self.timeline.create_rectangle(
            20,
            30,
            width - 20,
            60,
            fill="#353535",
            outline="#666666"
        )

        for start, end in self.cuts:
            x1 = self.timeline_x_from_time(start)
            x2 = self.timeline_x_from_time(end)

            self.timeline.create_rectangle(
                x1,
                30,
                x2,
                60,
                fill="#8b2525",
                outline="#ff5555"
            )

        sx = self.timeline_x_from_time(
            self.start_time
        )

        ex = self.timeline_x_from_time(
            self.end_time
        )

        self.timeline.create_line(
            sx,
            18,
            sx,
            72,
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

        self.timeline.create_line(
            ex,
            18,
            ex,
            72,
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

        self.timeline.create_text(
            20,
            12,
            anchor="w",
            text=self.format_time(0),
            fill="#bbbbbb",
            font=("Consolas", 8)
        )

        self.timeline.create_text(
            width - 20,
            12,
            anchor="e",
            text=self.format_time(self.duration),
            fill="#bbbbbb",
            font=("Consolas", 8)
        )

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
            fill="#ffffff",
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

        seconds = self.timeline_time_from_x(x)

        if self.active_handle == "start":
            self.start_time = max(
                0.0,
                min(
                    seconds,
                    self.end_time - 0.01
                )
            )
        else:
            self.end_time = min(
                self.duration,
                max(
                    seconds,
                    self.start_time + 0.01
                )
            )

        self.update_handle_labels()
        self.draw_timeline()

        self.request_preview(seconds)

    def timeline_mouse_down(self, event):
        if self.duration <= 0:
            return

        self.timeline.focus_set()

        self.active_handle = self.nearest_handle(
            event.x
        )

        self.dragging = True

        self.set_handle_from_x(event.x)

    def timeline_mouse_drag(self, event):
        if self.dragging:
            self.set_handle_from_x(event.x)

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

    def update_handle_labels(self):
        self.start_var.set(
            self.format_time(self.start_time)
        )

        self.end_var.set(
            self.format_time(self.end_time)
        )

        current = (
            self.start_time
            if self.active_handle == "start"
            else self.end_time
        )

        self.current_time_var.set(
            self.format_time(current)
        )

    # =====================================================
    # Preview
    # =====================================================

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
            300,
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

        temp_dir = os.path.join(
            os.path.dirname(self.input_file),
            ".family_safe_preview"
        )

        os.makedirs(
            temp_dir,
            exist_ok=True
        )

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

            def wait_preview():
                try:
                    self.preview_process.wait()

                    if (
                        self.preview_process.returncode == 0
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
                target=wait_preview,
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
                text=f"Preview unavailable:\n{exc}"
            )

    # =====================================================
    # Cuts
    # =====================================================

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

            if start <= previous[1] + 0.001:
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

            self.cut_list.see(index)

        self.status_var.set(
            "Cut added."
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

        for start, end in self.cuts:
            self.cut_list.insert(
                tk.END,
                (
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

    def clear_cuts(self):
        self.cuts.clear()

        self.refresh_cut_list()
        self.draw_timeline()

    # =====================================================
    # Segment calculations
    # =====================================================

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
            for start, end in
            self.calculate_kept_segments()
        )

    # =====================================================
    # Subtitle timeline mapping
    # =====================================================

    def map_original_time_to_output(
        self,
        original_time
    ):
        """
        Convert an original timeline position into
        the shortened output timeline.

        Returns None if the timestamp itself lies
        inside a removed section.
        """

        cuts = self.normalize_cuts()

        removed_before = 0.0

        for start, end in cuts:

            if original_time < start:
                return (
                    original_time
                    - removed_before
                )

            if start <= original_time < end:
                return None

            removed_before += (
                end - start
            )

        return (
            original_time
            - removed_before
        )

    # =====================================================
    # SRT handling
    # =====================================================

    @staticmethod
    def parse_srt_timestamp(value):
        value = value.strip()

        match = re.match(
            r"(\d+):(\d{2}):(\d{2})[,.](\d{3})",
            value
        )

        if not match:
            raise ValueError(
                f"Invalid SRT timestamp: {value}"
            )

        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))

        return (
            hours * 3600
            + minutes * 60
            + seconds
            + milliseconds / 1000.0
        )

    @staticmethod
    def format_srt_timestamp(seconds):
        seconds = max(
            0.0,
            seconds
        )

        total_ms = int(
            round(seconds * 1000)
        )

        hours = total_ms // 3_600_000

        total_ms %= 3_600_000

        minutes = total_ms // 60_000

        total_ms %= 60_000

        secs = total_ms // 1000

        milliseconds = total_ms % 1000

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d},"
            f"{milliseconds:03d}"
        )

    def retime_srt(
        self,
        input_path,
        output_path
    ):
        """
        Retimes an SRT file according to the video's
        removed regions.

        Subtitles wholly inside removed regions are removed.

        Subtitles crossing a removed region are clipped
        to the surviving portions.
        """

        with open(
            input_path,
            "r",
            encoding="utf-8-sig",
            errors="replace"
        ) as f:
            text = f.read()

        blocks = re.split(
            r"\r?\n\r?\n+",
            text.strip()
        )

        output_blocks = []
        counter = 1

        for block in blocks:

            lines = block.splitlines()

            if len(lines) < 3:
                continue

            timestamp_index = None

            for i, line in enumerate(lines[:4]):
                if "-->" in line:
                    timestamp_index = i
                    break

            if timestamp_index is None:
                continue

            timestamp_line = lines[
                timestamp_index
            ]

            parts = timestamp_line.split(
                "-->"
            )

            if len(parts) != 2:
                continue

            start_text = parts[0].strip()
            end_text = parts[1].strip()

            try:
                start = self.parse_srt_timestamp(
                    start_text
                )

                end = self.parse_srt_timestamp(
                    end_text.split()[0]
                )

            except ValueError:
                continue

            # -------------------------------------------------
            # Split subtitle interval against removed regions.
            # -------------------------------------------------

            pieces = [
                (start, end)
            ]

            for cut_start, cut_end in self.normalize_cuts():

                new_pieces = []

                for piece_start, piece_end in pieces:

                    # No overlap
                    if (
                        piece_end <= cut_start
                        or piece_start >= cut_end
                    ):
                        new_pieces.append(
                            (
                                piece_start,
                                piece_end
                            )
                        )
                        continue

                    # Left surviving portion
                    if piece_start < cut_start:
                        new_pieces.append(
                            (
                                piece_start,
                                cut_start
                            )
                        )

                    # Right surviving portion
                    if piece_end > cut_end:
                        new_pieces.append(
                            (
                                cut_end,
                                piece_end
                            )
                        )

                pieces = new_pieces

                if not pieces:
                    break

            for piece_start, piece_end in pieces:

                mapped_start = (
                    self.map_original_time_to_output(
                        piece_start
                    )
                )

                mapped_end = (
                    self.map_original_time_to_output(
                        piece_end
                    )
                )

                if (
                    mapped_start is None
                    or mapped_end is None
                ):
                    continue

                if mapped_end <= mapped_start:
                    continue

                subtitle_text = lines[
                    timestamp_index + 1:
                ]

                output_block = [
                    str(counter),
                    (
                        self.format_srt_timestamp(
                            mapped_start
                        )
                        + " --> "
                        + self.format_srt_timestamp(
                            mapped_end
                        )
                    )
                ]

                output_block.extend(
                    subtitle_text
                )

                output_blocks.append(
                    "\n".join(
                        output_block
                    )
                )

                counter += 1

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(
                "\n\n".join(
                    output_blocks
                )
            )

            if output_blocks:
                f.write("\n")

    # =====================================================
    # Extract subtitle
    # =====================================================

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
            errors="replace"
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Could not extract subtitle stream "
                f"{stream_index}:\n\n"
                + result.stderr
            )

    # =====================================================
    # Build main video/audio filter
    # =====================================================

    def build_filter_complex(self):
        kept = self.calculate_kept_segments()

        if not kept:
            raise ValueError(
                "The cuts remove the entire video."
            )

        parts = []

        # -----------------------------
        # Video
        # -----------------------------

        video_labels = []

        for i, (start, end) in enumerate(kept):

            label = f"v{i}"

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

        # -----------------------------
        # Audio
        # -----------------------------

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

    # =====================================================
    # Quality
    # =====================================================

    def get_crf(self):
        quality = self.quality_var.get()

        if quality == "Very High":
            return "16"

        if quality == "High":
            return "18"

        return "20"

    # =====================================================
    # Audio encoder
    # =====================================================

    def get_audio_settings(self):
        """
        Use AAC for maximum compatibility.

        Preserve channel count/layout where possible.
        """

        if not self.audio_streams:
            return []

        return [
            "-c:a",
            "aac",
            "-b:a",
            "640k"
        ]

    # =====================================================
    # Export preparation
    # =====================================================

    def prepare_subtitles(
        self,
        temp_dir
    ):
        """
        Extract and retime every SRT subtitle stream.

        Returns a list containing:

            {
                "path": ...,
                "stream": original_stream
            }
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
                    f"{number + 1}/{len(self.subtitle_streams)}..."
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

            prepared.append(
                {
                    "path": retimed_path,
                    "stream": stream
                }
            )

        return prepared

    # =====================================================
    # Subtitle metadata
    # =====================================================

    @staticmethod
    def clean_metadata_value(value):
        if value is None:
            return ""

        return str(value).strip()

    # =====================================================
    # Main export
    # =====================================================

    def start_export(self):
        if self.worker and self.worker.is_alive():
            return

        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        if not ffmpeg or not ffprobe:
            messagebox.showerror(
                "FFmpeg/FFprobe Missing",
                "Both ffmpeg.exe and ffprobe.exe "
                "are required."
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
                "Add at least one cut."
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
                "Output must be different "
                "from the original."
            )
            return

        output_dir = os.path.dirname(
            os.path.abspath(
                self.output_file
            )
        )

        if not os.path.isdir(output_dir):
            messagebox.showerror(
                "Invalid Output Folder",
                "The output folder does not exist."
            )
            return

        if os.path.exists(
            self.output_file
        ):
            answer = messagebox.askyesno(
                "Overwrite?",
                "The output already exists.\n\n"
                "Replace it?"
            )

            if not answer:
                return

        output_duration = (
            self.calculate_output_duration()
        )

        if output_duration <= 0.1:
            messagebox.showerror(
                "Invalid Cuts",
                "The cuts remove the entire video."
            )
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

    # =====================================================
    # Export implementation
    # =====================================================

    def export_video(self):
        ffmpeg = self.find_ffmpeg()
        ffprobe = self.find_ffprobe()

        self.export_temp_dir = None

        try:
            output_dir = os.path.dirname(
                os.path.abspath(
                    self.output_file
                )
            )

            temp_dir = tempfile.mkdtemp(
                prefix=".family_safe_v3_",
                dir=output_dir
            )

            self.export_temp_dir = temp_dir

            # -------------------------------------------------
            # STEP 1
            # Prepare subtitles
            # -------------------------------------------------

            self.ui_queue.put(
                (
                    "status",
                    "Preparing subtitles..."
                )
            )

            prepared_subtitles = (
                self.prepare_subtitles(
                    temp_dir
                )
            )

            if self.cancel_requested:
                raise RuntimeError(
                    "Export cancelled."
                )

            # -------------------------------------------------
            # STEP 2
            # Build video/audio filter
            # -------------------------------------------------

            (
                filter_complex,
                audio_labels
            ) = self.build_filter_complex()

            # -------------------------------------------------
            # STEP 3
            # First output:
            #
            # Video + Audio only
            # -------------------------------------------------

            intermediate = os.path.join(
                temp_dir,
                "video_audio.mkv"
            )

            command = [
                ffmpeg,
                "-hide_banner",
                "-y",

                "-i",
                self.input_file,

                "-filter_complex",
                filter_complex,

                "-map",
                "[vout]"
            ]

            for label in audio_labels:
                command.extend(
                    [
                        "-map",
                        f"[{label}]"
                    ]
                )

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

            command.extend(
                self.get_audio_settings()
            )

            # Reset container-level chapters.
            command.extend(
                [
                    "-map_metadata",
                    "0",

                    "-map_chapters",
                    "-1",

                    "-avoid_negative_ts",
                    "make_zero",

                    "-f",
                    "matroska",

                    "-progress",
                    "pipe:1",

                    "-nostats",

                    intermediate
                ]
            )

            self.ui_queue.put(
                (
                    "status",
                    "Encoding video and audio..."
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

                    if (
                        self.process.poll()
                        is not None
                    ):
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

                        if total_duration:

                            percentage = min(
                                100.0,
                                (
                                    current
                                    / total_duration
                                ) * 100.0
                            )

                            # Leave some room for
                            # subtitle/remux verification.
                            percentage *= 0.90

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
                    "FFmpeg failed while encoding "
                    "video/audio."
                )

            if not os.path.isfile(
                intermediate
            ):
                raise RuntimeError(
                    "The intermediate video/audio "
                    "file was not created."
                )

            # -------------------------------------------------
            # STEP 4
            # Final remux
            # -------------------------------------------------

            self.ui_queue.put(
                (
                    "status",
                    "Adding retimed subtitles..."
                )
            )

            final_temp = os.path.join(
                temp_dir,
                "final.mkv"
            )

            remux_command = [
                ffmpeg,
                "-hide_banner",
                "-y",

                "-i",
                intermediate
            ]

            # Add each retimed SRT as a new input.
            for item in prepared_subtitles:
                remux_command.extend(
                    [
                        "-i",
                        item["path"]
                    ]
                )

            # Main video/audio.
            remux_command.extend(
                [
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?"
                ]
            )

            # Subtitle inputs.
            for i, item in enumerate(
                prepared_subtitles
            ):
                remux_command.extend(
                    [
                        "-map",
                        f"{i + 1}:0"
                    ]
                )

            # Copy already encoded streams.
            remux_command.extend(
                [
                    "-c",
                    "copy"
                ]
            )

            # Subtitle codec.
            if prepared_subtitles:
                remux_command.extend(
                    [
                        "-c:s",
                        "srt"
                    ]
                )

            # -------------------------------------------------
            # Subtitle metadata.
            # -------------------------------------------------

            for output_index, item in enumerate(
                prepared_subtitles
            ):

                stream = item["stream"]

                tags = stream.get(
                    "tags",
                    {}
                )

                language = tags.get(
                    "language"
                )

                title = tags.get(
                    "title"
                )

                if language:
                    remux_command.extend(
                        [
                            f"-metadata:s:s:{output_index}",
                            f"language={language}"
                        ]
                    )

                if title:
                    remux_command.extend(
                        [
                            f"-metadata:s:s:{output_index}",
                            f"title={title}"
                        ]
                    )

                disposition = stream.get(
                    "disposition",
                    {}
                )

                disposition_values = []

                for key, enabled in disposition.items():

                    if enabled:
                        disposition_values.append(
                            key
                        )

                if disposition_values:
                    remux_command.extend(
                        [
                            f"-disposition:s:{output_index}",
                            "+".join(
                                disposition_values
                            )
                        ]
                    )

            # Global metadata.
            remux_command.extend(
                [
                    "-map_metadata",
                    "0",

                    "-map_chapters",
                    "-1",

                    "-avoid_negative_ts",
                    "make_zero",

                    "-f",
                    "matroska",

                    final_temp
                ]
            )

            result = subprocess.run(
                remux_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "FFmpeg failed while adding subtitles.\n\n"
                    + result.stderr[-4000:]
                )

            if not os.path.isfile(
                final_temp
            ):
                raise RuntimeError(
                    "Final MKV was not created."
                )

            # -------------------------------------------------
            # STEP 5
            # Verify output
            # -------------------------------------------------

            self.ui_queue.put(
                (
                    "status",
                    "Verifying final video..."
                )
            )

            actual_duration = (
                self.probe_duration(
                    ffprobe,
                    final_temp
                )
            )

            expected_duration = (
                self.calculate_output_duration()
            )

            difference = abs(
                actual_duration
                - expected_duration
            )

            # Allow small container/rounding differences.
            if difference > 3.0:
                raise RuntimeError(
                    "Output duration verification failed.\n\n"
                    f"Expected approximately: "
                    f"{self.format_time(expected_duration)}\n"
                    f"Actual: "
                    f"{self.format_time(actual_duration)}\n\n"
                    "The output was NOT copied over the "
                    "requested destination."
                )

            # -------------------------------------------------
            # STEP 6
            # Atomically move final file.
            # -------------------------------------------------

            self.ui_queue.put(
                (
                    "status",
                    "Finalizing..."
                )
            )

            if os.path.exists(
                self.output_file
            ):
                os.remove(
                    self.output_file
                )

            shutil.move(
                final_temp,
                self.output_file
            )

            # -------------------------------------------------
            # Success
            # -------------------------------------------------

            self.ui_queue.put(
                (
                    "progress",
                    100
                )
            )

            self.ui_queue.put(
                (
                    "success",
                    {
                        "path": self.output_file,
                        "duration": actual_duration,
                        "subtitle_count": len(
                            prepared_subtitles
                        )
                    }
                )
            )

        except Exception as exc:

            # Remove partially generated destination.
            try:
                if (
                    self.output_file
                    and os.path.isfile(
                        self.output_file
                    )
                ):
                    # Only remove it if it was created
                    # during this run. Since we don't
                    # write to it until the very end,
                    # normally nothing needs doing here.
                    pass
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

            # Temporary directory cleanup.
            if self.export_temp_dir:

                def cleanup():
                    time.sleep(1)

                    try:
                        shutil.rmtree(
                            self.export_temp_dir,
                            ignore_errors=True
                        )
                    except Exception:
                        pass

                threading.Thread(
                    target=cleanup,
                    daemon=True
                ).start()

    # =====================================================
    # Probe output duration
    # =====================================================

    def probe_duration(
        self,
        ffprobe,
        path
    ):
        command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path
        ]

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
                "Could not verify output duration."
            )

        try:
            return float(
                result.stdout.strip()
            )
        except ValueError:
            raise RuntimeError(
                "FFprobe returned an invalid "
                "output duration."
            )

    # =====================================================
    # stderr
    # =====================================================

    def read_stderr(self):
        if not self.process:
            return

        try:
            for line in self.process.stderr:

                if self.cancel_requested:
                    break

        except Exception:
            pass

    # =====================================================
    # Cancel
    # =====================================================

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

            self.terminate_process()

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

    # =====================================================
    # UI queue
    # =====================================================

    def poll_ui_queue(self):

        try:

            while True:

                message_type, value = (
                    self.ui_queue.get_nowait()
                )

                # -----------------------------------------
                # Media loaded
                # -----------------------------------------

                if message_type == "media_loaded":

                    duration = value[
                        "duration"
                    ]

                    self.duration_var.set(
                        "Duration: "
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
                            f"Video: "
                            f"{value['video']}    "
                            f"Audio: "
                            f"{value['audio']}    "
                            f"Subtitles: "
                            f"{value['subtitles']}    "
                            f"Attachments: "
                            f"{value['attachments']}"
                        )
                    )

                    self.status_var.set(
                        "Video loaded."
                    )

                # -----------------------------------------
                # Preview
                # -----------------------------------------

                elif message_type == "preview":

                    self.show_preview(
                        value
                    )

                # -----------------------------------------
                # Progress
                # -----------------------------------------

                elif message_type == "progress":

                    self.progress[
                        "value"
                    ] = float(value)

                    self.status_var.set(
                        f"Exporting... "
                        f"{float(value):.1f}%"
                    )

                # -----------------------------------------
                # Status
                # -----------------------------------------

                elif message_type == "status":

                    self.status_var.set(
                        value
                    )

                # -----------------------------------------
                # Success
                # -----------------------------------------

                elif message_type == "success":

                    self.progress[
                        "value"
                    ] = 100

                    info = value

                    self.status_var.set(
                        "Export complete."
                    )

                    messagebox.showinfo(
                        "Export Complete",
                        (
                            "Family-safe video created.\n\n"
                            f"{info['path']}\n\n"
                            f"Final duration: "
                            f"{self.format_time(info['duration'])}\n"
                            f"Retimed subtitles: "
                            f"{info['subtitle_count']}"
                        )
                    )

                # -----------------------------------------
                # Error
                # -----------------------------------------

                elif message_type == "error":

                    self.status_var.set(
                        "Error."
                    )

                    messagebox.showerror(
                        "Export Error",
                        value
                    )

                # -----------------------------------------
                # Finished
                # -----------------------------------------

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


# =========================================================
# MAIN
# =========================================================

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
