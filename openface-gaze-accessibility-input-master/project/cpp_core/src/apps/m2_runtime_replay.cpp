#include "gaze_core/runtime/m2.hpp"

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

std::vector<std::string> SplitCsvSimple(const std::string& line) {
  std::vector<std::string> out;
  std::string cur;
  for (char c : line) {
    if (c == ',') {
      out.push_back(cur);
      cur.clear();
    } else if (c != '\r') {
      cur.push_back(c);
    }
  }
  out.push_back(cur);
  return out;
}

std::string JsonEscape(const std::string& s) {
  std::string out;
  out.reserve(s.size() + 8);
  for (char c : s) {
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        out.push_back(c);
        break;
    }
  }
  return out;
}

double ToDouble(const std::string& s) {
  char* end = nullptr;
  const double v = std::strtod(s.c_str(), &end);
  if (end == s.c_str()) {
    throw std::invalid_argument("invalid float: " + s);
  }
  return v;
}

std::int64_t ToInt64Round(const std::string& s) {
  return static_cast<std::int64_t>(std::llround(ToDouble(s)));
}

struct GazeRow {
  std::int64_t timestamp_ms = 0;
  double gaze_x = 0.0;
  double gaze_y = 0.0;
};

struct TracePoint {
  std::int64_t timestamp_ms = 0;
  double x = 0.0;
  double y = 0.0;
};

struct Options {
  std::string calibration_csv;
  std::string raw_x_col = "raw_x";
  std::string raw_y_col = "raw_y";
  std::string screen_x_col = "screen_x";
  std::string screen_y_col = "screen_y";

  std::string gaze_csv;
  std::string timestamp_col = "timestamp_ms";
  std::string x_col = "gaze_x";
  std::string y_col = "gaze_y";

  bool clamp = true;

  double ema_alpha = 0.4;
  double one_euro_min_cutoff = 1.0;
  double one_euro_beta = 0.01;
  double one_euro_d_cutoff = 1.0;

  std::string output_json;
};

Options ParseArgs(int argc, char** argv) {
  Options opt;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto need = [&](const char* name) -> std::string {
      if (i + 1 >= argc) {
        throw std::invalid_argument(std::string("missing value for ") + name);
      }
      ++i;
      return argv[i];
    };

    if (arg == "--calibration-csv") {
      opt.calibration_csv = need("--calibration-csv");
    } else if (arg == "--raw-x-col") {
      opt.raw_x_col = need("--raw-x-col");
    } else if (arg == "--raw-y-col") {
      opt.raw_y_col = need("--raw-y-col");
    } else if (arg == "--screen-x-col") {
      opt.screen_x_col = need("--screen-x-col");
    } else if (arg == "--screen-y-col") {
      opt.screen_y_col = need("--screen-y-col");
    } else if (arg == "--gaze-csv") {
      opt.gaze_csv = need("--gaze-csv");
    } else if (arg == "--timestamp-col") {
      opt.timestamp_col = need("--timestamp-col");
    } else if (arg == "--x-col") {
      opt.x_col = need("--x-col");
    } else if (arg == "--y-col") {
      opt.y_col = need("--y-col");
    } else if (arg == "--no-clamp") {
      opt.clamp = false;
    } else if (arg == "--ema-alpha") {
      opt.ema_alpha = ToDouble(need("--ema-alpha"));
    } else if (arg == "--one-euro-min-cutoff") {
      opt.one_euro_min_cutoff = ToDouble(need("--one-euro-min-cutoff"));
    } else if (arg == "--one-euro-beta") {
      opt.one_euro_beta = ToDouble(need("--one-euro-beta"));
    } else if (arg == "--one-euro-d-cutoff") {
      opt.one_euro_d_cutoff = ToDouble(need("--one-euro-d-cutoff"));
    } else if (arg == "--output-json") {
      opt.output_json = need("--output-json");
    } else if (arg == "--help" || arg == "-h") {
      std::cout
          << "Usage: m2_runtime_replay --calibration-csv <path> --gaze-csv <path> "
             "[--raw-x-col raw_x] [--raw-y-col raw_y] [--screen-x-col screen_x] [--screen-y-col screen_y] "
             "[--timestamp-col timestamp_ms] [--x-col gaze_x] [--y-col gaze_y] [--no-clamp] "
             "[--ema-alpha 0.4] [--one-euro-min-cutoff 1.0] [--one-euro-beta 0.01] [--one-euro-d-cutoff 1.0] "
             "[--output-json <path>]\n";
      std::exit(0);
    } else {
      throw std::invalid_argument("unknown arg: " + arg);
    }
  }

  if (opt.calibration_csv.empty()) {
    throw std::invalid_argument("--calibration-csv is required");
  }
  if (opt.gaze_csv.empty()) {
    throw std::invalid_argument("--gaze-csv is required");
  }
  return opt;
}

