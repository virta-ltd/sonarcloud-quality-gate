FROM alpine:3.8
RUN apk update && apk add bash curl jq

COPY task /usr/bin/
RUN chmod 755 /usr/bin/check-quality-gate.sh

ENTRYPOINT ["/usr/bin/check-quality-gate.sh"]
