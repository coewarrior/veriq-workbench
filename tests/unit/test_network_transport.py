from __future__ import annotations

import datetime
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from api_test_tool import network_transport as transport


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError, ssl.SSLError):
                # Expected for the negative TLS verification tests.
                pass

        def do_GET(self):
            self.server.received.append({"host": self.headers.get("Host"), "path": self.path})
            self.send_response(self.server.status)
            if self.server.status == 302:
                self.send_header("Location", "http://127.0.0.1:1/private")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.received = []
    httpd.status = 200
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def dns_rebind(monkeypatch):
    calls = []

    def getaddrinfo(host, port, *args, **kwargs):
        calls.append(host)
        # A second lookup would connect to a different loopback destination.
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1" if len(calls) == 1 else "127.0.0.2", port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return calls


def test_dns_is_resolved_once_and_socket_reconnect_stays_pinned(server, monkeypatch):
    calls = dns_rebind(monkeypatch)
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin + "/api", (origin,)) as session:
        for _ in range(2):
            response = session.get(origin + "/test?count=2", timeout=2)
            assert response.text == "OK"
        assert session._pinned_ips == ("127.0.0.1",)
    assert calls == ["safe.example"]
    assert len(server.received) == 2
    assert all(request == {"host": f"safe.example:{server.server_port}", "path": "/test?count=2"} for request in server.received)


def test_ip_literal_uses_no_dns_and_host_override_cannot_change_authority(server, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Numeric destination must not be resolved")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    origin = f"http://127.0.0.1:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        assert session.get(origin + "/", headers={"Host": "metadata.internal"}).text == "OK"
    assert server.received[0]["host"] == f"127.0.0.1:{server.server_port}"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "192.0.2.20", "192.168.2.3", "169.254.169.254", "0.0.0.0", "224.0.0.1", "::1", "fc00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1", "198.51.100.10"])
def test_nonpublic_and_legacy_targets_are_denied(address):
    host = f"[{address}]" if ":" in address else address
    with pytest.raises(transport.NetworkPolicyError):
        transport.pinned_session("https://" + host)


@pytest.mark.parametrize("address", ["198.51.100.10", "::ffff:198.51.100.10"])
def test_legacy_ip_cannot_be_allowed_even_by_trusted_origin(address):
    host = f"[{address}]" if ":" in address else address
    origin = "http://" + host
    with pytest.raises(transport.NetworkPolicyError):
        transport.pinned_session(origin, (origin,))


def test_every_dns_answer_must_be_global(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
    ])
    with pytest.raises(transport.NetworkPolicyError):
        transport.pinned_session("https://mixed.example")


def test_legacy_ip_hidden_behind_dns_is_denied(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("198.51.100.10", 443))])
    with pytest.raises(transport.NetworkPolicyError):
        transport.pinned_session("https://alias.example", ("https://alias.example",))


