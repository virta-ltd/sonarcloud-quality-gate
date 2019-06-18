FROM python:3.7-slim

COPY pipe /usr/bin/
COPY pipe.yml /usr/bin/

WORKDIR /usr/bin

RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "/usr/bin/pipe.py"]
