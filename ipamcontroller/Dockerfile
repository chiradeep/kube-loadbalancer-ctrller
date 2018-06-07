FROM python:2.7-alpine
ADD ipamcontroller.py /
RUN pip install kubernetes
CMD ["python", "./ipamcontroller.py"]
