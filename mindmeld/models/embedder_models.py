# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Cisco Systems, Inc. and others.  All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module contains the embedder model class.
"""
from abc import ABC, abstractmethod
import pickle
import logging
import os

from .. import path
from .helpers import register_embedder

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    logger.warning("Must install the extra [bert] to use the built in embbedder.")


class Embedder(ABC):
    """
    Base class for embedder model
    """

    def __init__(self, app_path, embedder_type, **kwargs):
        """Initializes an embedder.
        """
        self.cache_path = path.get_embedder_cache_file_path(app_path, embedder_type)

        folder = os.path.dirname(self.cache_path)
        if not os.path.isdir(folder):
            os.makedirs(folder)

        if not os.path.exists(self.cache_path) or os.path.getsize(self.cache_path) == 0:
            self.cache = {}
        else:
            with open(self.cache_path, "rb") as fp:
                self.cache = pickle.load(fp)

        self.model = self.load(**kwargs)

    @abstractmethod
    def load(self, **kwargs):
        """Loads the embedder model

        Returns:
            The model object.
        """
        pass

    @abstractmethod
    def encode(self, text_list):
        """
        Args:
            text_list (list): A list of text strings for which to generate the embeddings.

        Returns:
            (np.array): A numpy 2-D array of the embeddings.
        """
        # TODO: check return type
        pass

    def clear_cache(self):
        """Deletes the cache file.
        """
        if os.path.exists(self.cache_path):
            os.remove(self.cache_path)

    def get_encodings(self, text_list):
        """Fetches the encoded values from the cache, or generates them.
        Args:
            text_list (list): A list of text strings for which to get the embeddings.

        Returns:
            (list): A list of numpy arrays with the embeddings.
        """
        encoded = [self.cache.get(text, None) for text in text_list]
        cache_miss_indices = [i for i, vec in enumerate(encoded) if vec is None]
        text_to_encode = [text_list[i] for i in cache_miss_indices]
        model_encoded_text = self.encode(text_to_encode)

        for i, v in enumerate(cache_miss_indices):
            encoded[v] = model_encoded_text[i]
            self.cache[text_to_encode[i]] = model_encoded_text[i]
        return encoded

    def dump(self):
        """Dumps the cache to disk.
        """
        with open(self.cache_path, "wb") as fp:
            pickle.dump(self.cache, fp)


class BertEmbedder(Embedder):
    """
    Encoder class for bert models as described here: https://github.com/UKPLab/sentence-transformers
    """

    def load(self, **kwargs):
        DEFAULT_BERT = "bert-base-nli-mean-tokens"
        if "trained_data" in kwargs:
            return SentenceTransformer(kwargs["trained_data"])
        else:
            logger.warning("No bert model specifications passed, using default.")
            return SentenceTransformer(DEFAULT_BERT)

    def encode(self, text_list):
        return self.model.encode(text_list)


register_embedder("bert", BertEmbedder)
