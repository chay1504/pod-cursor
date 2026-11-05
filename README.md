# Pod Cursor

Experimental **earbud-case mouse**: turn a compatible open charging case to move the pointer and lightly tap it to left-click. Reads real earbud motion sensors; no webcam or markers. The application window currently calls itself **Case Mouse**.

**Status:** calibration, pointer mapping, tap detection, a Mac sensor helper and an experimental Windows adapter are implemented. **Physical case control remains unverified.** Exact model/firmware support and in-case sensor availability need a hardware test. Ordinary earbuds are not universally supported. Closed-lid operation, scrolling, right-click and dragging gestures are not implemented.

## Mac quick start

Requires **macOS 14+, Python 3.10+ with Tkinter, Apple command-line developer tools**, and compatible motion-capable earbuds. The [python.org Mac installer](https://www.python.org/downloads/macos/) includes Tkinter.

```bash
git clone https://github.com/chay1504/pod-cursor.git
cd pod-cursor

# If developer tools are missing, run this and finish Apple's installer first:
xcode-select --install

bash Setup-Mac.command
bash Start-Mac.command
```

For an existing checkout, run `git pull --ff-only`, then repeat setup to rebuild the helper after source changes.

### First hardware test

1. Connect earbuds to the Mac. Disable **Automatic Ear Detection**, select them as sound output, and leave both earbuds in the **OPEN case**. Restore ear detection when finished if you normally use it.
2. Click **Start sensor diagnostics** and allow Motion access. Diagnostics do not move or click the pointer. Confirm fresh samples arrive before proceeding.
3. Follow **Hold still → Turn RIGHT → Tilt UP**. Each step waits one second, then records for two seconds. Turn 15–45 degrees in the requested direction, then hold; do not return during recording.
4. Grant the launcher (usually Terminal/Python) **Accessibility** permission in System Settings → Privacy & Security. Restart if needed. The helper may have a separate Motion permission entry; rebuilding its ad-hoc signature may require permission again.
5. Enable pointer control with taps disabled. After movement works, opt into tap-to-left-click and test on an empty area.
6. Pause with **Control+Option+Q**, the pause button, or the physical mouse at a main-screen corner. A sensor stall pauses control and requires manual resuming.

Keep a normal mouse available. This prototype controls the primary monitor. See the [complete guide](START-HERE.md) for calibration, permission troubleshooting and limitations.

## Development

```bash
# No hardware or mouse output required
python3 -m unittest discover -s tests -p 'test_engine.py' -v
python3 -m unittest discover -s tests -p 'test_protocol.py' -v

# Full suite; requires Tkinter and a graphical desktop, with mouse output mocked
python3 -m unittest discover -s tests -v
```

GitHub Actions checks core/protocol logic on Mac and Windows, UI safety on Windows, and compiles the Swift helper on a Mac runner. CI does not prove hardware compatibility or grant runtime permissions.

| File | Role |
| --- | --- |
| `app.py` | UI, sensor connection, calibration and pointer dispatch |
| `engine.py` | Hardware-independent calibration, mapping and tap detection |
| `native/MotionBridge.swift` | Actual Mac sensor readings as JSON samples |
| `mouse_output.py` | Native Windows/macOS pointer output |
| `windows_aap.py` | Experimental access to an already-installed MagicAAP driver |
| `protocol.py` | Strict AAP/RemoteHID parsing |
| `tests/` | Logic, protocol and UI checks; attributed recorded-packet fixture |

Source operation uses Python's standard library, including Tkinter. Setup compiles the Mac helper locally. Research downloads, cached files and locally built executables are excluded from Git.

## Windows

Run `py -3.12 app.py` or `Start-Windows.cmd`. The sensor connection requires an already-installed compatible MagicAAP driver. Ordinary Bluetooth audio does not expose this channel. This app does not install drivers or change boot/security settings. See [Windows status](WINDOWS-STATUS.md).

## Evidence and attribution

- [Validation and remaining hardware checks](VALIDATION.md)
- [Sources and attribution](SOURCES.md)

The recorded fixture is credited to **MousePods by Matteo Gaudioso (starman-tech)** under CC BY 4.0; its metadata and sources document the origin. This project is independent of Apple and of the tweet creator's implementation.
