#include "gaze_core/runtime_m2.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace gaze_core {

namespace {

std::vector<double> Solve3x3(const std::vector<std::vector<double>>& a, const std::vector<double>& b) {
  if (a.size() != 3 || b.size() != 3) {
    throw std::invalid_argument("Solve3x3 expects 3x3 matrix and size-3 rhs");
  }

  std::vector<std::vector<double>> mat(3, std::vector<double>(4, 0.0));
  for (std::int32_t r = 0; r < 3; ++r) {
    if (a[r].size() != 3) {
      throw std::invalid_argument("Solve3x3 expects 3x3 matrix");
    }
    for (std::int32_t c = 0; c < 3; ++c) {
      mat[r][c] = a[r][c];
    }
    mat[r][3] = b[r];
  }

  for (std::int32_t col = 0; col < 3; ++col) {
    std::int32_t pivot = col;
    double pivot_abs = std::abs(mat[col][col]);
    for (std::int32_t r = col + 1; r < 3; ++r) {
      const double cand_abs = std::abs(mat[r][col]);
      if (cand_abs > pivot_abs) {
        pivot_abs = cand_abs;
        pivot = r;
      }
    }
    if (std::abs(mat[pivot][col]) < 1e-12) {
      throw std::invalid_argument("Calibration matrix is singular; provide more diverse calibration points.");
    }
    if (pivot != col) {
      std::swap(mat[col], mat[pivot]);
    }

    const double pivot_val = mat[col][col];
    for (std::int32_t j = col; j < 4; ++j) {
      mat[col][j] /= pivot_val;
    }

    for (std::int32_t r = 0; r < 3; ++r) {
      if (r == col) {
        continue;
      }
      const double factor = mat[r][col];
      if (factor == 0.0) {
        continue;
      }
      for (std::int32_t j = col; j < 4; ++j) {
        mat[r][j] -= factor * mat[col][j];
      }
    }
  }

  return {
      mat[0][3],
      mat[1][3],
      mat[2][3],
  };
}

}  // namespace

AffineCalibration::AffineCalibration(double ax, double bx, double cx, double ay, double by, double cy, bool clamp)
    : ax_(ax), bx_(bx), cx_(cx), ay_(ay), by_(by), cy_(cy), clamp_(clamp) {}

std::pair<double, double> AffineCalibration::Normalize(double raw_x, double raw_y) const {
  double x = ax_ * raw_x + bx_ * raw_y + cx_;
  double y = ay_ * raw_x + by_ * raw_y + cy_;
  if (clamp_) {
    x = std::min(1.0, std::max(0.0, x));
    y = std::min(1.0, std::max(0.0, y));
  }
  return {x, y};
}

AffineCalibrationFitResult FitAffineCalibration(const std::vector<CalibrationPoint>& points, bool clamp) {
  if (points.size() < 3) {
    throw std::invalid_argument("At least 3 points are required for affine calibration.");
  }

  double s_xx = 0.0;
  double s_xy = 0.0;
  double s_yy = 0.0;
  double s_x1 = 0.0;
  double s_y1 = 0.0;
  const double s_11 = static_cast<double>(points.size());

  std::vector<double> rhs_x(3, 0.0);
  std::vector<double> rhs_y(3, 0.0);

  for (const auto& p : points) {
    const double x = p.raw_x;
    const double y = p.raw_y;
    const double u = p.screen_x;
    const double v = p.screen_y;

    s_xx += x * x;
    s_xy += x * y;
    s_yy += y * y;
    s_x1 += x;
    s_y1 += y;

    rhs_x[0] += x * u;
    rhs_x[1] += y * u;
    rhs_x[2] += u;

    rhs_y[0] += x * v;
    rhs_y[1] += y * v;
    rhs_y[2] += v;
  }

  const double ridge = 1e-8;
  const std::vector<std::vector<double>> normal = {
      {s_xx + ridge, s_xy, s_x1},
      {s_xy, s_yy + ridge, s_y1},
      {s_x1, s_y1, s_11 + ridge},
  };

  const auto x_sol = Solve3x3(normal, rhs_x);
  const auto y_sol = Solve3x3(normal, rhs_y);

  const AffineCalibration calibration(x_sol[0], x_sol[1], x_sol[2], y_sol[0], y_sol[1], y_sol[2], clamp);

  double abs_sum_x = 0.0;
  double abs_sum_y = 0.0;
  double sq_sum = 0.0;
  double max_abs = 0.0;
  for (const auto& p : points) {
    const auto [pred_x, pred_y] = calibration.Normalize(p.raw_x, p.raw_y);
    const double dx = pred_x - p.screen_x;
    const double dy = pred_y - p.screen_y;
    const double abs_x = std::abs(dx);
    const double abs_y = std::abs(dy);
    abs_sum_x += abs_x;
    abs_sum_y += abs_y;
    sq_sum += dx * dx + dy * dy;
    max_abs = std::max(max_abs, std::max(abs_x, abs_y));
  }

  CalibrationFitMetrics metrics;
  metrics.point_count = static_cast<std::int32_t>(points.size());
  metrics.mae_x = abs_sum_x / static_cast<double>(points.size());
  metrics.mae_y = abs_sum_y / static_cast<double>(points.size());
  metrics.rmse = std::sqrt(sq_sum / (2.0 * static_cast<double>(points.size())));
  metrics.max_abs_error = max_abs;

  return {
      calibration,
      metrics,
  };
}

