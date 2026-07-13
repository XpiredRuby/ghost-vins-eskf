#include "ghost_x/config.hpp"
#include "ghost_x/imm.hpp"
#include "ghost_x/kalman_filter.hpp"
#include "ghost_x/mode_bank.hpp"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct InputRow {
  double t_s{};
  bool visible{};
  std::optional<ghost_x::Measurement> measurement;
};

std::vector<std::string> split(const std::string &line) {
  std::vector<std::string> fields;
  std::stringstream stream(line);
  std::string field;
  while (std::getline(stream, field, ',')) {
    fields.push_back(field);
  }
  while (fields.size() < 4U) {
    fields.emplace_back();
  }
  return fields;
}

std::vector<InputRow> read_input(const std::string &path) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("cannot open input CSV: " + path);
  }
  std::string line;
  std::getline(input, line);
  if (line != "t_s,visible,x_m,y_m") {
    throw std::runtime_error("unexpected CSV header");
  }
  std::vector<InputRow> rows;
  double previous_t = 0.0;
  bool first = true;
  while (std::getline(input, line)) {
    if (line.empty()) {
      continue;
    }
    const auto fields = split(line);
    InputRow row;
    row.t_s = std::stod(fields.at(0));
    row.visible = fields.at(1) == "1" || fields.at(1) == "true";
    if (!first && row.t_s <= previous_t) {
      throw std::runtime_error("timestamps must be strictly increasing");
    }
    first = false;
    previous_t = row.t_s;
    if (row.visible) {
      ghost_x::Measurement measurement;
      measurement << std::stod(fields.at(2)), std::stod(fields.at(3));
      row.measurement = measurement;
    }
    rows.push_back(row);
  }
  if (rows.empty()) {
    throw std::runtime_error("input CSV is empty");
  }
  return rows;
}

void write_header(std::ofstream &output) {
  output << "t_s,initialized,status,x_m,y_m,vx_mps,vy_mps,cov_xx,cov_xy,cov_yy,cov_vxvx,cov_vyvy\n";
}

void write_estimate(std::ofstream &output, double t_s, const ghost_x::Estimate &estimate) {
  output << std::setprecision(17) << t_s << ',' << (estimate.initialized ? 1 : 0) << ',' << estimate.status;
  if (!estimate.initialized) {
    output << ",,,,,,,,,\n";
    return;
  }
  output << ',' << estimate.state(0) << ',' << estimate.state(1) << ',' << estimate.state(2) << ','
         << estimate.state(3) << ',' << estimate.covariance(0, 0) << ',' << estimate.covariance(0, 1) << ','
         << estimate.covariance(1, 1) << ',' << estimate.covariance(2, 2) << ',' << estimate.covariance(3, 3)
         << '\n';
}

}  // namespace

int main(int argc, char **argv) {
  try {
    if (argc != 4 && argc != 5) {
      std::cerr << "usage: ghost_x_estimator_cli <cv|imm|mh> <input.csv> <output.csv> [config.cfg]\n";
      return 2;
    }
    const std::string estimator = argv[1];
    const auto rows = read_input(argv[2]);
    const ghost_x::EstimatorConfiguration configuration =
        argc == 5 ? ghost_x::load_estimator_configuration(argv[4])
                  : ghost_x::default_estimator_configuration();
    if (argc == 5) {
      std::cerr << "configuration_digest=" << configuration.source_digest_fnv1a64 << '\n';
    }

    std::ofstream output(argv[3]);
    if (!output) {
      throw std::runtime_error("cannot open output CSV");
    }
    write_header(output);

    ghost_x::CvKalmanFilter cv(configuration.cv);
    ghost_x::InteractingMultipleModel imm(configuration.imm);
    ghost_x::ModeBankTracker mh(configuration.mh);

    double previous_t = rows.front().t_s;
    for (std::size_t index = 0; index < rows.size(); ++index) {
      const auto &row = rows[index];
      const double dt_s = index == 0U ? 0.1 : row.t_s - previous_t;
      previous_t = row.t_s;
      if (estimator == "cv") {
        write_estimate(output, row.t_s, cv.step(dt_s, row.measurement));
      } else if (estimator == "imm") {
        write_estimate(output, row.t_s, imm.step(dt_s, row.measurement));
      } else if (estimator == "mh") {
        write_estimate(output, row.t_s, mh.step(dt_s, row.measurement));
      } else {
        throw std::runtime_error("unknown estimator: " + estimator);
      }
    }
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "ghost_x_estimator_cli: " << error.what() << '\n';
    return 1;
  }
}
