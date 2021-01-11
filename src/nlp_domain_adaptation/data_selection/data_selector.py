from collections import Counter
from typing import List, Optional, Sequence, Union

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
from transformers import PreTrainedTokenizerFast
from sklearn.base import BaseEstimator, TransformerMixin

from nlp_domain_adaptation.type import Corpus, Token
from nlp_domain_adaptation.data_selection.metrics import (
    SIMILARITY_FEATURES,
    DIVERSITY_FEATURES,
    similarity_func_factory,
    diversity_func_factory,
)


class DataSelector(BaseEstimator, TransformerMixin):
    def __init__(
        self,
        select: Union[int, float],
        tokenizer: PreTrainedTokenizerFast,
        similarity_metrics: Optional[Sequence[str]] = None,
        diversity_metrics: Optional[Sequence[str]] = None,
    ):
        if isinstance(select, int) and select <= 0:
            raise ValueError(f"Int value for `select` must be strictly positive.")
        if isinstance(select, float) and not 0 <= select <= 1:
            raise ValueError(
                f"Float value for `select` must be between 0 and 1 (inclusive)."
            )
        if similarity_metrics is not None:
            _invalid_sim_metrics = set(similarity_metrics) - SIMILARITY_FEATURES
            if _invalid_sim_metrics:
                raise ValueError(
                    f"Invalid similarity metric(s) {_invalid_sim_metrics} found"
                )
        if diversity_metrics is not None:
            _invalid_div_metrics = set(diversity_metrics) - DIVERSITY_FEATURES
            if _invalid_div_metrics:
                raise ValueError(
                    f"Invalid diversity metric(s) {_invalid_div_metrics} found"
                )
        if similarity_metrics is None and diversity_metrics is None:
            raise ValueError(
                f"No metrics provided. Please provide at least one similarity or diversity metric."
            )

        self.select = select
        self.tokenizer = tokenizer
        self.similarity_metrics = similarity_metrics
        self.diversity_metrics = diversity_metrics

    def to_term_dist(self, text: str) -> np.ndarray:
        if not len(text.strip()):
            raise ValueError(f"A non-empty string must be provided.")

        tokenized: List[Token] = self.tokenizer.tokenize(text)
        term_counts = Counter(tokenized)

        vocab = self.tokenizer.vocab

        # Create a term distribution
        term_dist: np.ndarray = np.zeros(len(vocab))
        for term, count in term_counts.items():
            term_dist[vocab[term]] = count
        term_dist /= term_dist.sum()

        return term_dist

    def fit(self, ft_corpus: Corpus):
        """Compute corpus-level term distribution of `ft_corpus`.

        A new fitted attribute `.ft_term_dist_` of shape (V,) is created,
        where V is the size of the tokenizer vocabulary.

        Note:
            The `ft_corpus` is treated as a single "document", which will be compared
            against other documents in the in-domain corpus in `.transform`

        Args:
            ft_corpus: Fine-tuning corpus
        """
        self.ft_term_dist_ = self.to_term_dist(" ".join(ft_corpus))
        return self

    def transform(self, docs: Corpus) -> Corpus:
        scores = self.compute_metrics(docs)
        composite_scores = scores["composite"].sort_values(ascending=False)

        n_select = (
            self.select
            if isinstance(self.select, int)
            else int(self.select * len(docs))
        )
        selection_index = composite_scores.index[:n_select]
        subset_corpus = pd.Series(docs)[selection_index]

        return subset_corpus.tolist()

    def compute_metrics(self, docs: Corpus) -> pd.DataFrame:
        scores = pd.concat(
            [
                self.compute_similarities(docs),
                self.compute_diversities(docs),
            ],
            axis=1,
        )

        # Ensure metrics are normalized, before combining them into a composite score
        scores = pd.DataFrame(
            RobustScaler().fit_transform(scores), columns=scores.columns
        )
        scores["composite"] = scores.sum(axis=1)
        return scores

    def compute_similarities(self, docs: Corpus) -> pd.DataFrame:
        similarities = pd.DataFrame()  # of shape (n_docs, n_metrics)
        if (
            self.similarity_metrics is None
        ):  # Short-circuit function to avoid unnecessary computations
            return similarities

        term_dists = np.stack([self.to_term_dist(doc) for doc in docs], axis=0)

        for metric in self.similarity_metrics:
            sim_func = similarity_func_factory(metric)
            similarities[metric] = sim_func(
                term_dists, self.ft_term_dist_.reshape(1, -1)
            )

        return similarities

    def compute_diversities(self, docs: Corpus) -> pd.DataFrame:
        diversities = pd.DataFrame()  # of shape (n_docs, n_metrics)
        if self.diversity_metrics is None:
            return diversities

        tokenized_docs: List[List[Token]] = [
            self.tokenizer.tokenize(doc) for doc in docs
        ]

        for metric in self.diversity_metrics:
            div_func = diversity_func_factory(
                metric,
                train_term_dist=self.ft_term_dist_,
                vocab2id=self.tokenizer.vocab,
            )
            diversities[metric] = pd.Series(
                (div_func(tokenized_doc) for tokenized_doc in tokenized_docs)
            )

        return diversities