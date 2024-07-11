#!/bin/bash
gunicorn server:app --workers 1 --bind 0.0.0.0:8000