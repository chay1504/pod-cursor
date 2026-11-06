# Pod Cursor — original project

Use **[Andy Gao’s original AirPointer](https://github.com/musubipapi/airpointer)**.

The earlier independent prototype has been removed from the current branch. It remains in Git history; no history was rewritten.

## Mac setup

```sh
git clone https://github.com/musubipapi/airpointer.git
cd airpointer
zsh ./build.sh
open AirPointer.app
```

Read the [original requirements and setup guide](https://github.com/musubipapi/airpointer#readme) first. The author reports testing AirPods Pro 3 on macOS 26 with Apple silicon; Pro 2 is recognized but untested. The build requires Xcode.

The original uses a diagnostic session to keep the closed case awake. Its README warns that ending a session consumes stored case diagnostics and some connection settings remain changed. Follow its Accessibility, connect, calibration and tap setup.

This repository is a pointer to the original, not a copy or an official Windows release.
