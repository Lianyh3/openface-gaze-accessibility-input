#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace gaze_core {

enum class TargetEventType : std::uint8_t {
  kNone = 0,
  kKeyInput = 1,
  kCandidatePick = 2,
  kBackspace = 3,
  kCommitDirect = 4,
  kClear = 5,
  kCandidateRefresh = 6,
};

// Frame-level features parsed from OpenFace (or fallback source).
struct FrameFeatures {
  std::int64_t frame_id = 0;
  std::int64_t timestamp_ms = 0;

  std::optional<double> raw_gaze_x;
  std::optional<double> raw_gaze_y;
  std::optional<double> confidence;
  std::optional<double> pose_rx;
  std::optional<double> pose_ry;
  std::optional<double> pose_rz;
};

// Normalized gaze point and hit-test result.
struct GazePoint {
  std::int64_t timestamp_ms = 0;
  double normalized_x = 0.0;
  double normalized_y = 0.0;
  std::string target_id;
};

// Output event emitted by dwell/hit-test runtime core.
struct TargetEvent {
  std::int64_t timestamp_ms = 0;
  TargetEventType event_type = TargetEventType::kNone;
  std::string target_id;

  // key_input only
  std::string text;
  // candidate_pick only, 1-based index
  std::int32_t candidate_index = 0;

  // dwell metadata
  std::int64_t dwell_started_ms = 0;
  std::int64_t dwell_elapsed_ms = 0;
};

inline const char* ToString(TargetEventType value) {
  switch (value) {
    case TargetEventType::kNone:
      return "none";
    case TargetEventType::kKeyInput:
      return "key_input";
    case TargetEventType::kCandidatePick:
      return "candidate_pick";
    case TargetEventType::kBackspace:
      return "backspace";
    case TargetEventType::kCommitDirect:
      return "commit_direct";
    case TargetEventType::kClear:
      return "clear";
    case TargetEventType::kCandidateRefresh:
      return "candidate_refresh";
  }
  return "none";
}

}  // namespace gaze_core
