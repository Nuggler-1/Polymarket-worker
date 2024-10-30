import json
import os
import random
from typing import Dict



def init_stats_file(stats_file: str, stats: dict, clear: bool = False,):
    """Create stats file if it doesn't exist"""
    if not os.path.exists(stats_file) or clear:

        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=4)

def read_stats(private_key: str, stats_file: str) -> int:
    """Read number of actions for specific private key"""

    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
            return stats.get(private_key, 0)
    except json.JSONDecodeError:
        return 0

def update_stats(private_key: str, new_data:dict , stats_file: str):
    """Update stats for specific private key"""

    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
    except json.JSONDecodeError:
        stats = {}
    
    # Update or add new entry
    stats[private_key] = new_data
    
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=4)

def get_all_stats(stats_file: str) -> Dict[str, int]:
    """Get all stats as dictionary"""

    try:
        with open(stats_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}