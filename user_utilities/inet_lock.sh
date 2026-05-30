#!/bin/bash

echo "Applying restrictive nftables firewall..."

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

echo "nftables firewall locked down. Inbound SSH allowed; outbound blocked."
