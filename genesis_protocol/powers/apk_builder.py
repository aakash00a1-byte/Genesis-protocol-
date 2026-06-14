"""Genesis Protocol - APK Builder

Android APK building automation and management.
"""

import os
import subprocess
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.apk_builder")


@dataclass
class APKBuildResult:
    """Result of APK build."""
    success: bool
    apk_path: Optional[str]
    size_mb: float
    build_time_seconds: float
    output: str
    error: Optional[str] = None


class APKBuilder:
    """
    Android APK building system.
    
    Capabilities:
    - Check Android SDK availability
    - Build debug APKs
    - Build release APKs
    - Sign APKs
    - List connected devices
    - Install APK to device
    """

    def __init__(self):
        """Initialize APK builder."""
        self.sdk_path = os.environ.get("ANDROID_HOME", "/usr/lib/android-sdk")
        self.gradle_available = self._check_gradle()
        self.sdk_available = self._check_sdk()
        logger.info(f"APK Builder initialized - SDK: {self.sdk_available}, Gradle: {self.gradle_available}")

    def _check_gradle(self) -> bool:
        """Check if Gradle is available."""
        try:
            result = subprocess.run(
                ["gradle", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def _check_sdk(self) -> bool:
        """Check if Android SDK is available."""
        return os.path.exists(self.sdk_path)

    def get_status(self) -> Dict[str, bool]:
        """Get builder status."""
        return {
            "sdk_available": self.sdk_available,
            "gradle_available": self.gradle_available,
            "build_tools_installed": self._check_build_tools(),
            "platforms_installed": self._check_platforms()
        }

    def _check_build_tools(self) -> bool:
        """Check if build tools are installed."""
        build_tools = os.path.join(self.sdk_path, "build-tools")
        return os.path.exists(build_tools)

    def _check_platforms(self) -> bool:
        """Check if platforms are installed."""
        platforms = os.path.join(self.sdk_path, "platforms")
        return os.path.exists(platforms)

    def list_devices(self) -> List[Dict[str, str]]:
        """List connected Android devices."""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            devices = []
            lines = result.stdout.strip().split('\n')[1:]
            
            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        devices.append({
                            "id": parts[0],
                            "status": parts[1]
                        })
            
            return devices
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            return []

    def build_apk(
        self,
        project_path: str,
        variant: str = "debug",
        clean: bool = False
    ) -> APKBuildResult:
        """
        Build an Android APK.
        
        Args:
            project_path: Path to Android project
            variant: Build variant (debug/release)
            clean: Whether to clean before building
            
        Returns:
            APKBuildResult with build status
        """
        import time
        start_time = time.time()
        
        if not os.path.exists(project_path):
            return APKBuildResult(
                success=False,
                apk_path=None,
                size_mb=0,
                build_time_seconds=0,
                output="",
                error=f"Project path does not exist: {project_path}"
            )
        
        try:
            # Change to project directory
            original_dir = os.getcwd()
            os.chdir(project_path)
            
            # Build command
            cmd = ["gradle", f":app:assemble{variant.capitalize()}"]
            
            if clean:
                subprocess.run(["gradle", "clean"], check=True)
            
            # Run build
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            os.chdir(original_dir)
            
            build_time = time.time() - start_time
            
            if result.returncode == 0:
                # Find the APK
                apk_path = self._find_apk(project_path, variant)
                size_mb = os.path.getsize(apk_path) / (1024 * 1024) if apk_path and os.path.exists(apk_path) else 0
                
                return APKBuildResult(
                    success=True,
                    apk_path=apk_path,
                    size_mb=round(size_mb, 2),
                    build_time_seconds=round(build_time, 1),
                    output=result.stdout
                )
            else:
                return APKBuildResult(
                    success=False,
                    apk_path=None,
                    size_mb=0,
                    build_time_seconds=round(build_time, 1),
                    output=result.stdout,
                    error=result.stderr
                )
                
        except subprocess.TimeoutExpired:
            return APKBuildResult(
                success=False,
                apk_path=None,
                size_mb=0,
                build_time_seconds=300,
                output="",
                error="Build timed out after 5 minutes"
            )
        except Exception as e:
            return APKBuildResult(
                success=False,
                apk_path=None,
                size_mb=0,
                build_time_seconds=0,
                output="",
                error=str(e)
            )

    def _find_apk(self, project_path: str, variant: str) -> Optional[str]:
        """Find built APK path."""
        # Common APK output locations
        search_paths = [
            f"{project_path}/app/build/outputs/apk/{variant}/app-{variant}.apk",
            f"{project_path}/app/build/outputs/apk/debug/app-debug.apk",
            f"{project_path}/app/build/outputs/apk/release/app-release-unsigned.apk",
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        # Search for any APK
        for root, dirs, files in os.walk(f"{project_path}/app/build/outputs"):
            for file in files:
                if file.endswith('.apk'):
                    return os.path.join(root, file)
        
        return None

    def install_apk(self, apk_path: str, device_id: str = None) -> bool:
        """Install APK to connected device."""
        try:
            cmd = ["adb"]
            if device_id:
                cmd.extend(["-s", device_id])
            cmd.extend(["install", "-r", apk_path])  # -r for reinstall
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0 and "Success" in result.stdout
        except Exception as e:
            logger.error(f"Failed to install APK: {e}")
            return False

    def create_basic_project(self, project_name: str, output_path: str) -> bool:
        """Create a basic Android project structure."""
        try:
            # Create directory structure
            dirs = [
                f"{output_path}/{project_name}/app/src/main/java/com/example/{project_name}",
                f"{output_path}/{project_name}/app/src/main/res/layout",
                f"{output_path}/{project_name}/app/src/main/res/values",
                f"{output_path}/{project_name}/gradle/wrapper",
            ]
            
            for d in dirs:
                os.makedirs(d, exist_ok=True)
            
            # Create build.gradle
            build_gradle = f'''// Top-level build file
plugins {{
    id 'com.android.application' version '8.1.0' apply false
    id 'org.jetbrains.kotlin.android' version '1.9.0' apply false
}}

allprojects {{
    repositories {{
        google()
        mavenCentral()
    }}
}}

task clean(type: Delete) {{
    delete rootProject.buildDir
}}
'''
            
            with open(f"{output_path}/{project_name}/build.gradle", "w") as f:
                f.write(build_gradle)
            
            # Create app/build.gradle
            app_build = f'''plugins {{
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
}}

android {{
    namespace 'com.example.{project_name}'
    compileSdk 34

    defaultConfig {{
        applicationId "com.example.{project_name}"
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }}

    buildTypes {{
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }}
    }}
    
    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }}
}}

dependencies {{
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
}}
'''
            
            with open(f"{output_path}/{project_name}/app/build.gradle", "w") as f:
                f.write(app_build)
            
            # Create settings.gradle
            with open(f"{output_path}/{project_name}/settings.gradle", "w") as f:
                f.write(f'''pluginManagement {{
    repositories {{
        google()
        mavenCentral()
        gradlePluginPortal()
    }}
}}
include ':app'
''')
            
            # Create AndroidManifest.xml
            manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="true"
        android:label="{project_name}"
        android:supportsRtl="true"
        android:theme="@style/Theme.Material3.DayNight">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
'''
            
            with open(f"{output_path}/{project_name}/app/src/main/AndroidManifest.xml", "w") as f:
                f.write(manifest)
            
            # Create MainActivity.kt
            main_activity = f'''package com.example.{project_name}

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        // Your app code here
    }}
}}
'''
            
            with open(f"{output_path}/{project_name}/app/src/main/java/com/example/{project_name}/MainActivity.kt", "w") as f:
                f.write(main_activity)
            
            logger.info(f"Created basic Android project at {output_path}/{project_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            return False


# Singleton
_apk_builder: Optional[APKBuilder] = None


def get_apk_builder() -> APKBuilder:
    """Get or create APKBuilder singleton."""
    global _apk_builder
    if _apk_builder is None:
        _apk_builder = APKBuilder()
    return _apk_builder