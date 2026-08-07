# Debian bookworm's 'main' apt repo ships no prebuilt asterisk package
# (confirmed directly), and building Asterisk + PJSIP (with the right SRTP/
# WebRTC flags chan_pjsip needs) from source is its own multi-step build
# most teams don't hand-roll from scratch. andrius/asterisk is a
# well-maintained, actively updated community image that ships Asterisk 20
# with chan_pjsip, ARI (incl. res_stasis_snoop, res_ari_channels for
# External Media), and WebRTC support already compiled in, at the standard
# /etc/asterisk config path — exactly what our conf/ overrides expect.
FROM andrius/asterisk:20

# This image ships with an empty /var/lib/asterisk/sounds — confirmed by
# inspecting a running container (0 files). Without core sounds,
# Playback(demo-congrats) etc. silently fail ("File ... does not exist"),
# which breaks scripts/make_test_call.py's whole premise: no audio ever
# gets generated for the realtime-assist tap or the recording to transcribe.
RUN mkdir -p /var/lib/asterisk/sounds/en \
    && curl -sL https://downloads.asterisk.org/pub/telephony/sounds/asterisk-core-sounds-en-wav-current.tar.gz \
        -o /tmp/core-sounds.tar.gz \
    && tar xzf /tmp/core-sounds.tar.gz -C /var/lib/asterisk/sounds/en/ \
    && rm /tmp/core-sounds.tar.gz

# Real customer-service call recording (public domain, archive.org) used by
# scripts/make_real_call_test.py to prove transcription/QA-scoring/nudging
# against genuine call content, not just Asterisk's own demo audio. See
# test-audio/README for provenance.
COPY test-audio/real-call-sample.wav /var/lib/asterisk/sounds/en/real-call-sample.wav

COPY conf/pjsip.conf /etc/asterisk/pjsip.conf
COPY conf/extensions.conf /etc/asterisk/extensions.conf
COPY conf/ari.conf /etc/asterisk/ari.conf
COPY conf/http.conf /etc/asterisk/http.conf
COPY conf/rtp.conf /etc/asterisk/rtp.conf
COPY conf/logger.conf /etc/asterisk/logger.conf

EXPOSE 5060/udp 8088 8089 10000-10099/udp
