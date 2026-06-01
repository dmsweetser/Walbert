#!/bin/bash

echo "Removing restrictive nftables firewall..."

# Flush ruleset
nft flush ruleset 2>/dev/null || true

echo "nftables firewall removed. All traffic allowed."
