#pragma once

#include <ESP8266WiFi.h>

#include <memory>
#include <string>
#include <vector>

#include "esphome/core/component.h"

namespace esphome {
namespace tamagonion_display {

class TamagonionDisplay : public Component {
 public:
  void set_port(uint16_t port) { this->port_ = port; }
  void set_max_frame_size(size_t size) { this->max_frame_size_ = size; }

  void setup() override;
  void loop() override;
  void dump_config() override;

  float get_setup_priority() const override {
    return setup_priority::AFTER_WIFI;
  }

  bool has_frame() const { return this->has_frame_; }

  const std::vector<std::string> &get_lines() const {
    return this->lines_;
  }

  uint32_t get_sequence() const {
    return this->sequence_;
  }

 protected:
  void reset_client_state_();
  void close_client_(const char *reason);

  bool process_rx_();
  bool parse_header_(std::string header);
  void commit_frame_(const std::string &payload);

  uint16_t port_{18511};
  size_t max_frame_size_{4096};

  std::unique_ptr<WiFiServer> server_;
  WiFiClient client_;

  std::string rx_buffer_;

  bool awaiting_payload_{false};
  size_t expected_payload_size_{0};
  uint32_t pending_sequence_{0};

  bool has_frame_{false};
  uint32_t sequence_{0};

  std::vector<std::string> lines_;
};

}  // namespace tamagonion_display
}  // namespace esphome
