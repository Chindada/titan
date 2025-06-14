#!/bin/sh

pip3 freeze >requirements.txt &&
  pip3 uninstall -y -r requirements.txt
rm -rf requirements.txt

pip3 install --upgrade pip
pip3 install -U \
  --no-warn-script-location \
  --no-cache-dir \
  shioaji[speed]

pip3 freeze >requirements.txt
