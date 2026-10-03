# amd64 child verified against the canonical index:
# sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79
COPY external_runner.py /opt/harness/external_runner.py
RUN chmod 0555 /opt/harness/external_runner.py
USER 65532:65532
WORKDIR /work
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-I", "-u", "/opt/harness/external_runner.py"]
