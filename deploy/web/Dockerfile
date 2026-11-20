FROM scratch AS browser_archive
# Matched against Google Chrome for Testing official size and MD5 before pinning SHA-256.
ADD --checksum=sha256:c3e50596aef52c58f8fda3c6b3411c33d34c88b177b3ed1c2243359fd3b8ba20 https://registry.npmmirror.com/-/binary/chrome-for-testing/156.0.8078.4/linux64/chrome-headless-shell-linux64.zip /chromium.zip

# Match the base verified by deploy-main #484; update this digest explicitly.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    API_TEST_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jre-headless ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -c "import urllib.request,hashlib; p='/tmp/jmeter.tgz'; urllib.request.urlretrieve('https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.tgz',p); assert hashlib.sha512(open(p,'rb').read()).hexdigest() == '5978a1a35edb5a7d428e270564ff49d2b1b257a65e17a759d259a9283fc17093e522fe46f474a043864aea6910683486340706d745fcdf3db1505fd71e689083'" \
    && tar -xzf /tmp/jmeter.tgz -C /opt && rm /tmp/jmeter.tgz \
    && ln -s /opt/apache-jmeter-5.6.3/bin/jmeter /usr/local/bin/jmeter

WORKDIR /app
COPY requirements-web.lock /tmp/requirements-web.lock
RUN python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/requirements-web.lock
COPY requirements-browser.lock /tmp/requirements-browser.lock
RUN python -m pip install --no-cache-dir --no-deps --only-binary=:all: --require-hashes --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/requirements-browser.lock && python -m pip check
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && python -m playwright install-deps chromium && rm -rf /var/lib/apt/lists/*
COPY install-browser.py /tmp/install-platform-browser.py
RUN --mount=type=bind,from=browser_archive,source=/chromium.zip,target=/tmp/platform-chromium.zip \
    python /tmp/install-platform-browser.py && chmod -R a+rX /opt/playwright
COPY requirements-postgres.lock /tmp/requirements-postgres.lock
RUN python -m pip install --no-cache-dir --no-deps --only-binary=:all: --require-hashes --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/requirements-postgres.lock && python -m pip check
COPY --chown=10001:10001 source/ /app/
RUN python -m pip install --no-cache-dir --no-deps --index-url https://pypi.tuna.tsinghua.edu.cn/simple . \
    && mkdir -p /data \
    && chown 10001:10001 /data \
    && chmod 700 /data

USER 10001:10001
EXPOSE 18089
CMD ["python", "-c", "from api_test_tool.web import serve; serve(host='0.0.0.0', port=18089, data_dir='/data')"]
