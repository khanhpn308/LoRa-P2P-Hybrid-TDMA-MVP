FROM eclipse-mosquitto:2.0

COPY --chown=1883:1883 --chmod=0600 acl /mosquitto/config/acl
COPY --chown=1883:1883 --chmod=0444 tls.conf /mosquitto/config/mosquitto.conf
USER 1883:1883
