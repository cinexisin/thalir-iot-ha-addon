ARG BUILD_FROM
FROM ${BUILD_FROM}

# Python deps for the lockdown + mDNS bridge
RUN apk add --no-cache python3 py3-pip py3-yaml py3-requests py3-zeroconf py3-paho-mqtt avahi

WORKDIR /opt/thalir

# Copy add-on source
COPY thalir/ ./thalir/
COPY rootfs/ /

# Make run script executable
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Don't run as root inside container (HA convention is uid 0 fine in supervised, but be defensive)
USER root

LABEL \
    io.hass.name="Thalir IoT" \
    io.hass.description="Smart farm automation — motor starters, valves, water level" \
    io.hass.version="1.0.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armv7"

CMD [ "/run.sh" ]
