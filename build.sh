#!/usr/bin/env bash

docker build \
    --platform linux/amd64,linux/arm64 \
    --tag ghcr.io/dragoncrafted87/alpine-speedtest-mqtt-publisher \
    .
