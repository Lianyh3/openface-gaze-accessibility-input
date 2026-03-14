#pragma once

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "gaze_core/contracts.hpp"

namespace gaze_core {

struct TargetRegion {
  std::string target_id;
  double x0 = 0.0;
  double y0 = 0.0;
  double x1 = 0.0;
  double y1 = 0.0;

  bool Contains(double x, double y) const { return x0 <= x && x < x1 && y0 <= y && y < y1; }
};

struct LayoutPreset {
  std::int32_t candidate_slots = 8;
};

class LinearNormalizer {
 public:
  LinearNormalizer(double x_min, double x_max, double y_min, double y_max, bool clamp)
      : x_min_(x_min), x_max_(x_max), y_min_(y_min), y_max_(y_max), clamp_(clamp) {
    if (x_min_ == x_max_) {
      throw std::invalid_argument("x_max must be different from x_min");
    }
    if (y_min_ == y_max_) {
      throw std::invalid_argument("y_max must be different from y_min");
    }
  }

  std::pair<double, double> Normalize(double x, double y) const {
    double nx = (x - x_min_) / (x_max_ - x_min_);
    double ny = (y - y_min_) / (y_max_ - y_min_);
    if (clamp_) {
      nx = std::min(1.0, std::max(0.0, nx));
      ny = std::min(1.0, std::max(0.0, ny));
    }
    return {nx, ny};
  }

 private:
  double x_min_;
  double x_max_;
  double y_min_;
  double y_max_;
  bool clamp_;
};

class KeyboardHitTester {
 public:
  explicit KeyboardHitTester(std::vector<TargetRegion> regions) : regions_(std::move(regions)) {
    if (regions_.empty()) {
      throw std::invalid_argument("regions must not be empty");
    }
  }

  std::string HitTest(double x, double y) const {
    if (x < 0.0 || x > 1.0 || y < 0.0 || y > 1.0) {
      return "";
    }
    for (const auto& region : regions_) {
      if (region.Contains(x, y)) {
        return region.target_id;
      }
    }
    return "";
  }

  const std::vector<TargetRegion>& regions() const { return regions_; }

  static KeyboardHitTester BuildDefault(const LayoutPreset& preset = LayoutPreset{});

 private:
  std::vector<TargetRegion> regions_;
};

class DwellDetectorCore {
 public:
  explicit DwellDetectorCore(std::int64_t dwell_ms) : dwell_ms_(dwell_ms) {
    if (dwell_ms_ <= 0) {
      throw std::invalid_argument("dwell_ms must be positive");
    }
  }

  void Reset() {
    active_target_.reset();
    target_start_ms_.reset();
    emitted_for_active_ = false;
  }

  std::optional<TargetEvent> Update(std::int64_t timestamp_ms, const std::string& target_id);

 private:
  std::int64_t dwell_ms_;
  std::optional<std::string> active_target_;
  std::optional<std::int64_t> target_start_ms_;
  bool emitted_for_active_ = false;
};

class RuntimeM1 {
 public:
  RuntimeM1(LinearNormalizer normalizer, KeyboardHitTester hit_tester, DwellDetectorCore dwell_detector)
      : normalizer_(std::move(normalizer)),
        hit_tester_(std::move(hit_tester)),
        dwell_detector_(std::move(dwell_detector)),
        last_gaze_point_(std::nullopt) {}

  std::optional<TargetEvent> UpdateFrame(const FrameFeatures& frame) {
    if (!frame.raw_gaze_x.has_value() || !frame.raw_gaze_y.has_value()) {
      return std::nullopt;
    }
    const auto [nx, ny] = normalizer_.Normalize(*frame.raw_gaze_x, *frame.raw_gaze_y);
    const std::string target = hit_tester_.HitTest(nx, ny);
    GazePoint point;
    point.timestamp_ms = frame.timestamp_ms;
    point.normalized_x = nx;
    point.normalized_y = ny;
    point.target_id = target;
    last_gaze_point_ = point;
    return dwell_detector_.Update(frame.timestamp_ms, target);
  }

  const std::optional<GazePoint>& LastGazePoint() const { return last_gaze_point_; }

