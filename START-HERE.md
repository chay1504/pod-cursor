# Case Mouse — real sensor prototype

This is a new project, separate from AirCursor. It has no camera, printed-marker input, face tracking, phone relay or simulated live sensor mode. Its purpose is the requested interaction: hold an earbud case, turn it to move the pointer, and tap it to left-click.

**Status:** the Windows executable is built and the shared code has automated checks, including decoding recorded real sensor packets. GitHub Actions has compiled the Mac helper successfully. No physical case has controlled the pointer during validation. The Windows development machine has no connected MagicAAP sensor interface. Build the helper locally and test permissions and real sensor streaming on a physical Mac; CI compilation is not a hardware demonstration.

## How this route works

The motion sensors we can access belong to compatible earbuds, not a general-purpose public charging-case API. When earbuds remain active inside the OPEN case, their sensors move with it. The app reads their rotation to move the pointer. A brief acceleration impulse followed by a quick decay is interpreted as a finger tap.

Independent developers report successful open-case operation with some AirPods, including AirPods Pro 1. Reports also show that other models can power their sensors off inside the case. Compatibility is specific to the earbuds, firmware, operating system and case state. The lid must remain open for our initial implementation; sustained closed-lid operation is not implemented or verified. An empty case cannot provide input through this route. This is a reconstruction of the interaction, not the tweet creator's recovered code or a verified account of his exact method.

## Windows: what you can open now

Double-click `Start-Windows.cmd`, or `dist/CaseMouse/CaseMouse.exe`. When transferring the executable, copy the WHOLE `CaseMouse` folder, including `_internal`, or extract `CaseMouse-Windows-prototype.zip`. Python does not need to be installed for the packaged Windows app.

The app starts disconnected with pointer control and taps disabled. Click **Start sensor diagnostics**. Diagnostics never move or click the pointer. If a live compatible sensor is accessible, the app reports a sample rate, rotation magnitude and tap signal.

On this PC the read-only driver check returned:

```json
{"platform":"win32","connected_magic_aap_interfaces":0,"mouse_control":false}
```

That means Bluetooth audio pairing alone is insufficient here. Read `WINDOWS-STATUS.md` before attempting anything else. The app does not install drivers or change Windows security settings. A Bluetooth device name does not establish model authenticity or sensor support.

Windows input is experimental. The adapter implements SensorDataWX service IDs 16, 14 or 6 (select one before connecting) and discovery of a RemoteHID `devmotion6` sensor. Unknown layouts are rejected. The documented raw block units were measured on other hardware and are not authenticated for every AirPods firmware. A recognised stream is only the beginning: in-case operation and tap accuracy still need a physical test. Do not try every service blindly and interpret a connection as proof of support.

## Mac: build and test the actual sensor path

You need macOS 14+, compatible motion-capable earbuds, Python 3.10+ with Tkinter (the python.org installer includes it), and Apple command-line developer tools. The native helper is independent Swift source using Apple's public `CMHeadphoneMotionManager` API. No Windows Bluetooth driver is involved on Mac.

1. Copy/extract the source kit onto the Mac. In Terminal, enter `cd `, drag the `case-mouse` folder into Terminal, and press Return.
2. If developer tools are missing, run `xcode-select --install` and complete Apple's installer.
3. Run `bash Setup-Mac.command`. It compiles the sensor helper for the current Mac architecture and ad-hoc signs its app bundle. No developer account is needed for this local build. The Swift source has compiled on a macOS CI runner; the complete local setup and permission flow still require a physical Mac test.
4. Run `bash Start-Mac.command` to open Case Mouse.
5. Connect the earbuds to the Mac. Turn OFF **Automatic Ear Detection** in their settings. Keep both earbuds inside the case with its lid OPEN. Select the earbuds as the Mac's sound output. Another device must not take over their audio connection. Restore Automatic Ear Detection when finished if you normally use it.
6. Click **Start sensor diagnostics** and allow the Motion permission prompt. Permission text explains why motion data is needed. You must see live samples before proceeding. If not, check the lid, model, audio route and Motion permission. Mac audio may be redirected into the earbuds; this initial app does not override the route for you or play keep-alive audio.
7. Before pointer control, allow the actual launcher (usually Terminal/Python) under System Settings > Privacy & Security > Accessibility, then restart it. The sensor helper may appear separately for Motion permission. Rebuilding an ad-hoc signed helper may require permission again.

## Calibrate and use — both operating systems

Do this only after the app shows live samples:

1. Hold the case in the grip you intend to use. Click **1 · Hold still**. There is a one-second preparation delay and then a two-second recording period. Keep it steady.
2. Click **2 · Turn RIGHT**. After the one-second preparation delay, turn slowly right about 15–45 degrees, then hold. Do not turn back until recording finishes.
3. Click **3 · Tilt UP**. After the delay, lift the front of the case about 15–45 degrees, then hold. Do not return during recording. The app rejects tiny movements, interrupted streams or a vertical movement that is too similar to the horizontal movement.
4. Click **Enable pointer control**. Turn the case to point. This maps rotational motion, not sliding the case over a table. Adjust pointer speed or the direction-reversal checkboxes if needed. Primary monitor only.
5. Once movement behaves correctly, check **Enable tap-to-left-click**. Hold the pointer over an empty area first. Settle your hand, then lightly tap the case. The app looks for a sharp impulse following quiet motion and a quick decay, then clicks at the buffered position before the impulse. It cannot guarantee that a movement will never be mistaken for a tap. Tap force thresholds are provisional until tested with your hardware.

The initial app implements movement and optional left-click. No scrolling, drag gesture, dedicated right-click or dedicated double-click sequence is implemented. Keep the physical mouse available for those actions. Diagnostics, calibration and pointer control are separate states so simply connecting does not take control of your computer.

**Pause:** click the pause button; press Control+Alt+Q on Windows or Control+Option+Q on Mac; or move the physical mouse to a corner of the primary screen. The global key check requires the native key-state API to work; the physical mouse corner stop is also available. Motion gaps longer than 150 ms pause control and require explicit resuming. Recognised source changes clear calibration. Windows ear-state changes also force recalibration; some firmware may switch sources without exposing an identifiable event.

## Can ordinary earbuds do this?

Only if they have suitable rotation/acceleration sensors, expose a usable live stream to software, and keep that stream active while sitting in the case. Bluetooth, ANC, touch controls or “spatial audio” in the product description do not establish those requirements.

This build contains an Apple CoreMotion helper and an experimental Apple AAP adapter. It has NO generic driver for boAt, Noise, realme, OnePlus, Samsung or other brands. Their exact models would need separate protocol research. Software cannot add missing sensor hardware or bypass a case that powers off the sensors through an undocumented, unimplemented command. We cannot promise compatibility with unnamed ordinary earbuds.

## Other electronics worth investigating with the same sensor idea

These are future input-adapter candidates, not replacements built into this delivery:

| Gadget you may already own | Why it is a useful candidate | Remaining work |
| --- | --- | --- |
| PlayStation DualSense / DualShock 4 | Built-in gyro, accelerometer and real buttons | Read its controller reports; map them to this engine |
| Nintendo Joy-Con | Built-in gyro and accelerometer; compact handheld shape | Bluetooth report decoding and calibration |
| Old smartphone with a gyro | Operating-system APIs expose rotation and acceleration | A companion app and authenticated connection to the computer |
| Smartwatch | Possible wrist-motion input | Exact model, sensor API access and companion app |
| A gyro-equipped air remote | Already designed for pointing | Verify its protocol; some already act as a mouse without this app |
| Small IMU plus Bluetooth-capable microcontroller | Can deliberately make a sensor-equipped case/controller | Additional hardware, battery, enclosure and firmware; not an unmodified earbud case |

Ordinary remotes without motion sensors, power banks and speakers are not automatically motion controllers merely because they are electronic. First identify the device's actual sensors and readable protocol. If choosing among gadgets already at home, a gyro-equipped game controller has a much clearer path than generic earbuds.

## Files and verification

- `app.py`: user interface, connection management, calibration and mouse dispatch.
- `engine.py`: calibration, pointer mapping and time-based tap detector.
- `protocol.py`: strict AAP packet and motion-block decoding.
- `windows_aap.py`: access to an already-installed MagicAAP interface.
- `mouse_output.py`: native Windows/macOS pointer output.
- `native/MotionBridge.swift`: Mac real-sensor helper.
- `tests/`: automated checks, including a small attributed real-packet fixture.
- `VALIDATION.md`: exact checks, blockers and unverified items.
- `SOURCES.md`: implementation references, attribution and hardware claims.

Run tests from source using `python -m unittest discover -s tests -v`. Normal operation uses the standard Python library only. The app has no camera, analytics, network listener, network client or automatic boot/security configuration changes. Source research files are not shipped in the kits. See README.md for Git clone/pull instructions and GitHub Actions for current build results.