def test_public_ips_validate_without_external_request(monkeypatch):
    calls = []

    def resolve(host, port, *args, **kwargs):
        calls.append(host)
        return [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:4700:4700::1111", port, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with transport.pinned_session("https://public.example/v1") as session:
        assert session._pinned_ips == ("8.8.8.8", "2606:4700:4700::1111")
        request = requests.Request("GET", "https://public.example/v1/test").prepare()
        pool = session.get_adapter(request.url).get_connection_with_tls_context(request, True)
        assert pool.host == "8.8.8.8"
        assert pool.assert_hostname == "public.example"
        assert pool.conn_kw["server_hostname"] == "public.example"
        assert pool.cert_reqs == "CERT_REQUIRED"
    assert calls == ["public.example"]


@pytest.mark.parametrize("target", ["http://other.example:80/", "https://safe.example/", "http://safe.example:1/", "file:///etc/passwd"])
def test_session_cannot_change_origin(server, monkeypatch, target):
    calls = dns_rebind(monkeypatch)
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(transport.NetworkPolicyError):
            session.get(target, timeout=1)
    assert server.received == []
    assert calls == ["safe.example"]


def test_redirect_is_rejected_without_second_request(server, monkeypatch):
    calls = dns_rebind(monkeypatch)
    server.status = 302
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(transport.NetworkPolicyError, match="重定向"):
            session.get(origin + "/", allow_redirects=True)
    assert calls == ["safe.example"]
    assert len(server.received) == 1


def test_redirect_rejected_before_requests_drains_response_body(server, monkeypatch):
    dns_rebind(monkeypatch)
    server.status = 302
    original = requests.Response.iter_content

    def read_guard(response, *args, **kwargs):
        if response.status_code == 302:
            pytest.fail("Requests must not drain a redirect body before the response limit can run")
        return original(response, *args, **kwargs)

    monkeypatch.setattr(requests.Response, "iter_content", read_guard)
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(transport.NetworkPolicyError, match="重定向"):
            session.get(origin + "/", stream=True, allow_redirects=False)
    assert len(server.received) == 1


def test_proxy_and_verification_bypass_and_adapter_replacement_are_rejected(server, monkeypatch):
    dns_rebind(monkeypatch)
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(transport.NetworkPolicyError):
            session.get(origin + "/", verify=False)
        with pytest.raises(transport.NetworkPolicyError):
            session.get(origin + "/", proxies={"http": "http://proxy.example"})
        with pytest.raises(transport.NetworkPolicyError):
            session.trust_env = True
        with pytest.raises(transport.NetworkPolicyError):
            session.verify = False
        with pytest.raises(transport.NetworkPolicyError):
            session.mount("http://", requests.adapters.HTTPAdapter())
    assert server.received == []


def test_environment_proxy_is_not_used(server, monkeypatch):
    dns_rebind(monkeypatch)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    origin = f"http://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        assert session.get(origin + "/").text == "OK"
        assert session.get_adapter(origin).max_retries.total == 0


@pytest.mark.parametrize("url", ["https://user:secret@example.test", "https://example.test?key=secret", "https://example.test#secret", "https://example.test:0", "https://example.test:99999", "https://example.test\\@127.0.0.1", "https://example.test\n", "ftp://example.test"])
def test_invalid_base_url_rejected_without_resolving(url, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not resolve invalid URL")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    with pytest.raises(transport.NetworkPolicyError) as error:
        transport.pinned_session(url)
    assert "secret" not in str(error.value)


@pytest.fixture
def tls_material(tmp_path):
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Local Transport Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
          .not_valid_after(now + datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                      data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                      encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "safe.example")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("safe.example")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                                        data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                        encipher_only=False, decipher_only=False), critical=True)
            .sign(ca_key, hashes.SHA256()))
    ca_path = tmp_path / "ca.pem"
    key_path = tmp_path / "key.pem"
    cert_path = tmp_path / "cert.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return ca_path, cert_path, key_path


def test_tls_uses_original_sni_and_hostname_with_pinned_socket(server, tls_material, monkeypatch):
    ca_path, cert_path, key_path = tls_material
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    sni = []
    context.set_servername_callback(lambda socket, server_name, context: sni.append(server_name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    calls = dns_rebind(monkeypatch)
    origin = f"https://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        assert session.get(origin + "/tls", verify=str(ca_path), timeout=2).text == "OK"
    assert calls == ["safe.example"]
    assert sni == ["safe.example"]
    assert server.received == [{"host": f"safe.example:{server.server_port}", "path": "/tls"}]


def test_tls_hostname_mismatch_is_not_bypassed(server, tls_material, monkeypatch):
    ca_path, cert_path, key_path = tls_material
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    calls = dns_rebind(monkeypatch)
    origin = f"https://wrong.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(requests.exceptions.SSLError, match="hostname|match"):
            session.get(origin + "/tls", verify=str(ca_path), timeout=2)
    assert calls == ["wrong.example"]
    assert server.received == []


def test_tls_untrusted_certificate_is_not_bypassed(server, tls_material, monkeypatch):
    _, cert_path, key_path = tls_material
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    calls = dns_rebind(monkeypatch)
    origin = f"https://safe.example:{server.server_port}"
    with transport.pinned_session(origin, (origin,)) as session:
        with pytest.raises(requests.exceptions.SSLError):
            session.get(origin + "/tls", verify=True, timeout=2)
    assert calls == ["safe.example"]
    assert server.received == []
