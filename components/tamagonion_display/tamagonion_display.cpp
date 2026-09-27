#include "tamagonion_display.h"

#include <algorithm>
#include <cstdio>
#include <cstring>

#include "esphome/core/log.h"

namespace esphome {
namespace tamagonion_display {

static const char *const TAG = "tamagonion_display";

void TamagonionDisplay::setup() {
  this->server_ = std::make_unique<WiFiServer>(this->port_);
  this->server_->begin();
  this->server_->setNoDelay(true);

  ESP_LOGI(TAG, "TCP server listening on port %u", this->port_);
}

void TamagonionDisplay::dump_config() {
  ESP_LOGCONFIG(TAG, "Tamagonion Display:");
  ESP_LOGCONFIG(TAG, "  TCP port: %u", this->port_);
  ESP_LOGCONFIG(
      TAG,
      "  Maximum frame size: %u bytes",
      static_cast<unsigned>(this->max_frame_size_)
  );
  ESP_LOGCONFIG(TAG, "  HMAC authentication: enabled");
}

void TamagonionDisplay::reset_client_state_() {
  this->rx_buffer_.clear();

  this->authenticated_ = false;
  this->challenge_.clear();
  this->auth_deadline_ = 0;

  this->awaiting_payload_ = false;
  this->expected_payload_size_ = 0;
  this->pending_sequence_ = 0;
}

void TamagonionDisplay::close_client_(const char *reason) {
  ESP_LOGW(TAG, "Closing client: %s", reason);

  if (this->client_) {
    this->client_.stop();
  }

  this->reset_client_state_();
}

std::string TamagonionDisplay::bytes_to_hex_(
    const uint8_t *data,
    size_t len
) {
  static const char HEX_DIGITS[] = "0123456789abcdef";

  std::string out;
  out.resize(len * 2);

  for (size_t i = 0; i < len; i++) {
    out[i * 2] = HEX_DIGITS[(data[i] >> 4) & 0x0F];
    out[i * 2 + 1] = HEX_DIGITS[data[i] & 0x0F];
  }

  return out;
}

bool TamagonionDisplay::constant_time_equal_(
    const std::string &a,
    const std::string &b
) {
  if (a.size() != b.size()) {
    return false;
  }

  uint8_t diff = 0;

  for (size_t i = 0; i < a.size(); i++) {
    diff |= static_cast<uint8_t>(a[i] ^ b[i]);
  }

  return diff == 0;
}

std::string TamagonionDisplay::hmac_sha256_hex_(
    const std::string &key,
    const std::string &data
) {
  br_hmac_key_context key_context;
  br_hmac_context context;

  uint8_t digest[32];

  br_hmac_key_init(
      &key_context,
      &br_sha256_vtable,
      key.data(),
      key.size()
  );

  br_hmac_init(&context, &key_context, 0);

  br_hmac_update(
      &context,
      data.data(),
      data.size()
  );

  br_hmac_out(&context, digest);

  return bytes_to_hex_(digest, sizeof(digest));
}

void TamagonionDisplay::send_line_(const std::string &line) {
  if (!this->client_) {
    return;
  }

  this->client_.write(
      reinterpret_cast<const uint8_t *>(line.data()),
      line.size()
  );

  this->client_.write('\n');
}

void TamagonionDisplay::start_auth_challenge_() {
  uint8_t nonce[16];

  ESP.random(nonce, sizeof(nonce));

  this->challenge_ =
      bytes_to_hex_(nonce, sizeof(nonce));

  this->auth_deadline_ = millis() + 5000;

  this->send_line_(
      "TG1|CHALLENGE|" + this->challenge_
  );

  ESP_LOGI(TAG, "Authentication challenge sent");
}

bool TamagonionDisplay::process_auth_line_(
    std::string line
) {
  if (!line.empty() && line.back() == '\r') {
    line.pop_back();
  }

  static const std::string PREFIX =
      "TG1|AUTH|";

  if (line.rfind(PREFIX, 0) != 0) {
    this->send_line_("TG1|ERR|AUTH_REQUIRED");
    return false;
  }

  const std::string provided =
      line.substr(PREFIX.size());

  const std::string expected =
      this->hmac_sha256_hex_(
          this->pairing_code_,
          this->challenge_
      );

  if (!constant_time_equal_(provided, expected)) {
    this->send_line_("TG1|ERR|AUTH_FAILED");
    ESP_LOGW(TAG, "Authentication failed");
    return false;
  }

  this->authenticated_ = true;
  this->auth_deadline_ = 0;

  this->send_line_("TG1|OK");

  ESP_LOGI(TAG, "Client authenticated");

  return true;
}

bool TamagonionDisplay::parse_header_(
    std::string header
) {
  if (!header.empty() && header.back() == '\r') {
    header.pop_back();
  }

  unsigned long sequence = 0;
  unsigned long payload_size = 0;
  char extra = 0;

  const int fields = std::sscanf(
      header.c_str(),
      "TG1|%lu|%lu%c",
      &sequence,
      &payload_size,
      &extra
  );

  if (fields != 2) {
    ESP_LOGW(TAG, "Invalid frame header");
    return false;
  }

  if (payload_size > this->max_frame_size_) {
    ESP_LOGW(
        TAG,
        "Frame too large: %lu bytes",
        payload_size
    );
    return false;
  }

  this->pending_sequence_ =
      static_cast<uint32_t>(sequence);

  this->expected_payload_size_ =
      static_cast<size_t>(payload_size);

  this->awaiting_payload_ = true;

  return true;
}

void TamagonionDisplay::commit_frame_(
    const std::string &payload
) {
  std::vector<std::string> new_lines;

  size_t start = 0;

  while (start <= payload.size()) {
    const size_t end =
        payload.find('\n', start);

    std::string line;

    if (end == std::string::npos) {
      line = payload.substr(start);
    } else {
      line = payload.substr(
          start,
          end - start
      );
    }

    if (!line.empty() &&
        line.back() == '\r') {
      line.pop_back();
    }

    new_lines.push_back(std::move(line));

    if (end == std::string::npos) {
      break;
    }

    start = end + 1;
  }

  this->lines_ = std::move(new_lines);
  this->sequence_ = this->pending_sequence_;
  this->has_frame_ = true;
  this->frame_dirty_ = true;

  ESP_LOGD(
      TAG,
      "Frame %u received: %u bytes",
      this->sequence_,
      static_cast<unsigned>(payload.size())
  );
}

bool TamagonionDisplay::process_rx_() {
  while (true) {
    if (!this->authenticated_) {
      const size_t newline =
          this->rx_buffer_.find('\n');

      if (newline == std::string::npos) {
        if (this->rx_buffer_.size() > 160) {
          this->close_client_("auth line too long");
          return false;
        }

        return true;
      }

      std::string line =
          this->rx_buffer_.substr(0, newline);

      this->rx_buffer_.erase(
          0,
          newline + 1
      );

      if (!this->process_auth_line_(line)) {
        this->close_client_("authentication failed");
        return false;
      }

      continue;
    }

    if (!this->awaiting_payload_) {
      const size_t newline =
          this->rx_buffer_.find('\n');

      if (newline == std::string::npos) {
        if (this->rx_buffer_.size() > 96) {
          this->close_client_("header too long");
          return false;
        }

        return true;
      }

      std::string header =
          this->rx_buffer_.substr(0, newline);

      this->rx_buffer_.erase(
          0,
          newline + 1
      );

      if (!this->parse_header_(header)) {
        this->close_client_("invalid header");
        return false;
      }
    }

    if (this->rx_buffer_.size() <
        this->expected_payload_size_) {
      return true;
    }

    std::string payload =
        this->rx_buffer_.substr(
            0,
            this->expected_payload_size_
        );

    this->rx_buffer_.erase(
        0,
        this->expected_payload_size_
    );

    this->commit_frame_(payload);

    this->awaiting_payload_ = false;
    this->expected_payload_size_ = 0;
  }
}

void TamagonionDisplay::loop() {
  if (!this->server_) {
    return;
  }

  uint8_t buffer[256];

  while (this->client_.available() > 0) {
    const size_t available =
        static_cast<size_t>(
            this->client_.available()
        );

    const size_t wanted =
        std::min(
            available,
            sizeof(buffer)
        );

    const int read =
        this->client_.read(
            buffer,
            wanted
        );

    if (read <= 0) {
      break;
    }

    this->rx_buffer_.append(
        reinterpret_cast<const char *>(buffer),
        static_cast<size_t>(read)
    );

    if (this->rx_buffer_.size() >
        this->max_frame_size_ + 256) {
      this->close_client_(
          "receive buffer overflow"
      );
      return;
    }

    if (!this->process_rx_()) {
      return;
    }
  }

  // Draw the setup/pairing screen once after Wi-Fi is ready.
  // The display has update_interval: never, so without this the
  // ST7789 would keep showing whatever was on screen before reboot.
  if (!this->boot_screen_drawn_ &&
      this->display_ != nullptr &&
      WiFi.status() == WL_CONNECTED) {
    this->boot_screen_drawn_ = true;
    this->display_->update();
  }

  if (this->frame_dirty_ &&
      this->display_ != nullptr) {
    this->frame_dirty_ = false;
    this->display_->update();
  }

  if (this->client_ &&
      !this->authenticated_ &&
      this->auth_deadline_ != 0 &&
      static_cast<int32_t>(
          millis() - this->auth_deadline_
      ) >= 0) {
    this->close_client_("authentication timeout");
    return;
  }

  if (this->client_ &&
      !this->client_.connected() &&
      this->client_.available() == 0) {
    this->client_.stop();
    this->reset_client_state_();
  }

  if (!this->client_ ||
      !this->client_.connected()) {
    WiFiClient incoming =
        this->server_->accept();

    if (!incoming) {
      return;
    }

    this->client_ = incoming;
    this->client_.setNoDelay(true);

    this->reset_client_state_();

    ESP_LOGI(TAG, "TCP client connected");

    this->start_auth_challenge_();
  }
}

}  // namespace tamagonion_display
}  // namespace esphome
