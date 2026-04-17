import os
import queue
import re
import threading
import time
import traceback
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional, Tuple, Union

import click
import numpy as np
import torch
import torch._inductor.config
from loguru import logger
from tqdm import tqdm

from fish_speech.content_sequence import (
    TextPart,
    VQPart,
)
from fish_speech.conversation import Conversation, Message
from fish_speech.tokenizer import IM_END_TOKEN

os.environ["TOKENIZERS_PARALLELISM"] = "false"
torch._inductor.config.coordinate_descent_tuning = True
torch._inductor.config.triton.unique_kernel_names = True

if hasattr(torch._inductor.config, "fx_graph_cache"):
    torch._inductor.config.fx_graph_cache = True


from torch.nn.attention import SDPBackend, sdpa_kernel

from fish_speech.models.text2semantic.llama import (
    BaseTransformer,
    DualARTransformer,
    NaiveTransformer,
)

# --- Text splitting constants ---
# Sentence boundary: .!? (Latin) and CJK equivalents
# Abbreviation filtering is done in _find_last_boundary() instead of lookbehind
# because Python re doesn't support variable-width lookbehinds.
_SENTENCE_END = re.compile(r"[.!?\u3002\uff01\uff1f]+(?:\s|$)")

# Common abbreviations that should NOT trigger sentence splits
_ABBREVIATIONS = frozenset(
    {"Dr", "Mr", "Mrs", "Ms", "Prof", "Jr", "Sr", "St", "vs", "etc",
     "Rev", "Gen", "Sgt", "Cpl", "Inc", "Ltd", "Corp", "Ave", "Blvd",
     "Dept", "Fig", "Vol", "No", "Capt", "Lt", "Col", "Maj"}
)

# Clause boundary: comma, semicolon, colon, em-dash followed by space
_CLAUSE_BOUNDARY = re.compile(r"[,;:]\s+|(?:--|—)\s*")

# Emotion tag: [word] optionally followed by whitespace
_EMOTION_TAG = re.compile(r"\[([a-zA-Z]{2,12})\]\s*")


def multinomial_sample_one_no_sync(probs_sort):
    q = torch.rand_like(probs_sort)
    q = -torch.log(q)
    return torch.argmax(probs_sort / q, dim=-1, keepdim=True).to(dtype=torch.int)


RAS_WIN_SIZE = 10  # window for Repetition Aware Sampling
RAS_HIGH_TEMP = 1.0
RAS_HIGH_TOP_P = 0.9


def logits_to_probs(
    logits,
    temperature: torch.Tensor,
    top_p: torch.Tensor,
    top_k: int,  # 注意: 我看到你传进来的是 int，这很关键
) -> torch.Tensor:
    sorted_logits, sorted_indices = torch.sort(logits, descending=True)
    cum_probs = torch.cumsum(torch.nn.functional.softmax(sorted_logits, dim=-1), dim=-1)

    indices = torch.arange(sorted_logits.shape[-1], device=sorted_logits.device)
    top_k_mask = indices >= top_k
    sorted_indices_to_remove = (cum_probs > top_p) | top_k_mask
    sorted_indices_to_remove[0] = False  # 单元素修改问题不大，或者写成 | (indices != 0)

    indices_to_remove = sorted_indices_to_remove.scatter(
        dim=-1, index=sorted_indices, src=sorted_indices_to_remove
    )
    logits = torch.where(
        indices_to_remove, float("-Inf"), logits
    )  # 同样替换 masked_fill_ 为 torch.where
    logits = logits / torch.clip(temperature, min=1e-5)

    probs = torch.nn.functional.softmax(logits, dim=-1)
    return probs


def sample(
    logits,
    temperature: torch.Tensor,
    top_p: torch.Tensor,
    top_k: int,
) -> Tuple[torch.Tensor, torch.Tensor]:
    probs = logits_to_probs(
        logits=logits[0, -1],
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
    )
    idx_next = multinomial_sample_one_no_sync(probs)
    return idx_next, probs


