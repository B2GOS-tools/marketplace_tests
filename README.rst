==================
Marketplace Tester
==================

A tool to sequentially install, launch, screenshot, and uninstall marketplace apps. Logcats are also stored for each app.

How to Run the Tests
====================

Run::

    source run.sh

And it will generate a virtual environment with the needed packages, and will run the tests.

Results
=======

Screenshots will be stored in a generated screenshots/ folder, with names: <appname>_<timestamp>.png

Logcats will be stored in a generated logcats/ folder, with names: <appname>_<timestamp>.log. These logcats are the snippets of logs generated during the duration of the particular app's installation, testing and uninstallation. 

There will also be a file named before_test_<timestamp>.log, which will hold all the logcat information before any tests were run.
