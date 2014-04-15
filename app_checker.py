import base64
import json
import os
import time

from gaiatest import GaiaApps, GaiaApp
from marionette import Marionette
from marionette.errors import TimeoutException
from marionette.wait import Wait
from mozdevice import DeviceManagerADB
import moznetwork


failed = {}

def launch_with_manifest(m, app_name, manifest):
    m.switch_to_frame() 
    result = m.execute_async_script("GaiaApps.launchWithManifestURL('%s')" % manifest, script_timeout=180000)
    assert result, "Failed to launch app with url '%s'" % manifest
    app = GaiaApp(frame=result.get('frame'),
                  src=result.get('src'),
                  name=result.get('name'),
                  origin=result.get('origin'))
    if app.frame_id is None:
        failed[app_name] = "failed to launch; there is no app frame"
    m.switch_to_frame(app.frame_id)
    return app


def uninstall_with_manifest(m, app_name, manifest):
    m.switch_to_frame() 
    script = """
    GaiaApps.locateWithManifestURL('%s',
                                   null,
                                   function uninstall(app) {
                                     navigator.mozApps.mgmt.uninstall(app);
                                     marionetteScriptFinished(true);
                                   });
    """
    result = m.execute_async_script(script % manifest, script_timeout=180000)
    if result != True:
        failed[app_name] = "Failed to uninstall app with url '%s'" % manifest
    return app

# Load manifest
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

# Get first logact before tests start
with open("logcats/before_test_%s.log" % int(time.time()), "w") as f:
    for line in logcat:
        f.write(line)

for app in apps:
    # clear logcat
    app_name = app["app_name"]
    dm._checkCmd(["logcat", "-c"])
    # launch (or switch to) marketplace, wait 3 minutes for successful launch
    marketplace_app = gaia_apps.launch("Marketplace", switch_to_frame=True, launch_timeout=180000)
    # trigger the install
    if app["is_packaged"]:
        m.execute_script(install_script % (app["app_manifest"], "installPackage"), script_timeout=30000)
    else:
        m.execute_script(install_script % (app["app_manifest"], "install"), script_timeout=30000)
    # go to system app
    m.switch_to_frame()
    # click Install
    for el in m.find_elements("tag name", "button"):
        if "Install" == el.text:
            el.tap()
    # get back into marketplace
    gaia_apps.switch_to_displayed_app()
    # Did the app get installed?
    result = m.execute_script("return window.wrappedJSObject.marionette_install_result") 
    if result != True: 
        failed[app_name] = "failed to install: %s" % result
        continue
    # launch app, wait 3 minutes
    #app_under_test = gaia_apps.launch(app_name, switch_to_frame=True, launch_timeout=180000)
    app_under_test = launch_with_manifest(m, app_name, app["app_manifest"])
    # Wait at most 3 minutes for app to load
    try:
        Wait(m, timeout=180).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
    except TimeoutException:
        failed[app_name] = "launch timeout"
        continue
    shot = m.screenshot()
    img = base64.b64decode(shot.encode('ascii'))
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    with open("screenshots/%s_%s.png" % (app_name, int(time.time())), "w") as f:
        f.write(img)
    gaia_apps.kill_all()
    uninstall_with_manifest(m, app_name, app["app_manifest"])
    logcat = dm.getLogcat()
    with open("logcats/%s_%s.log" % (app_name, int(time.time())), "w") as f:
        for line in logcat:
            f.write(line)
if failed:
    with open("failures.json", "w") as f:
        f.write(json.dumps(failed))
