#!/usr/bin/env python3
"""Run the real Tamagonion renderer against an ESP8266 display client.

The simulator imports Tamagonion itself and replaces only the terminal output
backend. Tor controller values are simulated so display states can be tested
without a running Tor relay.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import socket
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, ClassVar

import tamagonion.draw as tamagonion_draw
from stem.version import Version
from tamagonion.app_data import AppData, VersionStatus
from tamagonion.draw import Paper, Screen

DISPLAY_WIDTH = 48
DISPLAY_HEIGHT = 20
DEFAULT_PORT = 18511
DEFAULT_FPS = 1.0
MAX_TEST_FPS = 5.0
EXPECTED_TAMAGONION_VERSION = "1.4.1"
PROTOCOL_PREFIX = "TG1"
ANSI_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove terminal control sequences while preserving Unicode artwork."""
    return ANSI_SEQUENCE.sub("", text)


class BufferPen:
    """Minimal in-memory replacement for Tamagonion's terminal Pen class."""

    canvas: ClassVar[list[list[str]]] = []

    @classmethod
    def clear(cls) -> None:
        cls.canvas = [[" "] * DISPLAY_WIDTH for _ in range(DISPLAY_HEIGHT)]

    @classmethod
    def draw(
        cls,
        image: str,
        pos_y: int,
        pos_x: int,
        transparent: bool = False,
    ) -> None:
        for offset_y, line in enumerate(strip_ansi(str(image)).splitlines()):
            y = pos_y + offset_y
            if not 0 <= y < DISPLAY_HEIGHT:
                continue

            for offset_x, character in enumerate(line):
                x = pos_x + offset_x
                if x >= DISPLAY_WIDTH:
                    break
                if x < 0:
                    continue
                if transparent and character == " ":
                    continue
                cls.canvas[y][x] = character

    @classmethod
    def erase_in_frame(cls, frame: str):
        lines = strip_ansi(str(frame)).splitlines()
        if not lines:
            return cls

        frame_height = min(len(lines), DISPLAY_HEIGHT)
        frame_width = min(max(len(line) for line in lines), DISPLAY_WIDTH)

        for y in range(1, max(1, frame_height - 1)):
            for x in range(1, max(1, frame_width - 1)):
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
    def move_up(cls, _count: int = 1):
        return cls

    @classmethod
    def move_down(cls, _count: int = 1):
        return cls

    @classmethod
    def move_left(cls, _count: int = 1):
        return cls

    @classmethod
    def move_right(cls, _count: int = 1):
        return cls


BufferPen.clear()


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    flags: tuple[str, ...]
    bootstrap: int = 100
    network: bool = True
    enough_directory_info: bool = True
    reachable: bool = True
    descriptor_ok: bool = True
    version_status: str = "recommended"
    force_sleep: bool = False
    bootstrap_phase: str = "Done"


HEALTHY_FLAGS = ("Valid", "Running", "Stable", "Fast")

SCENARIOS = (
    Scenario("healthy", "Healthy / normal Stinky", HEALTHY_FLAGS),
    Scenario("exit", "Exit sign", HEALTHY_FLAGS + ("Exit",)),
    Scenario("guard", "Guard shield", HEALTHY_FLAGS + ("Guard",)),
    Scenario("hsdir", "HSDir books", HEALTHY_FLAGS + ("HSDir",)),
    Scenario("v2dir", "V2Dir cassette", HEALTHY_FLAGS + ("V2Dir",)),
    Scenario(
        "all_objects",
        "Exit + Guard + HSDir + V2Dir",
        HEALTHY_FLAGS + ("Exit", "Guard", "HSDir", "V2Dir"),
    ),
    Scenario(
        "badexit",
        "Broken BadExit sign",
        HEALTHY_FLAGS + ("BadExit", "Guard", "HSDir", "V2Dir"),
    ),
    Scenario(
        "bootstrap",
        "Egg / relay bootstrapping",
        HEALTHY_FLAGS,
        bootstrap=37,
        bootstrap_phase="Loading_descriptors",
    ),
    Scenario("blackout", "Network down / lights out", HEALTHY_FLAGS, network=False),
    Scenario(
        "confused",
        "Not enough directory information",
        HEALTHY_FLAGS,
        enough_directory_info=False,
    ),
    Scenario(
        "unreachable",
        "ORPort unreachable / looking away",
        HEALTHY_FLAGS,
        reachable=False,
    ),
    Scenario(
        "embarrassed",
        "Server descriptor rejected",
        HEALTHY_FLAGS,
        descriptor_ok=False,
    ),
    Scenario("sad", "Missing Running flag / sad", ("Valid", "Stable", "Fast")),
    Scenario("noed", "NoEdConsensus / sad", HEALTHY_FLAGS + ("NoEdConsensus",)),
    Scenario("old", "StaleDesc / old", HEALTHY_FLAGS + ("StaleDesc",)),
    Scenario(
        "hurt",
        "Obsolete Tor version / hurt",
        HEALTHY_FLAGS,
        version_status="obsolete",
    ),
    Scenario("unstable", "Missing Stable / glitchy", ("Valid", "Running", "Fast")),
    Scenario("bored", "MiddleOnly / bored", HEALTHY_FLAGS + ("MiddleOnly",)),
    Scenario("slow", "Missing Fast / slow animation", ("Valid", "Running", "Stable")),
    Scenario("asleep", "Bedtime / asleep", HEALTHY_FLAGS, force_sleep=True),
)