 private:
  LinearNormalizer normalizer_;
  KeyboardHitTester hit_tester_;
  DwellDetectorCore dwell_detector_;
  std::optional<GazePoint> last_gaze_point_;
};

namespace detail_m1 {

inline bool StartsWith(const std::string& s, const std::string& prefix) {
  return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

inline std::string Trim(const std::string& s) {
  std::size_t left = 0;
  while (left < s.size() && std::isspace(static_cast<unsigned char>(s[left])) != 0) {
    ++left;
  }
  std::size_t right = s.size();
  while (right > left && std::isspace(static_cast<unsigned char>(s[right - 1])) != 0) {
    --right;
  }
  return s.substr(left, right - left);
}

inline bool IsDigits(const std::string& s) {
  if (s.empty()) {
    return false;
  }
  for (char c : s) {
    if (!std::isdigit(static_cast<unsigned char>(c))) {
      return false;
    }
  }
  return true;
}

inline void AddGridRegions(std::vector<TargetRegion>* out,
                           const std::vector<std::string>& target_ids,
                           double x0,
                           double x1,
                           double y0,
                           double y1,
                           std::int32_t columns) {
  if (columns <= 0) {
    throw std::invalid_argument("columns must be positive");
  }
  if (target_ids.empty()) {
    return;
  }
  const std::int32_t rows = static_cast<std::int32_t>((target_ids.size() + columns - 1) / columns);
  const double cell_w = (x1 - x0) / static_cast<double>(columns);
  const double cell_h = (y1 - y0) / static_cast<double>(rows);

  for (std::size_t idx = 0; idx < target_ids.size(); ++idx) {
    const std::int32_t row = static_cast<std::int32_t>(idx / columns);
    const std::int32_t col = static_cast<std::int32_t>(idx % columns);
    const double rx0 = x0 + static_cast<double>(col) * cell_w;
    const double ry0 = y0 + static_cast<double>(row) * cell_h;
    TargetRegion region;
    region.target_id = target_ids[idx];
    region.x0 = rx0;
    region.y0 = ry0;
    region.x1 = rx0 + cell_w;
    region.y1 = ry0 + cell_h;
    out->push_back(region);
  }
}

inline std::optional<TargetEvent> ParseTargetToEvent(std::int64_t timestamp_ms,
                                                     const std::string& target_id,
                                                     std::int64_t dwell_started_ms,
                                                     std::int64_t dwell_elapsed_ms) {
  const std::string token = Trim(target_id);
  if (token.empty()) {
    return std::nullopt;
  }

  TargetEvent event;
  event.timestamp_ms = timestamp_ms;
  event.target_id = token;
  event.dwell_started_ms = dwell_started_ms;
  event.dwell_elapsed_ms = dwell_elapsed_ms;

  if (StartsWith(token, "key:")) {
    const std::string text = token.substr(4);
    if (text.empty()) {
      return std::nullopt;
    }
    event.event_type = TargetEventType::kKeyInput;
    event.text = text;
    return event;
  }

  if (StartsWith(token, "cand:")) {
    const std::string raw = Trim(token.substr(5));
    if (!IsDigits(raw)) {
      return std::nullopt;
    }
    event.event_type = TargetEventType::kCandidatePick;
    event.candidate_index = std::stoi(raw);
    return event;
  }

  if (StartsWith(token, "action:")) {
    std::string action = token.substr(7);
    std::transform(action.begin(), action.end(), action.begin(), [](unsigned char c) { return std::tolower(c); });
    if (action == "back") {
      event.event_type = TargetEventType::kBackspace;
      return event;
    }
    if (action == "commit") {
      event.event_type = TargetEventType::kCommitDirect;
      return event;
    }
    if (action == "clear") {
      event.event_type = TargetEventType::kClear;
      return event;
    }
    if (action == "refresh") {
      event.event_type = TargetEventType::kCandidateRefresh;
      return event;
    }
  }

  return std::nullopt;
}

}  // namespace detail_m1

inline KeyboardHitTester KeyboardHitTester::BuildDefault(const LayoutPreset& preset) {
  if (preset.candidate_slots <= 0) {
    throw std::invalid_argument("candidate_slots must be positive");
  }
  if (preset.candidate_slots > 8) {
    throw std::invalid_argument("default layout supports at most 8 candidate slots");
  }

  std::vector<TargetRegion> regions;
  std::vector<std::string> candidate_ids;
  candidate_ids.reserve(static_cast<std::size_t>(preset.candidate_slots));
  for (std::int32_t i = 1; i <= preset.candidate_slots; ++i) {
    candidate_ids.push_back("cand:" + std::to_string(i));
  }
  detail_m1::AddGridRegions(&regions, candidate_ids, 0.0, 1.0, 0.0, 0.24, 4);

  std::vector<std::string> key_ids = {
      "key:我", "key:今天", "key:想",   "key:去",   "key:你",   "key:现在",
      "key:需要", "key:请",  "key:帮", "key:打开", "key:发送", "key:消息",
  };
  detail_m1::AddGridRegions(&regions, key_ids, 0.0, 1.0, 0.24, 0.82, 4);

  std::vector<std::string> action_ids = {
      "action:back",
      "action:clear",
      "action:refresh",
      "action:commit",
  };
  detail_m1::AddGridRegions(&regions, action_ids, 0.0, 1.0, 0.82, 1.0, 4);

  return KeyboardHitTester(std::move(regions));
}

inline std::optional<TargetEvent> DwellDetectorCore::Update(std::int64_t timestamp_ms, const std::string& target_id) {
  const std::string token = detail_m1::Trim(target_id);
  if (token.empty()) {
    Reset();
    return std::nullopt;
  }

  if (!active_target_.has_value() || token != *active_target_) {
    active_target_ = token;
    target_start_ms_ = timestamp_ms;
    emitted_for_active_ = false;
    return std::nullopt;
  }

  if (emitted_for_active_) {
    return std::nullopt;
  }
  if (!target_start_ms_.has_value()) {
    return std::nullopt;
  }

  const std::int64_t elapsed = timestamp_ms - *target_start_ms_;
  if (elapsed < dwell_ms_) {
    return std::nullopt;
  }

  emitted_for_active_ = true;
  return detail_m1::ParseTargetToEvent(timestamp_ms, token, *target_start_ms_, elapsed);
}

}  // namespace gaze_core
