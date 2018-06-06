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
NAMESPACE = 'default'

class CitrixIpamController(object):
    def __init__(self):
        self.vip_cidrs = json.loads(os.environ.get('VIP_RANGE'))
        config.load_kube_config()

        self.unallocated_vips = set()
        self.init_unallocated_vips(self.vip_cidrs)
        self.watch_for_ipam_create_request([u'default'], self.ipam_handler)

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
                ipam_handler(event['object']['metadata']['namespace'],
                             event['object']['metadata']['name'], event['object']['spec'])

    def update_ipam_crd(self, namespace, name, service, ip):
        crds = client.CustomObjectsApi()
        body = {'spec': {'ipaddress': ip}}
        print("IPAM request: Patching VIP CRD %s/%s with ip %s" %
              (namespace, name, ip))
        crds.patch_namespaced_custom_object(
            GROUP, VERSION, namespace, PLURAL, name, body)

    def ipam_handler(self, namespace, name, ipam_spec):
        service = ipam_spec['service']
        vip = ipam_spec.get('ipaddress')
        print("IPAM request: service: %s vip: %s" % (service, vip))
        if vip is None:
            print("IPAM request: VIP is none, will allocate a new one")
            if len(self.unallocated_vips) > 0:
                ip = self.unallocated_vips.pop()
                print("IPAM request: Allocated VIP %s" % str(ip))
                self.update_ipam_crd(namespace, name, service, str(ip))
        else:
            print("IPAM request: VIP is already allocated, no action")

    def init_unallocated_vips(self, cidrs):
        for cidr in cidrs:
            for ip in ipaddress.ip_network(cidr).hosts():
                self.unallocated_vips.add(ip)
        # TODO: iterate over existing Vip CRD objects and delete them from the set of vips


if __name__ == '__main__':
    print("VIP range configured as: %s" %
          json.loads(os.environ.get('VIP_RANGE')))
    ctrller = CitrixIpamController()
