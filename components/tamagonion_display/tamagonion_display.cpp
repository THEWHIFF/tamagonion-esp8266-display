#include "tamagonion_display.h"

#include <algorithm>
#include <cstdio>

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
  ESP_LOGCONFIG(TAG, "  Maximum frame size: %u bytes",
                static_cast<unsigned>(this->max_frame_size_));
}

void TamagonionDisplay::reset_client_state_() {
  this->rx_buffer_.clear();
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

bool TamagonionDisplay::parse_header_(std::string header) {
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
    ESP_LOGW(TAG, "Frame too large: %lu bytes", payload_size);
    return false;
  }

  this->pending_sequence_ = static_cast<uint32_t>(sequence);
  this->expected_payload_size_ = static_cast<size_t>(payload_size);
  this->awaiting_payload_ = true;

  return true;
}

void TamagonionDisplay::commit_frame_(const std::string &payload) {
  std::vector<std::string> new_lines;

  size_t start = 0;

  while (start <= payload.size()) {
    const size_t end = payload.find('\n', start);

    std::string line;

    if (end == std::string::npos) {
      line = payload.substr(start);
    } else {
      line = payload.substr(start, end - start);
    }

    if (!line.empty() && line.back() == '\r') {
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

  ESP_LOGI(
      TAG,
      "Frame %u received: %u bytes, %u lines",
      this->sequence_,
      static_cast<unsigned>(payload.size()),
      static_cast<unsigned>(this->lines_.size())
  );
}

bool TamagonionDisplay::process_rx_() {
  while (true) {
    if (!this->awaiting_payload_) {
      const size_t newline = this->rx_buffer_.find('\n');

      if (newline == std::string::npos) {
        if (this->rx_buffer_.size() > 96) {
          this->close_client_("header too long");
          return false;
        }

        return true;
      }

      std::string header = this->rx_buffer_.substr(0, newline);
      this->rx_buffer_.erase(0, newline + 1);

      if (!this->parse_header_(header)) {
        this->close_client_("invalid header");
        return false;
      }
    }

    if (this->rx_buffer_.size() < this->expected_payload_size_) {
      return true;
    }

    std::string payload =
        this->rx_buffer_.substr(0, this->expected_payload_size_);

    this->rx_buffer_.erase(0, this->expected_payload_size_);

    this->commit_frame_(payload);

    this->awaiting_payload_ = false;
    this->expected_payload_size_ = 0;
  }
}

void TamagonionDisplay::loop() {
  if (!this->server_) {
    return;
  }

  // Always drain pending TCP data first, even if the remote side
  // has already closed the connection.
  uint8_t buffer[256];

  while (this->client_.available() > 0) {
    const size_t available =
        static_cast<size_t>(this->client_.available());

    const size_t wanted =
        std::min(available, sizeof(buffer));

    const int read =
        this->client_.read(buffer, wanted);

    if (read <= 0) {
      break;
    }

    this->rx_buffer_.append(
        reinterpret_cast<const char *>(buffer),
        static_cast<size_t>(read)
    );

    if (this->rx_buffer_.size() > this->max_frame_size_ + 128) {
      this->close_client_("receive buffer overflow");
      return;
    }

    if (!this->process_rx_()) {
      return;
    }
  }

  // Only discard connection state after all pending bytes have
  // been processed.
  if (this->client_ &&
      !this->client_.connected() &&
      this->client_.available() == 0) {
    ESP_LOGI(TAG, "TCP client disconnected");
    this->client_.stop();
    this->reset_client_state_();
  }

  // Accept a new client when no active connection exists.
  if (!this->client_ || !this->client_.connected()) {
    WiFiClient incoming = this->server_->accept();

    if (!incoming) {
      return;
    }

    this->client_ = incoming;
    this->client_.setNoDelay(true);
    this->reset_client_state_();

    ESP_LOGI(TAG, "TCP client connected");
  }
}

}  // namespace tamagonion_display
}  // namespace esphome
