#!/bin/bash
kill -9 $(lsof -t -i:8000)
cd /home/pi/lapsilapse
. .venv/bin.activate
gunicorn server:app --workers 1 --bind 0.0.0.0:8000