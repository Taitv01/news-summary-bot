#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration settings
"""

import json
import os

DEFAULT_CONFIG = {
    "max_retries": 3,
    "request_timeout": 15,
    "delay_between_requests": [1, 3],
    "rate_limit_delay": [2, 5],
    "max_content_length": 50000,
    "min_content_length": 100,
    "log_level": "INFO"
}

def load_config():
    """Load configuration từ file hoặc sử dụng mặc định"""
    config_file = "config.json"
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                return {**DEFAULT_CONFIG, **user_config}
        except Exception as e:
            print(f"Lỗi đọc config: {e}. Sử dụng config mặc định.")
    
    return DEFAULT_CONFIG

def create_default_config():
    """Tạo file config mặc định"""
    with open("config.json", 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    print("Đã tạo file config.json mặc định")
