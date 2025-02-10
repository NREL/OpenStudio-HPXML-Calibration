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

# Install NREL root certs.
RUN curl -fsSLk -o /usr/local/share/ca-certificates/nrel_root.crt https://raw.github.nrel.gov/TADA/nrel-certs/v20180329/certs/nrel_root.pem && \
  curl -fsSLk -o /usr/local/share/ca-certificates/nrel_xca1.crt https://raw.github.nrel.gov/TADA/nrel-certs/v20180329/certs/nrel_xca1.pem && \
  update-ca-certificates && \
  sed -i 's/^\(\[openssl_init\]\)/\1\nssl_conf = ssl_sect\n\n[ssl_sect]\nsystem_default = system_default_sect\n\n[system_default_sect]\nOptions = UnsafeLegacyServerConnect/' /etc/ssl/openssl.cnf
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

COPY --from=uv --chown=vscode: /uv /uvx /bin/

# Install OpenStudio
RUN wget -q "https://github.com/NREL/OpenStudio/releases/download/v3.9.0/OpenStudio-3.9.0+c77fbb9569-Ubuntu-22.04-arm64.deb" -O OpenStudio.deb \
    && dpkg -i OpenStudio.deb \
    && rm OpenStudio.deb # Clean up the .deb file

# Set the OpenStudio installation directory in the PATH
ENV PATH="/usr/local/openstudio-3.9.0/bin:${PATH}"
