import base64
import json
import os
import time

from gaiatest import GaiaApps, GaiaApp, GaiaDevice
from marionette import Marionette
from marionette.errors import ScriptTimeoutException, TimeoutException, MarionetteException
from marionette.wait import Wait
from mozdevice import DeviceManagerADB
import moznetwork


class TestRun(object):
    def __init__(self):
        self.test_results = {}
        self.m = None
        self.gaia_apps = None

    def get_marionette(self):
        if not self.m:
            self.m = Marionette()
            self.m.start_session()
            self.gaia_apps = GaiaApps(self.m)
        else:
            tries = 5
            while tries > 0:
                try:
                    self.m.get_url()
                    break
                except MarionetteException as e:
                    if "Please start a session" in str(e):
                        time.sleep(5)
                        self.m = Marionette()
                        self.m.start_session()
                        self.gaia_apps = GaiaApps(self.m)
                        tries -= 1
                    else:
                        import pdb;pdb.set_trace()
                        raise e
            else:
                raise Exception("Marionette is not available, phone seems unresponsive")
        return self.m

    def launch_with_manifest(self, app_name, manifest, attempt):
        self.m.switch_to_frame() 
        result = self.m.execute_async_script("GaiaApps.launchWithManifestURL('%s')" % manifest, script_timeout=180000)
        if result != True:
            entry = "%s_%s" % (app_name, attempt)
            self.test_results[entry] = "failed to launch; there is no app frame"
        app = GaiaApp(frame=result.get('frame'),
                      src=result.get('src'),
                      name=result.get('name'),
                      origin=result.get('origin'))
        if app.frame_id is None:
            entry = "%s_%s" % (app_name, attempt)
            self.test_results[entry] = "failed to launch; there is no app frame"
        self.m.switch_to_frame(app.frame_id)
        return app


    def uninstall_with_manifest(self, app_name, manifest, attempt):
        self.m.switch_to_frame() 
        script = """
        GaiaApps.locateWithManifestURL('%s',
                                       null,
                                       function uninstall(app) {
                                       navigator.mozApps.mgmt.uninstall(app);
                                       marionetteScriptFinished(true);
                                       });
        """
        result = self.m.execute_async_script(script % manifest, script_timeout=60000)
        if result != True:
            entry = "%s_%s" % (app_name, attempt)
            self.test_results[entry] = "Failed to uninstall app with url '%s'" % manifest
        return app
    
    
try:
    test_run = TestRun()
    # Load manifest
    apps = None
    with open('manifest.json', 'r') as f:
        apps = json.loads(f.read())
    test_run.get_marionette()
    test_run.gaia_apps.kill_all()
    
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
    
    
    device = GaiaDevice(test_run.get_marionette())
    device.add_device_manager(dm)
    device.unlock()
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
                print 'installing %s' % app_name
                # go to system app
                test_run.get_marionette().switch_to_frame()
                marketplace_app = test_run.gaia_apps.launch("Browser", switch_to_frame=True, launch_timeout=60000)
                test_run.get_marionette().navigate("https://marketplace.firefox.com")
                try:
                    Wait(test_run.get_marionette(), timeout=120).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
                except (TimeoutException, ScriptTimeoutException) as e:
                    print e
                    entry = "%s_%s" % (app_name, attempt)
                    test_run.test_results[entry] = "timed out waiting for marketplace"
                    continue
                # trigger the install
                if app["is_packaged"]:
                    test_run.get_marionette().execute_script(install_script % (app["app_manifest"], "installPackage"), script_timeout=30000)
                else:
                    test_run.get_marionette().execute_script(install_script % (app["app_manifest"], "install"), script_timeout=30000)
                # go to system app
                test_run.get_marionette().switch_to_frame()
                # click Install
                for el in test_run.get_marionette().find_elements("tag name", "button"):
                    if "Install" == el.text:
                        el.tap()
                # get back into marketplace
                test_run.gaia_apps.switch_to_displayed_app()
                # Did the app get installed?
                result = test_run.get_marionette().execute_script("return window.wrappedJSObject.marionette_install_result") 
                if result != True: 
                    entry = "%s_%s" % (app_name, attempt)
                    test_run.test_results[entry] = "failed to install: %s" % result
                    continue
                # switch to system frame to check if the app *fully* installed
                test_run.get_marionette().switch_to_frame()
                try:
                    Wait(test_run.get_marionette(), timeout=120).until(lambda m:
                                               m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s");' % app["app_manifest"]) != None)
                    Wait(test_run.get_marionette(), timeout=120).until(lambda m:
                                              m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s").manifest != undefined;' % app["app_manifest"]))
                except (TimeoutException, ScriptTimeoutException) as e:
                    print e
                    entry = "%s_%s" % (app_name, attempt)
                    test_run.test_results[entry] = "failed to install: %s" % result
                    continue
                installed = True
            try:
                Wait(test_run.get_marionette(), timeout=120).until(lambda m:
                                       m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s").manifest != undefined;' % app["app_manifest"]))
            except (TimeoutException, ScriptTimeoutException) as e:
                print e
                entry = "%s_%s" % (app_name, attempt)
                test_run.test_results[entry] = "failed to install correctly: %s" % result
                continue
            print 'launching'
            # Wait a few minutes for app to load
            try:
                app_under_test = test_run.launch_with_manifest(app_name, app["app_manifest"], attempt)
                Wait(test_run.get_marionette(), timeout=180).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
            except Exception as e:
                print e
                entry = "%s_%s" % (app_name, attempt)
                test_run.test_results[entry] = "launch timeout"
                test_run.get_marionette().switch_to_frame()
                continue
            print 'launched'
            shot = test_run.get_marionette().screenshot()
            img = base64.b64decode(shot.encode('ascii'))
            if not os.path.exists("screenshots"):
                os.makedirs("screenshots")
            with open("screenshots/%s_%d_%s.png" % (app_name, attempt, int(time.time())), "w") as f:
                f.write(img)
            # go back to system app
            test_run.get_marionette().switch_to_frame()
            test_run.gaia_apps.kill_all()
            if attempt == 2:
                test_run.uninstall_with_manifest(app_name, app["app_manifest"], attempt)
            logcat = dm.getLogcat()
            with open("logcats/%s_%d_%s.log" % (app_name, attempt, int(time.time())), "w") as f:
                for line in logcat:
                    f.write(line)
            entry = "%s_%s" % (app_name, attempt)
            test_run.test_results[entry] = "pass"
except (KeyboardInterrupt, Exception) as e:
    with open("test_results.json", "w") as f:
        f.write(json.dumps(test_run.test_results))
    raise e