std::vector<gaze_core::CalibrationPoint> LoadCalibrationPoints(const Options& opt) {
  std::ifstream in(opt.calibration_csv);
  if (!in.is_open()) {
    throw std::runtime_error("failed to open calibration csv: " + opt.calibration_csv);
  }

  std::string header_line;
  if (!std::getline(in, header_line)) {
    throw std::runtime_error("empty calibration csv: " + opt.calibration_csv);
  }
  const auto headers = SplitCsvSimple(header_line);
  std::unordered_map<std::string, std::size_t> idx;
  for (std::size_t i = 0; i < headers.size(); ++i) {
    idx[headers[i]] = i;
  }

  if (idx.find(opt.raw_x_col) == idx.end() || idx.find(opt.raw_y_col) == idx.end() ||
      idx.find(opt.screen_x_col) == idx.end() || idx.find(opt.screen_y_col) == idx.end()) {
    throw std::runtime_error("missing required columns in calibration csv");
  }

  std::vector<gaze_core::CalibrationPoint> points;
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty()) {
      continue;
    }
    const auto cols = SplitCsvSimple(line);
    const auto get_col = [&](const std::string& name) -> std::string {
      const auto it = idx.find(name);
      if (it == idx.end() || it->second >= cols.size()) {
        return "";
      }
      return cols[it->second];
    };

    const std::string raw_x = get_col(opt.raw_x_col);
    const std::string raw_y = get_col(opt.raw_y_col);
    const std::string screen_x = get_col(opt.screen_x_col);
    const std::string screen_y = get_col(opt.screen_y_col);
    if (raw_x.empty() || raw_y.empty() || screen_x.empty() || screen_y.empty()) {
      continue;
    }

    gaze_core::CalibrationPoint point;
    point.raw_x = ToDouble(raw_x);
    point.raw_y = ToDouble(raw_y);
    point.screen_x = ToDouble(screen_x);
    point.screen_y = ToDouble(screen_y);
    points.push_back(point);
  }
  return points;
}

std::vector<GazeRow> LoadGazeRows(const Options& opt) {
  std::ifstream in(opt.gaze_csv);
  if (!in.is_open()) {
    throw std::runtime_error("failed to open gaze csv: " + opt.gaze_csv);
  }

  std::string header_line;
  if (!std::getline(in, header_line)) {
    throw std::runtime_error("empty gaze csv: " + opt.gaze_csv);
  }
  const auto headers = SplitCsvSimple(header_line);
  std::unordered_map<std::string, std::size_t> idx;
  for (std::size_t i = 0; i < headers.size(); ++i) {
    idx[headers[i]] = i;
  }

  if (idx.find(opt.timestamp_col) == idx.end() || idx.find(opt.x_col) == idx.end() || idx.find(opt.y_col) == idx.end()) {
    throw std::runtime_error("missing required columns in gaze csv");
  }

  std::vector<GazeRow> rows;
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty()) {
      continue;
    }

    const auto cols = SplitCsvSimple(line);
    const auto get_col = [&](const std::string& name) -> std::string {
      const auto it = idx.find(name);
      if (it == idx.end() || it->second >= cols.size()) {
        return "";
      }
      return cols[it->second];
    };

    const std::string ts_raw = get_col(opt.timestamp_col);
    const std::string x_raw = get_col(opt.x_col);
    const std::string y_raw = get_col(opt.y_col);
    if (ts_raw.empty() || x_raw.empty() || y_raw.empty()) {
      continue;
    }

    GazeRow row;
    row.timestamp_ms = ToInt64Round(ts_raw);
    row.gaze_x = ToDouble(x_raw);
    row.gaze_y = ToDouble(y_raw);
    rows.push_back(row);
  }

  return rows;
}

