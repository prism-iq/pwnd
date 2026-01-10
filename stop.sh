#!/bin/bash
echo "Stopping PWND.ICU services..."
sudo systemctl stop pwnd-llm pwnd-api caddy pwnd-auto
echo "Done."
