# FAMILY-SAFE CUTTER — PROJECT HANDOFF
## Development Status, Architecture, History & Next Steps

> Purpose of this document:
> This is a complete handoff for continuing development of the
> Family-Safe Cutter project in a new ChatGPT session.
>
> The next session should treat the current working export engine
> as stable and avoid unnecessary rewrites.

---

# 1. PROJECT OVERVIEW

## Project Name

Family-Safe Cutter

Current development version:

V4

Previous internal version:

V3

The application is a Windows desktop GUI video cutter designed
to remove unwanted sections from videos while preserving:

- Video
- Audio synchronization
- Subtitle synchronization
- Multiple subtitle streams where supported
- Multiple audio streams
- MKV / MP4 / MOV and other common video formats

The application uses:

- Python
- Tkinter
- FFmpeg
- FFprobe

The UI has a minimalist "hacker / terminal" aesthetic using:

- Dark green background
- Bright green accents
- Monospace fonts
- Minimalist panels
- Terminal-style status information

---

# 2. IMPORTANT CURRENT STATUS

## VERY IMPORTANT

The current export implementation is WORKING.

Do NOT casually rewrite the export pipeline.

A previous UX modification accidentally broke subtitle input handling
and produced this FFmpeg error:

    Option map (set input stream mapping) cannot be applied to input url
    ...
    you are trying to apply an input option to an output file or vice versa

That problem was traced to the newer export implementation.

The older V3 export preparation / subtitle workflow was restored,
and the application is now working again.

Therefore:

> Preserve the current working export implementation while
> packaging the application.

Any future changes should be incremental and tested.

---

# 3. WHAT HAS ALREADY BEEN ACHIEVED

## 3.1 Video cutting

The application can:

- Load a video
- Display its duration
- Select a START point
- Select an END point
- Add a cut
- Add multiple cuts
- Remove selected cuts
- Clear all cuts
- Normalize/merge overlapping cuts
- Calculate the portions of the video that should be retained

Example:

Original:

    00:00 ───────────────────────── 60:00

Cut:

    10:00 ───── 20:00

Output:

    00:00 ───── 10:00 + 20:00 ───── 60:00

The retained portions are concatenated into one output video.

---

# 4. VIDEO PREVIEW

The application has a frame preview system.

When the user moves the timeline handles:

- A preview request is scheduled
- FFmpeg generates a single preview frame
- The preview is displayed in the Tkinter GUI

The preview uses FFmpeg and creates a temporary PNG.

Current preview approach:

    ffmpeg
        -ss <time>
        -i <input>
        -frames:v 1
        -vf scale=900:-2
        <preview.png>

The preview is intentionally debounced to avoid spawning FFmpeg
for every single pixel of mouse movement.

Current delay:

    300 ms

Previous issue:

Launching the application through a BAT file caused visible
black CMD windows to flash when FFmpeg was invoked.

The application was also tested directly from CMD, which removed
those visible flashes.

The eventual packaged EXE should eliminate this user-facing problem.

---

# 5. TIMELINE UI

The timeline supports:

- START handle
- END handle
- Dragging handles
- Keyboard movement

Keyboard controls:

    ← / →              = 0.1 second
    SHIFT + ← / →      = 1 second

The timeline displays:

- Video duration
- Cut regions
- Start handle
- End handle
- Current position
- Time labels

Cuts are shown in red.

START is green.

END is red.

---

# 6. CUT MANAGEMENT

The application maintains:

    self.cuts

Each cut is represented as:

    (start_time, end_time)

Cuts are normalized with:

    normalize_cuts()

This:

- Sorts cuts
- Merges overlapping cuts
- Produces clean non-overlapping intervals

The export engine then calculates the KEPT portions using:

    calculate_kept_segments()

And calculates final output duration using:

    calculate_output_duration()

---

# 7. MEDIA PROBING

FFprobe is used to inspect the input media.

The application runs:

    ffprobe
        -v error
        -print_format json
        -show_format
        -show_streams
        <input>

