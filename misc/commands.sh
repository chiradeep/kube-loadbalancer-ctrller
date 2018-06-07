minikube start --disk-size 20g --memory 4000 --insecure-registry localhost:5000 --vm-driver=hyperkit
kubectl apply -f vip_crd.yaml
kubectl apply -f vip1.yaml
kubectl create configmap vip-range --from-literal=vip.space=[10.20.30.0/24]
