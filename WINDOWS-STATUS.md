# Windows sensor access: unresolved on this PC

Read-only enumeration on 5 November 2026 found **zero connected MagicAAP sensor interfaces**. The Case Mouse executable can open diagnostics, but no actual AirPods/case motion stream has been established here.

The available independent Windows route uses the MagicAAP kernel driver to reach Apple's Bluetooth Classic L2CAP channel. Regular Bluetooth audio and BLE battery advertisements are not that channel. Case Mouse implements the application side of that driver interface; it does not supply a kernel driver.

The driver's official site currently says its official build is unsigned and requires Test Mode. Its community build has additional Windows driver-policy compatibility restrictions. Those changes are consequential and are not silently included in this prototype. No driver installation, Secure Boot change, test-signing change, Defender exclusion, certificate installation or driver-policy removal was performed. Do not assume downloading this app makes Windows sensor access work.

Official status and instructions: https://magicpods.app/magicaap/ . This is a dependency status reference, not a recommendation to change security settings on your everyday PC.

Even with a working driver, this app's Windows stream decoding and in-case behaviour need testing with the exact model/firmware. The adapter handles documented formats and rejects others; it cannot guarantee every AirPods model. No conventional earbuds are supported by this Apple-specific adapter.

For a physical first test without this Windows driver issue, the provided Mac helper uses Apple's public motion API. It still requires a compatible model and an open case; its compilation and live operation remain unverified in this Windows session.