SCENARIO_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


class FakeController:
    """Subset of Stem's controller API consumed by Tamagonion."""

    def __init__(self) -> None:
        self.scenario = SCENARIOS[0]
        self.started_at = time.monotonic() - (2 * 86400 + 3 * 3600 + 17 * 60)

    def set_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def get_network_status(self) -> SimpleNamespace:
        return SimpleNamespace(flags=list(self.scenario.flags))

    def get_uptime(self) -> float:
        return max(1.0, time.monotonic() - self.started_at)

    def get_version(self) -> Version:
        return Version("0.4.9.11")

    def get_conf(self, key: str) -> str | None:
        return {
            "Nickname": "SIM-Stinky",
            "ORPort": "9001",
            "DirPort": "9030",
        }.get(key)

    def get_info(self, key: str) -> str:
        scenario = self.scenario
        elapsed = int(time.monotonic())
        download_rate = 350 + (elapsed % 7) * 31
        upload_rate = 900 + (elapsed % 5) * 73
        uptime = int(self.get_uptime())

        values = {
            "status/version/current": scenario.version_status,
            "status/version/recommended": "0.4.9.11",
            "bw-event-cache": f"{download_rate},{upload_rate}",
            "traffic/read": str(75_000_000 + uptime * download_rate),
            "traffic/written": str(210_000_000 + uptime * upload_rate),
            "network-liveness": "up" if scenario.network else "down",
            "status/bootstrap-phase": (
                f'NOTICE BOOTSTRAP PROGRESS={scenario.bootstrap} '
                f'TAG=sim SUMMARY="{scenario.bootstrap_phase}"'
            ),
            "status/enough-dir-info": "1" if scenario.enough_directory_info else "0",
            "status/good-server-descriptor": "1" if scenario.descriptor_ok else "0",
            "status/reachability-succeeded/or": "1" if scenario.reachable else "0",
            "orconn-status": (
                "nodeA CONNECTED\n"
                "nodeB CONNECTED\n"
                "nodeC CONNECTED\n"
                "nodeD NEW\n"
                "nodeE CLOSED"
            ),
        }

        try:
            return values[key]
        except KeyError as exc:
            raise KeyError(f"FakeController does not implement get_info({key!r})") from exc

    def close(self) -> None:
        """Match the real controller API."""


class FakeRelayManager:
    def __init__(self) -> None:
        self.controller = FakeController()


