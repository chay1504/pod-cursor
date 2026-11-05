#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this script on a Mac.'
  exit 1
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo 'Install Apple command line tools with: xcode-select --install'
  exit 1
fi
python3 -c 'import sys, tkinter; assert sys.version_info >= (3,10)' || { echo 'Install Python 3.10 or later from python.org with Tkinter included.'; exit 1; }
mkdir -p native/CaseMotion.app/Contents/MacOS
cp native/Info.plist native/CaseMotion.app/Contents/Info.plist
xcrun swiftc native/MotionBridge.swift -O -target "$(uname -m)-apple-macosx14.0" \
  -framework Foundation -framework CoreMotion -o native/CaseMotion.app/Contents/MacOS/CaseMotion
codesign --force --sign - native/CaseMotion.app
echo 'Mac helper built. Next: bash Start-Mac.command'
