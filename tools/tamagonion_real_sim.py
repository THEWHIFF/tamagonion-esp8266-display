#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import tamagonion.draw as tdraw
from tamagonion.app_data import AppData, VersionStatus
from tamagonion.draw import Paper, Screen
from stem.version import Version

WIDTH = 48
HEIGHT = 20
DEFAULT_HOST = "192.168.18.237"
DEFAULT_PORT = 18511
DEFAULT_FPS = 1.0
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class BufferPen:
    canvas = [[" "] * WIDTH for _ in range(HEIGHT)]

    @classmethod
    def clear(cls) -> None:
        cls.canvas = [[" "] * WIDTH for _ in range(HEIGHT)]

    @classmethod
    def draw(cls, image: str, pos_y: int, pos_x: int, transparent: bool = False) -> None:
        image = strip_ansi(str(image))
        for dy, line in enumerate(image.splitlines()):
            y = pos_y + dy
            if not (0 <= y < HEIGHT):
                continue
            for dx, ch in enumerate(line):
                x = pos_x + dx
                if x >= WIDTH:
                    break
                if x < 0:
                    continue
                if transparent and ch == " ":
                    continue
                cls.canvas[y][x] = ch

    @classmethod
    def erase_in_frame(cls, frame: str):
        lines = strip_ansi(str(frame)).splitlines()
        if not lines:
            return cls
        height = min(len(lines), HEIGHT)
        width = min(max(len(line) for line in lines), WIDTH)
        for y in range(1, max(1, height - 1)):
            for x in range(1, max(1, width - 1)):
                cls.canvas[y][x] = " "
        return cls

    @classmethod
    def text(cls) -> str:
        return "\n".join("".join(row) for row in cls.canvas)

    @classmethod
    def erase_screen(cls):
        cls.clear()
        return cls

    @classmethod
    def hide_cursor(cls):
        return cls

    @classmethod
    def show_cursor(cls):
        return cls

    @classmethod
    def move_home(cls):
        return cls

    @classmethod
    def move_to_beginning_of_line(cls):
        return cls

    @classmethod
    def move_up(cls, n: int = 1):
        return cls

    @classmethod
    def move_down(cls, n: int = 1):
        return cls

    @classmethod
    def move_left(cls, n: int = 1):
        return cls

    @classmethod
    def move_right(cls, n: int = 1):
        return cls


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    flags: tuple[str, ...]
    bootstrap: int = 100
    network: bool = True
    enough_dir: bool = True
    reachable: bool = True
    descriptor_ok: bool = True
    version_status: str = "recommended"
    force_sleep: bool = False
    bootstrap_phase: str = "Done"


HEALTHY = ("Valid", "Running", "Stable", "Fast")

SCENARIOS = [
    Scenario("healthy", "Healthy / normal Stinky", HEALTHY),
    Scenario("exit", "Exit sign", HEALTHY + ("Exit",)),
    Scenario("guard", "Guard shield", HEALTHY + ("Guard",)),
    Scenario("hsdir", "HSDir books", HEALTHY + ("HSDir",)),
    Scenario("v2dir", "V2Dir cassette", HEALTHY + ("V2Dir",)),
    Scenario("all_objects", "Exit + Guard + HSDir + V2Dir", HEALTHY + ("Exit", "Guard", "HSDir", "V2Dir")),
    Scenario("badexit", "Broken BadExit sign", HEALTHY + ("BadExit", "Guard", "HSDir", "V2Dir")),
    Scenario("bootstrap", "Egg / relay bootstrapping", HEALTHY, bootstrap=37, bootstrap_phase="Loading_descriptors"),
    Scenario("blackout", "Network down / lights out", HEALTHY, network=False),
    Scenario("confused", "Not enough directory info", HEALTHY, enough_dir=False),
    Scenario("unreachable", "ORPort unreachable / looking away", HEALTHY, reachable=False),
    Scenario("embarrassed", "Server descriptor rejected", HEALTHY, descriptor_ok=False),
    Scenario("sad", "Missing Running flag / sad", ("Valid", "Stable", "Fast")),
    Scenario("noed", "NoEdConsensus / sad", HEALTHY + ("NoEdConsensus",)),
    Scenario("old", "StaleDesc / old", HEALTHY + ("StaleDesc",)),
    Scenario("hurt", "Obsolete Tor version / hurt", HEALTHY, version_status="obsolete"),
    Scenario("unstable", "Missing Stable / glitchy", ("Valid", "Running", "Fast")),
    Scenario("bored", "MiddleOnly / bored", HEALTHY + ("MiddleOnly",)),
    Scenario("slow", "Missing Fast / slow animation", ("Valid", "Running", "Stable")),
    Scenario("asleep", "Bedtime / asleep", HEALTHY, force_sleep=True),
]
SCENARIO_MAP = {s.key: s for s in SCENARIOS}


