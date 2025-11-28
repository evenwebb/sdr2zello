"""
Version checking and update management for sdr2zello
Monitors versions of audio cable software, Zello, and sdr2zello itself
"""

import asyncio
import aiohttp
import json
import subprocess
import platform
import re
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class VersionChecker:
    """Manages version checking for all components"""

    def __init__(self):
        self.system = platform.system()
        self.last_check = None
        self.check_interval = timedelta(hours=6)  # Check every 6 hours
        self._version_cache = {}

    async def get_all_versions(self) -> Dict:
        """Get version information for all components"""
        if (self.last_check is None or
            datetime.now() - self.last_check > self.check_interval):
            await self._refresh_version_cache()
            self.last_check = datetime.now()

        return self._version_cache

    async def _refresh_version_cache(self):
        """Refresh the version cache with current data"""
        self._version_cache = {
            'sdr2zello': await self.get_sdr2zello_version(),
            'audio_cable': await self.get_audio_cable_version(),
            'zello': await self.get_zello_version(),
            'last_updated': datetime.now().isoformat()
        }

    async def get_sdr2zello_version(self) -> Dict:
        """Get sdr2zello version information"""
        try:
            # Get current version from __init__.py
            current_version = "1.0.0"  # Default
            try:
                from . import __version__
                current_version = __version__
            except ImportError:
                pass

            # Check for updates on GitHub (simulate for now)
            latest_version = await self._check_github_releases(
                "your-username/sdr2zello"  # Replace with actual repo
            )

            return {
                'name': 'sdr2zello',
                'current': current_version,
                'latest': latest_version or current_version,
                'update_available': latest_version and latest_version != current_version,
                'status': 'installed'
            }

        except Exception as e:
            logger.error(f"Error checking sdr2zello version: {e}")
            return {
                'name': 'sdr2zello',
                'current': '1.0.0',
                'latest': '1.0.0',
                'update_available': False,
                'status': 'unknown'
            }

    async def get_audio_cable_version(self) -> Dict:
        """Get PulseAudio version information (Linux-only)"""
        # Audio cable/PulseAudio only works on Linux
        if self.system != 'Linux':
            return {
                'name': 'Audio Cable',
                'current': None,
                'latest': None,
                'update_available': False,
                'status': 'not_installed'
            }
        
        try:
            return await self._get_pulseaudio_version()
        except Exception as e:
            logger.error(f"Error checking PulseAudio version: {e}")
            return self._unknown_audio_version()


    async def _get_pulseaudio_version(self) -> Dict:
        """Get PulseAudio version on Linux"""
        try:
            # Check PulseAudio version
            result = subprocess.run(["pactl", "--version"], capture_output=True, text=True)

            if result.returncode == 0:
                # Extract version from output
                version_match = re.search(r'(\d+\.\d+)', result.stdout)
                current_version = version_match.group(1) if version_match else "Unknown"

                return {
                    'name': 'PulseAudio',
                    'current': current_version,
                    'latest': current_version,  # System managed
                    'update_available': False,  # Updated via system
                    'status': 'installed'
                }
            else:
                return {
                    'name': 'PulseAudio',
                    'current': None,
                    'latest': None,
                    'update_available': False,
                    'status': 'not_installed'
                }

        except Exception as e:
            logger.error(f"Error checking PulseAudio: {e}")
            return self._unknown_audio_version()

    def _unknown_audio_version(self) -> Dict:
        """Return unknown audio version info"""
        return {
            'name': 'Audio Cable',
            'current': None,
            'latest': None,
            'update_available': False,
            'status': 'unknown'
        }

    async def get_zello_version(self) -> Dict:
        """Get Zello version information (Linux-only)"""
        # Zello only works on Linux
        if self.system != 'Linux':
            return {
                'name': 'Zello',
                'current': None,
                'latest': None,
                'update_available': False,
                'status': 'not_installed'
            }
        
        try:
            return await self._get_zello_linux_version()
        except Exception as e:
            logger.error(f"Error checking Zello version: {e}")
            return self._unknown_zello_version()


    async def _get_zello_linux_version(self) -> Dict:
        """Get Zello version on Linux"""
        try:
            # Check for Snap version
            try:
                result = subprocess.run(["snap", "list", "zello-unofficial"],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Extract version from snap list output
                    lines = result.stdout.split('\n')
                    for line in lines[1:]:  # Skip header
                        if 'zello-unofficial' in line:
                            parts = line.split()
                            current_version = parts[1] if len(parts) > 1 else "Unknown"
                            break
                    else:
                        current_version = "Unknown"

                    return {
                        'name': 'Zello (Snap)',
                        'current': current_version,
                        'latest': current_version,  # Snap manages updates
                        'update_available': False,
                        'status': 'installed'
                    }
            except Exception:
                pass

            # Check for Flatpak version
            try:
                result = subprocess.run(["flatpak", "list", "--app", "com.zello.Zello"],
                                      capture_output=True, text=True)
                if result.returncode == 0 and "com.zello.Zello" in result.stdout:
                    return {
                        'name': 'Zello (Flatpak)',
                        'current': "Installed",
                        'latest': "Installed",
                        'update_available': False,
                        'status': 'installed'
                    }
            except Exception:
                pass

            # Not installed
            return {
                'name': 'Zello',
                'current': None,
                'latest': None,
                'update_available': False,
                'status': 'not_installed'
            }

        except Exception as e:
            logger.error(f"Error checking Zello on Linux: {e}")
            return self._unknown_zello_version()

    def _unknown_zello_version(self) -> Dict:
        """Return unknown Zello version info"""
        return {
            'name': 'Zello',
            'current': None,
            'latest': None,
            'update_available': False,
            'status': 'unknown'
        }

    async def _get_zello_latest_version(self) -> Optional[str]:
        """Get latest Zello version from web"""
        try:
            # This would need to scrape Zello's website or API
            # For now, return a simulated version
            return "5.8.2"  # Example version
        except Exception:
            return None

    async def _check_github_releases(self, repo: str) -> Optional[str]:
        """Check GitHub releases for latest version"""
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        tag_name = data.get('tag_name', '')
                        # Remove 'v' prefix if present
                        version = tag_name.lstrip('v')
                        return version
            return None
        except Exception as e:
            logger.error(f"Error checking GitHub releases for {repo}: {e}")
            return None

    async def check_for_updates(self) -> Dict:
        """Check for updates and return summary"""
        versions = await self.get_all_versions()

        updates_available = []
        for component, info in versions.items():
            if component == 'last_updated':
                continue
            if info.get('update_available', False):
                updates_available.append(component)

        return {
            'updates_available': len(updates_available),
            'components_with_updates': updates_available,
            'all_versions': versions
        }


# Global version checker instance
_version_checker = None


def get_version_checker() -> VersionChecker:
    """Get global version checker instance"""
    global _version_checker
    if _version_checker is None:
        _version_checker = VersionChecker()
    return _version_checker