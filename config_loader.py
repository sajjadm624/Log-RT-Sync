#!/usr/bin/env python3
"""
Configuration loader for Log-RT-Sync
Loads and validates configuration from YAML file
"""

import os
import sys
import yaml
from typing import Dict, Any, Optional


class ConfigLoader:
    """Load and manage configuration from YAML file"""
    
    DEFAULT_CONFIG_PATHS = [
        "/etc/log-rt-sync/config.yaml",
        "/etc/log-rt-sync.yaml",
        "./config.yaml",
        os.path.expanduser("~/.log-rt-sync.yaml"),
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration loader
        
        Args:
            config_path: Path to config file. If None, searches default locations.
        """
        self.config_path = config_path
        self.config = {}
        self._load_config()
    
    def _find_config_file(self) -> Optional[str]:
        """Find configuration file in default locations"""
        if self.config_path and os.path.exists(self.config_path):
            return self.config_path
        
        for path in self.DEFAULT_CONFIG_PATHS:
            if os.path.exists(path):
                return path
        
        return None
    
    def _load_config(self):
        """Load configuration from YAML file"""
        config_file = self._find_config_file()
        
        if not config_file:
            # No config file found, use defaults
            self.config = self._get_default_config()
            return
        
        try:
            with open(config_file, 'r') as f:
                self.config = yaml.safe_load(f) or {}
            # Only print to stderr when not being used for export
            if not os.environ.get('CONFIG_SILENT'):
                print(f"Loaded configuration from: {config_file}", file=sys.stderr)
        except Exception as e:
            print(f"Error loading config file {config_file}: {e}", file=sys.stderr)
            print("Using default configuration", file=sys.stderr)
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration"""
        return {
            'log_shipper': {
                'log_file': '/app/log/nginx/access.log',
                'offset_file': '/app/log/nginx/log-shipper/latest.offset',
                'chunk_size': 10000,
                'receiver_url': 'http://10.10.23.212:5000/upload',
                'logging_file': '/app/log/nginx/log-shipper/log_shipper_status.log',
                'debounce_delay': 1.0,
                'retry_attempts': 600,
                'retry_wait_seconds': 6,
            },
            'log_receiver': {
                'base_log_dir': '/app/log/access-log-reciever/',
                'port': 5000,
                'host': '0.0.0.0',
                'time_windows': [
                    {'start': 0, 'end': 19, 'label': '00-19'},
                    {'start': 20, 'end': 39, 'label': '20-39'},
                    {'start': 40, 'end': 59, 'label': '40-59'},
                ],
            },
            'log_sender': {
                'source_dir': '/app/log/access-log-reciever',
                'destination': {
                    'user': 'mygp1',
                    'host': '10.12.3.3',
                    'port': 22022,
                    'directory': '/cdrdata/oracle/ProdEDW/source_data/MYGP',
                    'password': '9Z@pfKV}3y!v',
                },
                'archive_dir': '/app/log/access-log-reciever/sent',
                'failed_dir': '/app/log/access-log-reciever/failed',
                'sleep_seconds': 60,
                'max_retries': 3,
                'file_pattern': 'MyGP_accessLog_*.log',
                'min_file_age_minutes': 2,
            },
            'log_monitoring': {
                'log_base_dir': '/app/log/access-log-reciever/',
                'threshold_minutes': 5,
                'email': {
                    'smtp_host': '192.168.207.212',
                    'smtp_port': 25,
                    'from_address': 'mygp-devops@grameenphone.com',
                    'recipients': ['sazzad.manik@miaki.com.bd'],
                    'subject_prefix': '[Nginx Access Log Sync Monitor and Hourly report]',
                    'timeout': 15,
                },
            },
            'housekeeping': {
                'base_dir': '/app/log/access-log-reciever',
                'compress_after_hours': 3,
                'delete_after_hours': 4,
            },
            'global': {
                'debug': False,
                'timezone': 'UTC',
            }
        }
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Path to config key (e.g., 'log_shipper.chunk_size')
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section
        
        Args:
            section: Section name (e.g., 'log_shipper')
        
        Returns:
            Configuration section dictionary
        """
        return self.config.get(section, {})
    
    def validate(self) -> bool:
        """
        Validate configuration
        
        Returns:
            True if configuration is valid
        """
        required_sections = ['log_shipper', 'log_receiver', 'log_sender', 'log_monitoring']
        
        for section in required_sections:
            if section not in self.config:
                print(f"Warning: Missing configuration section: {section}", file=sys.stderr)
                return False
        
        return True


def load_config(config_path: Optional[str] = None) -> ConfigLoader:
    """
    Convenience function to load configuration
    
    Args:
        config_path: Optional path to config file
    
    Returns:
        ConfigLoader instance
    """
    return ConfigLoader(config_path)


if __name__ == "__main__":
    # Test configuration loader
    import argparse
    
    parser = argparse.ArgumentParser(description="Test configuration loader")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("-s", "--section", help="Show specific section")
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    if args.section:
        section_data = config.get_section(args.section)
        import json
        print(json.dumps(section_data, indent=2))
    else:
        import json
        print(json.dumps(config.config, indent=2))
