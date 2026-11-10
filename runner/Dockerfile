FROM gcc:14-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY runner.py /opt/runner.py
RUN chmod 0555 /opt/runner.py
WORKDIR /tmp
ENTRYPOINT ["python3", "/opt/runner.py"]

