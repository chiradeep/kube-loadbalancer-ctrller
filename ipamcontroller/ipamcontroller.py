# Copyright 2018 Citrix Systems
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from kubernetes import client, config, watch
import ipaddress
import json
import os
import signal


GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"


class CitrixIpamController(object):

    def __init__(self, namespaces=[u'default']):
        vip_range = os.environ.get('VIP_RANGE')
        if vip_range is None:
            print("No VIP_RANGE env variable found, assuming 172.31.254.0/24")
            vip_range = '["172.31.254.0/24"]'
        print("VIP range configured as: %s" % vip_range)
        self.vip_cidrs = json.loads(vip_range)
        try:
            config.load_kube_config()
        except:
            config.load_incluster_config()
        self.namespaces = namespaces
        self.unallocated_vips = set()
        self.init_unallocated_vips(self.vip_cidrs)
        self._stop = False
        self.handlers = {'ADDED': self.handle_added,
                         'MODIFIED': self.handle_modified,
                         'DELETED': self.handle_deleted,
                         'ERROR': self.handle_error}
        self.watch = watch.Watch()
        signal.signal(signal.SIGINT, self.signal_handler)

    def start(self):
        self.watch_for_ipam_create_request(self.namespaces, self.ipam_handler)

    def stop(self):
        self._stop = True
        self.watch.stop()

    def watch_for_ipam_create_request(self, namespaces, ipam_handler):
        crds = client.CustomObjectsApi()
        resource_version = ""
        stream = self.watch.stream(crds.list_cluster_custom_object,
                                   GROUP, VERSION, PLURAL,
                                   resource_version=resource_version)
        for event in stream:
            if event['object']['metadata']['namespace'] in namespaces:
                print("Event: %s %s %s/%s" % (event['type'], event['object']['kind'],
                                              event['object']['metadata']['namespace'], event['object']['metadata']['name']))
                ipam_handler(event['type'], event['object'])
                if self._stop:
                    break

    def update_ipam_crd(self, namespace, name, ip):
        crds = client.CustomObjectsApi()
        body = {'spec': {'ipaddress': ip}}
        print("IPAM request: Patching VIP CRD %s/%s with ip %s" %
              (namespace, name, ip))
        crds.patch_namespaced_custom_object(
            GROUP, VERSION, namespace, PLURAL, name, body)

    def handle_added(self, ipam_obj):
        service = ipam_obj['spec']['service']
        vip = ipam_obj['spec'].get('ipaddress')
        namespace = ipam_obj['metadata']['namespace']
        name = service
        if vip is None:
            print("handle_added: VIP is none, will allocate a new one")
            if len(self.unallocated_vips) > 0:
                ip = self.unallocated_vips.pop()
                print("handle_added: Allocated VIP %s" % str(ip))
                self.update_ipam_crd(namespace, name, str(ip))
        else:
            print("handle_added: VIP is already allocated, no action")

    def handle_modified(self, ipam_obj):
        print("handle_modified: calling handle_added")
        self.handle_added(ipam_obj)

    def handle_deleted(self, ipam_obj):
        vip = ipam_obj['spec'].get('ipaddress')
        print("handle_deleted: adding back vip %s to pool" % vip)
        self.unallocated_vips.add(vip)

    def handle_error(self, ipam_obj):
        print("handle_error: not sure what to do")
        # TODO

    def ipam_handler(self, operation,  ipam_obj):
        service = ipam_obj['spec']['service']
        vip = ipam_obj['spec'].get('ipaddress')
        print("IPAM request: service: %s vip: %s" % (service, vip))
        self.handlers[operation](ipam_obj)

    def init_unallocated_vips(self, cidrs):
        for cidr in cidrs:
            for ip in ipaddress.ip_network(cidr).hosts():
                self.unallocated_vips.add(ip)
        # TODO: iterate over existing Vip CRD objects and delete them from the set of vips

    def signal_handler(self, signum, stack):
        if signum == signal.SIGINT:
            print("Received signal %d, exiting" % signum)
            self.stop()


if __name__ == '__main__':
    ctrller = CitrixIpamController(namespaces=[u'default'])
    ctrller.start()
