FROM grafana/grafana:11.3.0

# Provisioning files are mounted from compose (not copied into the image)
# so they can be edited without rebuild.

# Instead of a Dockerfile provision, we only copy what is static:
COPY provisioning/ /etc/grafana/provisioning/

# By default Grafana runs as user 472 (grafana). The provisioning dir
# must be readable. Since the compose volume mounts over /etc/grafana/provisioning
# at runtime, this only affects the first build.

EXPOSE 3000
