#!/usr/bin/env python3
"""Week 4 · Task 1 — Build reliable delivery on top of an unreliable channel.

Textbook §3.4 (reliable data transfer) and §3.5 (TCP's sequence numbers).

`UnreliableChannel` below loses packets, reorders them, duplicates them, and
delays them. It is the network as §3.4 models it. Your job is to move a file
across it and have the bytes arrive intact and in order.

That is the whole of TCP's reliability story with the congestion control taken
out, and it is worth building once by hand before you ever trust a socket again.

    python3 task1_rdt.py --verify
"""
import argparse, hashlib, random, struct

PAYLOAD = 8            # bytes per packet - small, so you see the sequencing

HEADER = struct.Struct("!I")   # 4-byte sequence number, big-endian, on every packet


def pack_seq(seq):
    return HEADER.pack(seq)


def unpack_seq(packet):
    return HEADER.unpack_from(packet, 0)[0]


class UnreliableChannel:
    """Loses 10%, duplicates 3%, reorders, and delays. Deterministic by seed.

    You may not make it nicer. You may not read its internals. It is the only
    way your sender can reach your receiver.
    """

    def __init__(self, seed=246, loss=0.10, dup=0.03, reorder=0.10):
        self.rng = random.Random(seed)
        self.loss, self.dup, self.reorder = loss, dup, reorder
        self.wire = []          # packets in flight, in no particular order
        self.stats = {"sent": 0, "lost": 0, "duplicated": 0, "delivered": 0}

    def send(self, packet):
        """Hand a packet to the network. It may never come out."""
        self.stats["sent"] += 1
        if self.rng.random() < self.loss:
            self.stats["lost"] += 1
            return
        copies = 2 if self.rng.random() < self.dup else 1
        self.stats["duplicated"] += copies - 1
        for _ in range(copies):
            if self.rng.random() < self.reorder and self.wire:
                self.wire.insert(self.rng.randrange(len(self.wire)), packet)
            else:
                self.wire.append(packet)

    def receive(self):
        """Take the next packet out, or None if the network has nothing."""
        if not self.wire:
            return None
        self.stats["delivered"] += 1
        return self.wire.pop(0)


class Sender:
    """A sliding-window sender with cumulative ACKs.

    Stop-and-wait would also pass, but it pays one full round trip per 8 bytes.
    The window is what makes the channel's reordering visible at all: with one
    packet outstanding nothing can arrive out of order, so there is nothing to
    reorder. §3.4.3.

    Three things keep it honest:

      - an ACK is cumulative. `ack` means "everything below this arrived", so a
        stale or duplicated ACK can only ever be ignored, never believed
      - every unacknowledged sequence number carries its own timer, so a loss
        costs one timeout and not the whole window
      - three duplicate ACKs for the same number mean a gap the receiver keeps
        complaining about, so resend that one packet without waiting
    """

    WINDOW = 8              # packets in flight; the pipe here is short
    TIMEOUT = 40            # steps before an unacknowledged packet goes again
    DUP_ACKS = 3            # duplicate ACKs that trigger a fast retransmit

    def __init__(self, data_channel, ack_channel, data):
        self.data_channel = data_channel
        self.ack_channel = ack_channel
        # R1: split into PAYLOAD-sized pieces; the index is the sequence number
        self.chunks = [data[i:i + PAYLOAD] for i in range(0, len(data), PAYLOAD)]
        self.base = 0           # lowest sequence number not yet acknowledged
        self.sent_at = {}       # seq -> clock when it last went out
        self.dup_acks = 0       # consecutive ACKs repeating the current base
        self.clock = 0

    def step(self):
        """One unit of work. False once every chunk has been acknowledged."""
        self.clock += 1
        self._collect_acks()
        if self.base >= len(self.chunks):
            return False
        self._send_window()
        return True

    def _collect_acks(self):
        while True:
            packet = self.ack_channel.receive()
            if packet is None:
                return
            ack = unpack_seq(packet)
            if ack > self.base:
                for seq in range(self.base, ack):
                    self.sent_at.pop(seq, None)
                self.base = ack
                self.dup_acks = 0
            elif ack == self.base:
                # The receiver is still missing `base`. It says so once per
                # packet that arrives past the gap - and the channel duplicates
                # 3% of everything, so one repeat proves nothing. Three do.
                self.dup_acks += 1
                if self.dup_acks >= self.DUP_ACKS and self.base < len(self.chunks):
                    self._transmit(self.base)
                    self.dup_acks = 0
            # ack < base is an ACK we already acted on. R4 is about data, not
            # about believing every number that comes back.

    def _send_window(self):
        end = min(self.base + self.WINDOW, len(self.chunks))
        for seq in range(self.base, end):
            last = self.sent_at.get(seq)
            if last is None or self.clock - last >= self.TIMEOUT:
                self._transmit(seq)      # R4: unacknowledged means resend

    def _transmit(self, seq):
        self.data_channel.send(pack_seq(seq) + self.chunks[seq])
        self.sent_at[seq] = self.clock


class Receiver:
    """Buffers by sequence number, delivers in order, and re-ACKs duplicates.

    R2 and R3 are both handled here. Out-of-order packets wait in `pending`
    until the gap ahead of them is filled, and a sequence number that is
    already delivered - or already waiting - is dropped rather than appended.
    A duplicate still gets an ACK, because the reason it was sent again is
    usually that the first ACK was the thing that got lost.
    """

    def __init__(self, data_channel, ack_channel):
        self.data_channel = data_channel
        self.ack_channel = ack_channel
        self.pending = {}       # seq -> payload, arrived early
        self.expected = 0       # next sequence number needed, in order
        self.stream = bytearray()

    def step(self):
        packet = self.data_channel.receive()
        if packet is None:
            return
        seq, payload = unpack_seq(packet), packet[HEADER.size:]

        if seq >= self.expected and seq not in self.pending:
            self.pending[seq] = payload          # R3: idempotent, not append
        while self.expected in self.pending:     # R2: in order, whatever order
            self.stream += self.pending.pop(self.expected)
            self.expected += 1

        # Cumulative ACK: "I have everything below this."
        self.ack_channel.send(pack_seq(self.expected))

    def data(self):
        return bytes(self.stream)


# ------------------------------------------------------------------- harness
def verify(seed=246, size=2000, max_steps=200_000):
    original = bytes(random.Random(seed).getrandbits(8) for _ in range(size))
    up, down = UnreliableChannel(seed), UnreliableChannel(seed + 1)

    # Data goes out over `up`, ACKs come back over `down`. Both are unreliable.
    sender = Sender(up, down, original)
    receiver = Receiver(up, down)

    for _ in range(max_steps):
        alive = sender.step()
        receiver.step()
        if not alive and len(receiver.data() or b"") >= size:
            break

    got = receiver.data() or b""
    ok = hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f"  bytes    sent {size}   received {len(got)}")
    print(f"  channel  {up.stats}")
    print(f"  result   {'IDENTICAL' if ok else 'CORRUPTED OR INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seed", type=int, default=246)
    a = p.parse_args()
    raise SystemExit(verify(a.seed) if a.verify else p.print_help())
