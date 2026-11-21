"""One chat turn runs on the LangChain agent."""

from tests.agent.conftest import history_of, run_one_turn
from tests.scripted_chat_model import reasoning_chunk, text_chunk, tool_call_chunk

# ---- One turn on the LangChain engine · unit with a fake chat model
# Baseline: Given a fake streaming chat model that answers "Hello", a FakeProgressView and a fake answer view · When run_turn runs one message


def test_answer_streams_into_the_reply(scripted):
    # Changed: nothing
    # Then: the view got deltas joining to "Hello"; history gained the message and the answer
    # Demonstrates: the engine streams like today
    scripted.scripts.append([text_chunk("Hel"), text_chunk("lo")])
    run = run_one_turn()
    assert ("".join(run.answer.streamed), run.answer.final) == ("Hello", "Hello")
    assert history_of(run)[1:] == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello"}]


def test_tool_call_runs_and_its_result_reaches_the_model(scripted, searches):
    # Changed: the model calls web_search, then answers
    # Then: one tool step; the second model call sees the tool result
    # Demonstrates: the tool loop works
    scripted.scripts += [[tool_call_chunk("web_search", {"query": "cats"})], [text_chunk("Done")]]
    run = run_one_turn()
    assert searches == [{"query": "cats"}]
    assert [step.output for step in run.progress.tool_steps] == ["2 results"]
    assert scripted.requests[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call-1", "content": "Result: https://found.example/page"
    }
    assert run.answer.final == "Done"


def test_reasoning_opens_a_thinking_step_before_the_answer(scripted):
    # Changed: the model streams reasoning first
    # Then: a Thinking step opened, then closed before the first answer text
    # Demonstrates: thinking shows before the answer
    scripted.scripts.append([reasoning_chunk("Let me "), reasoning_chunk("think"), text_chunk("Answer")])
    run = run_one_turn()
    assert run.progress.thinking == ["Let me ", "think"]
    assert "Writing answer" in run.progress.labels
    assert run.answer.final == "Answer"


def test_empty_answer_shows_the_empty_response_note(scripted):
    # Changed: the model returns nothing
    # Then: the reply is "(The model returned an empty response.)"
    # Demonstrates: an empty answer is explained
    scripted.scripts.append([text_chunk("")])
    assert run_one_turn().answer.final == "(The model returned an empty response.)"


def test_unknown_tool_name_fails_the_step_not_the_turn(scripted):
    # Changed: the model calls a tool named nope
    # Then: the step says Unknown tool: nope and failed; the turn still finishes
    # Demonstrates: bad calls don't crash the chat
    scripted.scripts += [[tool_call_chunk("nope", {})], [text_chunk("Sorry")]]
    run = run_one_turn()
    step = run.progress.tool_steps[0]
    assert step.title == "Unknown tool: nope" and step.output.startswith("Failed: Bad tool call: nope")
    assert run.answer.final == "Sorry"


def test_bad_tool_arguments_are_treated_as_empty(scripted, searches):
    # Changed: the tool arguments aren't JSON
    # Then: the tool runs with no arguments, as today
    # Demonstrates: today's tolerance is kept
    scripted.scripts += [[tool_call_chunk("web_search", "{not json")], [text_chunk("Done")]]
    run = run_one_turn()
    assert searches == [{}]
    assert run.answer.final == "Done"
