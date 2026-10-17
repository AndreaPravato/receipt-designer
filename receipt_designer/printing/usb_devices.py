"""USB device listing and endpoint discovery helpers (pyusb)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import usb.core  # pyusb
    import usb.util
except Exception:  # pragma: no cover - optional dependency / backend missing
    usb = None  # type: ignore


def parse_usb_id(value) -> Optional[int]:
    """Parse a USB VID/PID/endpoint from int or hex/decimal string.

    Accepts ``0x0416``, ``0416``, ``1046``, or an int. Returns ``None`` for
    empty / missing values.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        # Bare hex without 0x prefix (e.g. "0416")
        try:
            return int(text, 16)
        except ValueError as exc:
            raise ValueError(f"Invalid USB id/endpoint value: {value!r}") from exc


def format_usb_id(value: int) -> str:
    """Format an integer USB id as a 0xNNNN hex string."""
    return f"0x{int(value):04x}"


def format_usb_endpoint(value: int) -> str:
    """Format an endpoint address as a compact hex string (e.g. 0x81)."""
    return f"0x{int(value):02x}"


@dataclass(frozen=True)
class UsbDeviceInfo:
    vendor_id: int
    product_id: int
    manufacturer: str = ""
    product: str = ""
    in_ep: Optional[int] = None
    out_ep: Optional[int] = None

    @property
    def label(self) -> str:
        name = self.product or self.manufacturer or "USB device"
        return f"{format_usb_id(self.vendor_id)}:{format_usb_id(self.product_id)} — {name}"


def _safe_string(dev, getter_name: str) -> str:
    getter = getattr(dev, getter_name, None)
    if getter is None:
        return ""
    try:
        value = getter()
        return str(value).strip() if value else ""
    except Exception:
        return ""


def _endpoints_for_device(dev) -> tuple[Optional[int], Optional[int]]:
    """Return the first bulk/interrupt IN and OUT endpoint addresses, if any."""
    if usb is None:
        return None, None
    try:
        try:
            cfg = dev.get_active_configuration()
        except Exception:
            dev.set_configuration()
            cfg = dev.get_active_configuration()
    except Exception:
        return None, None

    in_ep: Optional[int] = None
    out_ep: Optional[int] = None
    try:
        for intf in cfg:
            for ep in intf:
                addr = int(ep.bEndpointAddress)
                direction = usb.util.endpoint_direction(addr)
                if direction == usb.util.ENDPOINT_OUT and out_ep is None:
                    out_ep = addr
                elif direction == usb.util.ENDPOINT_IN and in_ep is None:
                    in_ep = addr
            if in_ep is not None and out_ep is not None:
                break
    except Exception:
        return in_ep, out_ep
    return in_ep, out_ep


def list_usb_devices() -> list[UsbDeviceInfo]:
    """List connected USB devices with best-effort name and endpoint probes.

    Raises ``RuntimeError`` if pyusb is unavailable. Permission-denied devices
    are still listed with empty names/endpoints when possible.
    """
    if usb is None:
        raise RuntimeError(
            "pyusb is not available. Install it with `pip install pyusb` "
            "and ensure a libusb backend is present."
        )

    devices: list[UsbDeviceInfo] = []
    try:
        found = list(usb.core.find(find_all=True) or [])
    except Exception as exc:
        raise RuntimeError(f"Failed to scan USB devices: {exc}") from exc

    for dev in found:
        try:
            vid = int(dev.idVendor)
            pid = int(dev.idProduct)
        except Exception:
            continue
        manufacturer = _safe_string(dev, "manufacturer")
        product = _safe_string(dev, "product")
        in_ep, out_ep = _endpoints_for_device(dev)
        devices.append(
            UsbDeviceInfo(
                vendor_id=vid,
                product_id=pid,
                manufacturer=manufacturer,
                product=product,
                in_ep=in_ep,
                out_ep=out_ep,
            )
        )

    devices.sort(key=lambda d: (d.vendor_id, d.product_id, d.label.lower()))
    return devices


def discover_usb_endpoints(vendor_id: int, product_id: int) -> tuple[Optional[int], Optional[int]]:
    """Probe IN/OUT endpoints for a specific VID/PID. Returns (in_ep, out_ep)."""
    if usb is None:
        return None, None
    try:
        dev = usb.core.find(idVendor=int(vendor_id), idProduct=int(product_id))
    except Exception:
        return None, None
    if dev is None:
        return None, None
    return _endpoints_for_device(dev)
