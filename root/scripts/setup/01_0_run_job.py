#!/usr/bin/python3
# -*- coding: utf-8 -*-

from json import dumps as dump_to_json
from math import ceil as ceiling

# System Imports
from os import getenv
from pathlib import PurePath
from statistics import fmean as mean
from statistics import median
from time import sleep
from time import time

from paho.mqtt.client import MQTTv311
from paho.mqtt.publish import single as send_mqtt_message
from ping3 import ping

# Local Imports
from python_logger import create_logger

# 3rd Party
from requests import Session
from requests import get as requests_get
from requests import post as requests_post
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError

LOGGER = create_logger(PurePath(__file__).stem)
SLEEP_BETWEEN_MEASURMENTS = 5
MEASUREMENT_SIZES = [
    100000,
    1000000,
    10000000,
    25000000,
    50000000,
    100000000,
    250000000,
    500000000,
    1000000000,
]


CLOUDFLARE_ADAPTER = HTTPAdapter(max_retries=3)

SESSION = Session()
SESSION.mount("https://speed.cloudflare.com", CLOUDFLARE_ADAPTER)


def download(bytes):
    try:
        start_time = time()
        _ = requests_get(f"https://speed.cloudflare.com/__down?bytes={bytes}")
        finish_time = time()

        sleep(SLEEP_BETWEEN_MEASURMENTS)

        duration = finish_time - start_time
        measurement = (bytes / duration) / 100000
    except ConnectionError:
        measurement = 0

    LOGGER.info(measurement)
    return measurement


def upload(bytes):
    try:
        upload_data = bytearray(bytes)
        start_time = time()
        _ = requests_post(f"https://speed.cloudflare.com/__up", data=upload_data)
        finish_time = time()

        sleep(SLEEP_BETWEEN_MEASURMENTS)

        duration = finish_time - start_time
        measurement = (bytes / duration) / 100000
    except ConnectionError:
        measurement = 0

    LOGGER.info(measurement)
    return measurement


def calculate_percentile(data, percentile):
    sorted_data = sorted(data)
    n = len(sorted_data)
    p = n * percentile / 100
    if p.is_integer():
        return_value = sorted_data[int(p)]
    else:
        p = int(p) - 1
        return_value = (sorted_data[p] + sorted_data[p + 1]) / 2
    return return_value


def main():
    mqtt_server = getenv("MQTT_SERVER", "localhost")
    mqtt_server_port = int(getenv("MQTT_SERVER_PORT", "1883"))
    mqtt_username = getenv("MQTT_USERNAME", None)
    mqtt_password = getenv("MQTT_PASSWORD", None)

    ping_count = int(getenv("PING_COUNT", "20"))
    percentile = int(getenv("PERCENTILE", "90"))

    download_iterations = list(
        map(int, getenv("DOWNLOAD_ITERATIONS", "10,8,6,4,2").split(","))
    )
    upload_iterations = list(
        map(int, getenv("UPLOAD_ITERATIONS", "8,6,4,2").split(","))
    )

    ping_measurements = []
    for _ in range(ping_count):
        value = None
        while not value:
            value = ping("cloudflare.com", unit="ms")
        ping_measurements.append(value)

    median_ping = median(ping_measurements)
    ping_jitter = mean(
        [
            abs(ping_measurements[index] - ping_measurements[index - 1])
            for index in range(1, len(ping_measurements))
        ]
    )

    download_measurements = []
    upload_measurements = []
    for index in range(len(download_iterations)):
        download_size = MEASUREMENT_SIZES[index]
        iterations = download_iterations[index]
        for _ in range(iterations):
            download_measurements.append(download(download_size))

    for index in range(len(upload_iterations)):
        upload_size = MEASUREMENT_SIZES[index]
        iterations = upload_iterations[index]
        for _ in range(iterations):
            upload_measurements.append(upload(upload_size))

    LOGGER.info(f"Ping {median_ping}")
    LOGGER.info(f"Jitter {ping_jitter}")

    download_percentile = calculate_percentile(download_measurements, percentile)
    LOGGER.info(f"Download Percentile {download_percentile}")

    upload_percentile = calculate_percentile(upload_measurements, percentile)
    LOGGER.info(f"Upload Percentile {upload_percentile}")

    auth_dict = None
    if mqtt_username and mqtt_password:
        auth_dict = {"username": mqtt_username, "password": mqtt_password}

    json_payload = dump_to_json(
        {
            "median_ping": median_ping,
            "ping_jitter": ping_jitter,
            "download_mbps": download_percentile,
            "upload_mbps": upload_percentile,
        }
    )
    LOGGER.info(f"MQTT payload {json_payload}")

    send_mqtt_message(
        "speedtest",
        payload=json_payload,
        qos=0,
        retain=False,
        hostname=mqtt_server,
        port=mqtt_server_port,
        client_id="",
        keepalive=60,
        will=None,
        auth=auth_dict,
        tls=None,
        protocol=MQTTv311,
        transport="tcp",
    )


if __name__ == "__main__":
    main()
