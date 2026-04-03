# collector/snmp_client.py

from pysnmp.hlapi import (
    SnmpEngine, UsmUserData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity,
    usmHMACSHAAuthProtocol,
    usmAesCfb128Protocol,
    usmDESPrivProtocol,
    getCmd, nextCmd
)

# ── helpers ──────────────────────────────────────────────────────────────

def _get_priv_protocol(priv_type: str):
    """Return the correct privacy protocol object based on device type."""
    if priv_type == "AES128":
        return usmAesCfb128Protocol
    else:
        return usmDESPrivProtocol


def _build_usm(priv_type: str):
    """Build SNMPv3 USM credentials for a given device."""
    return UsmUserData(
        userName='snmpuser',
        authKey='AuthPass123',
        privKey='PrivPass123',
        authProtocol=usmHMACSHAAuthProtocol,
        privProtocol=_get_priv_protocol(priv_type)
    )


# ── core functions ────────────────────────────────────────────────────────

def snmp_get(ip: str, oid: str, priv_type: str = "AES128"):
    """
    Query a single OID from a device.
    Returns the value as a string, or None on error.
    """
    iterator = getCmd(
        SnmpEngine(),
        _build_usm(priv_type),
        UdpTransportTarget((ip, 161), timeout=2, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )

    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

    if errorIndication:
        print(f"[ERROR] {ip} | {errorIndication}")
        return None
    elif errorStatus:
        print(f"[ERROR] {ip} | {errorStatus.prettyPrint()}")
        return None
    else:
        return str(varBinds[0][1])


def snmp_walk(ip: str, oid: str, priv_type: str = "AES128"):
    """
    Walk an OID subtree from a device.
    Returns a list of (oid_str, value_str) tuples, or empty list on error.
    """
    results = []

    for errorIndication, errorStatus, errorIndex, varBinds in nextCmd(
        SnmpEngine(),
        _build_usm(priv_type),
        UdpTransportTarget((ip, 161), timeout=2, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False  # stop when we leave the subtree
    ):
        if errorIndication:
            print(f"[ERROR] {ip} | {errorIndication}")
            break
        elif errorStatus:
            print(f"[ERROR] {ip} | {errorStatus.prettyPrint()}")
            break
        else:
            for varBind in varBinds:
                results.append((str(varBind[0]), str(varBind[1])))

    return results


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    R1_IP = "192.168.235.136"

    print("Testing snmp_get — sysName of R1:")
    result = snmp_get(R1_IP, "1.3.6.1.2.1.1.5.0", priv_type="AES128")
    print(f"  sysName = {result}")

    print("\nTesting snmp_walk — interfaces of R1:")
    interfaces = snmp_walk(R1_IP, "1.3.6.1.2.1.2.2.1.2", priv_type="AES128")
    for oid, val in interfaces:
        print(f"  {oid} = {val}")