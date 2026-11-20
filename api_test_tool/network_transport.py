"""Resolve once, validate every address, connect only to a validated numeric IP.

The URL, Host header, TLS SNI and certificate hostname remain the original host.
Only the socket destination is pinned. Intended for requests >= 2.32.2 / urllib3 2.x;
verified against requests 2.34.2 and urllib3 2.7.0. No process-wide DNS patches.
"""
from __future__ import annotations

import ipaddress
import socket
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import idna
import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError


DENIED_ADDRESSES = frozenset({"198.51.100.10"})


class NetworkPolicyError(ValueError):
    """A fixed, non-sensitive message for configuration/network policy failures."""


@dataclass(frozen=True)
class _Origin:
    scheme: str
    hostname: str
    port: int

    @property
    def authority(self) -> str:
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        return host if self.port == (443 if self.scheme == "https" else 80) else f"{host}:{self.port}"

    @property
    def url(self) -> str:
        return f"{self.scheme}://{self.authority}"


def _origin(url: str, *, base: bool = False, only_origin: bool = False) -> _Origin:
    if not isinstance(url, str) or not url or len(url) > 16384:
        raise NetworkPolicyError("请求地址格式不正确。")
    if any(ord(char) < 33 or ord(char) == 127 for char in url) or "\\" in url:
        raise NetworkPolicyError("请求地址不能包含空白、控制字符或反斜杠。")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or "#" in url:
            raise ValueError
        if base and "?" in url:
            raise ValueError
        if only_origin and (parsed.path not in ("", "/") or "?" in url):
            raise ValueError
        if "%" in parsed.netloc:
            raise ValueError
        hostname = parsed.hostname
        try:
            hostname = str(ipaddress.ip_address(hostname))
        except ValueError:
            hostname = idna.encode(hostname, uts46=True).decode("ascii").lower()
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError
        return _Origin(parsed.scheme, hostname, port)
    except (ValueError, UnicodeError, idna.IDNAError):
        raise NetworkPolicyError("请求地址必须为 HTTP(S)，不能含账号、片段或无效端口；基础地址不能含查询参数。") from None


def _effective_ipv4(address):
    return address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address


def _allowed(address, trusted: bool) -> bool:
    effective = _effective_ipv4(address)
    if str(effective) in DENIED_ADDRESSES:
        return False
    if trusted:
        return not (address.is_unspecified or address.is_multicast or effective.is_unspecified or effective.is_multicast)
    if not effective.is_global or address.is_multicast:
        return False
    # Transition addresses must not smuggle a private/denied IPv4 destination.
    if isinstance(address, ipaddress.IPv6Address):
        embedded = [address.sixtofour] if address.sixtofour else list(address.teredo or ())
        if any(ip is not None and (not ip.is_global or str(ip) in DENIED_ADDRESSES) for ip in embedded):
            return False
    return True