EmaSmoother2D::EmaSmoother2D(double alpha) : alpha_(alpha), x_(std::nullopt), y_(std::nullopt) {
  if (alpha_ <= 0.0 || alpha_ > 1.0) {
    throw std::invalid_argument("EMA alpha must be in (0, 1].");
  }
}

void EmaSmoother2D::Reset() {
  x_.reset();
  y_.reset();
}

std::pair<double, double> EmaSmoother2D::Update(std::int64_t timestamp_ms, double x, double y) {
  (void)timestamp_ms;
  if (!x_.has_value() || !y_.has_value()) {
    x_ = x;
    y_ = y;
    return {x, y};
  }

  x_ = alpha_ * x + (1.0 - alpha_) * (*x_);
  y_ = alpha_ * y + (1.0 - alpha_) * (*y_);
  return {*x_, *y_};
}

OneEuroSmoother2D::OneEuroSmoother2D(double min_cutoff, double beta, double d_cutoff)
    : min_cutoff_(min_cutoff), beta_(beta), d_cutoff_(d_cutoff) {
  if (min_cutoff_ <= 0.0) {
    throw std::invalid_argument("min_cutoff must be > 0.");
  }
  if (d_cutoff_ <= 0.0) {
    throw std::invalid_argument("d_cutoff must be > 0.");
  }
  if (beta_ < 0.0) {
    throw std::invalid_argument("beta must be >= 0.");
  }
}

void OneEuroSmoother2D::Reset() {
  fx_ = OneEuro1DState{};
  fy_ = OneEuro1DState{};
}

double OneEuroSmoother2D::Alpha(double delta_seconds, double cutoff_hz) {
  constexpr double kPi = 3.14159265358979323846;
  const double tau = 1.0 / (2.0 * kPi * cutoff_hz);
  return 1.0 / (1.0 + (tau / delta_seconds));
}

double OneEuroSmoother2D::FilterLowPass(double value, double alpha, LowPass1DState* state) {
  if (!state->initialized) {
    state->initialized = true;
    state->value = value;
    return value;
  }
  state->value = alpha * value + (1.0 - alpha) * state->value;
  return state->value;
}

double OneEuroSmoother2D::UpdateAxis(std::int64_t timestamp_ms, double value, OneEuro1DState* state) {
  if (!state->prev_t_ms.has_value()) {
    state->prev_t_ms = timestamp_ms;
    state->prev_raw = value;
    return FilterLowPass(value, 1.0, &state->x_filter);
  }

  const double delta_s = std::max(1e-3, static_cast<double>(timestamp_ms - *state->prev_t_ms) / 1000.0);
  state->prev_t_ms = timestamp_ms;

  const double dx = (value - state->prev_raw) / delta_s;
  state->prev_raw = value;

  const double alpha_d = Alpha(delta_s, d_cutoff_);
  const double dx_hat = FilterLowPass(dx, alpha_d, &state->dx_filter);

  const double cutoff = min_cutoff_ + beta_ * std::abs(dx_hat);
  const double alpha_x = Alpha(delta_s, cutoff);
  return FilterLowPass(value, alpha_x, &state->x_filter);
}

std::pair<double, double> OneEuroSmoother2D::Update(std::int64_t timestamp_ms, double x, double y) {
  return {
      UpdateAxis(timestamp_ms, x, &fx_),
      UpdateAxis(timestamp_ms, y, &fy_),
  };
}

}  // namespace gaze_core
