import base64
import json
from optparse import OptionParser
import os
import socket
import sys
import time

from gaiatest import GaiaApps, GaiaApp, GaiaDevice
from marionette import Marionette
from marionette.errors import ScriptTimeoutException, TimeoutException, MarionetteException, JavascriptException
from marionette.wait import Wait
from mozdevice import DeviceManagerADB
import moznetwork


#TODO refactor this god object
class TestRun(object):
    def __init__(self, adb="adb", serial=None):
        self.test_results = {}
        self.m = None
        self.gaia_apps = None
        self.screenshot_path = None
        self.logcat_path = None
        self.app_name = None
        self.attempt = None
        self.num_apps = None
        self.device = None
        self.serial = serial
        if self.serial:
            self.dm = DeviceManagerADB(adbPath=adb, deviceSerial=serial)
        else:
            self.dm = DeviceManagerADB(adbPath=adb)

    def reset_marionette(self):
        try:
            self.m.delete_session()
        except Exception:
            pass
        self.m = None
        self.get_marionette()

    def get_marionette(self):
        if not self.m:
            self.m = Marionette()
            self.m.start_session()
            self.device = GaiaDevice(self.m)
            self.device.add_device_manager(self.dm)
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
                        self.device = GaiaDevice(self.m)
                        self.device.add_device_manager(self.dm)
                        self.gaia_apps = GaiaApps(self.m)
                        tries -= 1
                    else:
                        raise e
            else:
                print "Can't connect to marionette, rebooting" 
                self.restart_device()
        return self.m

    def add_result(self, passed=False, status=None, uninstalled_failure=False):
        values = {}
        if status:
            if not passed:
                values["status"] = "FAILED: %s" % status
            else:
                values["status"] = "PASS"
        if self.screenshot_path:
            values["screenshot"] = self.screenshot_path
        if self.logcat_path:
            values["logcat"] = self.logcat_path
        if uninstalled_failure:
            values["uninstalled_failure"] = uninstalled_failure
        entry = "%s_%s" % (self.app_name, self.attempt)
        self.test_results[entry] = values

    def launch_with_manifest(self, manifest):
        self.m.switch_to_frame() 
        result = self.m.execute_async_script("GaiaApps.launchWithManifestURL('%s')" % manifest, script_timeout=30000)
        if result == False:
            raise Exception("launch timed out")
        app = GaiaApp(frame=result.get('frame'),
                      src=result.get('src'),
                      name=result.get('name'),
                      origin=result.get('origin'))
        if app.frame_id is None:
            raise Exception("failed to launch; there is no app frame")
        self.m.switch_to_frame(app.frame_id)
        return app


    def uninstall_with_manifest(self, manifest):
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
            self.add_result(status="Failed to uninstall app with url '%s'" % manifest)
        return app

    def restart_device(self, restart_tries=0):
        print "rebooting"
        # TODO restarting b2g doesn't seem to work... reboot then
        while restart_tries < 3:
            restart_tries += 1
            self.dm.reboot(wait=True)
            print "forwarding"
            dm_tries = 0
            while dm_tries < 20:
                if self.dm.forward("tcp:2828", "tcp:2828") == 0:
                    break
                dm_tries += 1
                time.sleep(3)
            else:
                print "couldn't forward port in time, rebooting"
                continue
            self.m = Marionette()
            if not self.m.wait_for_port(180):
                print "couldn't contact marionette in time, rebooting"
                continue
            time.sleep(1)
            self.m.start_session()
            try:
                Wait(self.m, timeout=240).until(lambda m: m.find_element("id", "lockscreen-container").is_displayed())
                # It retuns a little early
                time.sleep(2)
                self.device = GaiaDevice(self.m)
                self.device.add_device_manager(self.dm)
                self.device.unlock()
                self.gaia_apps = GaiaApps(self.m)
            except (MarionetteException, IOError, socket.error) as e:
                print "got exception: %s, going to retry" % e
                try:
                    self.m.delete_session()
                except:
                    # at least attempt to clear the session if possible
                    pass
                continue
            break
        else:
            raise Exception("Couldn't restart the device in time, even after 3 tries")

    def readystate_wait(self, app):
        try:
            Wait(self.get_marionette(), timeout=30).until(lambda m: m.execute_script("return window.document.readyState;") == "complete")
        except ScriptTimeoutException as e:
            return False
        return True  

    def record_icons(self):
        self.device.touch_home_button()
        icons = self.m.find_elements("class name", "icon")
        self.num_apps = len(icons)

    def check_if_app_installed(self, timeout=180):
        # TODO: Find a better way to do this than checking homescreen
        # I hope there is one...
        self.device.touch_home_button()
        icons = self.m.find_elements("class name", "icon")
        start = time.time()
        end = start + 180
        found_icon = None
        claims_its_loaded = 0 # this is used in case 'loading' isn't applied immediately to the icon
        while time.time() < end:
            if not found_icon:
                icons = self.m.find_elements("class name", "icon")
                # We can't do set comparison b/c references change
                if len(icons) > self.num_apps:
                    for icon in icons:
                        if "loading" in icon.get_attribute("innerHTML"):
                            found_icon = icon
                            break 
                    else:
                        claims_its_loaded += 1
                        if claims_its_loaded == 3:
                            return True
            else:
                if "loading" not in found_icon.get_attribute("innerHTML"):
                    return True
            time.sleep(2)
            return False