The resulting JSON is used to determine:

- Duration
- Audio streams
- Subtitle streams
- Attachment streams
- Stream indexes
- Codec information

The application stores:

    self.media_info
    self.audio_streams
    self.subtitle_streams
    self.attachment_streams

---

# 8. AUDIO HANDLING

Audio streams are rebuilt according to the retained video segments.

For each audio stream:

- Each kept segment is trimmed with `atrim`
- Timestamps are reset using `asetpts`
- Segments are concatenated

Conceptually:

    [audio segment 1]
    [audio segment 2]
    [audio segment 3]

becomes:

    [audio 1] + [audio 2] + [audio 3]

The final audio streams are encoded as:

    AAC
    320k

This has been tested successfully.

---

# 9. VIDEO HANDLING

Video segments are processed with:

    trim
    setpts=PTS-STARTPTS

Then concatenated.

Final video codec:

    libx264

Preset:

    medium

CRF is selected from the UI.

Current quality mapping:

    Very High = CRF 16
    High      = CRF 18
    Balanced  = CRF 20

---

# 10. SUBTITLE HANDLING

THIS IS ONE OF THE MOST IMPORTANT PARTS OF THE PROJECT.

The application does NOT simply copy subtitle timestamps.

When video sections are removed, subtitle timestamps must also
be transformed to match the new output timeline.

Example:

Original:

    Video:
    0 ───────────────────────────── 100 sec

Cut:

    20 ───────── 40 sec

Output:

    0 ───── 20 sec
              +
    40 ───── 100 sec

The subtitle timestamps after 40 seconds must be shifted backward
by 20 seconds.

Additionally, subtitles overlapping removed sections need to be
handled correctly.

---

# 11. WORKING SUBTITLE PIPELINE

The currently working V3/V4 subtitle workflow is based on:

    prepare_subtitles()

This function:

1. Creates a temporary export directory
2. Extracts each supported subtitle stream
3. Converts it to SRT
4. Retimes the SRT
5. Produces a new retimed SRT file
6. Passes the retimed SRT files into the final FFmpeg export

Only SubRip subtitles are currently explicitly supported by this
workflow.

The code checks:

    stream.get("codec_name", "").lower()

and requires:

    subrip

Unsupported subtitle formats are skipped with a status message.

---

# 12. SUBTITLE RETIMING

The subtitle retiming process uses:

    retime_srt()

and helper functions such as:

    srt_time_to_seconds()
    seconds_to_srt_time()

The algorithm:

1. Reads every subtitle block
2. Finds its start/end timestamps
3. Checks overlap with each kept video segment
4. Discards subtitles that fall entirely inside removed sections
5. Clips subtitles that partially overlap removed sections
6. Shifts retained subtitles into the new output timeline
7. Writes a new SRT
8. Renumbers subtitle blocks

This is critical because subtitle synchronization is one of the
main reasons this application exists.

---

# 13. PREVIOUS SUBTITLE BUG

A broken export implementation attempted to add retimed subtitle
files like this:

    command.extend([
        "-i",
        subtitle_file
    ])

but then incorrectly calculated the subtitle input indexes.

This resulted in FFmpeg interpreting a subtitle path as an input
file in the wrong part of the command and generated an error similar
to:

    Option map (set input stream mapping) cannot be applied to input url

Therefore:

> DO NOT reconstruct the export command from memory.

Use the known working V3 export implementation as the baseline.

---

# 14. ATTACHMENTS

MKV files can contain attachments such as:

- Fonts
- Images
- Other attached resources

The application detects:

    codec_type == "attachment"

These are intended to be preserved.

The export pipeline uses attachment mapping where applicable.

This is particularly relevant for MKV files containing subtitle
fonts.

---

# 15. METADATA

The export process attempts to preserve source metadata using:

    -map_metadata 0

Chapters are currently removed using:

    -map_chapters -1

This is intentional in the current design because chapters can become
invalid after removing arbitrary sections.

