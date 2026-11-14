from pipecat.processors.aggregators.llm_context import LLMContext, LLMSpecificMessage

from bot import recent_text


def test_recent_text_skips_model_specific_entries_and_non_text():
    context = LLMContext()
    context.add_message({"role": "user", "content": "I think it is two"})
    context.add_message(LLMSpecificMessage(llm="google", message={"thought": "..."}))
    context.add_message({"role": "assistant", "content": "Good. What comes next?"})
    context.add_message({"role": "user", "content": [{"type": "image_url", "image_url": {}}]})
    context.add_message({"role": "developer", "content": "Student state, turn 1"})

    assert recent_text(context) == "Student: I think it is two\nTutor: Good. What comes next?"
