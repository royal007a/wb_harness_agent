FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY external_runner.py /opt/harness/external_runner.py
RUN chmod 0555 /opt/harness/external_runner.py
USER 65532:65532
WORKDIR /work
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-I", "-u", "/opt/harness/external_runner.py"]
