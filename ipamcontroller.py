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

VIP_RANGE = json.loads(os.environ.get('VIP_RANGE'))
allocated_vips = set()
unallocated_vips = set()

def watch_for_ipam_create_request(namespaces, ipam_handler):
    # load config from default location.
    config.load_kube_config()
    crds = client.CustomObjectsApi()
    resource_version = ""
    stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                  GROUP, VERSION, PLURAL,
                                  resource_version=resource_version)
    for event in stream:
        if event['object']['metadata']['namespace'] in namespaces:
            print("Event: %s %s %s/%s" % (event['type'],event['object']['kind'], event['object']['metadata']['namespace'], event['object']['metadata']['name']))
            ipam_handler(event['object']['metadata']['namespace'], event['object']['metadata']['name'], event['object']['spec'])


def update_ipam_crd(namespace, name, service, ip):
    crds = client.CustomObjectsApi()
    body = { 'spec' : { 'ipaddress': ip} }
    print("IPAM request: Patching VIP CRD %s/%s with ip %s" % (namespace, name, ip))
    response = crds.patch_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL, name, body)
    

def ipam_handler(namespace, name, ipam_spec):
    service = ipam_spec['service']
    vip = ipam_spec.get('ipaddress')
    print("IPAM request: service: %s vip: %s" % (service, vip))
    if vip is None:
        print("IPAM request: VIP is none, will allocate a new one")
        if len(unallocated_vips) > 0:
            ip = unallocated_vips.pop()
            print("IPAM request: Allocated VIP %s" % str(ip))
            update_ipam_crd(namespace, name, service, str(ip))
    else:
        print("IPAM request: VIP is already allocated, no action")
      
    
    
def init_unallocated_vips(cidrs):
    for cidr in cidrs:
        for ip in ipaddress.ip_network(cidr).hosts():
            unallocated_vips.add(ip)
    #TODO: iterate over existing Vip CRD objects and delete them from the set of vips

if __name__ == '__main__':
    print("VIP range configured as: %s" % json.loads(os.environ.get('VIP_RANGE')))
    vip_cidrs = json.loads(os.environ.get('VIP_RANGE'))
    init_unallocated_vips(vip_cidrs)
    watch_for_ipam_create_request([u'default'], ipam_handler)
