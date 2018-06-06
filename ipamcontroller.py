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
import os
import json
import ipaddress


GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"

class CitrixIpamController(object):

    def __init__(self, namespaces=[u'default']):
        self.vip_cidrs = json.loads(os.environ.get('VIP_RANGE'))
        config.load_kube_config()
        self.namespaces = namespaces
        self.unallocated_vips = set()
        self.init_unallocated_vips(self.vip_cidrs)
        self._stop = False
        self.handlers = {'ADDED': self.handle_added,
                         'MODIFIED': self.handle_modified,
                         'DELETED': self.handle_deleted}

    def start(self):
        self.watch_for_ipam_create_request(self.namespaces, self.ipam_handler)

    def stop(self):
        self._stop = True

    def watch_for_ipam_create_request(self, namespaces, ipam_handler):
        crds = client.CustomObjectsApi()
        resource_version = ""
        stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                      GROUP, VERSION, PLURAL,
                                      resource_version=resource_version)
        for event in stream:
            if event['object']['metadata']['namespace'] in namespaces:
                print("Event: %s %s %s/%s" % (event['type'], event['object']['kind'],
                                              event['object']['metadata']['namespace'], event['object']['metadata']['name']))
                ipam_handler(event['type'], event['object']['metadata']['namespace'],
                             event['object']['metadata']['name'], event['object']['spec'])
                if self._stop:
                    break

    def update_ipam_crd(self, namespace, name, service, ip):
        crds = client.CustomObjectsApi()
        body = {'spec': {'ipaddress': ip}}
        print("IPAM request: Patching VIP CRD %s/%s with ip %s" %
              (namespace, name, ip))
        crds.patch_namespaced_custom_object(
            GROUP, VERSION, namespace, PLURAL, name, body)

    def handle_added(self, namespace, name, service, ipam_spec):
        service = ipam_spec['service']
        vip = ipam_spec.get('ipaddress')
        if vip is None:
            print("handle_added: VIP is none, will allocate a new one")
            if len(self.unallocated_vips) > 0:
                ip = self.unallocated_vips.pop()
                print("handle_added: Allocated VIP %s" % str(ip))
                self.update_ipam_crd(namespace, name, service, str(ip))
        else:
            print("handle_added: VIP is already allocated, no action")

    def handle_modified(self, namespace, name, service, ipam_spec):
        print("handle_modified: calling handle_added")
        self.handle_added(namespace, name, service, ipam_spec)

    def handle_deleted(self, namespace, name, service, ipam_spec):
        print("handle_deleted: not sure what to do")
        # TODO
        pass

    def ipam_handler(self, operation, namespace, name, ipam_spec):
        service = ipam_spec['service']
        vip = ipam_spec.get('ipaddress')
        print("IPAM request: service: %s vip: %s" % (service, vip))
        self.handlers[operation](self, namespace, name, ipam_spec)

    def init_unallocated_vips(self, cidrs):
        for cidr in cidrs:
            for ip in ipaddress.ip_network(cidr).hosts():
                self.unallocated_vips.add(ip)
        # TODO: iterate over existing Vip CRD objects and delete them from the set of vips


if __name__ == '__main__':
    print("VIP range configured as: %s" %
          json.loads(os.environ.get('VIP_RANGE')))
    ctrller = CitrixIpamController(namespaces=[u'default'])
    ctrller.start()
