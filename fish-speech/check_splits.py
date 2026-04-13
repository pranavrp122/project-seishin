from fish_speech.models.text2semantic.inference import split_text_into_chunks

PROMPTS = [
    ("warm", "[warm] I left the hallway light on because I know you're coming home late and I didn't want you walking into darkness."),
    ("exhausted", "[exhausted] I forgot what day it is. I forgot what I ate for breakfast. I am running on autopilot. The autopilot is also exhausted and requesting permission to land immediately."),
    ("angry", "[angry] Don't patronize me with that tone, I can hear it from here!"),
    ("tender", "[tender] Some mornings I wake up and just look at the ceiling feeling truly grateful that my life has you woven through every part."),
    ("professional", "[professional] The lack of structured logging across our services makes incident investigation significantly harder. It is adding at least twenty minutes to our mean time to detect."),
]

for name, text in PROMPTS:
    chunks = split_text_into_chunks(text, first_chunk_bytes=80, subsequent_chunk_bytes=200, min_chunk_bytes=50)
    print(f"{name} ({len(text)} chars) -> {len(chunks)} chunks:")
    for i, c in enumerate(chunks):
        print(f"  [{i}] ({len(c.encode())}B) {c!r}")
    print()
