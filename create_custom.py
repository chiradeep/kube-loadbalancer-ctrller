from kubernetes import client, config, watch

GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"
NAMESPACE = "default"

config.load_kube_config()

crds = client.CustomObjectsApi()
body = { 'apiVersion': 'ipam.citrix.com/v1',
         'kind': 'Vip',
         'metadata': {'name': 'ojvip'},
         'description': 'VIP for OJ service',
         'spec' : {'description': 'VIP for the OJ Service',
                   'service': 'oj-service'}
         }

response = crds.create_namespaced_custom_object(GROUP, VERSION, NAMESPACE, PLURAL, body)
