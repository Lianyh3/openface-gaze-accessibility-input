#pragma once

#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "gaze_core/contracts.h"

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
  LinearNormalizer(double x_min, double x_max, double y_min, double y_max, bool clamp);

  std::pair<double, double> Normalize(double x, double y) const;

 private:
  double x_min_;
  double x_max_;
  double y_min_;
  double y_max_;
  bool clamp_;
};

class KeyboardHitTester {
 public:
  explicit KeyboardHitTester(std::vector<TargetRegion> regions);

  std::string HitTest(double x, double y) const;

  const std::vector<TargetRegion>& regions() const { return regions_; }

  static KeyboardHitTester BuildDefault(const LayoutPreset& preset = LayoutPreset{});

 private:
  std::vector<TargetRegion> regions_;
};

class DwellDetectorCore {
 public:
  explicit DwellDetectorCore(std::int64_t dwell_ms);

  void Reset();

  std::optional<TargetEvent> Update(std::int64_t timestamp_ms, const std::string& target_id);

 private:
  std::int64_t dwell_ms_;
  std::optional<std::string> active_target_;
  std::optional<std::int64_t> target_start_ms_;
  bool emitted_for_active_ = false;
};

class RuntimeM1 {
 public:
  RuntimeM1(LinearNormalizer normalizer, KeyboardHitTester hit_tester, DwellDetectorCore dwell_detector);

  std::optional<TargetEvent> UpdateFrame(const FrameFeatures& frame);

  const std::optional<GazePoint>& LastGazePoint() const { return last_gaze_point_; }

 private:
  LinearNormalizer normalizer_;
  KeyboardHitTester hit_tester_;
  DwellDetectorCore dwell_detector_;
  std::optional<GazePoint> last_gaze_point_;
};

}  // namespace gaze_core
