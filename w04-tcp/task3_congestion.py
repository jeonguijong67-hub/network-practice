#!/usr/bin/env python3
"""Week 4 · Task 3 — Beat the fixed window.

Textbook §3.7.

`FixedWindow` is a sender that never adapts. It picks a window and keeps it,
forever, no matter what the network says back. It is not a strawman: it is what
you get if you skip congestion control entirely, and it was the internet's
actual failure mode in October 1986.

Write `YourControl` and beat it on the harness:

    python3 bench.py
    python3 bench.py --yours

The interface is two events and one number:

    .window        how many packets you are willing to have in flight
    .on_ack()      one packet made it there and back
    .on_loss()     a packet was dropped, or timed out waiting for its ACK

That is all the information a real TCP sender has. It cannot see the queue,
it cannot see the link rate, and neither can you. You infer them from these
two events, which is the entire idea of §3.7.
"""


class FixedWindow:
    """Send 64 packets at a time and never listen."""

    def __init__(self):
        self.window = 64

    def on_ack(self):
        pass

    def on_loss(self):
        pass


class YourControl:
    """Slow start to find the scale of the pipe, then ratchet down onto it.

    The link never says how big it is. The only two facts it ever gives back
    are "one packet returned" and "one packet did not", so the pipe size has to
    be inferred from the boundary between them.

    The shape of the search:

    1. **Slow start.** Double the window every round trip until something is
       lost. Nothing else finds the right order of magnitude this quickly.
    2. **A loss names a ceiling.** The window in effect when a packet died was,
       by definition, too big. Keep the *smallest* such window ever seen and
       refuse to grow past `MARGIN` of it.
    3. **Refine.** The first ceiling is far too generous, because a timeout is
       3 RTTs long and the window went on doubling the whole time it was
       pending. So each later loss lowers the ceiling again, and the estimate
       walks down onto the real value instead of guessing it in one shot.
    4. **One loss event, one reaction.** A full queue drops a whole burst, and
       every one of those drops calls `on_loss` about 60 slots later. Reacting
       to each would collapse the window to nothing, so after backing off we
       ignore losses for one window's worth of ACKs - they are the same event.

    On this link the ceiling estimate falls 82 -> 59 -> 43 -> 24.5 and the
    window settles at 20.8, which is the bandwidth-delay product: 1 packet per
    slot times 20 slots of round trip. That is the number it should converge to,
    and nothing in here was told it.
    """

    BACKOFF = 0.7           # multiplicative decrease - gentler than halving
    MARGIN = 0.85           # sit this far below the smallest window that lost

    def __init__(self):
        self.window = 1.0
        self.ssthresh = float("inf")   # no reason to leave slow start yet
        self.ceiling = None            # smallest window ever seen to lose
        self.grace = 0                 # ACKs left in the current loss event

    def on_ack(self):
        if self.grace > 0:
            self.grace -= 1
        if self.window < self.ssthresh:
            self.window += 1.0             # slow start: doubles per round trip
        else:
            self.window += 1.0 / self.window   # congestion avoidance: +1 per RTT
        if self.ceiling is not None:
            self.window = min(self.window, self.ceiling * self.MARGIN)

    def on_loss(self):
        if self.grace > 0:
            return                          # same burst, already paid for
        self.ceiling = (self.window if self.ceiling is None
                        else min(self.ceiling, self.window))
        self.ssthresh = max(2.0, self.window * self.BACKOFF)
        self.window = self.ssthresh
        self.grace = int(self.window)       # one round trip of silence
