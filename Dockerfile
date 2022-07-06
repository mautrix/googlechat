FROM docker.io/alpine:3.16

RUN apk add --no-cache \
      python3 py3-pip py3-setuptools py3-wheel \
      py3-pillow \
      py3-aiohttp \
      py3-magic \
      py3-ruamel.yaml \
      py3-commonmark \
      #py3-prometheus-client \
      py3-protobuf \
      py3-idna \
      # encryption
      py3-olm \
      py3-cffi \
      py3-pycryptodome \
      py3-unpaddedbase64 \
      py3-future \
      # proxy support
      py3-pysocks \
      py3-aiohttp-socks \
      # Other dependencies
      ca-certificates \
      su-exec \
      bash \
      curl \
      jq \
      yq

COPY requirements.txt /opt/mautrix-googlechat/requirements.txt
COPY optional-requirements.txt /opt/mautrix-googlechat/optional-requirements.txt
WORKDIR /opt/mautrix-googlechat
RUN apk add --virtual .build-deps python3-dev libffi-dev build-base \
 && pip3 install --no-cache-dir -r requirements.txt -r optional-requirements.txt \
 && apk del .build-deps

COPY . /opt/mautrix-googlechat
RUN apk add git && pip3 install --no-cache-dir .[all] && apk del git \
  # This doesn't make the image smaller, but it's needed so that the `version` command works properly
  && cp mautrix_googlechat/example-config.yaml . && rm -rf mautrix_googlechat .git build

ENV UID=1337 GID=1337
VOLUME /data

CMD ["/opt/mautrix-googlechat/docker-run.sh"]
