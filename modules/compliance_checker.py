"""
Compliance Checker Module
Compares running configs against the golden template rules.
Supports multiple check types: regex_present, regex_absent,
section_check, conditional_present, and custom checks.
"""

import re
import logging
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)


class ComplianceChecker:
    """Checks switch configs against golden template compliance rules."""

    def __init__(self, template_path="config/golden_template.yaml"):
        self.template_path = template_path
        self.template = self._load_template()
        self.categories = self.template.get("categories", [])

    def _load_template(self):
        """Load golden template from YAML file."""
        try:
            with open(self.template_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Golden template not found: {self.template_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing golden template YAML: {e}")
            raise

    def reload_template(self):
        """Reload template from file."""
        self.template = self._load_template()
        self.categories = self.template.get("categories", [])

    def get_all_rules(self):
        """Return flat list of all rules with their category info."""
        rules = []
        for category in self.categories:
            for rule in category.get("rules", []):
                rule_copy = dict(rule)
                rule_copy["category_name"] = category["name"]
                rule_copy["category_id"] = category["id"]
                rules.append(rule_copy)
        return rules

    def get_rule_count(self):
        """Return total number of compliance rules."""
        return sum(len(cat.get("rules", [])) for cat in self.categories)

    def _check_regex_present(self, config_lines, config_text, patterns):
        """Check that at least one pattern matches somewhere in the config."""
        for pattern in patterns:
            regex = re.compile(pattern, re.MULTILINE)
            if regex.search(config_text):
                return True, f"Pattern found: {pattern}"
        return False, f"Required pattern(s) not found in running config"

    def _check_regex_absent(self, config_lines, config_text, patterns):
        """Check that NONE of the patterns exist in the config."""
        for pattern in patterns:
            regex = re.compile(pattern, re.MULTILINE)
            match = regex.search(config_text)
            if match:
                return False, f"Prohibited pattern found: '{match.group().strip()}'"
        return True, "No prohibited patterns found"

    def _check_section_check(self, config_lines, config_text, rule):
        """Check for patterns within a specific config section."""
        section_start = rule.get("section_start", "")
        section_end = rule.get("section_end", "")
        patterns = rule.get("patterns", [])

        # Find all matching sections
        in_section = False
        section_text = ""
        section_found = False

        for line in config_lines:
            if re.match(section_start, line):
                in_section = True
                section_found = True
                section_text += line + "\n"
                continue
            if in_section:
                if section_end and re.match(section_end, line):
                    in_section = False
                    # Check patterns in this section
                    for pattern in patterns:
                        if re.search(pattern, section_text, re.MULTILINE):
                            return True, f"Required config found in section"
                    section_text = ""
                else:
                    section_text += line + "\n"

        # Check last section if still open
        if in_section and section_text:
            for pattern in patterns:
                if re.search(pattern, section_text, re.MULTILINE):
                    return True, f"Required config found in section"

        if not section_found:
            return False, f"Section '{section_start}' not found in config"

        return False, f"Required pattern(s) not found in section '{section_start}'"

    def _check_conditional_present(self, config_lines, config_text, rule):
        """Check patterns only if condition patterns are met (e.g., if OSPF is configured)."""
        condition_patterns = rule.get("condition_patterns", [])
        patterns = rule.get("patterns", [])

        # Check if condition is met
        condition_met = False
        for cp in condition_patterns:
            if re.search(cp, config_text, re.MULTILINE):
                condition_met = True
                break

        if not condition_met:
            return True, "N/A - Feature not configured (condition not met)"

        # Condition is met, now check the required patterns
        for pattern in patterns:
            if re.search(pattern, config_text, re.MULTILINE):
                return True, "Required security config found for the protocol"

        return False, "Protocol is configured but security/authentication is missing"

    def _check_custom(self, config_lines, config_text, rule):
        """Handle custom compliance checks."""
        custom_check = rule.get("custom_check", "")

        if custom_check == "snmp_community_acl":
            return self._custom_snmp_community_acl(config_text)
        elif custom_check == "unused_ports_shutdown":
            return self._custom_unused_ports(config_text)
        else:
            return True, f"Custom check '{custom_check}' not implemented (skipped)"

    def _custom_snmp_community_acl(self, config_text):
        """Check that all SNMP community strings have ACL restrictions."""
        community_lines = re.findall(r'^snmp-server community \S+.*$', config_text, re.MULTILINE)
        if not community_lines:
            return True, "No SNMP community strings configured"

        for line in community_lines:
            # Pattern: snmp-server community <string> <RO/RW> [ACL-name/number]
            parts = line.split()
            if len(parts) < 5:  # Missing ACL
                return False, f"SNMP community without ACL restriction: '{line.strip()}'"

        return True, "All SNMP community strings have ACL restrictions"

    def _custom_unused_ports(self, config_text):
        """Check that there are shutdown ports (indicating unused ports are disabled)."""
        shutdown_count = len(re.findall(r'shutdown', config_text, re.MULTILINE))
        if shutdown_count > 0:
            return True, f"Found {shutdown_count} shutdown interface(s)"
        return False, "No shutdown interfaces found - verify all unused ports are disabled"

    def check_single_rule(self, config_text, rule):
        """
        Check a single compliance rule against a config.
        Returns (compliant: bool, detail: str)
        """
        config_lines = config_text.split("\n")
        check_type = rule.get("check_type", "regex_present")
        patterns = rule.get("patterns", [])

        try:
            if check_type == "regex_present":
                return self._check_regex_present(config_lines, config_text, patterns)
            elif check_type == "regex_absent":
                return self._check_regex_absent(config_lines, config_text, patterns)
            elif check_type == "section_check":
                return self._check_section_check(config_lines, config_text, rule)
            elif check_type == "conditional_present":
                return self._check_conditional_present(config_lines, config_text, rule)
            elif check_type == "custom":
                return self._check_custom(config_lines, config_text, rule)
            else:
                return True, f"Unknown check type: {check_type} (skipped)"
        except Exception as e:
            logger.error(f"Error checking rule {rule.get('id', '?')}: {e}")
            return False, f"Error during check: {str(e)}"

    def check_compliance(self, switch_result):
        """
        Run all compliance checks against a single switch's config.
        
        Args:
            switch_result: Dict from SSHConnector with 'config', 'name', etc.
        
        Returns:
            Dict with full compliance report for this switch.
        """
        report = {
            "switch_name": switch_result.get("name", "Unknown"),
            "hostname": switch_result.get("hostname", "Unknown"),
            "region": switch_result.get("region", "Unknown"),
            "location": switch_result.get("location", "Unknown"),
            "device_type": switch_result.get("device_type", "Unknown"),
            "collection_status": switch_result.get("status", "unknown"),
            "collection_error": switch_result.get("error", ""),
            "collection_timestamp": switch_result.get("timestamp", ""),
            "timestamp": datetime.now().isoformat(),
            "total_rules": 0,
            "compliant_count": 0,
            "non_compliant_count": 0,
            "na_count": 0,
            "compliance_percentage": 0.0,
            "overall_status": "unknown",
            "category_results": [],
            "all_findings": [],
        }

        # If config collection failed, mark everything as unknown
        if switch_result.get("status") != "success" or not switch_result.get("config"):
            report["overall_status"] = "unreachable"
            report["collection_error"] = switch_result.get("error", "No config available")
            return report

        config_text = switch_result["config"]
        total_rules = 0
        compliant = 0
        non_compliant = 0
        na_count = 0
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for category in self.categories:
            cat_result = {
                "category_name": category["name"],
                "category_id": category["id"],
                "rules_checked": 0,
                "compliant": 0,
                "non_compliant": 0,
                "na": 0,
                "findings": [],
            }

            for rule in category.get("rules", []):
                total_rules += 1
                cat_result["rules_checked"] += 1

                is_compliant, detail = self.check_single_rule(config_text, rule)

                # Handle N/A results
                is_na = detail.startswith("N/A")
                if is_na:
                    na_count += 1
                    cat_result["na"] += 1
                    status = "na"
                elif is_compliant:
                    compliant += 1
                    cat_result["compliant"] += 1
                    status = "compliant"
                else:
                    non_compliant += 1
                    cat_result["non_compliant"] += 1
                    severity_counts[rule.get("severity", "medium")] += 1
                    status = "non_compliant"

                finding = {
                    "rule_id": rule["id"],
                    "description": rule["description"],
                    "severity": rule.get("severity", "medium"),
                    "category": category["name"],
                    "status": status,
                    "detail": detail,
                    "remediation": rule.get("remediation", ""),
                }
                cat_result["findings"].append(finding)
                report["all_findings"].append(finding)

            # Calculate category compliance percentage
            applicable = cat_result["compliant"] + cat_result["non_compliant"]
            cat_result["compliance_pct"] = (
                round(cat_result["compliant"] / applicable * 100, 1) if applicable > 0 else 100.0
            )
            report["category_results"].append(cat_result)

        # Overall stats
        report["total_rules"] = total_rules
        report["compliant_count"] = compliant
        report["non_compliant_count"] = non_compliant
        report["na_count"] = na_count
        report["severity_counts"] = severity_counts

        applicable_rules = compliant + non_compliant
        report["compliance_percentage"] = (
            round(compliant / applicable_rules * 100, 1) if applicable_rules > 0 else 100.0
        )

        # Determine overall status
        if report["compliance_percentage"] >= 95:
            report["overall_status"] = "compliant"
        elif report["compliance_percentage"] >= 70:
            report["overall_status"] = "partially_compliant"
        else:
            report["overall_status"] = "non_compliant"

        # Critical findings flag
        report["has_critical_findings"] = severity_counts.get("critical", 0) > 0

        return report

    def check_all(self, switch_results):
        """
        Run compliance checks against all collected switch configs.
        
        Args:
            switch_results: List of dicts from SSHConnector.collect_all_configs()
        
        Returns:
            Dict with full audit report including per-switch and summary data.
        """
        audit = {
            "audit_timestamp": datetime.now().isoformat(),
            "template_version": self.template.get("metadata", {}).get("version", "unknown"),
            "template_standard": self.template.get("metadata", {}).get("standard", "unknown"),
            "total_switches": len(switch_results),
            "switches_reached": 0,
            "switches_unreachable": 0,
            "total_rules_per_switch": self.get_rule_count(),
            "overall_compliance_pct": 0.0,
            "compliant_switches": 0,
            "partially_compliant_switches": 0,
            "non_compliant_switches": 0,
            "unreachable_switches": 0,
            "switch_reports": [],
            "summary_by_category": {},
            "summary_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "summary_by_region": {},
            "top_non_compliant_rules": [],
        }

        rule_failure_count = {}
        all_compliance_pcts = []

        for switch_result in switch_results:
            report = self.check_compliance(switch_result)
            audit["switch_reports"].append(report)

            if report["overall_status"] == "unreachable":
                audit["unreachable_switches"] += 1
                audit["switches_unreachable"] += 1
            else:
                audit["switches_reached"] += 1
                all_compliance_pcts.append(report["compliance_percentage"])

                if report["overall_status"] == "compliant":
                    audit["compliant_switches"] += 1
                elif report["overall_status"] == "partially_compliant":
                    audit["partially_compliant_switches"] += 1
                else:
                    audit["non_compliant_switches"] += 1

                # Aggregate severity counts
                for sev, count in report.get("severity_counts", {}).items():
                    audit["summary_by_severity"][sev] = audit["summary_by_severity"].get(sev, 0) + count

                # Aggregate by category
                for cat_result in report.get("category_results", []):
                    cat_name = cat_result["category_name"]
                    if cat_name not in audit["summary_by_category"]:
                        audit["summary_by_category"][cat_name] = {
                            "total_checks": 0, "compliant": 0, "non_compliant": 0, "na": 0
                        }
                    audit["summary_by_category"][cat_name]["total_checks"] += cat_result["rules_checked"]
                    audit["summary_by_category"][cat_name]["compliant"] += cat_result["compliant"]
                    audit["summary_by_category"][cat_name]["non_compliant"] += cat_result["non_compliant"]
                    audit["summary_by_category"][cat_name]["na"] += cat_result["na"]

                # Track non-compliant rules
                for finding in report.get("all_findings", []):
                    if finding["status"] == "non_compliant":
                        rule_id = finding["rule_id"]
                        if rule_id not in rule_failure_count:
                            rule_failure_count[rule_id] = {
                                "rule_id": rule_id,
                                "description": finding["description"],
                                "severity": finding["severity"],
                                "category": finding["category"],
                                "count": 0,
                            }
                        rule_failure_count[rule_id]["count"] += 1

                # Aggregate by region
                region = report.get("region", "Unknown")
                if region not in audit["summary_by_region"]:
                    audit["summary_by_region"][region] = {
                        "total": 0, "compliant": 0, "partial": 0, "non_compliant": 0, "unreachable": 0,
                        "avg_compliance": 0, "pcts": []
                    }
                audit["summary_by_region"][region]["total"] += 1
                audit["summary_by_region"][region]["pcts"].append(report["compliance_percentage"])
                if report["overall_status"] == "compliant":
                    audit["summary_by_region"][region]["compliant"] += 1
                elif report["overall_status"] == "partially_compliant":
                    audit["summary_by_region"][region]["partial"] += 1
                else:
                    audit["summary_by_region"][region]["non_compliant"] += 1

        # Calculate overall compliance
        if all_compliance_pcts:
            audit["overall_compliance_pct"] = round(
                sum(all_compliance_pcts) / len(all_compliance_pcts), 1
            )

        # Calculate region averages
        for region in audit["summary_by_region"].values():
            if region["pcts"]:
                region["avg_compliance"] = round(sum(region["pcts"]) / len(region["pcts"]), 1)
            del region["pcts"]

        # Category compliance percentages
        for cat_name, cat_data in audit["summary_by_category"].items():
            applicable = cat_data["compliant"] + cat_data["non_compliant"]
            cat_data["compliance_pct"] = (
                round(cat_data["compliant"] / applicable * 100, 1) if applicable > 0 else 100.0
            )

        # Top non-compliant rules (sorted by failure count)
        audit["top_non_compliant_rules"] = sorted(
            rule_failure_count.values(), key=lambda x: x["count"], reverse=True
        )[:20]

        return audit
