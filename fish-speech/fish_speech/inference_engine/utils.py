import struct
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

import numpy as np


@dataclass
class InferenceResult:
    code: Literal["header", "segment", "error", "final"]
    audio: Optional[Tuple[int, np.ndarray]]
    error: Optional[Exception]


def wav_chunk_header(
    sample_rate: int = 44100, bit_depth: int = 16, channels: int = 1
) -> bytes:
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)

    header = struct.pack('<4sI4s', b'RIFF', 0xFFFFFFFF, b'WAVE')
    header += struct.pack('<4sIHHIIHH',
        b'fmt ', 16, 1, channels, sample_rate, byte_rate, block_align, bit_depth)
    header += struct.pack('<4sI', b'data', 0xFFFFFFFF)
    return header
