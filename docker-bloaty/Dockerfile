###############################################################################
# Builder image
###############################################################################
FROM ubuntu:22.04 as bloaty-builder

# Bloaty McBloatface git commit to build
ARG BLOATY_COMMIT=e1155149d54bb09b81e86f0e4e5cb7fbd2a318eb

# Install dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && \
    apt-get install -y git && \
    apt-get install -y --no-install-recommends build-essential cmake ninja-build libz-dev && \
    apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Clone, build and install Bloaty McBloatface
RUN mkdir /git && \
    git clone https://github.com/google/bloaty.git /git/bloaty && \
    cd /git/bloaty && \
    git checkout $BLOATY_COMMIT && \
    git submodule update --init --recursive && \
    cmake -B build -G Ninja -S . && \
    cmake --build build && \
    cmake --build build --target install

###############################################################################
# Image to ship
###############################################################################
FROM ubuntu:22.04

# The versioning system used for this image: <docker_img_version>-<bloaty_commit>
LABEL "version"="v1.0.0-e1155514"
LABEL org.opencontainers.image.title="Bloaty McBloatface Docker Image"
LABEL org.opencontainers.image.description="Docker image to run Bloaty McBloatface: a size profiler for binaries."
LABEL org.opencontainers.image.authors="Carlos Pereira Atencio <carlosperate@embeddedlog.com>, Alexander Lerach <alexander@auterion.com>"
LABEL org.opencontainers.image.source="https://github.com/PX4/bloaty-action"

# Copy the binaries into this image
COPY --from=bloaty-builder /usr/local/bin /usr/local/bin

WORKDIR /home

ENTRYPOINT ["bloaty"]
