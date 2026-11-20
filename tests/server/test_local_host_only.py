"""The app refuses to serve beyond this PC."""

import pytest

from researchchat.config import check_local_host

# ---- Local host only · unit
# Baseline: Given start-up · When the server host is checked


def test_loopback_hosts_are_accepted():
    # Changed: 127.0.0.1, localhost and ::1
    # Then: the app starts
    # Demonstrates: this PC can always open the app
    for host in ("127.0.0.1", "localhost", "::1"):
        check_local_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0"])
def test_all_interfaces_host_is_refused(host):
    # Changed: 0.0.0.0
    # Then: it refuses with today's message
    # Demonstrates: code can't be run from the network
    with pytest.raises(RuntimeError, match="only serves localhost"):
        check_local_host(host)


def test_lan_address_is_refused():
    # Changed: 192.168.1.5
    # Then: it refuses with today's message
    # Demonstrates: other devices on the network are refused
    with pytest.raises(RuntimeError, match="only serves localhost"):
        check_local_host("192.168.1.5")


def test_empty_host_is_refused():
    # Changed: an empty host
    # Then: it refuses with today's message
    # Demonstrates: a missing host isn't taken as local
    with pytest.raises(RuntimeError, match="only serves localhost"):
        check_local_host("")
