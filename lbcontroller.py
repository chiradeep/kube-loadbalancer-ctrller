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
from kubernetes.client.rest import ApiException
import threading

GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"
VIP_ANNOTATION_KEY = 'com.citrix.vip'


class CitrixLoadBalancerController(object):
    def __init__(self):
        config.load_kube_config()
        self.t1 = threading.Thread(target=self.watch_for_services,
                            args=([u'default'], self.service_handler))
        self.t2 = threading.Thread(target=self.watch_for_ipam_create_request,
                            args=([u'default'], self.ipam_handler))
        self.t1.start()
        self.t2.start()
    
    def __del__(self):
        self.t1.join()
        self.t2.join()

    def watch_for_ipam_create_request(self, namespaces, ipam_handler):
        # load config from default location.
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


    def ipam_handler(self, namespace, name, ipam_spec):
        service = ipam_spec['service']
        vip = ipam_spec.get('ipaddress')
        print("IPAM request: service: %s vip: %s" % (service, vip))
        if vip is None:
            print("IPAM request: VIP is none, nothing to do")
        else:
            print("IPAM request: VIP is  allocated, will update service VIP annotation")
            self.update_service_vip_annotation(namespace, name, vip)


    def watch_for_services(self, namespaces, service_handler):
        v1 = client.CoreV1Api()
        print("Listening for services for all namespaces")
        w = watch.Watch()

        for event in w.stream(v1.list_service_for_all_namespaces):
            if event['object'].metadata.namespace in namespaces:
                print("Event: %s %s %s/%s" % (event['type'], event['object'].kind,
                                            event['object'].metadata.namespace, event['object'].metadata.name))
                service_handler(event['object'])


    def service_handler(self, service_obj):
        namespace = service_obj.metadata.namespace
        name = service_obj.metadata.name
        spec = service_obj.spec
        if spec.type == 'LoadBalancer':
            print ("service_handler: handling type LoadBalancer for service %s/%s" %
                (namespace, name))
            lb_annotation = None
            if service_obj.metadata.annotations != None:
                lb_annotation = service_obj.metadata.annotations.get(
                    VIP_ANNOTATION_KEY)
            if lb_annotation is None:
                print ("service_handler: No VIP annotation: creating/reading VIP crd for service %s/%s" %
                    (namespace, name))
                self.read_or_create_vip_crd(service_obj)
                print ("service_handler: Read/created VIP crd for service %s/%s" %
                    (namespace, name))
            else:
                print ("service_handler:  vip annotation alreadys set for service %s/%s: %s" %
                    (namespace, name, lb_annotation))


    def annotate_service(self, namespace, name, service_obj, ipaddr):
        v1 = client.CoreV1Api()
        if service_obj.metadata.annotations is None:
            service_obj.metadata.annotations = {}
        service_obj.metadata.annotations[VIP_ANNOTATION_KEY] = ipaddr
        try:
            v1.replace_namespaced_service(name, namespace, service_obj)
        except ApiException as e:
            print("Exception when calling replace_namespaced_service: %s" % e)


    def update_service_vip_annotation(self, namespace, name, ipaddr):
        v1 = client.CoreV1Api()
        try:
            service_obj = v1.read_namespaced_service(name, namespace)
            lb_annotation = None
            if service_obj.metadata.annotations != None:
                lb_annotation = service_obj.metadata.annotations.get(
                    VIP_ANNOTATION_KEY)
            if lb_annotation is None:
                print ("update_service_vip_annotation: No vip annotation on service: updating annotation for service %s/%s" % (namespace, name))
                self.annotate_service(namespace, name, service_obj, ipaddr)
                print ("update_service_vip_annotation: Updated vip annotation for service %s/%s" %
                    (namespace, name))
            else:
                print ("update_service_vip_annotation:  vip annotation alreadys set for service %s/%s: %s" %
                    (namespace, name, lb_annotation))
        except ApiException as e:
            print("update_service_vip_annotation : no service of name %s/%s found, exception=%s" %
                (namespace, name, e))


    def read_or_create_vip_crd(self, service_obj):
        crds = client.CustomObjectsApi()
        name = service_obj.metadata.name
        namespace = service_obj.metadata.namespace
        body = {'apiVersion': 'ipam.citrix.com/v1',
                'kind': 'Vip',
                'metadata': {'name': '%s' % name},
                'description': 'VIP for %s service' % name,
                'spec': {'description': 'VIP for the %s Service' % name,
                        'service': name}
                }

        try:
            response = crds.get_namespaced_custom_object(
                GROUP, VERSION, namespace, PLURAL, '%s' % name)
            # print("Response is " , response)
            ipaddr = response['spec'].get('ipaddress')
            if ipaddr is None:
                print ("create_vip_cidr:  VIP CRD already created for service %s/%s but no IP address yet" %
                    (namespace, name))
            else:
                print ("create_vip_cidr:  VIP %s already created for service %s/%s" %
                    (ipaddr, namespace, name))
                # the vip crd may exist but not in the service object
                self.update_service_vip_annotation(namespace, name, ipaddr)
        except ApiException as e:
            print ("create_vip_cidr:  VIP not already created for service %s/%s, exception=%s" %
                (namespace, name, e))
            response = crds.create_namespaced_custom_object(
                GROUP, VERSION, namespace, PLURAL, body)


if __name__ == '__main__':
    ctrller = CitrixLoadBalancerController()
