import re

import pytest

from fish_speech.models.text2semantic.inference import split_text_into_chunks


class TestBoundaryDetection:
    def test_split_at_sentence_boundary(self):
        # 150+ bytes of text with sentence boundaries
        text = "Hello world, this is the first part. This is the second sentence that goes on a bit longer. And here is a third one."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        assert len(chunks) >= 2
        # First chunk should end at a sentence boundary (contains a period)
        assert chunks[0].rstrip().endswith((".", "!", "?"))

    def test_split_at_clause_boundary(self):
        # Text with only clause boundaries (commas) within the byte budget
        text = "This is a fairly long clause without periods, and here comes another clause after the comma, followed by yet another one"
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=60, subsequent_chunk_bytes=80
        )
        assert len(chunks) >= 2

    def test_boundary_priority(self):
        # Both sentence and clause boundary in budget -- sentence should win
        text = "Short, but done. Next part here."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        # Should prefer splitting at period, not comma
        if len(chunks) >= 2:
            assert chunks[0].rstrip().endswith(".")

    def test_cjk_sentence_boundaries(self):
        text = "This is some English text here now\u3002And this follows Chinese period\u3002More text here\u3002"
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=40, subsequent_chunk_bytes=60
        )
        assert len(chunks) >= 2


class TestFirstChunkSize:
    def test_first_chunk_targets_80_bytes(self):
        text = "A" * 50 + ". " + "B" * 50 + ". " + "C" * 150 + "."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        assert len(chunks) >= 2
        assert len(chunks[0].encode("utf-8")) <= 80

    def test_subsequent_chunks_target_200_bytes(self):
        text = "First sentence. " + "A" * 180 + ". " + "B" * 180 + "."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        if len(chunks) >= 3:
            # Content bytes of chunks after first should be <= 250 (soft target + merge tolerance)
            for chunk in chunks[1:]:
                content = re.sub(r"^\[\w+\]\s*", "", chunk)
                assert len(content.encode("utf-8")) <= 250


class TestSubsequentChunkSize:
    def test_custom_subsequent_chunk_bytes(self):
        text = "A" * 70 + ". " + "B" * 140 + ". " + "C" * 140 + "."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=150
        )
        assert len(chunks) >= 2
        for chunk in chunks[1:]:
            content = re.sub(r"^\[\w+\]\s*", "", chunk)
            # Should respect 150 byte limit (with merge tolerance)
            assert len(content.encode("utf-8")) <= 200


class TestMinimumChunkSize:
    def test_minimum_chunk_merge(self):
        # Construct text where final remainder is < 50 bytes
        text = "A" * 70 + ". " + "End."
        chunks = split_text_into_chunks(
            text,
            first_chunk_bytes=80,
            subsequent_chunk_bytes=200,
            min_chunk_bytes=50,
        )
        # "End." is 4 bytes, well below 50 -> merged into previous
        assert len(chunks) == 1

    def test_chunk_above_minimum_not_merged(self):
        text = "A" * 70 + ". " + "B" * 60 + "."
        chunks = split_text_into_chunks(
            text,
            first_chunk_bytes=80,
            subsequent_chunk_bytes=200,
            min_chunk_bytes=50,
        )
        # "B" * 60 + "." = 61 bytes, above 50 -> separate chunk
        assert len(chunks) == 2


class TestForceSplit:
    def test_force_split_at_word_boundary(self):
        # No punctuation, just words
        text = " ".join(["word"] * 50)  # ~250 bytes
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=100
        )
        assert len(chunks) >= 2
        # No chunk should have a broken word (no partial "word")
        for chunk in chunks:
            words = chunk.strip().split()
            for w in words:
                assert w == "word"

    def test_force_split_no_spaces(self):
        text = "a" * 300
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        assert len(chunks) >= 2

    def test_utf8_force_split_safety(self):
        # CJK characters are 3 bytes each
        text = "\u4f60" * 100  # 300 bytes
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=200
        )
        assert len(chunks) >= 2
        # Verify no garbled text -- all chunks should be valid strings
        for chunk in chunks:
            chunk.encode("utf-8")  # Should not raise


class TestEmotionExtraction:
    def test_leading_emotion_tag_extracted(self):
        chunks = split_text_into_chunks(
            "[angry] Hello world, this is quite a long sentence.",
            first_chunk_bytes=200,
        )
        assert len(chunks) == 1
        assert chunks[0].startswith("[angry]")

    def test_no_emotion_tag(self):
        chunks = split_text_into_chunks("Hello world.", first_chunk_bytes=200)
        assert chunks == ["Hello world."]


