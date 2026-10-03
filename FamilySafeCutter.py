import os
import re
import sys
import signal
import shutil
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_TITLE = "Family-Safe Video Cutter"
VIDEO_CRF = "18"


class FamilySafeCutter:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x700")
        self.root.minsize(780, 600)

        self.input_file = ""
        self.output_file = ""
        self.duration = 0.0
        self.cuts = []
        self.process = None
        self.worker = None
        self.cancel_requested = False
        self.ui_queue = queue.Queue()

        self.build_ui()
        self.check_ffmpeg()
        self.poll_ui_queue()

    # ---------------------------------------------------------
    # FFmpeg
    # ---------------------------------------------------------

    def find_ffmpeg(self):
        exe = shutil.which("ffmpeg")
        if exe:
            return exe

        # Common Windows locations
        candidates = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]

        for path in candidates:
            if os.path.isfile(path):
                return path

        return None

    def check_ffmpeg(self):
        ffmpeg = self.find_ffmpeg()

        if ffmpeg:
            self.ffmpeg_path.set(ffmpeg)
            self.status_var.set("FFmpeg detected.")
        else:
            self.status_var.set("FFmpeg was not found.")

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
            self.ffmpeg_path.set(path)
            self.status_var.set("FFmpeg selected.")

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------

    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        self.ffmpeg_path = tk.StringVar()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.duration_var = tk.StringVar(value="Duration: —")
        self.progress_var = tk.DoubleVar(value=0)

        # Input
        input_frame = ttk.LabelFrame(
            self.root, text="1. Input Video", padding=12
        )
        input_frame.pack(fill="x", padx=15, pady=(15, 8))

        ttk.Entry(
            input_frame,
            textvariable=self.input_var,
            state="readonly",
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            input_frame,
            text="Browse...",
            command=self.choose_input,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            input_frame,
            textvariable=self.duration_var,
        ).pack(anchor="w", pady=(8, 0))

        # Output
        output_frame = ttk.LabelFrame(
            self.root, text="2. Output Video", padding=12
        )
        output_frame.pack(fill="x", padx=15, pady=8)

        ttk.Entry(
            output_frame,
            textvariable=self.output_var,
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            output_frame,
            text="Save As...",
            command=self.choose_output,
        ).pack(side="left", padx=(8, 0))

        # Cuts
        cuts_frame = ttk.LabelFrame(
            self.root, text="3. Scenes to Remove", padding=12
        )
        cuts_frame.pack(fill="both", expand=True, padx=15, pady=8)

        instructions = (
            "Enter timestamps as HH:MM:SS, MM:SS, or seconds. "
            "Example: 00:12:31 → 00:13:45"
        )

        ttk.Label(
            cuts_frame,
            text=instructions,
        ).pack(anchor="w", pady=(0, 10))

        entry_frame = ttk.Frame(cuts_frame)
        entry_frame.pack(fill="x")

        ttk.Label(entry_frame, text="Start:").pack(side="left")

        self.start_entry = ttk.Entry(entry_frame, width=15)
        self.start_entry.pack(side="left", padx=(5, 15))

        ttk.Label(entry_frame, text="End:").pack(side="left")

        self.end_entry = ttk.Entry(entry_frame, width=15)
        self.end_entry.pack(side="left", padx=5)

        ttk.Button(
            entry_frame,
            text="Add Cut",
            command=self.add_cut,
        ).pack(side="left", padx=10)

        # Cut list
        list_frame = ttk.Frame(cuts_frame)
        list_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.cut_list = tk.Listbox(
            list_frame,
            height=12,
            font=("Consolas", 10),
        )
        self.cut_list.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.cut_list.yview,
        )
        scrollbar.pack(side="right", fill="y")

        self.cut_list.configure(
            yscrollcommand=scrollbar.set
        )

        buttons = ttk.Frame(cuts_frame)
        buttons.pack(fill="x", pady=(8, 0))

        ttk.Button(
            buttons,
            text="Remove Selected",
            command=self.remove_selected_cut,
        ).pack(side="left")

        ttk.Button(
            buttons,
            text="Clear All",
            command=self.clear_cuts,
        ).pack(side="left", padx=8)

        # Quality
        settings = ttk.LabelFrame(
            self.root, text="4. Export Settings", padding=12
        )
        settings.pack(fill="x", padx=15, pady=8)

        ttk.Label(
            settings,
            text="Video quality:",
        ).pack(side="left")

        self.quality_var = tk.StringVar(value="Very High")

        quality_combo = ttk.Combobox(
            settings,
            textvariable=self.quality_var,
            values=[
                "Very High",
                "High",
                "Balanced",
            ],
            state="readonly",
            width=15,
        )
        quality_combo.pack(side="left", padx=8)

        ttk.Label(
            settings,
            text="Recommended: Very High",
        ).pack(side="left", padx=10)

        # Progress
        progress_frame = ttk.LabelFrame(
            self.root, text="5. Export", padding=12
        )
        progress_frame.pack(fill="x", padx=15, pady=8)

        ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
        ).pack(fill="x")

        ttk.Label(
            progress_frame,
            textvariable=self.status_var,
        ).pack(anchor="w", pady=(7, 0))

        # Bottom buttons
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=15, pady=(5, 15))

        ttk.Button(
            bottom,
            text="Check FFmpeg",
            command=self.check_ffmpeg,
        ).pack(side="left")

        ttk.Button(
            bottom,
            text="Select FFmpeg...",
            command=self.choose_ffmpeg,
        ).pack(side="left", padx=8)

        self.export_button = ttk.Button(
            bottom,
            text="Export Family-Safe Video",
            command=self.start_export,
        )
        self.export_button.pack(side="right")

        self.cancel_button = ttk.Button(
            bottom,
            text="Cancel",
            command=self.cancel_export,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=8)

    # ---------------------------------------------------------
    # File selection
    # ---------------------------------------------------------

    def choose_input(self):
        path = filedialog.askopenfilename(
            title="Select Movie or Episode",
            filetypes=[
                (
                    "Video files",
                    "*.mkv *.mp4 *.avi *.mov *.m4v *.webm *.ts",
                ),
                ("All files", "*.*"),
            ],
        )

        if not path:
            return

        self.input_file = path
        self.input_var.set(path)

        base, _ = os.path.splitext(path)
        default_output = base + " - Family.mkv"
        self.output_file = default_output
        self.output_var.set(default_output)

        self.duration = 0
        self.duration_var.set("Reading duration...")
        self.status_var.set("Reading video information...")

        threading.Thread(
            target=self.read_media_info,
            daemon=True,
        ).start()

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Family-Safe Video",
            defaultextension=".mkv",
            filetypes=[
                ("Matroska video", "*.mkv"),
                ("MP4 video", "*.mp4"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.output_file = path
            self.output_var.set(path)

    # ---------------------------------------------------------
    # Media information
    # ---------------------------------------------------------

    def read_media_info(self):
        ffmpeg = self.find_ffmpeg()

        if not ffmpeg:
            self.ui_queue.put(
                ("error", "FFmpeg was not found.")
            )
            return

        command = [
            ffmpeg,
            "-hide_banner",
            "-i",
            self.input_file,
        ]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            text = result.stderr

            match = re.search(
                r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
                text,
            )

            if not match:
                self.ui_queue.put(
                    (
                        "error",
                        "Could not determine video duration.",
                    )
                )
                return

            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = float(match.group(3))

            self.duration = (
                hours * 3600
                + minutes * 60
                + seconds
            )

            self.ui_queue.put(
                (
                    "duration",
                    self.format_seconds(self.duration),
                )
            )

        except Exception as exc:
            self.ui_queue.put(
                (
                    "error",
                    f"Could not read video information:\n{exc}",
                )
            )

    # ---------------------------------------------------------
    # Timestamp handling
    # ---------------------------------------------------------

    @staticmethod
    def parse_timestamp(value):
        value = value.strip()

        if not value:
            raise ValueError("Timestamp is empty.")

        # Plain seconds
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return float(value)

        parts = value.split(":")

        try:
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])

                if not 0 <= seconds < 60:
                    raise ValueError

                return minutes * 60 + seconds

            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])

                if not 0 <= minutes < 60:
                    raise ValueError

                if not 0 <= seconds < 60:
                    raise ValueError

                return (
                    hours * 3600
                    + minutes * 60
                    + seconds
                )

        except ValueError:
            pass

        raise ValueError(
            f"Invalid timestamp: {value}"
        )

    @staticmethod
    def format_seconds(seconds):
        seconds = max(0, float(seconds))

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:05.2f}"
        )

    def normalize_cuts(self):
        if not self.cuts:
            return []

        cuts = sorted(self.cuts)

        merged = [list(cuts[0])]

        for start, end in cuts[1:]:
            previous = merged[-1]

            if start <= previous[1]:
                previous[1] = max(previous[1], end)
            else:
                merged.append([start, end])

        return [
            (start, end)
            for start, end in merged
        ]

    # ---------------------------------------------------------
    # Cut management
    # ---------------------------------------------------------

    def add_cut(self):
        try:
            start = self.parse_timestamp(
                self.start_entry.get()
            )
            end = self.parse_timestamp(
                self.end_entry.get()
            )

            if end <= start:
                raise ValueError(
                    "End timestamp must be after start."
                )

            if self.duration <= 0:
                raise ValueError(
                    "Select a valid video first."
                )

            if end > self.duration:
                raise ValueError(
                    "End timestamp is beyond the video duration."
                )

            self.cuts.append((start, end))
            self.cuts = self.normalize_cuts()

            self.refresh_cut_list()

            self.start_entry.delete(0, tk.END)
            self.end_entry.delete(0, tk.END)

        except ValueError as exc:
            messagebox.showerror(
                "Invalid Cut",
                str(exc),
            )

    def refresh_cut_list(self):
        self.cut_list.delete(0, tk.END)

        for start, end in self.cuts:
            self.cut_list.insert(
                tk.END,
                f"{self.format_seconds(start)}  →  "
                f"{self.format_seconds(end)}",
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

    def clear_cuts(self):
        self.cuts.clear()
        self.refresh_cut_list()

    # ---------------------------------------------------------
    # FFmpeg filter generation
    # ---------------------------------------------------------

    def build_filter_complex(self):
        """
        Build kept segments from the original timeline.

        Example:
            Cut 10-20
            Cut 40-50

        Kept:
            0-10
            20-40
            50-end

        Each video/audio segment has its timestamps reset.
        """

        cuts = self.normalize_cuts()

        kept = []
        cursor = 0.0

        for start, end in cuts:
            if start > cursor:
                kept.append((cursor, start))

            cursor = end

        if cursor < self.duration:
            kept.append((cursor, self.duration))

        if not kept:
            raise ValueError(
                "The selected cuts remove the entire video."
            )

        parts = []

        for i, (start, end) in enumerate(kept):
            parts.append(
                f"[0:v]trim=start={start:.6f}:end={end:.6f},"
                f"setpts=PTS-STARTPTS[v{i}]"
            )

            parts.append(
                f"[0:a]atrim=start={start:.6f}:end={end:.6f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

        concat_inputs = "".join(
            f"[v{i}][a{i}]"
            for i in range(len(kept))
        )

        parts.append(
            f"{concat_inputs}"
            f"concat=n={len(kept)}:v=1:a=1"
            f"[vout][aout]"
        )

        return ";".join(parts)

    # ---------------------------------------------------------
    # Export
    # ---------------------------------------------------------

    def get_crf(self):
        choice = self.quality_var.get()

        if choice == "Very High":
            return "16"

        if choice == "High":
            return "18"

        return "20"

    def start_export(self):
        if self.worker and self.worker.is_alive():
            return

        ffmpeg = self.find_ffmpeg()

        if not ffmpeg:
            messagebox.showerror(
                "FFmpeg Not Found",
                "FFmpeg could not be found.\n\n"
                "Install FFmpeg or select ffmpeg.exe.",
            )
            return

        if not self.input_file:
            messagebox.showerror(
                "No Input",
                "Please select a video first.",
            )
            return

        if not self.output_file:
            messagebox.showerror(
                "No Output",
                "Please choose an output filename.",
            )
            return

        if not self.cuts:
            messagebox.showerror(
                "No Cuts",
                "Add at least one scene to remove.",
            )
            return

        if os.path.abspath(self.input_file) == os.path.abspath(
            self.output_file
        ):
            messagebox.showerror(
                "Invalid Output",
                "The output must be different from the original.",
            )
            return

        if os.path.exists(self.output_file):
            answer = messagebox.askyesno(
                "Overwrite Output?",
                "The output file already exists.\n\n"
                "Replace it?",
            )

            if not answer:
                return

        self.cancel_requested = False
        self.progress_var.set(0)

        self.export_button.configure(
            state="disabled"
        )
        self.cancel_button.configure(
            state="normal"
        )

        self.worker = threading.Thread(
            target=self.export_video,
            daemon=True,
        )
        self.worker.start()

    def export_video(self):
        ffmpeg = self.find_ffmpeg()

        try:
            filter_complex = (
                self.build_filter_complex()
            )

            crf = self.get_crf()

            command = [
                ffmpeg,
                "-hide_banner",
                "-y",

                "-i",
                self.input_file,

                "-filter_complex",
                filter_complex,

                "-map",
                "[vout]",

                "-map",
                "[aout]",

                # High-quality H.264
                "-c:v",
                "libx264",

                "-preset",
                "medium",

                "-crf",
                crf,

                # Audio is re-encoded so its timeline matches
                # the removed video sections.
                "-c:a",
                "aac",

                "-b:a",
                "320k",

                # Preserve common container metadata.
                "-map_metadata",
                "0",

                "-map_chapters",
                "0",

                # MKV is the preferred output container.
                "-f",
                "matroska",

                # Machine-readable progress.
                "-progress",
                "pipe:1",

                "-nostats",

                self.output_file,
            ]

            self.ui_queue.put(
                (
                    "status",
                    "Starting FFmpeg export...",
                )
            )

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            stderr_thread = threading.Thread(
                target=self.read_stderr,
                daemon=True,
            )
            stderr_thread.start()

            total_duration = self.calculate_output_duration()

            while True:
                if self.cancel_requested:
                    self.terminate_process()
                    raise RuntimeError(
                        "Export cancelled."
                    )

                line = self.process.stdout.readline()

                if not line:
                    if self.process.poll() is not None:
                        break
                    continue

                line = line.strip()

                if line.startswith("out_time_ms="):
                    try:
                        microseconds = int(
                            line.split("=", 1)[1]
                        )

                        current_seconds = (
                            microseconds / 1_000_000
                        )

                        if total_duration > 0:
                            percent = min(
                                100,
                                (
                                    current_seconds
                                    / total_duration
                                ) * 100,
                            )

                            self.ui_queue.put(
                                ("progress", percent)
                            )

                    except ValueError:
                        pass

            return_code = self.process.wait()

            if self.cancel_requested:
                raise RuntimeError(
                    "Export cancelled."
                )

            if return_code != 0:
                raise RuntimeError(
                    "FFmpeg returned an error."
                )

            if not os.path.isfile(
                self.output_file
            ):
                raise RuntimeError(
                    "FFmpeg reported success, "
                    "but the output file was not found."
                )

            self.ui_queue.put(
                ("progress", 100)
            )

            self.ui_queue.put(
                (
                    "success",
                    self.output_file,
                )
            )

        except Exception as exc:
            self.ui_queue.put(
                (
                    "error",
                    str(exc),
                )
            )

        finally:
            self.process = None
            self.ui_queue.put(
                ("finished", None)
            )

    def read_stderr(self):
        if not self.process:
            return

        try:
            for line in self.process.stderr:
                if self.cancel_requested:
                    break

                line = line.strip()

                if line:
                    self.ui_queue.put(
                        ("ffmpeg_log", line)
                    )

        except Exception:
            pass

    def calculate_output_duration(self):
        total = self.duration

        for start, end in self.normalize_cuts():
            total -= end - start

        return max(0, total)

    # ---------------------------------------------------------
    # Cancellation
    # ---------------------------------------------------------

    def terminate_process(self):
        if not self.process:
            return

        try:
            if sys.platform.startswith("win"):
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

    def cancel_export(self):
        if not self.worker or not self.worker.is_alive():
            return

        answer = messagebox.askyesno(
            "Cancel Export?",
            "Cancel the current export?",
        )

        if answer:
            self.cancel_requested = True
            self.status_var.set(
                "Cancelling..."
            )

    # ---------------------------------------------------------
    # UI queue
    # ---------------------------------------------------------

    def poll_ui_queue(self):
        try:
            while True:
                message_type, value = (
                    self.ui_queue.get_nowait()
                )

                if message_type == "duration":
                    self.duration_var.set(
                        f"Duration: {value}"
                    )
                    self.status_var.set(
                        "Video loaded."
                    )

                elif message_type == "progress":
                    self.progress_var.set(
                        float(value)
                    )

                    self.status_var.set(
                        f"Exporting... "
                        f"{float(value):.1f}%"
                    )

                elif message_type == "status":
                    self.status_var.set(value)

                elif message_type == "ffmpeg_log":
                    # Keep the GUI concise.
                    # Detailed FFmpeg output is intentionally
                    # not displayed continuously.
                    pass

                elif message_type == "success":
                    self.progress_var.set(100)
                    self.status_var.set(
                        "Export completed successfully."
                    )

                    messagebox.showinfo(
                        "Export Complete",
                        "Family-safe video created successfully.\n\n"
                        f"{value}",
                    )

                elif message_type == "error":
                    self.status_var.set(
                        "Export failed."
                    )

                    messagebox.showerror(
                        "Error",
                        value,
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
            self.poll_ui_queue,
        )


def main():
    root = tk.Tk()

    app = FamilySafeCutter(root)

    root.protocol(
        "WM_DELETE_WINDOW",
        lambda: close_application(root, app),
    )

    root.mainloop()


def close_application(root, app):
    if app.worker and app.worker.is_alive():
        answer = messagebox.askyesno(
            "Export Running",
            "An export is currently running.\n\n"
            "Cancel it and exit?",
        )

        if not answer:
            return

        app.cancel_requested = True
        app.terminate_process()

    root.destroy()


if __name__ == "__main__":
    main()
