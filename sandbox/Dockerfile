# Minimal image for model-proposed code: Python stdlib + sandbox/ only.
# No project code, no corpus, no database, no secrets, no pip packages.
FROM python:3.12-slim

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /run/sandbox \
    && chown sandbox:sandbox /run/sandbox

WORKDIR /opt/sandbox
COPY executor.py server.py ./

USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD ["python", "-c", "import socket,json;s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect('/run/sandbox/sandbox.sock');s.sendall(b'{\"ping\": true}\\n');assert json.loads(s.makefile().readline())['ok']"]

CMD ["python", "server.py"]