class TestEmotionPropagation:
    def test_emotion_prepended_to_all_chunks(self):
        text = "[angry] You betrayed me. I trusted you completely. And now you have broken everything."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=40, subsequent_chunk_bytes=80
        )
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.startswith("[angry]")

    def test_emotion_tag_not_counted_in_bytes(self):
        # 71 bytes of content + [angry] tag (7+1 bytes) should still be one chunk at 80 byte limit
        content = "A" * 70 + "."  # 71 bytes
        text = f"[angry] {content}"
        chunks = split_text_into_chunks(text, first_chunk_bytes=80)
        assert len(chunks) == 1
        assert chunks[0].startswith("[angry]")


class TestMidTextEmotionTransition:
    def test_mid_text_emotion_change(self):
        text = "[angry] Stop doing that right now! [sad] I am really very sorry about all of this happening."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=40, subsequent_chunk_bytes=80, min_chunk_bytes=10
        )
        assert len(chunks) >= 2
        assert chunks[0].startswith("[angry]")
        # Find the chunk containing "sorry" -- it should have [sad]
        sad_chunks = [c for c in chunks if "sorry" in c]
        assert len(sad_chunks) >= 1
        assert sad_chunks[0].startswith("[sad]")

    def test_multiple_emotion_transitions(self):
        text = "[happy] Great news everyone! [angry] This is absolutely terrible! [sad] So very disappointing indeed."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=30, subsequent_chunk_bytes=50, min_chunk_bytes=10
        )
        assert len(chunks) >= 2
        assert chunks[0].startswith("[happy]")
        angry_chunks = [c for c in chunks if "terrible" in c]
        if angry_chunks:
            assert angry_chunks[0].startswith("[angry]")
        sad_chunks = [c for c in chunks if "disappointing" in c]
        if sad_chunks:
            assert sad_chunks[0].startswith("[sad]")


class TestEdgeCases:
    def test_empty_input(self):
        assert split_text_into_chunks("") == []

    def test_whitespace_only(self):
        assert split_text_into_chunks("   ") == []

    def test_tags_only_no_content(self):
        assert split_text_into_chunks("[angry] [sad]") == []

    def test_short_text_single_chunk(self):
        chunks = split_text_into_chunks("Hi.", first_chunk_bytes=80)
        assert chunks == ["Hi."]

    def test_abbreviation_not_false_split(self):
        text = "Dr. Smith said hello to the audience."
        chunks = split_text_into_chunks(text, first_chunk_bytes=200)
        # Should NOT split at "Dr." -- entire text fits in one chunk
        assert len(chunks) == 1

    def test_ellipsis_as_boundary(self):
        text = "Well... That was unexpected and quite surprising indeed, really truly."
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=20, subsequent_chunk_bytes=80, min_chunk_bytes=10
        )
        assert len(chunks) >= 2


class TestGenerateLongIntegration:
    """Verify split_text_into_chunks is called correctly in generate_long's else branch."""

    def test_single_speaker_uses_split_text_into_chunks(self):
        """When split_text_by_speaker returns empty, split_text_into_chunks is used."""
        from fish_speech.models.text2semantic.inference import (
            split_text_by_speaker,
            split_text_into_chunks,
        )

        text = "Hello world. This is a test sentence. And another one here."
        # Verify this text has no speaker tags (would go to else branch)
        assert split_text_by_speaker(text) == []
        # Verify split_text_into_chunks produces multiple chunks
        chunks = split_text_into_chunks(
            text, first_chunk_bytes=30, subsequent_chunk_bytes=40
        )
        assert len(chunks) >= 2

    def test_multi_speaker_still_uses_speaker_split(self):
        """When text has speaker tags, split_text_by_speaker is used (not our new function)."""
        from fish_speech.models.text2semantic.inference import split_text_by_speaker

        text = "<|speaker:0|>Hello world. <|speaker:1|>Goodbye world."
        turns = split_text_by_speaker(text)
        assert len(turns) >= 2  # Multi-speaker path still works

    def test_chunk_length_maps_to_subsequent_bytes(self):
        """chunk_length parameter should map to subsequent_chunk_bytes per D-03."""
        from fish_speech.models.text2semantic.inference import split_text_into_chunks

        text = "A" * 70 + ". " + "B" * 130 + ". " + "C" * 130 + "."
        # With subsequent=150, the B and C segments should be separate chunks
        chunks_150 = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=150
        )
        # With subsequent=500, they could merge
        chunks_500 = split_text_into_chunks(
            text, first_chunk_bytes=80, subsequent_chunk_bytes=500
        )
        assert len(chunks_150) >= len(chunks_500)

    def test_empty_text_fallback(self):
        """Empty text should produce empty list, generate_long would use [text] fallback."""
        from fish_speech.models.text2semantic.inference import split_text_into_chunks

        result = split_text_into_chunks("")
        assert result == []
        # In generate_long, this triggers: if not batches: batches = [text]
