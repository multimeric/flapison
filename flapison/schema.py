# -*- coding: utf-8 -*-

"""Helpers to deal with marshmallow schemas"""

from marshmallow import class_registry
from marshmallow.base import SchemaABC
from marshmallow_jsonapi.fields import Relationship, List, Nested

from flapison.exceptions import InvalidInclude


def compute_schema(schema_cls, default_kwargs, qs, include):
    """Compute a schema around compound documents and sparse fieldsets

    :param Schema schema_cls: the schema class
    :param dict default_kwargs: the schema default kwargs
    :param QueryStringManager qs: qs
    :param list include: the relation field to include data from

    :return Schema schema: the schema computed
    """
    # manage include_data parameter of the schema
    schema_kwargs = default_kwargs
    schema_kwargs["include_data"] = tuple()

    # collect sub-related_includes
    related_includes = {}

    if include:
        for include_path in include:
            field = include_path.split(".")[0]

            if field not in schema_cls._declared_fields:
                raise InvalidInclude(
                    "{} has no attribute {}".format(schema_cls.__name__, field)
                )
            elif not isinstance(schema_cls._declared_fields[field], Relationship):
                raise InvalidInclude(
                    "{} is not a relationship attribute of {}".format(
                        field, schema_cls.__name__
                    )
                )

            schema_kwargs["include_data"] += (field,)
            if field not in related_includes:
                related_includes[field] = []
            if "." in include_path:
                related_includes[field] += [".".join(include_path.split(".")[1:])]

    # manage only parameter of the schema
    only = schema_kwargs.get("only")

    # collect sub-related_only
    related_only = {}
    if only is not None:
        for only_path in only:
            if "." not in only_path:
                continue
            field = only_path.split(".")[0]
            if field not in related_only:
                related_only[field] = []
            related_only[field] += [".".join(only_path.split(".")[1:])]

    # manage sparse fieldsets
    if schema_cls.Meta.type_ in qs.fields:
        tmp_only = set(schema_cls._declared_fields.keys()) & set(qs.fields[schema_cls.Meta.type_])
        if only is not None:
            tmp_only &= set(only)
        only = tuple(tmp_only)

    if only is not None and "id" not in only:
        # make sure id field is in only parameter unless marshamllow will raise an Exception
        only += ("id",)

    # collect sub-related_exclude
    related_exclude = {}
    if schema_kwargs.get("exclude") is not None:
        for exclude_path in schema_kwargs["exclude"]:
            if "." not in exclude_path:
                continue
            field = exclude_path.split(".")[0]
            if field not in related_exclude:
                related_exclude[field] = []
            related_exclude[field] += [".".join(exclude_path.split(".")[1:])]

    # create base schema instance
    schema_kwargs["only"] = only
    schema = schema_cls(**schema_kwargs)

    # manage compound documents
    if include:
        for include_path in include:
            field = include_path.split(".")[0]
            relation_field = schema.declared_fields[field]
            related_schema_cls = schema.declared_fields[field].__dict__[
                "_Relationship__schema"
            ]
            related_schema_kwargs = {}
            if "context" in default_kwargs:
                related_schema_kwargs["context"] = default_kwargs["context"]

            if isinstance(related_schema_cls, SchemaABC):
                related_schema_kwargs["only"] = related_schema_cls.only
                related_schema_kwargs["exclude"] = related_schema_cls.exclude
                related_schema_kwargs["many"] = related_schema_cls.many
                related_schema_cls = related_schema_cls.__class__

            if isinstance(related_schema_cls, str):
                related_schema_cls = class_registry.get_class(related_schema_cls)

            if hasattr(relation_field, "only"):
                related_schema_kwargs["only"] = relation_field.only

            if hasattr(relation_field, "exclude"):
                related_schema_kwargs["exclude"] = relation_field.exclude

            if related_only.get(field) is not None:
                tmp_only = set(related_only[field])
                if related_schema_kwargs.get("only") is not None:
                    tmp_only &= set(related_schema_kwargs["only"])
                related_schema_kwargs["only"] = tuple(tmp_only)

            if related_exclude.get(field) is not None:
                tmp_exclude = set(related_exclude[field])
                if related_schema_kwargs.get("exclude") is not None:
                    tmp_exclude |= set(related_schema_kwargs["exclude"])
                related_schema_kwargs["exclude"] = tuple(tmp_exclude)

            related_schema = compute_schema(
                related_schema_cls,
                related_schema_kwargs,
                qs,
                related_includes[field] or None,
            )
            relation_field.__dict__["_Relationship__schema"] = related_schema

    return schema


def get_model_field(schema, field):
    """Get the model field of a schema field

    :param Schema schema: a marshmallow schema
    :param str field: the name of the schema field
    :return str: the name of the field in the model
    """
    if schema._declared_fields.get(field) is None:
        raise Exception("{} has no attribute {}".format(schema.__name__, field))

    if schema._declared_fields[field].attribute is not None:
        return schema._declared_fields[field].attribute
    return field


def get_nested_fields(schema, model_field=False):
    """Return nested fields of a schema to support a join

    :param Schema schema: a marshmallow schema
    :param boolean model_field: whether to extract the model field for the nested fields
    :return list: list of nested fields of the schema
    """

    nested_fields = []
    for (key, value) in schema._declared_fields.items():
        if isinstance(value, List) and isinstance(value.inner, Nested):
            nested_fields.append(key)
        elif isinstance(value, Nested):
            nested_fields.append(key)

    if model_field is True:
        nested_fields = [get_model_field(schema, key) for key in nested_fields]

    return nested_fields


def get_relationships(schema, model_field=False):
    """Return relationship fields of a schema

    :param Schema schema: a marshmallow schema
    :param list: list of relationship fields of a schema
    """
    relationships = [
        key
        for (key, value) in schema._declared_fields.items()
        if isinstance(value, Relationship)
    ]

    if model_field is True:
        relationships = [get_model_field(schema, key) for key in relationships]

    return relationships


def get_related_schema(schema, field):
    """Retrieve the related schema of a relationship field

    :param Schema schema: the schema to retrieve le relationship field from
    :param field: the relationship field
    :return Schema: the related schema
    """
    return schema._declared_fields[field].__dict__["_Relationship__schema"]


def get_schema_from_type(resource_type):
    """Retrieve a schema from the registry by his type

    :param str type_: the type of the resource
    :return Schema: the schema class
    """
    for cls_name, cls in class_registry._registry.items():
        try:
            if cls[0].opts.type_ == resource_type:
                return cls[0]
        except Exception:
            pass

    raise Exception("Couldn't find schema for type: {}".format(resource_type))


def get_schema_field(schema, field):
    """Get the schema field of a model field

    :param Schema schema: a marshmallow schema
    :param str field: the name of the model field
    :return str: the name of the field in the schema
    """
    schema_fields_to_model = {
        key: get_model_field(schema, key)
        for (key, value) in schema._declared_fields.items()
    }
    for key, value in schema_fields_to_model.items():
        if value == field:
            return key

    raise Exception("Couldn't find schema field from {}".format(field))
