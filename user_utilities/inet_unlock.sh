#!/bin/bash

echo "Removing restrictive nftables firewall..."

# Flush ruleset
nft flush ruleset

# Optionally restore an empty table (not required)
# nft add table inet firewall

echo "nftables firewall removed. All traffic allowed."
