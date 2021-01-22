#!/bin/sh

set -e

CURRENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_DIR="$(dirname "$CURRENT_DIR")"

cd $BASE_DIR

docker build --tag ctms-spike-185 --file docker/Dockerfile .
