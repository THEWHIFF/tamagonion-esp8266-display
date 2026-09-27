import socket

HOST = "192.168.18.237"
PORT = 18511
SEQUENCE = 3

lines = [
"┌──────────────────────────────────────────────┐",
"│Relay nickname: exitgpjkoely                  │",
"│Uptime: 0d 02h 58m 19s                        │",
"│Connections (N/L/Co/F/Cl): 0/0/7/0/0          │",
"│Download (Cur/Avg/Tot): 353B / 201B / 2MB     │",
"│Upload (Cur/Avg/Tot): 1KB / 389B / 4MB        │",
"│Version: 0.4.9.11                             │",
"│                                              │",
"│                              ░░░░░░░░        │",
"│                             ░╔══════╗░   █▄  │",
"│             ▌▌              ░║ EXIT ║░ █████ │",
"│             ▓▓▀             ░╚══════╝░   █▀  │",
"│         ▄▄▄▀▀▀▀▄▄▄           ░░░░░░░░        │",
"│        █   ─  ─    ▄▄▄▄▄                     │",
"│       █    ▄  ▄   █  █  █                    │",
"│      █     ▀  ▀  █  ▀█▀  █  ╓───┬───╖╤═══╕   │",
"│ ____ █      ──    █  █  █   ║---│---║╧╤══╧╤  │",
"││oV2o│█             ▀▀▀▀▀    ║---│---║╒╧══╤╧  │",
"│╘════╛ █▄▄▄▄▄▄▄▄▄▄▄▄█        ╙───┴───╜╘═══╧   │",
"└───────────────────────|Home│Status│Hints│Quit┘",
]

assert len(lines) == 20
assert all(len(line) == 48 for line in lines)

payload = "\n".join(lines).encode("utf-8")
header = f"TG1|{SEQUENCE}|{len(payload)}\n".encode("ascii")

print("Header:", header)
print("Characters:", sum(len(x) for x in lines))
print("Payload:", len(payload), "UTF-8 bytes")

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    sock.sendall(header + payload)

print("Tamagonion frame sent.")
