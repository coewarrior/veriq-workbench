FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.162.1
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/* \
 && npm install -g @openai/codex@${CODEX_VERSION} && npm cache clean --force
COPY bridge.py /opt/bridge.py
ENV CODEX_HOME=/state HTTPS_PROXY=http://127.0.0.1:18080 HTTP_PROXY=http://127.0.0.1:18080 ALL_PROXY=http://127.0.0.1:18080 NO_PROXY="" HOME=/state
WORKDIR /work
ENTRYPOINT ["python3", "/opt/bridge.py"]
