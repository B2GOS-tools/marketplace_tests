import base64
import json
import os
import time

from gaiatest import GaiaApps
from marionette import Marionette
from marionette.wait import Wait
from mozhttpd import MozHttpd
import moznetwork


def start_httpd(need_external_ip):
    host = "127.0.0.1"
    if need_external_ip:
        host = moznetwork.get_ip()
    docroot = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'apps')
    if not os.path.isdir(docroot):
        raise Exception("Server root %s is not a valid path" % docroot)
    print docroot
    httpd = MozHttpd(host=host,
                          port=0,
                          docroot=docroot)
    httpd.start()
    return (httpd, host)

httpd, host = start_httpd(True)
baseurl = 'http://%s:%d/' % (host, httpd.httpd.server_port)
print baseurl
apps = None
with open('manifest', 'r') as f:
    apps = json.loads(f.read())
# get marionette
m = Marionette()
m.start_session()
gaia_apps = GaiaApps(m)
gaia_apps.kill_all()

install_script = """
var installUrl = '%s%s';
var request = window.navigator.mozApps.%s(installUrl);
request.onsuccess = function () {
  window.wrappedJSObject.marionette_install_result = true;
};
request.onerror = function () {
 window.wrappedJSObject.marionette_install_result = this.error.name;
};
"""
for app_name, path in apps.iteritems():
    # launch (or switch to) marketplace, wait 3 minutes for successful launch
    marketplace_app = gaia_apps.launch("Marketplace", switch_to_frame=True, launch_timeout=180000)
    # trigger the install
    print "%s%s" % (baseurl, path)
    #TODO: remove
    baseurl = ''
    if path.endswith(".webapp"):
        m.execute_script(install_script % (baseurl, path, "install"), script_timeout=30000)
    elif path.endswith(".zip"):
        m.execute_script(install_script % (baseurl, path, "installPackage"), script_timeout=30000)
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
    with open("%s_screenshot.png" % app_name, "w") as f:
        f.write(img)
    gaia_apps.kill_all()
    gaia_apps.uninstall(app_name)
    import pdb;pdb.set_trace()
    # TODO: get logcats

httpd.stop()
