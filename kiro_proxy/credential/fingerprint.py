"""设备指纹生成"""
import hashlib
import platform
import subprocess
import time
from pathlib import Path
from typing import Optional


def get_raw_machine_id() -> Optional[str]:
    """获取系统原始 Machine ID"""
    system = platform.system()
    
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "IOPlatformUUID" in line:
                    return line.split("=")[1].strip().strip('"').lower()
        
        elif system == "Linux":
            for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
                if Path(path).exists():
                    return Path(path).read_text().strip().lower()
        
        elif system == "Windows":
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000
            )
            lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
            if len(lines) > 1:
                return lines[1].lower()
    except Exception:
        pass
    
    return None


def generate_machine_id(
    profile_arn: Optional[str] = None, 
    client_id: Optional[str] = None
) -> str:
    """生成基于凭证的唯一 Machine ID
    
    每个凭证生成独立的 Machine ID，避免多账号共用同一指纹被检测。
    优先级：profileArn > clientId > 系统硬件 ID
    生成后固定不变（不含时间因子）。
    """
    unique_key = None
    if profile_arn:
        unique_key = profile_arn
    elif client_id:
        unique_key = client_id
    else:
        unique_key = get_raw_machine_id() or "KIRO_DEFAULT_MACHINE"
    
    hasher = hashlib.sha256()
    hasher.update(unique_key.encode())
    
    return hasher.hexdigest()


def generate_telemetry_ids() -> dict:
    """生成完整遥测 ID 集合（与 kiro-account-manager 对齐）
    
    Returns:
        dict with keys:
            machine_id: 64 位十六进制字符串 (SHA256)
            sqm_id: GUID 格式 {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
            dev_device_id: UUID4 小写
    """
    import os
    import uuid
    
    # machine_id: SHA256(random_bytes + timestamp_nanos)
    random_bytes = os.urandom(32)
    hasher = hashlib.sha256()
    hasher.update(random_bytes)
    hasher.update(int(time.time() * 1e9).to_bytes(8, 'little'))
    machine_id = hasher.hexdigest()
    
    # sqm_id: {UUID4-UPPERCASE} — GUID 格式
    sqm_id = "{" + str(uuid.uuid4()).upper() + "}"
    
    # dev_device_id: UUID4 小写
    dev_device_id = str(uuid.uuid4())
    
    return {
        "machine_id": machine_id,
        "sqm_id": sqm_id,
        "dev_device_id": dev_device_id,
    }


def get_kiro_version() -> str:
    """获取 Kiro IDE 版本号"""
    if platform.system() == "Darwin":
        kiro_paths = [
            "/Applications/Kiro.app/Contents/Info.plist",
            str(Path.home() / "Applications/Kiro.app/Contents/Info.plist"),
        ]
        for plist_path in kiro_paths:
            try:
                result = subprocess.run(
                    ["defaults", "read", plist_path, "CFBundleShortVersionString"],
                    capture_output=True, text=True, timeout=5
                )
                version = result.stdout.strip()
                if version:
                    return version
            except Exception:
                pass
    
    return "0.1.25"


def get_system_info() -> tuple:
    """获取系统运行时信息 (os_name, node_version)"""
    system = platform.system()
    
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["sw_vers", "-productVersion"], 
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip() or "14.0"
            os_name = f"macos#{version}"
        except Exception:
            os_name = "macos#14.0"
    elif system == "Linux":
        try:
            result = subprocess.run(
                ["uname", "-r"], 
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip() or "5.15.0"
            os_name = f"linux#{version}"
        except Exception:
            os_name = "linux#5.15.0"
    elif system == "Windows":
        os_name = "windows#10.0"
    else:
        os_name = "other#1.0"
    
    node_version = "20.18.0"
    return os_name, node_version
