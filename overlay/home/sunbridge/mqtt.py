"""Minimal MQTT 3.1.1 publisher (QoS 0) for Python 2.6. No dependencies.

Only what the bridge needs: connect with optional credentials and a last
will, publish, ping to prove the connection is alive, disconnect. Every call
raises socket.error or MQTTError on failure; the caller reconnects.
"""
import socket
import struct

CONNECT, CONNACK, PUBLISH, PINGREQ, PINGRESP, DISCONNECT = 1, 2, 3, 12, 13, 14


class MQTTError(Exception):
    pass


def _str(s):
    if isinstance(s, unicode):
        s = s.encode('utf-8')
    return struct.pack('!H', len(s)) + s


def _packet(kind, flags, body):
    n, length = len(body), ''
    while True:
        digit, n = n % 128, n // 128
        length += chr(digit | (0x80 if n else 0))
        if not n:
            return chr(kind << 4 | flags) + length + body


class Client(object):
    def __init__(self, host, port=1883, client_id='sunbridge', user=None,
                 password=None, keepalive=600, timeout=10):
        self.host, self.port, self.client_id = host, port, client_id
        self.user, self.password = user, password
        self.keepalive, self.timeout = keepalive, timeout
        self.sock = None

    def connect(self, will_topic=None, will_payload='', will_retain=True):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        flags, payload = 0x02, _str(self.client_id)  # clean session
        if will_topic:
            flags |= 0x04 | (0x20 if will_retain else 0)
            payload += _str(will_topic) + _str(will_payload)
        if self.user:
            flags |= 0x80
            payload += _str(self.user)
            if self.password:
                flags |= 0x40
                payload += _str(self.password)
        body = _str('MQTT') + chr(4) + chr(flags) + struct.pack('!H', self.keepalive)
        self.sock.sendall(_packet(CONNECT, 0, body + payload))
        kind, body = self._read()
        if kind != CONNACK or len(body) != 2:
            raise MQTTError('unexpected reply to CONNECT')
        if ord(body[1]) != 0:
            raise MQTTError('connection refused, code %d' % ord(body[1]))

    def publish(self, topic, payload, retain=False):
        if isinstance(payload, unicode):
            payload = payload.encode('utf-8')
        self.sock.sendall(_packet(PUBLISH, 1 if retain else 0, _str(topic) + payload))

    def ping(self):
        """Round trip to the broker; raises if the connection is dead."""
        self.sock.sendall(_packet(PINGREQ, 0, ''))
        kind, _ = self._read()
        if kind != PINGRESP:
            raise MQTTError('unexpected reply to PINGREQ')

    def disconnect(self):
        try:
            self.sock.sendall(_packet(DISCONNECT, 0, ''))
        except (socket.error, AttributeError):
            pass
        self.close()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except socket.error:
                pass
        self.sock = None

    def _read(self):
        head = self._recv(1)
        n, shift = 0, 0
        while True:
            digit = ord(self._recv(1))
            n |= (digit & 0x7f) << shift
            if not digit & 0x80:
                break
            shift += 7
            if shift > 21:
                raise MQTTError('bad remaining length')
        return ord(head) >> 4, self._recv(n)

    def _recv(self, n):
        data = ''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise MQTTError('connection closed by broker')
            data += chunk
        return data
