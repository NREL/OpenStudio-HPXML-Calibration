ARG UV_VERSION=latest
ARG DEBIAN_VERSION=bookworm

FROM ghcr.io/astral-sh/uv:$UV_VERSION AS uv

FROM mcr.microsoft.com/vscode/devcontainers/base:$DEBIAN_VERSION

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv --chown=vscode: /uv /uvx /bin/

# Install OpenStudio
RUN wget -q "https://github.com/NREL/OpenStudio/releases/download/v3.9.0/OpenStudio-3.9.0+c77fbb9569-Ubuntu-22.04-arm64.deb" -O OpenStudio.deb \
    && dpkg -i OpenStudio.deb \
    && rm OpenStudio.deb # Clean up the .deb file

# Set the OpenStudio installation directory in the PATH
ENV PATH="/usr/local/openstudio-3.9.0/bin:${PATH}"
