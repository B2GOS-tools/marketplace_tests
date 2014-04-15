==================
Marketplace Tester
==================

A tool to sequentially install, launch, screenshot, and uninstall marketplace apps. Logcats are also stored for each app.

How to Run the Tests
====================

Run::

    source run.sh

And it will generate a virtual environment with the needed packages, and will run the tests.

For each app, it will install it once, and uninstall it once. After installation it will attempt to do do a sequence of "launch app, screenshot, kill app" twice.

Results
=======

Screenshots will be stored in a generated screenshots/ folder, with names: <appname>_<attempt_number>_<timestamp>.png

Logcats will be stored in a generated logcats/ folder, with names: <appname>_<attempt_number>_<timestamp>.log. These logcats are the snippets of logs generated during the duration of the particular app's installation, testing and uninstallation. 

There will also be a file named before_test_<timestamp>.log, which will hold all the logcat information before any tests were run.

If there were failures, a file named failed.json will be in the current working directory, and it will contain a map of appname to cause of failure