---

# 16. EXPORT PROCESS

The export is performed in a background thread so the Tkinter UI
doesn't freeze.

Relevant state:

    self.worker
    self.process
    self.cancel_requested

The application uses a UI queue:

    self.ui_queue = queue.Queue()

Worker threads place messages into the queue.

Tkinter periodically processes them with:

    poll_ui_queue()

This avoids updating Tkinter widgets directly from background threads.

---

# 17. EXPORT PROGRESS

A progress bar exists in the GUI.

FFmpeg is launched with:

    -progress pipe:1
    -nostats

The application reads:

    out_time_ms=

and calculates:

    percentage =
        current_output_time /
        total_output_duration
        * 100

The progress bar is then updated.

The UI also displays:

    EXPORTING // XX.X%

---

# 18. EXPORT TIME ESTIMATION

This was one of the desired UX improvements.

The previous request was:

- Export loading/progress bar
- Estimated export time

The current project direction should retain the progress bar and add
a proper ETA display.

A future implementation can calculate:

    elapsed time
    processing rate
    remaining output duration
    estimated remaining wall-clock time

For example:

    EXPORTING // 42.7%
    ETA 00:03:18

This should be added without changing the actual FFmpeg export
pipeline.

---

# 19. CANCEL EXPORT

The UI contains a CANCEL button.

When pressed:

- The user is asked to confirm
- `cancel_requested` is set
- The FFmpeg process is terminated
- The export thread exits
- UI controls are restored

On Windows the current implementation attempts:

    CTRL_BREAK_EVENT

and falls back to:

    kill()

if required.

---

# 20. GUI DESIGN

Current visual direction:

    Hacker / terminal / minimalist

Primary colors:

    BG       = #080C0A
    PANEL    = #0D1410
    PANEL_2  = #101A14
    BORDER   = #1E3928

    GREEN    = #39FF88
    GREEN_DIM = #208A4A
    GREEN_DARK = #123D25

    TEXT     = #D9FFE5
    TEXT_DIM = #71977E

    RED      = #FF5264
    RED_DARK = #4D1820

Font:

    Cascadia Mono

The GUI is built with:

    tkinter
    ttk

---

# 21. GUI SECTIONS

Current interface contains:

    FAMILY-SAFE CUTTER // V3/V4

