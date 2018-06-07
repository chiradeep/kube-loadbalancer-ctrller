#all: push
all: docker

TAG = latest
PREFIX ?= localhost:5000

LBC_PREFIX = $(PREFIX)/citrix-lbcontroller
IPAM_PREFIX = $(PREFIX)/citrix-ipamcontroller

docker: lbc-docker ipam-docker

lbc-docker: lbcontroller/lbcontroller.py
	(cd lbcontroller; docker build -t $(LBC_PREFIX):$(TAG) .)

ipam-docker: ipamcontroller/ipamcontroller.py
	(cd ipamcontroller; docker build -t $(IPAM_PREFIX):$(TAG) .)

.PHONY: deploy

deploy:
	kubectl apply -f deploy/vip_crd.yml
	kubectl apply -f deploy/rbac.yml
	kubectl apply -f deploy/deploy.yml
