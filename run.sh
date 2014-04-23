#!/bin/bash
source setup_venv.sh
pip install gaiatest 
python run_app_checker.py $@
deactivate