class FakeController:
    def __init__(self) -> None:
        self.scenario = SCENARIOS[0]
        self.started = time.monotonic() - (2 * 86400 + 3 * 3600 + 17 * 60)

    def set_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def get_network_status(self):
        return SimpleNamespace(flags=list(self.scenario.flags))

    def get_uptime(self) -> float:
        return max(1.0, time.monotonic() - self.started)

    def get_version(self):
        return Version("0.4.9.11")

    def get_conf(self, key: str):
        return {
            "Nickname": "SIM-Stinky",
            "ORPort": "9001",
            "DirPort": "9030",
        }.get(key)

    def get_info(self, key: str):
        s = self.scenario
        elapsed = int(time.monotonic())
        down = 350 + (elapsed % 7) * 31
        up = 900 + (elapsed % 5) * 73
        uptime = int(self.get_uptime())
        total_down = 75_000_000 + uptime * down
        total_up = 210_000_000 + uptime * up

        values = {
            "status/version/current": s.version_status,
            "status/version/recommended": "0.4.9.11",
            "bw-event-cache": f"{down},{up}",
            "traffic/read": str(total_down),
            "traffic/written": str(total_up),
            "network-liveness": "up" if s.network else "down",
            "status/bootstrap-phase": (
                f'NOTICE BOOTSTRAP PROGRESS={s.bootstrap} TAG=sim SUMMARY="{s.bootstrap_phase}"'
            ),
            "status/enough-dir-info": "1" if s.enough_dir else "0",
            "status/good-server-descriptor": "1" if s.descriptor_ok else "0",
            "status/reachability-succeeded/or": "1" if s.reachable else "0",
            "orconn-status": (
                "nodeA CONNECTED\n"
                "nodeB CONNECTED\n"
                "nodeC CONNECTED\n"
                "nodeD NEW\n"
                "nodeE CLOSED"
            ),
        }
        if key not in values:
            raise KeyError(f"FakeController: unsupported get_info({key!r})")
        return values[key]

    def close(self) -> None:
        pass


class FakeRelayManager:
    def __init__(self) -> None:
        self.controller = FakeController()


def load_pairing_code(path: Path) -> str:
    text = path.read_text()
    match = re.search(
        r'^tamagonion_pairing_code:\s*["\']?([^"\'\s#]+)',
        text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"tamagonion_pairing_code introuvable dans {path}")
    return match.group(1)


def recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Connexion fermee par l'ESP")
        data.extend(chunk)
    return data.rstrip(b"\r\n").decode("ascii")


