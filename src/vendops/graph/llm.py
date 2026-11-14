import os
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T", bound=BaseModel)


def is_rate_limit_error(exc: BaseException) -> bool:
    """Detect if an exception is a 429 / resource exhausted error."""
    msg = str(exc).lower()
    return any(
        term in msg
        for term in (
            "429",
            "resource_exhausted",
            "resourceexhausted",
            "rate limit",
            "quota exceeded",
            "too many requests",
        )
    )


class BaseLLMAdapter(ABC):
    """Abstract thin adapter for LLM interactions."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate a raw text completion."""

    @abstractmethod
    def generate_structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        """Generate structured output conforming to a Pydantic schema."""

    async def agenerate(self, prompt: str, **kwargs: Any) -> str:
        """Asynchronously generate a raw text completion."""
        return self.generate(prompt, **kwargs)

    async def agenerate_structured(
        self, prompt: str, schema: type[T], **kwargs: Any
    ) -> T:
        """Asynchronously generate structured output conforming to a Pydantic schema."""
        return self.generate_structured(prompt, schema, **kwargs)


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini LLM adapter with jittered exponential backoff for 429 resilience."""

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_retries: int = 5,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.temperature = temperature
        self.max_retries = max_retries
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._client = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                temperature=self.temperature,
            )
        return self._client

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text with exponential backoff on 429 errors."""

        @retry(
            retry=retry_if_exception(is_rate_limit_error),
            wait=wait_exponential_jitter(initial=1.0, max=60.0),
            stop=stop_after_attempt(self.max_retries),
            reraise=True,
        )
        def _invoke_with_retry() -> str:
            client = self._get_client()
            response = client.invoke(prompt, **kwargs)
            content = response.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(str(part) for part in content)
            return str(content)

        return _invoke_with_retry()

    def generate_structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        """Generate structured Pydantic object with exponential backoff on 429."""

        @retry(
            retry=retry_if_exception(is_rate_limit_error),
            wait=wait_exponential_jitter(initial=1.0, max=60.0),
            stop=stop_after_attempt(self.max_retries),
            reraise=True,
        )
        def _invoke_structured_with_retry() -> T:
            client = self._get_client()
            structured_model = client.with_structured_output(schema)
            res: T = structured_model.invoke(prompt, **kwargs)
            return res

        return _invoke_structured_with_retry()


class FakeLLM(BaseLLMAdapter):
    """Deterministic FakeLLM for 100% offline testing and evaluations."""

    def __init__(
        self,
        default_text: str = "Deterministic test response",
        text_responses: list[str] | None = None,
        structured_responses: list[BaseModel] | None = None,
        canned_by_type: dict[type[BaseModel], BaseModel] | None = None,
    ) -> None:
        self.default_text = default_text
        self._text_queue: list[str] = list(text_responses or [])
        self._structured_queue: list[BaseModel] = list(structured_responses or [])
        self._canned_by_type: dict[type[BaseModel], BaseModel] = dict(canned_by_type or {})
        self.prompt_history: list[str] = []
        self.call_count: int = 0

    def add_text_response(self, text: str) -> None:
        self._text_queue.append(text)

    def add_structured_response(self, obj: BaseModel) -> None:
        self._structured_queue.append(obj)

    def register_structured_response(self, schema: type[T], obj: T) -> None:
        self._canned_by_type[schema] = obj

    def generate(self, prompt: str, **kwargs: Any) -> str:
        self.prompt_history.append(prompt)
        self.call_count += 1
        if self._text_queue:
            return self._text_queue.pop(0)
        return self.default_text

    def generate_structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        self.prompt_history.append(prompt)
        self.call_count += 1
        if self._structured_queue:
            item = self._structured_queue.pop(0)
            if isinstance(item, schema):
                return item
            # Attempt coercion if it matches schema structure
            if isinstance(item, BaseModel):
                return schema.model_validate(item.model_dump())
        if schema in self._canned_by_type:
            canned = self._canned_by_type[schema]
            if isinstance(canned, schema):
                return canned
            return schema.model_validate(canned.model_dump())
        raise ValueError(
            f"FakeLLM has no structured response queued or registered for schema {schema.__name__}"
        )
