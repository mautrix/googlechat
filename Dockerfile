FROM docker.io/alpine:3.11

RUN echo "@edge_main http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@edge_testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@edge_community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories

RUN apk add --no-cache \
      py3-pillow \
      py3-aiohttp \
      py3-magic \
      py3-sqlalchemy \
      py3-psycopg2 \
      py3-ruamel.yaml \
      py3-commonmark@edge_testing \
      py3-alembic@edge_testing \
      #hangups
        py3-async-timeout \
        py3-requests \
        py3-appdirs \
        #py3-protobuf@edge_community \ # (too new)
        #py3-urwid \ # (too new in repos)
        #mechanicalsoup
          py3-beautifulsoup4 \
      py3-idna \
      # matrix-nio
      olm-dev@edge_community \
      py3-cffi \
      py3-future \
      py3-atomicwrites \
      py3-pycryptodome@edge_main \
      py3-peewee@edge_community \
      py3-pyrsistent@edge_community \
      py3-jsonschema \
      py3-aiofiles \
      py3-cachetools@edge_community \
      py3-unpaddedbase64 \
      py3-pyaes@edge_testing \
      py3-logbook@edge_testing \
      # Other dependencies
      ca-certificates \
      su-exec \
      py3-pysocks

COPY requirements.txt /opt/mautrix-hangouts/requirements.txt
COPY optional-requirements.txt /opt/mautrix-hangouts/optional-requirements.txt
WORKDIR /opt/mautrix-hangouts
RUN apk add --virtual .build-deps python3-dev libffi-dev build-base \
 && sed -Ei 's/psycopg2-binary.+//' optional-requirements.txt \
 && pip3 install -r requirements.txt -r optional-requirements.txt \
 && apk del .build-deps

COPY . /opt/mautrix-hangouts
RUN apk add --no-cache git && pip3 install .[e2be] && apk del git \
  # This doesn't make the image smaller, but it's needed so that the `version` command works properly
  && cp mautrix_hangouts/example-config.yaml . && rm -rf mautrix_hangouts

ENV UID=1337 GID=1337
VOLUME /data

CMD ["/opt/mautrix-hangouts/docker-run.sh"]
