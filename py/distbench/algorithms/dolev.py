"""Dolev's Reliable Communication (RC) algorithm.

Part A: Basic Dolev RC algorithm (Dolev, FOCS 1981).
Part B: Optimizations MD.1-MD.5 (Bonomi et al. 2019).

The algorithm guarantees reliable broadcast in a (2f+1)-connected network
even with up to f Byzantine processes, using authenticated point-to-point links.

Properties guaranteed:
  RC-Validity:    If a correct process broadcasts m, every correct process delivers m.
  RC-No-Duplication: No correct process delivers m more than once.
  RC-Integrity:   If a correct process delivers m with sender s, then s broadcast m.
"""

import asyncio
import logging
import random
import time
from collections import defaultdict
from typing import Any

from distbench.algorithm import Algorithm, Peer
from distbench.community import PeerId
from distbench.decorators import config_field, distbench, handler, message

logger = logging.getLogger(__name__)


@message
class DolevMessage:
    """A Dolev RC protocol message.

    Sent between nodes to propagate a broadcast message along with the
    sequence of intermediate nodes through which it passed.
    """

    sender: str      # original source node ID (the broadcaster)
    msg_id: int      # sequence number at the sender (unique per sender)
    content: str     # message payload
    path: list[str]  # nodes that relayed this message, NOT including current receiver


