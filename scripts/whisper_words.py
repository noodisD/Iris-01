"""Write a recording down word by word with faster-whisper, on this machine.

Run by agent/local_whisper.py in its own Python environment, so the speech
model and its GPU libraries stay out of the server's process and its memory.
Prints one JSON object: {"device", "duration", "words": [[start, end, word], ...]}.
"""

import argparse
import json
import sys

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

RATE = 16000
#: Whisper is given the recording this many seconds at a time (see `pieces`).
PIECE_SECONDS = 600


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--language", default=None)
    parser.add_argument("--model", default="large-v3")
    args = parser.parse_args()
    try:
        model, device = WhisperModel(args.model, device="cuda", compute_type="int8_float16"), "gpu"
    except Exception as exc:  # no usable GPU: slower, same words
        print(f"gpu unavailable ({type(exc).__name__}), using the cpu", file=sys.stderr)
        model, device = WhisperModel(args.model, device="cpu", compute_type="int8"), "cpu"
    audio = decode_audio(args.audio, sampling_rate=RATE)
    words = []
    for start, end in pieces(audio):
        # No conditioning on earlier text: it is what lets one mis-hearing repeat
        # itself for a minute. The silence filter stops words being invented in pauses.
        segments, _ = model.transcribe(audio[start:end], language=args.language or None, beam_size=5,
                                       vad_filter=True, word_timestamps=True,
                                       condition_on_previous_text=False)
        offset = start / RATE
        words += [[round(w.start + offset, 2), round(w.end + offset, 2), w.word]
                  for s in segments for w in (s.words or [])]
    json.dump({"device": device, "duration": len(audio) / RATE, "words": words}, sys.stdout, ensure_ascii=False)


def pieces(audio, length: int = PIECE_SECONDS * 16000, search: int = 15 * 16000) -> list[tuple[int, int]]:
    """The recording cut into pieces of about PIECE_SECONDS, each at the quietest
    half-second near its mark, so no word is cut in two.

    Whole, Whisper can move past speech and not come back to it: on an
    hour-long session, ten minutes at a time wrote 12% more words, most of
    them in stretches the whole-file run had thinned out.
    """
    import numpy as np

    frame = RATE // 2
    cuts = [0]
    while len(audio) - cuts[-1] > length + search:
        mark = cuts[-1] + length
        window = audio[mark - search:mark + search]
        energy = [float(np.mean(window[i:i + frame] ** 2)) for i in range(0, len(window) - frame, frame // 2)]
        cuts.append(mark - search + int(np.argmin(energy)) * (frame // 2) + frame // 2)
    return list(zip(cuts, [*cuts[1:], len(audio)]))


if __name__ == "__main__":
    main()
