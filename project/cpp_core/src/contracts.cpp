#include "gaze_core/contracts.h"

namespace gaze_core {

const char* ToString(TargetEventType value) {
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
