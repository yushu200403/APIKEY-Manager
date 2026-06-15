from dataclasses import dataclass

import requests

from .validators import parse_formats


TIMEOUT_SECONDS = 30


@dataclass
class TestResult:
    message: str
    reasoning: str = ""


def choose_format(api_format, preferred=None):
    formats = parse_formats(api_format)
    if preferred and preferred in formats:
        return preferred
    for item in ("openai_response", "openai_chat_completion", "anthropic_message"):
        if item in formats:
            return item
    raise ValueError("供应商没有可用的API格式")


def test_chat_endpoint(provider, api_key, config):
    fmt = choose_format(provider["api_format"])
    model = (config.get("test_model") or "").strip()
    if not model:
        raise ValueError("请先填写测试模型")
    if fmt == "openai_response":
        return _test_openai_response(provider["base_url"], api_key, config, model)
    if fmt == "openai_chat_completion":
        return _test_openai_chat_completion(provider["base_url"], api_key, config, model)
    if fmt == "anthropic_message":
        return _test_anthropic_message(provider["base_url"], api_key, config, model)
    raise ValueError(f"不支持的API格式：{fmt}")


def fetch_model_ids(provider, api_key):
    fmt = choose_format(provider["api_format"])
    headers = _headers(fmt, api_key)
    url = provider["base_url"].rstrip("/") + "/models"
    response = _request("get", url, headers=headers)
    payload = _parse_response(response)
    models = payload.get("data", payload)
    if not isinstance(models, list):
        raise ValueError("模型列表响应格式不符合预期")
    ids = []
    for item in models:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if model_id:
                ids.append(str(model_id))
    if not ids:
        raise ValueError("响应中没有可识别的模型ID")
    return sorted(dict.fromkeys(ids))


def _headers(fmt, api_key):
    if fmt.startswith("openai"):
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if fmt == "anthropic_message":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    raise ValueError(f"不支持的API格式：{fmt}")


def _test_openai_response(base_url, api_key, config, model):
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": config["user_prompt"]},
        ],
        "max_output_tokens": 50,
    }
    response = _request(
        "post",
        base_url.rstrip("/") + "/responses",
        headers=_headers("openai_response", api_key),
        json=body,
    )
    payload = _parse_response(response)
    text = payload.get("output_text") or _extract_response_text(payload)
    reasoning = _extract_response_reasoning(payload)
    return _result(text, "请求成功，但响应中没有文本内容", reasoning)


def _test_openai_chat_completion(base_url, api_key, config, model):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": config["user_prompt"]},
        ],
        "max_tokens": 50,
    }
    response = _request(
        "post",
        base_url.rstrip("/") + "/chat/completions",
        headers=_headers("openai_chat_completion", api_key),
        json=body,
    )
    payload = _parse_response(response)
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    text = _extract_chat_completion_text(choice) if choice else ""
    reasoning = _extract_chat_completion_reasoning(choice) if choice else ""
    return _result(text, "请求成功，但响应中没有文本内容", reasoning)


def _test_anthropic_message(base_url, api_key, config, model):
    body = {
        "model": model,
        "system": config["system_prompt"],
        "messages": [{"role": "user", "content": config["user_prompt"]}],
        "max_tokens": 50,
    }
    response = _request(
        "post",
        base_url.rstrip("/") + "/messages",
        headers=_headers("anthropic_message", api_key),
        json=body,
    )
    payload = _parse_response(response)
    content = payload.get("content") or []
    text_parts = []
    reasoning_parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") != "thinking" and item.get("text"):
            text_parts.append(item["text"])
        if isinstance(item, dict) and item.get("type") == "thinking":
            reasoning = item.get("thinking") or item.get("text")
            if reasoning:
                reasoning_parts.append(str(reasoning))
    return _result("\n".join(text_parts), "请求成功，但响应中没有文本内容", "\n".join(reasoning_parts))


def _parse_response(response):
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"HTTP {response.status_code}，响应不是有效JSON") from exc
    if response.status_code >= 400:
        message = payload.get("error", payload)
        if isinstance(message, dict):
            message = message.get("message") or message.get("type") or str(message)
        raise ValueError(f"HTTP {response.status_code}：{message}")
    return payload


def _extract_response_text(payload):
    text_parts = []
    for output in payload.get("output") or []:
        for item in output.get("content") or []:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    text_parts.append(text)
    return "\n".join(text_parts)


def _extract_chat_completion_text(choice):
    message = choice.get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                text_parts.append(item["text"])
        return "\n".join(text_parts)
    return choice.get("text", "")


def _extract_response_reasoning(payload):
    parts = []
    for output in payload.get("output") or []:
        if not isinstance(output, dict):
            continue
        if output.get("type") == "reasoning":
            parts.extend(_text_values(output.get("summary")))
            parts.extend(_text_values(output.get("content")))
            text = output.get("text")
            if text:
                parts.append(str(text))
        reasoning = output.get("reasoning")
        if reasoning:
            parts.extend(_text_values(reasoning))
    reasoning = payload.get("reasoning")
    if reasoning:
        parts.extend(_text_values(reasoning))
    return "\n".join(part for part in parts if part).strip()


def _extract_chat_completion_reasoning(choice):
    message = choice.get("message") or {}
    candidates = [
        message.get("reasoning_content"),
        message.get("reasoning"),
        choice.get("reasoning_content"),
        choice.get("reasoning"),
    ]
    parts = []
    for value in candidates:
        parts.extend(_text_values(value))
    return "\n".join(part for part in parts if part).strip()


def _text_values(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        parts = []
        for key in ("text", "content", "summary", "thinking", "reasoning"):
            parts.extend(_text_values(value.get(key)))
        return parts
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_text_values(item))
        return parts
    return [str(value)]


def _request(method, url, **kwargs):
    try:
        return requests.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.Timeout as exc:
        raise ValueError("网络请求超时") from exc
    except requests.RequestException as exc:
        raise ValueError(f"网络请求失败：{exc}") from exc


def _summary(text, fallback):
    text = (text or "").strip()
    if not text:
        raise ValueError(fallback)
    return text[:300]


def _result(text, fallback, reasoning=""):
    return TestResult(
        message=_summary(text, fallback),
        reasoning=(reasoning or "").strip()[:4000],
    )