def _resolve_once(origin: _Origin, trusted: bool) -> tuple[str, ...]:
    try:
        literal = ipaddress.ip_address(origin.hostname)
    except ValueError:
        try:
            records = socket.getaddrinfo(origin.hostname, origin.port, family=socket.AF_UNSPEC,
                                         type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        except OSError:
            raise NetworkPolicyError("无法解析请求域名。") from None
        addresses = []
        for family, socktype, proto, _canonname, sockaddr in records:
            if family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM:
                continue
            try:
                if "%" in str(sockaddr[0]):
                    raise ValueError
                address = ipaddress.ip_address(sockaddr[0])
                if (family == socket.AF_INET) != (address.version == 4):
                    raise ValueError
                if family == socket.AF_INET6 and len(sockaddr) >= 4 and sockaddr[3] != 0:
                    raise ValueError
                addresses.append(address)
            except (ValueError, IndexError, TypeError):
                raise NetworkPolicyError("域名返回了无效网络地址。") from None
    else:
        addresses = [literal]
    if not addresses:
        raise NetworkPolicyError("域名没有可连接的 TCP 地址。")
    if not all(_allowed(address, trusted) for address in addresses):
        raise NetworkPolicyError("请求目标包含未授权的内网、保留地址或禁用地址。")
    # A single chosen IP is retained for the session, including reopened sockets.
    # IPv4 first avoids hosts advertising IPv6 when this deployment has no route.
    return tuple(str(address) for address in sorted(set(addresses), key=lambda address: (address.version, int(address))))


class _NumericSocketMixin:
    def _new_conn(self):
        # The pool accepts only an already validated numeric host. Do not call
        # urllib3.util.connection.create_connection: it performs getaddrinfo again.
        try:
            address = ipaddress.ip_address(self.host.strip("[]"))
        except ValueError:
            raise NetworkPolicyError("固定连接地址不是有效 IP。") from None
        family = socket.AF_INET if address.version == 4 else socket.AF_INET6
        destination = (str(address), self.port) if address.version == 4 else (str(address), self.port, 0, 0)
        sock = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        try:
            for option in self.socket_options or ():
                sock.setsockopt(*option)
            if self.timeout is None or isinstance(self.timeout, (int, float)):
                sock.settimeout(self.timeout)
            if self.source_address:
                sock.bind(self.source_address)
            sock.connect(destination)
        except socket.timeout:
            sock.close()
            raise ConnectTimeoutError(self, "固定地址连接超时。") from None
        except OSError:
            sock.close()
            raise NewConnectionError(self, "无法连接已校验的目标地址。") from None
        except BaseException:
            sock.close()
            raise
        sys.audit("http.client.connect", self, self.host, self.port)
        return sock


class _PinnedHTTPConnection(_NumericSocketMixin, HTTPConnection):
    pass


class _PinnedHTTPSConnection(_NumericSocketMixin, HTTPSConnection):
    pass


class _PinnedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PinnedAdapter(HTTPAdapter):
    def __init__(self, origin: _Origin, pinned_ip: str):
        self._origin = origin
        self._pinned_ip = pinned_ip
        super().__init__(max_retries=0, pool_connections=2, pool_maxsize=2)
        # PoolManager's default mapping is module-global; replace, never mutate it.
        self.poolmanager.pool_classes_by_scheme = {"http": _PinnedHTTPPool, "https": _PinnedHTTPSPool}

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        if _origin(request.url) != self._origin:
            raise NetworkPolicyError("此会话只能访问配置的同一来源。")
        if verify is not True and not (isinstance(verify, str) and verify):
            raise NetworkPolicyError("不能关闭 TLS 证书验证。")
        if proxies:
            raise NetworkPolicyError("固定连接会话不允许使用代理。")
        _host, pool_kwargs = self.build_connection_pool_key_attributes(request, verify, cert)
        if self._origin.scheme == "https":
            pool_kwargs.update(assert_hostname=self._origin.hostname, server_hostname=self._origin.hostname,
                               cert_reqs="CERT_REQUIRED")
        else:
            # HTTPConnection does not take TLS connection keyword arguments.
            pool_kwargs = {}
        request.headers["Host"] = self._origin.authority
        return self.poolmanager.connection_from_host(self._pinned_ip, port=self._origin.port,
                                                     scheme=self._origin.scheme, pool_kwargs=pool_kwargs)

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            # Session.send calls resolve_redirects(..., yield_requests=True)
            # even with allow_redirects=False, and that consumes response.content.
            # Reject here, before Session can drain an unbounded redirect body.
            response.close()
            raise NetworkPolicyError("目标返回重定向，已停止；请填写最终请求地址。")
        return response


class _PinnedSession(requests.Session):
    def __init__(self, origin: _Origin, ips: tuple[str, ...]):
        super().__init__()
        for adapter in self.adapters.values():
            adapter.close()
        self.adapters.clear()
        self.trust_env = False
        self.proxies = {}
        self.verify = True
        self._origin = origin
        self._pinned_ips = ips
        self._pinned_adapter = _PinnedAdapter(origin, ips[0])
        # get_adapter below enforces the origin; no permissive fallback adapter.
        super().mount(origin.url + "/", self._pinned_adapter)
        self._policy_ready = True

    def __setattr__(self, name, value):
        if getattr(self, "_policy_ready", False):
            if name == "trust_env" and value is not False:
                raise NetworkPolicyError("固定连接会话不能继承系统代理或认证配置。")
            if name == "verify" and value is not True and not (isinstance(value, str) and value):
                raise NetworkPolicyError("不能关闭 TLS 证书验证。")
        super().__setattr__(name, value)

    def mount(self, prefix, adapter):
        if getattr(self, "_policy_ready", False):
            raise NetworkPolicyError("不能替换固定连接会话的网络适配器。")
        super().mount(prefix, adapter)

    def get_adapter(self, url):
        if _origin(url) != self._origin:
            raise NetworkPolicyError("此会话只能访问配置的同一来源。")
        return self._pinned_adapter

    def send(self, request, **kwargs):
        if _origin(request.url) != self._origin:
            raise NetworkPolicyError("此会话只能访问配置的同一来源。")
        if kwargs.get("verify", self.verify) is not True and not isinstance(kwargs.get("verify", self.verify), str):
            raise NetworkPolicyError("不能关闭 TLS 证书验证。")
        if kwargs.get("proxies") or self.proxies:
            raise NetworkPolicyError("固定连接会话不允许使用代理。")
        # Requests defaults allow_redirects=True; always disable instead of
        # requiring every consumer to override its default.
        kwargs["allow_redirects"] = False
        kwargs["proxies"] = {}
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (10, 90)
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise NetworkPolicyError("目标返回重定向，已停止；请填写最终请求地址。")
        return response


def pinned_session(url: str, trusted_origins: tuple[str, ...] = ()) -> requests.Session:
    """Create an origin-limited Session, resolving the target hostname once.

    `trusted_origins` is server-side configuration, never user/model input. It
    permits known private demo/test origins; the old shared service IP remains
    denied even if explicitly listed. Public DNS answers must all be global.

    Callers may provide verify=<CA bundle> for private test CAs, but may never
    disable certificate verification. Do not mount another adapter on this
    session. Close it or use it as a context manager when the run ends.
    """
    origin = _origin(url, base=True)
    if not isinstance(trusted_origins, tuple) or not all(isinstance(value, str) for value in trusted_origins):
        raise NetworkPolicyError("可信来源必须由服务器配置为地址元组。")
    trusted = {_origin(value, base=True, only_origin=True) for value in trusted_origins}
    ips = _resolve_once(origin, origin in trusted)
    return _PinnedSession(origin, ips)
