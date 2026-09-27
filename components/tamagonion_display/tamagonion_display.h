#pragma once

#include <ESP8266WiFi.h>
#include <bearssl/bearssl.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

#include "esphome/components/display/display.h"
#include "esphome/core/component.h"

namespace esphome {
namespace tamagonion_display {

class TamagonionDisplay : public Component {
 protected:
  enum class SessionState : uint8_t {
    DISCONNECTED,
    AWAITING_AUTH,
    AUTHENTICATED,
  };

 public:
  void set_display(display::Display *display) { this->display_ = display; }
  void set_port(uint16_t port) { this->port_ = port; }
  void set_max_frame_size(size_t size) { this->max_frame_size_ = size; }
  void set_pairing_code(const std::string &code) { this->pairing_code_ = code; }

  void setup() override;
  void loop() override;
  void dump_config() override;

  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  bool has_frame() const { return this->has_frame_; }
  bool is_authenticated() const { return this->session_state_ == SessionState::AUTHENTICATED; }
  bool has_client() const { return this->session_state_ != SessionState::DISCONNECTED; }

  size_t get_line_count() const { return this->line_count_; }
  const std::string &get_line(size_t index) const { return this->lines_[index]; }
  const std::string &get_pairing_code() const { return this->pairing_code_; }

  std::string get_ip_address() const { return std::string(WiFi.localIP().toString().c_str()); }
  uint16_t get_port() const { return this->port_; }

 protected:
  static constexpr size_t AUTH_NONCE_BYTES = 16;
  static constexpr size_t READ_BUFFER_BYTES = 256;
  static constexpr size_t MAX_AUTH_LINE_BYTES = 160;
  static constexpr size_t MAX_HEADER_BYTES = 96;
  static constexpr size_t MAX_VISIBLE_LINES = 20;
  static constexpr uint32_t AUTH_TIMEOUT_MS = 5000;

  void accept_client_();
  void close_client_(const char *reason);
  void reset_transport_state_();
  void mark_display_dirty_();
  void invalidate_frame_();
  void refresh_display_if_needed_();
  void refresh_network_state_();

  void start_auth_challenge_();
  bool process_rx_();
  bool process_auth_line_(std::string line);
  bool parse_header_(std::string header);
  void commit_frame_(const std::string &payload);

  void send_line_(const std::string &line);

  std::string hmac_sha256_hex_(const std::string &key, const std::string &data) const;

  static std::string bytes_to_hex_(const uint8_t *data, size_t len);
  static bool constant_time_equal_(const std::string &left, const std::string &right);

  display::Display *display_{nullptr};

  uint16_t port_{18511};
  size_t max_frame_size_{4096};
  std::string pairing_code_;

  std::unique_ptr<WiFiServer> server_;
  WiFiClient client_;
  SessionState session_state_{SessionState::DISCONNECTED};

  std::string rx_buffer_;
  std::string challenge_;
  uint32_t auth_deadline_{0};

  bool awaiting_payload_{false};
  size_t expected_payload_size_{0};
  uint32_t pending_sequence_{0};

  bool has_frame_{false};
  uint32_t sequence_{0};
  std::array<std::string, MAX_VISIBLE_LINES> lines_;
  size_t line_count_{0};

  bool display_dirty_{false};
  bool network_state_initialized_{false};
  uint32_t last_ip_address_{0};
};

}  // namespace tamagonion_display
}  // namespace esphome
