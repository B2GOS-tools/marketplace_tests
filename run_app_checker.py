from __future__ import division
import math
import json
from optparse import OptionParser
import os
import shutil
import subprocess
import sys
import time

import mozdevice


def cli():
    parser = OptionParser(usage="usage: %prog [options] [deviceID] " \
                                "[deviceID] ...",
                          description="[deviceID] are the ids of " \
                          "the devices to run against. If you do not pass " \
                          "any deviceIDs, we assume there is only one device " \
                          "attached, and we will run tests against that.")
    parser.add_option("--adb-path", dest="adb_path", default="adb",
                      help="path to adb executable. If not passed, we assume "\
                      "that 'adb' is on the path")
    parser.add_option("--manifest",
                       default="manifest.json",
                       dest="manifest",
                       help="path to manifest " \
                       "file. By default, we use manifest.json")
    (options, args) = parser.parse_args()
    manifest_file = options.manifest
    if not os.path.isfile(manifest_file):
        print "%s does not exist. Please pass in a valid manifest.json file " \
        "using the --manifest option" % manifest_file
        sys.exit(1)
    dm = None
    devices = args
    # if specific or multiple devices
    for device in devices:
        proc = subprocess.Popen(["%s -s %s get-state" % (options.adb_path, device)],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               shell=True)
        proc.wait()
        state = proc.stdout.read()
        if "device" not in state:
            print "%s is in this state: %s, and cannot be used" % (device, state)
            sys.exit(1)

        #batch the manifest
        manifest = json.loads(open(manifest_file, "r").read())
        chunk_size = int(math.ceil(len(manifest) / len(devices)))
        print len(manifest)
        print "chunk size: %d" % chunk_size

        def chunks(l, n):
            """ Yield successive n-sized chunks from l.
            """
            for i in xrange(0, len(l), n):
                yield (i,i+n)

        chunker = chunks(manifest, chunk_size)
        procs = []
        chunks = []

        try:
            for device in devices:
                chunk_tuple = chunker.next()
                print "Device: %s is assigned range: %s" % (device, chunk_tuple)
                chunk = "%d,%d" % (chunk_tuple[0], chunk_tuple[1])
                print chunk
                cmd = ["python", "app_checker.py", "--range", chunk, \
                       "--device", device, manifest_file]
                proc = subprocess.Popen(cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                print "Running tests and logging to file: run_log_%s.log" % chunk_tuple[0]
                chunks.append(chunk_tuple[0])
                procs.append(proc)
                time.sleep(1) # stagger in case we have port acquisition problems
            for proc in procs:
                proc.wait()
        except (KeyboardInterrupt, Exception) as e:
            for proc in procs:
                proc.terminate()
            time.sleep(1)
            test_results = {}
            print chunks
            for chunk in chunks:
                def get_file(path):
                    with open(path, "r") as f:
                        contents = f.read()
                        if contents:
                            results = json.loads(contents)
                            test_results.update(results)
                        else:
                            return False
                    shutil.rmtree(path)
                    return True
                try:
                    if not get_file("test_results_%s.json" % chunk):
                        get_file("test_results_%s.json.tmp" % chunk)
                except (IOError, OSError):
                    continue
            with open("test_results.json", "w") as f:
                f.write(json.dumps(test_results))
            raise e

    # if running against the only device plugged in
    if not devices:
        proc = subprocess.Popen(["%s -d get-state" % options.adb_path],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               shell=True)

        proc.wait()
        state = proc.stdout.read()
        if "device" not in state:
            print "Device is in this state: %s, and cannot be used" % (state)
            sys.exit(1)

        #run the tests
        print "Running all the tests on one device"
        proc = subprocess.Popen(["python app_checker.py %s" % manifest_file],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               shell=True)
        proc.wait()


if __name__ == "__main__":
    cli()