Sections:

    [ 01 // INPUT MEDIA ]

    [ 02 // FRAME PREVIEW ]

    [ 03 // CUT TIMELINE ]

    [ 04 // CUTS ]

    [ MEDIA STREAMS ]

    [ 05 // OUTPUT ]

Bottom status bar:

    Progress bar
    Status text
    FFmpeg status
    FFprobe status
    CANCEL
    EXPORT

---

# 22. FFmpeg STATUS

The UI displays:

    FFMPEG ● ONLINE

and:

    FFPROBE ● ONLINE

If missing:

    FFMPEG ● OFFLINE
    FFPROBE ● OFFLINE

There is also currently a manual:

    Select ffmpeg.exe

mechanism.

---

# 23. FFmpeg INSTALLATION HISTORY

During development, FFmpeg was installed manually on the developer
machine.

The machine required adding FFmpeg's `bin` directory to the Windows
PATH environment variable.

This made commands like:

    ffmpeg
    ffprobe

available from CMD.

This worked.

However:

> This is NOT the desired experience for normal users.

The finished application should NOT require users to:

- Install Python
- Install FFmpeg manually
- Modify Windows PATH
- Edit environment variables
- Use CMD
- Run a BAT file to launch the application

---

# 24. NEW DISTRIBUTION GOAL

The goal is:

    Double-click Family-Safe-Cutter.exe

and the application launches directly.

No CMD window.

No Python installation.

No manual FFmpeg PATH configuration.

No launcher BAT required.

---

# 25. PACKAGING TECHNOLOGY

The chosen packaging technology is:

    PyInstaller

PyInstaller supports:

    --onedir

and:

    --onefile

It also supports:

    --windowed
    --noconsole

for GUI applications.

Official PyInstaller documentation:

    https://pyinstaller.org/en/stable/usage.html

PyInstaller also supports adding additional data and binaries using:

    --add-data
    --add-binary

and supports custom `.spec` files for more complex packaging.

Reference:
PyInstaller documentation confirms that `--onedir` creates a folder
bundle, `--onefile` creates a single executable, and `--windowed`
prevents a console window for Windows GUI applications.

---

# 26. PACKAGING STRATEGY

IMPORTANT:

Do NOT immediately jump to a one-file EXE.

First build:

    --onedir
    --windowed

because debugging is easier.

Initial target:

    dist/
        Family-Safe-Cutter/
            Family-Safe-Cutter.exe
            supporting files...

Once that works:

    test thoroughly

Then move toward:

    --onefile
    --windowed

for the polished end-user build.

---

# 27. CURRENT PLANNED PROJECT STRUCTURE

The intended development directory is:

    D:\Family-Safe-Cutter\

Initial structure:

    D:\Family-Safe-Cutter\
    │
    ├── family_safe_cutter.py
    │
    └── ffmpeg\
        ├── ffmpeg.exe
        └── ffprobe.exe

Later structure:

    Family-Safe-Cutter/
    │
    ├── src/
    │   └── family_safe_cutter.py
    │
    ├── ffmpeg/
    │   ├── ffmpeg.exe
    │   └── ffprobe.exe
    │
    ├── assets/
    │   └── icon.ico
    │
    ├── build.bat
    ├── requirements.txt
    ├── README.md
    ├── LICENSE
    ├── .gitignore
    └── Family-Safe-Cutter.spec

---

# 28. FFmpeg DISCOVERY — NEXT CODE CHANGE

The current FFmpeg discovery logic uses:

    shutil.which("ffmpeg")

plus hardcoded Windows paths.

This must be improved for packaging.

Desired lookup order:

    1. Bundled FFmpeg beside the application
    2. Bundled ./ffmpeg/ directory
    3. System PATH
    4. Known Windows installation locations
    5. Manual user selection

The application should be able to locate:

    ffmpeg.exe
    ffprobe.exe

without the user modifying PATH.

---

# 29. IMPORTANT PACKAGING DETAIL

There are two different concepts:

## Development build

Files can exist as:

    application/
        Family-Safe-Cutter.exe
        ffmpeg/
            ffmpeg.exe
            ffprobe.exe

## One-file PyInstaller build

PyInstaller can include additional binaries using:

    --add-binary

or through the `.spec` file.

When running in one-file mode, bundled files are extracted into a
temporary `_MEI...` directory.

Therefore the Python code must be able to distinguish between:

    source/development location

and:

    PyInstaller runtime location

The next implementation should use PyInstaller runtime information,
typically involving:

    sys._MEIPASS

when appropriate.

However, do not blindly rewrite the code around this without testing
the actual onedir build first.

---

# 30. WHY ONEDIR FIRST

The first build should be:

    --onedir
    --windowed

This allows us to verify:

- GUI launches
- FFmpeg is found
- FFprobe is found
- Video loading works
- Preview works
- Timeline works
- Cuts work
- Audio remains synchronized
- Subtitles remain synchronized
- Export works
- Progress works
- Cancellation works

Only after that should we attempt:

    --onefile

PyInstaller's current documentation states that `--onedir` creates
a one-folder bundle and `--onefile` creates a single executable.

---

# 31. BUILD TOOL

PyInstaller should preferably be invoked with:

    python -m PyInstaller

rather than relying entirely on:

    pyinstaller

because this avoids some PATH/environment issues.

Installation:

    python -m pip install --upgrade pyinstaller

Version check:

    python -m PyInstaller --version

---

# 32. BUILD BAT

Eventually there should be a developer-only:

    build.bat

Its purpose is:

    Double-click build.bat
        ↓
    Clean old build
        ↓
    Run PyInstaller
        ↓
    Produce dist/
        ↓
    Report success/failure

The BAT file is NOT intended to launch the application.

It is only a developer build tool.

PyInstaller documentation explicitly supports using BAT files for
repeatable builds and Windows command-line continuation.

---

# 33. USER LAUNCHER

The final user should NOT need:

    launch.bat

The user should simply run:

    Family-Safe-Cutter.exe

The final EXE should be built using:

    --windowed

so there is no visible console window.

---

# 34. GITHUB OPEN-SOURCE PLAN

After the Windows EXE is stable, the project should be published
to GitHub.

Proposed repository:

    family-safe-cutter

Possible repository structure:

    family-safe-cutter/
    │
    ├── src/
    │   └── family_safe_cutter.py
    │
    ├── assets/
    │
    ├── build.bat
    ├── requirements.txt
    ├── Family-Safe-Cutter.spec
    ├── README.md
    ├── LICENSE
    ├── .gitignore
    └── docs/

---

# 35. README CONTENT

README should explain:

- What Family-Safe Cutter is
- Why it exists
- Features
- Supported formats
- Installation
- Running the application
- FFmpeg requirements
- Building from source
- Creating an EXE
- Known limitations
- Subtitle support
- License
- Credits

The README should be friendly enough for normal users and useful
enough for developers.

---

# 36. LICENSE

An open-source license should be explicitly selected.

A likely candidate:

    MIT License

But this should be confirmed before publication.

Important:

FFmpeg is a separate project with its own licensing considerations.

Do not assume that the application's license automatically applies
to FFmpeg binaries.

Before distributing FFmpeg binaries through GitHub releases, review
the applicable FFmpeg licensing/build information and document the
relationship appropriately.

---

# 37. GITIGNORE

The repository should NOT include generated build output.

Likely exclusions:

    __pycache__/
    *.pyc

    build/
    dist/

    *.spec

or include the `.spec` file deliberately if it is part of the
official reproducible build.

Also exclude:

    .family_safe_preview/
    .family_safe_subtitles/
    temporary files
    IDE files
    local test media

Do NOT commit personal videos.

---

# 38. RELEASE STRATEGY

Once stable:

    v4.0.0

could be the first public release.

Possible release artifact:

    Family-Safe-Cutter-v4.0.0-Windows.zip

or later:

    Family-Safe-Cutter-v4.0.0-Setup.exe

Potential contents:

    Family-Safe-Cutter.exe
    ffmpeg/
    ffprobe
    README
    LICENSE
    third-party notices

---

# 39. POSSIBLE FUTURE INSTALLER

After the basic EXE works, a proper Windows installer could be added.

Possible future flow:

    Family-Safe-Cutter-Setup.exe
            ↓
    Install
            ↓
    Start Menu shortcut
            ↓
    Desktop shortcut
            ↓
    Uninstall support

This is NOT the immediate task.

First get the application working as an EXE.

---

# 40. FUTURE UX IMPROVEMENTS

The application should NOT be over-engineered.

The guiding principle:

    Keep it fast.
    Keep it simple.
    Keep it reliable.

Potential future improvements:

- Export ETA
- Better export status
- Better error messages
- Output folder shortcut
- Recent files
- Better subtitle codec support
- More polished timeline
- Better application icon
- About dialog
- Version display
- GitHub link
- Settings screen only if genuinely necessary

Do NOT add unnecessary complexity unless there is a clear benefit.

---

# 41. CURRENT KNOWN LIMITATIONS

Potential limitations include:

## Subtitle codecs

The current robust subtitle workflow explicitly handles:

    SubRip / SRT

Other subtitle codecs may be skipped.

## Preview

Preview uses temporary PNG files.

## Encoding

Video is re-encoded using:

    libx264

Audio is re-encoded using:

    AAC 320k

This is intentional because arbitrary cuts require rebuilding the
timeline cleanly.

## Chapters

Chapters are currently removed.

## Attachments

Attachments are intended to be preserved, especially relevant for MKV.

---

# 42. CRITICAL DEVELOPMENT RULE

Do NOT rewrite working systems merely to make them "cleaner."

Especially avoid casually rewriting:

- Subtitle preparation
- Subtitle retiming
- FFmpeg export command
- Audio concat logic
- Video concat logic

The project has already demonstrated that changing these pieces
without careful testing can break the export.

Prefer:

    small change
        ↓
    test
        ↓
    confirm
        ↓
    next change

---

# 43. CURRENT WORKING BASELINE

The current working baseline is the code supplied by the developer
during this conversation after reverting to the known-working V3
export preparation/subtitle workflow.

The user explicitly confirmed:

    "it's working"

Therefore this version is considered the stable baseline.

Future work should build around this version.

---

# 44. IMMEDIATE NEXT TASK

The immediate next task is NOT to redesign the application.

It is:

    PACKAGE THE WORKING APPLICATION AS A WINDOWS EXE.

First phase:

    1. Create project folder
    2. Put working Python file into it
    3. Put ffmpeg.exe and ffprobe.exe in ./ffmpeg/
    4. Modify FFmpeg discovery
    5. Install PyInstaller
    6. Build ONEDIR
    7. Test ONEDIR
    8. Fix packaging-only issues
    9. Test export again
    10. Build ONEFILE
    11. Test ONEFILE
    12. Add icon
    13. Prepare GitHub repository

---

# 45. FIRST TARGET DIRECTORY

The developer has been instructed to create:

    D:\Family-Safe-Cutter\

with:

    D:\Family-Safe-Cutter\family_safe_cutter.py

and:

    D:\Family-Safe-Cutter\ffmpeg\ffmpeg.exe

    D:\Family-Safe-Cutter\ffmpeg\ffprobe.exe

IMPORTANT:

The user should NOT modify Windows PATH for the packaged
application.

The existing system-wide FFmpeg installation can remain as-is,
but the application should eventually prefer its bundled FFmpeg.

---

# 46. NEXT CHATGPT SESSION INSTRUCTIONS

When continuing this project:

1. Acknowledge that the export engine is currently working.

2. Do NOT replace the export engine unnecessarily.

3. Start with FFmpeg discovery / packaging.

4. Ask the user to confirm their folder structure if necessary.

5. Provide COMPLETE FILES rather than tiny snippets whenever
   practical.

6. The user specifically requested full code because manually
   modifying snippets is challenging.

7. Therefore, when modifying the Python program, provide the
   COMPLETE replacement Python file whenever feasible.

8. Do not make the user manually hunt through hundreds of lines
   for small changes unless absolutely unavoidable.

9. Test packaging in ONEDIR first.

10. Only after ONEDIR works should ONEFILE be attempted.

---

# 47. USER PREFERENCE FOR CODE DELIVERY

The user explicitly said:

    "kindly gimme the full code in chat, it would be really
    challenging for me to change snippets"

Therefore:

> Prefer full copy-paste-ready files.

For example:

    "Replace family_safe_cutter.py with this complete file."

is preferred over:

    "Change lines 123-145."

The same applies to:

- build.bat
- requirements.txt
- .gitignore
- README.md
- spec file

---

# 48. IMPORTANT FFmpeg PACKAGING CONCEPT

There are two different goals:

## Development machine

The developer can have FFmpeg installed globally and in PATH.

## End-user machine

The end user should not need to install FFmpeg manually.

The application should eventually find bundled:

    ffmpeg.exe
    ffprobe.exe

automatically.

The desired UX is:

    Download
        ↓
    Extract / Install
        ↓
    Double-click
        ↓
    Application works

No environment-variable editing.

---

# 49. PYINSTALLER REFERENCE

Official documentation:

    https://pyinstaller.org/en/stable/usage.html

Relevant capabilities:

    --onedir
    --onefile
    --windowed
    --noconsole
    --add-data
    --add-binary
    --icon

PyInstaller documentation also confirms that BAT files can be used
for repeatable build commands.

---

# 50. FINAL LONG-TERM VISION

Family-Safe Cutter should become a small, polished, open-source
Windows desktop application.

Target experience:

    ┌──────────────────────────────────────────────┐
    │ FAMILY-SAFE CUTTER                          │
    │                                              │
    │ INPUT                                        │
    │ [ video.mkv                         ][...]   │
    │                                              │
    │ PREVIEW                                      │
    │ ┌──────────────────────────────────────────┐ │
    │ │                                          │ │
    │ │              VIDEO FRAME                 │ │
    │ │                                          │ │
    │ └──────────────────────────────────────────┘ │
    │                                              │
    │ TIMELINE                                     │
    │ ────●───────────────●──────────────────────  │
    │                                              │
    │ CUTS                                         │
    │ [01] 00:10 → 00:22                          │
    │ [02] 01:05 → 01:14                          │
    │                                              │
    │ OUTPUT                                       │
    │ [ output.mkv                        ][SAVE]  │
    │                                              │
    │ █████████████████░░░░░░  68%                 │
    │ EXPORTING // ETA 00:02:31                    │
    │                                              │
    │                 [CANCEL] [EXPORT]            │
    └──────────────────────────────────────────────┘

The application should feel like a small dedicated utility rather
than a Python script.

---

# 51. CURRENT PROJECT PHILOSOPHY

The most important principles going forward:

    RELIABILITY > FEATURES

    SIMPLE UX > OVER-ENGINEERING

    WORKING EXPORT PIPELINE > REFACTORING FOR STYLE

    FULL COPY-PASTEABLE CODE > FRAGMENTED PATCHES

    TEST EACH CHANGE

    PACKAGE LAST, BUT DESIGN FOR PACKAGING NOW

---

# 52. IMMEDIATE COMMAND CHECKLIST

Once the project folder is prepared, the developer can verify Python:

    python --version

Verify FFmpeg:

    ffmpeg -version

Verify FFprobe:

    ffprobe -version

Install PyInstaller:

    python -m pip install --upgrade pyinstaller

Verify PyInstaller:

    python -m PyInstaller --version

DO NOT build the final EXE until the FFmpeg discovery code has been
made packaging-aware.

---

# 53. SUCCESS CRITERIA FOR FIRST EXE

The first packaged ONEDIR build is considered successful only if:

    [ ] EXE launches by double-click
    [ ] No CMD window appears
    [ ] GUI loads correctly
    [ ] FFmpeg status says ONLINE
    [ ] FFprobe status says ONLINE
    [ ] Video opens
    [ ] Duration is detected
    [ ] Preview works
    [ ] Timeline works
    [ ] Cuts can be added
    [ ] Multiple cuts work
    [ ] Audio remains synchronized
    [ ] Subtitles remain synchronized
    [ ] Export completes
    [ ] Progress bar works
    [ ] ETA works if implemented
    [ ] Cancel works
    [ ] Output file opens correctly
    [ ] Attachments work where applicable
    [ ] Application works WITHOUT FFmpeg being added to PATH

Only after these are confirmed should the project move to ONEFILE
and GitHub release preparation.

---

# 54. HANDOFF SUMMARY

Current state:

    WORKING VIDEO CUTTER
    WORKING AUDIO SYNC
    WORKING SUBTITLE RETIMING
    WORKING FRAME PREVIEW
    WORKING DARK HACKER UI
    WORKING MULTI-CUT TIMELINE
    WORKING EXPORT
    WORKING PROGRESS BAR
    WORKING CANCEL

Current major task:

    PACKAGE INTO WINDOWS EXE

Then:

    GITHUB OPEN SOURCE

Then:

    POLISH / MINOR UX IMPROVEMENTS

The application is already functionally useful.

Do not destabilize it by unnecessarily rewriting the core FFmpeg
export engine.

The next logical engineering step is packaging.
