FROM qdrant/qdrant:v1.13.2

RUN apt-get update \
    && apt-get install --yes --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*
