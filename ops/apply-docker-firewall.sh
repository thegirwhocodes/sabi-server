#!/usr/bin/env bash
set -euo pipefail

AT_IP="102.223.37.68"
TWILIO_SIGNALING_CIDRS=(
  "54.172.60.0/30"
  "54.244.51.0/30"
  "54.171.127.192/30"
  "35.156.191.128/30"
  "54.65.63.192/30"
  "54.169.127.128/30"
  "54.252.254.64/30"
  "177.71.206.192/30"
)

ensure_v4_rule() {
  if ! iptables -C DOCKER-USER "$@" 2>/dev/null; then
    iptables -I DOCKER-USER 1 "$@"
  fi
}

ensure_v6_drop() {
  if ip6tables -L DOCKER-USER >/dev/null 2>&1; then
    if ! ip6tables -C DOCKER-USER "$@" 2>/dev/null; then
      ip6tables -I DOCKER-USER 1 "$@"
    fi
  fi
}

# Docker-published Asterisk SIP signaling. Accept only the configured carriers'
# documented signaling networks, then reject every other public SIP source.
# Rules are scoped to inbound traffic so Asterisk can still send SIP requests.
# Remove the former Africa's-Talking-only negative-source rules first.
iptables -D DOCKER-USER -i enp4s0 -p udp ! -s "$AT_IP" --dport 5060 -j DROP 2>/dev/null || true
iptables -D DOCKER-USER -i enp4s0 -p tcp ! -s "$AT_IP" --dport 5060 -j DROP 2>/dev/null || true

# `iptables -I ... 1` reverses declaration order. Install the fallback drops
# first, then insert carrier accepts above them.
ensure_v4_rule -i enp4s0 -p udp --dport 5060 -j DROP
ensure_v4_rule -i enp4s0 -p tcp --dport 5060 -j DROP
ensure_v4_rule -i enp4s0 -p udp -s "$AT_IP" --dport 5060 -j ACCEPT
for cidr in "${TWILIO_SIGNALING_CIDRS[@]}"; do
  ensure_v4_rule -i enp4s0 -p udp -s "$cidr" --dport 5060 -j ACCEPT
done

# Neither trunk uses IPv6. RTP remains IPv4-only while the current Asterisk
# media range is 10000:10100.
ensure_v6_drop -p udp --dport 5060 -j DROP
ensure_v6_drop -p tcp --dport 5060 -j DROP
ensure_v6_drop -p udp --dport 10000:10100 -j DROP

# The production trunks use UDP; do not expose host-level TCP SIP.
if ! iptables -C INPUT -p tcp --dport 5060 -j DROP 2>/dev/null; then
  iptables -I INPUT 1 -p tcp --dport 5060 -j DROP
fi
if ip6tables -L INPUT >/dev/null 2>&1; then
  if ! ip6tables -C INPUT -p tcp --dport 5060 -j DROP 2>/dev/null; then
    ip6tables -I INPUT 1 -p tcp --dport 5060 -j DROP
  fi
fi