def authenticate(sock: socket.socket, pairing_code: str) -> None:
    line = recv_line(sock)
    prefix = "TG1|CHALLENGE|"
    if not line.startswith(prefix):
        raise RuntimeError(f"Challenge inattendu: {line!r}")

    challenge = line[len(prefix):]
    digest = hmac.new(
        pairing_code.encode("utf-8"),
        challenge.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    sock.sendall(f"TG1|AUTH|{digest}\n".encode("ascii"))
    response = recv_line(sock)
    if response != "TG1|OK":
        raise RuntimeError(f"Authentification refusee: {response}")


def send_frame(sock: socket.socket, seq: int, frame: str) -> None:
    payload = frame.encode("utf-8")
    header = f"TG1|{seq}|{len(payload)}\n".encode("ascii")
    sock.sendall(header + payload)


def render(paper: Paper, app_data: AppData, controller: FakeController, scenario: Scenario, screen: Screen, hint_scroll: int = 0) -> str:
    controller.set_scenario(scenario)
    app_data.update()
    app_data.version_status = VersionStatus(scenario.version_status)

    tdraw.SLEEP_HOURS = set(range(24)) if scenario.force_sleep else set()

    paper.active_screen = screen
    paper.hints_scroll_index = hint_scroll

    BufferPen.clear()
    paper.draw()
    return BufferPen.text()


def print_scenarios() -> None:
    for scenario in SCENARIOS:
        print(f"{scenario.key:12} {scenario.label}")


def auto_demo(sock: socket.socket, paper: Paper, app_data: AppData, controller: FakeController, fps: float, seconds_per_state: float, seq: int) -> int:
    interval = 1.0 / fps

    for index, scenario in enumerate(SCENARIOS, start=1):
        print(f"[{index:02}/{len(SCENARIOS)}] HOME  {scenario.key:12} - {scenario.label}")
        deadline = time.monotonic() + seconds_per_state
        next_tick = time.monotonic()
        while time.monotonic() < deadline:
            frame = render(paper, app_data, controller, scenario, Screen.HOME)
            send_frame(sock, seq, frame)
            seq += 1
            next_tick += interval
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)

    status_scenario = SCENARIO_MAP["all_objects"]
    print("[VIEW] STATUS - healthy relay with all room flags")
    deadline = time.monotonic() + 5
    next_tick = time.monotonic()
    while time.monotonic() < deadline:
        frame = render(paper, app_data, controller, status_scenario, Screen.STATUS)
        send_frame(sock, seq, frame)
        seq += 1
        next_tick += interval
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    hint_scenario = SCENARIO_MAP["unstable"]
    print("[VIEW] HINTS - Missing Stable flag, scrolling")
    deadline = time.monotonic() + 8
    next_tick = time.monotonic()
    hint_scroll = 0
    while time.monotonic() < deadline:
        frame = render(paper, app_data, controller, hint_scenario, Screen.HINT, hint_scroll)
        send_frame(sock, seq, frame)
        seq += 1
        hint_scroll += 1
        next_tick += interval
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    return seq


def single_state(sock: socket.socket, paper: Paper, app_data: AppData, controller: FakeController, scenario: Scenario, screen: Screen, fps: float, seq: int) -> None:
    interval = 1.0 / fps
    next_tick = time.monotonic()
    hint_scroll = 0
    print(f"State: {scenario.key} - {scenario.label} | screen={screen.name.lower()} | Ctrl+C pour quitter")
    while True:
        frame = render(paper, app_data, controller, scenario, screen, hint_scroll)
        send_frame(sock, seq, frame)
        seq += 1
        if screen is Screen.HINT:
            hint_scroll += 1
        next_tick += interval
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulateur Tamagonion reel vers l'ecran ESP8266")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS, help="1.0 reproduit la cadence actuelle de Tamagonion")
    parser.add_argument("--seconds", type=float, default=4.0, help="Duree de chaque etat en mode auto")
    parser.add_argument("--state", choices=sorted(SCENARIO_MAP), help="Boucler sur un seul etat")
    parser.add_argument("--screen", choices=("home", "status", "hint"), default="home")
    parser.add_argument("--list", action="store_true", help="Lister tous les etats simules")
    parser.add_argument("--secrets", type=Path, default=Path(__file__).resolve().parents[1] / "secrets.yaml")
    args = parser.parse_args()

    if args.list:
        print_scenarios()
        return

    if args.fps <= 0 or args.fps > 5:
        raise SystemExit("--fps doit etre > 0 et <= 5")

    pairing_code = load_pairing_code(args.secrets)

    # Make the real Tamagonion renderer write into our 48x20 memory buffer.
    tdraw.Pen = BufferPen

    manager = FakeRelayManager()
    app_data = AppData(manager)
    paper = Paper(app_data)

    screen_map = {
        "home": Screen.HOME,
        "status": Screen.STATUS,
        "hint": Screen.HINT,
    }

    print(f"Connexion a {args.host}:{args.port}...")
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.settimeout(5)
        authenticate(sock, pairing_code)
        print("HMAC OK. Simulateur connecte.")

        try:
            if args.state:
                single_state(
                    sock,
                    paper,
                    app_data,
                    manager.controller,
                    SCENARIO_MAP[args.state],
                    screen_map[args.screen],
                    args.fps,
                    1,
                )
            else:
                auto_demo(
                    sock,
                    paper,
                    app_data,
                    manager.controller,
                    args.fps,
                    args.seconds,
                    1,
                )
                print("Demo complete. Relance la commande pour recommencer.")
        except KeyboardInterrupt:
            print("\nArret du simulateur.")


if __name__ == "__main__":
    main()
