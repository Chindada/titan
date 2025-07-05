#!/bin/sh

set -e

pip3 freeze >requirements.txt
pip3 uninstall -y -r requirements.txt || true
rm -rf requirements.txt

pip3 install --upgrade pip
pip3 install -U --no-warn-script-location --no-cache-dir \
  git+ssh://git@github.com/Chindada/panther.git@v1.0

pip3 install -U --no-warn-script-location --no-cache-dir \
  grpcio \
  grpcio-tools \
  cron-converter \
  APScheduler \
  PyYAML \
  pydantic \
  shioaji[speed] \
  prometheus-client

pip3 freeze >requirements.txt
