from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class AnalyzerOptions:
    header_mark_min_us: int = 3000
    header_space_min_us: int = 1500
    gap_space_min_us: int = 8000
    max_pair_mark_us: int = 2000


def analyze_raw(raw: list[int], options: AnalyzerOptions | None = None) -> dict[str, Any]:
    """Protocol-agnostic raw timing analyzer."""
    options = options or AnalyzerOptions()
    result: dict[str, Any] = {
        "timing_count": len(raw),
        "duration_us": sum(raw),
        "header": None,
        "gap_values": [],
        "gap_median": None,
        "bit_mark_median": None,
        "zero_space_median": None,
        "one_space_median": None,
        "space_threshold": None,
        "frames": [],
        "warnings": [],
    }
    if len(raw) < 4:
        result["warnings"].append("Raw troppo corto per analisi binaria")
        return result
    start = 0
    if raw[0] >= options.header_mark_min_us and raw[1] >= options.header_space_min_us:
        result["header"] = [raw[0], raw[1]]
        start = 2
    if (len(raw) - start) % 2:
        result["warnings"].append("Durate dispari dopo header: ultima durata ignorata")
    pairs = [(raw[pos], raw[pos + 1]) for pos in range(start, len(raw) - 1, 2)]
    normal_pairs = [(mark, space) for mark, space in pairs if space < options.gap_space_min_us]
    gap_values = [space for _, space in pairs if space >= options.gap_space_min_us]
    result["gap_values"] = gap_values
    result["gap_median"] = int(median(gap_values)) if gap_values else None
    if not normal_pairs:
        result["warnings"].append("Nessuna coppia bit-like trovata")
        return result
    marks = [mark for mark, _ in normal_pairs if mark <= options.max_pair_mark_us]
    spaces = [space for _, space in normal_pairs]
    result["bit_mark_median"] = int(median(marks)) if marks else None
    short_spaces, long_spaces = split_two_clusters(spaces)
    if not short_spaces or not long_spaces:
        result["warnings"].append("Impossibile separare zero/one in due cluster")
        return result
    zero_median = int(median(short_spaces))
    one_median = int(median(long_spaces))
    threshold = (zero_median + one_median) / 2
    result["zero_space_median"] = zero_median
    result["one_space_median"] = one_median
    result["space_threshold"] = threshold
    frames: list[dict[str, Any]] = []
    current_bits: list[str] = []
    current_pairs = 0
    for _mark, space in pairs:
        if space >= options.gap_space_min_us:
            if current_bits:
                frames.append(frame_from_bits("".join(current_bits), current_pairs))
                current_bits = []
                current_pairs = 0
            continue
        current_bits.append("1" if space > threshold else "0")
        current_pairs += 1
    if current_bits:
        frames.append(frame_from_bits("".join(current_bits), current_pairs))
    result["frames"] = frames
    return result


def split_two_clusters(values: list[int]) -> tuple[list[int], list[int]]:
    if len(values) < 2:
        return values, []
    ordered = sorted(values)
    gaps = [(ordered[index + 1] - ordered[index], index) for index in range(len(ordered) - 1)]
    max_gap, split_index = max(gaps, key=lambda item: item[0])
    if max_gap <= 0:
        return ordered, []
    return ordered[: split_index + 1], ordered[split_index + 1 :]


def frame_from_bits(bits: str, pair_count: int) -> dict[str, Any]:
    whole_len = (len(bits) // 8) * 8
    byte_bits = bits[:whole_len]
    tail_bits = bits[whole_len:]
    return {
        "bit_length": len(bits),
        "pair_count": pair_count,
        "bits": bits,
        "hex_msb": bits_to_hex(byte_bits) if byte_bits else "",
        "tail_bits": tail_bits,
        "bytes_msb": bits_to_bytes(byte_bits) if byte_bits else [],
    }


def bits_to_bytes(bits: str) -> list[int]:
    if len(bits) % 8:
        raise ValueError("bits length must be multiple of 8")
    return [int(bits[index : index + 8], 2) for index in range(0, len(bits), 8)]


def bits_to_hex(bits: str) -> str:
    return "".join(f"{byte:02X}" for byte in bits_to_bytes(bits))


def format_analysis(analysis: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"timings: {analysis.get('timing_count')} | durata: {analysis.get('duration_us')} us")
    if analysis.get("header"):
        lines.append(f"header: {analysis['header']}")
    if analysis.get("zero_space_median") is not None:
        lines.append(
            "bit: mark~{mark} zero~{zero} one~{one} threshold~{threshold:.1f}".format(
                mark=analysis.get("bit_mark_median"),
                zero=analysis.get("zero_space_median"),
                one=analysis.get("one_space_median"),
                threshold=analysis.get("space_threshold"),
            )
        )
    if analysis.get("gap_median"):
        lines.append(f"gap median: {analysis['gap_median']} us")
    for index, frame in enumerate(analysis.get("frames", []), start=1):
        tail = f" tail={frame['tail_bits']}" if frame.get("tail_bits") else ""
        lines.append(f"frame {index}: {frame['bit_length']} bit hex={frame['hex_msb']}{tail}")
    for warning in analysis.get("warnings", []):
        lines.append(f"warning: {warning}")
    return "\n".join(lines)