class DisplayClient:
    """Authenticated client for the Tamagonion display protocol."""

    def __init__(self, host: str, port: int, pairing_code: str) -> None:
        self.host = host
        self.port = port
        self.pairing_code = pairing_code
        self.socket: socket.socket | None = None

    def __enter__(self) -> "DisplayClient":
        self.socket = socket.create_connection((self.host, self.port), timeout=5)
        self.socket.settimeout(5)
        self._authenticate()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def _require_socket(self) -> socket.socket:
        if self.socket is None:
            raise RuntimeError("Display connection is not open")
        return self.socket

    def _recv_line(self, max_bytes: int = 256) -> str:
        connection = self._require_socket()
        data = bytearray()

        while not data.endswith(b"\n"):
            if len(data) >= max_bytes:
                raise RuntimeError("Display returned an oversized protocol line")
            chunk = connection.recv(1)
            if not chunk:
                raise RuntimeError("Display closed the connection")
            data.extend(chunk)

        return data.rstrip(b"\r\n").decode("ascii")

    def _authenticate(self) -> None:
        connection = self._require_socket()
        challenge_line = self._recv_line()
        challenge_prefix = f"{PROTOCOL_PREFIX}|CHALLENGE|"

        if not challenge_line.startswith(challenge_prefix):
            raise RuntimeError(f"Unexpected authentication challenge: {challenge_line!r}")

        challenge = challenge_line[len(challenge_prefix) :]
        digest = hmac.new(
            self.pairing_code.encode("utf-8"),
            challenge.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

        connection.sendall(f"{PROTOCOL_PREFIX}|AUTH|{digest}\n".encode("ascii"))
        response = self._recv_line()

        if response != f"{PROTOCOL_PREFIX}|OK":
            raise RuntimeError(f"Display authentication failed: {response}")

    def send_frame(self, sequence: int, frame: str) -> None:
        validate_frame(frame)
        payload = frame.encode("utf-8")
        header = f"{PROTOCOL_PREFIX}|{sequence}|{len(payload)}\n".encode("ascii")
        self._require_socket().sendall(header + payload)


def load_pairing_code(path: Path) -> str:
    environment_code = os.environ.get("TAMAGONION_DISPLAY_PAIRING_CODE")
    if environment_code:
        return environment_code

    text = path.read_text(encoding="utf-8")
    match = re.search(
        r'^tamagonion_pairing_code:\s*["\']?([^"\'\s#]+)',
        text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"tamagonion_pairing_code was not found in {path}")
    return match.group(1)


def validate_frame(frame: str) -> None:
    lines = frame.splitlines()
    if len(lines) != DISPLAY_HEIGHT:
        raise RuntimeError(
            f"Renderer produced {len(lines)} lines; expected {DISPLAY_HEIGHT}. "
            "Tamagonion's viewport geometry may have changed."
        )

    invalid_widths = [index + 1 for index, line in enumerate(lines) if len(line) != DISPLAY_WIDTH]
    if invalid_widths:
        raise RuntimeError(
            "Renderer produced lines that are not 48 columns wide: "
            + ", ".join(map(str, invalid_widths))
        )


def render_frame(
    paper: Paper,
    app_data: AppData,
    controller: FakeController,
    scenario: Scenario,
    screen: Screen,
    hint_scroll: int = 0,
) -> str:
    controller.set_scenario(scenario)
    app_data.update()
    app_data.version_status = VersionStatus(scenario.version_status)

    tamagonion_draw.SLEEP_HOURS = set(range(24)) if scenario.force_sleep else set()
    paper.active_screen = screen
    paper.hints_scroll_index = hint_scroll

    BufferPen.clear()
    paper.draw()
    frame = BufferPen.text()
    validate_frame(frame)
    return frame


def stream_for_duration(
    client: DisplayClient,
    frame_factory: Callable[[], str],
    duration: float,
    fps: float,
    sequence: int,
) -> int:
    interval = 1.0 / fps
    deadline = time.monotonic() + duration
    next_tick = time.monotonic()

    while time.monotonic() < deadline:
        client.send_frame(sequence, frame_factory())
        sequence += 1
        next_tick += interval

        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    return sequence


def run_auto_demo(
    client: DisplayClient,
    paper: Paper,
    app_data: AppData,
    controller: FakeController,
    fps: float,
    seconds_per_state: float,
) -> None:
    sequence = 1

    for index, scenario in enumerate(SCENARIOS, start=1):
        print(f"[{index:02}/{len(SCENARIOS)}] HOME   {scenario.key:12} - {scenario.label}")
        sequence = stream_for_duration(
            client,
            lambda scenario=scenario: render_frame(
                paper,
                app_data,
                controller,
                scenario,
                Screen.HOME,
            ),
            seconds_per_state,
            fps,
            sequence,
        )

    status_scenario = SCENARIO_BY_KEY["all_objects"]
    print("[VIEW] STATUS - healthy relay with all room flags")
    sequence = stream_for_duration(
        client,
        lambda: render_frame(
            paper,
            app_data,
            controller,
            status_scenario,
            Screen.STATUS,
        ),
        5.0,
        fps,
        sequence,
    )

    hints_scenario = SCENARIO_BY_KEY["unstable"]
    print("[VIEW] HINTS  - Missing Stable flag with scrolling")
    hint_scroll = 0

    def next_hint_frame() -> str:
        nonlocal hint_scroll
        frame = render_frame(
            paper,
            app_data,
            controller,
            hints_scenario,
            Screen.HINT,
            hint_scroll,
        )
        hint_scroll += 1
        return frame

    stream_for_duration(client, next_hint_frame, 8.0, fps, sequence)


def run_single_state(
    client: DisplayClient,
    paper: Paper,
    app_data: AppData,
    controller: FakeController,
    scenario: Scenario,
    screen: Screen,
    fps: float,
) -> None:
    sequence = 1
    hint_scroll = 0
    interval = 1.0 / fps
    next_tick = time.monotonic()

    print(f"State: {scenario.key} - {scenario.label} | screen={screen.name.lower()} | Ctrl+C to stop")

    while True:
        client.send_frame(
            sequence,
            render_frame(
                paper,
                app_data,
                controller,
                scenario,
                screen,
                hint_scroll,
            ),
        )
        sequence += 1

        if screen is Screen.HINT:
            hint_scroll += 1

        next_tick += interval
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def print_scenarios() -> None:
    for scenario in SCENARIOS:
        print(f"{scenario.key:12} {scenario.label}")


def check_tamagonion_version() -> None:
    try:
        installed_version = version("tamagonion")
    except PackageNotFoundError:
        return

    if installed_version != EXPECTED_TAMAGONION_VERSION:
        print(
            f"Warning: simulator was validated with Tamagonion "
            f"{EXPECTED_TAMAGONION_VERSION}; installed version is {installed_version}."
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render real Tamagonion screens on an ESP8266 display using simulated Tor states."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("TAMAGONION_DISPLAY_HOST", "tamagonion-display.local"),
        help="Display hostname or IP address (default: tamagonion-display.local)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_FPS,
        help="Frames per second; 1.0 approximates Tamagonion's normal update cadence",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=4.0,
        help="Seconds per state in the automatic demo",
    )
    parser.add_argument(
        "--state",
        choices=sorted(SCENARIO_BY_KEY),
        help="Loop on one scenario instead of running the automatic demo",
    )
    parser.add_argument(
        "--screen",
        choices=("home", "status", "hint"),
        default="home",
    )
    parser.add_argument("--list", action="store_true", help="List available scenarios and exit")
    parser.add_argument(
        "--secrets",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "secrets.yaml",
        help="Path to secrets.yaml",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    if args.list:
        print_scenarios()
        return

    if not 0 < args.fps <= MAX_TEST_FPS:
        raise SystemExit(f"--fps must be greater than 0 and no more than {MAX_TEST_FPS:g}")
    if args.seconds <= 0:
        raise SystemExit("--seconds must be greater than 0")
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    check_tamagonion_version()
    pairing_code = load_pairing_code(args.secrets)

    original_pen = tamagonion_draw.Pen
    original_sleep_hours = tamagonion_draw.SLEEP_HOURS
    tamagonion_draw.Pen = BufferPen

    manager = FakeRelayManager()
    app_data = AppData(manager)
    paper = Paper(app_data)
    screen_by_name = {
        "home": Screen.HOME,
        "status": Screen.STATUS,
        "hint": Screen.HINT,
    }

    print(f"Connecting to {args.host}:{args.port}...")

    try:
        with DisplayClient(args.host, args.port, pairing_code) as client:
            print("Authenticated. Starting Tamagonion renderer.")

            if args.state:
                run_single_state(
                    client,
                    paper,
                    app_data,
                    manager.controller,
                    SCENARIO_BY_KEY[args.state],
                    screen_by_name[args.screen],
                    args.fps,
                )
            else:
                run_auto_demo(
                    client,
                    paper,
                    app_data,
                    manager.controller,
                    args.fps,
                    args.seconds,
                )
                print("Demo complete.")
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        tamagonion_draw.Pen = original_pen
        tamagonion_draw.SLEEP_HOURS = original_sleep_hours


if __name__ == "__main__":
    main()
