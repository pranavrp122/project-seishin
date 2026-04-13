import queue
from typing import Generator

import numpy as np
import torch
from loguru import logger
from pedalboard import Pedalboard, PeakFilter

from fish_speech.inference_engine.crossfader import StreamingCrossfader
from fish_speech.inference_engine.reference_loader import ReferenceLoader
from fish_speech.inference_engine.utils import InferenceResult, wav_chunk_header
from fish_speech.inference_engine.vq_manager import VQManager
from fish_speech.models.dac.modded_dac import DAC
from fish_speech.models.text2semantic.inference import (
    GenerateRequest,
    GenerateResponse,
    WrappedGenerateResponse,
)
from fish_speech.utils import autocast_exclude_mps, set_seed
from fish_speech.utils.schema import ServeTTSRequest


class TTSInferenceEngine(ReferenceLoader, VQManager):

    _post_fx = Pedalboard([
        PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7),
    ])

    def __init__(
        self,
        llama_queue: queue.Queue,
        decoder_model: DAC,
        precision: torch.dtype,
        compile: bool,
    ) -> None:

        super().__init__()

        self.llama_queue = llama_queue
        self.decoder_model = decoder_model
        self.precision = precision
        self.compile = compile

    @torch.inference_mode()
    def inference(self, req: ServeTTSRequest) -> Generator[InferenceResult, None, None]:
        """
        Main inference function:
        - Loads the reference audio and text.
        - Calls the LLAMA model for inference.
        - Decodes the VQ tokens to audio.
        """

        ref_id: str | None = req.reference_id
        prompt_tokens, prompt_texts = [], []
        # Load the reference audio and text based on id or hash
        if ref_id is not None:
            prompt_tokens, prompt_texts = self.load_by_id(ref_id, req.use_memory_cache)

        elif req.references:
            prompt_tokens, prompt_texts = self.load_by_hash(
                req.references, req.use_memory_cache
            )

        # Set the random seed if provided
        if req.seed is not None:
            set_seed(req.seed)
            logger.warning(f"set seed: {req.seed}")

        # Get the symbolic tokens from the LLAMA model
        response_queue = self.send_Llama_request(req, prompt_tokens, prompt_texts)

        # Get the sample rate from the decoder model
        if hasattr(self.decoder_model, "spec_transform"):
            sample_rate = self.decoder_model.spec_transform.sample_rate
        else:
            sample_rate = self.decoder_model.sample_rate

        # If streaming, send the header
        if req.streaming:
            yield InferenceResult(
                code="header",
                audio=(
                    sample_rate,
                    wav_chunk_header(sample_rate=sample_rate),
                ),
                error=None,
            )

        segments = []
        crossfader = StreamingCrossfader(overlap_samples=1764) if req.streaming else None

        # Grow-and-redecode state for sub-chunk streaming
        prev_audio_samples = 0
        prev_batch_tail: np.ndarray | None = None
        is_sub_chunk_mode = False

        while True:
            wrapped_result: WrappedGenerateResponse = response_queue.get()
            if wrapped_result.status == "error":
                yield InferenceResult(
                    code="error",
                    audio=None,
                    error=(
                        wrapped_result.response
                        if isinstance(wrapped_result.response, Exception)
                        else Exception("Unknown error")
                    ),
                )
                break

            if not isinstance(wrapped_result.response, GenerateResponse):
                raise TypeError(
                    f"Expected GenerateResponse, got {type(wrapped_result.response).__name__}"
                )

            result: GenerateResponse = wrapped_result.response
            if result.action == "next":
                break

            if result.is_partial:
                # --- Sub-chunk partial: grow-and-redecode ---
                is_sub_chunk_mode = True
                segment = self.get_audio_segment(result)
                new_audio = segment[prev_audio_samples:]
                prev_audio_samples = len(segment)

                if len(new_audio) > 0:
                    # Apply text-chunk boundary crossfade if tail from previous batch exists
                    if prev_batch_tail is not None:
                        if len(new_audio) >= len(prev_batch_tail):
                            overlap_len = len(prev_batch_tail)
                            t = np.linspace(0, 1, overlap_len, dtype=np.float32)
                            fade_in = np.sin(t * np.pi / 2) ** 2
                            fade_out = np.cos(t * np.pi / 2) ** 2
                            head = new_audio[:overlap_len]
                            blended = prev_batch_tail * fade_out + head * fade_in
                            new_audio = np.concatenate([blended, new_audio[overlap_len:]])
                        else:
                            new_audio = np.concatenate([prev_batch_tail, new_audio])
                        prev_batch_tail = None

                    yield InferenceResult(
                        code="segment",
                        audio=(sample_rate, new_audio),
                        error=None,
                    )
                    segments.append(new_audio)

            else:
                # --- Final chunk of text batch (is_partial=False) ---
                if is_sub_chunk_mode:
                    segment = self.get_audio_segment(result)
                    new_audio = segment[prev_audio_samples:]
                    prev_audio_samples = 0
                    is_sub_chunk_mode = False

                    if len(new_audio) > 0:
                        overlap = 1764
                        if len(new_audio) > overlap:
                            body = new_audio[:-overlap]
                            prev_batch_tail = new_audio[-overlap:].copy()
                            yield InferenceResult(
                                code="segment",
                                audio=(sample_rate, body),
                                error=None,
                            )
                            segments.append(body)
                        else:
                            prev_batch_tail = new_audio.copy()

                else:
                    # No sub-chunking -- use crossfader as before (backward compat)
                    segment = self.get_audio_segment(result)
                    if crossfader is not None:
                        emittable = crossfader.process(segment)
                        if emittable is not None and len(emittable) > 0:
                            yield InferenceResult(
                                code="segment",
                                audio=(sample_rate, emittable),
                                error=None,
                            )
                    segments.append(segment)

        # Flush sub-chunk tail buffer
        if prev_batch_tail is not None:
            yield InferenceResult(
                code="segment",
                audio=(sample_rate, prev_batch_tail),
                error=None,
            )
            segments.append(prev_batch_tail)

        # Flush remaining crossfader tail for streaming (per D-07)
        if crossfader is not None:
            tail = crossfader.flush()
            if tail is not None and len(tail) > 0:
                yield InferenceResult(
                    code="segment",
                    audio=(sample_rate, tail),
                    error=None,
                )

        # Skip per-request memory cleanup — on a dedicated TTS server with stable
        # VRAM, empty_cache + gc.collect adds ~200-400ms overhead per request by
        # forcing CUDA to re-allocate memory pools.

        # Edge case: no audio generated
        if len(segments) == 0:
            yield InferenceResult(
                code="error",
                audio=None,
                error=RuntimeError("No audio generated, please check the input text."),
            )
        else:
            # Streaming or not, return the final audio
            audio = np.concatenate(segments, axis=0)
            yield InferenceResult(
                code="final",
                audio=(sample_rate, audio),
                error=None,
            )

        return None

    def send_Llama_request(
        self, req: ServeTTSRequest, prompt_tokens: list, prompt_texts: list
    ) -> queue.Queue:
        """
        Send a request to the LLAMA model to generate the symbolic tokens.
        """

        # Prepare the request
        request = dict(
            device=self.decoder_model.device,
            max_new_tokens=req.max_new_tokens,
            text=req.text,
            top_p=req.top_p,
            repetition_penalty=req.repetition_penalty,
            temperature=req.temperature,
            compile=self.compile,
            iterative_prompt=req.chunk_length > 0,
            chunk_length=req.chunk_length,
            prompt_tokens=prompt_tokens,
            prompt_text=prompt_texts,
            sub_chunk_tokens=req.sub_chunk_tokens if req.streaming else 0,
        )

        # Create a queue to get the response
        response_queue = queue.Queue()

        # Send the request to the LLAMA model
        self.llama_queue.put(
            GenerateRequest(
                request=request,
                response_queue=response_queue,
            )
        )

        return response_queue

    def get_audio_segment(self, result: GenerateResponse) -> np.ndarray:
        """
        Decode the VQ tokens to audio.
        """

        # Don't use autocast on MPS devices
        with autocast_exclude_mps(
            device_type=self.decoder_model.device.type, dtype=self.precision
        ):
            # Decode the symbolic tokens to audio
            segment = self.decode_vq_tokens(codes=result.codes)

        # Convert the audio to numpy and apply post-processing filter
        audio = segment.float().cpu().numpy()
        if hasattr(self.decoder_model, "spec_transform"):
            sr = self.decoder_model.spec_transform.sample_rate
        else:
            sr = self.decoder_model.sample_rate
        return self._post_fx(audio, sr)
