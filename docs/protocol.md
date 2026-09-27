# Tamagonion Display Protocol

This document describes the TCP protocol used between Tamagonion and the ESP8266 display client.

The display is intentionally stateless with respect to Tor. Tamagonion decides which screen to render and sends complete 48x20 UTF-8 frames. The ESP8266 only authenticates the client and displays the most recent complete frame.

## Transport

- TCP
- Default port: `18511`
- One client at a time
- Persistent connections are recommended
- The sender may transmit multiple frames on one connection

## Authentication

Each TCP connection starts with a challenge-response exchange.

### 1. Display challenge

The ESP8266 generates a fresh 16-byte random nonce, converts it to lowercase hexadecimal, and sends:

```text
TG1|CHALLENGE|<32-hex-character challenge>\n
```

Example:

```text
TG1|CHALLENGE|4bc61288d7be2f4836b3ad6b92ee49a1
```

### 2. Client response

The client calculates:

```text
HMAC-SHA256(pairing_code, challenge_hex_string)
```

The HMAC output is encoded as lowercase hexadecimal and sent as:

```text
TG1|AUTH|<64-hex-character digest>\n
```

The HMAC input is the ASCII hexadecimal challenge string exactly as received, not the raw 16-byte nonce.

### 3. Authentication result

Success:

```text
TG1|OK\n
```

Failure:

```text
TG1|ERR|AUTH_FAILED\n
```

A client that does not authenticate within five seconds is disconnected.

The pairing code is never transmitted during authentication.

## Frames

After authentication, each frame consists of an ASCII header followed immediately by a UTF-8 payload:

```text
TG1|<sequence>|<payload_length>\n
<payload bytes>
```

Fields:

- `sequence`: unsigned decimal frame sequence number
- `payload_length`: payload size in bytes, not characters
- payload: UTF-8 text representing the rendered Tamagonion viewport

Example header:

```text
TG1|42|979
```

If the header declares 979 bytes, exactly 979 payload bytes must follow before the frame is considered complete.

## Viewport

The current display viewport is:

- 48 columns
- 20 rows
- UTF-8 text

Box-drawing and block characters are supported by the display font.

The protocol itself does not contain a screen name. Home, Status, Hints, or any future Tamagonion view is simply another complete rendered frame. This keeps the ESP8266 independent from Tamagonion application logic.

## Frame replacement

The display updates only after a complete frame has been received. If several complete frames arrive while the LCD is busy refreshing, the most recent parsed frame is the one that matters for the next display update.

## Disconnect behavior

When the authenticated client disconnects, the current frame is invalidated and the display returns to its connection/pairing screen.

A reconnect always starts with a new authentication challenge.

## Security properties

The protocol provides client authentication and replay resistance through a fresh random challenge on every connection.

It does not encrypt frame contents. Anyone able to passively observe traffic on the local network may read the display payload.

The display service is intended for a trusted LAN and should not be exposed directly to the public Internet.
