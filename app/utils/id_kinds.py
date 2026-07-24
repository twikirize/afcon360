from enum import Enum


class IDKind(str, Enum):
    INTERNAL_FK = "internal_fk"          # BIGINT, real DB FK, same-tier table
                                          # (users/orgs/accounts)
    CROSS_MODULE_REF = "cross_module"    # BIGINT or string, logically points at
                                          # another module's table, deliberately
                                          # has NO db-level FK
    EXTERNAL_STRING_ID = "external_str"  # provider/webhook/txn reference,
                                          # format is opaque
    PUBLIC_ID = "public_id"              # UUID string for public exposure


def id_kind_of(column) -> str:
    """
    Read classification off a SQLAlchemy column. Defaults to INTERNAL_FK for
    BigInteger/Integer columns and EXTERNAL_STRING_ID for String/Text columns
    with no explicit tag, so nothing already working changes behavior yet.
    """
    if column is None:
        return IDKind.INTERNAL_FK
    tagged = column.info.get("id_kind")
    if tagged:
        return tagged
    from sqlalchemy import String, Text
    if isinstance(column.type, (String, Text)):
        return IDKind.EXTERNAL_STRING_ID
    return IDKind.INTERNAL_FK
