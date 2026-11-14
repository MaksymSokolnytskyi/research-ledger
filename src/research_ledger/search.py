r"""Okapi BM25 over notes: exact-term retrieval, no embeddings, no dependencies.

Technical corpora are queried by identifiers and numbers ("why did ladder4 fail on
CUDA 12") more than by paraphrase, and BM25 hits those exactly. It is also
deterministic and explainable, which a context pack shown to an agent should be.
Vectors can be added later as a second ranker; BM25 stays as the lexical half of a
hybrid.

.. math::

    \mathrm{score}(D, Q) = \sum_{q \in Q} \mathrm{idf}(q)
        \frac{f(q, D)\,(k_1 + 1)}{f(q, D) + k_1 (1 - b + b\,|D|/\overline{|D|})},
    \qquad \mathrm{idf}(q) = \ln\!\left(1 + \frac{N - n(q) + 0.5}{n(q) + 0.5}\right)

(Robertson & Zaragoza 2009, with the non-negative idf variant.)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_TOKEN_RE = re.compile(r"[^\W_]+(?:[._\-][^\W_]+)*", re.UNICODE)
K1 = 1.5
B = 0.75

# Function words of the two supported languages; they carry no topic.
STOPWORDS = frozenset(
    """a an and are as at be by for from has have how i in is it its of on or that the
    this to was were what when where which who why will with you your we our can do
    does not no yes into than then there these those also but if so just about
    і й та в у на з із до від що як це це не але або для по за при про чи ж же би
    бо його її їх ми ви вони він вона воно я ти так ще вже тут там коли де який яка
    яке які щоб""".split()
)


def tokenize(text: str) -> list[str]:
    """Lower-cased words; identifiers like ``gpu_search.py`` stay whole *and* split."""
    out: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group()
        parts = re.split(r"[._\-]", token)
        for t in {token, *parts}:
            if len(t) > 1 and t not in STOPWORDS:
                out.append(t)
    return out


class BM25:
    def __init__(self, documents: Sequence[str], k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: str, index: int) -> float:
        doc, length = self.docs[index], self.lengths[index]
        if not length:
            return 0.0
        norm = self.k1 * (1 - self.b + self.b * length / self.avg_length)
        total = 0.0
        for term in set(tokenize(query)):
            f = doc.get(term, 0)
            if f:
                total += self.idf[term] * f * (self.k1 + 1) / (f + norm)
        return total

    def rank(self, query: str) -> list[tuple[int, float]]:
        scored = [(i, self.score(query, i)) for i in range(len(self.docs))]
        return sorted((s for s in scored if s[1] > 0), key=lambda s: -s[1])
