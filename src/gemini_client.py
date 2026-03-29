import os
from typing import Any, Optional

from .prompt_builder import build_parser_prompt, build_summary_prompt
from .query_parser import extract_json_from_text


def get_gemini_api_key(streamlit_secrets: Optional[Any] = None) -> str | None:
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key

    if streamlit_secrets is not None:
        try:
            if "GEMINI_API_KEY" in streamlit_secrets:
                value = streamlit_secrets["GEMINI_API_KEY"]
                if value:
                    return str(value)
        except Exception:
            pass

    return None


def is_gemini_available(streamlit_secrets: Optional[Any] = None) -> bool:
    return bool(get_gemini_api_key(streamlit_secrets))


def _client(streamlit_secrets: Optional[Any] = None):
    api_key = get_gemini_api_key(streamlit_secrets)
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

    from google import genai

    return genai.Client(api_key=api_key)


def parse_question_with_gemini(
    question: str,
    category: str,
    manufacturers: list[str],
    brands: list[str],
    types: list[str],
    markets: list[str],
    periods: list[str],
    default_period: str,
    streamlit_secrets: Optional[Any] = None,
    model: str = "gemini-3-flash-preview",
) -> dict[str, Any]:
    client = _client(streamlit_secrets)
    prompt = build_parser_prompt(
        question=question,
        category=category,
        manufacturers=manufacturers,
        brands=brands,
        types=types,
        markets=markets,
        periods=periods,
        default_period=default_period,
    )
    response = client.models.generate_content(model=model, contents=prompt)
    data = extract_json_from_text(response.text)
    data["parser_mode"] = "gemini"
    return data


def summarize_with_gemini(
    question: str,
    structured_query: dict,
    computed_context: dict,
    streamlit_secrets: Optional[Any] = None,
    model: str = "gemini-3-flash-preview",
) -> str:
    client = _client(streamlit_secrets)
    prompt = build_summary_prompt(question, structured_query, computed_context)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()
