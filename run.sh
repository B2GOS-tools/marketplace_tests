#!/bin/bash
if [ ! -d "venv" ]; then
  virtualenv --no-site-packages venv || { echo 'error creating virtualenv' ; exit 1; }
fi

source venv/bin/activate
pip install gaiatest 
python app_checker.py
deactivate
