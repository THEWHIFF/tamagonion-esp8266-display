import socket

HOST = "192.168.18.237"
PORT = 18511
WIDTH = 48

def border():
    return "+" + "-" * (WIDTH - 2) + "+"

def row(text=""):
    return "|" + text[:WIDTH - 2].ljust(WIDTH - 2) + "|"

lines = [
    border(),
    row("          TAMAGONION TCP TEST"),
    row(),
    row("              /\\_/\\"),
    row("             ( o.o )"),
    row("              > ^ <"),
    row(),
    row(" TCP: CONNECTED"),
    row(" PROTOCOL: TG1"),
    row(),
    row(" ESP8266"),
    row(" ST7789 240x240"),
    row(),
    row(" FULL FRAME RECEIVED"),
    row(),
    row(" SEQUENCE: 2"),
    row(),
    row(" 48 columns x 20 rows"),
    row(),
    border(),
]

assert len(lines) == 20
assert all(len(line) == 48 for line in lines)

payload = "\n".join(lines).encode("utf-8")
header = f"TG1|2|{len(payload)}\n".encode("ascii")

print(f"Header: {header!r}")
print(f"Payload: {len(payload)} bytes")

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    sock.sendall(header + payload)

print("Frame sent and socket closed immediately.")
