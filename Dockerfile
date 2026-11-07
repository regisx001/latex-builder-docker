FROM texlive/texlive:latest

RUN apt-get update && \
    apt-get install -y \
        fonts-liberation \
        fonts-dejavu \
        fonts-noto \
        fonts-noto-cjk \
        fonts-noto-extra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
