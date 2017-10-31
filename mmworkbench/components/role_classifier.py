# -*- coding: utf-8 -*-
"""
This module contains the role classifier component of the Workbench natural language processor.
"""
from __future__ import absolute_import, unicode_literals
from builtins import super

import logging
import os

from sklearn.externals import joblib

from ..models import create_model, ENTITY_EXAMPLE_TYPE, CLASS_LABEL_TYPE
from ..core import Query

from .classifier import Classifier, ClassifierConfig
from ._config import get_classifier_config

logger = logging.getLogger(__name__)


class RoleClassifier(Classifier):
    """A role classifier is used to determine the target role for entities in a given query. It is
    trained using all the labeled queries for a particular intent. The labels are the role names
    associated with each entity within each query.

    Attributes:
        domain (str): The domain that this role classifier belongs to
        intent (str): The intent that this role classifier belongs to
        entity_type (str): The entity type that this role classifier is for
        roles (set): A set containing the roles which can be classified
    """

    CLF_TYPE = 'role'

    def __init__(self, resource_loader, domain, intent, entity_type):
        """Initializes a role classifier

        Args:
            resource_loader (ResourceLoader): An object which can load resources for the classifier
            domain (str): The domain that this role classifier belongs to
            intent (str): The intent that this role classifier belongs to
            entity_type (str): The entity type that this role classifier is for
        """
        super().__init__(resource_loader)
        self.domain = domain
        self.intent = intent
        self.entity_type = entity_type
        self.roles = set()

    def _get_model_config(self, **kwargs):
        """Gets a machine learning model configuration

        Returns:
            ModelConfig: The model configuration corresponding to the provided config name
        """
        kwargs['example_type'] = ENTITY_EXAMPLE_TYPE
        kwargs['label_type'] = CLASS_LABEL_TYPE
        loaded_config = get_classifier_config(self.CLF_TYPE, self._resource_loader.app_path,
                                              domain=self.domain, intent=self.intent,
                                              entity=self.entity_type)
        return super()._get_model_config(loaded_config, **kwargs)

    def fit(self, queries=None, label_set='train', previous_model_path=None, **kwargs):
        """Trains a statistical model for role classification using the provided training examples

        Args:
            queries (list of ProcessedQuery): The labeled queries to use as training data
            label_set (list, optional): A label set to load. If not specified, the default
                training set will be loaded.
            previous_model_path (str, optional): The path of a previous version of the model for
                this classifier. If the previous model is equivalent to the new one, it will be
                loaded instead. Equivalence here is determined by the model's training data and
                configuration.
        """
        logger.info('Fitting role classifier: domain=%r, intent=%r, entity_type=%r',
                    self.domain, self.intent, self.entity_type)

        # create model with given params
        model_config = self._get_model_config(**kwargs)
        model = create_model(model_config)
        new_hash = self._get_model_hash(model_config, queries, label_set)

        if previous_model_path:
            old_hash = self._load_hash(previous_model_path)
            if old_hash == new_hash:
                logger.info('No need to fit. Loading previous model.')
                self.load(previous_model_path)
                return

        # Load labeled data
        examples, labels = self._get_queries_and_labels(queries, label_set=label_set)

        if examples:
            # Build roles set
            self.roles = set()
            for label in labels:
                self.roles.add(label)

            model.initialize_resources(self._resource_loader, queries, labels)
            model.fit(examples, labels)
            self._model = model
            self.config = ClassifierConfig.from_model_config(self._model.config)
        self.hash = new_hash

        self.ready = True
        self.dirty = True

    def dump(self, model_path):
        """Persists the trained role classification model to disk.

        Args:
            model_path (str): The location on disk where the model should be stored
        """
        logger.info('Saving role classifier: domain=%r, intent=%r, entity_type=%r',
                    self.domain, self.intent, self.entity_type)
        # make directory if necessary
        folder = os.path.dirname(model_path)
        if not os.path.isdir(folder):
            os.makedirs(folder)

        rc_data = {'model': self._model, 'roles': self.roles}
        joblib.dump(rc_data, model_path)

        hash_path = model_path + '.hash'
        with open(hash_path, 'w') as hash_file:
            hash_file.write(self.hash)

        self.dirty = False

    def load(self, model_path):
        """Loads the trained role classification model from disk

        Args:
            model_path (str): The location on disk where the model is stored
        """
        logger.info('Loading role classifier: domain=%r, intent=%r, entity_type=%r',
                    self.domain, self.intent, self.entity_type)
        try:
            rc_data = joblib.load(model_path)
            self._model = rc_data['model']
            self.roles = rc_data['roles']
        except (OSError, IOError):
            logger.error('Unable to load %s. Pickle file cannot be read from %r',
                         self.__class__.__name__, model_path)
            return
            # msg = 'Unable to load {}. Pickle file cannot be read from {!r}'
            # raise ClassifierLoadError(msg.format(self.__class__.__name__, model_path))
        if self._model is not None:
            gazetteers = self._resource_loader.get_gazetteers()
            self._model.register_resources(gazetteers=gazetteers)
            self.config = ClassifierConfig.from_model_config(self._model.config)
            self.hash = self._load_hash(model_path)

        self.ready = True
        self.dirty = False

    def predict(self, query, entities, entity_index):
        """Predicts a role for the given entity using the trained role classification model

        Args:
            query (Query): The input query
            entities (list): The entities in the query
            entity_index (int): The index of the entity whose role should be classified

        Returns:
            str: The predicted role for the provided entity
        """
        if not self._model:
            logger.error('You must fit or load the model before running predict')
            return
        if not isinstance(query, Query):
            query = self._resource_loader.query_factory.create_query(query)
        gazetteers = self._resource_loader.get_gazetteers()
        self._model.register_resources(gazetteers=gazetteers)
        return self._model.predict([(query, entities, entity_index)])[0]

    def predict_proba(self, query, entities, entity_index):
        """Runs prediction on a given entity and generates multiple role hypotheses with their
        associated probabilities using the trained role classification model

        Args:
            query (Query): The input query
            entities (list): The entities in the query
            entity_index (int): The index of the entity whose role should be classified

        Returns:
            list: a list of tuples of the form (str, float) grouping roles and their probabilities
        """
        raise NotImplementedError

    def _get_query_tree(self, queries=None, label_set='train', raw=False):
        """Returns the set of queries to train on

        Args:
            queries (list, optional): A list of ProcessedQuery objects, to
                train. If not specified, a label set will be loaded.
            label_set (list, optional): A label set to load. If not specified,
                the default training set will be loaded.
            raw (bool, optional): When True, raw query strings will be returned

        Returns:
            List: list of queries
        """
        if queries:
            # TODO: should we filter these by domain?
            return self._build_query_tree(queries, raw=raw)

        return self._resource_loader.get_labeled_queries(domain=self.domain, intent=self.intent,
                                                         label_set=label_set, raw=raw)

    def _get_queries_and_labels(self, queries=None, label_set='train'):
        """Returns a set of queries and their labels based on the label set

        Args:
            queries (list, optional): A list of ProcessedQuery objects, to
                train on. If not specified, a label set will be loaded.
            label_set (list, optional): A label set to load. If not specified,
                the default training set will be loaded.
        """
        query_tree = self._get_query_tree(queries, label_set=label_set)
        queries = self._resource_loader.flatten_query_tree(query_tree)

        # build list of examples -- entities of this role classifier's type
        examples = []
        labels = []
        for query in queries:
            for idx, entity in enumerate(query.entities):
                if entity.entity.type == self.entity_type and entity.entity.role:
                    examples.append((query.query, query.entities, idx))
                    labels.append(entity.entity.role)

        unique_labels = set(labels)
        if len(unique_labels) == 1:
            # No roles
            return (), ()
        if None in unique_labels:
            bad_examples = [e for i, e in enumerate(examples) if labels[i] is None]
            for example in bad_examples:
                logger.error('Invalid entity annotation, expecting role in query %r', example[0])
            raise ValueError('One or more invalid entity annotations, expecting role')

        return examples, labels

    def _get_queries_and_labels_hash(self, queries=None, label_set='train'):
        query_tree = self._get_query_tree(queries, label_set=label_set, raw=True)
        queries = self._resource_loader.flatten_query_tree(query_tree)
        queries.sort()
        return self._resource_loader.hash_queries(queries)
