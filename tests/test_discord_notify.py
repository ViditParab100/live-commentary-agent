"""Tests for discord_notify.py — backend selection, formatting, and post routing.
Network calls are stubbed so no real Discord traffic happens."""

import discord_notify
from discord_notify import DiscordNotifier


# --- backend selection ----------------------------------------------------
def test_disabled_when_no_creds(monkeypatch):
    for k in ("DISCORD_WEBHOOK_URL", "DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"):
        monkeypatch.delenv(k, raising=False)
    n = DiscordNotifier()
    assert n.enabled is False
    assert n.post("hi") is False          # no-op when disabled

def test_webhook_mode_selected(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/a/b")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert DiscordNotifier().mode == "webhook"

def test_bot_mode_selected(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
    assert DiscordNotifier().mode == "bot"

def test_webhook_wins_over_bot(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/a/b")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
    assert DiscordNotifier().mode == "webhook"


# --- formatting -----------------------------------------------------------
def test_format_includes_emoji_and_clock(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://x")
    n = DiscordNotifier()
    out = n.format("Lead change!", "lead_change", "18:52:00")
    assert "🔄" in out
    assert "`[18:52:00]`" in out
    assert "Lead change!" in out

def test_format_unknown_type_uses_mic(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://x")
    out = DiscordNotifier().format("hello", "weird_type", None)
    assert "🎙️" in out


# --- post routing (stubbed network) --------------------------------------
class _Resp:
    def __init__(self, status): self.status_code = status
    def json(self): return {}

def test_webhook_post_calls_requests(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://hook")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    calls = {}
    def fake_post(url, **kw):
        calls["url"] = url
        calls["json"] = kw.get("json")
        return _Resp(204)
    monkeypatch.setattr(discord_notify.requests, "post", fake_post)
    assert DiscordNotifier().post("hi", "overtake", "01:02:03") is True
    assert calls["url"] == "https://hook"
    assert "hi" in calls["json"]["content"]

def test_bot_post_uses_rest_endpoint(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "999")
    calls = {}
    def fake_post(url, **kw):
        calls["url"] = url
        calls["headers"] = kw.get("headers")
        return _Resp(200)
    monkeypatch.setattr(discord_notify.requests, "post", fake_post)
    assert DiscordNotifier().post("go") is True
    assert calls["url"].endswith("/channels/999/messages")
    assert calls["headers"]["Authorization"] == "Bot tok"

def test_post_failure_returns_false_not_raise(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://hook")
    def boom(*a, **k): raise RuntimeError("network down")
    monkeypatch.setattr(discord_notify.requests, "post", boom)
    assert DiscordNotifier().post("hi") is False   # swallowed, never raises
