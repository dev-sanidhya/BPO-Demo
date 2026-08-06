FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        asterisk \
        asterisk-config \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Recordings volume shared with qa-scoring service
RUN mkdir -p /var/spool/asterisk/monitor && chown -R asterisk:asterisk /var/spool/asterisk

COPY conf/pjsip.conf /etc/asterisk/pjsip.conf
COPY conf/extensions.conf /etc/asterisk/extensions.conf
COPY conf/ari.conf /etc/asterisk/ari.conf
COPY conf/http.conf /etc/asterisk/http.conf
COPY conf/rtp.conf /etc/asterisk/rtp.conf
COPY conf/logger.conf /etc/asterisk/logger.conf

EXPOSE 5060/udp 8088 8089 10000-10099/udp

CMD ["asterisk", "-f", "-vvv"]
