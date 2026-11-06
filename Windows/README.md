# AirPointer Windows port — experimental

This is a **local Windows adaptation of the original closed-case AirPointer**, based on upstream commit `a73cc798e71a2e4c568f5a2ec8a351a58cd8e311`. The original Mac app and assets are preserved. This port uses the original `Sources/AirPointer/Session/Orientation.js` unchanged, translates the raw service-11/12 sensor protocol and closed-case diagnostic lifecycle, and translates the original tap detector. Andy Gao's MIT license in the repository root applies to the original code; retain it with this distribution.

Shareable source: https://github.com/chay1504/pod-cursor/tree/windows-port . The repository's `main` branch remains only a pointer to the original Mac project. The Windows branch does not republish the original Mac assets.

```powershell
git clone --branch windows-port https://github.com/chay1504/pod-cursor.git
cd pod-cursor
```

## Actual status

- Windows source and packaged GUI open and close successfully; **24 automated tests pass**.
- Against the author's recorded fixture, the translated detector finds **15 of 15 held-case taps**, with zero clicks in the recorded handling/pointing segments. Lid-closing motion can look like a tap, so clicks are disabled until the user calibrates and enables them.
- The original orientation math passes four additional offline assertions, both from source and from the packaged resources.
- The 24 tests also passed on a fresh Windows GitHub Actions runner: https://github.com/chay1504/pod-cursor/actions/runs/42174082637 . CI is an offline check, not a physical sensor test.
- The Windows computer used for development reports **zero connected MagicAAP interfaces**. **A live Windows AirPods/case connection has not been established or verified.** Passing offline tests is not evidence that this port works with a physical case.
- This is not an official Windows release from the original author. The original's tested combination is AirPods Pro 3, Apple silicon and macOS 26; Pro 2 is recognized but untested even there. Generic earbuds are not supported by this protocol.

## Requirements

- Windows 10/11, 64-bit, with Bluetooth Classic.
- Compatible AirPods Pro, already paired.
- An **already installed and usable MagicAAP driver** exposing the sensor channel. Normal Bluetooth audio does not provide that channel. The port does not install a driver, remove driver policies, import certificates, change Secure Boot or enable Test Mode.
- Node.js 22+ on PATH, to execute the original orientation math. The development machine uses Node 24.
- For source execution: Python 3.12 with Tkinter. The packaged executable includes Python/Tkinter, so those are not required for the packaged version.

The driver maintainer currently lists an unsigned official driver requiring Test Mode and restrictions on the community-signed version. Read https://magicpods.app/magicaap/ . This is an unresolved dependency, not a recommendation to weaken security on an everyday computer. No such changes were made during development.

## Important device effects

As in the original, closing a session can consume stored case diagnostic records. Some AACP connection settings are write-only and remain as set; their previous values cannot be reconstructed. Do not use during calls. The Windows UI explicitly asks the user to acknowledge these effects before connecting.

Unlike the Mac original, this Windows port does **not** automatically reconnect the normal Bluetooth link, guard/restore audio endpoints, play silent keep-alive audio or read the lid's manufacturer broadcast. Those integrations remain unimplemented. You reconnect manually, select speakers and the laptop microphone yourself, and explicitly confirm lid closure. Live stability and these manual setup requirements need hardware testing; this is not feature parity with the Mac app.

## Start safely

For the packaged version, extract the whole ZIP and run `AirPointer-Windows.exe`; keep its `_internal` folder beside it. Node.js must still be installed.

For source execution, from the repository root:

```powershell
py -3.12 Windows/app.py --diagnose
py -3.12 Windows/app.py
```

Or double-click `Windows/Start-Windows.cmd`.

1. Click **Scan driver (read only)**. This does not send commands to earbuds or move the mouse. With zero interfaces, stop here; the app cannot connect to the sensors yet.
2. If exactly one usable interface is present, close competing AAP clients. Select laptop speakers and laptop microphone. Close apps that use the AirPods microphone. Disconnect the paired iPhone temporarily if it takes the AirPods connection.
3. Reconnect AirPods in Windows Bluetooth settings, then immediately click **Connect with lid OPEN**. The original protocol needs a fresh channel. A scan alone does not validate hardware/firmware compatibility.
4. Wait for both raw sensors and the AirPods Pro identity to verify. Only when the UI says so, close the lid and click **Confirm lid CLOSED**. The app then performs the original identity-gated diagnostic setup/renewal.
5. Set the case on a firm surface until its sensor offset is ready. Hold it upright and aim at the center; save **CENTER**, then aim at the right edge and save **RIGHT**, then aim at the top edge and save **TOP**. This uses the original three-point orientation mapping.
6. Click **Enable pointer**. Tap-clicks start OFF. After aiming works, opt into front-tap left-clicks over an empty area. The default direction comes from the author's fixture; a Windows equivalent of the Mac **Teach Tap** learner is not implemented yet.
7. Pause with **Ctrl+Alt+Q**, the pause button, or a physical mouse at a main-screen corner. Motion older than 150 ms pauses control; re-enable manually. **Disconnect** stops the raw sensors first and releases the specific diagnostic asset, if one was accepted. Cleanup problems are reported rather than hidden. A hung kernel driver can still prevent normal cleanup; this has not been tested with hardware.

The first version controls the primary monitor. It does not include scrolling, dragging, the native notch UI, tap teaching, saved aiming calibration or automatic audio/connection management. Sessions have a 30-minute limit matching the upstream observed limit.

## Tests and build

From the repository root:

```powershell
py -3.12 -m unittest discover -s Windows/tests -v
node Windows/orientation.mjs --self-test
```

To build with PyInstaller 6.17.0, use `Windows/Build-Windows.cmd`. That script expects PyInstaller already installed; it does not install anything automatically. The Windows transport was adapted from the earlier app's Win32 device-interface transport only; the earlier generic motion engine, webcam prototype and guides are not dependencies.

Source layout: `protocol.py` contains the identity-gated UARP/MTIC state machine and strict raw-report reader; `transport.py` contains Win32 access to the existing driver; `runtime.py` manages heartbeat, sensor start/stop and cleanup; `orientation.mjs` executes upstream math; `taps.py` translates upstream tap detection; `app.py` is the Windows UI and explicit control state; `mouse.py` posts native pointer events.

Only sensor sequence state is stored under `%LOCALAPPDATA%/AirPointerWindows/`. It is saved before each sensor-setting command so sequences carry on across sessions. The port has no camera input, analytics, network listener or telemetry upload. Source/package offline checks never connect to the device.
