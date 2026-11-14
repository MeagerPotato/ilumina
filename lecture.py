"""Record a lecture through the Vexo band library and teach Ilumina from it.

    uv run lecture.py record --band 42        your Vexo band (its own mic, Bluetooth)
    uv run lecture.py record --usb            your Vexo band on the USB cable
    uv run lecture.py record                  no band: Mac mic as the band's mic
    uv run lecture.py record --seconds 60     stop after a minute; Ctrl+C stops any time
    uv run lecture.py record --file talk.m4a  a recording instead of the live mic
    uv run lecture.py record --text talk.txt  a transcript you already have, no sound
    uv run lecture.py plan                    a study plan from everything in memory
    uv run lecture.py show                    what Ilumina remembers
    uv run lecture.py forget                  delete all of it

Nothing goes into memory unless you say yes at the end (or pass --save).
"""

import argparse
import os
import sys
from pathlib import Path

import certifi

# Same fix as bot.py: some macOS Pythons have no root certificates.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from google import genai
from vexo_open.sync import VexoError

from ilumina import config, memory, vexo_band
from ilumina.transcribe import to_wav, transcribe


def ask_yes(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def read_text(path: str) -> str:
    """A transcript someone already has, as text. Skips the band and Deepgram."""
    if not config.GOOGLE_API_KEY:
        sys.exit("Add GOOGLE_API_KEY to .env first.")
    try:
        transcript = Path(path).read_text().strip()
    except (OSError, ValueError) as e:  # missing, or not plain text
        sys.exit(f"Could not read {path}: {e}")
    if not transcript:
        sys.exit(f"{path} is empty.")
    print(f"Read {len(transcript.split())} words from {path}.")
    print("This text did not come through the Vexo band. It goes to Google Gemini for notes.")
    return transcript


def listen(args) -> str:
    """Record through the Vexo band library and get the words from Deepgram."""
    # Check the keys first, so a lecture is never recorded for nothing.
    missing = [k for k in ("DEEPGRAM_API_KEY", "GOOGLE_API_KEY") if not getattr(config, k)]
    if missing:
        sys.exit(f"Add {' and '.join(missing)} to .env first.")
    if args.usb:
        print("Listening on the Vexo band that is plugged in by USB cable.")
        source = None
    elif args.band:
        print(f"Listening on Vexo band {args.band} over Bluetooth. Double-tap it now, so its")
        print("light blinks blue and it can be found. Close anything else connected to it.")
        source = None
    elif args.file:
        print(f"Playing {args.file} through the Vexo pretend band (at real speed).")
        source = vexo_band.file_packets(args.file)
    else:
        print("Listening on this computer's microphone as the Vexo band's microphone.")
        source = vexo_band.mic_packets()
    print("Tell the people near you that the lecture is being recorded. When it ends, the")
    print("sound goes to Deepgram for text and the text to Google Gemini for notes.")
    print("Press Ctrl+C to stop.")

    def progress(seconds):
        print(f"\r  recording {int(seconds) // 60}:{int(seconds) % 60:02d}", end="", flush=True)

    try:
        pcm = vexo_band.record(
            source=source,
            seconds=args.seconds,
            band_number=args.band,
            usb=args.usb,
            on_progress=progress,
        )
    except VexoError as e:
        if not (args.band or args.usb):
            raise
        # The lecture is still happening, so do not lose it: listen on this computer.
        print(f"\nThe band did not connect: {e}")
        print("Listening on this computer's microphone as the band's microphone instead.")
        args.band, args.usb = None, False  # what gets saved says where the sound came from
        pcm = vexo_band.record(
            source=vexo_band.mic_packets(), seconds=args.seconds, on_progress=progress
        )
    print(f"\nGot {len(pcm) / 32000:.0f} seconds of sound. Sending it to Deepgram for text...")
    try:
        transcript = transcribe(pcm, config.DEEPGRAM_API_KEY)
    except RuntimeError as e:
        print(e)
        if ask_yes("Keep the recording on this computer so you can try again?"):
            path = memory.MEMORY_DIR / "recordings" / f"{memory._now()}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(to_wav(pcm))
            print(f"Kept. Try again with: uv run lecture.py record --file {path}")
        sys.exit(1)
    if not transcript:
        sys.exit("Deepgram heard no words. Check the microphone and try again.")
    return transcript


def record(args) -> None:
    transcript = read_text(args.text) if args.text else listen(args)
    print(f"\n--- Transcript ---\n{transcript[:1500]}{' ...' if len(transcript) > 1500 else ''}")

    print("\nMaking study notes with Gemini...")
    try:
        client = genai.Client(api_key=config.GOOGLE_API_KEY)
        notes = memory.lecture_notes(client, config.GOOGLE_MODEL, transcript)
    except Exception as e:  # noqa: BLE001 - keep the transcript even when notes fail
        print(f"Gemini could not make notes ({e}). You can still save the transcript.")
        notes = memory.empty_notes()
    print(f"\n--- {notes['title']} ({notes['subject']}) ---\n{notes['summary']}")
    for concept in notes["key_concepts"]:
        print(f"  * {concept['name']}: {concept['explanation']}")

    if args.save or ask_yes("\nSave this lecture to Ilumina's memory so the tutor can use it?"):
        if args.text:
            source_name = f"text file {args.text}"
        else:
            band = "Vexo band on USB" if args.usb else args.band and f"Vexo band {args.band}"
            source_name = band or args.file or "computer mic"
        path = memory.save(
            "lectures", {"source": source_name, "transcript": transcript, "notes": notes}
        )
        print(f"Saved to {path}. Ilumina will use it in the next tutoring session.")
    else:
        print("Not saved. Nothing was kept on this computer.")


def plan(args) -> None:
    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    text = memory.study_plan(client, config.GOOGLE_MODEL, days=args.days)
    path = memory.PLAN_PATH
    path.write_text(text + "\n")
    print(text)
    print(f"\n(Also saved to {path})")


def show(_args) -> None:
    lectures, sessions = memory.load("lectures"), memory.load("sessions")
    print(f"{len(lectures)} lecture(s), {len(sessions)} tutoring session(s) in memory.")
    for lec in lectures:
        print(f"- {lec['saved_at']}  {lec['notes']['title']}  ({lec['source']})")
    note = memory.tutor_note()
    if note:
        print("\nWhat the tutor is told:" + note)


def forget(_args) -> None:
    if ask_yes("Delete everything Ilumina remembers?"):
        memory.forget()
        print("Deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="record a lecture")
    rec.add_argument("--seconds", type=float, help="stop after this many seconds")
    rec.add_argument("--file", help="a sound file to use instead of the live microphone")
    rec.add_argument("--band", type=int, help="number of your Vexo band (Bluetooth)")
    rec.add_argument("--usb", action="store_true", help="your Vexo band on the USB cable")
    rec.add_argument("--text", help="a transcript in a text file, instead of sound")
    rec.add_argument("--save", action="store_true", help="save to memory without asking")
    rec.set_defaults(run=record)
    pl = sub.add_parser("plan", help="make a study plan from memory")
    pl.add_argument("--days", type=int, default=3)
    pl.set_defaults(run=plan)
    sub.add_parser("show", help="show what Ilumina remembers").set_defaults(run=show)
    sub.add_parser("forget", help="delete all memory").set_defaults(run=forget)
    args = parser.parse_args()
    try:
        args.run(args)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
