#!/bin/sh

pip3 freeze >requirements.txt
pip3 uninstall -y -r requirements.txt
rm -rf requirements.txt

pip3 install --upgrade pip
pip3 install -U --no-warn-script-location --no-cache-dir \
  git+ssh://git@github.com/Chindada/panther.git@v1.0

pip3 install -U --no-warn-script-location --no-cache-dir \
  grpcio \
  grpcio-tools \
  PyYAML \
  pydantic \
  shioaji[speed] \
  prometheus-client

pip3 freeze >requirements.txt
