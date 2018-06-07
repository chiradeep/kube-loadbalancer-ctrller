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
import signal
import threading

GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"
VIP_ANNOTATION_KEY = 'com.citrix.vip'


class CitrixLoadBalancerController(object):
    def __init__(self):
        try:
            config.load_kube_config()
        except:
            config.load_incluster_config()
        signal.signal(signal.SIGINT, self.signal_handler)

        self.t1 = threading.Thread(target=self.watch_for_services,
                                   args=([u'default'], self.service_handler))
        self.t2 = threading.Thread(target=self.watch_for_ipam_create_request,
                                   args=([u'default'], self.ipam_handler))
        self._stop = False
        self.svc_handlers = {'ADDED': self.handle_svc_added,
                             'MODIFIED': self.handle_svc_modified,
                             'DELETED': self.handle_svc_deleted,
                             'ERROR': self.handle_svc_error}

        self.ipam_handlers = {'ADDED': self.handle_ipam_added,
                              'MODIFIED': self.handle_ipam_modified,
                              'DELETED': self.handle_ipam_deleted,
                              'ERROR': self.handle_ipam_error}
        self.watch = watch.Watch()

    def start(self):
        self._stop = False
        self.t1.start()
        self.t2.start()

    def stop(self):
        self._stop = True
        self.t1.join()
        self.t2.join()

    def __del__(self):
        self._stop = True
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
                ipam_handler(event['type'], event['object']['metadata']['namespace'],
                             event['object']['metadata']['name'], event['object']['spec'])
                if self._stop:
                    break

    def handle_ipam_added(self, namespace, name, ipam_obj):
        service = ipam_obj['service']
        vip = ipam_obj.get('ipaddress')
        print("handle_ipam_added: service: %s vip: %s" % (service, vip))
        if vip is None:
            print("handle_ipam_added: VIP is none, nothing to do")
        else:
            print(
                "handle_ipam_added: VIP is  allocated, will update service VIP annotation")
            self.update_service_vip_annotation(namespace, name, vip)

    def handle_ipam_deleted(self, namespace, name, ipam_obj):
        print("handle_ipam_deleted: not sure what to do")
        # TODO: remove lb config from NetScaler?, or some way of preventing this?
        # for now remove service annotation

    def handle_ipam_modified(self, namespace, name, ipam_obj):
        print("handle_ipam_modified: calling handle_ipam_added")
        self.handle_ipam_added(namespace, name, ipam_obj)

    def handle_ipam_error(self, namespace, name, ipam_obj):
        print("handle_ipam_error: not sure what to do")
        # TODO

    def ipam_handler(self, operation, namespace, name, ipam_obj):
        service = ipam_obj['service']
        vip = ipam_obj.get('ipaddress')
        print("IPAM request: operation: %s service: %s vip: %s" %
              (operation, service, vip))
        self.ipam_handlers[operation](namespace, name, ipam_obj)

    def watch_for_services(self, namespaces, service_handler):
        v1 = client.CoreV1Api()
        print("Listening for services for all namespaces")
        w = watch.Watch()

        for event in w.stream(v1.list_service_for_all_namespaces):
            if event['object'].metadata.namespace in namespaces:
                print("Event: %s %s %s/%s" % (event['type'], event['object'].kind,
                                              event['object'].metadata.namespace, event['object'].metadata.name))
                service_handler(event['type'], event['object'])

    def handle_svc_added(self, service_obj):
        namespace = service_obj.metadata.namespace
        name = service_obj.metadata.name
        spec = service_obj.spec
        if spec.type == 'LoadBalancer':
            print ("handle_svc_added: handling type LoadBalancer for service %s/%s" %
                   (namespace, name))
            lb_annotation = None
            if service_obj.metadata.annotations != None:
                lb_annotation = service_obj.metadata.annotations.get(
                    VIP_ANNOTATION_KEY)
            if lb_annotation is None:
                print ("handle_svc_added: No VIP annotation: creating/reading VIP crd for service %s/%s" %
                       (namespace, name))
                self.read_or_create_vip_crd(service_obj)
                print ("handle_svc_added: Read/created VIP crd for service %s/%s" %
                       (namespace, name))
            else:
                print ("handle_svc_added:  vip annotation alreadys set for service %s/%s: %s" %
                       (namespace, name, lb_annotation))

    def handle_svc_deleted(self, service_obj):
        print ("handle_svc_deleted:  deleting VIP crd")
        self.delete_vip_crd(service_obj)

    def handle_svc_modified(self, service_obj):
        print ("handle_svc_modified  calling handle_svc_added")
        self.handle_svc_added(service_obj)
        # TODO : what was modified? if change was expected annotation?

    def handle_svc_error(self, service_obj):
        print ("handle_svc_error:  not sure what to do!")
        # TODO

    def service_handler(self, operation, service_obj):
        print("service_handler: operation %s, service: %s" %
              (operation, service_obj.metadata.name))
        self.svc_handlers[operation](service_obj)

    def annotate_service(self, namespace, name, service_obj, ipaddr):
        v1 = client.CoreV1Api()
        if service_obj.metadata.annotations is None:
            service_obj.metadata.annotations = {}
        service_obj.metadata.annotations[VIP_ANNOTATION_KEY] = ipaddr
        try:
            v1.replace_namespaced_service(name, namespace, service_obj)
        except ApiException as e:
            print("Exception when calling replace_namespaced_service: %s" % e)

    def unannotate_service(self, namespace, name, service_obj):
        v1 = client.CoreV1Api()
        if service_obj.metadata.annotations is None:
            return
        service_obj.metadata.annotations.pop(VIP_ANNOTATION_KEY, None)
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
                print (
                    "update_service_vip_annotation: No vip annotation on service: updating annotation for service %s/%s" % (namespace, name))
                self.annotate_service(namespace, name, service_obj, ipaddr)
                print ("update_service_vip_annotation: Updated vip annotation for service %s/%s" %
                       (namespace, name))
            else:
                print ("update_service_vip_annotation:  vip annotation alreadys set for service %s/%s: %s" %
                       (namespace, name, lb_annotation))
        except ApiException as e:
            print("update_service_vip_annotation : no service of name %s/%s found, exception=%s" %
                  (namespace, name, e))

    def remove_service_vip_annotation(self, namespace, name, ipaddr):
        v1 = client.CoreV1Api()
        try:
            service_obj = v1.read_namespaced_service(name, namespace)
            lb_annotation = None
            if service_obj.metadata.annotations != None:
                lb_annotation = service_obj.metadata.annotations.get(
                    VIP_ANNOTATION_KEY)
            if lb_annotation is None:
                print (
                    "remove_service_vip_annotation: No vip annotation on service: %s/%s" % (namespace, name))
                return
            else:
                self.unannotate_service(namespace, name, service_obj)       
                print ("remove_service_vip_annotation:  removed vip annotation  for service %s/%s: %s" %
                       (namespace, name, lb_annotation))
        except ApiException as e:
            print("update_service_vip_annotation : no service of name %s/%s found, exception=%s" %
                  (namespace, name, e))

    def delete_vip_crd(self, service_obj):
        crds = client.CustomObjectsApi()
        name = service_obj.metadata.name
        namespace = service_obj.metadata.namespace
        options = client.V1DeleteOptions()
        print ("delete_vip_crd:  Deleting VIP CRD %s/%s" % (namespace, name))
        try:
            # TODO figure out a good value for grace period
            # TODO figure out if we want this done via garbage collection
            crds.delete_namespaced_custom_object(
                GROUP, VERSION, namespace, PLURAL, name, options, grace_period_seconds=30)
        except ApiException as e:
            print ("delete_vip_crd:  Exception while deleting VIP %s/%s, exception=%s" %
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

    def signal_handler(self, signum, stack):
        print("Received signal %d " % signum)

        if signum == signal.SIGINT:
            print("Received signal %d, exiting" % signum)
            self.stop()


if __name__ == '__main__':
    ctrller = CitrixLoadBalancerController()
    ctrller.start()
