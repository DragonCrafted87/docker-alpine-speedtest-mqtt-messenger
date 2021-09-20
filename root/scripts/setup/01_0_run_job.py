#!/usr/bin/python3
# -*- coding: utf-8 -*-

from datetime import datetime
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
from paho.mqtt.publish import single as single_mqtt_message
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

MQTT_SERVER = getenv("MQTT_SERVER", "localhost")
MQTT_SERVER_PORT = int(getenv("MQTT_SERVER_PORT", "1883"))
MQTT_USERNAME = getenv("MQTT_USERNAME", None)
MQTT_PASSWORD = getenv("MQTT_PASSWORD", None)
AUTH_DICT = None
if MQTT_USERNAME and MQTT_PASSWORD:
    AUTH_DICT = {"username": MQTT_USERNAME, "password": MQTT_PASSWORD}


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

    return measurement


def run_speed_test(iterations_list, operation):
    measurements = []

    for index in range(len(iterations_list)):
        size = MEASUREMENT_SIZES[index]
        iterations = iterations_list[index]
        for _ in range(iterations):
            measurements.append(operation(size))

    return measurements


def calculate_ping():
    ping_count = int(getenv("PING_COUNT", "20"))

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
    return (median_ping, ping_jitter)


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


def calculate_download_percentile(percentile):
    download_iterations = list(
        map(int, getenv("DOWNLOAD_ITERATIONS", "10,8,6,4,2").split(","))
    )

    download_measurements = run_speed_test(download_iterations, download)
    LOGGER.info(f"Download {download_measurements}")

    return calculate_percentile(download_measurements, percentile)


def calculate_upload_percentile(percentile):
    upload_iterations = list(
        map(int, getenv("UPLOAD_ITERATIONS", "8,6,4,2").split(","))
    )

    upload_measurements = run_speed_test(upload_iterations, upload)
    LOGGER.info(f"Upload {upload_measurements}")

    return calculate_percentile(upload_measurements, percentile)


def send_mqtt_message(topic, payload_value):

    LOGGER.info(f"MQTT {topic} payload {payload_value}")

    single_mqtt_message(
        topic,
        payload=payload_value,
        qos=0,
        retain=True,
        hostname=MQTT_SERVER,
        port=MQTT_SERVER_PORT,
        client_id="",
        keepalive=60,
        will=None,
        auth=AUTH_DICT,
        tls=None,
        protocol=MQTTv311,
        transport="tcp",
    )


def main():
    percentile = int(getenv("PERCENTILE", "90"))

    median_ping, ping_jitter = calculate_ping()
    download_percentile = calculate_download_percentile(percentile)
    upload_percentile = calculate_upload_percentile(percentile)

    LOGGER.info(f"Ping {median_ping}")
    LOGGER.info(f"Jitter {ping_jitter}")
    LOGGER.info(f"Download Percentile {download_percentile}")
    LOGGER.info(f"Upload Percentile {upload_percentile}")

    time_string_payload = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_payload = dump_to_json(
        {
            "median_ping": median_ping,
            "ping_jitter": ping_jitter,
            "download_mbps": download_percentile,
            "upload_mbps": upload_percentile,
        }
    )

    send_mqtt_message("speedtest", time_string_payload)
    send_mqtt_message("speedtest/attributes", json_payload)


if __name__ == "__main__":
    main()
