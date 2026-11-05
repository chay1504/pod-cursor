// Case Mouse: sensor-only helper. Never opens a camera or posts mouse events.
import Foundation
import CoreMotion

func emit(_ value: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: value),
          let line = String(data: data, encoding: .utf8) else { return }
    print(line)
    fflush(stdout)
}

let manager = CMHeadphoneMotionManager()
emit(["status": "Waiting for headphone motion. Keep earbuds in the OPEN case; disable Automatic Ear Detection; select AirPods as audio output."])
manager.startDeviceMotionUpdates(to: .main) { motion, error in
    if let error = error {
        emit(["error": error.localizedDescription])
        return
    }
    guard let m = motion else { return }
    emit(["t": m.timestamp,
          "gyro": [m.rotationRate.x, m.rotationRate.y, m.rotationRate.z],
          "accel": [m.userAcceleration.x, m.userAcceleration.y, m.userAcceleration.z],
          "gravity": [m.gravity.x, m.gravity.y, m.gravity.z],
          "source": String(describing: m.sensorLocation)])
}
RunLoop.main.run()
