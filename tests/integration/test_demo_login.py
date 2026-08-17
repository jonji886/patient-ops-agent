import pytest


@pytest.mark.asyncio
async def test_demo_account_directory_exposes_only_switcher_safe_metadata(sut):
    response = await sut.client.get("/api/v1/auth/demo-accounts")

    assert response.status_code == 200
    assert response.json() == [
        {"username": "patient", "display_name": "演示患者", "actor_role": "PATIENT"},
        {"username": "operator", "display_name": "演示客服", "actor_role": "OPERATOR"},
        {"username": "admin", "display_name": "演示管理员", "actor_role": "ADMIN"},
    ]
    assert "password" not in response.text
    assert "patient_id" not in response.text


@pytest.mark.asyncio
async def test_demo_login_issues_a_token_that_can_create_a_conversation(sut):
    login = await sut.client.post(
        "/api/v1/auth/login",
        json={"username": "patient", "password": "123456"},
    )

    assert login.status_code == 200
    payload = login.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in_seconds"] == 86400
    assert payload["display_name"] == "演示患者"
    assert payload["actor_role"] == "PATIENT"
    assert '"password"' not in login.text

    conversation = await sut.client.post(
        "/api/v1/conversations",
        json={"channel": "web_simulator"},
        headers={"Authorization": f"Bearer {payload['access_token']}", "X-Request-ID": "login-conversation-1"},
    )
    assert conversation.status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(("username", "password", "role", "display_name"), [
    ("operator", "123456", "OPERATOR", "演示客服"),
    ("admin", "123456", "ADMIN", "演示管理员"),
])
async def test_demo_login_issues_role_scoped_actor_tokens(sut, username, password, role, display_name):
    response = await sut.client.post("/api/v1/auth/login", json={"username": username, "password": password})

    assert response.status_code == 200
    assert response.json()["actor_role"] == role
    assert response.json()["display_name"] == display_name


@pytest.mark.asyncio
async def test_demo_login_rejects_invalid_credentials_without_disclosing_the_reason(sut):
    response = await sut.client.post(
        "/api/v1/auth/login",
        json={"username": "patient", "password": "incorrect-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert response.json()["error"]["message"] == "用户名或密码错误"


@pytest.mark.asyncio
async def test_agent_api_does_not_serve_an_embedded_runtime_page(sut):
    response = await sut.client.get("/")

    assert response.status_code == 404
