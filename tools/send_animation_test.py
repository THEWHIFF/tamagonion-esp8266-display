import socket
import time

HOST = "192.168.18.237"
PORT = 18511
FPS = 5
DURATION = 20

WIDTH = 48
HEIGHT = 20

def border():
    return "┌" + "─" * (WIDTH - 2) + "┐"

def bottom():
    return "└" + "─" * (WIDTH - 2) + "┘"

def row(text=""):
    return "│" + text[:WIDTH - 2].ljust(WIDTH - 2) + "│"

def make_frame(frame):
    if frame == 0:
        stinky = [
            "              ▌▌",
            "              ▓▓▀",
            "          ▄▄▄▀▀▀▀▄▄▄",
            "         █   ─  ─   █",
            "        █    ▄  ▄    █",
            "       █     ▀  ▀     █",
            "       █      ──      █",
            "        █▄▄▄▄▄▄▄▄▄▄▄▄█",
        ]
    else:
        stinky = [
            "              ▌▌",
            "              ▓▓▀",
            "          ▄▄▄▀▀▀▀▄▄▄",
            "         █   ─  ─   █",
            "        █    ▀  ▀    █",
            "       █     ▄  ▄     █",
            "       █      ──      █",
            "        █▄▄▄▄▄▄▄▄▄▄▄▄█",
        ]

    lines = [
        border(),
        row(" Tamagonion animation test"),
        row(" TCP persistent connection"),
        row(),
        row(stinky[0]),
        row(stinky[1]),
        row(stinky[2]),
        row(stinky[3]),
        row(stinky[4]),
        row(stinky[5]),
        row(stinky[6]),
        row(stinky[7]),
        row(),
        row(" Relay: ONLINE"),
        row(" Refresh target: 5 FPS"),
        row(),
        row(f" Animation frame: {frame}"),
        row(),
        row(" Watch for flicker / tearing / lag"),
        bottom(),
    ]

    assert len(lines) == HEIGHT
    assert all(len(x) == WIDTH for x in lines)

    return "\n".join(lines).encode("utf-8")

seq = 100
delay = 1.0 / FPS
end = time.monotonic() + DURATION

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    print(f"Connected. Sending at {FPS} FPS for {DURATION}s")

    frame = 0
    next_frame = time.monotonic()

    while time.monotonic() < end:
        payload = make_frame(frame)
        header = f"TG1|{seq}|{len(payload)}\n".encode("ascii")

        sock.sendall(header + payload)

        seq += 1
        frame ^= 1

        next_frame += delay
        remaining = next_frame - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

print("Animation test finished.")
