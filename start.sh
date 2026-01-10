#!/bin/bash
echo "Starting PWND.ICU services..."
sudo systemctl start pwnd-llm pwnd-api caddy
sleep 2
echo ""
echo "Services status:"
systemctl is-active pwnd-llm pwnd-api caddy
echo ""
echo "Access: http://localhost or https://your-domain"
