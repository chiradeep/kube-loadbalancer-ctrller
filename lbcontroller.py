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

GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"
NAMESPACE = "default"

def watch_for_services(namespaces, service_handler):
    # load config from default location.
    config.load_kube_config()

    v1 = client.CoreV1Api()
    print("Listening for services for all namespaces")
    w = watch.Watch()
    
    for event in  w.stream(v1.list_service_for_all_namespaces): 
        if event['object'].metadata.namespace in namespaces:
            print("Event: %s %s %s/%s" % (event['type'],event['object'].kind, event['object'].metadata.namespace, event['object'].metadata.name))
            service_handler(event['object'])


def service_handler(service_obj):
    namespace = service_obj.metadata.namespace
    name= service_obj.metadata.name
    spec = service_obj.spec
    if spec.type == 'LoadBalancer':
        print ("service_handler: handling type LoadBalancer for service %s/%s" % (namespace, name))
        create_vip_crd(service_obj)
        print ("service_handler: created VIP crd for service %s/%s" % (namespace, name))


def create_vip_crd(service_obj):
    crds = client.CustomObjectsApi()
    name = service_obj.metadata.name
    namespace = service_obj.metadata.namespace
    body = { 'apiVersion': 'ipam.citrix.com/v1',
             'kind': 'Vip',
             'metadata': {'name': '%s-vip' % name},
             'description': 'VIP for %s service' % name,
             'spec' : {'description': 'VIP for the %s Service' % name,
                       'service': name}
           }
    #TODO: check if it already exists
    response = crds.create_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL, body)

if __name__ == '__main__':
    watch_for_services([u'default'], service_handler)
