#!/usr/bin/env python3
"""
Simple runner script for renglo-api.
Handler projects can copy this file and use it to run renglo-api locally.
"""

from renglo_api import run

if __name__ == "__main__":
    print("🚀 Starting Renglo API...")
    print("📍 http://localhost:5000")
    print("🔍 Use Ctrl+C to stop")
    
    run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )

