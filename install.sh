#!/bin/bash
# QtCast installation script

set -e

echo "=== QtCast Installation ==="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "Warning: ffmpeg is not installed"
    echo "Install with: sudo apt install ffmpeg"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate and install
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -e .

echo ""
echo "=== Installation Complete! ==="
echo ""
echo "To run QtCast:"
echo "  ./launch-qtcast.sh"
echo ""
echo "Or manually:"
echo "  source venv/bin/activate"
echo "  python3 -m qtcast"
