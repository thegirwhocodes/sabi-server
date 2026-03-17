FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Asterisk from Ubuntu repos + dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    asterisk \
    asterisk-core-sounds-en \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy Asterisk configs
COPY pjsip.conf /etc/asterisk/pjsip.conf
COPY extensions.conf /etc/asterisk/extensions.conf
COPY manager.conf /etc/asterisk/manager.conf
COPY modules.conf /etc/asterisk/modules.conf
COPY rtp.conf /etc/asterisk/rtp.conf

# Create shared audio directory
RUN mkdir -p /shared/audio

# Expose SIP + RTP + AMI ports
EXPOSE 5060/udp 5060/tcp 5038/tcp
EXPOSE 10000-10100/udp

CMD ["asterisk", "-fvvv"]
