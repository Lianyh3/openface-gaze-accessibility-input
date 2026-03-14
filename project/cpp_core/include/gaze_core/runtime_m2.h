#pragma once

#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

namespace gaze_core {

struct CalibrationPoint {
  double raw_x = 0.0;
  double raw_y = 0.0;
  double screen_x = 0.0;
  double screen_y = 0.0;
};

struct CalibrationFitMetrics {
  std::int32_t point_count = 0;
  double mae_x = 0.0;
  double mae_y = 0.0;
  double rmse = 0.0;
  double max_abs_error = 0.0;
};

class AffineCalibration {
 public:
  AffineCalibration(double ax, double bx, double cx, double ay, double by, double cy, bool clamp = true);

  std::pair<double, double> Normalize(double raw_x, double raw_y) const;

  double ax() const { return ax_; }
  double bx() const { return bx_; }
  double cx() const { return cx_; }
  double ay() const { return ay_; }
  double by() const { return by_; }
  double cy() const { return cy_; }
  bool clamp() const { return clamp_; }

 private:
  double ax_;
  double bx_;
  double cx_;
  double ay_;
  double by_;
  double cy_;
  bool clamp_;
};

struct AffineCalibrationFitResult {
  AffineCalibration model;
  CalibrationFitMetrics metrics;
};

AffineCalibrationFitResult FitAffineCalibration(const std::vector<CalibrationPoint>& points, bool clamp = true);

class EmaSmoother2D {
 public:
  explicit EmaSmoother2D(double alpha = 0.4);

  void Reset();

  std::pair<double, double> Update(std::int64_t timestamp_ms, double x, double y);

 private:
  double alpha_;
  std::optional<double> x_;
  std::optional<double> y_;
};

class OneEuroSmoother2D {
 public:
  OneEuroSmoother2D(double min_cutoff = 1.0, double beta = 0.01, double d_cutoff = 1.0);

  void Reset();

  std::pair<double, double> Update(std::int64_t timestamp_ms, double x, double y);

 private:
  struct LowPass1DState {
    bool initialized = false;
    double value = 0.0;
  };

  struct OneEuro1DState {
    std::optional<std::int64_t> prev_t_ms;
    double prev_raw = 0.0;
    LowPass1DState x_filter;
    LowPass1DState dx_filter;
  };

  static double Alpha(double delta_seconds, double cutoff_hz);
  static double FilterLowPass(double value, double alpha, LowPass1DState* state);

  double UpdateAxis(std::int64_t timestamp_ms, double value, OneEuro1DState* state);

  double min_cutoff_;
  double beta_;
  double d_cutoff_;
  OneEuro1DState fx_;
  OneEuro1DState fy_;
};

}  // namespace gaze_core
