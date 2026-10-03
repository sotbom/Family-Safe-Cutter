\# FamilySafeCutter



\*\*FamilySafeCutter\*\* is a Windows desktop application for creating family-safe versions of video files by removing unwanted sections while preserving the remaining media.



The application provides a graphical timeline-based workflow for selecting sections to remove, previewing the media, and exporting the processed video through FFmpeg.



\## Features



\- Simple desktop GUI built with Python and Tkinter

\- Supports common video formats:

&#x20; - MKV

&#x20; - MP4

&#x20; - MOV

&#x20; - M4V

&#x20; - WebM

&#x20; - AVI

&#x20; - TS

\- Media information detection through FFprobe

\- Interactive video timeline

\- Select start and end points for cuts

\- Add multiple cut sections

\- Remove individual cuts or clear all cuts

\- Fine timeline adjustment:

&#x20; - `←` / `→` — move by 0.1 seconds

&#x20; - `SHIFT + ←` / `SHIFT + →` — move by 1 second

\- Video preview/seeking

\- Displays detected media stream information

\- Handles audio streams during export

\- Handles subtitle streams

\- Retimes supported SRT subtitles after cuts

\- Preserves Matroska attachment streams when present

\- Adjustable encoding quality:

&#x20; - Very High

&#x20; - High

&#x20; - Balanced

\- Export progress reporting

\- Export cancellation

\- Prevents overwriting the source video

\- Automatically generates a default output filename

\- Windows FFmpeg console windows are hidden during processing



\## How It Works



FamilySafeCutter does not directly decode and encode video itself.



Instead, it uses:



\- \*\*FFprobe\*\* to inspect the input media and detect duration and available streams.

\- \*\*FFmpeg\*\* to generate previews and perform the final video export.



The application determines which portions of the video should be removed and builds an FFmpeg filter graph containing the remaining portions.



For subtitle streams using the SubRip (`.srt`) format, the application extracts the subtitles, adjusts their timestamps according to the removed sections, and adds the retimed subtitles to the exported video.



\## Requirements



\### Operating System



The current application is designed primarily for \*\*Windows\*\*.



\### Python



Python 3.10+ is recommended.



Python's standard library is sufficient to run the application. No third-party Python packages are required by the application itself.



\### FFmpeg



Both of the following executables are required:



\- `ffmpeg.exe`

\- `ffprobe.exe`



The application first checks whether FFmpeg/FFprobe are available through the system `PATH`.



It also checks the following Windows locations:



```text

C:\\ffmpeg\\bin\\ffmpeg.exe

C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe

C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe

