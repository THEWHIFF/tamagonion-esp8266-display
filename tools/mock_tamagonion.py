import hashlib
import hmac
import re
import socket
import time
from pathlib import Path

HOST = "192.168.18.237"
PORT = 18511
FPS = 5

WIDTH = 48
HEIGHT = 20


def load_pairing_code():
    text = Path("secrets.yaml").read_text()
    m = re.search(
        r'^tamagonion_pairing_code:\s*["\']?([^"\']+)["\']?\s*$',
        text,
        re.MULTILINE,
    )
    if not m:
        raise RuntimeError("tamagonion_pairing_code introuvable")
    return m.group(1).strip()


def recv_line(sock):
    data = bytearray()

    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Connexion fermee par l'ESP")
        data.extend(chunk)

    return data.rstrip(b"\r\n").decode("ascii")


def authenticate(sock, pairing_code):
    line = recv_line(sock)
    print("ESP:", line)

    prefix = "TG1|CHALLENGE|"
    if not line.startswith(prefix):
        raise RuntimeError("Challenge invalide")

    challenge = line[len(prefix):]

    digest = hmac.new(
        pairing_code.encode(),
        challenge.encode(),
        hashlib.sha256,
    ).hexdigest()

    sock.sendall(
        f"TG1|AUTH|{digest}\n".encode("ascii")
    )

    response = recv_line(sock)
    print("ESP:", response)

    if response != "TG1|OK":
        raise RuntimeError("Authentification refusee")


def fit(text=""):
    return text[:WIDTH].ljust(WIDTH)


def frame_home(anim=0):
    if anim == 0:
        pet = [
            "                 /\\_/\\\\",
            "                ( o.o )",
            "                 > ^ <",
        ]
    else:
        pet = [
            "                 /\\_/\\\\",
            "                ( -.- )",
            "                 > ^ <",
        ]

    lines = [
        "+----------------------------------------------+",
        "|              TAMAGONION HOME                 |",
        "|                                              |",
        "|  TOR relay: ONLINE                           |",
        "|  Network: OK                                 |",
        "|  Guard: active                               |",
        "|  HSDir: active                               |",
        "|                                              |",
    ]

    lines += [f"|{fit(x)[1:-1]}|" for x in pet]

    lines += [
        "|                                              |",
        "|                                              |",
        "|             Mock client Fedora               |",
        "|                                              |",
        "|                                              |",
        "|                                              |",
        "|                                              |",
        "+----------------------------------------------+",
    ]

    return "\n".join(lines[:HEIGHT])


def frame_status():
    lines = [
        "+----------------------------------------------+",
        "|             TAMAGONION STATUS                |",
        "|                                              |",
        "|  TCP       CONNECTED                         |",
        "|  AUTH      HMAC-SHA256 OK                    |",
        "|  DISPLAY   240x240                           |",
        "|  GRID      48x20                             |",
        "|  FPS       5                                 |",
        "|                                              |",
        "|  This frame simulates Dax's service.         |",
        "|                                              |",
        "|  Disconnect test follows automatically.      |",
    ]

    while len(lines) < 19:
        lines.append("|                                              |")

    lines.append("+----------------------------------------------+")

    return "\n".join(lines)


def send_frame(sock, seq, text):
    payload = text.encode("utf-8")
    header = f"TG1|{seq}|{len(payload)}\n".encode("ascii")
    sock.sendall(header + payload)


def run_session(pairing_code, mode, duration, seq):
    print(f"\nConnexion -> {HOST}:{PORT}")

    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        sock.settimeout(5)

        authenticate(sock, pairing_code)

        start = time.monotonic()
        next_frame = start
        anim = 0

        while time.monotonic() - start < duration:
            if mode == "home":
                text = frame_home(anim)
                anim ^= 1
            else:
                text = frame_status()

            send_frame(sock, seq, text)
            seq += 1

            next_frame += 1 / FPS
            delay = next_frame - time.monotonic()

            if delay > 0:
                time.sleep(delay)

    print("Connexion fermee volontairement.")
    return seq


def main():
    code = load_pairing_code()

    print("Pairing code charge depuis secrets.yaml.")
    print("\n=== PHASE 1 : HOME + animation 5 FPS ===")

    seq = 1
    seq = run_session(code, "home", 10, seq)

    print("\n=== PHASE 2 : deconnexion simulee 3 secondes ===")
    time.sleep(3)

    print("\n=== PHASE 3 : reconnexion + STATUS ===")
    seq = run_session(code, "status", 6, seq)

    print("\nTest termine.")


if __name__ == "__main__":
    main()
