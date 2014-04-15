import base64
import json
import os
import time

from gaiatest import GaiaApps
from marionette import Marionette
from marionette.wait import Wait
from mozdevice import DeviceManagerADB
from mozhttpd import MozHttpd
import moznetwork

apps = None
with open('manifest', 'r') as f:
    apps = json.loads(f.read())
# get marionette
m = Marionette()
m.start_session()
gaia_apps = GaiaApps(m)
gaia_apps.kill_all()

install_script = """
var installUrl = '%s';
var request = window.navigator.mozApps.%s(installUrl);
request.onsuccess = function () {
  window.wrappedJSObject.marionette_install_result = true;
};
request.onerror = function () {
 window.wrappedJSObject.marionette_install_result = this.error.name;
};
"""
# TODO: assumes adb is on path
dm = DeviceManagerADB()
if not os.path.exists("logcats"):
    os.makedirs("logcats")
logcat = dm.getLogcat()
with open("logcats/before_test.logcat", "w") as f:
    for line in logcat:
        f.write(line)
for app_name, path in apps.iteritems():
    # clear logcat
    dm._checkCmd(["logcat", "-c"])
    # launch (or switch to) marketplace, wait 3 minutes for successful launch
    marketplace_app = gaia_apps.launch("Marketplace", switch_to_frame=True, launch_timeout=180000)
    # trigger the install
    if path.endswith(".webapp"):
        m.execute_script(install_script % (path, "install"), script_timeout=30000)
    elif path.endswith(".zip"):
        m.execute_script(install_script % (path, "installPackage"), script_timeout=30000)
    else:
        raise Exception("Can't install from given path: %s" % path)
    # go to system app
    m.switch_to_frame()
    # click Install
    for el in m.find_elements("tag name", "button"):
        if "Install" == el.text:
            el.tap()
    # get back into marketplace
    gaia_apps.switch_to_displayed_app()
    # Did the app get installed?
    assert m.execute_script("return window.wrappedJSObject.marionette_install_result")
    # launch app, wait 3 minutes
    app_under_test = gaia_apps.launch(app_name, switch_to_frame=True, launch_timeout=180000)
    # Wait at most 3 minutes for app to load
    Wait(m, timeout=180).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
    shot = m.screenshot()
    img = base64.b64decode(shot.encode('ascii'))
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    with open("screenshots/%s.png" % app_name, "w") as f:
        f.write(img)
    gaia_apps.kill_all()
    gaia_apps.uninstall(app_name)
    logcat = dm.getLogcat()
    with open("logcats/%s.logcat" % app_name, "w") as f:
        for line in logcat:
            f.write(line)
