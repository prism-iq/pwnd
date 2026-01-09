#!/bin/bash
# L Investigation - Stop All Services

echo "Stopping all L Investigation services..."

pkill -f "l-extract" 2>/dev/null || true
pkill -f "l-gateway" 2>/dev/null || true
pkill -f "l-search" 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true

echo "All services stopped."
