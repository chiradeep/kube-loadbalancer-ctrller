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


def watch_for_services(namespaces):
    # load config from default location.
    config.load_kube_config()

    v1 = client.CoreV1Api()
    print("Listening for services for all namespaces")
    w = watch.Watch()
    
    for event in  w.stream(v1.list_service_for_all_namespaces): 
        if event['object'].metadata.namespace in namespaces:
            print("Event: %s %s %s/%s" % (event['type'],event['object'].kind, event['object'].metadata.namespace, event['object'].metadata.name))


if __name__ == '__main__':
    watch_for_services([u'default'])
