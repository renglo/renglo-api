#!/usr/bin/env python3
"""
Simple runner script for tank-api.
Handler projects can copy this file and use it to run tank-api locally.
"""

from tank_api import run

if __name__ == "__main__":
    print("🚀 Starting Tank API...")
    print("📍 http://localhost:5000")
    print("🔍 Use Ctrl+C to stop")
    
    run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )

