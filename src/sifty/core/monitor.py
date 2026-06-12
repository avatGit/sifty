"""Live system snapshot: CPU, memory, disk I/O, network, top processes."""

from __future__ import annotations

from dataclasses import dataclass, field

import psutil


@dataclass
class ProcInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float


@dataclass
class SystemSnapshot:
    cpu_percent: float
    memory_used_gb: float
    memory_total_gb: float
    memory_percent: float
    disk_read_bytes: int      # delta since last snapshot (bytes)
    disk_write_bytes: int
    net_sent_bytes: int
    net_recv_bytes: int
    processes: list[ProcInfo] = field(default_factory=list)


def fmt_rate(bytes_delta: int, interval_seconds: float = 2.0) -> str:
    """Format a byte-delta as a human-readable rate string (e.g. '102 KB/s')."""
    rate = bytes_delta / max(interval_seconds, 0.001)
    if rate < 1_024:
        return f"{rate:.0f} B/s"
    elif rate < 1_048_576:
        return f"{rate / 1_024:.1f} KB/s"
    elif rate < 1_073_741_824:
        return f"{rate / 1_048_576:.1f} MB/s"
    return f"{rate / 1_073_741_824:.2f} GB/s"


# Module-level I/O baselines for computing deltas between snapshots.
_last_disk_io: object = None
_last_net_io: object = None


def snapshot(top_procs: int = 15) -> SystemSnapshot:
    """Take a point-in-time system snapshot.

    I/O fields (disk_read_mb, disk_write_mb, net_*) are deltas since the
    previous call, so the first call returns 0.0 for those fields.
    """
    global _last_disk_io, _last_net_io

    # interval=1 blocks for 1 second but is accurate on any thread.
    # interval=None is broken for our use: psutil stores baselines per thread-ID,
    # so every new Textual worker thread sees no baseline and returns 0.0.
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()

    disk_read = disk_write = 0
    try:
        di = psutil.disk_io_counters()
        if di is not None:
            if _last_disk_io is not None:
                disk_read = max(0, di.read_bytes - _last_disk_io.read_bytes)
                disk_write = max(0, di.write_bytes - _last_disk_io.write_bytes)
            _last_disk_io = di
    except Exception:
        pass

    net_sent = net_recv = 0
    try:
        ni = psutil.net_io_counters()
        if ni is not None:
            if _last_net_io is not None:
                net_sent = max(0, ni.bytes_sent - _last_net_io.bytes_sent)
                net_recv = max(0, ni.bytes_recv - _last_net_io.bytes_recv)
            _last_net_io = ni
    except Exception:
        pass

    procs: list[ProcInfo] = []
    try:
        raw: list[ProcInfo] = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                raw.append(ProcInfo(
                    pid=info["pid"] or 0,
                    name=info["name"] or "",
                    cpu_percent=float(info["cpu_percent"] or 0.0),
                    memory_mb=(info["memory_info"].rss / 1_048_576)
                    if info["memory_info"] else 0.0,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs = sorted(raw, key=lambda p: p.cpu_percent, reverse=True)[:top_procs]
    except Exception:
        pass

    return SystemSnapshot(
        cpu_percent=cpu,
        memory_used_gb=mem.used / 1_073_741_824,
        memory_total_gb=mem.total / 1_073_741_824,
        memory_percent=mem.percent,
        disk_read_bytes=disk_read,
        disk_write_bytes=disk_write,
        net_sent_bytes=net_sent,
        net_recv_bytes=net_recv,
        processes=procs,
    )
