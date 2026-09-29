def constraint(*ids):
    """Mark a test as confirming one or more safety constraints."""
    def wrap(fn):
        fn.constraint_ids = ids
        return fn
    return wrap