std::string BuildJson(const Options& opt,
                      const gaze_core::AffineCalibrationFitResult& fit,
                      const std::vector<TracePoint>& ema_trace,
                      const std::vector<TracePoint>& one_euro_trace) {
  std::ostringstream os;
  os << std::setprecision(17);
  os << "{\n";
  os << "  \"calibration_csv\": \"" << JsonEscape(opt.calibration_csv) << "\",\n";
  os << "  \"gaze_csv\": \"" << JsonEscape(opt.gaze_csv) << "\",\n";
  os << "  \"calibration\": {\n";
  os << "    \"model\": {"
     << "\"ax\": " << fit.model.ax() << ", "
     << "\"bx\": " << fit.model.bx() << ", "
     << "\"cx\": " << fit.model.cx() << ", "
     << "\"ay\": " << fit.model.ay() << ", "
     << "\"by\": " << fit.model.by() << ", "
     << "\"cy\": " << fit.model.cy() << ", "
     << "\"clamp\": " << (fit.model.clamp() ? "true" : "false") << "},\n";
  os << "    \"fit_metrics\": {"
     << "\"point_count\": " << fit.metrics.point_count << ", "
     << "\"mae_x\": " << fit.metrics.mae_x << ", "
     << "\"mae_y\": " << fit.metrics.mae_y << ", "
     << "\"rmse\": " << fit.metrics.rmse << ", "
     << "\"max_abs_error\": " << fit.metrics.max_abs_error << "}\n";
  os << "  },\n";

  os << "  \"ema\": {\n";
  os << "    \"alpha\": " << opt.ema_alpha << ",\n";
  os << "    \"trace\": [\n";
  for (std::size_t i = 0; i < ema_trace.size(); ++i) {
    const auto& p = ema_trace[i];
    os << "      {"
       << "\"timestamp_ms\": " << p.timestamp_ms << ", "
       << "\"x\": " << p.x << ", "
       << "\"y\": " << p.y << "}";
    if (i + 1 < ema_trace.size()) {
      os << ",";
    }
    os << "\n";
  }
  os << "    ]\n";
  os << "  },\n";

  os << "  \"one_euro\": {\n";
  os << "    \"min_cutoff\": " << opt.one_euro_min_cutoff << ",\n";
  os << "    \"beta\": " << opt.one_euro_beta << ",\n";
  os << "    \"d_cutoff\": " << opt.one_euro_d_cutoff << ",\n";
  os << "    \"trace\": [\n";
  for (std::size_t i = 0; i < one_euro_trace.size(); ++i) {
    const auto& p = one_euro_trace[i];
    os << "      {"
       << "\"timestamp_ms\": " << p.timestamp_ms << ", "
       << "\"x\": " << p.x << ", "
       << "\"y\": " << p.y << "}";
    if (i + 1 < one_euro_trace.size()) {
      os << ",";
    }
    os << "\n";
  }
  os << "    ]\n";
  os << "  }\n";
  os << "}\n";

  return os.str();
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options opt = ParseArgs(argc, argv);

    const auto calibration_points = LoadCalibrationPoints(opt);
    const auto fit = gaze_core::FitAffineCalibration(calibration_points, opt.clamp);

    const auto gaze_rows = LoadGazeRows(opt);
    gaze_core::EmaSmoother2D ema(opt.ema_alpha);
    gaze_core::OneEuroSmoother2D one_euro(opt.one_euro_min_cutoff, opt.one_euro_beta, opt.one_euro_d_cutoff);

    std::vector<TracePoint> ema_trace;
    std::vector<TracePoint> one_euro_trace;
    ema_trace.reserve(gaze_rows.size());
    one_euro_trace.reserve(gaze_rows.size());

    for (const auto& row : gaze_rows) {
      const auto [ema_x, ema_y] = ema.Update(row.timestamp_ms, row.gaze_x, row.gaze_y);
      const auto [one_x, one_y] = one_euro.Update(row.timestamp_ms, row.gaze_x, row.gaze_y);

      TracePoint ema_point;
      ema_point.timestamp_ms = row.timestamp_ms;
      ema_point.x = ema_x;
      ema_point.y = ema_y;
      ema_trace.push_back(ema_point);

      TracePoint one_point;
      one_point.timestamp_ms = row.timestamp_ms;
      one_point.x = one_x;
      one_point.y = one_y;
      one_euro_trace.push_back(one_point);
    }

    const std::string output = BuildJson(opt, fit, ema_trace, one_euro_trace);
    std::cout << output;

    if (!opt.output_json.empty()) {
      std::ofstream out(opt.output_json);
      if (!out.is_open()) {
        throw std::runtime_error("failed to open output json: " + opt.output_json);
      }
      out << output;
    }

    return 0;
  } catch (const std::exception& e) {
    std::cerr << "[m2_runtime_replay][error] " << e.what() << "\n";
    return 2;
  }
}
