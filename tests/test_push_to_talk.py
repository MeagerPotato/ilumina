import asyncio

from pipecat.frames.frames import InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection

from ilumina.processors import PushToTalkGate


def run_gate(settings: list[tuple]) -> list[bytes]:
    """Send one loud audio frame through the gate after each (on, held) setting."""

    async def go():
        gate = PushToTalkGate()
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        gate.push_frame = capture
        for on, held in settings:
            if on is not None:
                gate.set(on, held)
            frame = InputAudioRawFrame(audio=b"\x10\x27" * 160, sample_rate=16000, num_channels=1)
            await PushToTalkGate.process_frame(gate, frame, FrameDirection.DOWNSTREAM)
        return [f.audio for f in out]

    return asyncio.run(go())


def test_heard_as_before_until_the_dashboard_turns_push_to_talk_on():
    assert run_gate([(None, None)]) == [b"\x10\x27" * 160]


def test_silent_between_holds_and_heard_while_held():
    off, held, let_go = run_gate([(True, False), (True, True), (True, False)])
    assert off == bytes(320) and let_go == bytes(320)
    assert held == b"\x10\x27" * 160


def test_frames_keep_flowing_as_silence_so_the_turn_can_end():
    (frame,) = run_gate([(True, False)])
    assert len(frame) == 320  # same length: speech to text still gets audio


def test_switching_push_to_talk_off_opens_the_microphone():
    assert run_gate([(True, False), (False, False)])[1] == b"\x10\x27" * 160
