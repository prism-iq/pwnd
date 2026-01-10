#!/bin/bash
# L Investigation - Install Systemd Services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing L Investigation services..."

# Copy service files
sudo cp "$SCRIPT_DIR"/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
for svc in l-cells l-brain l-lungs l-veins l-discord; do
    sudo systemctl enable $svc 2>/dev/null || true
    echo "  Enabled: $svc"
done

echo ""
echo "Services installed. Start with:"
echo "  sudo systemctl start l-cells l-brain l-lungs l-veins"
echo ""
echo "Check status:"
echo "  sudo systemctl status l-cells l-brain l-lungs l-veins"
echo ""
echo "Discord bot (needs DISCORD_TOKEN in .env):"
echo "  sudo systemctl start l-discord"
