"""Dummy VDA5050 AGV clients for local testing.

Simulates multiple AGVs using vda5050_core's rmf_migration API. Each robot
immediately acknowledges all navigation commands and instant actions.

Usage:
    uv run python dummy_clients.py
    uv run python dummy_clients.py --broker tcp://localhost:1883 --serials 1 2 3

Environment variables (overridden by CLI flags):
    MQTT_BROKER          MQTT broker URI  (default: tcp://localhost:1883)
    VDA5050_MANUFACTURER AGV manufacturer (default: Manufacturer)
    VDA5050_MAP_ID       Map ID           (default: warehouse_floor1)
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from vda5050_core.rmf_migration import (
    Adapter,
    FleetConfiguration,
    RobotCallbacks,
    RobotConfiguration,
    RobotState,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

BROKER_URI   = os.environ.get("MQTT_BROKER",           "tcp://localhost:1883")
MANUFACTURER = os.environ.get("VDA5050_MANUFACTURER",  "Manufacturer")
MAP_ID       = os.environ.get("VDA5050_MAP_ID",        "warehouse_floor1")
DEFAULT_SERIALS = [str(i) for i in range(1, 5)]


def _make_callbacks(manufacturer: str, serial_number: str, handle_ref: list):
    def navigate(destination, execution) -> None:
        LOGGER.info("[%s/%s] navigate → %s pos=%s",
                    manufacturer, serial_number, destination.map, destination.position)
        if handle_ref:
            handle_ref[0].update(
                RobotState(destination.map, destination.position, 1.0),
                execution.identifier,
            )
        execution.finished()

    def stop() -> None:
        LOGGER.info("[%s/%s] stop", manufacturer, serial_number)

    def execute_action(action_type: str, action_id: str, execution) -> None:
        LOGGER.info("[%s/%s] action %s (id=%s)", manufacturer, serial_number, action_type, action_id)
        execution.finished()

    return RobotCallbacks(navigate, stop, execute_action)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dummy VDA5050 AGV clients")
    parser.add_argument("--broker",       default=BROKER_URI,    help="MQTT broker URI")
    parser.add_argument("--manufacturer", default=MANUFACTURER,  help="AGV manufacturer")
    parser.add_argument("--map",          default=MAP_ID,        help="Map ID for initial state")
    parser.add_argument("--serials", nargs="+", default=DEFAULT_SERIALS,
                        metavar="SN", help="Serial numbers to simulate")
    args = parser.parse_args()

    LOGGER.info("Starting %d dummy AGV(s) — manufacturer=%s broker=%s",
                len(args.serials), args.manufacturer, args.broker)

    adapter = Adapter.make()
    fleet_config = FleetConfiguration(
        fleet_name=args.manufacturer,
        broker_uri=args.broker,
        client_id_prefix=f"dummy-{args.manufacturer.lower()}",
    )
    for sn in args.serials:
        fleet_config.add_known_robot_configuration(
            sn,
            RobotConfiguration(manufacturer=args.manufacturer, serial_number=sn),
        )

    fleet = adapter.add_vda5050_fleet(fleet_config)

    for sn in args.serials:
        handle_ref: list = []
        callbacks = _make_callbacks(args.manufacturer, sn, handle_ref)
        handle = fleet.add_robot(
            sn,
            RobotState(args.map, [0.0, 0.0, 0.0], 1.0),
            RobotConfiguration(manufacturer=args.manufacturer, serial_number=sn),
            callbacks,
        )
        handle_ref.append(handle)
        LOGGER.info("Robot %s/%s registered", args.manufacturer, sn)

    adapter.start()
    LOGGER.info("All robots online. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        adapter.stop()
        LOGGER.info("Stopped.")


if __name__ == "__main__":
    main()