def decode_one_token_ar(
    model: DualARTransformer,
    x: torch.Tensor,
    input_pos: torch.Tensor,
    temperature: torch.Tensor,
    top_p: torch.Tensor,
    top_k: int,
    semantic_logit_bias: torch.Tensor,
    audio_masks: torch.Tensor,
    audio_parts: torch.Tensor,
    previous_tokens: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    forward_result = model.forward_generate(
        x,
        input_pos,
        audio_masks=audio_masks,
        audio_parts=audio_parts,
    )
    logits = forward_result.logits  # (1, 1, vocab_size)
    hidden_states = forward_result.hidden_states

    # Apply constrained decoding: only allow semantic tokens + im_end
    biased_logits = logits + semantic_logit_bias

    # Normal sample
    main_token_normal = sample(
        biased_logits, temperature=temperature, top_p=top_p, top_k=top_k
    )[0]

    # RAS: also sample with high temp to use as fallback if token repeats
    high_temp = torch.tensor(
        RAS_HIGH_TEMP, device=temperature.device, dtype=temperature.dtype
    )
    high_top_p = torch.tensor(RAS_HIGH_TOP_P, device=top_p.device, dtype=top_p.dtype)
    main_token_high = sample(
        biased_logits, temperature=high_temp, top_p=high_top_p, top_k=top_k
    )[0]

    # Use high-temp sample if: token is semantic AND token is in previous window
    if previous_tokens is not None:
        in_window = (previous_tokens[0] == main_token_normal).any()
        # Use tensor ops (&, torch.where) instead of Python (and, if) — torch.compile requires no data-dependent branching
        is_semantic = (main_token_normal >= model.config.semantic_begin_id) & (
            main_token_normal <= model.config.semantic_end_id
        )
        should_use_high = in_window & is_semantic
        main_token_normal = torch.where(
            should_use_high, main_token_high, main_token_normal
        )

    codebooks = [main_token_normal]

    input_pos = torch.tensor([0], device=hidden_states.device, dtype=torch.long)
    model.forward_generate_fast(hidden_states, input_pos)

    a = codebooks[0] - model.config.semantic_begin_id
    a = torch.clamp(a, min=0, max=model.config.codebook_size - 1)

    hidden_states = model.fast_embeddings(a)
    codebooks.append(a)

    for codebook_idx in range(1, model.config.num_codebooks):
        input_pos = torch.tensor(
            [codebook_idx], device=hidden_states.device, dtype=torch.long
        )
        logits = model.forward_generate_fast(hidden_states, input_pos)

        short_logits = logits  # DualAR predicts config.codebook_size number of tokens

        # Convert logits to probs (no constrain for fast codebooks)
        a = sample(
            short_logits,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )[0]

        hidden_states = model.fast_embeddings(a)
        codebooks.append(a)

    codebooks = torch.stack(codebooks, dim=1)

    # Only delete references, let Python GC handle cleanup
    del logits, hidden_states, forward_result

    return codebooks.T


def decode_n_tokens(
    model: DualARTransformer,
    cur_token: torch.Tensor,
    input_pos: torch.Tensor,
    num_new_tokens: int,
    temperature: torch.Tensor,
    top_p: torch.Tensor,
    top_k: int,
    semantic_logit_bias: torch.Tensor,
    audio_masks: torch.Tensor,
    audio_parts: torch.Tensor,
    decode_one_token=decode_one_token_ar,
    sub_chunk_tokens: int = 0,
):
    # Rolling window for RAS (Repetition Aware Sampling)
    previous_tokens = torch.zeros(
        (model.config.num_codebooks + 1, RAS_WIN_SIZE),
        dtype=torch.int,
        device=cur_token.device,
    )
    # Accumulate all generated tokens (the actual output)
    new_tokens = []

    # [MODIFIED] Pre-fetch ID for efficiency loop
    im_end_id = model.tokenizer.get_token_id(IM_END_TOKEN)

    for i in tqdm(range(num_new_tokens)):
        with sdpa_kernel(SDPBackend.MATH):
            next_token = decode_one_token(
                model=model,
                x=cur_token,
                input_pos=input_pos,
                previous_tokens=previous_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                semantic_logit_bias=semantic_logit_bias,
                audio_masks=audio_masks,
                audio_parts=audio_parts,
            ).clone()

        input_pos += 1
        cur_token = next_token.view(1, model.config.num_codebooks + 1, -1)
        # Roll RAS window left and insert new token at end
        previous_tokens = previous_tokens.roll(-1, dims=1)
        previous_tokens[:, -1] = next_token.view(model.config.num_codebooks + 1, -1)[
            :, 0
        ]
        new_tokens.append(next_token)

        # Sub-chunk yield point: yield accumulated tokens every sub_chunk_tokens steps
        if sub_chunk_tokens > 0 and len(new_tokens) >= sub_chunk_tokens:
            yield torch.cat(new_tokens, dim=1)
            new_tokens = []

        if cur_token[0, 0, -1] == im_end_id:
            break

    del cur_token

    # Yield remaining tokens (final batch or all tokens if sub_chunk_tokens=0)
    if new_tokens:
        yield torch.cat(new_tokens, dim=1)


@torch.no_grad()
@torch.inference_mode()
def generate(
    *,
    model: DualARTransformer,
    prompt: torch.Tensor,
    max_new_tokens: int,
    audio_masks: torch.Tensor,
    audio_parts: torch.Tensor,
    decode_one_token=decode_one_token_ar,
    num_samples: int = 1,
    sub_chunk_tokens: int = 0,
    **sampling_kwargs,
):
    """
    Takes a conditioning sequence (prompt) as input and continues to generate as many tokens as requested.
    """

    # create an empty tensor of the expected final shape and fill in the current tokens
    T = prompt.size(1)
    prompt = prompt[None].repeat(num_samples, 1, 1)

    if T >= model.config.max_seq_len:
        raise ValueError(
            f"Input sequence length {T} exceeds max_seq_len {model.config.max_seq_len}"
        )

    if max_new_tokens:
        if T + max_new_tokens > model.config.max_seq_len:
            max_new_tokens = model.config.max_seq_len - T

        T_new = T + max_new_tokens
    else:
        T_new = model.config.max_seq_len
        max_new_tokens = T_new - T

    device = prompt.device
    dtype = next(
        model.parameters()
    ).dtype  # model weight dtype (bfloat16), NOT prompt dtype (int32)

    # Critical fix: Only set up cache on first run or when necessary
    if not hasattr(model, "_cache_setup_done") or not model._cache_setup_done:
        with torch.device(device):
            model.setup_caches(
                max_batch_size=1,  # Fixed to 1, avoid dynamic changes
                max_seq_len=model.config.max_seq_len,
                dtype=next(model.parameters()).dtype,
            )
        model._cache_setup_done = True

    codebook_dim = 1 + model.config.num_codebooks

    # Create new tensor each time, but try to reuse memory
    input_pos = torch.arange(0, T, device=device, dtype=torch.long)
    empty = torch.empty(
        (codebook_dim, model.config.max_seq_len), dtype=prompt.dtype, device=device
    )
    empty[:, :T] = prompt
    seq = empty

    temp_val = sampling_kwargs.get("temperature", 1.0)
    top_p_val = sampling_kwargs.get("top_p", 0.9)
    top_k_val = sampling_kwargs.get("top_k", 30)

    temperature = torch.tensor(temp_val, device=device, dtype=dtype)
    top_p = torch.tensor(top_p_val, device=device, dtype=dtype)

    # Build semantic logit bias: 0 for semantic tokens + im_end, -inf for all others
    vocab_size = model.config.vocab_size
    semantic_logit_bias = torch.full(
        (1, 1, vocab_size), float("-inf"), device=device, dtype=dtype
    )

    # [MODIFIED] Use config for semantic range
    semantic_logit_bias[
        0, 0, model.config.semantic_begin_id : model.config.semantic_end_id + 1
    ] = 0.0

    # [MODIFIED] Use tokenizer.get_token_id (Wrapper method)
    semantic_logit_bias[0, 0, model.tokenizer.get_token_id(IM_END_TOKEN)] = 0.0

    prefill_decode = decode_one_token_ar

    first_token = prefill_decode(
        model,
        prompt.view(1, codebook_dim, -1),
        input_pos,
        temperature,
        top_p,
        top_k_val,
        semantic_logit_bias,
        audio_masks,
        audio_parts,
    )
    seq[:, T : T + 1] = first_token

    # Recreate input_pos
    input_pos = torch.tensor([T], device=device, dtype=torch.int)

    # Track cumulative write position for assembling seq
    write_pos = T + 1

    for partial_codes in decode_n_tokens(
        model,
        first_token.view(1, codebook_dim, -1),
        input_pos,
        max_new_tokens - 1,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k_val,
        semantic_logit_bias=semantic_logit_bias,
        audio_masks=audio_masks,
        audio_parts=audio_parts,
        decode_one_token=decode_one_token,
        sub_chunk_tokens=sub_chunk_tokens,
    ):
        n = partial_codes.size(1)
        seq[:, write_pos : write_pos + n] = partial_codes
        write_pos += n
        yield seq[:, :write_pos]

    del first_token, prompt, empty, input_pos


def init_model(checkpoint_path, device, precision, compile=False):
    model = DualARTransformer.from_pretrained(
        checkpoint_path, load_weights=True, max_length=8192
    )

    model = model.to(device=device, dtype=precision)
    logger.info(f"Restored model from checkpoint")

    if isinstance(model, DualARTransformer):
        decode_one_token = decode_one_token_ar
        logger.info("Using DualARTransformer")
    else:
        raise ValueError("Unsupported model type")

    # TF32 matmul precision — free 10-15% speed boost
    if str(device) == "cuda" or getattr(device, "type", None) == "cuda":
        torch.set_float32_matmul_precision("high")
        logger.info("TF32 matmul precision enabled")

    # Quantization — gate behind FISH_QUANT env var (default "none" = native BF16)
    _quant = os.environ.get("FISH_QUANT", "none").lower()
    if _quant == "int8" and (str(device) == "cuda" or getattr(device, "type", None) == "cuda"):
        from torchao.quantization import quantize_, Int8WeightOnlyConfig
        quantize_(model, Int8WeightOnlyConfig())
        logger.info("Applied INT8 W8A16 quantization")
    else:
        logger.info(f"Running native BF16 (FISH_QUANT={_quant})")

    # Pre-create fixed parameter tensors to avoid runtime creation
    model.fixed_temperature = torch.tensor(0.7, device=device, dtype=torch.float)
    model.fixed_top_p = torch.tensor(0.7, device=device, dtype=torch.float)
    model.fixed_repetition_penalty = torch.tensor(1.5, device=device, dtype=torch.float)

    # Mark whether cache has been initialized
    model._cache_setup_done = False

    if compile:
        if _quant == "int8":
            # Inductor tuning for INT8 — fuse dequant with matmul for ~5-10% speedup
            torch._inductor.config.force_fuse_int_mm_with_mul = True
            torch._inductor.config.coordinate_descent_tuning = True
            torch._inductor.config.coordinate_descent_check_all_directions = True


        logger.info("Compiling function with reduce-overhead...")
        decode_one_token = torch.compile(
            decode_one_token,
            backend="inductor" if torch.cuda.is_available() else "aot_eager",
            mode="reduce-overhead",
            fullgraph=False,
        )

    return model.eval(), decode_one_token


@torch.inference_mode()
def load_codec_model(codec_checkpoint_path, device, precision=torch.bfloat16):
    """Load the DAC codec model for audio encoding/decoding."""
    from hydra.utils import instantiate
    from omegaconf import OmegaConf

    config_path = Path(__file__).parent.parent.parent / "configs" / "modded_dac_vq.yaml"
    cfg = OmegaConf.load(str(config_path))
    codec = instantiate(cfg)

    state_dict = torch.load(codec_checkpoint_path, map_location="cpu")
    if "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    if any("generator" in k for k in state_dict):
        state_dict = {
            k.replace("generator.", ""): v
            for k, v in state_dict.items()
            if "generator." in k
        }
    codec.load_state_dict(state_dict, strict=False)
    codec.eval()
    codec.to(device=device, dtype=precision)
    return codec


@torch.inference_mode()
def encode_audio(audio_path, codec, device):
    """Encode an audio file to VQ codes."""
    import torchaudio

    wav, sr = torchaudio.load(str(audio_path))
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    wav = torchaudio.functional.resample(wav.to(device), sr, codec.sample_rate)[0]

    # Match codec model dtype (e.g. bfloat16)
    model_dtype = next(codec.parameters()).dtype
    audios = wav[None, None].to(dtype=model_dtype)  # (1, 1, T)
    audio_lengths = torch.tensor([len(wav)], device=device, dtype=torch.long)

    indices, feature_lengths = codec.encode(audios, audio_lengths)
    return indices[0, :, : feature_lengths[0]]  # (num_codebooks, T)


@torch.inference_mode()
def decode_to_audio(codes, codec):
    """Decode VQ codes to audio waveform."""
    # codes: (num_codebooks, T) -> (1, num_codebooks, T)
    audio = codec.from_indices(codes[None])
    return audio[0, 0]  # (T,) mono waveform


@dataclass
class GenerateResponse:
    action: Literal["sample", "next"]
    codes: Optional[torch.Tensor] = None
    text: Optional[str] = None
    is_partial: bool = False


def split_text_by_speaker(text: str) -> list[str]:
    """
    Split text into turns based on <|speaker:X|> tags.

    Args:
        text: The full text with speaker tags

    Returns:
        List of speaker turns, each starting with <|speaker:X|>
    """
    pattern = r"(<\|speaker:\d+\|>)"
    parts = re.split(pattern, text)

    turns = []
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if re.match(pattern, part):
            if i + 1 < len(parts):
                turn = part + parts[i + 1]
                turns.append(turn.strip())
                i += 2
            else:
                turns.append(part)
                i += 1
        else:
            i += 1

    return turns


def group_turns_into_batches(
    turns: list[str], max_speakers: int = 3, max_bytes: int = 300
) -> list[str]:
    """
    Group turns into batches based on speaker count or byte limit.

    Args:
        turns: List of speaker turns
        max_speakers: Maximum number of speakers per batch (default 3)
        max_bytes: Maximum UTF-8 bytes per batch (default 300)

    Returns:
        List of batched text strings
    """
    batches = []
    current_batch = []
    current_bytes = 0

    for turn in turns:
        turn_bytes = len(turn.encode("utf-8"))

        would_exceed_speakers = len(current_batch) >= max_speakers
        would_exceed_bytes = current_bytes + turn_bytes > max_bytes and current_batch

        if would_exceed_speakers or would_exceed_bytes:
            batches.append("\n".join(current_batch))
            current_batch = [turn]
            current_bytes = turn_bytes
        else:
            current_batch.append(turn)
            current_bytes += turn_bytes

    if current_batch:
        batches.append("\n".join(current_batch))

    return batches


def _char_position_at_byte_limit(text: str, max_bytes: int) -> int:
    """Return the character index where cumulative UTF-8 bytes exceed max_bytes.

    This is the safe alternative to slicing bytes directly -- avoids
    mid-codepoint splits on multi-byte UTF-8 characters.
    """
    byte_count = 0
    for i, ch in enumerate(text):
        byte_count += len(ch.encode("utf-8"))
        if byte_count > max_bytes:
            return i
    return len(text)


def _find_last_boundary(
    text: str, pattern: re.Pattern, filter_abbreviations: bool = False
) -> Optional[int]:
    """Find the last match of pattern in text, return split position after the match.

    When filter_abbreviations is True, skips matches preceded by a common
    abbreviation (Dr., Mr., etc.) to avoid false sentence splits.

    Returns None if no match found.
    """
    last_match = None
    for match in pattern.finditer(text):
        if filter_abbreviations:
            # Check if the period is preceded by an abbreviation
            start = match.start()
            # Extract the word before the punctuation
            preceding = text[:start].rstrip()
            last_word = preceding.rsplit(None, 1)[-1] if preceding else ""
            if last_word in _ABBREVIATIONS:
                continue
        last_match = match
    if last_match is not None:
        return last_match.end()
    return None


def _find_best_split(text: str, max_bytes: int) -> int:
    """Find the best character position to split text within max_bytes budget.

    Priority: sentence boundary > clause boundary > word boundary > force-split.
    When no sentence/clause boundary exists within budget, looks ahead up to 50%
    beyond the budget for the next sentence boundary to avoid mid-phrase splits.
    Returns character index for the split point.
    """
    text_bytes = text.encode("utf-8")
    if len(text_bytes) <= max_bytes:
        return len(text)

    # Find character position at byte limit
    char_pos = _char_position_at_byte_limit(text, max_bytes)
    search_region = text[:char_pos]

    # Priority 1: Sentence boundaries (with abbreviation filtering)
    best = _find_last_boundary(search_region, _SENTENCE_END, filter_abbreviations=True)
    if best is not None:
        return best

    # Priority 2: Clause boundaries
    best = _find_last_boundary(search_region, _CLAUSE_BOUNDARY)
    if best is not None:
        return best

    # Priority 3: Lookahead — search beyond budget for the next sentence or clause
    # boundary (up to 50% overshoot) to avoid splitting mid-phrase
    lookahead_bytes = int(max_bytes * 1.5)
    lookahead_char_pos = _char_position_at_byte_limit(text, lookahead_bytes)
    lookahead_region = text[char_pos:lookahead_char_pos]

    # Check for next sentence boundary in the lookahead zone
    match = _SENTENCE_END.search(lookahead_region)
    if match is not None:
        return char_pos + match.end()

    # Check for next clause boundary in the lookahead zone
    match = _CLAUSE_BOUNDARY.search(lookahead_region)
    if match is not None:
        return char_pos + match.end()

    # Priority 4: Last space (word boundary) within original budget
    last_space = search_region.rfind(" ")
    if last_space > 0:
        return last_space + 1  # Split after the space

    # Priority 5: Force-split at byte limit (no word boundary found)
    return char_pos


def _split_at_boundaries(
    text: str,
    first_chunk_bytes: int,
    subsequent_chunk_bytes: int,
    min_chunk_bytes: int,
) -> tuple[list[str], list[int]]:
    """Split text into chunks using boundary-priority splitting.

    First iteration uses first_chunk_bytes as budget, subsequent iterations
    use subsequent_chunk_bytes. Sub-minimum final chunks are merged back.

    Returns:
        Tuple of (chunks, offsets) where offsets[i] is the start position
        of chunks[i] in the original text.
    """
    chunks: list[str] = []
    offsets: list[int] = []
    pos = 0  # Current position in original text
    is_first = True

    while pos < len(text):
        # Skip leading whitespace, tracking position
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break

        remaining = text[pos:]
        budget = first_chunk_bytes if is_first else subsequent_chunk_bytes
        remaining_bytes = len(remaining.encode("utf-8"))

        if remaining_bytes <= budget:
            # Everything fits in this chunk
            if chunks and remaining_bytes < min_chunk_bytes:
                # Merge sub-minimum remainder into previous chunk
                chunks[-1] = chunks[-1] + " " + remaining
            else:
                chunks.append(remaining)
                offsets.append(pos)
            break

        split_pos = _find_best_split(remaining, budget)
        if split_pos <= 0:
            # Safety: shouldn't happen, but avoid infinite loop
            chunks.append(remaining)
            offsets.append(pos)
            break

        chunk = remaining[:split_pos].rstrip()
        is_first = False

        if chunk:
            chunks.append(chunk)
            offsets.append(pos)

        pos += split_pos

    return chunks, offsets


def _propagate_emotions(
    chunks: list[str],
    chunk_offsets: list[int],
    tag_positions: list[tuple[int, str]],
) -> list[str]:
    """Prepend the active emotion tag to each chunk based on character position.

    Args:
        chunks: List of text chunks (clean text, no emotion tags).
        chunk_offsets: Start position of each chunk in the original clean text.
        tag_positions: List of (char_position_in_clean_text, tag_name).
    """
    if not tag_positions:
        return chunks

    result = []
    tag_idx = 0
    active_tag: Optional[str] = None

    for i, chunk in enumerate(chunks):
        offset = chunk_offsets[i] if i < len(chunk_offsets) else 0

        # Advance tag state to this chunk's position
        while tag_idx < len(tag_positions) and tag_positions[tag_idx][0] <= offset:
            active_tag = tag_positions[tag_idx][1]
            tag_idx += 1

        # Prepend tag if active and chunk doesn't already start with one
        if active_tag and not re.match(r"^\[\w+\]", chunk):
            result.append(f"[{active_tag}] {chunk}")
        else:
            result.append(chunk)

    return result


def split_text_into_chunks(
    text: str,
    first_chunk_bytes: int = 80,
    subsequent_chunk_bytes: int = 200,
    min_chunk_bytes: int = 50,
) -> list[str]:
    """Split single-speaker text into byte-budgeted chunks with emotion tag propagation.

    Three phases:
    1. Strip emotion tags, record their positions in the clean text
    2. Split the clean text at natural boundaries (sentence > clause > word > force)
    3. Propagate the correct emotion tag to each chunk

    Args:
        text: Input text, may contain emotion tags like [angry]
        first_chunk_bytes: Byte budget for the first chunk (smaller for fast TTFA)
        subsequent_chunk_bytes: Byte budget for subsequent chunks
        min_chunk_bytes: Minimum chunk size; smaller remainders merge into previous

    Returns:
        List of text chunks, each with the appropriate emotion tag prepended
    """
    # Phase 1: Extract and strip emotion tags, recording positions
    text = text.strip()
    tag_positions: list[tuple[int, str]] = []
    clean_text = ""
    last_end = 0

    for match in _EMOTION_TAG.finditer(text):
        clean_text += text[last_end : match.start()]
        tag_name = match.group(1)
        tag_positions.append((len(clean_text), tag_name))
        last_end = match.end()
    clean_text += text[last_end:]
    clean_text = clean_text.strip()

    if not clean_text:
        return []

    # Phase 2: Split clean text at boundaries
    chunks, chunk_offsets = _split_at_boundaries(
        clean_text, first_chunk_bytes, subsequent_chunk_bytes, min_chunk_bytes
    )

    if not chunks:
        return []

    # Phase 3: Propagate emotion tags to chunks
    return _propagate_emotions(chunks, chunk_offsets, tag_positions)


def generate_long(
    *,
    model,
    device: Union[str, torch.device],
    decode_one_token: Callable,
    text: str,
    num_samples: int = 1,
    max_new_tokens: int = 0,
    top_p: float = 0.9,
    top_k: int = 30,
    repetition_penalty: float = 1.1,
    temperature: float = 1.0,
    compile: bool = False,
    iterative_prompt: bool = True,
    chunk_length: int = 512,
    prompt_text: Optional[Union[str, list[str]]] = None,
    prompt_tokens: Optional[Union[torch.Tensor, list[torch.Tensor]]] = None,
    sub_chunk_tokens: int = 0,
):
    assert 0 < top_p <= 1, "top_p must be in (0, 1]"
    assert 0 < temperature < 2, "temperature must be in (0, 2)"

    use_prompt = bool(prompt_text) and bool(prompt_tokens)
    if use_prompt and isinstance(prompt_text, str):
        prompt_text = [prompt_text]
        prompt_tokens = [prompt_tokens]

    if use_prompt:
        assert len(prompt_text) == len(
            prompt_tokens
        ), "Prompt text and tokens must have the same length"

    if prompt_tokens:
        prompt_tokens = [i.cpu() for i in prompt_tokens]

    model_size = sum(p.numel() for p in model.parameters() if p.requires_grad)
    tokenizer = model.tokenizer
    max_length = model.config.max_seq_len

    # Build base conversation with system message
    base_conversation = Conversation()

    if use_prompt:
        # Auto-add speaker tags to prompt texts that don't have them
        tagged_prompt_text = []
        for i, t in enumerate(prompt_text):
            if not re.search(r"<\|speaker:\d+\|>", t):
                tagged_prompt_text.append(f"<|speaker:{i}|>{t}")
            else:
                tagged_prompt_text.append(t)

        system_parts = [
            TextPart(
                text="convert the provided text to speech reference to the following:\n\nText:\n",
                cal_loss=False,
            ),
        ]
        reference_text = "\n".join(tagged_prompt_text)
        system_parts.append(TextPart(text=reference_text, cal_loss=False))
        system_parts.append(TextPart(text="\n\nSpeech:\n", cal_loss=False))
        all_codes = torch.cat([c for c in prompt_tokens], dim=1)
        system_parts.append(VQPart(codes=all_codes, cal_loss=False))
        # torch.save(all_codes, "debug_vq_codes.pt")
    else:
        system_parts = [
            TextPart(text="convert the provided text to speech", cal_loss=False)
        ]

    base_conversation.append(
        Message(
            role="system",
            parts=system_parts,
            cal_loss=False,
            add_im_start=True,
            add_im_end=True,
        )
    )

    # Split text by speaker and group into batches
    turns = split_text_by_speaker(text)
    if turns:
        batches = group_turns_into_batches(
            turns, max_speakers=5, max_bytes=chunk_length
        )
        logger.info(f"Split into {len(turns)} turns, grouped into {len(batches)} batches")
    else:
        text = text.strip()
        if not text:
            return
        batches = split_text_into_chunks(
            text,
            first_chunk_bytes=80,
            subsequent_chunk_bytes=chunk_length,
            min_chunk_bytes=50,
        )
        if not batches:
            batches = [text]
        logger.info(f"Single-speaker: split text into {len(batches)} chunks")

    for sample_idx in range(num_samples):
        if torch.cuda.is_available():
            torch.cuda.synchronize()

        t0 = time.perf_counter()

        # Deep copy base conversation for this sample
        conversation = deepcopy(base_conversation)

        for batch_idx, batch_text in enumerate(batches):
            logger.info(
                f"--- Sample {sample_idx}, Batch {batch_idx} "
                f"({len(batch_text.encode('utf-8'))} bytes) ---"
            )
            logger.info(f"Batch text: {batch_text}")

            # Add user message
            conversation.append(
                Message(
                    role="user",
                    parts=[TextPart(text=batch_text, cal_loss=False)],
                    cal_loss=False,
                    add_im_start=True,
                    add_im_end=True,
                )
            )

            # Deep copy for generation (don't pollute original conversation)
            conversation_gen = deepcopy(conversation)
            conversation_gen.append(
                Message(
                    role="assistant",
                    parts=[],
                    cal_loss=False,
                    modality="voice",
                    add_im_start=True,
                    add_im_end=False,
                )
            )

            logger.info("Visualizing prompt structure:")
            conversation_gen.visualize(
                tokenizer,
                merge_audio_tokens=True,
                merge_semantic_tokens=True,
            )

            encoded, audio_masks, audio_parts = conversation_gen.encode_for_inference(
                tokenizer, num_codebooks=model.config.num_codebooks
            )

            logger.info(f"Encoded prompt shape: {encoded.shape}")
            if audio_parts is not None:
                logger.info(f"Audio parts shape: {audio_parts.shape}")
            if audio_masks is not None:
                logger.info(
                    f"Audio masks non-zero count: {torch.count_nonzero(audio_masks)}"
                )

            if encoded.size(1) > max_length - 2048:
                raise ValueError(
                    f"Prompt is too long: {encoded.size(1)} > {max_length - 2048}"
                )

            encoded = encoded.to(device=device)
            prompt_length = encoded.size(1)

            last_seq = None
            for cumulative_seq in generate(
                model=model,
                prompt=encoded,
                max_new_tokens=max_new_tokens,
                audio_masks=audio_masks,
                audio_parts=audio_parts,
                decode_one_token=decode_one_token,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                sub_chunk_tokens=sub_chunk_tokens,
            ):
                last_seq = cumulative_seq
                if sub_chunk_tokens > 0:
                    # Extract codes from cumulative seq for this partial
                    codes = cumulative_seq[1:, prompt_length:].clone()
                    if codes.size(1) > 0:
                        yield GenerateResponse(
                            action="sample", codes=codes, text=batch_text, is_partial=True
                        )

            if sample_idx == 0 and batch_idx == 0 and compile:
                logger.info(f"Compilation time: {time.perf_counter() - t0:.2f} seconds")

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            y = last_seq
            t_batch = time.perf_counter() - t0
            tokens_generated = y.size(1) - prompt_length
            tokens_sec = tokens_generated / t_batch if t_batch > 0 else 0
            logger.info(
                f"Batch {batch_idx}: Generated {tokens_generated} tokens in "
                f"{t_batch:.02f} seconds, {tokens_sec:.02f} tokens/sec"
            )
            logger.info(
                f"Bandwidth achieved: {model_size * tokens_sec / 1e9:.02f} GB/s"
            )

            # Extract final codes (full chunk)
            codes = y[1:, prompt_length:-1].clone()
            assert (codes >= 0).all(), f"Negative code found: {codes}"

            # Add assistant message with generated codes back to conversation
            conversation.append(
                Message(
                    role="assistant",
                    parts=[VQPart(codes=codes.cpu(), cal_loss=False)],
                    cal_loss=False,
                    modality="voice",
                    add_im_start=True,
                    add_im_end=True,
                )
            )

            # Final yield for this text batch (is_partial=False)
            yield GenerateResponse(action="sample", codes=codes, text=batch_text, is_partial=False)

            del y, encoded

        if torch.cuda.is_available():
            logger.info(
                f"GPU Memory used: {torch.cuda.max_memory_reserved() / 1e9:.02f} GB"
            )

        yield GenerateResponse(action="next")


@dataclass
class WrappedGenerateResponse:
    status: Literal["success", "error"]
    response: Optional[Union[GenerateResponse, Exception]] = None


@dataclass
class GenerateRequest:
    request: dict
    response_queue: queue.Queue


def launch_thread_safe_queue(
    checkpoint_path,
    device,
    precision,
    compile: bool = False,
):
    input_queue = queue.Queue()
    init_event = threading.Event()

    def worker():
        model, decode_one_token = init_model(
            checkpoint_path, device, precision, compile=compile
        )
        with torch.device(device):
            model.setup_caches(
                max_batch_size=1,
                max_seq_len=model.config.max_seq_len,
                dtype=next(model.parameters()).dtype,
            )
        init_event.set()

        while True:
            item: GenerateRequest | None = input_queue.get()
            if item is None:
                break

            kwargs = item.request
            response_queue = item.response_queue

            try:
                for chunk in generate_long(
                    model=model, decode_one_token=decode_one_token, **kwargs
                ):
                    response_queue.put(
                        WrappedGenerateResponse(status="success", response=chunk)
                    )

                # Only clear cache after complete request batch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except Exception as e:
                logger.error(traceback.format_exc())
                response_queue.put(WrappedGenerateResponse(status="error", response=e))
                # Clear cache on error
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    threading.Thread(target=worker, daemon=True).start()
    init_event.wait()

    return input_queue


@click.command()
@click.option(
    "--text",
    type=str,
    default="<|speaker:0|>你说的对, 但是原神是一款由米哈游自主研发的开放世界手游.",
)
@click.option("--prompt-text", type=str, default=None, multiple=True)
@click.option(
    "--prompt-tokens",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    multiple=True,
)
@click.option(
    "--prompt-audio",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    multiple=True,
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--num-samples", type=int, default=1)
@click.option("--max-new-tokens", type=int, default=0)
@click.option("--top-p", type=float, default=0.9)
@click.option("--top-k", type=int, default=30)
@click.option("--temperature", type=float, default=1.0)
@click.option(
    "--checkpoint-path",
    type=click.Path(path_type=Path, exists=True),
    default="checkpoints/s2-pro",
)
@click.option("--device", type=str, default="cuda")
@click.option("--compile/--no-compile", default=False)
@click.option("--seed", type=int, default=42)
@click.option("--half/--no-half", default=False)
@click.option("--iterative-prompt/--no-iterative-prompt", default=True)
@click.option("--chunk-length", type=int, default=300)
@click.option("--output-dir", type=Path, default="output")
def main(
    text: str,
    prompt_text: Optional[tuple[str, ...]],
    prompt_tokens: Optional[tuple[Path, ...]],
    prompt_audio: Optional[tuple[Path, ...]],
    output: Optional[Path],
    num_samples: int,
    max_new_tokens: int,
    top_p: float,
    top_k: int,
    temperature: float,
    checkpoint_path: Path,
    device: str,
    compile: bool,
    seed: int,
    half: bool,
    iterative_prompt: bool,
    chunk_length: int,
    output_dir: Path,
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    precision = torch.half if half else torch.bfloat16

    if prompt_text and not prompt_audio and not prompt_tokens:
        raise ValueError(
            "--prompt-text requires either --prompt-audio or --prompt-tokens"
        )
    if prompt_text and prompt_tokens and len(prompt_text) != len(prompt_tokens):
        raise ValueError(
            f"Number of prompt text ({len(prompt_text)}) and prompt tokens ({len(prompt_tokens)}) should be the same"
        )
    if prompt_text and prompt_audio and len(prompt_text) != len(prompt_audio):
        raise ValueError(
            f"Number of prompt text ({len(prompt_text)}) and prompt audio ({len(prompt_audio)}) should be the same"
        )

    logger.info("Loading model ...")
    t0 = time.time()
    model, decode_one_token = init_model(
        checkpoint_path, device, precision, compile=compile
    )
    with torch.device(device):
        model.setup_caches(
            max_batch_size=1,
            max_seq_len=model.config.max_seq_len,
            dtype=next(model.parameters()).dtype,
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()

    logger.info(f"Time to load model: {time.time() - t0:.02f} seconds")

    codec = None
    codec_checkpoint = checkpoint_path / "codec.pth"

    # Handle prompt: --prompt-audio takes priority over --prompt-tokens
    prompt_tokens_list = None
    if prompt_audio:
        logger.info("Loading codec model for audio encoding...")
        codec = load_codec_model(codec_checkpoint, device, precision)
        prompt_tokens_list = [
            encode_audio(p, codec, device).cpu() for p in prompt_audio
        ]
        logger.info(f"Encoded {len(prompt_audio)} audio file(s) to VQ codes")
    elif prompt_tokens is not None:
        prompt_tokens_list = [torch.from_numpy(np.load(p)) for p in prompt_tokens]

    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)

    generator = generate_long(
        model=model,
        device=device,
        decode_one_token=decode_one_token,
        text=text,
        num_samples=num_samples,
        max_new_tokens=max_new_tokens,
        top_p=top_p,
        top_k=top_k,
        temperature=temperature,
        compile=compile,
        iterative_prompt=iterative_prompt,
        chunk_length=chunk_length,
        prompt_text=list(prompt_text) if prompt_text else None,
        prompt_tokens=prompt_tokens_list,
    )

    idx = 0
    codes = []

    for response in generator:
        if response.action == "sample":
            codes.append(response.codes)
            logger.info(f"Sampled text: {response.text}")
        elif response.action == "next":
            if codes:
                merged_codes = torch.cat(codes, dim=1)
                codes_npy_path = os.path.join(output_dir, f"codes_{idx}.npy")
                np.save(codes_npy_path, merged_codes.cpu().numpy())
                logger.info(f"Saved codes to {codes_npy_path}")

                # Decode to wav if --output is specified
                if output:
                    if codec is None:
                        logger.info("Loading codec model for audio decoding...")
                        codec = load_codec_model(codec_checkpoint, device, precision)
                    audio = decode_to_audio(merged_codes.to(device), codec)
                    import soundfile as sf

                    out_path = (
                        str(output)
                        if num_samples == 1
                        else str(output.with_stem(f"{output.stem}_{idx}"))
                    )
                    sf.write(out_path, audio.cpu().float().numpy(), codec.sample_rate)
                    logger.info(f"Saved audio to {out_path}")

            logger.info(f"Next sample")
            codes = []
            idx += 1
        else:
            logger.error(f"Error: {response}")


if __name__ == "__main__":
    main()
