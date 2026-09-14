"""
Standalone smoke check for the local model.

Not part of the test suite - run it by hand to confirm Ollama is up and the
configured model is installed and returning JSON:

    python backend/test_ollama.py
"""

import asyncio
import sys

import config
import llm


async def main() -> int:
    print(f"Model:    {config.OLLAMA_MODEL}")
    print(f"Endpoint: {config.OLLAMA_URL}")
    print("Sending a trivial prompt...\n")

    try:
        result = await llm.generate_json(
            'Return ONLY this JSON object: {"name": "John"}',
            timeout=30,
            stage="smoke-test",
            options={"temperature": 0},
        )
    except llm.LLMUnavailableError as exc:
        print(f"FAILED - {exc.message}\n  {exc.detail}")
        print("\nIs Ollama running? Try:  ollama serve")
        print(f"Is the model installed? Try:  ollama pull {config.OLLAMA_MODEL}")
        return 1
    except llm.LLMError as exc:
        print(f"FAILED - [{exc.code}] {exc.message}\n  {exc.detail}")
        return 1
    finally:
        await llm.close_client()

    print(f"OK - model returned: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
