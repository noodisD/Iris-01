"""Write a recording down word by word with faster-whisper, on this machine.

Run by agent/local_whisper.py in its own Python environment, so the speech
model and its GPU libraries stay out of the server's process and its memory.
Prints one JSON object: {"device", "duration", "words": [[start, end, word], ...]}.
"""

import argparse
import json
import sys

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--language", default=None)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--hotwords", default=None, help="terms the speakers use, to listen for")
    args = parser.parse_args()
    try:
        model, device = WhisperModel(args.model, device="cuda", compute_type="int8_float16"), "gpu"
    except Exception as exc:  # no usable GPU: slower, same words
        print(f"gpu unavailable ({type(exc).__name__}), using the cpu", file=sys.stderr)
        model, device = WhisperModel(args.model, device="cpu", compute_type="int8"), "cpu"
    # No conditioning on earlier text: it is what lets one mis-hearing repeat
    # itself for a minute. The silence filter stops words being invented in pauses.
    segments, info = model.transcribe(args.audio, language=args.language or None, beam_size=5,
                                      vad_filter=True, word_timestamps=True,
                                      condition_on_previous_text=False, hotwords=args.hotwords or None)
    words = [[round(w.start, 2), round(w.end, 2), w.word] for s in segments for w in (s.words or [])]
    json.dump({"device": device, "duration": info.duration, "words": words}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
