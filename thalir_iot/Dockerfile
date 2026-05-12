ARG BUILD_FROM
FROM ${BUILD_FROM}

# HA base-python image already ships python3 + pip + bashio.
# We add avahi for mDNS advertising + python deps via pip (works on any
# alpine/python combo and avoids hunting apk-packaged variants per arch).
RUN apk add --no-cache avahi avahi-tools \
 && pip3 install --no-cache-dir --break-system-packages \
      pyyaml requests paho-mqtt zeroconf

WORKDIR /opt/thalir

# Copy add-on source
COPY thalir/ ./thalir/

# Run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
    io.hass.name="Thalir IoT" \
    io.hass.description="Smart farm automation - motor starters, valves, water level" \
    io.hass.version="1.0.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armv7"

CMD [ "/run.sh" ]
