# FamilySafeCutter

 **FamilySafeCutter** is a Windows desktop application for creating family-safe versions of video files by removing unwanted sections while preserving the remaining media.

 The application provides a graphical timeline-based workflow for selecting sections to remove, previewing the media, and exporting the processed video through FFmpeg.

 ## Features

 - Simple desktop GUI built with Python and Tkinter
- Supports common video formats:
  - MKV
  - MP4
  - MOV
  - M4V
  - WebM
  - AVI
  - TS
- Media information detection through FFprobe
- Interactive video timeline
- Select start and end points for cuts
- Add multiple cut sections
- Remove individual cuts or clear all cuts
- Fine timeline adjustment:
  - `←` / `→` — move by 0.1 seconds
  - `SHIFT + ←` / `SHIFT + →` — move by 1 second
- Video preview and seeking
- Displays detected media stream information
- Handles audio streams during export
- Handles subtitle streams
- Retimes supported SRT subtitles after cuts
- Preserves Matroska attachment streams when present
- Adjustable encoding quality:
  - Very High
  - High
  - Balanced
- Export progress reporting
- Export cancellation
- Prevents overwriting the source video
- Automatically generates a default output filename
- Windows FFmpeg console windows are hidden during processing

 ## How It Works

 FamilySafeCutter does not directly decode and encode video itself.

 Instead, it uses:

 - **FFprobe** to inspect the input media and detect duration and available streams.
- **FFmpeg** to generate previews and perform the final video export.

 The application determines which portions of the video should be removed and builds an FFmpeg filter graph containing the remaining portions.

 For subtitle streams using the SubRip (`.srt`) format, the application extracts the subtitles, adjusts their timestamps according to the removed sections, and adds the retimed subtitles to the exported video.

 ## Requirements

 ### Operating System

 The current application is designed primarily for **Windows**.

 ### Python

 Python **3.10+** is recommended.

 Python's standard library is sufficient to run the application. No third-party Python packages are required by the application itself.

 ### FFmpeg

 Both of the following executables are required:

```
ffmpeg.exe
ffprobe.exe
```

 The application first checks whether FFmpeg/FFprobe are available through the system `PATH`.

 It also checks the following Windows locations:

```
C:\ffmpeg\bin\ffmpeg.exe
C:\Program Files\ffmpeg\bin\ffmpeg.exe
C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe
```

 Make sure both `ffmpeg.exe` and `ffprobe.exe` are available in one of these locations or are accessible through the system `PATH`.

 ## Installation

 ### 1\. Install Python

 Install Python 3.10 or newer and make sure Python is available from the command line.

 Verify the installation:

```
python --version
```

 ### 2\. Install FFmpeg

 Install FFmpeg and ensure that both `ffmpeg.exe` and `ffprobe.exe` are available.

 Verify the installation:

```
ffmpeg -version
ffprobe -version
```

 ### 3\. Clone the Repository

```
git clone https://github.com/sotbom/Family-Safe-Cutter.git
cd Family-Safe-Cutter
```

 ### 4\. Run the Application

 Run the main Python application:

```
python FamilySafeCutterV4.py
```

 ## Usage

 1. Launch FamilySafeCutter.
2. Select the video file you want to process.
3. Allow the application to analyze the media streams.
4. Use the timeline to navigate through the video.
5. Select the start and end points of sections you want to remove.
6. Add the selected section to the cut list.
7. Repeat the process for additional sections.
8. Review the cut list.
9. Select the desired encoding quality.
10. Choose the output location if required.
11. Start the export.
12. FamilySafeCutter uses FFmpeg to generate the processed video.

 The original source video is not overwritten.

 ## Timeline Controls

 | Key | Action |
| --- | --- |
| `←` | Move timeline position backward by 0.1 seconds |
| `→` | Move timeline position forward by 0.1 seconds |
| `SHIFT + ←` | Move timeline position backward by 1 second |
| `SHIFT + →` | Move timeline position forward by 1 second |

## Subtitle Handling

 FamilySafeCutter supports subtitle processing for **SubRip (`.srt`)** subtitles.

 When sections are removed from a video, the application adjusts subtitle timestamps so that subtitles remain synchronized with the resulting video.

 Subtitle timing is recalculated based on the portions of the video that remain after the selected cuts are applied.

 ## Matroska Attachments

 When working with Matroska (`.mkv`) files, FamilySafeCutter can preserve supported attachment streams when exporting the processed media.

 This can be useful for MKV files containing embedded resources such as fonts used by subtitle streams.

 ## Encoding Quality

 FamilySafeCutter provides three encoding quality levels:

 - **Very High**
- **High**
- **Balanced**

 Higher quality settings generally produce better visual quality but may require more processing time and result in larger output files.

 ## FFmpeg Processing

 FamilySafeCutter relies on FFmpeg for media processing rather than implementing its own video codec pipeline.

 The general workflow is:

```
Input Video
    │
    ▼
   FFprobe
    │
    ├── Detect duration
    ├── Detect video streams
    ├── Detect audio streams
    ├── Detect subtitle streams
    └── Detect attachments
    │
    ▼
FamilySafeCutter
    │
    ├── Select sections to remove
    ├── Build remaining timeline
    └── Process subtitle timestamps
    │
    ▼
   FFmpeg
    │
    ▼
Output Video
```

 ## Project Structure

 The main application is contained in the Python source file:

```
FamilySafeCutterV4.py
```

 A typical project structure may look like:

```
Family-Safe-Cutter/
│
├── FamilySafeCutterV4.py
├── README.md
├── LICENSE
└── ...
```

 ## Troubleshooting

 ### FFmpeg Not Found

 If the application cannot find FFmpeg or FFprobe, verify that:

```
ffmpeg -version
ffprobe -version
```

 work from Command Prompt.

 If they do not, add the FFmpeg `bin` directory to your Windows `PATH`, or place FFmpeg in one of the supported locations checked by the application.

 ### Export Fails

 If an export fails:

 - Check that the input video is readable.
- Make sure sufficient disk space is available.
- Verify that FFmpeg is installed correctly.
- Check that the output file is not already in use by another application.
- Review the application's FFmpeg output/error information.

 ### Subtitle Timing Issues

 Subtitle retiming currently targets supported **SRT** subtitle streams. Other subtitle formats may not receive the same timestamp adjustment behavior.

 ## License

 This project is distributed under the license included in the repository.

 See the `LICENSE` file for details.

 ## Disclaimer

 FamilySafeCutter is intended for personal media processing and editing.

 Users are responsible for ensuring that their use of the application and any media they process complies with applicable laws, licenses, copyrights, and terms of service.

 ## Contributing

 Contributions, bug reports, and suggestions are welcome.

 Before submitting a pull request, please ensure that changes are tested on Windows and that existing functionality remains intact.

 ## Repository

 GitHub:

 https://github.com/sotbom/Family-Safe-Cutter