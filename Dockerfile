ARG BASE_IMAGE_TAG=focal-3.8
FROM makinacorpus/geodjango:${BASE_IMAGE_TAG}

ENV ENV=prod
ENV SERVER_NAME="localhost"
# If POSTGRES_HOST is empty, entrypoint will set it to the IP of the docker host in the container
ENV POSTGRES_HOST=""
ENV POSTGRES_PORT="5432"
ENV POSTGRES_USER="geotrek"
ENV POSTGRES_PASSWORD="geotrek"
ENV POSTGRES_DB="geotrekdb"
ENV REDIS_HOST="redis"
ENV CONVERSION_HOST="convertit"
ENV CAPTURE_HOST="screamshotter"
ENV CUSTOM_SETTINGS_FILE="/opt/geotrek-admin/var/conf/custom.py"

WORKDIR /opt/geotrek-admin
RUN mkdir -p /opt/geotrek-admin/var/log

# Install postgis because raster2pgsl is required by manage.py loaddem
RUN apt-get update -qq && apt-get install -y -qq  \
    unzip \
    sudo \
    less \
    nano \
    curl \
    git \
    iproute2 \
    software-properties-common \
    shared-mime-info \
    fonts-liberation \
    libssl-dev \
    libfreetype6-dev \
    libxml2-dev \
    libxslt-dev \
    libcairo2 \
    libpango1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-dev \
    libffi-dev && \
    apt-get install -y --no-install-recommends postgis && \
    apt-get clean all && rm -rf /var/lib/apt/lists/* && rm -rf /var/cache/apt/*

COPY requirements.txt requirements.txt
RUN python3 -m venv /opt/venv
RUN /opt/venv/bin/pip install -U pip setuptools wheel
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt -U

COPY geotrek/ geotrek/
COPY manage.py manage.py
COPY VERSION VERSION
COPY .coveragerc .coveragerc
COPY docker/* /usr/local/bin/

ENTRYPOINT ["/bin/sh", "-e", "/usr/local/bin/entrypoint.sh"]
EXPOSE 8000

RUN ENV=dev CONVERSION_HOST=localhost CAPTURE_HOST=localhost CUSTOM_SETTINGS_FILE= SECRET_KEY=tmp /opt/venv/bin/python ./manage.py compilemessages

CMD ["gunicorn", "geotrek.wsgi:application", "--bind=0.0.0.0:8000"]
