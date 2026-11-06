# AirPointer — Windows adaptation

Use [Andy Gao's original AirPointer](https://github.com/musubipapi/airpointer) for the Mac application. The default branch of this repository points to that original.

This `windows-port` branch contains an experimental Windows adaptation of the original closed-case protocol and tap detector. It executes the original orientation JavaScript unchanged. It is not an official release from the original author.

## Run on Windows

Install Python 3.12 and Node.js 22+ first. A compatible, already installed MagicAAP driver and supported AirPods Pro hardware are also needed for real sensor access.

```powershell
git clone --branch windows-port https://github.com/chay1504/pod-cursor.git
cd pod-cursor
py -3.12 Windows/app.py --diagnose
py -3.12 Windows/app.py
```

Read [Windows setup, real device effects and limitations](Windows/README.md) before connecting. No driver or Windows security changes are made automatically. This computer had zero usable MagicAAP interfaces: live Windows case control has not been validated.

24 offline tests pass, including 15/15 of the author's recorded held-case taps and no clicks in recorded handling/pointing. Source and packaged Windows GUI launch/exit checks pass. Offline checks do not establish hardware compatibility. The Mac reconnect/audio-management services and tap learner are not implemented in this Windows port.

For tests: `py -3.12 -m unittest discover -s Windows/tests -v`.

Original code and fixtures: copyright 2026 Andy Gao, [MIT License](LICENSE). The original Mac assets are not included in this branch.