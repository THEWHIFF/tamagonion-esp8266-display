#include "tamagonion_display.h"

#include <algorithm>
#include <cstdio>
#include <utility>

#include "esphome/core/log.h"

namespace esphome {
namespace tamagonion_display {

static const char *const TAG = "tamagonion_display";

void TamagonionDisplay::setup() {
  this->server_ = std::make_unique<WiFiServer>(this->port_);
  this->server_->begin();
  this->server_->setNoDelay(true);

  this->mark_display_dirty_();

  ESP_LOGI(TAG, "TCP server listening on port %u", this->port_);
}

void TamagonionDisplay::dump_config() {
  ESP_LOGCONFIG(TAG, "Tamagonion Display:");
  ESP_LOGCONFIG(TAG, "  TCP port: %u", this->port_);
  ESP_LOGCONFIG(TAG, "  Maximum frame size: %u bytes", static_cast<unsigned>(this->max_frame_size_));
  ESP_LOGCONFIG(TAG, "  Authentication: HMAC-SHA256 challenge-response");
}

void TamagonionDisplay::reset_transport_state_() {
  this->rx_buffer_.clear();
  this->challenge_.clear();
  this->auth_deadline_ = 0;

  this->awaiting_payload_ = false;
  this->expected_payload_size_ = 0;
  this->pending_sequence_ = 0;
}

void TamagonionDisplay::mark_display_dirty_() { this->display_dirty_ = true; }

void TamagonionDisplay::invalidate_frame_() {
  this->has_frame_ = false;
  this->line_count_ = 0;
  this->mark_display_dirty_();
}

void TamagonionDisplay::close_client_(const char *reason) {
  if (reason != nullptr) {
    ESP_LOGW(TAG, "Closing TCP client: %s", reason);
  }

  if (this->client_) {
    this->client_.stop();
  }

  this->session_state_ = SessionState::DISCONNECTED;
  this->reset_transport_state_();
  this->invalidate_frame_();
}

void TamagonionDisplay::accept_client_() {
  WiFiClient incoming = this->server_->accept();
  if (!incoming) {
    return;
  }

  this->client_ = incoming;
  this->client_.setNoDelay(true);

  this->reset_transport_state_();
  this->session_state_ = SessionState::AWAITING_AUTH;
  this->invalidate_frame_();

  ESP_LOGI(TAG, "TCP client connected");
  this->start_auth_challenge_();
}

std::string TamagonionDisplay::bytes_to_hex_(const uint8_t *data, size_t len) {
  static constexpr char HEX_DIGITS[] = "0123456789abcdef";

  std::string output;
  output.resize(len * 2);

  for (size_t i = 0; i < len; ++i) {
    output[i * 2] = HEX_DIGITS[(data[i] >> 4) & 0x0F];
    output[i * 2 + 1] = HEX_DIGITS[data[i] & 0x0F];
  }

  return output;
}

bool TamagonionDisplay::constant_time_equal_(const std::string &left, const std::string &right) {
  if (left.size() != right.size()) {
    return false;
  }

  uint8_t difference = 0;
  for (size_t i = 0; i < left.size(); ++i) {
    difference |= static_cast<uint8_t>(left[i] ^ right[i]);
  }

  return difference == 0;
}

std::string TamagonionDisplay::hmac_sha256_hex_(const std::string &key, const std::string &data) const {
  br_hmac_key_context key_context;
  br_hmac_context context;
  uint8_t digest[32];

  br_hmac_key_init(&key_context, &br_sha256_vtable, key.data(), key.size());
  br_hmac_init(&context, &key_context, 0);
  br_hmac_update(&context, data.data(), data.size());
  br_hmac_out(&context, digest);

  return bytes_to_hex_(digest, sizeof(digest));
}

void TamagonionDisplay::send_line_(const std::string &line) {
  if (!this->client_ || !this->client_.connected()) {
    return;
  }

  this->client_.write(reinterpret_cast<const uint8_t *>(line.data()), line.size());
  this->client_.write('\n');
}

void TamagonionDisplay::start_auth_challenge_() {
  uint8_t nonce[AUTH_NONCE_BYTES];
  ESP.random(nonce, sizeof(nonce));

  this->challenge_ = bytes_to_hex_(nonce, sizeof(nonce));
  this->auth_deadline_ = millis() + AUTH_TIMEOUT_MS;

  this->send_line_("TG1|CHALLENGE|" + this->challenge_);
  ESP_LOGD(TAG, "Authentication challenge sent");
}

bool TamagonionDisplay::process_auth_line_(std::string line) {
  if (!line.empty() && line.back() == '\r') {
    line.pop_back();
  }

  static const std::string PREFIX = "TG1|AUTH|";
  if (line.rfind(PREFIX, 0) != 0) {
    this->send_line_("TG1|ERR|AUTH_REQUIRED");
    return false;
  }

  const std::string provided_digest = line.substr(PREFIX.size());
  const std::string expected_digest = this->hmac_sha256_hex_(this->pairing_code_, this->challenge_);

  if (!constant_time_equal_(provided_digest, expected_digest)) {
    this->send_line_("TG1|ERR|AUTH_FAILED");
    ESP_LOGW(TAG, "Client authentication failed");
    return false;
  }

  this->session_state_ = SessionState::AUTHENTICATED;
  this->auth_deadline_ = 0;
  this->challenge_.clear();
  this->send_line_("TG1|OK");
  this->mark_display_dirty_();

  ESP_LOGI(TAG, "Client authenticated");
  return true;
}

bool TamagonionDisplay::parse_header_(std::string header) {
  if (!header.empty() && header.back() == '\r') {
    header.pop_back();
  }

  unsigned long sequence = 0;
  unsigned long payload_size = 0;
  char trailing = 0;

  const int parsed_fields = std::sscanf(
      header.c_str(),
      "TG1|%lu|%lu%c",
      &sequence,
      &payload_size,
      &trailing);

  if (parsed_fields != 2) {
    ESP_LOGW(TAG, "Invalid frame header");
    return false;
  }

  if (payload_size == 0 || payload_size > this->max_frame_size_) {
    ESP_LOGW(TAG, "Invalid frame size: %lu bytes", payload_size);
    return false;
  }

  this->pending_sequence_ = static_cast<uint32_t>(sequence);
  this->expected_payload_size_ = static_cast<size_t>(payload_size);
  this->awaiting_payload_ = true;

  return true;
}

void TamagonionDisplay::commit_frame_(const std::string &payload) {
  size_t line_start = 0;
  size_t line_count = 0;

  while (line_start < payload.size() && line_count < MAX_VISIBLE_LINES) {
    const size_t line_end = payload.find('\n', line_start);
    std::string &line = this->lines_[line_count];

    if (line_end == std::string::npos) {
      line.assign(payload, line_start, std::string::npos);
    } else {
      line.assign(payload, line_start, line_end - line_start);
    }

    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }

    ++line_count;

    if (line_end == std::string::npos) {
      break;
    }
    line_start = line_end + 1;
  }

