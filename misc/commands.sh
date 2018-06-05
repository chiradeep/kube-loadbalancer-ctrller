kubectl create configmap vip-range --from-literal=vip.space=[10.20.30.0/24]
kubectl apply -f vip_crd.yaml