def cli():
    parser = OptionParser(usage="usage: %prog [options] manifestFile")
    parser.add_option("--device", dest="device", default=None,
                       help="Device id of the device you want to test against. "\
                       "If not passed in, it will assume there is only one " \
                       "device plugged in and will use that one.")
    parser.add_option("--adb-path", dest="adb_path", default="adb",
                      help="path to adb executable. If not passed, we assume "\
                      "that 'adb' is on the path")
    parser.add_option("--range", dest="chunk",
                       help="Runs the given index range of the manifest")
    (options, args) = parser.parse_args()
    manifest_file = "manifest.json"
    if args:
        manifest_file = args[0]
    
    
    test_run = TestRun(adb=options.adb_path, serial=options.device)
    # Load manifest
    apps = None
    with open(manifest_file, 'r') as f:
        apps = json.loads(f.read())

    # use given chunk if applicable
    if options.chunk:
        apps = apps[int(options.chunk[0]):int(options.chunk[-1])]
        test_run.test_results["chunk"] = options.chunk

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
    if not os.path.exists("logcats"):
        os.makedirs("logcats")
    logcat = test_run.dm.getLogcat()
    
    
    test_run.device.unlock()
    # Get first logact before tests start
    with open("logcats/before_test_%s.log" % int(time.time()), "w") as f:
        for line in logcat:
            f.write(line)
    
    start_time = time.time()
    for app in apps:
        # clear logcat
        app_name = app["app_name"]
        test_run.app_name = app_name
        installed = False
        # Checkpoint
        with open("test_results.json", "w") as f:
            f.write(json.dumps(test_run.test_results))
        for attempt in [1, 2]:
            test_run.attempt = attempt
            exception_occurred = False
            test_run.screenshot_path = None
            test_run.logcat_path = "logcats/%s_%d_%s.log" % (app_name, attempt, int(time.time()))
            print "testing: %s %s" % (app_name, attempt)
            try:
                test_run.record_icons()
                test_run.dm._checkCmd(["logcat", "-c"])
                # launch (or switch to) marketplace, wait 3 minutes for successful launch
                if not installed:
                    print 'installing %s' % app_name
                    # go to system app
                    test_run.get_marionette().switch_to_frame()
                    marketplace_app = test_run.gaia_apps.launch("Browser", switch_to_frame=True, launch_timeout=60000)
                    test_run.get_marionette().navigate("https://marketplace.firefox.com")
                    if not test_run.readystate_wait("marketplace"):
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
                        test_run.add_result(status="failed to install, didn't get onsuccess: %s" % result)
                        continue
                    # switch to system frame to check if the app *fully* installed
                    test_run.get_marionette().switch_to_frame()
                    try:
                        Wait(test_run.get_marionette(), timeout=120).until(lambda m:
                                                   m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s");' % app["app_manifest"]) != None)
                        Wait(test_run.get_marionette(), timeout=120).until(lambda m:
                                                  m.execute_script('return window.wrappedJSObject.Applications.getByManifestURL("%s").manifest != undefined;' % app["app_manifest"]))
                        # DOMRequest onsuccess for install returns too quickly, and so does the Applications manager
                        if not test_run.check_if_app_installed():
                            raise TimeoutException("Didn't install the app in time")
                    except (TimeoutException, ScriptTimeoutException) as e:
                        test_run.add_result(status="failed to install: %s" % e)
                        print 'failed to install'
                        continue
                    installed = True
                print 'launching' 
                try:
                    # ensure we're in system frame
                    test_run.get_marionette().switch_to_frame()
                    app_under_test = test_run.launch_with_manifest(app["app_manifest"])
                except Exception as e:
                    test_run.add_result(status=str(e))
                    continue
                if not test_run.readystate_wait(app_name):
                    test_run.add_result(status="timed out waiting for %s" % app)
                    continue
                print 'launched'
                shot = test_run.get_marionette().screenshot()
                img = base64.b64decode(shot.encode('ascii'))
                if not os.path.exists("screenshots"):
                    os.makedirs("screenshots")
                test_run.screenshot_path = "screenshots/%s_%d_%s.png" % (app_name, attempt, int(time.time()))
                with open(test_run.screenshot_path, "w") as f:
                    f.write(img)
                test_run.device.touch_home_button()
                # go back to system app
                test_run.get_marionette().switch_to_frame()
                test_run.gaia_apps.kill_all()
                test_run.add_result(passed=True)
            except (TimeoutException, JavascriptException, socket.error, IOError) as e:
                #NOTE: JavascriptExceptions are added because if we get in a weird
                # state in gaia, we get errors when we execute JS, so we reboot
                exception_occurred = True
                test_run.add_result(status="Connection timeout, restarting phone")
                print "connection error occurred, restarting %s" % e
                test_run.restart_device()
                continue
            except ScriptTimeoutException as e:
                exception_occurred = True
                test_run.add_result(status="Script timeout: %s running next test" % e)
                print "Script timeout: %s running next test" % e
                continue
            except MarionetteException as e:
                exception_occurred = True
                test_run.add_result(status="Script error: %s running next test" % e)
                print "Marionette script error: %s running next test" % e
                print 'restarting'
                # if we can't get a session here, we reset
                test_run.restart_device()
                continue
            except (KeyboardInterrupt, Exception) as e:
                exception_occurred = True
                entry = "%s_%s" % (app_name, attempt)
                if not test_run.test_results.has_key(entry):
                    test_run.add_result(status="Unknown failure: %s" % e)
                with open("test_results.json", "w") as f:
                    # explain why we failed
                    test_run.test_results["Suite failure when running %s" % app_name] = str(e)
                    test_run.test_results["Total Time"] = time.time() - start_time
                    f.write(json.dumps(test_run.test_results))
                raise e
            finally:
                if (attempt == 2) or exception_occurred:
                    try:
                        test_run.uninstall_with_manifest(app["app_manifest"])
                        installed = False
                    except Exception as e:
                        entry = "%s_%s" % (app_name, attempt)
                        if not test_run.test_results.has_key(entry):
                            test_run.test_results(status="Failed to uninstall", uninstalled_failure=str(e))
                        else:
                            test_run.test_results[entry]["Uninstalled"] = "FAILED: %s" % str(e)
                logcat = test_run.dm.getLogcat()
                with open(test_run.logcat_path, "w") as f:
                    for line in logcat:
                        f.write(line)
    with open("test_results.json", "w") as f:
        test_run.test_results["Total Time"] = time.time() - start_time
        f.write(json.dumps(test_run.test_results))

if __name__ == "__main__":
    cli()
