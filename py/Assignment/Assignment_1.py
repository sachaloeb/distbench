"""
Dolev's reliable communication algorithm (Dolev, 1982), as a small simulation.

Guarantee: in a network that is at least (2f+1)-vertex-connected, every
correct node delivers exactly the messages that correct sources broadcast,
even if up to f nodes are Byzantine (arbitrarily malicious).

Core rule: a node delivers a message once it has received it along f+1
paths that are node-disjoint (not counting the source and the node itself),
or directly from the source.
"""
from collections import deque, defaultdict

import random

class Network:
    """Delivers messages in FIFO order over authenticated point-to-point links."""

    def __init__(self):
        self.nodes = {}
        self.queue = deque()
        self.messages_sent = 0

    def add(self, node):
        self.nodes[node.id] = node
        node.network = self

    def send(self, sender, receiver, message):
        assert receiver in self.nodes[sender].neighbors, "no such link"
        self.queue.append((sender, receiver, message))
        self.messages_sent += 1

    def run(self):
        while self.queue:
            sender, receiver, message = self.queue.popleft()
            # Links are authenticated: the receiver learns the real sender.
            self.nodes[receiver].on_receive(sender, message)


class DolevNode:
    def __init__(self, node_id, neighbors, f):
        self.id = node_id
        self.neighbors = set(neighbors)
        self.f = f
        self.network = None
        self.paths = defaultdict(list)  # (source, content) -> list of interior-node sets
        self.seen = set()               # (source, content, path) already handled
        self.delivered_keys = set()
        self.delivered = []             # delivered (source, content) in order

    # ---- public API -------------------------------------------------------
    def broadcast(self, content):
        self.deliver(self.id, content)
        for nb in self.neighbors:
            self.network.send(self.id, nb, (self.id, content, ()))

    def deliver(self, source, content):
        self.delivered_keys.add((source, content))
        self.delivered.append((source, content))

    # ---- message handling -------------------------------------------------
    def on_receive(self, sender, message):
        source, content, path = message
        full_path = path + (sender,)

        # Discard malformed paths, loops back through us, and duplicates.
        if full_path[0] != source or self.id in full_path:
            return
        if (source, content, full_path) in self.seen:
            return
        self.seen.add((source, content, full_path))

        key = (source, content)
        self.paths[key].append(frozenset(full_path[1:]))  # interior nodes only

        if key not in self.delivered_keys and self._has_disjoint_paths(key):
            self.deliver(source, content)

        # Relay to every neighbor not already on the path.
        for nb in self.neighbors - set(full_path):
            self.network.send(self.id, nb, (source, content, full_path))

    def _has_disjoint_paths(self, key):
        paths = self.paths[key]
        if any(len(p) == 0 for p in paths):  # received straight from the source
            return True
        paths = sorted(paths, key=len)        # short paths first: faster search
        return self._search(paths, self.f + 1, frozenset(), 0)

    def _search(self, paths, needed, used, start):
        """Backtracking: can we pick `needed` pairwise-disjoint paths?"""
        if needed == 0:
            return True
        for i in range(start, len(paths)):
            if not (paths[i] & used):
                if self._search(paths, needed - 1, used | paths[i], i + 1):
                    return True
        return False


class ByzantineNode(DolevNode):
    """Malicious node: drops real messages and relays a forged version instead."""

    def on_receive(self, sender, message):
        source, content, path = message
        full_path = path + (sender,)
        if (source, content, full_path) in self.seen:
            return
        self.seen.add((source, content, full_path))
        for nb in self.neighbors - set(full_path):
            self.network.send(self.id, nb, (source, "FORGED", full_path))


# ---- demo -----------------------------------------------------------------
if __name__ == "__main__":
    f = 1
    n = 8
    byzantine = {2}

    # Circulant graph: each node linked to i±1 and i±2 -> 4-connected (>= 2f+1).
    def neighbors_of(i):
        return {(i + d) % n for d in (-2, -1, 1, 2)}

    net = Network()
    for i in range(n):
        cls = ByzantineNode if i in byzantine else DolevNode
        net.add(cls(i, neighbors_of(i), f))

    net.nodes[0].broadcast("hello")
    net.run()

    print(f"Messages sent: {net.messages_sent}\n")
    for i, node in net.nodes.items():
        role = "BYZANTINE" if i in byzantine else "correct"
        print(f"Node {i} ({role:9}): delivered {node.delivered}")