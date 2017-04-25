#!/bin/sh
cd "$(dirname "$0")"
python3.4 post_download.py "$1" | tee -a "post_download.sh.log"
