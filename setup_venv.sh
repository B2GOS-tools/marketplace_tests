#!/bin/bash
which pip
if [ $? != 0 ]; then
  which easy_install
  if [ $? != 0 ]; then
    echo "Neither pip nor easy_install is found in your path"
    echo "Please install pip directly using: http://pip.readthedocs.org/en/latest/installing.html#install-or-upgrade-pip"
    exit 1
  fi
  notify_sudo
  sudo easy_install pip || { echo 'error installing pip' ; exit 1; }
fi

which virtualenv
if [ $? != 0 ]; then
  notify_sudo
  sudo pip install virtualenv || { echo 'error installing virtualenv' ; exit 1; }
fi

if [ ! -d "venv" ]; then
  virtualenv --no-site-packages venv || { echo 'error creating virtualenv' ; exit 1; }
fi

source venv/bin/activate