@distbench
class Dolev(Algorithm):
    """Dolev's Reliable Communication algorithm.

    Part A (base): delivers when f+1 node-disjoint paths from the source
    have been received.

    Part B (optimized): all five Bonomi et al. modifications enabled together:
      MD.1  Deliver immediately on direct receipt from source.
      MD.2  After delivery, relay with empty path only (discard stored paths).
      MD.3  Only relay paths to neighbors that have not yet delivered.
      MD.4  Ignore future paths that pass through a neighbor known to have delivered.
      MD.5  Stop all relaying after delivery + empty-path forwarded.
    """

    # --- Configuration fields ---
    f: int = config_field(default=1)                           # max Byzantine faults
    broadcaster: bool = config_field(default=False)            # this node initiates a broadcast
    messages: list[str] = config_field(default_factory=list)   # messages to broadcast
    optimized: bool = config_field(default=False)              # enable all MD.1-MD.5
    byzantine: bool = config_field(default=False)              # this node is Byzantine
    # byzantine_mode: "passive" | "impersonate" | "partial"
    #   passive:     drop all received messages silently (models a crash-like node)
    #   impersonate: send a fake message claiming to be another node (tests RC-Integrity)
    #   partial:     broadcast to only half of neighbors (tests no-totality)
    byzantine_mode: str = config_field(default="passive")
    byzantine_target: str = config_field(default="")          # node to impersonate
    delay_min: float = config_field(default=0.0)              # min send delay (seconds)
    delay_max: float = config_field(default=0.5)              # max send delay (seconds)

    def __init__(self, config: dict[str, Any], peers: dict[PeerId, Any]) -> None:
        super().__init__()
        self._msg_counter: int = 0

        # Per-message state, keyed by (sender_id, msg_id)
        self._delivered: set[tuple[str, int]] = set()
        self._paths: dict[tuple[str, int], set[tuple[str, ...]]] = defaultdict(set)
        self._content_cache: dict[tuple[str, int], str] = {}

        # Timing for latency measurement
        self._first_seen: dict[tuple[str, int], float] = {}
        self._delivery_time: dict[tuple[str, int], float] = {}
        self._broadcast_time: dict[tuple[str, int], float] = {}

        # Optimisation state (Part B)
        self._delivered_neighbors: dict[tuple[str, int], set[str]] = defaultdict(set)  # MD.3/4
        self._empty_path_sent: set[tuple[str, int]] = set()                            # MD.5

        # Metrics
        self._messages_sent: int = 0
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # Lifecycle hooks
    # -------------------------------------------------------------------------

    async def on_start(self) -> None:
        logger.info(
            f"Dolev RC starting | f={self.f} optimized={self.optimized} "
            f"byzantine={self.byzantine} broadcaster={self.broadcaster}"
        )

        if self.byzantine:
            await self._run_byzantine()
            return

        if self.broadcaster:
            for content in self.messages:
                await self._broadcast(content)
                await asyncio.sleep(0.05)

    async def on_exit(self) -> None:
        logger.info(
            f"Dolev RC exit | delivered={len(self._delivered)} "
            f"messages_sent={self._messages_sent}"
        )

    async def report(self) -> dict[str, str]:
        avg_latency_ms = 0.0
        latencies = []
        for key in self._delivered:
            if key in self._broadcast_time and key in self._delivery_time:
                latencies.append((self._delivery_time[key] - self._broadcast_time[key]) * 1000)
            elif key in self._first_seen and key in self._delivery_time:
                latencies.append((self._delivery_time[key] - self._first_seen[key]) * 1000)
        if latencies:
            avg_latency_ms = sum(latencies) / len(latencies)

        return {
            "f": str(self.f),
            "optimized": str(self.optimized),
            "byzantine": str(self.byzantine),
            "delivered_count": str(len(self._delivered)),
            "messages_sent": str(self._messages_sent),
            "avg_latency_ms": f"{avg_latency_ms:.2f}",
            "deliveries": str([f"{k[0]}:{k[1]}" for k in sorted(self._delivered)]),
        }

    # -------------------------------------------------------------------------
    # Byzantine node behaviour
    # -------------------------------------------------------------------------

    async def _run_byzantine(self) -> None:
        """Simulate a Byzantine node according to byzantine_mode."""
        logger.warning(f"[BYZANTINE] mode='{self.byzantine_mode}'")

        if self.byzantine_mode == "passive":
            # Drop everything silently (models a node that crashed / doesn't relay)
            return

        elif self.byzantine_mode == "impersonate" and self.byzantine_target:
            # Send one forged message claiming it comes from byzantine_target.
            # Correct nodes require f+1 disjoint paths → one Byzantine source is
            # never enough for delivery, so RC-Integrity is preserved.
            await asyncio.sleep(random.uniform(0.5, 1.5))
            fake = DolevMessage(
                sender=self.byzantine_target,
                msg_id=0,
                content="[BYZANTINE FAKE MESSAGE - should never be delivered]",
                path=[],
            )
            logger.warning(
                f"[BYZANTINE] Impersonating {self.byzantine_target}, "
                f"broadcasting fake message to {len(self.peers)} neighbors"
            )
            for peer_id, peer in self.peers.items():
                try:
                    await peer.dolev_message(fake)
                except Exception as e:
                    logger.error(f"[BYZANTINE] Send error to {peer_id}: {e}")

        elif self.byzantine_mode == "partial":
            # Broadcast to only half of neighbors, so not all correct nodes
            # can gather f+1 disjoint paths → demonstrates lack of totality.
            if not self.messages:
                return
            content = self.messages[0]
            partial = list(self.peers.items())[: max(1, len(self.peers) // 2)]
            logger.warning(
                f"[BYZANTINE] Partial broadcast to {len(partial)}/{len(self.peers)} peers"
            )
            for peer_id, peer in partial:
                try:
                    await peer.dolev_message(DolevMessage(
                        sender=str(self.id),
                        msg_id=0,
                        content=content,
                        path=[],
                    ))
                except Exception as e:
                    logger.error(f"[BYZANTINE] Send error to {peer_id}: {e}")

    # -------------------------------------------------------------------------
    # Broadcast
    # -------------------------------------------------------------------------

    async def _broadcast(self, content: str) -> None:
        """RC-Broadcast: source delivers to itself immediately and sends to neighbours."""
        msg_id = self._msg_counter
        self._msg_counter += 1
        key = (str(self.id), msg_id)
        now = time.time()

        async with self._lock:
            self._delivered.add(key)
            self._content_cache[key] = content
            self._delivery_time[key] = now
            self._broadcast_time[key] = now

        logger.info(
            f"RC-Deliver (self-broadcast) | sender={self.id} msg_id={msg_id} content='{content}'"
        )

        for peer_id, peer in self.peers.items():
            asyncio.create_task(self._send_delayed(peer_id, peer, DolevMessage(
                sender=str(self.id),
                msg_id=msg_id,
                content=content,
                path=[],
            )))

    # -------------------------------------------------------------------------
    # Sending helpers
    # -------------------------------------------------------------------------

    async def _send_delayed(self, peer_id: PeerId, peer: Peer, msg: DolevMessage) -> None:
        """Send with a random delay to simulate network conditions (requirement 4)."""
        delay = random.uniform(self.delay_min, self.delay_max)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            await peer.dolev_message(msg)
            self._messages_sent += 1
            logger.debug(
                f"→ {peer_id} | sender={msg.sender} id={msg.msg_id} path_len={len(msg.path)}"
            )
        except Exception as e:
            logger.error(f"Send error to {peer_id}: {e}")

    def _relay(
        self,
        key: tuple[str, int],
        msg: DolevMessage,
        full_path: tuple[str, ...],
        exclude: set[str],
    ) -> None:
        """Schedule relay of msg to all neighbours not in exclude."""
        sender, msg_id = key
        for peer_id, peer in self.peers.items():
            if str(peer_id) not in exclude:
                asyncio.create_task(self._send_delayed(peer_id, peer, DolevMessage(
                    sender=sender,
                    msg_id=msg_id,
                    content=msg.content,
                    path=list(full_path),
                )))

    def _relay_empty(
        self,
        key: tuple[str, int],
        content: str,
        exclude: set[str],
    ) -> None:
        """MD.2: schedule an empty-path delivery notification to all neighbours not in exclude."""
        if key in self._empty_path_sent:
            return  # MD.5: send empty path only once
        self._empty_path_sent.add(key)

        sender, msg_id = key
        for peer_id, peer in self.peers.items():
            if str(peer_id) not in exclude:
                asyncio.create_task(self._send_delayed(peer_id, peer, DolevMessage(
                    sender=sender,
                    msg_id=msg_id,
                    content=content,
                    path=[],
                )))

    # -------------------------------------------------------------------------
    # Message handler
    # -------------------------------------------------------------------------

    @handler
    async def dolev_message(self, src: PeerId, msg: DolevMessage) -> None:
        """Handle an incoming Dolev message from neighbour src."""
        if self.byzantine:
            return  # Byzantine node ignores all received messages

        full_path = tuple(msg.path + [str(src)])

        # --- Path validation (Byzantine robustness) ---
        # Non-empty paths must start with the claimed original sender.
        if msg.path and full_path[0] != msg.sender:
            logger.debug(f"Drop: bad origin in path from {src}: {full_path} ≠ {msg.sender}")
            return

        # No repeated nodes in path (no cycles / Byzantine crafted loops).
        if len(set(full_path)) != len(full_path):
            logger.debug(f"Drop: cyclic path from {src}: {full_path}")
            return

        # In the base algorithm, only the source broadcasts with an empty path.
        # Reject empty-path messages that claim to come from someone other than the source.
        if not self.optimized and not msg.path and str(src) != msg.sender:
            logger.debug(f"Drop: empty-path from non-source {src} in base mode")
            return

        key = (msg.sender, msg.msg_id)

        async with self._lock:
            # Empty-path message from a non-source neighbour = MD.2 delivery notification
            if self.optimized and not msg.path and str(src) != msg.sender:
                await self._handle_delivery_notification(src, msg, key)
                return

            await self._handle_relay_message(src, msg, key, full_path)

    async def _handle_delivery_notification(
        self,
        src: PeerId,
        msg: DolevMessage,
        key: tuple[str, int],
    ) -> None:
        """Process an MD.2 empty-path notification: src has already delivered key."""
        # MD.4: record that src has delivered; future paths through src are ignorable.
        self._delivered_neighbors[key].add(str(src))

        # If we have already delivered and not yet sent empty path, do it now (MD.5 guard).
        if key in self._delivered and key not in self._empty_path_sent:
            content = self._content_cache.get(key, msg.content)
            self._relay_empty(key, content, exclude=self._delivered_neighbors[key])

    async def _handle_relay_message(
        self,
        src: PeerId,
        msg: DolevMessage,
        key: tuple[str, int],
        full_path: tuple[str, ...],
    ) -> None:
        """Process a regular (possibly first-hop) Dolev message."""
        sender, msg_id = key
        now = time.time()

        # Cache content and first-seen timestamp.
        if key not in self._content_cache:
            self._content_cache[key] = msg.content
        if key not in self._first_seen:
            self._first_seen[key] = now

        # --- MD.4: ignore paths through a neighbour known to have delivered,
        #           but ONLY after we ourselves have already delivered.
        #           Before delivery we still need every path to build up
        #           the required f+1 disjoint paths; applying MD.4 too early
        #           can cause a race with the empty-path relay (MD.2) and
        #           inadvertently block paths we still need. ---
        if self.optimized and key in self._delivered:
            path_nodes = set(full_path)
            if path_nodes & self._delivered_neighbors[key]:
                logger.debug(f"MD.4 drop (post-delivery): path {full_path} through delivered neighbours")
                return

        # Deduplicate: only process each path once.
        if full_path in self._paths[key]:
            return
        self._paths[key].add(full_path)

        logger.debug(
            f"← {src} | sender={sender} id={msg_id} "
            f"path={full_path} total_paths={len(self._paths[key])}"
        )

        # --- Relay to neighbours not already on the path (Algorithm 1, line 17-18) ---
        # MD.5: stop all relaying once empty path has been forwarded.
        if not (self.optimized and key in self._empty_path_sent):
            excluded = set(msg.path) | {str(src)}
            if self.optimized:
                excluded |= self._delivered_neighbors[key]  # MD.3

            self._relay(key, msg, full_path, exclude=excluded)

        # --- Delivery check ---
        if key in self._delivered:
            # Already delivered; in the optimised version, trigger MD.2 relay if needed.
            if self.optimized and key not in self._empty_path_sent:
                content = self._content_cache[key]
                self._relay_empty(key, content, exclude=self._delivered_neighbors[key])
            return

        deliver = False
        reason = ""

        # MD.1: Deliver immediately if received directly from the source.
        if self.optimized and str(src) == sender and not msg.path:
            deliver = True
            reason = "MD.1 (direct from source)"

        # Base check: f+1 node-disjoint paths from source.
        if not deliver and self._has_disjoint_paths(key):
            deliver = True
            reason = f"f+1={self.f + 1} node-disjoint paths"

        if deliver:
            self._delivered.add(key)
            self._delivery_time[key] = now
            self._log_delivery(key, msg.content, reason=reason)

            if self.optimized:
                # MD.2 + MD.5: relay once with empty path.
                content = self._content_cache[key]
                exclude = {str(src)} | self._delivered_neighbors[key]
                self._relay_empty(key, content, exclude=exclude)

    # -------------------------------------------------------------------------
    # Disjoint-paths check
    # -------------------------------------------------------------------------

    def _has_disjoint_paths(self, key: tuple[str, int]) -> bool:
        """Return True if f+1 node-disjoint paths from source to self exist.

        Uses a greedy algorithm:
          1. Sort paths by number of intermediate nodes (ascending).
          2. Greedily select paths whose intermediate nodes don't overlap with
             previously selected paths.

        Byzantine robustness: a Byzantine node b can contribute forged paths,
        but every forged path that passes through b (or claims to) will share
        b as an intermediate node. At most f Byzantine nodes can each
        contribute one independent path. Since we require f+1 disjoint paths,
        at least one must come from honest relaying.
        """
        paths = list(self._paths[key])
        if not paths:
            return False

        paths.sort(key=len)  # prefer shorter (more direct) paths first

        selected = 0
        used_nodes: set[str] = set()

        for path in paths:
            # Intermediate nodes: everything after the source (index 0).
            # The source is shared by all paths (it's the common endpoint).
            intermediates = set(path[1:])

            if not intermediates & used_nodes:
                selected += 1
                used_nodes |= intermediates
                if selected >= self.f + 1:
                    return True

        return False

    # -------------------------------------------------------------------------
    # Logging helper
    # -------------------------------------------------------------------------

    def _log_delivery(
        self, key: tuple[str, int], content: str, reason: str = ""
    ) -> None:
        sender, msg_id = key
        latency_ms = 0.0
        if key in self._first_seen and key in self._delivery_time:
            latency_ms = (self._delivery_time[key] - self._first_seen[key]) * 1000

        logger.info(
            f"RC-Deliver | sender={sender} msg_id={msg_id} content='{content}' "
            f"reason={reason} paths_stored={len(self._paths[key])} "
            f"latency={latency_ms:.1f}ms"
        )
