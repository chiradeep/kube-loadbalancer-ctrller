FROM python:2.7-alpine
ADD lbcontroller.py /
RUN pip install kubernetes
CMD ["python", "./lbcontroller.py"]
