#!/bin/bash

echo "Applying restrictive nftables firewall (PyPI‑only)..."

# Flush existing rules
nft flush ruleset

# Create table
nft add table inet firewall

# Create chains with default DROP
nft add chain inet firewall input  '{ type filter hook input priority 0; policy drop; }'
nft add chain inet firewall output '{ type filter hook output priority 0; policy drop; }'
nft add chain inet firewall forward '{ type filter hook forward priority 0; policy drop; }'

# Allow loopback
nft add rule inet firewall input  iif lo accept
nft add rule inet firewall output oif lo accept

# Allow inbound SSH + return traffic
nft add rule inet firewall input  tcp dport 22 ct state { new, established } accept
nft add rule inet firewall output tcp sport 22 ct state established accept

# -----------------------------
# Allow DNS (required for pip)
# -----------------------------
nft add rule inet firewall output udp dport 53 ct state { new, established } accept
nft add rule inet firewall input  udp sport 53 ct state established accept

nft add rule inet firewall output tcp dport 53 ct state { new, established } accept
nft add rule inet firewall input  tcp sport 53 ct state established accept

# ----------------------------------------------------
# Allow HTTPS only to Fastly (PyPI CDN)
# Official Fastly IP ranges (IPv4 + IPv6)
# ----------------------------------------------------

# IPv4 Fastly ranges
FASTLY4=(
  23.235.32.0/20
  43.249.72.0/22
  103.244.50.0/24
  103.245.222.0/23
  103.245.224.0/24
  104.156.80.0/20
  146.75.0.0/16
  151.101.0.0/16
  157.52.64.0/18
  172.111.64.0/18
  185.31.16.0/22
)

for net in "${FASTLY4[@]}"; do
  nft add rule inet firewall output ip daddr $net tcp dport 443 ct state { new, established } accept
  nft add rule inet firewall input  ip saddr $net tcp sport 443 ct state established accept
done

# IPv6 Fastly
nft add rule inet firewall output ip6 daddr 2a04:4e40::/32 tcp dport 443 ct state { new, established } accept
nft add rule inet firewall input  ip6 saddr 2a04:4e40::/32 tcp sport 443 ct state established accept

echo "Firewall locked down. SSH + PyPI‑only pip allowed; all other outbound HTTPS blocked."
