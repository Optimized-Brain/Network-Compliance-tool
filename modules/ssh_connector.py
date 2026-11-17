"""
SSH Connector Module
Handles SSH connections to network switches via Netmiko.
Supports direct connections and jump host (bastion) based access.
"""

import logging
import os
import yaml
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False

logger = logging.getLogger(__name__)


class SSHConnector:
    """Manages SSH connections to network switches and retrieves running configs."""

    def __init__(self, inventory_path="config/inventory.yaml"):
        self.inventory_path = inventory_path
        self.inventory = self._load_inventory()
        self.global_defaults = self.inventory.get("global_defaults", {})

    def _load_inventory(self):
        """Load switch inventory from YAML file."""
        try:
            with open(self.inventory_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Inventory file not found: {self.inventory_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing inventory YAML: {e}")
            raise

    def reload_inventory(self):
        """Reload inventory from file (useful after edits)."""
        self.inventory = self._load_inventory()
        self.global_defaults = self.inventory.get("global_defaults", {})

    def get_all_switches(self):
        """Return a flat list of all switches with their region/location info."""
        switches = []
        for region_block in self.inventory.get("regions", []):
            region = region_block.get("region", "Unknown")
            location = region_block.get("location", "Unknown")
            for switch in region_block.get("switches", []):
                switch_info = {
                    "name": switch.get("name", "Unknown"),
                    "hostname": switch.get("hostname", ""),
                    "device_type": switch.get("device_type", self.global_defaults.get("device_type", "cisco_ios")),
                    "region": region,
                    "location": location,
                    "username": switch.get("username", self.global_defaults.get("username", "")),
                    "password": switch.get("password", self.global_defaults.get("password", "")),
                    "secret": switch.get("secret", self.global_defaults.get("secret", "")),
                    "port": switch.get("port", self.global_defaults.get("port", 22)),
                    "timeout": switch.get("timeout", self.global_defaults.get("timeout", 30)),
                }
                switches.append(switch_info)
        return switches

    def _build_connection_params(self, switch):
        """Build Netmiko connection parameters for a switch."""
        params = {
            "device_type": switch["device_type"],
            "host": switch["hostname"],
            "username": switch["username"],
            "password": switch["password"],
            "secret": switch.get("secret", ""),
            "port": switch.get("port", 22),
            "timeout": switch.get("timeout", 30),
            "fast_cli": False,
            "session_log": None,
        }

        # Jump host / bastion support
        jump_host = self.global_defaults.get("jump_host")
        if jump_host:
            params["sock"] = self._create_jump_channel(jump_host, switch["hostname"], switch.get("port", 22))

        return params

    def _create_jump_channel(self, jump_host_config, target_host, target_port):
        """Create an SSH channel through the jump/bastion host."""
        import paramiko

        jump = paramiko.SSHClient()
        jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump.connect(
            hostname=jump_host_config["hostname"],
            username=jump_host_config["username"],
            password=jump_host_config.get("password", ""),
            port=jump_host_config.get("port", 22),
            timeout=30,
        )
        transport = jump.get_transport()
        dest_addr = (target_host, target_port)
        local_addr = ("127.0.0.1", 0)
        channel = transport.open_channel("direct-tcpip", dest_addr, local_addr)
        return channel

    def _check_port_open(self, hostname, port, timeout=5):
        """Quick TCP check to see if a switch is reachable."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((hostname, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def get_running_config(self, switch):
        """
        Connect to a single switch and retrieve its running configuration.
        Returns dict with status, config, and error info.
        """
        result = {
            "name": switch["name"],
            "hostname": switch["hostname"],
            "region": switch.get("region", "Unknown"),
            "location": switch.get("location", "Unknown"),
            "device_type": switch["device_type"],
            "status": "unknown",
            "config": "",
            "error": "",
            "timestamp": datetime.now().isoformat(),
            "collection_time_sec": 0,
        }

        if not NETMIKO_AVAILABLE:
            result["status"] = "error"
            result["error"] = "Netmiko library not installed. Install with: pip install netmiko"
            return result

        start_time = datetime.now()

        try:
            logger.info(f"Connecting to {switch['name']} ({switch['hostname']})...")

            # Quick reachability check
            if not self._check_port_open(switch["hostname"], switch.get("port", 22)):
                result["status"] = "unreachable"
                result["error"] = f"Port {switch.get('port', 22)} not reachable on {switch['hostname']}"
                return result

            params = self._build_connection_params(switch)
            connection = ConnectHandler(**params)

            # Enter enable mode if needed
            if switch.get("secret"):
                try:
                    connection.enable()
                except Exception:
                    pass  # Already in enable mode or not needed

            # Get running config
            config = connection.send_command("show running-config", read_timeout=60)

            # Also try to get version info for context
            try:
                version_info = connection.send_command("show version", read_timeout=30)
                result["version_info"] = version_info
            except Exception:
                result["version_info"] = ""

            connection.disconnect()

            result["status"] = "success"
            result["config"] = config
            elapsed = (datetime.now() - start_time).total_seconds()
            result["collection_time_sec"] = round(elapsed, 2)

            logger.info(f"Successfully collected config from {switch['name']} in {elapsed:.1f}s")

        except NetmikoTimeoutException:
            result["status"] = "timeout"
            result["error"] = f"SSH connection timed out to {switch['hostname']}"
            logger.warning(f"Timeout connecting to {switch['name']}")

        except NetmikoAuthenticationException:
            result["status"] = "auth_failed"
            result["error"] = f"Authentication failed for {switch['hostname']}"
            logger.warning(f"Auth failed for {switch['name']}")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Error connecting to {switch['name']}: {e}")

        return result

    def collect_all_configs(self, max_workers=10, progress_callback=None):
        """
        Collect running configs from all switches in parallel.
        
        Args:
            max_workers: Max concurrent SSH sessions
            progress_callback: Optional function(completed, total, switch_name, status)
        
        Returns:
            List of result dicts for each switch
        """
        switches = self.get_all_switches()
        total = len(switches)
        results = []
        completed = 0

        logger.info(f"Starting config collection from {total} switches (max {max_workers} concurrent)...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_switch = {
                executor.submit(self.get_running_config, switch): switch
                for switch in switches
            }

            for future in as_completed(future_to_switch):
                switch = future_to_switch[future]
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                    if progress_callback:
                        progress_callback(completed, total, result["name"], result["status"])
                except Exception as e:
                    error_result = {
                        "name": switch["name"],
                        "hostname": switch["hostname"],
                        "region": switch.get("region", "Unknown"),
                        "location": switch.get("location", "Unknown"),
                        "status": "error",
                        "config": "",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    }
                    results.append(error_result)
                    if progress_callback:
                        progress_callback(completed, total, switch["name"], "error")

        # Sort by region, then location, then name
        results.sort(key=lambda x: (x.get("region", ""), x.get("location", ""), x.get("name", "")))

        logger.info(f"Config collection complete. {sum(1 for r in results if r['status'] == 'success')}/{total} successful")
        return results


class DemoSSHConnector(SSHConnector):
    """
    Demo connector that generates realistic sample configs for testing
    without requiring actual network access.
    """

    def __init__(self, inventory_path="config/inventory.yaml"):
        super().__init__(inventory_path)

    def get_running_config(self, switch):
        """Generate a demo running config with random compliance gaps."""
        import random
        import time

        # Simulate connection delay
        time.sleep(random.uniform(0.1, 0.5))

        # Base compliant config template
        compliant_sections = {
            "header": f"""!
! Last configuration change at 10:30:45 IST Mon Nov 17 2024
! NVRAM config last updated at 10:31:02 IST Mon Nov 17 2024
!
version 17.6
service timestamps debug datetime msec localtime show-timezone
service timestamps log datetime msec localtime show-timezone
service password-encryption
!
hostname {switch['name']}
!""",

            "aaa": """!
aaa new-model
aaa authentication login default group tacacs+ local
aaa authentication enable default group tacacs+ enable
aaa authentication dot1x default group radius
aaa authorization exec default group tacacs+ local
aaa authorization commands 15 default group tacacs+ local
aaa authorization network default group radius
aaa accounting exec default start-stop group tacacs+
aaa accounting commands 15 default start-stop group tacacs+
!""",

            "user": """!
username admin privilege 15 secret 9 $9$xxxxxxxxxxxxxxxxxxxx
!""",

            "ssh": """!
ip ssh version 2
ip ssh time-out 60
ip ssh authentication-retries 3
ip ssh rsa keypair-name SSH-KEYS
!""",

            "hardening": """!
no ip http server
no ip http secure-server
no cdp run
no ip source-route
no ip finger
no service tcp-small-servers
no service udp-small-servers
no ip bootp server
no ip domain-lookup
no ip gratuitous-arps
!""",

            "logging": """!
logging buffered 65536 informational
logging console critical
logging host 10.100.1.10
logging host 10.100.1.11
logging source-interface Loopback0
!""",

            "ntp": """!
ntp authenticate
ntp authentication-key 1 md5 073E25767E7A3A
ntp trusted-key 1
ntp source Loopback0
ntp server 10.100.1.20
ntp server 10.100.1.21
!""",

            "snmp": """!
snmp-server group SNMPV3GRP v3 priv
snmp-server user snmpuser SNMPV3GRP v3 auth sha AuthPass priv aes 128 PrivPass
snmp-server enable traps
no snmp-server community public
no snmp-server community private
!""",

            "tacacs": """!
tacacs server TACACS-PRIMARY
 address ipv4 10.100.1.30
 key 7 045E0A0A1D3A2B
tacacs server TACACS-SECONDARY
 address ipv4 10.100.1.31
 key 7 045E0A0A1D3A2B
!""",

            "radius": """!
radius server RADIUS-PRIMARY
 address ipv4 10.100.1.40 auth-port 1812 acct-port 1813
 key 7 096E4A0A2C4B5D
radius server RADIUS-SECONDARY
 address ipv4 10.100.1.41 auth-port 1812 acct-port 1813
 key 7 096E4A0A2C4B5D
radius-server dead-criteria time 10 tries 3
radius-server deadtime 15
!""",

            "dot1x": """!
dot1x system-auth-control
!""",

            "l2_security": """!
ip dhcp snooping
ip dhcp snooping vlan 10-100
ip arp inspection vlan 10-100
spanning-tree portfast bpduguard default
spanning-tree portfast default
!""",

            "banner": """!
banner login ^
*************************************************************
* WARNING: This system is for authorized use only.          *
* All activity is monitored, logged, and subject to audit.  *
* Unauthorized access will be prosecuted.                   *
*************************************************************
^
banner motd ^
Unauthorized access is prohibited. Disconnect immediately.
^
banner exec ^
This system is for authorized use only.
^
!""",

            "acl": """!
ip access-list standard VTY-ACL
 permit 10.100.0.0 0.0.255.255
 deny any log
ip access-list standard SNMP-ACL
 permit host 10.100.1.10
 permit host 10.100.1.11
 deny any log
!""",

            "vty": """!
line con 0
 exec-timeout 5 0
 logging synchronous
 login authentication default
line aux 0
 no exec
 transport input none
line vty 0 4
 access-class VTY-ACL in
 exec-timeout 10 0
 transport input ssh
line vty 5 15
 access-class VTY-ACL in
 exec-timeout 10 0
 transport input ssh
!""",

            "interfaces": """!
interface Loopback0
 ip address 10.200.1.1 255.255.255.255
!
interface Vlan10
 description Management-VLAN
 ip address 10.10.1.1 255.255.255.0
!
interface GigabitEthernet1/0/1
 description Uplink-to-Core
 switchport mode trunk
 spanning-tree guard root
!
interface GigabitEthernet1/0/2
 description Access-Port-User
 switchport access vlan 20
 switchport mode access
 authentication host-mode multi-auth
 authentication order dot1x mab
 authentication priority dot1x mab
 authentication violation restrict
 authentication periodic
 authentication timer reauthenticate server
 mab
 dot1x pam authenticator
 dot1x timeout tx-period 10
 spanning-tree portfast
 storm-control broadcast level 20.00
 ip verify source
!
interface GigabitEthernet1/0/48
 description UNUSED
 shutdown
 switchport access vlan 999
!""",

            "management": """!
login block-for 120 attempts 3 within 60
login on-failure log every 3
login on-success log
!
enable secret 9 $9$yyyyyyyyyyyyyyyyyyyy
!""",

            "footer": """!
end"""
        }

        # Randomly remove some sections to simulate non-compliance
        # Different switches have different levels of compliance
        random.seed(hash(switch["name"]))
        compliance_level = random.choice(["high", "high", "medium", "medium", "low"])

        sections_to_potentially_remove = []
        if compliance_level == "high":
            # 85-95% compliant - minor issues
            sections_to_potentially_remove = random.sample(
                ["banner", "ntp"],
                k=random.randint(0, 1)
            )
        elif compliance_level == "medium":
            # 60-80% compliant - several issues
            sections_to_potentially_remove = random.sample(
                ["dot1x", "l2_security", "snmp", "banner", "ntp", "management"],
                k=random.randint(2, 3)
            )
        else:
            # 40-60% compliant - many issues
            sections_to_potentially_remove = random.sample(
                ["dot1x", "l2_security", "snmp", "banner", "ntp", "radius",
                 "management", "acl", "hardening"],
                k=random.randint(3, 5)
            )

        # Build config
        config_parts = []
        for section_name, section_content in compliant_sections.items():
            if section_name in sections_to_potentially_remove:
                # Add partial/broken config for this section
                if section_name == "snmp":
                    config_parts.append("!\nsnmp-server community public RO\nsnmp-server community private RW\n!")
                elif section_name == "hardening":
                    config_parts.append("!\nip http server\n!")
                elif section_name == "banner":
                    pass  # Completely missing
                elif section_name == "ntp":
                    config_parts.append("!\nntp server 10.100.1.20\n!")  # No auth
                elif section_name == "management":
                    config_parts.append("!\nenable password cisco123\n!")
                elif section_name == "l2_security":
                    pass  # Missing DHCP snooping, DAI
                elif section_name == "dot1x":
                    pass  # Missing 802.1X
                elif section_name == "acl":
                    pass  # Missing ACLs
                elif section_name == "radius":
                    pass  # Missing RADIUS
            else:
                config_parts.append(section_content)

        config = "\n".join(config_parts)

        # Simulate random success/failure
        if random.random() < 0.05:  # 5% chance of connection failure
            status = random.choice(["timeout", "unreachable", "auth_failed"])
            return {
                "name": switch["name"],
                "hostname": switch["hostname"],
                "region": switch.get("region", "Unknown"),
                "location": switch.get("location", "Unknown"),
                "device_type": switch["device_type"],
                "status": status,
                "config": "",
                "error": f"Simulated {status} for demo",
                "timestamp": datetime.now().isoformat(),
                "collection_time_sec": round(random.uniform(0.5, 5.0), 2),
            }

        return {
            "name": switch["name"],
            "hostname": switch["hostname"],
            "region": switch.get("region", "Unknown"),
            "location": switch.get("location", "Unknown"),
            "device_type": switch["device_type"],
            "status": "success",
            "config": config,
            "error": "",
            "timestamp": datetime.now().isoformat(),
            "collection_time_sec": round(random.uniform(1.0, 8.0), 2),
        }
