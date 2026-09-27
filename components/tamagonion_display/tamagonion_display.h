#pragma once

#include <ESP8266WiFi.h>
#include <bearssl/bearssl.h>

#include <memory>
#include <string>
#include <vector>

#include "esphome/core/component.h"
#include "esphome/components/display/display.h"

namespace esphome {
namespace tamagonion_display {

class TamagonionDisplay : public Component {
 public:
  void set_port(uint16_t port) { this->port_ = port; }
  void set_max_frame_size(size_t size) { this->max_frame_size_ = size; }
  void set_pairing_code(const std::string &code) { this->pairing_code_ = code; }
  void set_display(display::Display *display) { this->display_ = display; }

  void setup() override;
  void loop() override;
  void dump_config() override;

  float get_setup_priority() const override {
    return setup_priority::AFTER_WIFI;
  }

  bool has_frame() const { return this->has_frame_; }
  bool is_authenticated() const { return this->authenticated_; }

  const std::vector<std::string> &get_lines() const {
    return this->lines_;
  }

  const std::string &get_pairing_code() const {
    return this->pairing_code_;
  }

  std::string get_ip_address() const {
    return WiFi.localIP().toString().c_str();
  }

  uint16_t get_port() const {
    return this->port_;
  }

 protected:
  void reset_client_state_();
  void close_client_(const char *reason);

  void start_auth_challenge_();
  bool process_rx_();
  bool process_auth_line_(std::string line);

  bool parse_header_(std::string header);
  void commit_frame_(const std::string &payload);

  void send_line_(const std::string &line);

  static std::string bytes_to_hex_(const uint8_t *data, size_t len);
  static bool constant_time_equal_(
      const std::string &a,
      const std::string &b
  );

  std::string hmac_sha256_hex_(
      const std::string &key,
      const std::string &data
  );

  display::Display *display_{nullptr};
  bool frame_dirty_{false};
  bool boot_screen_drawn_{false};

  uint16_t port_{18511};
  size_t max_frame_size_{4096};

  std::string pairing_code_;

  std::unique_ptr<WiFiServer> server_;
  WiFiClient client_;

  std::string rx_buffer_;

  bool authenticated_{false};
  std::string challenge_;
  uint32_t auth_deadline_{0};

  bool awaiting_payload_{false};
  size_t expected_payload_size_{0};
  uint32_t pending_sequence_{0};

  bool has_frame_{false};
  uint32_t sequence_{0};

  std::vector<std::string> lines_;
};

}  // namespace tamagonion_display
}  // namespace esphome
