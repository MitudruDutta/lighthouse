"""Plain implementations of the graph algorithms, written here to compare the library with:
sets that edges join, PageRank, betweenness by Brandes' algorithm, and the fewest steps."""

from collections import deque


def linked_sets(nodes, edges) -> set[frozenset]:
    parent = {node: node for node in nodes}

    def root(node):
        while parent[node] != node:
            node = parent[node]
        return node

    for a, b in edges:
        parent[root(a)] = root(b)
    sets = {}
    for node in nodes:
        sets.setdefault(root(node), set()).add(node)
    return {frozenset(members) for members in sets.values()}


def page_rank(nodes, edges, damping=0.85) -> dict:
    out = {node: {b for a, b in edges if a == node} for node in nodes}
    rank = dict.fromkeys(nodes, 1 / len(nodes))
    for _ in range(200):
        nothing = sum(rank[node] for node in nodes if not out[node])  # shared among all
        step = dict.fromkeys(nodes, (1 - damping + damping * nothing) / len(nodes))
        for node in nodes:
            for target in out[node]:
                step[target] += damping * rank[node] / len(out[node])
        rank = step
    return rank


def paths_through(nodes, edges) -> dict:
    """Betweenness by Brandes' algorithm, along the direction of the edges."""
    out = {node: sorted({b for a, b in edges if a == node and b != node}) for node in nodes}
    score = dict.fromkeys(nodes, 0.0)
    for source in nodes:
        order, before = [], {node: [] for node in nodes}
        ways, far = dict.fromkeys(nodes, 0), {source: 0}
        ways[source], todo = 1, deque([source])
        while todo:
            node = todo.popleft()
            order.append(node)
            for target in out[node]:
                if target not in far:
                    far[target] = far[node] + 1
                    todo.append(target)
                if far[target] == far[node] + 1:
                    ways[target] += ways[node]
                    before[target].append(node)
        part = dict.fromkeys(nodes, 0.0)
        for node in reversed(order):
            for earlier in before[node]:
                part[earlier] += ways[earlier] / ways[node] * (1 + part[node])
            if node != source:
                score[node] += part[node]
    return score


def fewest_steps(edges, start, end):
    near = {}
    for a, b in edges:
        near.setdefault(a, set()).add(b)
        near.setdefault(b, set()).add(a)
    far, todo = {start: 0}, deque([start])
    while todo:
        node = todo.popleft()
        if node == end:
            return far[node]
        for other in near.get(node, ()):
            if other not in far:
                far[other] = far[node] + 1
                todo.append(other)
    return None