  this->line_count_ = line_count;
  this->sequence_ = this->pending_sequence_;
  this->has_frame_ = true;
  this->mark_display_dirty_();

  ESP_LOGD(
      TAG,
      "Frame %u received: %u bytes, %u lines",
      this->sequence_,
      static_cast<unsigned>(payload.size()),
      static_cast<unsigned>(this->line_count_));
}

bool TamagonionDisplay::process_rx_() {
  while (true) {
    if (this->session_state_ == SessionState::AWAITING_AUTH) {
      const size_t newline = this->rx_buffer_.find('\n');
      if (newline == std::string::npos) {
        if (this->rx_buffer_.size() > MAX_AUTH_LINE_BYTES) {
          this->close_client_("authentication line too long");
          return false;
        }
        return true;
      }

      std::string line = this->rx_buffer_.substr(0, newline);
      this->rx_buffer_.erase(0, newline + 1);

      if (!this->process_auth_line_(std::move(line))) {
        this->close_client_("authentication failed");
        return false;
      }
      continue;
    }

    if (this->session_state_ != SessionState::AUTHENTICATED) {
      return true;
    }

    if (!this->awaiting_payload_) {
      const size_t newline = this->rx_buffer_.find('\n');
      if (newline == std::string::npos) {
        if (this->rx_buffer_.size() > MAX_HEADER_BYTES) {
          this->close_client_("frame header too long");
          return false;
        }
        return true;
      }

      std::string header = this->rx_buffer_.substr(0, newline);
      this->rx_buffer_.erase(0, newline + 1);

      if (!this->parse_header_(std::move(header))) {
        this->close_client_("invalid frame header");
        return false;
      }
    }

    if (this->rx_buffer_.size() < this->expected_payload_size_) {
      return true;
    }

    const std::string payload = this->rx_buffer_.substr(0, this->expected_payload_size_);
    this->rx_buffer_.erase(0, this->expected_payload_size_);

    this->commit_frame_(payload);
    this->awaiting_payload_ = false;
    this->expected_payload_size_ = 0;
  }
}

void TamagonionDisplay::refresh_network_state_() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  const uint32_t current_ip = static_cast<uint32_t>(WiFi.localIP());
  if (!this->network_state_initialized_ || current_ip != this->last_ip_address_) {
    this->network_state_initialized_ = true;
    this->last_ip_address_ = current_ip;
    this->mark_display_dirty_();
  }
}

void TamagonionDisplay::refresh_display_if_needed_() {
  if (!this->display_dirty_ || this->display_ == nullptr) {
    return;
  }

  this->display_dirty_ = false;
  this->display_->update();
}

void TamagonionDisplay::loop() {
  if (!this->server_) {
    return;
  }

  this->refresh_network_state_();

  uint8_t read_buffer[READ_BUFFER_BYTES];
  while (this->client_.available() > 0) {
    const size_t available = static_cast<size_t>(this->client_.available());
    const size_t bytes_to_read = std::min(available, sizeof(read_buffer));
    const int bytes_read = this->client_.read(read_buffer, bytes_to_read);

    if (bytes_read <= 0) {
      break;
    }

    this->rx_buffer_.append(
        reinterpret_cast<const char *>(read_buffer),
        static_cast<size_t>(bytes_read));

    if (this->rx_buffer_.size() > this->max_frame_size_ + MAX_AUTH_LINE_BYTES) {
      this->close_client_("receive buffer overflow");
      return;
    }

    if (!this->process_rx_()) {
      return;
    }
  }

  if (this->session_state_ == SessionState::AWAITING_AUTH && this->auth_deadline_ != 0 &&
      static_cast<int32_t>(millis() - this->auth_deadline_) >= 0) {
    this->close_client_("authentication timeout");
    return;
  }

  if (this->client_ && !this->client_.connected() && this->client_.available() == 0) {
    this->close_client_(nullptr);
  }

  if (!this->client_ || this->session_state_ == SessionState::DISCONNECTED) {
    this->accept_client_();
  }

  this->refresh_display_if_needed_();
}

}  // namespace tamagonion_display
}  // namespace esphome
