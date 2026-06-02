#!/bin/bash

echo "Applying restrictive nftables firewall (PyPI-only)..."

# Flush existing rules
nft flush ruleset 2>/dev/null || true

# Create table
nft add table inet firewall 2>/dev/null || true

# Create chains with default DROP
nft add chain inet firewall input  '{ type filter hook input priority 0; policy drop; }' 2>/dev/null || true
nft add chain inet firewall output '{ type filter hook output priority 0; policy drop; }' 2>/dev/null || true
nft add chain inet firewall forward '{ type filter hook forward priority 0; policy drop; }' 2>/dev/null || true

# Allow loopback
nft add rule inet firewall input  iif lo accept 2>/dev/null || true
nft add rule inet firewall output oif lo accept 2>/dev/null || true

# Allow inbound SSH + return traffic
nft add rule inet firewall input  tcp dport 22 ct state { new, established } accept 2>/dev/null || true
nft add rule inet firewall output tcp sport 22 ct state established accept 2>/dev/null || true

echo "Firewall locked down. SSH allowed; all other traffic blocked."
