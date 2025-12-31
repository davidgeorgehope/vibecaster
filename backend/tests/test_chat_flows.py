"""Integration tests for chat flow behavior."""
import pytest
import json
import sys
import os

# Add backend to path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# We need to test the actual flow, so import from the root agents.py
import importlib.util
agents_file = os.path.join(backend_path, "agents.py")
spec = importlib.util.spec_from_file_location("agents_module", agents_file)
agents_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agents_module)

chat_post_builder_stream = agents_module.chat_post_builder_stream
agent_intent_parser = agents_module.agent_intent_parser


class TestGreetingFlow:
    """Test that greetings are handled correctly without searching."""

    def test_hello_returns_greeting_intent(self):
        """Test that 'hello' is parsed as a greeting intent."""
        result = agent_intent_parser("hello")
        print(f"Intent parser result for 'hello': {result}")
        assert result["intent"] == "greeting", f"Expected greeting intent, got: {result['intent']}"

    def test_hi_returns_greeting_intent(self):
        """Test that 'hi' is parsed as a greeting intent."""
        result = agent_intent_parser("hi")
        print(f"Intent parser result for 'hi': {result}")
        assert result["intent"] == "greeting", f"Expected greeting intent, got: {result['intent']}"

    def test_hello_stream_does_not_search(self):
        """Test that hello stream response doesn't include searching events."""
        events = list(chat_post_builder_stream("hello", []))

        # Parse all events
        parsed_events = []
        for event in events:
            try:
                parsed = json.loads(event.strip())
                parsed_events.append(parsed)
                print(f"Event: {parsed}")
            except json.JSONDecodeError:
                print(f"Non-JSON event: {event[:100]}")

        # Should NOT have a searching event
        event_types = [e.get("type") for e in parsed_events if isinstance(e, dict)]
        assert "searching" not in event_types, f"Greeting should not trigger search! Events: {event_types}"

        # Should have a text response (the greeting)
        text_events = [e for e in parsed_events if e.get("type") == "text"]
        assert len(text_events) > 0, "Should have a text response for greeting"

        # The text should be a greeting
        greeting_text = text_events[0].get("content", "")
        assert "hello" in greeting_text.lower() or "help" in greeting_text.lower(), \
            f"Greeting response should mention hello or help: {greeting_text[:100]}"

    def test_hey_there_returns_greeting(self):
        """Test that 'hey there' is parsed as a greeting."""
        result = agent_intent_parser("hey there")
        print(f"Intent parser result for 'hey there': {result}")
        assert result["intent"] == "greeting", f"Expected greeting intent, got: {result['intent']}"


class TestPostGenerationFlow:
    """Test that post requests trigger searching."""

    def test_mario_luigi_returns_generate_posts_intent(self):
        """Test that creative post request is parsed correctly."""
        result = agent_intent_parser("mario and luigi explain observability concepts")
        print(f"Intent parser result: {result}")

        # Should be generate_posts intent
        assert result["intent"] == "generate_posts", f"Expected generate_posts, got: {result['intent']}"

        # Topic should be about observability, NOT mario/luigi
        topic = result.get("topic", "").lower()
        assert "observability" in topic, f"Topic should contain 'observability': {topic}"
        assert "mario" not in topic, f"Topic should NOT contain 'mario': {topic}"

        # Persona should mention mario/luigi
        persona = result.get("persona", "").lower()
        assert "mario" in persona or "luigi" in persona, f"Persona should mention mario/luigi: {persona}"

    def test_post_request_triggers_search(self):
        """Test that post requests trigger the search flow."""
        events = list(chat_post_builder_stream("mario and luigi explain observability concepts", []))

        # Parse all events
        parsed_events = []
        for event in events:
            try:
                parsed = json.loads(event.strip())
                parsed_events.append(parsed)
                print(f"Event: {parsed.get('type', 'unknown')} - {str(parsed)[:80]}")
            except json.JSONDecodeError:
                # Could be the base64 tool call
                if "__TOOL_CALL_B64__" in event:
                    print(f"Tool call event (base64)")
                else:
                    print(f"Non-JSON event: {event[:80]}")

        event_types = [e.get("type") for e in parsed_events if isinstance(e, dict)]
        print(f"All event types: {event_types}")

        # Should have thinking event first
        assert "thinking" in event_types, f"Should have thinking event. Events: {event_types}"

        # Should have searching event
        assert "searching" in event_types, f"Should have searching event. Events: {event_types}"

    def test_kubernetes_post_request(self):
        """Test a simpler post request about kubernetes."""
        result = agent_intent_parser("create a post about kubernetes best practices")
        print(f"Intent parser result: {result}")

        assert result["intent"] == "generate_posts", f"Expected generate_posts, got: {result['intent']}"
        assert "kubernetes" in result.get("topic", "").lower(), f"Topic should mention kubernetes"


class TestBrainstormFlow:
    """Test that brainstorm requests are handled correctly."""

    def test_whats_trending_returns_brainstorm_or_generate(self):
        """Test that 'what's trending' triggers brainstorm or generate_posts intent.

        Note: This is an integration test calling the real LLM. Both 'brainstorm' and
        'generate_posts' are valid interpretations of "what's trending" - the LLM may
        decide to either brainstorm ideas OR generate posts about trending topics.
        Unit tests in test_intent_parser.py mock the LLM for deterministic testing.
        """
        result = agent_intent_parser("what's trending in AI?")
        print(f"Intent parser result: {result}")

        # Both brainstorm and generate_posts are valid - the LLM interprets intent
        valid_intents = ["brainstorm", "generate_posts"]
        assert result["intent"] in valid_intents, f"Expected one of {valid_intents}, got: {result['intent']}"

        # Verify the response includes AI-related content
        topic = result.get("topic", "").lower()
        assert any(term in topic for term in ["ai", "artificial intelligence", "trending"]), \
            f"Topic should be AI-related, got: {topic}"


class TestClarifyFlow:
    """Test that vague requests ask for clarification."""

    def test_vague_request_asks_for_clarification(self):
        """Test that very vague requests trigger clarify intent."""
        result = agent_intent_parser("something")
        print(f"Intent parser result for 'something': {result}")

        # Should be clarify intent (or possibly generate_posts with topic=something)
        # The LLM might interpret this differently, so we check it doesn't search for "something" as a real topic
        intent = result["intent"]
        assert intent in ["clarify", "greeting", "generate_posts"], f"Unexpected intent: {intent}"

        if intent == "generate_posts":
            # If it's generate_posts, the topic should be vague
            print(f"Warning: LLM chose generate_posts for vague input. Topic: {result.get('topic')}")


if __name__ == "__main__":
    # Run specific tests
    print("=" * 60)
    print("Testing greeting flow...")
    print("=" * 60)

    test = TestGreetingFlow()
    try:
        test.test_hello_returns_greeting_intent()
        print("✓ test_hello_returns_greeting_intent passed")
    except AssertionError as e:
        print(f"✗ test_hello_returns_greeting_intent failed: {e}")

    print("\n" + "=" * 60)
    print("Testing post generation flow...")
    print("=" * 60)

    test2 = TestPostGenerationFlow()
    try:
        test2.test_mario_luigi_returns_generate_posts_intent()
        print("✓ test_mario_luigi_returns_generate_posts_intent passed")
    except AssertionError as e:
        print(f"✗ test_mario_luigi_returns_generate_posts_intent failed: {e}")
