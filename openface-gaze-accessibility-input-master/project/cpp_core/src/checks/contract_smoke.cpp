#include "gaze_core/contracts.h"

#include <iostream>

int main() {
  gaze_core::FrameFeatures frame;
  frame.frame_id = 1;
  frame.timestamp_ms = 1000;
  frame.raw_gaze_x = -0.1;
  frame.raw_gaze_y = 0.2;

  gaze_core::GazePoint point;
  point.timestamp_ms = frame.timestamp_ms;
  point.normalized_x = 0.5;
  point.normalized_y = 0.5;
  point.target_id = "key:wo";

  gaze_core::TargetEvent event;
  event.timestamp_ms = 1650;
  event.event_type = gaze_core::TargetEventType::kKeyInput;
  event.target_id = point.target_id;
  event.text = "wo";
  event.dwell_started_ms = frame.timestamp_ms;
  event.dwell_elapsed_ms = 650;

  std::cout << "contract-smoke event_type=" << gaze_core::ToString(event.event_type)
            << " target=" << event.target_id << " text=" << event.text << "\n";
  return 0;
}
