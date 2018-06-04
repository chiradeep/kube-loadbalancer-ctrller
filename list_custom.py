from kubernetes import client, config, watch

GROUP = "ipam.citrix.com"
VERSION = "v1"
PLURAL = "vips"

config.load_kube_config()

crds = client.CustomObjectsApi()
        
resource_version = ""

while True:

    print "initializing stream"
    stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                  GROUP, VERSION, PLURAL,
                                  resource_version=resource_version)
    for event in stream:
        t = event["type"]
        obj = event["object"]
    
        print t
        print obj  

        # Configure where to resume streaming.
        metadata = obj['metadata']

        if metadata['resourceVersion'] is not None:
            resource_version = metadata['resourceVersion']
            print resource_version
