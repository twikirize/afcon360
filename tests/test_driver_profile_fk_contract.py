from app.transport.models import DriverProfile


def test_driver_profile_user_id_has_one_named_cascade_fk():
    table = DriverProfile.__table__

    user_id_fks = [
        constraint
        for constraint in table.foreign_key_constraints
        if tuple(column.name for column in constraint.columns) == ("user_id",)
    ]

    assert len(user_id_fks) == 1

    fk = user_id_fks[0]
    assert fk.name == "fk_driver_user"
    assert fk.ondelete == "CASCADE"
    assert tuple(
        element.target_fullname for element in fk.elements
    ) == ("users.id",)

    assert table.c.user_id.nullable is False
    assert table.c.user_id.unique is True