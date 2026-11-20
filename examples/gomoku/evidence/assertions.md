# 内置示例的断言依据

以下是原独立项目 tests/test_info.py（5154858）的原文摘录，仅供平台规则来源追踪，不是可执行测试入口。

## 无效信息请求

```python
def assert_invalid_info_response(response) -> None:
    response_json = get_json(response)
    assert response.status_code == 400
    assert response_json.get("result") is False
    assert response_json.get("reason") in INFO_INVALID_REASONS

```

## 登录后获取信息

```python
def test_info_positive_cases(case: dict, api_client):
    allure.dynamic.title(f'{case["id"]} {case["name"]}')
    payload = render_payload(case["payload"], unique_suffix())

    ensure_registered(api_client, payload, allow_duplicate=True)
    session = requests.Session()
    ensure_logged_in(api_client, payload, session=session)
    info_response = api_client.info(session=session)
    info_json = get_json(info_response)
    assert info_response.status_code == 200
    for key in case["expected_keys"]:
        assert key in info_json

    if case.get("assert_username_match"):
        assert info_json["username"] == payload["username"]

```
