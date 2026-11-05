# Validation — 5 November 2026

## Completed

- Independent sensor-based project; no camera/marker input dependency.
- Python-source GUI smoke check opened and closed successfully on Windows without connecting sensors or posting mouse events.
- **31 automated checks passed** with `python -m unittest discover -s tests -v`. These cover pointer direction/inversion and limits; invalid, stale and changed-source data; signed axis calibration and rejected calibration; impulse-versus-wave tap logic at 25/50 Hz; strict packet parsing; truncated/malformed/random packets; RemoteHID discovery; and application-level zero-event diagnostics, required calibration, emergency pause, stale queue rejection and opt-in taps.
- Twelve motion-containing packets from a real public MousePods recording decode successfully, with checked timestamp and gravity values. These are from someone else's captured hardware stream, not a local case experiment. Attribution is embedded in the fixture and SOURCES.md.
- All application Python modules passed compilation checks.
- Mac permission plist parsed successfully with minimum version 14.0.
- Both Mac shell scripts passed Bash syntax checks using the installed Git Bash.
- GitHub Actions successfully compiled the Swift helper on a macOS runner and passed the core/protocol tests. The Windows runner passed the full 31-test suite. [Verified run](https://github.com/chay1504/pod-cursor/actions/runs/42029017422).
- Windows read-only SetupAPI enumeration ran successfully and returned **0 connected MagicAAP interfaces** on the development machine. No sensor commands were sent in this check.
- Windows PyInstaller build produced `dist/CaseMouse/CaseMouse.exe` with its `_internal` dependencies. No third-party Python runtime packages are required by the source application beyond standard-library Tkinter.

## Blocked or unverified

- **No physical case has controlled the cursor in this session.** Hardware compatibility, real tap accuracy, noise thresholds, long-run stability and closed-lid operation are not verified.
- No supported Windows sensor feed was available. The app-side AAP transport/commands are implemented but real driver I/O and in-case streaming need an exact device plus a working driver. The decoder's real-capture check does not validate Windows transport.
- Automatic approval review rejected the packaged executable launch smoke check with only `blocked by policy`. It was not retried through another launcher. The Python-source GUI check passed; packaged binary launch remains unverified.
- Mac native helper is provided as source and compiled successfully in GitHub Actions. Runtime permissions, local app-bundle setup, real sensor streaming and mouse operation still need testing on a physical Mac; compilation does not establish those behaviours.
- Case support for unnamed ordinary earbuds is not implemented or promised. Both sensor hardware and readable live protocol are required.
- Additional gadgets in the guide are candidates for future adapters, not supported inputs of this build.

No driver installation, boot/signing changes, certificate installation, policy removal or security exclusion was performed. No camera was opened. See GitHub Actions for the current source-check and native Mac compile results; those checks do not prove hardware compatibility.
