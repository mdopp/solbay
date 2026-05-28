"""Tests for client-id derivation from the socket peer.

Regression guard for the previously-undefined `self.client_id` referenced
in the conversation endpoint: Wyoming exposes no client identity, so it is
derived from the connection peer here.
"""

from __future__ import annotations

from gatekeeper.handler import client_id_from_peername


def test_client_id_from_tcp_peername():
    assert client_id_from_peername(("192.168.178.42", 53124)) == "192.168.178.42"


def test_client_id_from_unix_socket_path():
    assert client_id_from_peername("/run/wyoming/sat.sock") == "/run/wyoming/sat.sock"


def test_client_id_none_when_peer_missing():
    assert client_id_from_peername(None) is None
    assert client_id_from_peername(()) is None


def test_client_id_none_when_host_empty():
    assert client_id_from_peername(("", 5000)) is None
