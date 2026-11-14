from collections import deque
from itertools import combinations


class Dolev:
    def __init__(self, pid, neighbors, f, send):
        self.pid = pid
        self.neighbors = neighbors

        self.f = f
        self.send = send            # send(to, m, path) -> the "al" link
        # Init (lines 5-7)
        self.delivered = False
        self.paths = []

    # Broadcast (lines 9-13). m = (source, content)
    def broadcast(self, content):
        m = (self.pid, content)
        for pj in self.neighbors:
            self.send(self.pid, pj, m, [])
        self.delivered = True
        self.deliver(m)

    # al.Deliver (lines 15-18). pj is the authenticated sender.
    def on_receive(self, pj, m, path):
        self.paths.append(path + [pj])
        for pk in self.neighbors:
            if pk not in path and pk != pj:
                self.send(self.pid, pk, m, path + [pj])
        # Delivery condition (lines 20-22)
        if not self.delivered and self.has_disjoint_paths(m[0]):
            self.delivered = True
            self.deliver(m)

    def has_disjoint_paths(self, source):
        # Only paths that start at the source count; ignore the source label itself.
        interiors = [set(p[1:]) for p in self.paths if p[0] == source]
        for combo in combinations(interiors, self.f + 1):
            if all(a.isdisjoint(b) for a, b in combinations(combo, 2)):
                return True
        return False

    def deliver(self, m):
        print(f"p{self.pid} delivered {m}")


# ---- demo: the graph from Figure 1 (N=10, connectivity 3, f=1) ----
if __name__ == "__main__":
    edges = [(0, 1), (0, 9), (0, 7), (1, 5), (1, 4), (9, 8), (9, 2), (4, 5),
             (4, 8), (5, 6), (8, 6), (7, 2), (7, 3), (2, 3), (3, 6)]
    neighbors = {i: [] for i in range(10)}
    for a, b in edges:
        neighbors[a].append(b)
        neighbors[b].append(a)

    queue = deque()
    def send(frm, to, m, path):
        queue.append((frm, to, m, path))

    nodes = {i: Dolev(i, neighbors[i], f=1, send=send) for i in range(10)}

    nodes[0].broadcast("hello")
    while queue:
        frm, to, m, path = queue.popleft()
        nodes[to].on_receive(frm, m, path)