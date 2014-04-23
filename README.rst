==================
Marketplace Tester
==================

A tool to sequentially install, launch, screenshot, and uninstall marketplace apps. Logcats are also stored for each app.

How to Run the Tests
====================

Setup
-----

First, make sure that the lockscreen is enabled on your phone, and that the display timeout is set to 'Never' (in Settings->Display).

You also need to make sure adb is enabled. Go to Settings->Device Information->More Information->Developer and make "Remote Debugging" be "adb and devtools".

Your device must be connected to the internet, either via WiFi or some data plan (since this test uses the live marketplace).

Running the tests
----------------

Run::

    source run.sh

And it will generate a virtual environment with the needed packages, and will run the tests.

For each app, it will install it once, and uninstall it once. After installation it will attempt to do do a sequence of "launch app, screenshot, kill app" twice.

Running the tests on multiple devices
-------------------------------------

*Multiple Devices on Many Machines*:

You can manually batch the tests against a device. First you need to activate the python virtualenv::

  source setup_venv.sh

and then you can start the tests. Given a range of (start_index, end_index), you can start the tests like so::

  python app_checker.py --range=start_index,end_index

and it will start at start_index of the manifest.json file, and end at the end_index of the manifest.json file. You can also specify a manifest by doing::

  python app_checker.py --manifest=/path/to/manifest --range=start_index,end_index

*Multiple Devices on One Machine*:

You can parallelize test running by running them against multiple phones. It will automatically divide the work amongst the devices.
You just need to pass in the phone ids to the run.sh script::

    source run.sh [deviceId] [deviceId] ...

To do this, you need to know the ids of each device. Do::

    adb devices

and you'll get output that looks like the following example::

  List of devices attached
  19761202  device
  M23A232A  device

The device ids are 19761202 and M23A232A. To run the tests, pass in these ids to the run.sh script::

    source run.sh 19761202 M23A232A

Results
=======

Screenshots will be stored in a generated screenshots/ folder, with names: <appname>_<attempt_number>_<timestamp>.png

Logcats will be stored in a generated logcats/ folder, with names: <appname>_<attempt_number>_<timestamp>.log. These logcats are the snippets of logs generated during the duration of the particular app's installation, testing and uninstallation. 

There will also be a file named before_test_<timestamp>.log, which will hold all the logcat information before any tests were run.

If there were failures, a file named failed.json will be in the current working directory, and it will contain a map of appname to cause of failure
