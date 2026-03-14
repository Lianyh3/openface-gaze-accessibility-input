#include "gaze_core/runtime/m1.hpp"

#include <cmath>
#include <cstdlib>
#include <fstream>
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

struct Options {
  std::string gaze_csv;
  std::string timestamp_col = "timestamp_ms";
  std::string x_col = "gaze_x";
  std::string y_col = "gaze_y";
  std::int64_t dwell_ms = 600;
  std::int32_t candidate_slots = 8;
  double x_min = 0.0;
  double x_max = 1.0;
  double y_min = 0.0;
  double y_max = 1.0;
  bool clamp = true;
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
    if (arg == "--gaze-csv") {
      opt.gaze_csv = need("--gaze-csv");
    } else if (arg == "--timestamp-col") {
      opt.timestamp_col = need("--timestamp-col");
    } else if (arg == "--x-col") {
      opt.x_col = need("--x-col");
    } else if (arg == "--y-col") {
      opt.y_col = need("--y-col");
    } else if (arg == "--dwell-ms") {
      opt.dwell_ms = std::stoll(need("--dwell-ms"));
    } else if (arg == "--candidate-slots") {
      opt.candidate_slots = std::stoi(need("--candidate-slots"));
    } else if (arg == "--x-min") {
      opt.x_min = ToDouble(need("--x-min"));
    } else if (arg == "--x-max") {
      opt.x_max = ToDouble(need("--x-max"));
    } else if (arg == "--y-min") {
      opt.y_min = ToDouble(need("--y-min"));
    } else if (arg == "--y-max") {
      opt.y_max = ToDouble(need("--y-max"));
    } else if (arg == "--no-clamp") {
      opt.clamp = false;
    } else if (arg == "--output-json") {
      opt.output_json = need("--output-json");
    } else if (arg == "--help" || arg == "-h") {
      std::cout
          << "Usage: m1_runtime_replay --gaze-csv <path> [--timestamp-col timestamp_ms] [--x-col gaze_x] "
             "[--y-col gaze_y] [--dwell-ms 600] [--candidate-slots 8] [--x-min 0] [--x-max 1] [--y-min 0] "
             "[--y-max 1] [--no-clamp] [--output-json <path>]\n";
      std::exit(0);
    } else {
      throw std::invalid_argument("unknown arg: " + arg);
    }
  }
  if (opt.gaze_csv.empty()) {
    throw std::invalid_argument("--gaze-csv is required");
  }
  return opt;
}

struct EventOut {
  std::int64_t timestamp_ms = 0;
  std::string event_type;
  std::string target_id;
  std::string text;
  std::int32_t candidate_index = 0;
  std::int64_t dwell_started_ms = 0;
  std::int64_t dwell_elapsed_ms = 0;
};

std::string BuildJson(const std::string& gaze_csv,
                      std::size_t row_count,
                      std::size_t frame_count,
                      const std::vector<EventOut>& events) {
  std::ostringstream os;
  os << "{\n";
  os << "  \"gaze_csv\": \"" << JsonEscape(gaze_csv) << "\",\n";
  os << "  \"row_count\": " << row_count << ",\n";
  os << "  \"frame_count\": " << frame_count << ",\n";
  os << "  \"event_count\": " << events.size() << ",\n";
  os << "  \"events\": [\n";
  for (std::size_t i = 0; i < events.size(); ++i) {
    const auto& e = events[i];
    os << "    {"
       << "\"timestamp_ms\": " << e.timestamp_ms << ", "
       << "\"event_type\": \"" << JsonEscape(e.event_type) << "\", "
       << "\"target_id\": \"" << JsonEscape(e.target_id) << "\", "
       << "\"text\": \"" << JsonEscape(e.text) << "\", "
       << "\"candidate_index\": " << e.candidate_index << ", "
       << "\"dwell_started_ms\": " << e.dwell_started_ms << ", "
       << "\"dwell_elapsed_ms\": " << e.dwell_elapsed_ms << "}";
    if (i + 1 < events.size()) {
      os << ",";
    }
    os << "\n";
  }
  os << "  ]\n";
  os << "}\n";
  return os.str();
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options opt = ParseArgs(argc, argv);

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
    if (idx.find(opt.timestamp_col) == idx.end() || idx.find(opt.x_col) == idx.end() ||
        idx.find(opt.y_col) == idx.end()) {
      throw std::runtime_error("missing required columns in csv");
    }

    gaze_core::LayoutPreset preset;
    preset.candidate_slots = opt.candidate_slots;

    gaze_core::RuntimeM1 runtime(
        gaze_core::LinearNormalizer(opt.x_min, opt.x_max, opt.y_min, opt.y_max, opt.clamp),
        gaze_core::KeyboardHitTester::BuildDefault(preset),
        gaze_core::DwellDetectorCore(opt.dwell_ms));

    std::vector<EventOut> events;
    std::size_t row_count = 0;
    std::size_t frame_count = 0;
    std::string line;
    while (std::getline(in, line)) {
      if (line.empty()) {
        continue;
      }
      ++row_count;
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

      gaze_core::FrameFeatures frame;
      frame.frame_id = static_cast<std::int64_t>(frame_count + 1);
      frame.timestamp_ms = ToInt64Round(ts_raw);
      frame.raw_gaze_x = ToDouble(x_raw);
      frame.raw_gaze_y = ToDouble(y_raw);
      ++frame_count;

      const auto maybe_event = runtime.UpdateFrame(frame);
      if (!maybe_event.has_value()) {
        continue;
      }
      const auto& event = *maybe_event;
      EventOut out;
      out.timestamp_ms = event.timestamp_ms;
      out.event_type = gaze_core::ToString(event.event_type);
      out.target_id = event.target_id;
      out.text = event.text;
      out.candidate_index = event.candidate_index;
      out.dwell_started_ms = event.dwell_started_ms;
      out.dwell_elapsed_ms = event.dwell_elapsed_ms;
      events.push_back(out);
    }

    const std::string output = BuildJson(opt.gaze_csv, row_count, frame_count, events);
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
    std::cerr << "[m1_runtime_replay][error] " << e.what() << "\n";
    return 2;
  }
}
