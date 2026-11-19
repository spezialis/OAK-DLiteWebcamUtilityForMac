#!/usr/bin/env python3
"""Headless background service: turns an OAK-D Lite into a UVC webcam whenever it is plugged in.

The OAK-D Lite has no flash, so after every plug-in the host must boot it and
upload a UVC pipeline. This loop does exactly that:

    wait for an unbooted device -> boot it in UVC mode -> hold the connection
    -> device closes (unplug / crash) -> back to waiting

A device that is already booted (by us or by another DepthAI client such as
TouchDesigner) is not listed by getAllAvailableDevices(), so this service never
steals a device that is in use.

Only depends on depthai, so it can run from a minimal venv under launchd.
Intended to be run by the LaunchAgent installed with launchd/install.sh.
"""

import argparse
import logging
import logging.handlers
import os
import signal
import sys
import time
from pathlib import Path

import depthai as dai

LOG_DIR = Path.home() / "Library" / "Logs" / "OAKWebcam"
POLL_INTERVAL_S = 2.0
HEALTH_INTERVAL_S = 1.0
RETRY_BACKOFF_MAX_S = 30.0

log = logging.getLogger("oakwebcam")
_stop = False


def _handle_signal(signum, _frame):
    global _stop
    log.info("Received signal %s, shutting down", signum)
    _stop = True


def setup_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "oakwebcam.log", maxBytes=1_000_000, backupCount=3
    )
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    if sys.stderr.isatty():
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        log.addHandler(stream)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def build_pipeline(width: int, height: int, fps: int) -> dai.Pipeline:
    pipeline = dai.Pipeline()
    cam = pipeline.createColorCamera()
    cam.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam.setInterleaved(False)
    cam.setFps(fps)
    if (width, height) != (1920, 1080):
        cam.setVideoSize(width, height)

    uvc = pipeline.createUVC()
    cam.video.link(uvc.input)
    return pipeline


def build_config(width: int, height: int) -> dai.Device.Config:
    config = dai.Device.Config()
    config.board.uvc = dai.BoardConfig.UVC(width, height)
    config.board.uvc.frameType = dai.ImgFrame.Type.NV12
    return config


def find_unbooted_device():
    """Return DeviceInfo of a device waiting to be booted, or None."""
    for info in dai.Device.getAllAvailableDevices():
        if info.state in (dai.XLinkDeviceState.X_LINK_UNBOOTED,
                          dai.XLinkDeviceState.X_LINK_BOOTLOADER):
            return info
    return None


def run_device(info, args) -> None:
    """Boot the device in UVC mode and block until it closes or we are told to stop."""
    log.info("Booting %s (%s) in UVC mode %dx%d@%d",
             info.getMxId(), info.name, args.width, args.height, args.fps)
    pipeline = build_pipeline(args.width, args.height, args.fps)
    config = build_config(args.width, args.height)
    with dai.Device(config, info) as device:
        device.startPipeline(pipeline)
        log.info("UVC camera running (device %s, USB %s)",
                 device.getMxId(), device.getUsbSpeed().name)
        while not _stop and not device.isClosed():
            time.sleep(HEALTH_INTERVAL_S)
    if _stop:
        log.info("Stopped UVC camera")
    else:
        log.info("Device connection closed (unplugged?)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info("OAK webcam service started (depthai %s, python %s)",
             dai.__version__, sys.version.split()[0])

    backoff = POLL_INTERVAL_S
    waiting_logged = False
    while not _stop:
        try:
            info = find_unbooted_device()
        except Exception:
            log.exception("Device discovery failed")
            info = None

        if info is None:
            if not waiting_logged:
                log.info("Waiting for OAK device...")
                waiting_logged = True
            time.sleep(POLL_INTERVAL_S)
            continue

        waiting_logged = False
        try:
            run_device(info, args)
            backoff = POLL_INTERVAL_S
        except Exception:
            log.exception("UVC session failed; retrying in %.0fs", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, RETRY_BACKOFF_MAX_S)

    log.info("OAK webcam service exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
