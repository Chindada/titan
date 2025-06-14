#!/bin/sh

pip3 install -U \
  --no-warn-script-location \
  --no-cache-dir \
  mypy-protobuf \
  pylint-protobuf \
  black \
  mypy \
  pylint

mypy --install-types --non-interactive --check-untyped-defs --config-file=./mypy.ini ./src
