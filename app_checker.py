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

def launch_with_manifest(m, app_name, manifest, attempt):
    m.switch_to_frame() 
    result = m.execute_async_script("GaiaApps.launchWithManifestURL('%s')" % manifest, script_timeout=180000)
    assert result, "Failed to launch app with url '%s'" % manifest
    app = GaiaApp(frame=result.get('frame'),
                  src=result.get('src'),
                  name=result.get('name'),
                  origin=result.get('origin'))
    if app.frame_id is None:
        entry = "%s_%s" % (app_name, attempt)
        failed[entry] = "failed to launch; there is no app frame"
    m.switch_to_frame(app.frame_id)
    return app


def uninstall_with_manifest(m, app_name, manifest, attempt):
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
        entry = "%s_%s" % (app_name, attempt)
        failed[entry] = "Failed to uninstall app with url '%s'" % manifest
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
    installed = False
    for attempt in [1, 2]:
        dm._checkCmd(["logcat", "-c"])
        # launch (or switch to) marketplace, wait 3 minutes for successful launch
        if not installed:
            print 'not installed'
            marketplace_app = gaia_apps.launch("Browser", switch_to_frame=True, launch_timeout=180000)
            m.navigate("https://marketplace.firefox.com")
            try:
                Wait(m, timeout=120).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
            except TimeoutException:
                entry = "%s_%s" % (app_name, attempt)
                failed[entry] = "timed out waiting for marketplace"
                continue
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
                entry = "%s_%s" % (app_name, attempt)
                failed[entry] = "failed to install: %s" % result
                continue
            # switch to system frame to check if the app *fully* installed
            m.switch_to_frame()
            try:
                Wait(m, timeout=120).until(lambda m:
                                           m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s");' % app["app_manifest"]) != None)
                Wait(m, timeout=120).until(lambda m:
                                           m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s").manifest != undefined;' % app["app_manifest"]))
            except TimeoutException:
                entry = "%s_%s" % (app_name, attempt)
                failed[entry] = "failed to install: %s" % result
                continue
            installed = True
        # launch app, wait 3 minutes
        print 'launching'
        app_under_test = launch_with_manifest(m, app_name, app["app_manifest"], attempt)
        # Wait a few minutes for app to load
        try:
            Wait(m, timeout=120).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
        except TimeoutException:
            entry = "%s_%s" % (app_name, attempt)
            failed[entry] = "launch timeout"
            continue
        print 'launched'
        shot = m.screenshot()
        img = base64.b64decode(shot.encode('ascii'))
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
        with open("screenshots/%s_%d_%s.png" % (app_name, attempt, int(time.time())), "w") as f:
            f.write(img)
        # go back to system app
        m.switch_to_frame()
        gaia_apps.kill_all()
        if attempt == 2:
            uninstall_with_manifest(m, app_name, app["app_manifest"], attempt)
        logcat = dm.getLogcat()
        with open("logcats/%s_%d_%s.log" % (app_name, attempt, int(time.time())), "w") as f:
            for line in logcat:
                f.write(line)
if failed:
    with open("failures.json", "w") as f:
        f.write(json.dumps(failed))
