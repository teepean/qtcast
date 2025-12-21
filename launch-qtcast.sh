#!/bin/bash
# QtCast launcher script

cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -e .
else
    source venv/bin/activate
fi

# Launch QtCast with unbuffered output for console logging
PYTHONUNBUFFERED=1 python3 -m qtcast "$@"
