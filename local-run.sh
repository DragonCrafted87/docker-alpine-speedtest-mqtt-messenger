#!/bin/bash

docker build \
        --no-cache \
        --pull \
        --file Dockerfile \
        --tag speed \
        .

MSYS_NO_PATHCONV=1 \
    docker run -it \
        --env TZ=America/Chicago \
        --env MQTT_SERVER="192.168.8.21" \
        --env MQTT_SERVER_PORT="1883" \
        --env PING_COUNT="20" \
        --env PERCENTILE="90" \
        --env DOWNLOAD_ITERATIONS="10,8,6,4,2" \
        --env UPLOAD_ITERATIONS="8,6,4,2" \
        speed
