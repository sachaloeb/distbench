"""Dolev's reliable communication algorithm (basic version, Algorithm 1).

A node delivers a message once it has received it along f+1 node-disjoint
paths from the source. Every received path is relayed to all neighbours
that are not already on it.
"""

import asyncio
import logging
import time
from itertools import combinations
from typing import Any

from distbench.algorithm import Algorithm
from distbench.community import PeerId
from distbench.decorators import config_field, distbench, handler, message

logger = logging.getLogger(__name__)


@message
class DolevMessage:
    source: str       # node that broadcast the content
    content: str
    path: list[str]   # nodes the message passed through (sender not included yet)


@distbench
class Dolev(Algorithm):
    f: int = config_field(default=1)
    is_sender: bool = config_field(default=False)
    content: str = config_field(default="hello")
    run_time: float = config_field(default=5.0)  # seconds before terminating

    def __init__(self, config: dict[str, object], peers: dict[PeerId, Any]) -> None:
        super().__init__()
        # Init (lines 5-7), kept per message so several messages can coexist
        self.delivered: set[tuple[str, str]] = set()
        self.paths: dict[tuple[str, str], list[list[str]]] = {}
        self.delivery_times: dict[str, float] = {}
        self.messages_sent = 0
        self.start_time = 0.0

    async def on_start(self) -> None:
        self.start_time = time.time()
        if self.is_sender:
            await self.broadcast(self.content)
        await asyncio.sleep(self.run_time)
        await self.terminate()

    # Broadcast (lines 9-13)
    async def broadcast(self, content: str) -> None:
        me = str(self.id)
        logger.info(f"{me} broadcasting '{content}'")
        for pj, peer in self.peers.items():
            await self.send(pj, peer, DolevMessage(source=me, content=content, path=[]))
        self.deliver_msg(me, content)

    # al.Deliver (lines 15-18), then the delivery check (lines 20-22)
    @handler
    async def dolev(self, src: PeerId, msg: DolevMessage) -> None:
        pj = str(src)
        new_path = msg.path + [pj]
        key = (msg.source, msg.content)

        self.paths.setdefault(key, []).append(new_path)

        for pk, peer in self.peers.items():
            if str(pk) not in msg.path and str(pk) != pj:
                await self.send(
                    pk, peer,
                    DolevMessage(source=msg.source, content=msg.content, path=new_path),
                )

        if key not in self.delivered and self.has_disjoint_paths(key):
            self.deliver_msg(msg.source, msg.content)

    def has_disjoint_paths(self, key: tuple[str, str]) -> bool:
        source = key[0]
        # Only paths starting at the source count; leave out the source label.
        interiors = [set(p[1:]) for p in self.paths[key] if p and p[0] == source]
        for combo in combinations(interiors, self.f + 1):
            if all(a.isdisjoint(b) for a, b in combinations(combo, 2)):
                return True
        return False

    def deliver_msg(self, source: str, content: str) -> None:
        self.delivered.add((source, content))
        elapsed = time.time() - self.start_time
        self.delivery_times[f"{source}:{content}"] = elapsed
        logger.info(f"{self.id} DELIVERED '{content}' from {source} after {elapsed:.3f}s")

    async def send(self, pid: PeerId, peer: Any, msg: DolevMessage) -> None:
        try:
            await peer.dolev(msg)
            self.messages_sent += 1
        except Exception as e:
            logger.warning(f"Failed to send to {pid}: {e}")

    async def report(self) -> dict[str, str]:
        return {
            "delivered": str(sorted(self.delivered)),
            "delivery_times": str(self.delivery_times),
            "messages_sent": str(self.messages_sent),
        }